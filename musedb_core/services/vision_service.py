"""Vision service — describe images using a free vision-capable LLM.

Calls OpenRouter's google/gemma-3-27b-it:free via plain HTTP (no SDK needed).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
from pathlib import Path

logger = logging.getLogger(__name__)

_VISION_MODEL = "google/gemini-2.5-flash-lite"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_DESCRIBE_PROMPT = (
    "Describe this image in detail. Extract ALL text, numbers, dates, and "
    "amounts visible in the image. If it's a receipt, invoice, or bill, "
    "list: vendor name, date, line items with amounts, subtotal, tax, and total. "
    "If it's a screenshot of a website or app, describe the UI and extract all visible text. "
    "Respond in the same language as the text in the image."
)

# Concurrency guard — avoid hammering the API with too many parallel calls
_semaphore = asyncio.Semaphore(8)


async def describe_image(
    file_path: Path,
    *,
    api_key: str | None = None,
    prompt: str | None = None,
) -> str:
    """Describe an image using the free vision model."""
    import os

    key = (
        api_key
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("MUSE_OPENROUTER_API_KEY")
    )
    if not key:
        logger.warning("No OpenRouter API key — cannot describe image %s", file_path)
        return "(no API key configured for vision model)"

    if not file_path.exists():
        return f"(image not found: {file_path})"

    # Build data URL
    raw = file_path.read_bytes()
    b64 = base64.b64encode(raw).decode("utf-8")
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = f"image/{file_path.suffix.lstrip('.')}"
    data_url = f"data:{mime_type};base64,{b64}"

    async with _semaphore:
        return await _call_api(key, data_url, prompt or _DESCRIBE_PROMPT)


async def _call_api(
    api_key: str,
    image_url: str,
    prompt: str,
    *,
    max_retries: int = 3,
) -> str:
    """POST to OpenRouter with retry on 429."""
    import httpx

    payload = {
        "model": _VISION_MODEL,
        "provider": {"sort": "throughput"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(max_retries):
            try:
                resp = await client.post(_OPENROUTER_URL, json=payload, headers=headers)

                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.info("Vision 429, retry in %ds (%d/%d)", wait, attempt + 1, max_retries)
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                return text.strip() if text else "(no description extracted)"

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.info("Vision 429, retry in %ds (%d/%d)", wait, attempt + 1, max_retries)
                    await asyncio.sleep(wait)
                    continue
                logger.warning("Vision API error: %s", e)
                return f"(vision API error: {e})"
            except Exception as e:
                logger.warning("Vision API call failed: %s", e)
                return f"(vision API error: {e})"

    return "(vision API rate limited — try again later)"
