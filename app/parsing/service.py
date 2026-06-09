# app/parsing/service.py
import logging
from pathlib import Path

from openai import AsyncOpenAI

from app.config import Settings
from app.ingestion.service import IngestionService
from app.parsing import parsers
from app.schemas import DocumentStatus, ParsedDocument


logger = logging.getLogger("app.parsing")

class ParsingService:
    def __init__(self, settings: Settings, openai: AsyncOpenAI, ingestion: IngestionService) -> None:
        self.settings = settings
        self.openai = openai
        self.ingestion = ingestion

    def _parsed_path(self, document_id: str) -> Path:
        return Path(self.settings.data_dir) / "raw" / document_id / "parsed.json"

    async def parse(self, document_id: str) -> ParsedDocument:
        record = self.ingestion.get(document_id)
        if record is None:
            raise FileNotFoundError(document_id)
        # Extract file extension to determine which parser to use
        ext = Path(record.document_name).suffix.lower()
        try:
            # Route to appropriate parser based on file type (sync or async)
            if ext == ".txt":
                pages = parsers.parse_txt(record.storage_path)
            elif ext in (".docx", ".doc"):
                pages = parsers.parse_docx(record.storage_path)
            elif ext == ".pdf":
                pages = await parsers.parse_pdf(
                    record.storage_path, openai=self.openai,
                    vision_model=self.settings.vision_model,
                    min_chars=self.settings.pdf_text_min_chars)
            elif ext in (".png", ".jpg", ".jpeg"):
                pages = await parsers.parse_image(
                    record.storage_path, openai=self.openai,
                    vision_model=self.settings.vision_model)
            else:
                raise ValueError(f"No parser for {ext}")
            parsed = ParsedDocument(
                document_id=record.document_id, document_name=record.document_name,
                subject=record.subject, pages=pages)
            # Persist parsed result and update document status to "parsed"
            self._parsed_path(document_id).write_text(parsed.model_dump_json(indent=2), encoding="utf-8")
            record.status = DocumentStatus.parsed
            self.ingestion.save_record(record)
            logger.info("Parsed %s: %d pages", document_id, len(pages))
            return parsed
        except Exception:
            # Mark document as failed and persist status for audit trail
            record.status = DocumentStatus.failed
            self.ingestion.save_record(record)
            logger.exception("Parsing failed for %s", document_id)
            raise