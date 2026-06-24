# app/parsing/vision.py
import base64
from openai import AsyncOpenAI

_PROMPT = (
    "You are an OCR engine. Transcribe ALL text in this image exactly as written, "
    "including handwriting. Preserve reading order, headings, bullets and table structure "
    "as Markdown. Do not summarize or add anything not in the image. "
    "Mark unreadable regions as [illegible]. Output only the transcription."
)

async def ocr_image(client: AsyncOpenAI, model: str, image_bytes: bytes,
                    mime_type: str = "image/png") -> str:
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    resp = await client.chat.completions.create(
        model=model,
        temperature=0,
        timeout=60,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": _PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
    )
    return (resp.choices[0].message.content or "").strip()