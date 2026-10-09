"""Unverified coverage hints enter native revisions only through explicit reviewed edits."""

import hashlib
import json
import uuid

import pytest
import test_rehearsal_coverage as coverage_tests
from test_presentation_planning import call
from test_rehearsal_analysis_store import read, saved

from presenter_core.presentation.rewrite import PresentationRewriteService
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.providers.service import ProviderService

rehearsal = coverage_tests.rehearsal


def selection(scope, result):
    return {
        **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
        "finding_id": result["finding_id"],
    }


def edit(scope, result, kind="notes"):
    payload = selection(scope, result) | {
        "slide_id": result["slide_id"],
        "edit_kind": kind,
        "expected_text": "private notes excluded" if kind == "notes" else "First point",
        "replacement_text": "User reviewed: explain the pilot before asking for the decision.",
    }
    if kind == "text":
        payload["object_id"] = result["point"]["object_id"]
    return payload


def rewrite_service(core, provider):
    providers = ProviderService(core._storage, provider)
    core._presentation_rewrites = PresentationRewriteService(
        core._storage,
        core._presentation_workspace_sources,
        providers,
        ProviderExecutionService(core._storage, providers),
        core._presentation_rehearsal,
    )


def rewrite_params(scope, result):
    return {
        **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
        "slide_number": 1,
        "object_id": result["point"]["object_id"],
        "instruction": "Clarify this point using my reviewed window hint.",
        "rehearsal_finding_id": result["finding_id"],
    }


def native_files(core, scope):
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in core._storage.project_paths(scope["project_id"]).root.rglob("*.pptx")
    }


