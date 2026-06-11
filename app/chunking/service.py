# app/chunking/service.py
import logging

from app.chunking.chunker import SemanticChunker
from app.config import Settings
from app.ingestion.service import IngestionService
from app.schemas import ChunkedDocument, DocumentStatus, ParsedDocument
from app.storage import PARSED_BLOB, CHUNKS_BLOB

logger = logging.getLogger("app.chunking")

class ChunkingService:
    def __init__(self, settings: Settings, ingestion: IngestionService) -> None:
        self.settings = settings
        self.ingestion = ingestion
        self.storage = ingestion.storage
        self.chunker = SemanticChunker(settings)

    # The chunk method is responsible for taking a document ID, retrieving the corresponding DocumentRecord, and then processing the parsed document to create chunks of text. It first checks if the document has been parsed by fetching the parsed blob from the cloud document store. If the blob exists, it reads the parsed document and uses the SemanticChunker to create chunks based on the content of the parsed document and the upload date. The resulting chunks are then saved as the chunks blob in the same store. Finally, it updates the status of the document to "chunked" and returns a ChunkedDocument object containing the chunks that were created.
    async def chunk(self, document_id: str) -> ChunkedDocument:
        record = await self.ingestion.get(document_id)
        if record is None:
            raise FileNotFoundError(document_id)
        parsed_blob = await self.storage.get_blob(document_id, PARSED_BLOB)
        if parsed_blob is None:
            raise ValueError("Document not parsed yet")

        parsed = ParsedDocument.model_validate_json(parsed_blob)
        chunks = self.chunker.chunk(parsed, record.upload_date)
        chunked = ChunkedDocument(
            document_id=record.document_id, document_name=record.document_name,
            subject=record.subject, chunks=chunks)

        await self.storage.put_blob(
            document_id, CHUNKS_BLOB, chunked.model_dump_json(indent=2).encode("utf-8"))
        record.status = DocumentStatus.chunked
        await self.ingestion.save_record(record)
        logger.info("Chunked %s into %d chunks", document_id, len(chunks))
        return chunked
