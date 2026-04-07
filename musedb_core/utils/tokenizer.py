"""Tokenizer utilities for FTS5 indexing — handles CJK segmentation via jieba."""

from __future__ import annotations

import re

import jieba

# CJK Unicode ranges: Chinese, Hiragana, Katakana, Hangul
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]"
)


def tokenize_for_fts(text: str) -> str:
    """Tokenize text for FTS5 indexing.

    For text containing CJK characters, applies jieba segmentation so that
    FTS5 can index individual Chinese/Japanese/Korean words.
    For pure Latin/ASCII text, returns as-is (FTS5 unicode61 handles it fine).
    """
    if not _CJK_RE.search(text):
        return text
    return " ".join(jieba.cut_for_search(text))
