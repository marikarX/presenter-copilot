"""Actual audited objection persistence remains separate from review and native edits."""

import copy
import json
import uuid

import pytest
import test_rehearsal_coverage as coverage_tests
from test_rehearsal_objection_context import append, parameters, prepare

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.claims import digest
from presenter_core.presentation.rehearsal_objection_analysis import RehearsalObjectionAnalysis
from presenter_core.presentation.rehearsal_objection_store import (
    RehearsalObjectionStore,
    candidate_id,
    validate_snapshot,
)
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.providers.models import ReasoningResult
from presenter_core.providers.service import ProviderService

rehearsal = coverage_tests.rehearsal


class ObjectionProvider(DeterministicFakeReasoningProvider):
    def __init__(self, *, empty=False, action=None, invented=False, locality="local", multi=False):
        super().__init__(locality=locality)
        self.empty, self.action, self.invented = empty, action, invented
        self.multi = multi

    def generate(self, invocation):
        result = super().generate(invocation)
        if self.action:
            self.action()
        speech = json.loads(invocation.request.current_slide_summary)["recorded_speech"]
        quote = {
            "utterance_id": speech[0]["utterance_id"],
            "quote": "invented" if self.invented else speech[0]["text"],
        }
        observations = (
            []
            if self.empty
            else [
                {
                    "concern": "Fixture possible pilot concern",
                    "reason": "Unverified fixture interpretation.",
                    "concern_quotes": [quote],
                    "answer_status": "not_observed",
                    "answer_quotes": [],
                }
            ]
        )
        if self.multi:
            observations.append(
                {
                    **observations[0],
                    "concern": "Fixture second possible concern",
                    "concern_quotes": [
                        {"utterance_id": speech[1]["utterance_id"], "quote": speech[1]["text"]}
                    ],
                }
            )
        return ReasoningResult(
            output={"observations": observations},
            latency_ms=result.latency_ms,
        )


def analysis(core, provider):
    providers = ProviderService(core._storage, provider)
    return RehearsalObjectionAnalysis(
        core._presentation_semantics, providers, ProviderExecutionService(core._storage, providers)
    )


def params(core, scope):
    selected = parameters(core, scope)
    context = prepare(core, selected)
    return {
        **selected,
        "expected_context_sha256": context["context_sha256"],
        "expected_recording_sha256": context["recording_sha256"],
        "window_index": 0,
    }


def saved(core, scope, **kwargs):
    return analysis(core, ObjectionProvider(**kwargs)).analyze(params(core, scope))


def read(core, scope, result):
    return RehearsalObjectionStore(core._presentation_semantics).read(
        {
            **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "analysis_id": result["analysis_id"],
        }
    )


def test_actual_execution_saves_audited_window_and_independent_candidate_without_review_or_edit(
    rehearsal,
):
    core, scope = rehearsal
    result = saved(core, scope)
    detail = read(core, scope, result)
    assert detail["context_current"] and detail["requires_user_review"]
    assert detail["findings"][0]["can_adopt"]
    assert detail["findings"][0]["disposition"] == "unreviewed"
    assert result["finding_ids"] == [detail["findings"][0]["finding_id"]]
    with core._storage.project_database(scope["project_id"]) as db:
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_reviews").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM presentation_claims").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM presentation_revisions").fetchone()[0] == 1
        run = db.execute(
            "SELECT * FROM provider_runs WHERE id=?", (result["provider_run_id"],)
        ).fetchone()
        assert (
            run["task_type"] == "presentation_rehearsal_objections" and run["status"] == "success"
        )


def test_empty_analysis_is_durable_without_a_candidate_or_whole_run_absence_claim(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope, empty=True)
    detail = read(core, scope, result)
    assert result["finding_ids"] == detail["findings"] == []
    assert detail["snapshot"]["hint"] == {"observations": []}
    assert "no_objections" not in detail
    with core._storage.project_database(scope["project_id"]) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM presentation_rehearsal_objection_analyses").fetchone()[
                0
            ]
            == 1
        )
        assert (
            db.execute("SELECT COUNT(*) FROM presentation_rehearsal_objection_findings").fetchone()[
                0
            ]
            == 0
        )


