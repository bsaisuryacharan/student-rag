# app/worker/tasks.py
import asyncio
import logging

from billiard.exceptions import SoftTimeLimitExceeded
from qdrant_client import AsyncQdrantClient

from app.config import get_settings
from app.clients import build_qdrant_client, build_openai_client
from app.storage import QdrantStorage
from app.store.qdrant_store import VectorStore
from app.embedding.sparse import SparseEncoder
from app.embedding.dense import DenseEncoder
from app.ingestion.service import IngestionService
from app.parsing.service import ParsingService
from app.chunking.service import ChunkingService
from app.embedding.service import EmbeddingService
from app.schemas import DocumentStatus, ChunkedDocument
from app.storage import CHUNKS_BLOB
from app.worker.celery_app import celery_app

logger = logging.getLogger("app.worker")

# Loaded once per worker process — expensive to initialise
_settings = get_settings()
_sparse_encoder = SparseEncoder(_settings.sparse_model)
_dense_encoder = DenseEncoder(_settings.embedding_model)


async def _process(document_id: str) -> None:
    openai = build_openai_client(_settings)
    qdrant = build_qdrant_client(_settings)
    try:
        storage = QdrantStorage(qdrant, _settings)
        vector_store = VectorStore(qdrant, _settings)
        ingestion = IngestionService(_settings, storage)
        parsing = ParsingService(_settings, openai, ingestion)
        chunking = ChunkingService(_settings, ingestion)
        embedding = EmbeddingService(_settings, _dense_encoder, vector_store, ingestion, _sparse_encoder)

        await parsing.parse(document_id)
        await chunking.chunk(document_id)
        await embedding.embed_document(document_id)
    finally:
        await qdrant.close()
        await openai.close()


async def _update(document_id: str) -> None:
    """
    Incremental re-index. The new file has already been written over the document's
    raw blob. We re-parse it, diff each page's content hash against the previous
    version, and then touch ONLY what changed:
      - changed/added pages -> delete their old vectors, re-embed their new chunks
      - removed pages        -> delete their vectors
      - unchanged pages      -> left exactly as they are (no re-embed)
    Re-parsing and re-chunking are cheap/local; the saving is in not re-embedding and
    not re-uploading every unchanged page's vectors.
    """
    openai = build_openai_client(_settings)
    qdrant = build_qdrant_client(_settings)
    try:
        storage = QdrantStorage(qdrant, _settings)
        vector_store = VectorStore(qdrant, _settings)
        ingestion = IngestionService(_settings, storage)
        parsing = ParsingService(_settings, openai, ingestion)
        chunking = ChunkingService(_settings, ingestion)
        embedding = EmbeddingService(_settings, _dense_encoder, vector_store, ingestion, _sparse_encoder)

        before = await ingestion.get(document_id)
        if before is None:
            raise FileNotFoundError(document_id)
        old_hashes = dict(before.page_hashes)   # snapshot BEFORE parse overwrites it

        # Re-parse (refreshes page_hashes) and re-chunk the full new document.
        await parsing.parse(document_id)
        await chunking.chunk(document_id)

        after = await ingestion.get(document_id)
        new_hashes = after.page_hashes

        # Diff by page number: a page is "changed" if its hash differs or it's new.
        changed = sorted(int(p) for p, h in new_hashes.items() if old_hashes.get(p) != h)
        removed = sorted(int(p) for p in old_hashes if p not in new_hashes)

        if not changed and not removed:
            after.status = DocumentStatus.embedded
            await ingestion.save_record(after)
            logger.info("Update %s: no page changes detected; nothing re-embedded", document_id)
            return

        # Drop vectors for changed + removed pages, then embed only the changed pages.
        await vector_store.delete_pages(document_id, changed + removed)

        chunks_blob = await storage.get_blob(document_id, CHUNKS_BLOB)
        chunked = ChunkedDocument.model_validate_json(chunks_blob)
        changed_set = set(changed)
        to_embed = [c for c in chunked.chunks if c.metadata.page in changed_set]
        await embedding.embed_chunks(document_id, to_embed)

        after.status = DocumentStatus.embedded
        await ingestion.save_record(after)
        logger.info("Update %s: re-embedded pages %s, removed pages %s (%d chunks touched)",
                    document_id, changed, removed, len(to_embed))
    finally:
        await qdrant.close()
        await openai.close()


async def _mark_failed(document_id: str, error: str) -> None:
    qdrant = build_qdrant_client(_settings)
    try:
        storage = QdrantStorage(qdrant, _settings)
        ingestion = IngestionService(_settings, storage)
        record = await ingestion.get(document_id)
        if record is not None:
            record.status = DocumentStatus.failed
            record.error = error
            await ingestion.save_record(record)
    finally:
        await qdrant.close()


@celery_app.task(name="process_document")
def process_document(document_id: str) -> dict:
    logger.info("Processing document %s", document_id)
    try:
        asyncio.run(_process(document_id))
        return {"document_id": document_id, "status": "embedded"}
    except SoftTimeLimitExceeded:
        msg = "Processing timed out (document too large or embedding took too long)"
        logger.error("Soft time limit exceeded for %s", document_id)
        asyncio.run(_mark_failed(document_id, msg))
        raise
    except Exception as exc:
        logger.exception("Processing failed for %s", document_id)
        asyncio.run(_mark_failed(document_id, str(exc)))
        raise


@celery_app.task(name="update_document")
def update_document(document_id: str) -> dict:
    logger.info("Incrementally updating document %s", document_id)
    try:
        asyncio.run(_update(document_id))
        return {"document_id": document_id, "status": "embedded"}
    except SoftTimeLimitExceeded:
        msg = "Update timed out (document too large or embedding took too long)"
        logger.error("Soft time limit exceeded updating %s", document_id)
        asyncio.run(_mark_failed(document_id, msg))
        raise
    except Exception as exc:
        logger.exception("Update failed for %s", document_id)
        asyncio.run(_mark_failed(document_id, str(exc)))
        raise


@celery_app.task(name="ping")
def ping() -> str:
    return "pong"
