# app/parsing/parsers.py
import asyncio
import io

import fitz                       # PyMuPDF
from PIL import Image
from openai import AsyncOpenAI

from app.parsing.vision import ocr_image
from app.schemas import PageUnit

# All parsers operate on the raw file bytes (fetched from the cloud document store)
# rather than filesystem paths, so parsing never requires the file to exist on disk.

def parse_txt(data: bytes) -> list[PageUnit]:
    text = data.decode("utf-8", errors="replace").strip()
    return [PageUnit(page=1, text=text)]


def parse_docx(data: bytes) -> list[PageUnit]:
    from docx import Document as Docx
    doc = Docx(io.BytesIO(data))
    lines: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "").lower() if para.style else ""
        lines.append(f"# {text}" if style.startswith("heading") or style == "title" else text)
    for table in doc.tables:                      # flatten tables to Markdown-ish rows
        for row in table.rows:
            lines.append(" | ".join(c.text.strip() for c in row.cells))
            
    return [PageUnit(page=1, text="\n".join(lines).strip())]


def _extract_page_text(page: fitz.Page) -> str:
    """
    Faithful full-page text extraction that handles complex layouts.

    PyMuPDF's get_text("text") follows its own internal reading order and
    silently drops any block that falls outside the main text column:
    floating labels (labels inside ovals/boxes), sidebar notes, multi-column
    layouts, margin annotations, table cells read out of order, etc.

    Strategy:
    1. Detect and extract tables first via PyMuPDF's table detector, rendered
       as tab-separated rows so their content is fully searchable.
    2. Collect every remaining text block on the page (including floating ones
       that the flow reader skips).
    3. Merge everything sorted by vertical position so reading order is
       preserved regardless of where on the page the block sits.

    This generically handles:
    - Floating labels anywhere on the page (set numbers, roll-no boxes, codes)
    - Multi-column academic / exam paper layouts
    - Sidebar / margin notes and annotations
    - Tables (cells kept together and in row order)
    - Any text inside drawn shapes (ovals, rectangles, callouts)
    """
    # Step 1: extract tables and record their bounding boxes
    table_bboxes: list[fitz.Rect] = []
    table_parts: list[tuple[float, str]] = []   # (y0, rendered_text)
    try:
        for table in page.find_tables():
            rect = fitz.Rect(table.bbox)
            table_bboxes.append(rect)
            rows = []
            for row in table.extract():
                cells = [str(c).strip() if c is not None else "" for c in row]
                rows.append("\t".join(cells))
            table_parts.append((rect.y0, "\n".join(rows)))
    except Exception:
        pass  # older PyMuPDF or page has no tables — skip gracefully

    # Step 2: collect all text blocks, skipping regions already covered by tables
    block_parts: list[tuple[float, float, str]] = []
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
        text = text.strip()
        if not text:
            continue
        if any(fitz.Rect(x0, y0, x1, y1).intersects(tb) for tb in table_bboxes):
            continue  # already captured by table extractor
        block_parts.append((y0, x0, text))

    # Step 3: merge and sort everything by vertical position
    all_parts: list[tuple[float, str]] = [(y, t) for y, x, t in block_parts]
    all_parts.extend(table_parts)
    all_parts.sort(key=lambda p: p[0])

    return "\n".join(t for _, t in all_parts)


async def parse_pdf(data: bytes, *, openai: AsyncOpenAI, vision_model: str,
                    min_chars: int, ocr_concurrency: int = 4) -> list[PageUnit]:
    # Pass 1 (fast, local): extract every page's text layer. Pages below min_chars are
    # scanned and need vision OCR — rasterise them now and queue for parallel OCR.
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        text_by_page: dict[int, str] = {}
        ocr_jobs: list[tuple[int, bytes]] = []   # (page number, png bytes)
        for i, page in enumerate(doc, start=1):
            text = _extract_page_text(page)
            if len(text) >= min_chars:            # has a real text layer
                text_by_page[i] = text
            else:                                 # scanned/image page -> vision OCR
                ocr_jobs.append((i, page.get_pixmap(dpi=200).tobytes("png")))
    finally:
        doc.close()

    # Pass 2 (network-bound): OCR all scanned pages concurrently, bounded by a semaphore
    # so a long book doesn't fire dozens of vision calls at once and hit rate limits.
    sem = asyncio.Semaphore(max(1, ocr_concurrency))

    async def _ocr(page_num: int, img_bytes: bytes) -> tuple[int, str]:
        async with sem:
            return page_num, await ocr_image(openai, vision_model, img_bytes)

    for page_num, text in await asyncio.gather(*(_ocr(n, b) for n, b in ocr_jobs)):
        text_by_page[page_num] = text

    pages = [PageUnit(page=n, text=text_by_page[n]) for n in sorted(text_by_page)]
    return pages


def _normalize_image(data: bytes, max_side: int = 2000) -> bytes:
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        if max(im.size) > max_side:               # cap size to control vision cost
            im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()


async def parse_image(data: bytes, *, openai: AsyncOpenAI, vision_model: str) -> list[PageUnit]:
    text = await ocr_image(openai, vision_model, _normalize_image(data), "image/png")
    return [PageUnit(page=1, text=text)]
