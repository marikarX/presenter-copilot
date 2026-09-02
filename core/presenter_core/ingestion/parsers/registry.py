"""Supported source type to parser mapping."""

from __future__ import annotations

from presenter_core.errors import CoreDomainError
from presenter_core.transcript.parsers import transcript_parser_for

from .base import SourceParser
from .pdf import PdfParser
from .pptx import PptxParser
from .text import TextParser

_PARSERS: dict[str, SourceParser] = {
    "pdf": PdfParser(),
    "pptx": PptxParser(),
    "txt": TextParser(),
    "markdown": TextParser(),
}


def parser_for(source_type: str, kind: str = "supporting") -> SourceParser:
    if kind == "transcript":
        return transcript_parser_for(source_type)
    try:
        return _PARSERS[source_type]
    except KeyError as exc:
        raise CoreDomainError(
            "SOURCE_TYPE_UNSUPPORTED",
            "This source type is not supported for this document kind.",
            details={"source_type": source_type, "kind": kind},
        ) from exc
