"""Parser adapter protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from presenter_core.ingestion.models import ParsedSourceUnit


class SourceParser(Protocol):
    """Small parser interface used by IngestionService."""

    parser_id: str

    def parse(self, path: Path) -> list[ParsedSourceUnit]:
        """Parse one snapshotted source without mutating the filesystem."""
