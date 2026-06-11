# app/storage.py
from __future__ import annotations

import base64
import hashlib
import uuid
from dataclasses import dataclass
from typing import AsyncIterator, Protocol

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings
from app.errors import FileTooLargeError

# Raw bytes per stored point. Base64 inflates this by ~33%, so each point payload
# stays around ~700 KB and an upsert batch stays far below Qdrant Cloud's request limit.
PART_SIZE = 512 * 1024
UPSERT_BATCH = 8

# Well-known blob names used by the pipeline (one of each per document)
RAW_BLOB = "raw"
MANIFEST_BLOB = "manifest"
PARSED_BLOB = "parsed"
CHUNKS_BLOB = "chunks"


@dataclass
class StoredFile:
    path: str
    size_bytes: int
    sha256: str


class Storage(Protocol):
    async def ensure_collection(self) -> None: ...
    async def save(self, document_id: str, filename: str,
                   chunks: AsyncIterator[bytes], max_bytes: int) -> StoredFile: ...
    async def put_blob(self, document_id: str, name: str, data: bytes) -> None: ...
    async def get_blob(self, document_id: str, name: str) -> bytes | None: ...
    async def list_blobs(self, name: str) -> list[bytes]: ...
    async def cleanup(self, document_id: str) -> None: ...


# QdrantStorage keeps every artifact of a document (the raw uploaded file plus the
# manifest/parsed/chunks JSON produced by the pipeline) inside Qdrant Cloud, so no data
# lives on the local filesystem. Qdrant is a vector database, not a blob store, so files
# are stored in a dedicated vector-less collection: each blob is split into PART_SIZE
# pieces, base64-encoded, and written as payload-only points. Point IDs are deterministic
# (uuid5 of document_id/name/part) so re-writing a blob overwrites its previous parts.
class QdrantStorage:
    def __init__(self, client: AsyncQdrantClient, settings: Settings) -> None:
        self.client = client
        self.collection = settings.docs_collection_name

    # Creates the document-store collection on first use. vectors_config={} makes it a
    # payload-only collection (no vectors stored). Keyword indexes on document_id and
    # name keep the filtered scrolls/deletes fast.
    async def ensure_collection(self) -> None:
        if await self.client.collection_exists(self.collection):
            return
        await self.client.create_collection(self.collection, vectors_config={})
        for field in ("document_id", "name"):
            await self.client.create_payload_index(
                self.collection, field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD)

    def _filter(self, document_id: str, name: str | None = None) -> models.Filter:
        must = [models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
        if name is not None:
            must.append(models.FieldCondition(key="name", match=models.MatchValue(value=name)))
        return models.Filter(must=must)

    def _point_id(self, document_id: str, name: str, part: int) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.collection}/{document_id}/{name}/{part}"))

    # Streams an upload into memory (uploads are capped at max_upload_mb, so buffering is
    # safe), enforcing the size limit and hashing as it reads, then writes the bytes to
    # the cloud as the document's "raw" blob.
    async def save(self, document_id: str, filename: str,
                   chunks: AsyncIterator[bytes], max_bytes: int) -> StoredFile:
        hasher = hashlib.sha256()
        buf = bytearray()
        async for chunk in chunks:
            buf.extend(chunk)
            if len(buf) > max_bytes:
                raise FileTooLargeError(f"File exceeds {max_bytes} bytes")
            hasher.update(chunk)
        data = bytes(buf)
        await self.put_blob(document_id, RAW_BLOB, data)
        return StoredFile(
            path=f"qdrant://{self.collection}/{document_id}/{RAW_BLOB}",
            size_bytes=len(data), sha256=hasher.hexdigest())

    # Writes (or replaces) one named blob for a document. The old parts are deleted first
    # so a shorter rewrite never leaves stale trailing parts behind, then the new parts
    # are upserted in small batches to respect request-size limits.
    async def put_blob(self, document_id: str, name: str, data: bytes) -> None:
        await self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=self._filter(document_id, name)))
        parts = [data[i:i + PART_SIZE] for i in range(0, len(data), PART_SIZE)] or [b""]
        points = [
            models.PointStruct(
                id=self._point_id(document_id, name, idx),
                vector={},
                payload={
                    "document_id": document_id, "name": name,
                    "part": idx, "parts": len(parts),
                    "data": base64.b64encode(part).decode("ascii"),
                },
            )
            for idx, part in enumerate(parts)
        ]
        for i in range(0, len(points), UPSERT_BATCH):
            await self.client.upsert(self.collection, points=points[i:i + UPSERT_BATCH])

    async def _scroll_payloads(self, qfilter: models.Filter) -> list[dict]:
        payloads: list[dict] = []
        offset = None
        while True:
            points, offset = await self.client.scroll(
                self.collection, scroll_filter=qfilter, limit=32,
                offset=offset, with_payload=True, with_vectors=False)
            payloads.extend(p.payload for p in points)
            if offset is None:
                return payloads

    # Reads one named blob back: fetch all its parts, reorder, decode, join.
    # Returns None when the blob does not exist.
    async def get_blob(self, document_id: str, name: str) -> bytes | None:
        payloads = await self._scroll_payloads(self._filter(document_id, name))
        if not payloads:
            return None
        payloads.sort(key=lambda p: p["part"])
        return b"".join(base64.b64decode(p["data"]) for p in payloads)

    # Returns the blob with the given name for every document that has one — used to
    # list all manifests without knowing the document IDs up front.
    async def list_blobs(self, name: str) -> list[bytes]:
        qfilter = models.Filter(must=[models.FieldCondition(
            key="name", match=models.MatchValue(value=name))])
        by_doc: dict[str, list[dict]] = {}
        for p in await self._scroll_payloads(qfilter):
            by_doc.setdefault(p["document_id"], []).append(p)
        blobs: list[bytes] = []
        for parts in by_doc.values():
            parts.sort(key=lambda p: p["part"])
            blobs.append(b"".join(base64.b64decode(p["data"]) for p in parts))
        return blobs

    # Removes every blob belonging to a document (raw, manifest, parsed, chunks).
    async def cleanup(self, document_id: str) -> None:
        await self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=self._filter(document_id)))
