# app/retrieval/service.py
import asyncio
import logging

from openai import AsyncOpenAI

from app.config import Settings
from app.embedding.sparse import SparseEncoder
from app.schemas import RetrievedChunk
from app.store.qdrant_store import VectorStore

logger = logging.getLogger("app.retrieval")


class RetrievalService:
    def __init__(self, settings: Settings, openai: AsyncOpenAI,
                 vector_store: VectorStore, sparse_encoder: SparseEncoder) -> None:
        self.settings = settings
        self.openai = openai
        self.store = vector_store
        self.sparse = sparse_encoder

    # The _embed_query method is responsible for generating a vector embedding for a given query string using the OpenAI API. It sends the query to the embeddings endpoint and retrieves the resulting embedding vector, which can then be used for similarity search in the vector database.
    async def _embed_query(self, query: str) -> list[float]:
        resp = await self.openai.embeddings.create(
            model=self.settings.embedding_model, input=[query])
        return resp.data[0].embedding


    # The search method performs a hybrid search in the Qdrant vector database for a given query string. It generates a dense embedding via OpenAI and a sparse (BM25) embedding via the SparseEncoder, then calls the VectorStore's hybrid_search, which fuses both result lists with Reciprocal Rank Fusion (RRF). The search can be filtered by subject, document_id, or chapter. Results come back as RetrievedChunk objects with the chunk text, metadata, and fused score. Note: RRF scores are rank-based (not cosine similarity), so retrieval_min_score does not apply here.
    async def search(self, query: str, top_k: int | None = None, *,
                     subject: str | None = None, document_id: str | None = None,
                     chapter: str | None = None) -> list[RetrievedChunk]:
        k = top_k or self.settings.retrieval_top_k
        # Dense embedding is network I/O, sparse encoding is CPU-bound — run the
        # sparse one in a thread so the event loop isn't blocked
        dense_vec = await self._embed_query(query)
        sparse_vec = await asyncio.to_thread(self.sparse.encode_one, query)

        points = await self.store.hybrid_search(
            dense_vec, sparse_vec, k,
            subject=subject, document_id=document_id, chapter=chapter,
            prefetch_limit=self.settings.hybrid_prefetch_limit)

        results: list[RetrievedChunk] = []
        for p in points:
            pl = p.payload or {}
            results.append(RetrievedChunk(
                chunk_id=pl.get("chunk_id"), text=pl.get("text", ""), score=p.score,
                document_id=pl.get("document_id"), document_name=pl.get("document_name"),
                subject=pl.get("subject"), chapter=pl.get("chapter"), page=pl.get("page"),
            ))
        logger.info("Hybrid query '%s' -> %d hits", query[:60], len(results))
        return results
