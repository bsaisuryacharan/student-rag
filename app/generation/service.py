# app/generation/service.py
import logging

from openai import AsyncOpenAI

from app.config import Settings
from app.retrieval.service import RetrievalService
from app.schemas import AnswerResponse, Citation, RetrievedChunk

logger = logging.getLogger("app.generation")

SYSTEM_PROMPT = (
    "You are a study assistant that answers questions using ONLY the provided context "
    "taken from the student's own documents.\n"
    "Rules:\n"
    "- Use ONLY the context below. Never use outside knowledge or guess.\n"
    "- If the answer is not in the context, reply exactly: "
    "\"I couldn't find that in your documents.\"\n"
    "- Each context block is labelled with its source and page number. "
    "When the user's question mentions a specific SET, page, chapter, part, or section "
    "(e.g. 'Set 1', 'page two', 'Part B', 'first set'), find the block whose label "
    "matches and answer ONLY from that block. Do NOT mix content from other sets or pages.\n"
    "- Cite the sources you used with bracketed numbers like [1], [2] matching the context blocks.\n"
    "- Be concise and accurate. Answer in English."
)

NOT_FOUND = "I couldn't find that in your documents."


class GenerationService:
    def __init__(self, settings: Settings, openai: AsyncOpenAI, retrieval: RetrievalService) -> None:
        self.settings = settings
        self.openai = openai
        self.retrieval = retrieval

    def _build_context(self, chunks: list[RetrievedChunk]) -> str:
        blocks = []
        for i, c in enumerate(chunks, start=1):
            src = c.document_name or "document"
            page = f", Page {c.page}" if c.page else ""
            blocks.append(f"[{i}] (Source: {src}{page})\n{c.text}")
        context = "\n\n".join(blocks)
        return context[: self.settings.max_context_chars]

    async def ask(self, question: str, top_k: int | None = None, *,
                  user_id: str | None = None, subject: str | None = None,
                  document_id: str | None = None, chapter: str | None = None) -> AnswerResponse:
        chunks = await self.retrieval.search(
            question, top_k, user_id=user_id, subject=subject, document_id=document_id, chapter=chapter)
        if not chunks:
            return AnswerResponse(question=question, answer=NOT_FOUND, citations=[])

        context = self._build_context(chunks)
        user_msg = (
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            "Answer using only the context above, and cite sources as [n]."
        )
        resp = await self.openai.chat.completions.create(
            model=self.settings.generation_model,
            temperature=self.settings.generation_temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        answer = (resp.choices[0].message.content or "").strip()
        citations = [
            Citation(index=i, document_name=c.document_name, page=c.page, chapter=c.chapter,
                     document_id=c.document_id, chunk_id=c.chunk_id, score=c.score)
            for i, c in enumerate(chunks, start=1)
        ]
        logger.info("Answered '%s' using %d chunks", question[:60], len(chunks))
        return AnswerResponse(question=question, answer=answer, citations=citations)