def test_exact_semantic_resolution_bypasses_debrief_and_latest_ten_cap(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    with core._storage.project_database(scope["project_id"]) as db:
        row = dict(
            db.execute("SELECT * FROM sessions WHERE id=?", (scope["session_id"],)).fetchone()
        )
        columns = list(row)
        for index in range(12):
            later = row | {"id": str(uuid.uuid4()), "started_at": f"2026-10-09T12:{index:02d}:00Z"}
            db.execute(
                f"INSERT INTO sessions ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                [later[key] for key in columns],
            )
        db.execute(
            "UPDATE run_debriefs SET debrief_json='broken JSON' WHERE session_id=?",
            (scope["session_id"],),
        )
        db.commit()
    finding = core._presentation_rehearsal.resolve_finding(selection(scope, result))
    assert finding["kind"] == "semantic_coverage" and finding["quote"] == "First point"
    assert finding["source_revision_number"] == 1
    assert finding["semantic_review"]["reason"] == result["hint"]["reason"]
    assert not finding["semantic_review"]["recorded_speech_included"]


def test_dismiss_reopen_and_retry_have_independent_dispositions(rehearsal):
    core, scope = rehearsal
    result, retry = saved(core, scope), saved(core, scope)
    before = native_files(core, scope)
    call(core, "presentation.workspace.reject_rehearsal_finding", selection(scope, result))
    assert read(core, scope, result)["disposition"] == "rejected"
    assert read(core, scope, retry)["disposition"] == "unreviewed"
    call(
        core,
        "presentation.workspace.reject_rehearsal_finding",
        selection(scope, result) | {"reopen": True},
    )
    assert read(core, scope, result)["disposition"] == "unreviewed"
    assert native_files(core, scope) == before


@pytest.mark.parametrize("kind", ["notes", "text"])
def test_explicit_native_save_records_atomic_disposition(rehearsal, kind):
    core, scope = rehearsal
    result = saved(core, scope)
    applied = call(core, "presentation.workspace.apply_rehearsal_edit", edit(scope, result, kind))
    assert applied["changed"] and applied["parent_revision_id"] == scope["expected_revision_id"]
    current = scope | {"expected_revision_id": applied["revision_id"]}
    item = read(core, current, result)
    assert (
        item["disposition"] == "applied" and item["applied_revision_id"] == applied["revision_id"]
    )
    assert item["snapshot"]["source_revision_id"] == scope["expected_revision_id"]
    assert item["snapshot"]["point"]["quote"] == "First point" and not item["can_adopt"]
    assert (
        call(
            core,
            "presentation.workspace.reject_rehearsal_finding",
            selection(current, result) | {"reopen": True},
            ok=False,
        )["code"]
        == "REHEARSAL_FINDING_REVIEWED"
    )
    assert (
        call(
            core,
            "presentation.workspace.apply_rehearsal_edit",
            edit(current, result, kind),
            ok=False,
        )["code"]
        == "REHEARSAL_FINDING_REVIEWED"
    )


def test_stale_recording_blocks_adoption_but_remains_dismissible(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    provider = DeterministicFakeReasoningProvider(locality="local")
    rewrite_service(core, provider)
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute(
            "UPDATE utterances SET text='changed recording' WHERE session_id=?",
            (scope["session_id"],),
        )
        db.commit()
    before = native_files(core, scope)
    assert (
        call(core, "presentation.workspace.apply_rehearsal_edit", edit(scope, result), ok=False)[
            "code"
        ]
        == "REHEARSAL_CONTEXT_CHANGED"
    )
    assert (
        call(
            core,
            "presentation.workspace.propose_text_rewrite",
            rewrite_params(scope, result),
            ok=False,
        )["code"]
        == "REHEARSAL_CONTEXT_CHANGED"
    )
    assert provider.call_count == 0 and native_files(core, scope) == before
    call(core, "presentation.workspace.reject_rehearsal_finding", selection(scope, result))
    call(
        core,
        "presentation.workspace.reject_rehearsal_finding",
        selection(scope, result) | {"reopen": True},
    )
    assert read(core, scope, result)["disposition"] == "unreviewed"
    assert not read(core, scope, result)["context_current"]


def test_text_and_rewrite_cannot_adopt_to_another_object(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    targets = call(
        core,
        "presentation.workspace.list_text_targets",
        {
            "project_id": scope["project_id"],
            "document_id": scope["document_id"],
            "revision_id": scope["expected_revision_id"],
            "slide_number": 1,
        },
    )["targets"]
    other = next(
        target for target in targets if target["object_id"] != result["point"]["object_id"]
    )
    provider = DeterministicFakeReasoningProvider(locality="local")
    rewrite_service(core, provider)
    assert (
        call(
            core,
            "presentation.workspace.apply_rehearsal_edit",
            edit(scope, result, "text")
            | {"object_id": other["object_id"], "expected_text": other["current_text"]},
            ok=False,
        )["code"]
        == "INVALID_REQUEST"
    )
    assert (
        call(
            core,
            "presentation.workspace.propose_text_rewrite",
            rewrite_params(scope, result) | {"object_id": other["object_id"]},
            ok=False,
        )["code"]
        == "INVALID_REQUEST"
    )
    assert provider.call_count == 0


def test_rewrite_keeps_native_quote_and_model_hint_separate_without_knowledge(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    provider = DeterministicFakeReasoningProvider(locality="local")
    rewrite_service(core, provider)
    before = native_files(core, scope)
    rewritten = call(
        core, "presentation.workspace.propose_text_rewrite", rewrite_params(scope, result)
    )
    request = provider.request_objects[-1]
    context = json.loads(request.current_slide_summary)["rehearsal_finding"]
    assert context["quote"] == "First point" and context["kind"] == "semantic_coverage"
    assert context["semantic_review"]["status"] == result["hint"]["status"]
    assert context["semantic_review"]["reason"] == result["hint"]["reason"]
    assert (
        context["semantic_review"]["provenance"] == "unverified_model_hint_from_one_recorded_window"
    )
    assert (
        not request.evidence
        and not request.preferred_user_explanations
        and not request.speaker_evidence
    )
    assert (
        native_files(core, scope) == before
        and read(core, scope, result)["disposition"] == "unreviewed"
    )
    with core._storage.project_database(scope["project_id"]) as db:
        manifest = json.loads(
            db.execute(
                "SELECT context_manifest_json FROM provider_runs WHERE id=?",
                (rewritten["provider_run_id"],),
            ).fetchone()[0]
        )
    assert manifest["rehearsal_finding_ids"] == [result["finding_id"]]
    assert manifest["rehearsal_session_ids"] == [scope["session_id"]]


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("speech", "REHEARSAL_CONTEXT_CHANGED"),
        ("review", "REHEARSAL_FINDING_REVIEWED"),
        ("analysis", "REHEARSAL_ANALYSIS_CORRUPT"),
    ],
)
def test_transaction_guard_rolls_back_native_revision_and_disposition(
    rehearsal, monkeypatch, mutation, code
):
    core, scope = rehearsal
    result = saved(core, scope)
    before = native_files(core, scope)
    method = core._presentation_rehearsal._edits.replace_speaker_notes

    def changed(params, *, on_commit):
        def callback(db, revision):
            if mutation == "speech":
                db.execute(
                    "UPDATE utterances SET text='late recording change' WHERE session_id=?",
                    (scope["session_id"],),
                )
            elif mutation == "review":
                db.execute(
                    "INSERT INTO presentation_rehearsal_reviews VALUES (?,?,?,?,?,?,?,?)",
                    (
                        result["finding_id"],
                        scope["session_id"],
                        scope["document_id"],
                        scope["expected_revision_id"],
                        scope["expected_revision_id"],
                        None,
                        "rejected",
                        "now",
                    ),
                )
            else:
                db.execute(
                    "UPDATE presentation_rehearsal_analyses SET snapshot_sha256=?", ("0" * 64,)
                )
            on_commit(db, revision)

        return method(params, on_commit=callback)

    monkeypatch.setattr(core._presentation_rehearsal._edits, "replace_speaker_notes", changed)
    error = call(core, "presentation.workspace.apply_rehearsal_edit", edit(scope, result), ok=False)
    assert error["code"] == code
    assert native_files(core, scope) == before
    with core._storage.project_database(scope["project_id"]) as db:
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_reviews").fetchone()[0] == 0
        assert (
            db.execute("SELECT revision_id FROM presentation_revision_heads").fetchone()[0]
            == scope["expected_revision_id"]
        )
    assert read(core, scope, result)["disposition"] == "unreviewed"


def test_recording_change_during_rewrite_rejects_provider_output(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)

    class ChangedProvider(DeterministicFakeReasoningProvider):
        def generate(self, invocation):
            output = super().generate(invocation)
            with core._storage.project_database(scope["project_id"]) as db:
                db.execute(
                    "UPDATE utterances SET text='changed during rewrite' WHERE session_id=?",
                    (scope["session_id"],),
                )
                db.commit()
            return output

    provider = ChangedProvider(locality="local")
    rewrite_service(core, provider)
    before = native_files(core, scope)
    error = call(
        core, "presentation.workspace.propose_text_rewrite", rewrite_params(scope, result), ok=False
    )
    assert error["code"] == "REHEARSAL_CONTEXT_CHANGED" and provider.call_count == 1
    assert (
        native_files(core, scope) == before
        and read(core, scope, result)["disposition"] == "unreviewed"
    )
    with core._storage.project_database(scope["project_id"]) as db:
        row = db.execute(
            "SELECT status,error_code FROM provider_runs "
            "WHERE task_type='presentation_text_rewrite'"
        ).fetchone()
    assert row["status"] == "error" and row["error_code"] == "REHEARSAL_CONTEXT_CHANGED"


def test_reordered_source_identity_enters_explicit_notes_save(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    coverage = call(core, "presentation.workspace.rehearsal_coverage", scope)
    revision = call(
        core,
        "presentation.workspace.reorder_slides",
        {
            **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "ordered_slide_ids": [item["slide_id"] for item in coverage["slides"]][::-1],
        },
    )["revision_id"]
    current = scope | {"expected_revision_id": revision}
    finding = core._presentation_rehearsal.resolve_finding(selection(current, result))
    assert finding["source_slide_number"] == 1 and finding["current_slide_number"] == 3
    applied = call(core, "presentation.workspace.apply_rehearsal_edit", edit(current, result))
    assert applied["parent_revision_id"] == revision
    item = read(core, current | {"expected_revision_id": applied["revision_id"]}, result)
    assert item["disposition"] == "applied" and item["snapshot"]["source_slide_number"] == 1


def test_deleted_point_can_recover_intent_in_notes_but_cannot_rewrite_unrelated_text(rehearsal):
    from test_selection_actions import save

    core, scope = rehearsal
    result = saved(core, scope)
    current = {k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")}
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
    target = next(
        item for item in inventory["objects"] if item["object_id"] == result["point"]["object_id"]
    )
    plan = core._presentation_edit_plans.prepare(
        {
            **current,
            "summary": "Delete source point after the recording",
            "operations": [
                {
                    "type": "delete_object",
                    "params": {
                        "slide_id": result["slide_id"],
                        "object_id": target["object_id"],
                        "expected_geometry": target["geometry"],
                    },
                }
            ],
        }
    )
    save(core, current, plan)
    fresh = scope | {"expected_revision_id": current["expected_revision_id"]}
    assert read(core, fresh, result)["current_span_status"] == "missing"
    provider = DeterministicFakeReasoningProvider(locality="local")
    rewrite_service(core, provider)
    call(
        core, "presentation.workspace.propose_text_rewrite", rewrite_params(fresh, result), ok=False
    )
    assert provider.call_count == 0
    applied = call(core, "presentation.workspace.apply_rehearsal_edit", edit(fresh, result))
    assert applied["changed"]
    assert (
        read(core, fresh | {"expected_revision_id": applied["revision_id"]}, result)["disposition"]
        == "applied"
    )