def test_retry_and_restart_preserve_immutable_results_and_distinct_candidate_identities(rehearsal):
    from presenter_core.ipc.core import CoreService
    from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter

    core, scope = rehearsal
    first, second = saved(core, scope), saved(core, scope)
    assert (
        first["analysis_id"] != second["analysis_id"]
        and first["finding_ids"] != second["finding_ids"]
    )
    before = read(core, scope, first)
    restarted = CoreService(
        data_root=core._storage.paths.root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        assert read(restarted, scope, first) == before
    finally:
        restarted.close()


@pytest.mark.parametrize("change", ["selected", "unmapped", "deleted"])
def test_changed_recording_keeps_historical_quotes_but_blocks_candidate_adoption(rehearsal, change):
    core, scope = rehearsal
    result = saved(core, scope)
    original = read(core, scope, result)["snapshot"]
    if change == "unmapped":
        append(core, scope, "Unmapped later recording", ordinal=None)
    else:
        with core._storage.project_database(scope["project_id"]) as db:
            sql = (
                "DELETE FROM utterances WHERE session_id=?"
                if change == "deleted"
                else "UPDATE utterances SET text='Changed transcription' WHERE session_id=?"
            )
            db.execute(sql, (scope["session_id"],))
            db.commit()
    detail = read(core, scope, result)
    assert detail["snapshot"] == original and not detail["context_current"]
    assert not detail["findings"][0]["can_adopt"]


def test_historical_window_metadata_survives_current_privacy_preference_change(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute("UPDATE project SET privacy_mode='selected_context_cloud'")
        db.commit()
    detail = read(core, scope, result)
    assert detail["context_current"] and detail["findings"][0]["can_adopt"]
    assert detail["snapshot"]["privacy_mode"] == "local_only"


@pytest.mark.parametrize("change", ["snapshot", "candidate", "audit", "reason"])
def test_corrupt_storage_or_rehashed_candidate_cannot_become_a_verified_detail(rehearsal, change):
    core, scope = rehearsal
    result = saved(core, scope)
    with core._storage.project_database(scope["project_id"]) as db:
        if change == "snapshot":
            db.execute(
                "UPDATE presentation_rehearsal_objection_analyses SET snapshot_sha256=?",
                ("a" * 64,),
            )
        elif change == "candidate":
            db.execute("DELETE FROM presentation_rehearsal_objection_findings")
        elif change == "audit":
            db.execute("UPDATE provider_runs SET task_type='presentation_rehearsal_coverage'")
        else:
            row = db.execute(
                "SELECT snapshot_json FROM presentation_rehearsal_objection_analyses"
            ).fetchone()
            snapshot = json.loads(row[0])
            snapshot["hint"]["observations"][0]["reason"] = "Changed after storage"
            raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            db.execute(
                "UPDATE presentation_rehearsal_objection_analyses "
                "SET snapshot_json=?,snapshot_sha256=?",
                (raw, digest(raw)),
            )
        db.commit()
    with pytest.raises(CoreDomainError) as error:
        read(core, scope, result)
    assert error.value.code == "REHEARSAL_OBJECTION_CORRUPT"


def test_invented_provider_quote_has_error_audit_and_no_analysis_or_candidate(rehearsal):
    core, scope = rehearsal
    with pytest.raises(CoreDomainError):
        saved(core, scope, invented=True)
    with core._storage.project_database(scope["project_id"]) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM presentation_rehearsal_objection_analyses").fetchone()[
                0
            ]
            == 0
        )
        assert (
            db.execute("SELECT COUNT(*) FROM presentation_rehearsal_objection_findings").fetchone()[
                0
            ]
            == 0
        )
        assert db.execute("SELECT status FROM provider_runs").fetchone()[0] == "error"


def test_unmapped_recording_change_after_preparation_never_invokes_provider(rehearsal):
    core, scope = rehearsal
    selected = params(core, scope)
    append(core, scope, "Later unmapped question", ordinal=None)
    provider = ObjectionProvider()
    with pytest.raises(CoreDomainError) as error:
        analysis(core, provider).analyze(selected)
    assert error.value.code == "REHEARSAL_CONTEXT_CHANGED" and provider.call_count == 0


@pytest.mark.parametrize(
    "mode,code",
    [
        ("local_only", "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED"),
        ("selected_context_cloud", "PRIVACY_REMOTE_ACK_REQUIRED"),
    ],
)
def test_remote_provider_remains_blocked_before_invocation_without_project_authority(
    rehearsal, mode, code
):
    core, scope = rehearsal
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute(
            "UPDATE project SET privacy_mode=?,remote_reasoning_acknowledged_at=NULL", (mode,)
        )
        db.commit()
    provider = ObjectionProvider(locality="remote")
    with pytest.raises(CoreDomainError) as error:
        analysis(core, provider).analyze(params(core, scope))
    assert error.value.code == code and provider.call_count == 0


