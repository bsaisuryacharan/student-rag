# app/ingestion/service.py
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from app.config import Settings
from app.errors import UnsupportedFileTypeError, FileTooLargeError
from app.schemas import DocumentRecord, DocumentStatus
from app.storage import Storage

logger = logging.getLogger("app.ingestion")

def _safe_filename(name: str) -> str:
    return Path(name).name.replace("\\", "_")   # strip any path components


class IngestionService:
    def __init__(self, settings: Settings, storage: Storage) -> None:
        self.settings = settings
        self.storage = storage

    def _validate_type(self, filename: str) -> None:
        ext = Path(filename).suffix.lower()
        if ext not in self.settings.allowed_extensions:
            raise UnsupportedFileTypeError(f"Unsupported file type: {ext or 'unknown'}")

    def _manifest_path(self, document_id: str) -> Path:
        return Path(self.settings.data_dir) / "raw" / document_id / "manifest.json"

    async def ingest(self, filename: str, content_type: str | None,
                     chunks: AsyncIterator[bytes], subject: str | None = None) -> DocumentRecord:
        filename = _safe_filename(filename)
        self._validate_type(filename)
        document_id = uuid.uuid4().hex
        max_bytes = self.settings.max_upload_mb * 1024 * 1024
        try:
            stored = await self.storage.save(document_id, filename, chunks, max_bytes)
        except FileTooLargeError:
            self.storage.cleanup(document_id)   # remove partial write
            raise
        record = DocumentRecord(
            document_id=document_id, document_name=filename, subject=subject,
            content_type=content_type, size_bytes=stored.size_bytes, sha256=stored.sha256,
            storage_path=stored.path, status=DocumentStatus.uploaded,
            upload_date=datetime.now(timezone.utc),
        )
        self._manifest_path(document_id).write_text(record.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Stored document %s (%s, %d bytes)", document_id, filename, stored.size_bytes)
        return record
    
    def get(self, document_id: str) -> DocumentRecord | None:
        p = self._manifest_path(document_id)
        if not p.exists():
            return None
        return DocumentRecord.model_validate_json(p.read_text(encoding="utf-8"))