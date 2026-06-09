# app/api/ingestion.py
import logging
from fastapi import APIRouter, UploadFile, File, Form, Request, HTTPException, status

from app.errors import UnsupportedFileTypeError, FileTooLargeError
from app.ingestion.service import IngestionService
from app.schemas import UploadResponse, DocumentRecord

logger = logging.getLogger("app.api.ingestion")
router = APIRouter(prefix="/documents", tags=["documents"])

READ_CHUNK = 1024 * 1024  # 1 MiB
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