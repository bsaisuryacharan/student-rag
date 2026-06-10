# app/chunking/chunker.py
import re
from dataclasses import dataclass
from datetime import datetime

import tiktoken

from app.config import Settings
from app.schemas import Chunk, ChunkMetadata, ParsedDocument

@dataclass
class _Segment:
    text: str
    page: int
    chapter: str | None

class SemanticChunker:
    def __init__(self, settings: Settings) -> None:
        self.enc = tiktoken.get_encoding("cl100k_base")   # matches text-embedding-3-*
        self.target = settings.chunk_target_tokens
        self.overlap = max(1, int(self.target * settings.chunk_overlap_pct / 100))

    def _ntokens(self, text: str) -> int:
        return len(self.enc.encode(text))
    
    # Below is the main method of the SemanticChunker class, which takes a ParsedDocument as input and returns a list of Chunk objects. The method first splits the parsed document into segments based on page breaks and chapter hints. It then iterates through the segments and creates chunks of text that are close to the target token count, while allowing for some overlap between chunks to maintain context. Each chunk is associated with metadata that includes the original document name, subject, chapter, page number, and upload date. Finally, the method returns a list of Chunk objects that can be stored in the vector database for later retrieval and use in generating answers to user queries.
    def _split_segments(self, parsed: ParsedDocument) -> list[_Segment]:
        segments: list[_Segment] = []
        chapter: str | None = None
        for page in parsed.pages:
            chapter = page.chapter_hint or chapter
            buf: list[str] = []
            for line in page.text.splitlines():
                s = line.strip()
                heading = re.match(r"^#{1,6}\s+(.*)", s)
                if heading:                       # heading -> new chapter + block boundary
                    if buf:
                        segments.append(_Segment("\n".join(buf).strip(), page.page, chapter)); buf = []
                    chapter = heading.group(1).strip()
                elif not s:                       # blank line -> paragraph boundary
                    if buf:
                        segments.append(_Segment("\n".join(buf).strip(), page.page, chapter)); buf = []
                else:
                    buf.append(line)
            if buf:
                segments.append(_Segment("\n".join(buf).strip(), page.page, chapter))
        return [s for s in segments if s.text]
    

    # Below is the _hard_split method of the SemanticChunker class, which takes a _Segment as input and returns a list of _Segment objects. The method first encodes the text of the input segment into tokens using the tiktoken library. If the number of tokens is less than or equal to the target token count, it simply returns a list containing the original segment. However, if the number of tokens exceeds the target, it splits the token list into smaller chunks of the target size and decodes each chunk back into text to create new _Segment objects. Each new segment retains the same page and chapter information as the original segment. Finally, the method returns a list of _Segment objects that represent the split segments of text.
    def _hard_split(self, seg: _Segment) -> list[_Segment]:
        toks = self.enc.encode(seg.text)
        if len(toks) <= self.target:
            return [seg]
        return [_Segment(self.enc.decode(toks[i:i + self.target]), seg.page, seg.chapter)
                for i in range(0, len(toks), self.target)]
    

    # The chunk method is the main method of the SemanticChunker class, which takes a ParsedDocument and an upload date as input and returns a list of Chunk objects. The method first splits the parsed document into segments using the _split_segments method, and then applies a hard split to any segments that exceed the target token count using the _hard_split method. After obtaining a list of segments that are within the target token count, the method iterates through these segments and creates chunks of text by packing paragraphs together until the target token count is reached. It also allows for some overlap between chunks to maintain context. Each chunk is associated with metadata that includes the original document name, subject, chapter, page number, and upload date. Finally, the method returns a list of Chunk objects that can be stored in the vector database for later retrieval and use in generating answers to user queries.
    def chunk(self, parsed: ParsedDocument, upload_date: datetime) -> list[Chunk]:
        segments: list[_Segment] = []
        for s in self._split_segments(parsed):
            segments.extend(self._hard_split(s))

        # Phase 1: pack paragraphs up to the token target
        base: list[tuple[str, int, str | None]] = []
        cur: list[str] = []
        cur_tok = 0
        cur_page: int | None = None
        cur_ch: str | None = None
        for s in segments:
            st = self._ntokens(s.text)
            if cur and cur_tok + st > self.target:
                base.append(("\n\n".join(cur).strip(), cur_page, cur_ch))
                cur, cur_tok, cur_page, cur_ch = [], 0, None, None
            if not cur:
                cur_page, cur_ch = s.page, s.chapter
            cur.append(s.text)
            cur_tok += st
        if cur:
            base.append(("\n\n".join(cur).strip(), cur_page, cur_ch))

        # Phase 2: prepend token-level overlap from the previous chunk
        chunks: list[Chunk] = []
        for i, (text, page, ch) in enumerate(base):
            if i > 0:
                prev = self.enc.encode(base[i - 1][0])
                if prev:
                    text = f"{self.enc.decode(prev[-self.overlap:])}\n\n{text}"
            chunks.append(Chunk(
                chunk_id=f"{parsed.document_id}:{i}",
                text=text,
                metadata=ChunkMetadata(
                    document_name=parsed.document_name, subject=parsed.subject,
                    chapter=ch, page=page or 1, upload_date=upload_date),
            ))
        return chunks