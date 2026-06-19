# app/parsing/service.py
import hashlib
import logging
from pathlib import Path

from openai import AsyncOpenAI

from app.config import Settings
from app.ingestion.service import IngestionService
from app.parsing import parsers
from app.schemas import DocumentStatus, ParsedDocument
from app.storage import RAW_BLOB, PARSED_BLOB


logger = logging.getLogger("app.parsing")


def hash_pages(parsed: ParsedDocument) -> dict[str, str]:
    """Per-page content fingerprint: {page number (as str) -> sha256 of page text}.
    Used by incremental re-indexing to detect exactly which pages changed."""
    return {
        str(page.page): hashlib.sha256(page.text.encode("utf-8")).hexdigest()
        for page in parsed.pages
    }

class ParsingService:
    def __init__(self, settings: Settings, openai: AsyncOpenAI, ingestion: IngestionService) -> None:
        self.settings = settings
        self.openai = openai
        self.ingestion = ingestion
        self.storage = ingestion.storage

    async def parse(self, document_id: str) -> ParsedDocument:
        record = await self.ingestion.get(document_id)
        if record is None:
            raise FileNotFoundError(document_id)
        # The original file lives in the cloud document store; pull its bytes for parsing
        raw = await self.storage.get_blob(document_id, RAW_BLOB)
        if raw is None:
            raise FileNotFoundError(document_id)
        # Extract file extension to determine which parser to use
        ext = Path(record.document_name).suffix.lower()
        try:
            # Route to appropriate parser based on file type (sync or async)
            if ext == ".txt":
                pages = parsers.parse_txt(raw)
            elif ext in (".docx", ".doc"):
                pages = parsers.parse_docx(raw)
            elif ext == ".pdf":
                pages = await parsers.parse_pdf(
                    raw, openai=self.openai,
                    vision_model=self.settings.vision_model,
                    min_chars=self.settings.pdf_text_min_chars)
            elif ext in (".png", ".jpg", ".jpeg"):
                pages = await parsers.parse_image(
                    raw, openai=self.openai,
                    vision_model=self.settings.vision_model)
            else:
                raise ValueError(f"No parser for {ext}")
            parsed = ParsedDocument(
                document_id=record.document_id, document_name=record.document_name,
                subject=record.subject, pages=pages)
            # Persist parsed result to the cloud store and update document status to "parsed"
            await self.storage.put_blob(
                document_id, PARSED_BLOB, parsed.model_dump_json(indent=2).encode("utf-8"))
            record.status = DocumentStatus.parsed
            record.page_count = len(pages)
            # Fingerprint each page so a later re-upload can diff page-by-page
            record.page_hashes = hash_pages(parsed)
            await self.ingestion.save_record(record)
            logger.info("Parsed %s: %d pages", document_id, len(pages))
            return parsed
        except Exception:
            # Mark document as failed and persist status for audit trail
            record.status = DocumentStatus.failed
            await self.ingestion.save_record(record)
            logger.exception("Parsing failed for %s", document_id)
            raise
