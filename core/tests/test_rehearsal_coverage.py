"""Frozen native density and recorded coverage do not become semantic conclusions."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import DeterministicFakeAudioInput
from tests.test_m6_run import make_core
from tests.test_presentation_planning import call

METHOD = "presentation.workspace.rehearsal_coverage"


@pytest.fixture
def rehearsal(tmp_path: Path):
    core = make_core(tmp_path, DeterministicFakeAudioInput(), DeterministicFakeASRAdapter(), [])
    project = call(core, "project.create", {"name": "Coverage"})["project"]["id"]
    document = call(
        core,
        "presentation.workspace.create_from_outline",
        {
            "project_id": project,
            "title": "Decision",
            "slides": [
                {"title": "Opening", "bullets": ["First point"], "notes": "private notes excluded"},
                {"title": "Detail", "bullets": [" ".join(["observation"] * 10)] * 5, "notes": ""},
                {"title": "Decision", "bullets": ["Next steps"], "notes": ""},
            ],
        },
    )["document"]["id"]
    revision = call(
        core,
        "presentation.workspace.list_revisions",
        {"project_id": project, "document_id": document},
    )["current_revision_id"]
    scope = {"project_id": project, "document_id": document, "expected_revision_id": revision}
    call(core, "presentation.workspace.select_for_rehearsal", scope)
    session = call(
        core,
        "session.start",
        {
            "project_id": project,
            "mode": "run",
            "current_slide_start": 1,
            "expected_presentation_revision_id": revision,
        },
    )["session"]["id"]
    with core._storage.project_database(project) as connection:
        connection.execute(
            "INSERT INTO utterances (id,session_id,actor,text,created_at,start_ms,end_ms, "
            "asr_confidence,slide_ordinal,is_final) "
            "VALUES (?,?,'user',?,'2026-10-08T10:00:00Z',0,2000,NULL,1,1)",
            (str(uuid.uuid4()), session, "We should review this pilot before the next decision."),
        )
        connection.execute(
            "INSERT INTO slide_state_events VALUES (?,?,2,3000,'manual','2026-10-08T10:00:00Z')",
            (str(uuid.uuid4()), session),
        )
        connection.commit()
    call(core, "session.stop", {"project_id": project, "session_id": session})
    try:
        yield core, {**scope, "session_id": session}
    finally:
        core.close()


def test_native_density_and_visit_gaps_are_read_only(rehearsal) -> None:
    core, params = rehearsal
    with core._storage.project_database(params["project_id"]) as connection:
        row = connection.execute(
            "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
            (params["expected_revision_id"],),
        ).fetchone()
    path = core._storage.paths.snapshot_path(params["project_id"], row[0], require_exists=True)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = call(core, METHOD, {**params, "sort": "native_words"})
    assert result["slides"][0]["source_slide_number"] == 2
    assert result["slides"][0]["native_text_words"] == 54
    by_number = {slide["source_slide_number"]: slide for slide in result["slides"]}
    assert by_number[1]["status"] == "recorded_speech"
    assert by_number[1]["native_text_words"] == 6
    assert by_number[2]["status"] == "visited_without_recorded_speech"
    assert by_number[3]["status"] == "no_recorded_visit_or_speech"
    assert result["totals"]["slides_without_recorded_speech"] == 2
    assert result["session_word_count"] == 9
    assert by_number[1]["recorded"]["speaking_time_ms"] == 2000
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert (
        call(
            core,
            "presentation.workspace.list_revisions",
            {key: params[key] for key in ("project_id", "document_id")},
        )["current_revision_id"]
        == params["expected_revision_id"]
    )


def test_filters_and_pages_retain_exact_counts(rehearsal) -> None:
    core, params = rehearsal
    no_speech = call(core, METHOD, {**params, "filter": "no_speech", "limit": 1})
    assert no_speech["total_filtered"] == 2
    assert no_speech["slides"][0]["source_slide_number"] == 2
    assert (
        call(core, METHOD, {**params, "filter": "no_speech", "limit": 1, "offset": 1})["slides"][0][
            "source_slide_number"
        ]
        == 3
    )
    assert call(core, METHOD, {**params, "filter": "no_visit"})["total_filtered"] == 1
    assert call(core, METHOD, {**params, "offset": 10})["slides"] == []


def test_reorder_retains_source_text_and_updates_only_current_ordinal(rehearsal) -> None:
    core, params = rehearsal
    original = call(core, METHOD, params)
    identities = [slide["slide_id"] for slide in original["slides"]]
    revision = call(
        core,
        "presentation.workspace.reorder_slides",
        {
            key: value
            for key, value in {**params, "ordered_slide_ids": identities[::-1]}.items()
            if key != "session_id"
        },
    )["revision_id"]
    current = call(core, METHOD, {**params, "expected_revision_id": revision})
    assert [
        (slide["source_slide_number"], slide["current_slide_number"]) for slide in current["slides"]
    ] == [(3, 1), (2, 2), (1, 3)]
    assert current["source_revision_id"] == params["expected_revision_id"]
    assert current["slides"][2]["native_text_words"] == 6
    assert call(core, METHOD, params, ok=False)["code"] == "PRESENTATION_REVISION_CONFLICT"


@pytest.mark.parametrize(
    "change",
    [
        {"offset": True},
        {"offset": -1},
        {"limit": 51},
        {"limit": False},
        {"filter": "skipped"},
        {"sort": "quality"},
        {"extra": 1},
    ],
)
def test_rejects_invalid_queries(rehearsal, change) -> None:
    core, params = rehearsal
    assert call(core, METHOD, {**params, **change}, ok=False)["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize(
    "change", ["identity", "negative", "boolean", "duplicate", "total", "ordinal"]
)
def test_rejects_corrupt_observations(rehearsal, change) -> None:
    core, params = rehearsal
    with core._storage.project_database(params["project_id"]) as connection:
        data = json.loads(
            connection.execute(
                "SELECT debrief_json FROM run_debriefs WHERE session_id=?", (params["session_id"],)
            ).fetchone()[0]
        )
        if change == "identity":
            data["session"]["session_id"] = str(uuid.uuid4())
        elif change == "negative":
            data["per_slide"][0]["word_count"] = -1
        elif change == "boolean":
            data["per_slide"][0]["utterance_count"] = True
        elif change == "duplicate":
            data["per_slide"].append(data["per_slide"][0])
        elif change == "total":
            data["session"]["word_count"] = 0
        else:
            data["per_slide"][0]["slide_ordinal"] = True
        connection.execute(
            "UPDATE run_debriefs SET debrief_json=? WHERE session_id=?",
            (json.dumps(data), params["session_id"]),
        )
        connection.commit()
    assert call(core, METHOD, params, ok=False)["code"] == "RUN_DEBRIEF_CORRUPT"


def test_unmapped_speech_stays_outside_slide_counts(rehearsal) -> None:
    core, params = rehearsal
    with core._storage.project_database(params["project_id"]) as connection:
        data = json.loads(
            connection.execute(
                "SELECT debrief_json FROM run_debriefs WHERE session_id=?", (params["session_id"],)
            ).fetchone()[0]
        )
        data["per_slide"][0]["slide_ordinal"] = None
        connection.execute(
            "UPDATE run_debriefs SET debrief_json=? WHERE session_id=?",
            (json.dumps(data), params["session_id"]),
        )
        connection.commit()
    result = call(core, METHOD, params)
    assert result["unmapped"]["word_count"] == 9
    assert result["totals"]["slides_with_recorded_speech"] == 0


def test_unrelated_sessions_are_unavailable(rehearsal) -> None:
    core, params = rehearsal
    assert (
        call(core, METHOD, {**params, "session_id": str(uuid.uuid4())}, ok=False)["code"]
        == "REHEARSAL_COVERAGE_UNAVAILABLE"
    )
    other = call(core, "project.create", {"name": "Other"})["project"]["id"]
    assert (
        call(core, METHOD, {**params, "project_id": other}, ok=False)["code"] == "SOURCE_NOT_FOUND"
    )


def test_added_and_removed_slides_are_not_given_false_zero_observations(rehearsal) -> None:
    core, params = rehearsal
    result = call(core, METHOD, params)
    first = result["slides"][0]["slide_id"]
    scope = {key: params[key] for key in ("project_id", "document_id", "expected_revision_id")}
    duplicated = call(core, "presentation.workspace.duplicate_slide", {**scope, "slide_id": first})
    scope["expected_revision_id"] = duplicated["revision_id"]
    deleted = call(core, "presentation.workspace.delete_slide", {**scope, "slide_id": first})
    result = call(core, METHOD, {**params, "expected_revision_id": deleted["revision_id"]})
    added = next(slide for slide in result["slides"] if slide["source_slide_number"] is None)
    assert added["status"] == "not_rehearsed_revision"
    assert added["recorded"] is None and added["native_text_words"] is None
    removed = next(slide for slide in result["slides"] if slide["slide_id"] == first)
    assert removed["current_slide_number"] is None
    assert removed["recorded"]["word_count"] == 9
    assert result["totals"]["slides_added_since_rehearsal"] == 1
    assert result["totals"]["slides_removed_since_rehearsal"] == 1


def test_head_change_during_snapshot_inspection_rejects_late_result(rehearsal, monkeypatch) -> None:
    from presenter_core.presentation import rehearsal_coverage

    core, params = rehearsal
    original = call(core, METHOD, params)
    identities = [slide["slide_id"] for slide in original["slides"]]
    inspect = rehearsal_coverage._slides
    moved = False

    def changing_snapshot(*args):
        nonlocal moved
        slides = inspect(*args)
        if not moved:
            moved = True
            call(
                core,
                "presentation.workspace.reorder_slides",
                {
                    **{
                        key: params[key]
                        for key in ("project_id", "document_id", "expected_revision_id")
                    },
                    "ordered_slide_ids": identities[::-1],
                },
            )
        return slides

    monkeypatch.setattr(rehearsal_coverage, "_slides", changing_snapshot)
    assert call(core, METHOD, params, ok=False)["code"] == "PRESENTATION_REVISION_CONFLICT"
