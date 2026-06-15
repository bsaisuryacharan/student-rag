# app/worker/tasks.py
from app.worker.celery_app import celery_app
# app/worker/tasks.py
import asyncio
import logging

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient

from app.config import get_settings
from app.storage import LocalStorage
from app.store.qdrant_store import VectorStore
from app.embedding.sparse import SparseEncoder
from app.ingestion.service import IngestionService
from app.parsing.service import ParsingService
from app.chunking.service import ChunkingService
from app.embedding.service import EmbeddingService
from app.schemas import DocumentStatus

logger = logging.getLogger("app.worker")
# Loaded ONCE per worker process (BM25 model is expensive to construct)
_settings = get_settings()
_sparse_encoder = SparseEncoder(_settings.sparse_model)


async def _process(document_id: str) -> None:
    openai = AsyncOpenAI(api_key=_settings.openai_api_key, timeout=30, max_retries=2)
    qdrant = AsyncQdrantClient(url=_settings.qdrant_url, api_key=_settings.qdrant_api_key or None, timeout=30)
    try:
        storage = LocalStorage(_settings.data_dir)
        vector_store = VectorStore(qdrant, _settings)
        ingestion = IngestionService(_settings, storage)
        parsing = ParsingService(_settings, openai, ingestion)
        chunking = ChunkingService(_settings, ingestion)
        embedding = EmbeddingService(_settings, openai, vector_store, ingestion, _sparse_encoder)

        await parsing.parse(document_id)              # status -> parsed
        chunking.chunk(document_id)                   # status -> chunked (sync)
        await embedding.embed_document(document_id)   # status -> embedded
    finally:
        await qdrant.close()
        await openai.close()

@celery_app.task(name="process_document")
def process_document(document_id: str) -> dict:
    logger.info("Processing document %s", document_id)
    try:
        asyncio.run(_process(document_id))
        return {"document_id": document_id, "status": "embedded"}
    except Exception as exc:                          # noqa: BLE001
        logger.exception("Processing failed for %s", document_id)
        ingestion = IngestionService(_settings, LocalStorage(_settings.data_dir))
        record = ingestion.get(document_id)
        if record is not None:
            record.status = DocumentStatus.failed
            record.error = str(exc)                   # the user-facing note
            ingestion.save_record(record)
        raise

@celery_app.task(name="ping")
def ping() -> str:
    return "pong"