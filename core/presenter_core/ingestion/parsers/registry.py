"""Supported source type to parser mapping."""

from __future__ import annotations

from presenter_core.errors import CoreDomainError

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


def parser_for(source_type: str) -> SourceParser:
    try:
        return _PARSERS[source_type]
    except KeyError as exc:
        raise CoreDomainError(
            "SOURCE_TYPE_UNSUPPORTED",
            "This source type is not supported in Milestone 1.",
            details={"source_type": source_type},
        ) from exc
