"""Shared parser text normalization helpers."""

from __future__ import annotations

import re


def normalize_text(value: str) -> str:
    """Normalize line endings while retaining source-visible content."""
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def lexical_normalize(value: str) -> str:
    """Create deterministic, case-insensitive text used by lexical search."""
    folded = value.casefold().replace("\u2019", "'")
    tokens = re.findall(
        r"\d[\d,]*(?:\.\d+)?%?|[^\W_]+(?:[._/%+-][^\W_]+)*",
        folded,
        flags=re.UNICODE,
    )
    return " ".join(tokens)
