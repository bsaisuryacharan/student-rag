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
from app.schemas import DocumentStatus
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


@celery_app.task(name="ping")
def ping() -> str:
    return "pong"
