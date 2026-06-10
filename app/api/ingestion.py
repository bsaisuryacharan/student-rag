# app/api/ingestion.py
import logging
from fastapi import APIRouter, UploadFile, File, Form, Request, HTTPException, status
from pathlib import Path
from app.parsing.service import ParsingService
from app.schemas import ParsedDocument
from app.chunking.service import ChunkingService
from app.schemas import ChunkedDocument

from app.errors import UnsupportedFileTypeError, FileTooLargeError
from app.ingestion.service import IngestionService
from app.schemas import UploadResponse, DocumentRecord

logger = logging.getLogger("app.api.ingestion")
router = APIRouter(prefix="/documents", tags=["documents"])

READ_CHUNK = 1024 * 1024  # 1 MiB
# Generator that yields file in 1MB chunks to handle large uploads without loading entire file into memory
async def _file_chunks(upload: UploadFile):
    while chunk := await upload.read(READ_CHUNK):
        yield chunk

@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    subject: str | None = Form(default=None),
):
    service = IngestionService(request.app.state.settings, request.app.state.storage)
    try:
        # Stream file in chunks to service for storage and validation
        record = await service.ingest(
            filename=file.filename or "upload",
            content_type=file.content_type,
            chunks=_file_chunks(file),
            subject=subject,
        )
    except UnsupportedFileTypeError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except FileTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e))
    finally:
        # Ensure file handle is always closed, even on error
        await file.close()

    return UploadResponse(
        document_id=record.document_id, document_name=record.document_name,
        status=record.status, size_bytes=record.size_bytes,
    )

@router.get("/{document_id}", response_model=DocumentRecord)
async def get_document(request: Request, document_id: str):
    service = IngestionService(request.app.state.settings, request.app.state.storage)
    record = service.get(document_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return record

# Endpoint to trigger parsing of an uploaded document. It retrieves the document record, determines the appropriate parser based on file type, and processes the document to extract text content. The parsed result is saved, and the document status is updated accordingly. If the document is not found or if parsing fails, appropriate HTTP errors are returned.
@router.post("/{document_id}/parse")
async def parse_document(request: Request, document_id: str):
    ingestion = IngestionService(request.app.state.settings, request.app.state.storage)
    service = ParsingService(request.app.state.settings, request.app.state.openai, ingestion)
    try:
        parsed = await service.parse(document_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document_id": document_id, "status": "parsed",
        "pages": len(parsed.pages),
        "chars": sum(len(p.text) for p in parsed.pages),
    }

# Endpoint to retrieve the parsed content of a document. It checks if the parsed JSON file exists for the given document ID, and if it does, it reads and returns the parsed content as a ParsedDocument object. If the parsed content is not found, it returns a 404 error.
@router.get("/{document_id}/parsed", response_model=ParsedDocument)
async def get_parsed(request: Request, document_id: str):
    p = Path(request.app.state.settings.data_dir) / "raw" / document_id / "parsed.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Parsed content not found")
    return ParsedDocument.model_validate_json(p.read_text(encoding="utf-8"))


# Endpoint to trigger chunking of a parsed document. It retrieves the document record and checks if the document has been parsed. If the parsed content exists, it uses the ChunkingService to create chunks from the parsed document and saves the chunks as a JSON file. The document status is updated to "chunked". If the document is not found or if the document has not been parsed yet, appropriate HTTP errors are returned.
@router.post("/{document_id}/chunk")
async def chunk_document(request: Request, document_id: str):
    ingestion = IngestionService(request.app.state.settings, request.app.state.storage)
    service = ChunkingService(request.app.state.settings, ingestion)
    try:
        chunked = service.chunk(document_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))   # parse it first
    return {"document_id": document_id, "status": "chunked", "chunks": len(chunked.chunks)}


# Endpoint to retrieve the chunks of a document. It checks if the chunks JSON file exists for the given document ID, and if it does, it reads and returns the chunked content as a ChunkedDocument object. If the chunks are not found, it returns a 404 error.
@router.get("/{document_id}/chunks", response_model=ChunkedDocument)
async def get_chunks(request: Request, document_id: str):
    p = Path(request.app.state.settings.data_dir) / "raw" / document_id / "chunks.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Chunks not found")
    return ChunkedDocument.model_validate_json(p.read_text(encoding="utf-8"))