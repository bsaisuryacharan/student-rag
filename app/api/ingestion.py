# app/api/ingestion.py
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, UploadFile, File, Form, Request, HTTPException, status
from fastapi.responses import StreamingResponse
from app.parsing.service import ParsingService
from app.storage import PARSED_BLOB, CHUNKS_BLOB
from app.schemas import ParsedDocument
from app.chunking.service import ChunkingService
from app.schemas import ChunkedDocument

from app.errors import UnsupportedFileTypeError, FileTooLargeError, DuplicateDocumentError
from app.ingestion.service import IngestionService
from app.schemas import UploadResponse, DocumentRecord, DocumentStatus
from app.embedding.service import EmbeddingService
from app.auth import require_admin, get_current_user
from typing import Annotated
from app.worker.tasks import process_document, update_document

logger = logging.getLogger("app.api.ingestion")
router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_admin)])

READ_CHUNK = 1024 * 1024  # 1 MiB
# Generator that yields file in 1MB chunks to handle large uploads without loading entire file into memory
async def _file_chunks(upload: UploadFile):
    while chunk := await upload.read(READ_CHUNK):
        yield chunk

@router.post("",
             summary="Upload a document (streams processing status via SSE)",
             response_description="Server-Sent Events: first event is upload confirmation, then one event per processing stage until embedded or failed.")
async def upload_document(
    request: Request,
    user: Annotated[dict, Depends(require_admin)],
    file: UploadFile = File(...),
    subject: str | None = Form(default=None),
):
    """
    Upload a document and receive a **Server-Sent Events** stream that tracks every
    processing stage on the same connection:

    1. `uploaded` — file saved, Celery task queued
    2. `parsed`   — text extracted from PDF/DOCX
    3. `chunked`  — split into overlapping token windows
    4. `embedded` — vectors stored in Qdrant (stream closes)
    5. `failed`   — something went wrong (stream closes, error included)

    > **Swagger note:** Swagger collects all events and shows them together once the
    > stream closes. For live updates use:
    > `curl -N -H "Authorization: Bearer <token>" -F "file=@doc.pdf" http://localhost:8000/v1/documents`
    """
    service = IngestionService(request.app.state.settings, request.app.state.storage)
    try:
        record = await service.ingest(
            filename=file.filename or "upload",
            content_type=file.content_type,
            chunks=_file_chunks(file),
            subject=subject,
            user_id=user.get("sub"),
        )
    except UnsupportedFileTypeError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except FileTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e))
    except DuplicateDocumentError as e:
        raise HTTPException(status_code=409, detail=str(e))
    finally:
        await file.close()

    process_document.delay(record.document_id)
    logger.info("Queued processing for document %s", record.document_id)

    base = str(request.base_url).rstrip("/")
    raw_token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    ingestion = IngestionService(request.app.state.settings, request.app.state.storage)

    async def event_generator():
        doc_url = f"{base}/v1/documents/{record.document_id}"
        token_qs = f"?token={raw_token}" if raw_token else ""
        # Event 1: upload confirmed — document saved and queued for processing
        yield f"data: {json.dumps({'status': 'uploaded', 'document_id': record.document_id, 'document_name': record.document_name, 'size_bytes': record.size_bytes, 'status_url': f'{doc_url}{token_qs}', 'stream_url': f'{doc_url}/status-stream{token_qs}', 'message': 'Processing started (parse → chunk → embed). Final status below.'})}\n\n"

        # Poll silently — only surface the terminal result (embedded or failed)
        # parsed and chunked are internal pipeline stages; not shown to the caller
        terminal = {"embedded", "failed"}
        while True:
            await asyncio.sleep(2)
            current = await ingestion.get(record.document_id)
            if current is None:
                break
            if current.status.value in terminal:
                payload = {"status": current.status.value, "document_id": record.document_id}
                if current.error:
                    payload["error"] = current.error
                yield f"data: {json.dumps(payload)}\n\n"
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Endpoint to list all documents that have been uploaded to the system. It scans the stored manifests and returns the full DocumentRecord for each document (id, name, subject, size, status, upload date, etc.), sorted by upload date with the most recent first.
@router.get("", response_model=list[DocumentRecord])
async def list_documents(request: Request, user: Annotated[dict, Depends(get_current_user)]):
    service = IngestionService(request.app.state.settings, request.app.state.storage)
    return await service.list_all(user_id=user.get("sub"))


@router.delete("", summary="Clear all documents (admin reset)",
               response_description="Number of documents cleared and Qdrant collection recreated.")
