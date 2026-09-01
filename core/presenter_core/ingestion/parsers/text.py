"""Plain text and Markdown parser with deterministic section boundaries."""

from __future__ import annotations

import re
from pathlib import Path

from presenter_core.errors import CoreDomainError
from presenter_core.ingestion.models import ParsedSourceUnit

from .utils import normalize_text

_MARKDOWN_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")


class TextParser:
    parser_id = "text.stdlib"

    def parse(self, path: Path) -> list[ParsedSourceUnit]:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise CoreDomainError(
                "SOURCE_PARSE_FAILED",
                "The text source could not be decoded.",
                details={"parser_id": self.parser_id, "source_type": "text"},
            ) from exc

        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if path.suffix.casefold() in {".md", ".markdown"}:
            return self._markdown_units(normalized)
        return [
            ParsedSourceUnit(
                unit_type="section",
                ordinal=1,
                title=None,
                text=normalize_text(normalized),
                metadata={"parser": self.parser_id, "format": "text"},
            )
        ]

    def _markdown_units(self, text: str) -> list[ParsedSourceUnit]:
        lines = text.splitlines(keepends=True)
        sections: list[tuple[str | None, str]] = []
        current_title: str | None = None
        current_lines: list[str] = []

        for line in lines:
            match = _MARKDOWN_HEADING.match(line.rstrip("\n"))
            if match:
                if current_lines:
                    sections.append((current_title, "".join(current_lines)))
                current_title = match.group(2).strip().rstrip("#").strip() or None
                current_lines = [line]
            else:
                current_lines.append(line)
        if current_lines or not sections:
            sections.append((current_title, "".join(current_lines)))

        units: list[ParsedSourceUnit] = []
        for ordinal, (title, section_text) in enumerate(sections, start=1):
            units.append(
                ParsedSourceUnit(
                    unit_type="section",
                    ordinal=ordinal,
                    title=title,
                    text=normalize_text(section_text),
                    metadata={"parser": self.parser_id, "format": "markdown"},
                )
            )
        return units
