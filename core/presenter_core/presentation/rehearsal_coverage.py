"""Read-only density and recorded coverage observations from frozen rehearsals."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.fidelity import FidelitySlide, inspect_pptx_snapshot
from presenter_core.storage.service import StorageManager

METRICS = ("speaking_time_ms", "word_count", "utterance_count")


def _slides(
    storage: StorageManager, project: str, document: str, row: sqlite3.Row
) -> tuple[FidelitySlide, ...]:
    path = storage.paths.snapshot_path(project, row["local_snapshot_path"], require_exists=True)
    with path.open("rb") as handle:
        return inspect_pptx_snapshot(
            handle, document_id=document, expected_sha256=row["sha256"], byte_size=row["byte_size"]
        ).slides


def inspect_coverage(
    storage: StorageManager,
    project: str,
    document: str,
    current: sqlite3.Row,
    session: sqlite3.Row,
    events: list[sqlite3.Row],
    *,
    offset: int,
    limit: int,
    sort: str,
    filter_by: str,
) -> dict[str, Any]:
    source = _slides(storage, project, document, session)
    present = (
        source
        if session["presentation_revision_id"] == current["id"]
        else _slides(storage, project, document, current)
    )
    mapping = {slide.ordinal: slide.slide_id for slide in source}
    counts = {slide.slide_id: dict.fromkeys(METRICS, 0) for slide in source}
    unmapped = dict.fromkeys(METRICS, 0)
    try:
        raw = session["debrief_json"]
        if not isinstance(raw, str) or len(raw) > 8 * 1024 * 1024:
            raise ValueError("Debrief size")
        data = json.loads(raw)
        summary = data["session"]
        if summary["session_id"] != session["session_id"]:
            raise ValueError("Debrief identity")
        for name in ("duration_ms", "word_count", "utterance_count"):
            if type(summary[name]) is not int or summary[name] < 0:
                raise ValueError("Summary metric")
        rows = data["per_slide"]
        if not isinstance(rows, list) or len(rows) > 5001:
            raise ValueError("Slide observations")
        seen: set[int | None] = set()
        for row in rows:
            ordinal = row["slide_ordinal"]
            if ordinal is not None and (type(ordinal) is not int or not 1 <= ordinal <= 5000):
                raise ValueError("Slide ordinal")
            if ordinal in seen:
                raise ValueError("Duplicate slide summary")
            seen.add(ordinal)
            identity = mapping.get(ordinal) if ordinal is not None else None
            target = counts[identity] if identity is not None else unmapped
            for name in METRICS:
                value = row[name]
                if type(value) is not int or value < 0:
                    raise ValueError("Observation metric")
                target[name] += value
        for name in ("word_count", "utterance_count"):
            if sum(row[name] for row in counts.values()) + unmapped[name] != summary[name]:
                raise ValueError("Inconsistent summary")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise CoreDomainError(
            "RUN_DEBRIEF_CORRUPT", "The rehearsal debrief contains invalid coverage data."
        ) from error
    visited = {
        mapping[event["slide_ordinal"]]
        for event in events
        if type(event["slide_ordinal"]) is int and event["slide_ordinal"] in mapping
    }
    current_ordinals = {slide.slide_id: slide.ordinal for slide in present}
    source_by_id = {slide.slide_id: slide for slide in source}
    identities = list(dict.fromkeys([*current_ordinals, *source_by_id]))
    output: list[dict[str, Any]] = []
    for identity in identities:
        slide = source_by_id.get(identity)
        recorded = counts.get(identity)
        state = (
            "not_rehearsed_revision"
            if slide is None
            else "recorded_speech"
            if recorded and recorded["utterance_count"] > 0
            else "visited_without_recorded_speech"
            if identity in visited
            else "no_recorded_visit_or_speech"
        )
        native_words = sum(len(obj.text.split()) for obj in slide.objects) if slide else None
        output.append(
            {
                "slide_id": identity,
                "current_slide_number": current_ordinals.get(identity),
                "source_slide_number": slide.ordinal if slide else None,
                "native_text_words": native_words,
                "native_text_objects": sum(bool(obj.text.strip()) for obj in slide.objects)
                if slide
                else None,
                "recorded": recorded,
                "recorded_visit": identity in visited if slide else None,
                "status": state,
            }
        )
    totals = {
        "source_slides": len(source),
        "current_slides": len(present),
        "slides_with_recorded_speech": sum(row["status"] == "recorded_speech" for row in output),
        "slides_without_recorded_speech": sum(
            row["recorded"] is not None and row["recorded"]["utterance_count"] == 0
            for row in output
        ),
        "slides_without_recorded_visit_or_speech": sum(
            row["status"] == "no_recorded_visit_or_speech" for row in output
        ),
        "slides_added_since_rehearsal": sum(row["source_slide_number"] is None for row in output),
        "slides_removed_since_rehearsal": sum(
            row["current_slide_number"] is None for row in output
        ),
    }
    if filter_by == "no_speech":
        output = [
            row
            for row in output
            if row["recorded"] is not None and row["recorded"]["utterance_count"] == 0
        ]
    elif filter_by == "no_visit":
        output = [row for row in output if row["status"] == "no_recorded_visit_or_speech"]
    output.sort(
        key=lambda row: ((-(row["native_text_words"] or 0),) if sort == "native_words" else ())
        + (
            row["current_slide_number"] is None,
            row["current_slide_number"] or row["source_slide_number"] or 0,
        )
    )
    return {
        "document_id": document,
        "revision_id": current["id"],
        "session_id": session["session_id"],
        "source_revision_id": session["presentation_revision_id"],
        "source_revision_number": session["revision_number"],
        "started_at": session["started_at"],
        "session_word_count": summary["word_count"],
        "session_utterance_count": summary["utterance_count"],
        "unmapped": unmapped,
        "totals": totals,
        "offset": offset,
        "limit": limit,
        "sort": sort,
        "filter": filter_by,
        "total_filtered": len(output),
        "slides": output[offset : offset + limit],
    }
