# app/parsing/parsers.py
import io
from pathlib import Path

import fitz                       # PyMuPDF
from PIL import Image
from openai import AsyncOpenAI

from app.parsing.vision import ocr_image
from app.schemas import PageUnit

# Below parse_txt fucntion reads the text content of a .txt file and returns it as a list of PageUnit objects. Each PageUnit represents a page of the document, and since .txt files typically do not have multiple pages, we create a single PageUnit with the entire text content.
def parse_txt(path: str) -> list[PageUnit]:
    text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    return [PageUnit(page=1, text=text)]

# The parse_docx function uses the python-docx library to read the content of a .docx file. It iterates through the paragraphs and tables in the document, extracting the text and formatting it as needed. For paragraphs, it checks the style to determine if it should be treated as a heading. For tables, it flattens them into a Markdown-like format. The resulting text is returned as a list of PageUnit objects, with each PageUnit representing a page of the document (in this case, we treat the entire document as one page).
def parse_docx(path: str) -> list[PageUnit]:
    from docx import Document as Docx
    doc = Docx(path)
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


# The parse_pdf function uses the PyMuPDF library to read the content of a PDF file. It iterates through each page of the PDF, extracting the text content. If a page has a text layer with enough characters (as determined by the min_chars parameter), it is treated as a regular text page. If a page has fewer characters than the threshold, it is assumed to be a scanned image, and the function uses the ocr_image function to perform OCR on the page's image representation. The resulting text for each page is returned as a list of PageUnit objects, with each PageUnit representing a page of the PDF document.
async def parse_pdf(path: str, *, openai: AsyncOpenAI, vision_model: str,
                    min_chars: int) -> list[PageUnit]:
    pages: list[PageUnit] = []
    doc = fitz.open(path)
    try:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if len(text) >= min_chars:            # has a real text layer
                pages.append(PageUnit(page=i, text=text))
            else:                                 # scanned/image page -> vision OCR
                img_bytes = page.get_pixmap(dpi=200).tobytes("png")
                pages.append(PageUnit(page=i, text=await ocr_image(openai, vision_model, img_bytes)))
    finally:
        doc.close()
    return pages

# The _normalize_image function takes an image file path and a maximum side length as input. It uses the PIL library to open the image, convert it to RGB format, and resize it if its largest dimension exceeds the specified maximum side length. The normalized image is then saved to a bytes buffer in PNG format and returned as bytes. This function is used to prepare images for OCR processing, ensuring that they are in a consistent format and size to optimize OCR performance and cost.
def _normalize_image(path: str, max_side: int = 2000) -> bytes:
    with Image.open(path) as im:
        im = im.convert("RGB")
        if max(im.size) > max_side:               # cap size to control vision cost
            im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

# The parse_image function is an asynchronous function that takes an image file path, an OpenAI client, and a vision model name as input. It uses the _normalize_image function to preprocess the image and then calls the ocr_image function to perform OCR on the normalized image. The resulting text is returned as a list of PageUnit objects, with each PageUnit representing a page of the document (in this case, we treat the entire image as one page). This function is used to extract text from images, which can be particularly useful for scanned documents or handwritten notes.
async def parse_image(path: str, *, openai: AsyncOpenAI, vision_model: str) -> list[PageUnit]:
    text = await ocr_image(openai, vision_model, _normalize_image(path), "image/png")
    return [PageUnit(page=1, text=text)]