async def clear_all_documents(request: Request, user: Annotated[dict, Depends(require_admin)]):
    """
    **Admin-only.** Deletes every document — raw files, parsed JSON, chunks, and all
    Qdrant vectors — then recreates the empty collection so you can start fresh.

    Use this to reset the system between test runs.
    """
    ingestion = IngestionService(request.app.state.settings, request.app.state.storage)
    records = await ingestion.list_all()  # all docs, no user filter

    # Remove all blobs (raw file + manifest + parsed + chunks) for every document
    for record in records:
        await request.app.state.storage.cleanup(record.document_id)

    # Drop and recreate the vector collection — fastest way to wipe all embeddings
    vector_store = request.app.state.vector_store
    if await vector_store.client.collection_exists(vector_store.collection):
        await vector_store.client.delete_collection(vector_store.collection)
    await vector_store.ensure_collection()

    logger.info("Cleared %d document(s) and recreated vector collection", len(records))
    return {
        "cleared": len(records),
        "message": f"Deleted {len(records)} document(s). Vector collection recreated and ready.",
    }


@router.get("/{document_id}", response_model=DocumentRecord)
async def get_document(request: Request, document_id: str, user: Annotated[dict, Depends(get_current_user)]):
    service = IngestionService(request.app.state.settings, request.app.state.storage)
    record = await service.get(document_id)
    sub = user.get("sub")
    if record is None or (record.user_id is not None and record.user_id != sub):
        raise HTTPException(status_code=404, detail="Document not found")
    return record


@router.put("/{document_id}", summary="Upload a new version of a document (incremental re-index)")
async def update_document_version(
    request: Request,
    document_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    file: UploadFile = File(...),
):
    """
    Replace a document's file with an updated version and **re-index only the pages
    that changed**. The new file is parsed and diffed page-by-page against the previous
    version; only changed/added pages are re-embedded and removed pages are dropped.
    Unchanged pages keep their existing vectors, so updating one page of a large
    document costs roughly one page of work instead of the whole document.
    """
    service = IngestionService(request.app.state.settings, request.app.state.storage)
    record = await service.get(document_id)
    sub = user.get("sub")
    if record is None or (record.user_id is not None and record.user_id != sub):
        raise HTTPException(status_code=404, detail="Document not found")

    # Overwrite the raw blob with the new bytes (reuses the size-limit + hashing path).
    # We deliberately skip the sha256 duplicate check here — changed content is the point.
    max_bytes = request.app.state.settings.max_upload_mb * 1024 * 1024
    try:
        stored = await request.app.state.storage.save(
            document_id, record.document_name, _file_chunks(file), max_bytes)
    except FileTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e))
    finally:
        await file.close()

    if stored.sha256 == record.sha256:
        return {"document_id": document_id, "status": record.status.value,
                "message": "Uploaded file is identical to the current version; nothing to re-index."}

    record.sha256 = stored.sha256
    record.size_bytes = stored.size_bytes
    record.status = DocumentStatus.queued
    await service.save_record(record)

    update_document.delay(document_id)
    logger.info("Queued incremental update for document %s", document_id)
    return {
        "document_id": document_id,
        "status": "queued",
        "message": "New version queued for incremental re-index (only changed pages will be re-embedded). "
                   "Track progress via GET /v1/documents/{id} or the status-stream endpoint.",
    }


@router.delete("/{document_id}", summary="Delete a single document")
async def delete_document(request: Request, document_id: str,
                          user: Annotated[dict, Depends(get_current_user)]):
    """
    Delete a single document: removes all blobs (raw file, parsed, chunks)
    and all vectors from Qdrant.  Users can only delete their own documents;
    admins can delete any document.
    """
    ingestion = IngestionService(request.app.state.settings, request.app.state.storage)
    record = await ingestion.get(document_id)
    sub = user.get("sub")
    is_admin = user.get("role") == "admin" or sub in (request.app.state.settings.admin_emails or [])

    if record is None or (not is_admin and record.user_id is not None and record.user_id != sub):
        raise HTTPException(status_code=404, detail="Document not found")

    await request.app.state.storage.cleanup(document_id)
    await request.app.state.vector_store.delete_document(document_id)

    logger.info("Deleted document %s (%s)", document_id, record.document_name)
    return {"deleted": document_id, "document_name": record.document_name}


@router.get("/{document_id}/status-stream",
            summary="Stream processing status (SSE)",
            response_description="Server-Sent Events — one event per status change until embedded or failed")
