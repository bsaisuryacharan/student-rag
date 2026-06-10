# app/chunking/service.py
import logging
from pathlib import Path

from app.chunking.chunker import SemanticChunker
from app.config import Settings
from app.ingestion.service import IngestionService
from app.schemas import ChunkedDocument, DocumentStatus, ParsedDocument

logger = logging.getLogger("app.chunking")

class ChunkingService:
    def __init__(self, settings: Settings, ingestion: IngestionService) -> None:
        self.settings = settings
        self.ingestion = ingestion
        self.chunker = SemanticChunker(settings)

    def _doc_dir(self, document_id: str) -> Path:
        return Path(self.settings.data_dir) / "raw" / document_id


    # The chunk method is responsible for taking a document ID, retrieving the corresponding DocumentRecord, and then processing the parsed document to create chunks of text. It first checks if the document has been parsed by looking for the parsed.json file. If the file exists, it reads the parsed document and uses the SemanticChunker to create chunks based on the content of the parsed document and the upload date. The resulting chunks are then saved as a JSON file in the same directory as the original document. Finally, it updates the status of the document to "chunked" and returns a ChunkedDocument object containing the chunks that were created.
    def chunk(self, document_id: str) -> ChunkedDocument:
        record = self.ingestion.get(document_id)
        if record is None:
            raise FileNotFoundError(document_id)
        parsed_path = self._doc_dir(document_id) / "parsed.json"
        if not parsed_path.exists():
            raise ValueError("Document not parsed yet")

        parsed = ParsedDocument.model_validate_json(parsed_path.read_text(encoding="utf-8"))
        chunks = self.chunker.chunk(parsed, record.upload_date)
        chunked = ChunkedDocument(
            document_id=record.document_id, document_name=record.document_name,
            subject=record.subject, chunks=chunks)

        (self._doc_dir(document_id) / "chunks.json").write_text(
            chunked.model_dump_json(indent=2), encoding="utf-8")
        record.status = DocumentStatus.chunked
        self.ingestion.save_record(record)
        logger.info("Chunked %s into %d chunks", document_id, len(chunks))
        return chunked