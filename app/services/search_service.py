"""Search service: full-text search with filters and CJK fallback."""

from __future__ import annotations

import re

from app.storage import get_backend

# CJK character ranges
_CJK_PATTERN = re.compile(
    r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]"
)


def _is_cjk_query(query: str) -> bool:
    return bool(_CJK_PATTERN.search(query))


async def search_files(
    query: str,
    filters: dict | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search across all files. Returns page-level results with highlights."""
    filters = filters or {}
    backend = get_backend()

    if _is_cjk_query(query):
        return await backend.search_cjk(query, filters, limit, offset)
    else:
        return await backend.search_fts(query, filters, limit, offset)
