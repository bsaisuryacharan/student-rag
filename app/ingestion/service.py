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


# The IngestionService class is responsible for handling the ingestion of documents into the system. It takes care of validating the file type, saving the file using the provided storage mechanism, and creating a record of the document in the system. The ingest method is the main entry point for ingesting a document, and it returns a DocumentRecord that contains information about the ingested document. The get method allows retrieval of a DocumentRecord by its document ID.
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

    # The ingest method is responsible for handling the ingestion of a document. It first sanitizes the filename, validates the file type, generates a unique document ID, and then attempts to save the file using the storage mechanism. If the file exceeds the maximum allowed size, it cleans up any partially written data and raises an error. Finally, it creates a DocumentRecord with all the relevant information about the ingested document and saves it as a JSON manifest for later retrieval.
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
        self.save_record(record)
        logger.info("Stored document %s (%s, %d bytes)", document_id, filename, stored.size_bytes)
        return record
    
    # The get method retrieves a DocumentRecord by its document ID. It checks if a manifest file exists for the given document ID, and if it does, it reads the JSON content of the manifest and returns a DocumentRecord object. If the manifest file does not exist, it returns None, indicating that no record was found for the given document ID.
    def get(self, document_id: str) -> DocumentRecord | None:
        p = self._manifest_path(document_id)
        if not p.exists():
            return None
        return DocumentRecord.model_validate_json(p.read_text(encoding="utf-8"))
    # The save_record method is responsible for saving a DocumentRecord to the manifest file. It takes a DocumentRecord object as input and writes its JSON representation to the manifest file corresponding to the document ID. This method can be used to update the status or other information of a document record after it has been ingested or processed further in the system.
    def save_record(self, record: DocumentRecord) -> None:
            self._manifest_path(record.document_id).write_text(
                record.model_dump_json(indent=2), encoding="utf-8")