@pytest.mark.parametrize(
    "change",
    [
        {"speaker_identity_verified": True},
        {"asr_accuracy_verified": True},
        {"total_utterances": True},
        {"actor_counts": {"audience": 1}},
        {"has_more": 0},
        {"privacy_mode": "other"},
        {"window_index": 10000},
    ],
)
def test_strict_snapshot_never_upgrades_unverified_labels_or_accepts_invalid_counts(
    rehearsal, change
):
    core, scope = rehearsal
    snapshot = read(core, scope, saved(core, scope))["snapshot"]
    with pytest.raises(CoreDomainError) as error:
        validate_snapshot(snapshot | change)
    assert error.value.code == "REHEARSAL_OBJECTION_CORRUPT"


@pytest.mark.parametrize("change", ["speech", "privacy", "cancel"])
def test_last_storage_guard_refuses_late_changes_without_partial_result(
    rehearsal, monkeypatch, change
):
    core, scope = rehearsal
    original_save = RehearsalObjectionStore.save
    cancelled = False

    def save_after_change(self, project, result, *, transaction_guard):
        nonlocal cancelled
        if change == "cancel":
            cancelled = True
        else:
            with core._storage.project_database(project) as db:
                if change == "speech":
                    db.execute(
                        "UPDATE utterances SET text='Changed after provider' WHERE session_id=?",
                        (scope["session_id"],),
                    )
                else:
                    db.execute("UPDATE project SET privacy_mode='selected_context_cloud'")
                db.commit()
        return original_save(self, project, result, transaction_guard=transaction_guard)

    monkeypatch.setattr(RehearsalObjectionStore, "save", save_after_change)
    with pytest.raises(CoreDomainError):
        analysis(core, ObjectionProvider()).analyze(
            params(core, scope), cancellation_check=lambda: cancelled
        )
    with core._storage.project_database(scope["project_id"]) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM presentation_rehearsal_objection_analyses").fetchone()[
                0
            ]
            == 0
        )
        assert (
            db.execute("SELECT COUNT(*) FROM presentation_rehearsal_objection_findings").fetchone()[
                0
            ]
            == 0
        )
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_reviews").fetchone()[0] == 0


def test_write_locked_recording_change_rolls_back_instead_of_creating_an_adoptable_result(
    rehearsal, monkeypatch
):
    core, scope = rehearsal
    original_save = RehearsalObjectionStore.save
    original_text = prepare(core, parameters(core, scope))["windows"][0]["utterances"][0]["text"]

    def save_with_sql_change(self, project, result, *, transaction_guard):
        def changed(connection):
            transaction_guard(connection)
            connection.execute(
                "UPDATE utterances SET text='Changed inside write lock' WHERE session_id=?",
                (scope["session_id"],),
            )

        return original_save(self, project, result, transaction_guard=changed)

    monkeypatch.setattr(RehearsalObjectionStore, "save", save_with_sql_change)
    with pytest.raises(CoreDomainError) as error:
        saved(core, scope)
    assert error.value.code == "REHEARSAL_CONTEXT_CHANGED"
    assert (
        prepare(core, parameters(core, scope))["windows"][0]["utterances"][0]["text"]
        == original_text
    )
    with core._storage.project_database(scope["project_id"]) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM presentation_rehearsal_objection_analyses").fetchone()[
                0
            ]
            == 0
        )


def test_rehashed_other_window_cannot_replace_original_window_even_with_valid_recorded_quotes(
    rehearsal,
):
    core, scope = rehearsal
    initial = prepare(core, parameters(core, scope))
    original_text = initial["windows"][0]["utterances"][0]["text"]
    for index in range(8):
        append(core, scope, "x" * len(original_text), actor="user", start=3000 + index * 2000)
    result = saved(core, scope)
    snapshot = read(core, scope, result)["snapshot"]
    next_window = prepare(core, {**parameters(core, scope), "offset": 1, "limit": 1})
    substituted = copy.deepcopy(next_window["windows"][0]["utterances"][0])
    # Preserve the serialized timing width as well as text/ID lengths so the
    # audit's bounded-character check cannot stand in for actual window authority.
    substituted["start_ms"] = snapshot["windows"][0]["utterances"][0]["start_ms"]
    substituted["end_ms"] = snapshot["windows"][0]["utterances"][0]["end_ms"]
    snapshot["windows"][0]["utterances"][0] = substituted
    snapshot["hint"]["observations"][0]["concern_quotes"] = [
        {
            "utterance_id": substituted["utterance_id"],
            "quote": substituted["text"],
        }
    ]
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    identity = candidate_id(result["provider_run_id"], 0, snapshot["hint"]["observations"][0])
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute(
            "UPDATE presentation_rehearsal_objection_analyses "
            "SET snapshot_json=?,snapshot_sha256=?",
            (raw, digest(raw)),
        )
        db.execute("UPDATE presentation_rehearsal_objection_findings SET finding_id=?", (identity,))
        db.commit()
    with pytest.raises(CoreDomainError) as error:
        read(core, scope, result)
    assert error.value.code == "REHEARSAL_OBJECTION_CORRUPT"


