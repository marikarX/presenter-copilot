"""Comparisons retain frozen identities and reject unrelated/stale observations."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import DeterministicFakeAudioInput
from tests.test_m6_run import make_core
from tests.test_presentation_planning import call


def test_comparison_aligns_reordered_slides_and_preserves_deck(tmp_path: Path) -> None:
    core = make_core(tmp_path, DeterministicFakeAudioInput(), DeterministicFakeASRAdapter(), [])
    try:
        project = call(core, "project.create", {"name": "Compare"})["project"]["id"]
        document = call(
            core,
            "presentation.workspace.create_from_outline",
            {
                "project_id": project,
                "title": "Decision",
                "slides": [
                    {"title": title, "bullets": ["Review"], "notes": ""}
                    for title in ("Opening", "Decision")
                ],
            },
        )["document"]["id"]
        scope = {"project_id": project, "document_id": document}
        revision = call(core, "presentation.workspace.list_revisions", scope)["current_revision_id"]
        scope["expected_revision_id"] = revision
        slide = call(
            core,
            "presentation.workspace.list_text_targets",
            {
                "project_id": project,
                "document_id": document,
                "revision_id": revision,
                "slide_number": 1,
            },
        )["slide_id"]
        other = call(
            core,
            "presentation.workspace.list_text_targets",
            {
                "project_id": project,
                "document_id": document,
                "revision_id": revision,
                "slide_number": 2,
            },
        )["slide_id"]

        def rehearse(ordinal: int, markers: int) -> str:
            call(core, "presentation.workspace.select_for_rehearsal", scope)
            identity = call(
                core,
                "session.start",
                {
                    "project_id": project,
                    "mode": "run",
                    "current_slide_start": ordinal,
                    "expected_presentation_revision_id": scope["expected_revision_id"],
                },
            )["session"]["id"]
            for _ in range(markers):
                call(
                    core,
                    "run.mark_event",
                    {
                        "project_id": project,
                        "session_id": identity,
                        "marker_type": "weak_point",
                        "note": "Review",
                    },
                )
            call(core, "session.stop", {"project_id": project, "session_id": identity})
            return str(identity)

        baseline = rehearse(1, 1)
        reordered = call(
            core,
            "presentation.workspace.reorder_slides",
            {**scope, "ordered_slide_ids": [other, slide]},
        )
        scope["expected_revision_id"] = reordered["revision_id"]
        call(core, "source.reindex", {"project_id": project, "document_id": document})
        comparison = rehearse(2, 2)
        params = {**scope, "baseline_session_id": baseline, "comparison_session_id": comparison}
        result = call(core, "presentation.workspace.compare_rehearsals", params)
        matched = next(row for row in result["slides"] if row["slide_id"] == slide)
        assert (
            matched["baseline_slide_number"],
            matched["comparison_slide_number"],
            matched["current_slide_number"],
        ) == (1, 2, 2)
        assert matched["delta"]["markers"] == 1
        assert result["delta"]["markers"] == 1
        assert result["algorithm_versions_match"] is True
        assert (
            call(
                core,
                "presentation.workspace.list_revisions",
                {"project_id": project, "document_id": document},
            )["current_revision_id"]
            == scope["expected_revision_id"]
        )
        assert (
            call(
                core,
                "presentation.workspace.compare_rehearsals",
                {**params, "expected_revision_id": revision},
                ok=False,
            )["code"]
            == "PRESENTATION_REVISION_CONFLICT"
        )
        assert (
            call(
                core,
                "presentation.workspace.compare_rehearsals",
                {**params, "comparison_session_id": baseline},
                ok=False,
            )["code"]
            == "INVALID_REQUEST"
        )
        assert (
            call(
                core,
                "presentation.workspace.compare_rehearsals",
                {**params, "comparison_session_id": str(uuid.uuid4())},
                ok=False,
            )["code"]
            == "REHEARSAL_COMPARISON_UNAVAILABLE"
        )

        # Stored observations without an ordinal remain in totals, never assigned to a slide.
        with core._storage.project_database(project) as connection:
            payload = json.loads(
                connection.execute(
                    "SELECT debrief_json FROM run_debriefs WHERE session_id = ?", (comparison,)
                ).fetchone()[0]
            )
            payload["per_slide"] = [
                {
                    "slide_ordinal": None,
                    "speaking_time_ms": 1000,
                    "word_count": 4,
                    "utterance_count": 1,
                }
            ]
            payload["session"].update(word_count=4, utterance_count=1)
            payload["algorithm_version"] = "another-version"
            payload["evidence_review_candidates"] = [{"slide_ordinal": 2}] * 100
            payload["long_segments"] = [{"slide_ordinal": 2}] * 1001
            connection.execute(
                "UPDATE run_debriefs SET debrief_json = ? WHERE session_id = ?",
                (json.dumps(payload), comparison),
            )
            connection.commit()
        result = call(core, "presentation.workspace.compare_rehearsals", params)
        assert result["comparison"]["unmapped"]["word_count"] == 4
        assert result["comparison"]["totals"]["word_count"] == 4
        assert result["candidate_counts_may_be_capped"] is True
        assert result["algorithm_versions_match"] is False
        assert (
            next(row for row in result["slides"] if row["slide_id"] == slide)["comparison"][
                "word_count"
            ]
            == 0
        )
        with core._storage.project_database(project) as connection:
            payload["session"]["session_id"] = baseline
            connection.execute(
                "UPDATE run_debriefs SET debrief_json = ? WHERE session_id = ?",
                (json.dumps(payload), comparison),
            )
            connection.commit()
        assert (
            call(core, "presentation.workspace.compare_rehearsals", params, ok=False)["code"]
            == "RUN_DEBRIEF_CORRUPT"
        )
        # A slide absent from a later frozen revision has no numeric delta.
        deleted = call(core, "presentation.workspace.delete_slide", {**scope, "slide_id": slide})
        scope["expected_revision_id"] = deleted["revision_id"]
        call(core, "source.reindex", {"project_id": project, "document_id": document})
        later = rehearse(1, 0)
        result = call(
            core,
            "presentation.workspace.compare_rehearsals",
            {**scope, "baseline_session_id": baseline, "comparison_session_id": later},
        )
        absent = next(row for row in result["slides"] if row["slide_id"] == slide)
        assert absent["current_slide_number"] is None
        assert absent["comparison"] is None
        assert absent["delta"] is None
        unrelated = call(
            core,
            "presentation.workspace.create_from_outline",
            {
                "project_id": project,
                "title": "Other",
                "slides": [{"title": "Other", "bullets": ["Other"], "notes": ""}],
            },
        )["document"]["id"]
        unrelated_revision = call(
            core,
            "presentation.workspace.list_revisions",
            {"project_id": project, "document_id": unrelated},
        )["current_revision_id"]
        assert (
            call(
                core,
                "presentation.workspace.compare_rehearsals",
                {
                    "project_id": project,
                    "document_id": unrelated,
                    "expected_revision_id": unrelated_revision,
                    "baseline_session_id": baseline,
                    "comparison_session_id": later,
                },
                ok=False,
            )["code"]
            == "REHEARSAL_COMPARISON_UNAVAILABLE"
        )
    finally:
        core.close()
