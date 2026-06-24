# app/chunking/chunker.py
from datetime import datetime

import tiktoken

from app.config import Settings
from app.schemas import Chunk, ChunkMetadata, ParsedDocument


class FixedChunker:
    def __init__(self, settings: Settings) -> None:
        self.enc = tiktoken.get_encoding("cl100k_base")
        self.target = settings.chunk_target_tokens
        self.overlap = settings.chunk_overlap_pct

    def chunk(self, parsed: ParsedDocument, upload_date: datetime, user_id: str | None = None) -> list[Chunk]:
        chunks: list[Chunk] = []
        stride = self.target - self.overlap

        for page in parsed.pages:
            tokens = self.enc.encode(page.text)
            if not tokens:
                continue

            page_num = page.page
            page_label = f"[Page {page_num}]"

            for i, start in enumerate(range(0, len(tokens), stride)):
                window = tokens[start : start + self.target]
                chunks.append(Chunk(
                    chunk_id=f"{parsed.document_id}:p{page_num}:{i}",
                    text=f"{page_label}\n{self.enc.decode(window)}",
                    metadata=ChunkMetadata(
                        document_name=parsed.document_name,
                        subject=parsed.subject,
                        chapter=page.chapter_hint,
                        page=page_num,
                        upload_date=upload_date,
                        user_id=user_id,
                    ),
                ))
        return chunks
