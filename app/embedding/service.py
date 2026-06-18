# app/embedding/service.py
import asyncio
import logging

from app.config import Settings
from app.embedding.dense import DenseEncoder
from app.embedding.sparse import SparseEncoder
from app.ingestion.service import IngestionService
from app.schemas import ChunkedDocument, DocumentStatus
from app.storage import CHUNKS_BLOB
from app.store.qdrant_store import VectorStore

logger = logging.getLogger("app.embedding")


class EmbeddingService:

    def __init__(self, settings: Settings, dense_encoder: DenseEncoder,
                 vector_store: VectorStore, ingestion: IngestionService,
                 sparse_encoder: SparseEncoder) -> None:
        self.settings = settings
        self.dense = dense_encoder
        self.store = vector_store
        self.ingestion = ingestion
        self.sparse = sparse_encoder

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.dense.encode, texts)

    # The embed_document method is responsible for taking a document ID, retrieving the corresponding DocumentRecord, and then processing the chunked document to generate vector embeddings for each chunk of text. It first checks if the document has been chunked by looking for the chunks.json file. If the file exists, it reads the chunked document and uses the _embed_texts method to generate embeddings for each chunk of text. The resulting vectors are then upserted into the Qdrant vector database using the VectorStore's upsert method. Finally, it updates the status of the document to "embedded" and returns the number of chunks that were embedded. If the document is not found, not chunked, or if there are no chunks to embed, appropriate errors are raised.
    async def embed_document(self, document_id: str) -> int:
        record = await self.ingestion.get(document_id)
        if record is None:
            raise FileNotFoundError(document_id)
        chunks_blob = await self.ingestion.storage.get_blob(document_id, CHUNKS_BLOB)
        if chunks_blob is None:
            raise ValueError("Document not chunked yet")

        chunked = ChunkedDocument.model_validate_json(chunks_blob)
        if not chunked.chunks:
            raise ValueError("No chunks to embed")

        await self.store.ensure_collection()
        texts = [c.text for c in chunked.chunks]
        vectors = await self._embed_texts(texts)
        if vectors and len(vectors[0]) != self.settings.embedding_dim:
            raise ValueError(f"Embedding dim {len(vectors[0])} != configured {self.settings.embedding_dim}")
        # Sparse (BM25) encoding is CPU-bound; run it in a thread so the event loop isn't blocked
        sparse_vectors = await asyncio.to_thread(self.sparse.encode, texts)

        await self.store.upsert(document_id, chunked.chunks, vectors, sparse_vectors)
        record.status = DocumentStatus.embedded
        await self.ingestion.save_record(record)
        logger.info("Embedded %s: %d chunks", document_id, len(chunked.chunks))
        return len(chunked.chunks)