def test_foreign_analysis_identity_cannot_open_another_document_history(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    with pytest.raises(CoreDomainError):
        RehearsalObjectionStore(core._presentation_semantics).read(
            {
                **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
                "analysis_id": str(uuid.uuid4()),
            }
        )
    assert read(core, scope, result)["analysis_id"] == result["analysis_id"]


def test_individual_candidate_dispositions_remain_independent_in_durable_history(rehearsal):
    core, scope = rehearsal
    append(core, scope, "How much does this pilot cost?")
    result = saved(core, scope, multi=True)
    assert len(result["finding_ids"]) == 2
    # Seed a reviewed disposition, not an assertion that the future review RPC/GUI
    # exists. The immutable candidate's sibling must retain its own state.
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute(
            "INSERT INTO presentation_rehearsal_reviews VALUES (?,?,?,?,?,NULL,'rejected','now')",
            (
                result["finding_ids"][0],
                scope["session_id"],
                scope["document_id"],
                scope["expected_revision_id"],
                scope["expected_revision_id"],
            ),
        )
        db.commit()
    detail = read(core, scope, result)
    assert [f["disposition"] for f in detail["findings"]] == ["rejected", "unreviewed"]
    assert [f["can_adopt"] for f in detail["findings"]] == [False, True]
    assert (
        detail["findings"][1]["observation"]["concern_quotes"][0]["quote"]
        == "How much does this pilot cost?"
    )


def test_original_slide_context_survives_reorder_and_removed_slide_disables_adoption(rehearsal):
    from test_presentation_planning import call

    core, scope = rehearsal
    result = saved(core, scope)
    _, _, _, source = core._presentation_workspace_sources.read_revision_inventory(
        {
            "project_id": scope["project_id"],
            "document_id": scope["document_id"],
            "revision_id": scope["expected_revision_id"],
        }
    )
    revision = call(
        core,
        "presentation.workspace.reorder_slides",
        {
            **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "ordered_slide_ids": [slide.slide_id for slide in source.slides][::-1],
        },
    )["revision_id"]
    latest_scope = scope | {"expected_revision_id": revision}
    detail = read(core, latest_scope, result)
    assert detail["context_current"] and detail["current_slide_number"] == 3
    assert detail["snapshot"]["source_slide_number"] == 1
    assert detail["findings"][0]["can_adopt"]
    deleted = call(
        core,
        "presentation.workspace.delete_slide",
        {
            **{k: latest_scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "slide_id": result["slide_id"],
        },
    )
    detail = read(core, scope | {"expected_revision_id": deleted["revision_id"]}, result)
    assert detail["context_current"] and detail["current_slide_number"] is None
    assert not detail["findings"][0]["can_adopt"]


def test_native_snapshot_change_under_storage_lock_prevents_partial_candidate(
    rehearsal, monkeypatch
):
    core, scope = rehearsal
    guard = RehearsalObjectionStore.native_guard

    def changed(self, connection, project, result):
        row = connection.execute(
            "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
            (result["source_revision_id"],),
        ).fetchone()
        path = core._storage.paths.snapshot_path(project, row[0], require_exists=True)
        original = path.read_bytes()
        try:
            path.write_bytes(original + b"changed-after-preparation")
            guard(self, connection, project, result)
        finally:
            path.write_bytes(original)

    monkeypatch.setattr(RehearsalObjectionStore, "native_guard", changed)
    with pytest.raises(CoreDomainError) as error:
        saved(core, scope)
    assert error.value.code == "SOURCE_SNAPSHOT_CHANGED"
    with core._storage.project_database(scope["project_id"]) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM presentation_rehearsal_objection_analyses").fetchone()[
                0
            ]
            == 0
        )
        assert (
            db.execute("SELECT COUNT(*) FROM presentation_rehearsal_objection_findings").fetchone()[
                0
            ]
            == 0
        )
