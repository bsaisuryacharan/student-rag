# app/storage.py
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Protocol

import aiofiles

from app.errors import FileTooLargeError

@dataclass
class StoredFile:
    path: str
    size_bytes: int
    sha256: str

class Storage(Protocol):
    async def save(self, document_id: str, filename: str,
                   chunks: AsyncIterator[bytes], max_bytes: int) -> StoredFile: ...
    def cleanup(self, document_id: str) -> None: ...

class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _dir(self, document_id: str) -> Path:
        return self.root / "raw" / document_id
    
    async def save(self, document_id: str, filename: str,
                   chunks: AsyncIterator[bytes], max_bytes: int) -> StoredFile:
        dest_dir = self._dir(document_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        hasher = hashlib.sha256()
        size = 0
        async with aiofiles.open(dest, "wb") as f:
            async for chunk in chunks:
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLargeError(f"File exceeds {max_bytes} bytes")
                hasher.update(chunk)
                await f.write(chunk)
        return StoredFile(path=str(dest), size_bytes=size, sha256=hasher.hexdigest())
    
    def cleanup(self, document_id: str) -> None:
        d = self._dir(document_id)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)