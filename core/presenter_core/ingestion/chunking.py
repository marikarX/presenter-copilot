"""Deterministic, replaceable source-unit chunking for M1 lexical retrieval."""

from __future__ import annotations

import re

from presenter_core.ingestion.models import ChunkDraft

from .parsers.utils import lexical_normalize

MAX_CHUNK_CHARACTERS = 1_200


def chunk_text(text: str) -> list[ChunkDraft]:
    """Split one source unit without ever crossing its provenance boundary."""
    if not text.strip():
        return []
    if len(text) <= MAX_CHUNK_CHARACTERS:
        pieces = [text.strip()]
    else:
        pieces = _pack_segments(_split_segments(text))
    return [
        ChunkDraft(chunk_index=index, text=piece, lexical_text=lexical_normalize(piece))
        for index, piece in enumerate(pieces)
        if piece
    ]


def _split_segments(text: str) -> list[str]:
    segments: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= MAX_CHUNK_CHARACTERS:
            segments.append(paragraph)
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= MAX_CHUNK_CHARACTERS:
                segments.append(sentence)
                continue
            remainder = sentence
            while len(remainder) > MAX_CHUNK_CHARACTERS:
                cut = remainder.rfind(" ", 0, MAX_CHUNK_CHARACTERS + 1)
                if cut <= 0:
                    cut = MAX_CHUNK_CHARACTERS
                segments.append(remainder[:cut].strip())
                remainder = remainder[cut:].strip()
            if remainder:
                segments.append(remainder)
    return segments


def _pack_segments(segments: list[str]) -> list[str]:
    packed: list[str] = []
    current = ""
    for segment in segments:
        candidate = f"{current}\n\n{segment}" if current else segment
        if current and len(candidate) > MAX_CHUNK_CHARACTERS:
            packed.append(current.strip())
            current = segment
        else:
            current = candidate
    if current:
        packed.append(current.strip())
    return packed
