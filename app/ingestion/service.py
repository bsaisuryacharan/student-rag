# app/ingestion/service.py
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from app.config import Settings
from app.errors import UnsupportedFileTypeError, FileTooLargeError, DuplicateDocumentError
from app.schemas import DocumentRecord, DocumentStatus
from app.storage import Storage, MANIFEST_BLOB

logger = logging.getLogger("app.ingestion")

def _safe_filename(name: str) -> str:
    return Path(name).name.replace("\\", "_")   # strip any path components


# The IngestionService class is responsible for handling the ingestion of documents into the system. It takes care of validating the file type, saving the file using the provided storage mechanism, and creating a record of the document in the system. All persistence (the raw file and the manifest record) goes through the Storage abstraction, which keeps everything in Qdrant Cloud — nothing is written to the local filesystem. The ingest method is the main entry point for ingesting a document, and it returns a DocumentRecord that contains information about the ingested document. The get method allows retrieval of a DocumentRecord by its document ID.
class IngestionService:
    def __init__(self, settings: Settings, storage: Storage) -> None:
        self.settings = settings
        self.storage = storage

    def _validate_type(self, filename: str) -> None:
        ext = Path(filename).suffix.lower()
        if ext not in self.settings.allowed_extensions:
            raise UnsupportedFileTypeError(f"Unsupported file type: {ext or 'unknown'}")

    # The ingest method is responsible for handling the ingestion of a document. It first sanitizes the filename, validates the file type, generates a unique document ID, and then attempts to save the file using the storage mechanism. If the file exceeds the maximum allowed size, it cleans up any partially written data and raises an error. Finally, it creates a DocumentRecord with all the relevant information about the ingested document and saves it as a manifest blob in the cloud document store for later retrieval.
    async def ingest(self, filename: str, content_type: str | None,
                     chunks: AsyncIterator[bytes], subject: str | None = None,
                     user_id: str | None = None) -> DocumentRecord:
        filename = _safe_filename(filename)
        self._validate_type(filename)
        document_id = uuid.uuid4().hex
        max_bytes = self.settings.max_upload_mb * 1024 * 1024
        try:
            stored = await self.storage.save(document_id, filename, chunks, max_bytes)
        except FileTooLargeError:
            await self.storage.cleanup(document_id)   # remove partial write
            raise
        # Content-hash dedup: the sha256 is only known after the stream is fully read,
        # so the duplicate check happens post-save and the new copy is removed on a hit
        existing = await self.find_by_sha256(stored.sha256)
        if existing is not None:
            await self.storage.cleanup(document_id)
            logger.info("Rejected duplicate upload of '%s' (matches document %s)",
                        filename, existing.document_id)
            raise DuplicateDocumentError(
                f"This file was already uploaded as '{existing.document_name}' "
                f"(document_id={existing.document_id}, status={existing.status.value})",
                existing.document_id)
        record = DocumentRecord(
            document_id=document_id, document_name=filename, subject=subject,
            content_type=content_type, size_bytes=stored.size_bytes, sha256=stored.sha256,
            storage_path=stored.path, status=DocumentStatus.uploaded,
            upload_date=datetime.now(timezone.utc), user_id=user_id,
        )
        await self.save_record(record)
        logger.info("Stored document %s (%s, %d bytes)", document_id, filename, stored.size_bytes)
        return record

    # The find_by_sha256 method looks up an existing DocumentRecord by its content hash. It is used during ingestion to detect re-uploads of identical content: two files with the same sha256 are byte-for-byte the same regardless of their filename. Returns the first matching record, or None if the content has not been uploaded before.
    async def find_by_sha256(self, sha256: str) -> DocumentRecord | None:
        for record in await self.list_all():
            if record.sha256 == sha256:
                return record
        return None

    # The list_all method retrieves the DocumentRecords of every document that has been ingested into the system. It fetches every manifest blob from the cloud document store (one per document), reads each one into a DocumentRecord object, and returns them sorted by upload date with the most recent first. Manifests that cannot be read or validated are skipped with a warning rather than failing the whole listing, so one corrupt record does not break the endpoint.
    async def list_all(self, user_id: str | None = None) -> list[DocumentRecord]:
        records: list[DocumentRecord] = []
        for blob in await self.storage.list_blobs(MANIFEST_BLOB):
            try:
                record = DocumentRecord.model_validate_json(blob)
                if user_id is None or record.user_id == user_id:
                    records.append(record)
            except Exception:
                logger.warning("Skipping unreadable manifest blob")
        records.sort(key=lambda r: r.upload_date, reverse=True)
        return records

    # The get method retrieves a DocumentRecord by its document ID. It fetches the manifest blob for the given document ID from the cloud document store, and if it exists, returns it as a DocumentRecord object. If no manifest blob exists, it returns None, indicating that no record was found for the given document ID.
    async def get(self, document_id: str) -> DocumentRecord | None:
        blob = await self.storage.get_blob(document_id, MANIFEST_BLOB)
        if blob is None:
            return None
        return DocumentRecord.model_validate_json(blob)

    # The save_record method is responsible for saving a DocumentRecord to the cloud document store. It takes a DocumentRecord object as input and writes its JSON representation as the manifest blob for that document. This method can be used to update the status or other information of a document record after it has been ingested or processed further in the system.
    async def save_record(self, record: DocumentRecord) -> None:
        await self.storage.put_blob(
            record.document_id, MANIFEST_BLOB,
            record.model_dump_json(indent=2).encode("utf-8"))
