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

    # Embed a list of chunks in bounded batches, inserting each batch as it is encoded.
    # Caps peak memory (one batch of vectors at a time) and keeps each Qdrant upsert small
    # enough to stay under request-size limits — essential for very large documents.
    # Each batch is retried with exponential backoff on transient errors (e.g. a Qdrant
    # network blip), so one hiccup doesn't fail the whole document. A dimension mismatch is
    # permanent and is not retried. Inserts only (no delete) so callers control deletion.
    async def _embed_in_batches(self, document_id: str, chunks: list) -> int:
        batch_size = max(1, self.settings.embed_batch_size)
        max_retries = self.settings.embed_max_retries
        base_delay = self.settings.embed_retry_base_delay
        total = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c.text for c in batch]
            attempt = 0
            while True:
                try:
                    vectors = await self._embed_texts(texts)
                    if vectors and len(vectors[0]) != self.settings.embedding_dim:
                        raise ValueError(
                            f"Embedding dim {len(vectors[0])} != configured {self.settings.embedding_dim}")
                    sparse_vectors = await asyncio.to_thread(self.sparse.encode, texts)
                    await self.store.insert(document_id, batch, vectors, sparse_vectors)
                    break
                except ValueError:
                    raise  # config/dimension mismatch is permanent — don't retry
                except Exception as exc:
                    attempt += 1
                    if attempt > max_retries:
                        logger.error("Batch at offset %d failed after %d retries for %s: %s",
                                     i, max_retries, document_id, exc)
                        raise
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning("Batch at offset %d failed (attempt %d/%d) for %s: %s; retrying in %.1fs",
                                   i, attempt, max_retries, document_id, exc, delay)
                    await asyncio.sleep(delay)
            total += len(batch)
            logger.info("Embedded %d/%d chunks for %s", total, len(chunks), document_id)
        return total

    # Embed an explicit list of chunks and INSERT them (no full-document delete).
    # Used by incremental re-indexing to embed only the changed pages' chunks.
    # The caller is responsible for deleting stale page vectors first.
    async def embed_chunks(self, document_id: str, chunks: list) -> int:
        if not chunks:
            return 0
        await self.store.ensure_collection()
        n = await self._embed_in_batches(document_id, chunks)
        logger.info("Embedded %d chunk(s) for %s (incremental)", n, document_id)
        return n

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
        # Resumable embed: skip chunks already stored under the CURRENT model with identical
        # text (matched by chunk_id + text hash), and embed only the rest. This means a retry
        # after a partial/failed embed picks up where it left off instead of redoing
        # everything, while a model switch or changed text still forces a re-embed.
        existing = await self.store.existing_chunk_hashes(document_id)
        pending = [c for c in chunked.chunks
                   if existing.get(c.chunk_id) != self.store.text_hash(c.text)]
        if pending:
            await self._embed_in_batches(document_id, pending)
        # Remove stale points whose chunk_id is no longer in the document (old chunking /
        # removed pages / previous model), so the stored set matches the current chunks.
        await self.store.delete_orphans(document_id, {c.chunk_id for c in chunked.chunks})
        record.status = DocumentStatus.embedded
        await self.ingestion.save_record(record)
        skipped = len(chunked.chunks) - len(pending)
        logger.info("Embedded %s: %d (re)embedded, %d resumed/unchanged (total %d)",
                    document_id, len(pending), skipped, len(chunked.chunks))
        return len(chunked.chunks)