async def stream_status(request: Request, document_id: str,
                        user: Annotated[dict, Depends(get_current_user)]):
    """
    Opens a Server-Sent Events stream that emits one JSON event each time the
    document status changes.  Closes automatically when status reaches
    **embedded** or **failed**.

    > **Swagger note:** Swagger shows all events together after the stream
    > closes. For live updates use:
    > `curl -N -H "Authorization: Bearer <token>" http://localhost:8000/v1/documents/{id}/status-stream`
    """
    ingestion = IngestionService(request.app.state.settings, request.app.state.storage)

    async def event_generator():
        last_status = None
        terminal = {"embedded", "failed"}
        sub = user.get("sub")
        while True:
            record = await ingestion.get(document_id)
            if record is None:
                logger.warning("stream_status: document %s not found in storage", document_id)
                yield f"data: {json.dumps({'error': 'Document not found'})}\n\n"
                break
            if record.user_id is not None and record.user_id != sub:
                logger.warning("stream_status: user_id mismatch for %s (record=%s, user=%s)",
                               document_id, record.user_id, sub)
                yield f"data: {json.dumps({'error': 'Document not found'})}\n\n"
                break
            current = record.status.value
            if current != last_status:
                last_status = current
                payload = {"status": current, "document_id": document_id}
                if record.error:
                    payload["error"] = record.error
                yield f"data: {json.dumps(payload)}\n\n"
            if current in terminal:
                break
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Endpoint to trigger parsing of an uploaded document. It retrieves the document record, determines the appropriate parser based on file type, and processes the document to extract text content. The parsed result is saved, and the document status is updated accordingly. If the document is not found or if parsing fails, appropriate HTTP errors are returned.
@router.post("/{document_id}/parse", include_in_schema=False)
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

# Endpoint to retrieve the parsed content of a document. It fetches the parsed blob from the cloud document store, and if it exists, returns it as a ParsedDocument object. If the parsed content is not found, it returns a 404 error.
@router.get("/{document_id}/parsed", response_model=ParsedDocument, include_in_schema=False)
async def get_parsed(request: Request, document_id: str):
    blob = await request.app.state.storage.get_blob(document_id, PARSED_BLOB)
    if blob is None:
        raise HTTPException(status_code=404, detail="Parsed content not found")
    return ParsedDocument.model_validate_json(blob)


# Endpoint to trigger chunking of a parsed document. It retrieves the document record and checks if the document has been parsed. If the parsed content exists, it uses the ChunkingService to create chunks from the parsed document and saves the chunks as a JSON file. The document status is updated to "chunked". If the document is not found or if the document has not been parsed yet, appropriate HTTP errors are returned.
@router.post("/{document_id}/chunk", include_in_schema=False)
async def chunk_document(request: Request, document_id: str):
    ingestion = IngestionService(request.app.state.settings, request.app.state.storage)
    service = ChunkingService(request.app.state.settings, ingestion)
    try:
        chunked = await service.chunk(document_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))   # parse it first
    return {"document_id": document_id, "status": "chunked", "chunks": len(chunked.chunks)}


# Endpoint to retrieve the chunks of a document. It fetches the chunks blob from the cloud document store, and if it exists, returns it as a ChunkedDocument object. If the chunks are not found, it returns a 404 error.
@router.get("/{document_id}/chunks", response_model=ChunkedDocument, include_in_schema=False)
async def get_chunks(request: Request, document_id: str):
    blob = await request.app.state.storage.get_blob(document_id, CHUNKS_BLOB)
    if blob is None:
        raise HTTPException(status_code=404, detail="Chunks not found")
    return ChunkedDocument.model_validate_json(blob)


# Endpoint to trigger embedding of a chunked document. It retrieves the document record and checks if the document has been chunked. If the chunks exist, it uses the EmbeddingService to generate vector embeddings for each chunk and upserts them into the vector database. The document status is updated to "embedded". If the document is not found, not chunked, or if there are no chunks to embed, appropriate HTTP errors are returned.
@router.post("/{document_id}/embed", include_in_schema=False)
async def embed_document(request: Request, document_id: str):
    ingestion = IngestionService(request.app.state.settings, request.app.state.storage)
    service = EmbeddingService(
        request.app.state.settings, request.app.state.dense_encoder,
        request.app.state.vector_store, ingestion, request.app.state.sparse_encoder)
    try:
        n = await service.embed_document(document_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))   # chunk it first
    return {"document_id": document_id, "status": "embedded", "chunks_embedded": n}


@router.get("/{document_id}/vector-count", include_in_schema=False)
async def vector_count(request: Request, document_id: str):
    n = await request.app.state.vector_store.count(document_id)
    return {"document_id": document_id, "vectors": n}