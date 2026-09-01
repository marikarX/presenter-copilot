"""PDF parser preserving one SourceUnit per human-facing page."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from presenter_core.errors import CoreDomainError
from presenter_core.ingestion.models import ParsedSourceUnit

from .utils import normalize_text


class PdfParser:
    parser_id = "pdf.pypdf"

    def parse(self, path: Path) -> list[ParsedSourceUnit]:
        try:
            reader = PdfReader(str(path), strict=False)
            units: list[ParsedSourceUnit] = []
            for ordinal, page in enumerate(reader.pages, start=1):
                text = normalize_text(page.extract_text() or "")
                units.append(
                    ParsedSourceUnit(
                        unit_type="page",
                        ordinal=ordinal,
                        title=None,
                        text=text,
                        metadata={"parser": self.parser_id},
                    )
                )
            return units
        except Exception as exc:
            raise CoreDomainError(
                "SOURCE_PARSE_FAILED",
                "The PDF could not be parsed.",
                details={"parser_id": self.parser_id, "source_type": "pdf"},
            ) from exc
