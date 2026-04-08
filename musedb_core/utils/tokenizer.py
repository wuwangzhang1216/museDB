"""Tokenizer utilities for FTS5 indexing — handles CJK segmentation via jieba."""

from __future__ import annotations

import re

import jieba

# CJK Unicode ranges: Chinese, Hiragana, Katakana, Hangul
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]"
)

# Hyphenated compound words: split "gardening-related" → "gardening-related gardening related"
_HYPHEN_RE = re.compile(r"\b(\w+(?:-\w+)+)\b")


def _expand_hyphens(text: str) -> str:
    """Expand hyphenated words while keeping the original form.

    "gardening-related tips" → "gardening-related gardening related tips"
    """
    def _replace(m: re.Match) -> str:
        original = m.group(0)
        parts = original.split("-")
        return original + " " + " ".join(parts)

    return _HYPHEN_RE.sub(_replace, text)


def tokenize_for_fts(text: str) -> str:
    """Tokenize text for FTS5 indexing.

    For text containing CJK characters, applies jieba segmentation so that
    FTS5 can index individual Chinese/Japanese/Korean words.
    For pure Latin/ASCII text, returns as-is (FTS5 unicode61 handles it fine).

    Hyphenated compound words are always expanded so both the whole form
    and individual parts are indexed.
    """
    text = _expand_hyphens(text)
    if not _CJK_RE.search(text):
        return text
    return " ".join(jieba.cut_for_search(text))
