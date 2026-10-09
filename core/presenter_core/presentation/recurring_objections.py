"""Exact-wording recurrence is an observation, never semantic objection equivalence."""

from __future__ import annotations

import hashlib
from typing import Any


def group_objections(
    document: str, findings: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    excluded = 0
    for finding in findings:
        note = " ".join(str(finding["quote"]).split())
        slide = finding["slide_id"]
        if not note or slide is None:
            excluded += 1
            continue
        buckets.setdefault((slide, note), []).append(finding)
    groups: list[dict[str, Any]] = []
    for (slide, note), occurrences in buckets.items():
        sessions = {finding["session_id"] for finding in occurrences}
        if len(sessions) < 2:
            excluded += len(occurrences)
            continue
        reviewed = {
            status: sum(finding["disposition"] == status for finding in occurrences)
            for status in ("unreviewed", "applied", "rejected")
        }
        # Keep original quote/revision for review; the grouping key is not an edit payload.
        selected = next(
            (finding for finding in occurrences if finding["disposition"] == "unreviewed"),
            occurrences[0],
        )
        preview = occurrences[:5]
        if selected not in preview:
            preview = [*preview[:4], selected]
        groups.append(
            {
                "group_id": hashlib.sha256(f"{document}\0{slide}\0{note}".encode()).hexdigest(),
                "slide_id": slide,
                "current_slide_number": occurrences[0]["current_slide_number"],
                "note": note,
                "session_count": len(sessions),
                "occurrence_count": len(occurrences),
                "dispositions": reviewed,
                "occurrences": preview,
                "occurrences_truncated": len(occurrences) > len(preview),
                "selected_finding": selected,
            }
        )
    groups.sort(
        key=lambda group: (-group["session_count"], -group["occurrence_count"], group["group_id"])
    )
    return groups, excluded
