# app/retrieval/service.py
import logging

from openai import AsyncOpenAI

from app.config import Settings
from app.schemas import RetrievedChunk
from app.store.qdrant_store import VectorStore

logger = logging.getLogger("app.retrieval")


class RetrievalService:
    def __init__(self, settings: Settings, openai: AsyncOpenAI, vector_store: VectorStore) -> None:
        self.settings = settings
        self.openai = openai
        self.store = vector_store

    # The _embed_query method is responsible for generating a vector embedding for a given query string using the OpenAI API. It sends the query to the embeddings endpoint and retrieves the resulting embedding vector, which can then be used for similarity search in the vector database.
    async def _embed_query(self, query: str) -> list[float]:
        resp = await self.openai.embeddings.create(
            model=self.settings.embedding_model, input=[query])
        return resp.data[0].embedding


    # The search method is responsible for performing a similarity search in the Qdrant vector database based on a given query string. It first generates an embedding for the query using the _embed_query method, and then uses the VectorStore's search method to retrieve relevant chunks of text that are similar to the query embedding. The search can be filtered by subject, document_id, or chapter if specified. The results are returned as a list of RetrievedChunk objects, which include the chunk text, metadata, and similarity score. The method also logs the number of hits returned for the query.
    async def search(self, query: str, top_k: int | None = None, *,
                     subject: str | None = None, document_id: str | None = None,
                     chapter: str | None = None) -> list[RetrievedChunk]:
        k = top_k or self.settings.retrieval_top_k
        vector = await self._embed_query(query)
        points = await self.store.search(
            vector, k, subject=subject, document_id=document_id, chapter=chapter,
            score_threshold=self.settings.retrieval_min_score)

        results: list[RetrievedChunk] = []
        for p in points:
            pl = p.payload or {}
            results.append(RetrievedChunk(
                chunk_id=pl.get("chunk_id"), text=pl.get("text", ""), score=p.score,
                document_id=pl.get("document_id"), document_name=pl.get("document_name"),
                subject=pl.get("subject"), chapter=pl.get("chapter"), page=pl.get("page"),
            ))
        logger.info("Query '%s' -> %d hits", query[:60], len(results))
        return results