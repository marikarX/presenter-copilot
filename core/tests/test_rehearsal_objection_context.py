"""Objection windows retain original recording ownership, actors and complete text."""

import json
import uuid

import pytest
import test_rehearsal_coverage as coverage_tests
from test_rehearsal_semantic_context import selection

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.rehearsal_objection_context import (
    SOURCE_FIELDS,
    RehearsalObjectionContext,
    objection_context_size,
    objection_request,
)
from presenter_core.providers.context import MAX_TOTAL_CONTEXT_CHARS

rehearsal = coverage_tests.rehearsal


def parameters(core, scope, number=1):
    result = selection(core, scope, number)
    result.pop("object_id")
    return result


def prepare(core, params):
    return RehearsalObjectionContext(core._presentation_semantics).prepare(params)


def append(core, scope, text, actor="unknown_audience", ordinal=1, start=3000):
    identity = str(uuid.uuid4())
    with core._storage.project_database(scope["project_id"]) as connection:
        connection.execute(
            "INSERT INTO utterances(id,session_id,actor,text,created_at,start_ms,end_ms,"
            "slide_ordinal,is_final) VALUES (?,?,?,?,'2026-10-08T10:00:00Z',?,?,?,1)",
            (identity, scope["session_id"], actor, text, start, start + 1000, ordinal),
        )
        connection.commit()
    return identity


def test_all_original_actor_labels_remain_unverified_and_private_notes_are_excluded(rehearsal):
    core, scope = rehearsal
    for actor in ("unknown_audience", "ai_coach", "audience_profile"):
        append(core, scope, f"Who owns this pilot? Recorded actor {actor}", actor)
    result = prepare(core, parameters(core, scope))
    assert result["actor_counts"] == dict.fromkeys(
        ("user", "unknown_audience", "ai_coach", "audience_profile"), 1
    )
    assert result["total_utterances"] == 4 and result["total_windows"] == 1
    assert not result["speaker_identity_verified"] and not result["asr_accuracy_verified"]
    assert result["recording_completeness"] == "unknown"
    assert "private notes excluded" not in json.dumps(result)
    assert "point" not in result  # Detection does not require an editable native text object.
    with core._storage.project_database(scope["project_id"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 0
        assert (
            connection.execute("SELECT COUNT(*) FROM presentation_rehearsal_reviews").fetchone()[0]
            == 0
        )


def test_paged_escaped_windows_preserve_every_utterance_and_measure_actual_request(rehearsal):
    core, scope = rehearsal
    params = parameters(core, scope)
    identities = [
        append(core, scope, ('Quoted \\" concern ' * 400)[:4000], start=3000 + i * 2000)
        for i in range(9)
    ]
    initial = prepare(core, {**params, "limit": 1})
    speech = []
    for offset in range(initial["total_windows"]):
        result = prepare(core, {**params, "offset": offset, "limit": 1})
        assert result["context_sha256"] == initial["context_sha256"]
        assert result["recording_sha256"] == initial["recording_sha256"]
        window = result["windows"][0]
        request = objection_request(
            {k: result[k] for k in SOURCE_FIELDS}, window["utterances"], "local_only"
        )
        assert window["serialized_context_chars"] == objection_context_size(request)
        assert objection_context_size(request) <= MAX_TOTAL_CONTEXT_CHARS
        speech.extend(window["utterances"])
    assert len(speech) == 10 and [u["utterance_id"] for u in speech[1:]] == identities
    assert all(len(u["text"]) == 4000 for u in speech[1:])


def test_no_recorded_speech_does_not_assert_no_objections(rehearsal):
    core, scope = rehearsal
    result = prepare(core, parameters(core, scope, 2))
    assert result["total_windows"] == result["total_utterances"] == 0
    assert result["windows"] == [] and not result["has_recorded_speech"]
    assert "observations" not in result and "answer_status" not in result


@pytest.mark.parametrize(
    "change",
    [
        {"session_id": str(uuid.uuid4())},
        {"slide_id": str(uuid.uuid4())},
        {"offset": True},
        {"offset": -1},
        {"limit": 21},
        {"limit": False},
        {"object_id": str(uuid.uuid4())},
        {"quote": "arbitrary"},
        {"confirm": True},
    ],
)
def test_unowned_context_and_invalid_selection_are_rejected(rehearsal, change):
    core, scope = rehearsal
    with pytest.raises(CoreDomainError):
        prepare(core, {**parameters(core, scope), **change})


def test_unknown_ordinal_is_disclosed_and_whole_recording_change_invalidates_guard(rehearsal):
    core, scope = rehearsal
    params = parameters(core, scope)
    original = prepare(core, params)
    append(core, scope, "Question without an original slide", ordinal=None)
    changed = prepare(core, params)
    assert changed["unmapped_session_utterances"] == 1
    assert changed["context_sha256"] == original["context_sha256"]
    assert changed["recording_sha256"] != original["recording_sha256"]
    assert "Question without an original slide" not in json.dumps(changed)


def test_unfit_escaped_utterance_is_rejected_instead_of_truncated(rehearsal):
    core, scope = rehearsal
    append(core, scope, "\x01" * 4000)
    with pytest.raises(CoreDomainError, match="cannot fit"):
        prepare(core, parameters(core, scope))


def test_recording_mutation_during_snapshot_read_is_rejected(rehearsal, monkeypatch):
    core, scope = rehearsal
    params = parameters(core, scope)
    require = core._presentation_semantics._require_current_presentation

    def mutate(connection, *args):
        connection.execute(
            "UPDATE utterances SET text='Changed during preparation' WHERE session_id=?",
            (scope["session_id"],),
        )
        connection.commit()
        return require(connection, *args)

    monkeypatch.setattr(core._presentation_semantics, "_require_current_presentation", mutate)
    with pytest.raises(CoreDomainError) as error:
        prepare(core, params)
    assert error.value.code == "REHEARSAL_CONTEXT_CHANGED"


def test_active_run_cannot_be_selected_even_if_recorded_rows_exist(rehearsal):
    core, scope = rehearsal
    with core._storage.project_database(scope["project_id"]) as connection:
        connection.execute("UPDATE sessions SET status='active' WHERE id=?", (scope["session_id"],))
        connection.commit()
    with pytest.raises(CoreDomainError) as error:
        prepare(core, parameters(core, scope))
    assert error.value.code == "REHEARSAL_ANALYSIS_UNAVAILABLE"


def test_privacy_preference_does_not_relabel_unchanged_recording_as_stale(rehearsal):
    from presenter_core.presentation.rehearsal_analysis_store import recording_state

    core, scope = rehearsal
    params = parameters(core, scope)
    original = prepare(core, params)
    with core._storage.project_database(scope["project_id"]) as connection:
        assert original["recording_sha256"] == recording_state(connection, scope["session_id"])
        connection.execute(
            "UPDATE project SET privacy_mode='selected_context_cloud' WHERE id=?",
            (scope["project_id"],),
        )
        connection.commit()
    changed = prepare(core, params)
    assert changed["recording_sha256"] == original["recording_sha256"]
    assert changed["context_sha256"] == original["context_sha256"]
