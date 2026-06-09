# app/schemas.py
from datetime import datetime
from pydantic import BaseModel
from enum import Enum

# As per the scenario, since students was the audience of this app, we are creating a schema for the chunks of the documents that will be stored in the vector database. The ChunkMetadata class contains information about the document from which the chunk was created, such as the document name, subject, chapter, page number, and upload date. 
# The Chunk class contains the chunk ID, the text of the chunk, and the metadata associated with it. This schema will be used to structure the data that we store in the vector database and to ensure that we have all the necessary information about each chunk for later retrieval and use in generating answers to user queries. 
class ChunkMetadata(BaseModel):
    document_name: str
    subject: str | None = None
    chapter: str | None = None
    page: int | None = None
    upload_date: datetime


class Chunk(BaseModel):
    chunk_id: str            # stable, unique, e.g. f"{document_id}:{index}"
    text: str
    metadata: ChunkMetadata

class DocumentStatus(str, Enum):
    uploaded = "uploaded"
    parsed = "parsed"
    chunked = "chunked"
    embedded = "embedded"
    failed = "failed"

class DocumentRecord(BaseModel):
    document_id: str
    document_name: str            # sanitized original filename
    subject: str | None = None
    content_type: str | None = None
    size_bytes: int
    sha256: str
    storage_path: str
    status: DocumentStatus = DocumentStatus.uploaded
    upload_date: datetime
    page_count: int | None = None

class UploadResponse(BaseModel):
    document_id: str
    document_name: str
    status: DocumentStatus
    size_bytes: int

class PageUnit(BaseModel):
    page: int
    text: str
    chapter_hint: str | None = None


class ParsedDocument(BaseModel):
    document_id: str
    document_name: str
    subject: str | None = None
    pages: list[PageUnit]