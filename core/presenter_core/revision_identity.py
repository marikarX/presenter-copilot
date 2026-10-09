"""Stable identifiers for immutable presentation revision metadata."""

from __future__ import annotations

import uuid

_PRESENTATION_REVISION_NAMESPACE = uuid.UUID("bc781251-54ea-4eb4-9951-a3487c73b2c4")


def original_presentation_revision_id(presentation_id: str, sha256: str) -> str:
    """Derive the one import-revision id from a presentation and its exact bytes."""
    return str(
        uuid.uuid5(
            _PRESENTATION_REVISION_NAMESPACE,
            f"presentation-original\0{presentation_id}\0{sha256}",
        )
    )
