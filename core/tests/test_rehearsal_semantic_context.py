"""Speech coverage contexts preserve complete windows and frozen native authority."""

import json
import uuid

import pytest
import test_rehearsal_coverage as coverage_tests
from test_presentation_planning import call

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.rehearsal_semantic_context import (
    RehearsalSemanticContext,
    coverage_context_size,
    coverage_request,
)
from presenter_core.providers.context import MAX_TOTAL_CONTEXT_CHARS

rehearsal = coverage_tests.rehearsal


def selection(core, scope, number=1):
    _, _, _, source = core._presentation_workspace_sources.read_revision_inventory(
        {
            "project_id": scope["project_id"],
            "document_id": scope["document_id"],
            "revision_id": scope["expected_revision_id"],
        }
    )
    target = next(
        t for t in source.text_targets(number)["semantic_targets"] if t["name"] == "Point 1"
    )
    return {
        **scope,
        "slide_id": source.slides[number - 1].slide_id,
        "object_id": target["object_id"],
    }


def prepare(core, params):
    return RehearsalSemanticContext(core._presentation_semantics).prepare(params)


def test_frozen_point_and_actual_speech_without_private_notes_or_inference(rehearsal):
    core, scope = rehearsal
    params = selection(core, scope)
    result = prepare(core, params)
    assert call(core, "presentation.workspace.prepare_rehearsal_coverage_review", params) == result
    assert result["point"]["quote"] == "First point"
    assert result["current_span_status"] == "unchanged"
    assert result["source_revision_id"] == scope["expected_revision_id"]
    assert result["total_utterances"] == 1 and result["total_windows"] == 1
    assert result["windows"][0]["utterances"][0]["text"].startswith("We should review")
    assert result["recording_completeness"] == "unknown"
    assert not result["speaker_identity_verified"] and not result["asr_accuracy_verified"]
    assert "private notes excluded" not in json.dumps(result)
    with core._storage.project_database(scope["project_id"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 0
        assert (
            connection.execute("SELECT COUNT(*) FROM presentation_rehearsal_reviews").fetchone()[0]
            == 0
        )


def test_full_speech_windows_paging_and_exact_serialized_budget(rehearsal):
    core, scope = rehearsal
    params = selection(core, scope)
    ids = []
    with core._storage.project_database(scope["project_id"]) as connection:
        for index in range(12):
            key = str(uuid.uuid4())
            ids.append(key)
            connection.execute(
                "INSERT INTO utterances (id,session_id,actor,text,created_at,start_ms,end_ms,"
                "slide_ordinal,is_final) "
                "VALUES (?,?,'user',?,'2026-10-08T10:00:00Z',?,?,1,1)",
                (
                    key,
                    scope["session_id"],
                    ('Quoted \\" text ' * 400)[:4000],
                    (index + 1) * 3000,
                    (index + 1) * 3000 + 1000,
                ),
            )
        connection.commit()
    result = prepare(core, {**params, "limit": 1})
    assert result["total_utterances"] == 13 and result["has_more"]
    assert result["total_windows"] > 1
    windows = []
    for offset in range(result["total_windows"]):
        page = prepare(core, {**params, "offset": offset, "limit": 1})
        assert page["context_sha256"] == result["context_sha256"]
        windows.extend(page["windows"])
    supplied = [u for window in windows for u in window["utterances"]]
    assert len(supplied) == 13 and len({u["utterance_id"] for u in supplied}) == 13
    assert [u["utterance_id"] for u in supplied[1:]] == ids
    native_scope = {
        k: result[k]
        for k in (
            "document_id",
            "session_id",
            "source_revision_id",
            "source_sha256",
            "slide_id",
            "source_slide_number",
        )
    }
    for window in windows:
        request = coverage_request(
            native_scope, result["point"], window["utterances"], "local_only"
        )
        assert coverage_context_size(request) == window["serialized_context_chars"]
        assert coverage_context_size(request) <= MAX_TOTAL_CONTEXT_CHARS
        assert len(window["utterances"]) <= 4


def test_reorder_uses_frozen_identity_and_current_ordinal(rehearsal):
    core, scope = rehearsal
    params = selection(core, scope)
    original = prepare(core, params)
    coverage = call(core, "presentation.workspace.rehearsal_coverage", scope)
    revision = call(
        core,
        "presentation.workspace.reorder_slides",
        {
            **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "ordered_slide_ids": [slide["slide_id"] for slide in coverage["slides"]][::-1],
        },
    )["revision_id"]
    current = prepare(core, {**params, "expected_revision_id": revision})
    assert current["current_slide_number"] == 3 and current["source_slide_number"] == 1
    assert current["context_sha256"] == original["context_sha256"]
    assert current["point"] == original["point"]
    with pytest.raises(CoreDomainError, match="current presentation revision changed"):
        prepare(core, params)


def test_absent_speech_never_becomes_semantic_omission(rehearsal):
    core, scope = rehearsal
    result = prepare(core, selection(core, scope, 2))
    assert result["total_utterances"] == result["total_windows"] == 0
    assert not result["windows"] and result["recording_completeness"] == "unknown"
    assert "omission" not in result and "status" not in result


@pytest.mark.parametrize(
    "change",
    [
        {"quote": "not on this slide"},
        {"quote": ""},
        {"limit": True},
        {"limit": 21},
        {"offset": -1},
        {"object_id": str(uuid.uuid4())},
        {"confirm": True},
    ],
)
def test_rejects_unowned_spans_ids_and_invalid_queries(rehearsal, change):
    core, scope = rehearsal
    with pytest.raises(CoreDomainError):
        prepare(core, {**selection(core, scope), **change})


def test_escaped_utterance_that_cannot_fit_is_rejected_not_truncated(rehearsal):
    core, scope = rehearsal
    with core._storage.project_database(scope["project_id"]) as connection:
        connection.execute(
            "UPDATE utterances SET text=? WHERE session_id=?", ("\x01" * 4000, scope["session_id"])
        )
        connection.commit()
    with pytest.raises(CoreDomainError, match="cannot fit"):
        prepare(core, selection(core, scope))


def test_recording_change_invalidates_context_identity(rehearsal):
    core, scope = rehearsal
    params = selection(core, scope)
    original = prepare(core, params)
    with core._storage.project_database(scope["project_id"]) as connection:
        connection.execute(
            "UPDATE utterances SET text=? WHERE session_id=?",
            ("New recorded wording", scope["session_id"]),
        )
        connection.commit()
    assert prepare(core, params)["context_sha256"] != original["context_sha256"]


def test_unmapped_and_other_recorded_actors_are_disclosed_without_source_promotion(rehearsal):
    core, scope = rehearsal
    with core._storage.project_database(scope["project_id"]) as connection:
        for actor, ordinal in (("user", None), ("ai_coach", 1)):
            connection.execute(
                "INSERT INTO utterances (id,session_id,actor,text,created_at,"
                "slide_ordinal,is_final) "
                "VALUES (?,?,?,'Other recorded words','2026-10-08T10:00:00Z',?,1)",
                (str(uuid.uuid4()), scope["session_id"], actor, ordinal),
            )
        connection.commit()
    result = prepare(core, selection(core, scope))
    assert result["unmapped_session_utterances"] == result["excluded_actor_utterances"] == 1
    assert result["total_utterances"] == 1
    assert "Other recorded words" not in json.dumps(result)


def test_current_native_edit_discloses_change_but_does_not_rewrite_frozen_message(rehearsal):
    from test_selection_actions import save

    core, scope = rehearsal
    params = selection(core, scope)
    original = prepare(core, params)
    edits = {k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")}
    proposed = core._presentation_edit_plans.prepare(
        {
            **edits,
            "summary": "Change native message after rehearsal",
            "operations": [
                {
                    "type": "replace_text_shape",
                    "params": {
                        "operation_type": "replace_text_shape",
                        "slide_id": params["slide_id"],
                        "object_id": params["object_id"],
                        "expected_text": "First point",
                        "replacement_text": "Current different message",
                    },
                }
            ],
        }
    )
    save(core, edits, proposed)
    current = prepare(core, {**params, "expected_revision_id": edits["expected_revision_id"]})
    assert current["current_span_status"] == "changed"
    assert current["point"] == original["point"]
    assert current["context_sha256"] == original["context_sha256"]


def test_other_project_and_active_session_cannot_read_bound_speech(rehearsal):
    core, scope = rehearsal
    params = selection(core, scope)
    other = call(core, "project.create", {"name": "Other"})["project"]["id"]
    assert "windows" not in call(
        core,
        "presentation.workspace.prepare_rehearsal_coverage_review",
        {
            **params,
            "project_id": other,
        },
        ok=False,
    )
    with core._storage.project_database(scope["project_id"]) as connection:
        connection.execute("UPDATE sessions SET status='active' WHERE id=?", (scope["session_id"],))
        connection.commit()
    with pytest.raises(CoreDomainError, match="ended Run"):
        prepare(core, params)


def test_overlapping_repeated_quote_is_ambiguous_in_actual_native_message(rehearsal):
    core, scope = rehearsal
    document = call(
        core,
        "presentation.workspace.create_from_outline",
        {
            "project_id": scope["project_id"],
            "title": "Overlapping quote",
            "slides": [{"title": "Message", "bullets": ["aaa"], "notes": ""}],
        },
    )["document"]["id"]
    revision = call(
        core,
        "presentation.workspace.list_revisions",
        {
            "project_id": scope["project_id"],
            "document_id": document,
        },
    )["current_revision_id"]
    fresh = {
        "project_id": scope["project_id"],
        "document_id": document,
        "expected_revision_id": revision,
    }
    call(core, "presentation.workspace.select_for_rehearsal", fresh)
    session = call(
        core,
        "session.start",
        {
            "project_id": fresh["project_id"],
            "mode": "run",
            "current_slide_start": 1,
            "expected_presentation_revision_id": revision,
        },
    )["session"]["id"]
    call(core, "session.stop", {"project_id": fresh["project_id"], "session_id": session})
    with pytest.raises(CoreDomainError, match="unique message span"):
        prepare(core, {**selection(core, {**fresh, "session_id": session}), "quote": "aa"})


def test_final_head_check_rejects_change_after_native_read(rehearsal, monkeypatch):
    core, scope = rehearsal
    params = selection(core, scope)
    calls = []

    def changed(*args):
        calls.append(True)
        raise CoreDomainError("PRESENTATION_REVISION_CONFLICT", "Injected head change")

    monkeypatch.setattr(core._presentation_semantics, "_require_current_presentation", changed)
    with pytest.raises(CoreDomainError, match="Injected head change"):
        prepare(core, params)
    assert calls


def test_deleted_current_point_stays_historical_context_and_tampered_source_is_rejected(rehearsal):
    from test_selection_actions import save

    core, scope = rehearsal
    params = selection(core, scope)
    original = prepare(core, params)
    inventory = call(
        core,
        "presentation.workspace.list_text_targets",
        {
            "project_id": scope["project_id"],
            "document_id": scope["document_id"],
            "revision_id": scope["expected_revision_id"],
            "slide_number": 1,
        },
    )
    target = next(o for o in inventory["objects"] if o["object_id"] == params["object_id"])
    edits = {k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")}
    proposed = core._presentation_edit_plans.prepare(
        {
            **edits,
            "summary": "Delete a point after recording",
            "operations": [
                {
                    "type": "delete_object",
                    "params": {
                        "slide_id": params["slide_id"],
                        "object_id": params["object_id"],
                        "expected_geometry": target["geometry"],
                    },
                }
            ],
        }
    )
    save(core, edits, proposed)
    fresh = {**params, "expected_revision_id": edits["expected_revision_id"]}
    result = prepare(core, fresh)
    assert result["current_span_status"] == "missing" and result["point"] == original["point"]
    with core._storage.project_database(scope["project_id"]) as connection:
        relative = connection.execute(
            "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
            (scope["expected_revision_id"],),
        ).fetchone()[0]
    snapshot = core._storage.paths.snapshot_path(scope["project_id"], relative, require_exists=True)
    snapshot.write_bytes(snapshot.read_bytes() + b"tampered")
    with pytest.raises(CoreDomainError):
        prepare(core, fresh)
