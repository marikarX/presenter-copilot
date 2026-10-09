"""Actual objection IPC shares queue bounds and transactional cancellation with coverage."""

import json
import threading
import uuid

import pytest
import test_rehearsal_coverage as coverage_tests
from test_presentation_planning import call
from test_rehearsal_analysis_jobs import owner, terminal
from test_rehearsal_objection_context import append, parameters
from test_rehearsal_objection_store import ObjectionProvider, params
from test_rehearsal_semantic_analysis import params as coverage_params

from presenter_core.presentation.rehearsal_objection_store import RehearsalObjectionStore

rehearsal = coverage_tests.rehearsal
PREFIX = "presentation.workspace."


def start(core, scope):
    return call(core, PREFIX + "start_rehearsal_objections_analysis", params(core, scope))


def counts(core, scope):
    with core._storage.project_database(scope["project_id"]) as db:
        return tuple(
            db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "presentation_rehearsal_objection_analyses",
                "presentation_rehearsal_objection_findings",
                "presentation_rehearsal_reviews",
            )
        )


@pytest.mark.parametrize("empty", [False, True])
def test_actual_ipc_preparation_completion_and_verified_detail(rehearsal, monkeypatch, empty):
    core, scope = rehearsal
    append(core, scope, "What is the pilot cost?")
    monkeypatch.setattr(
        core._providers, "_injected_provider", ObjectionProvider(empty=empty, multi=not empty)
    )
    context = call(core, PREFIX + "prepare_rehearsal_objections_review", parameters(core, scope))
    assert not context["speaker_identity_verified"] and counts(core, scope) == (0, 0, 0)
    started = start(core, scope)
    result = terminal(core, scope, started)
    assert result["state"] == "completed" and result["analysis_kind"] == "objections"
    assert set(result["result"]) == {"analysis_id", "finding_ids"}
    assert len(result["result"]["finding_ids"]) == (0 if empty else 2)
    assert "pilot" not in json.dumps(result).lower()
    selected = {k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")}
    detail = call(
        core,
        PREFIX + "get_rehearsal_objections_analysis",
        selected | {"analysis_id": result["result"]["analysis_id"]},
    )
    assert detail["context_current"] and detail["requires_user_review"]
    assert [item["finding_id"] for item in detail["findings"]] == result["result"]["finding_ids"]
    assert counts(core, scope) == (1, 0 if empty else 2, 0)
    assert not call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, started))[
        "cancellation_accepted"
    ]
    call(
        core,
        PREFIX + "get_rehearsal_objections_analysis",
        selected | {"analysis_id": str(uuid.uuid4())},
        ok=False,
    )


def hold_before_storage(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    save = RehearsalObjectionStore.save

    def held(self, *args, **kwargs):
        entered.set()
        assert release.wait(5)
        return save(self, *args, **kwargs)

    monkeypatch.setattr(RehearsalObjectionStore, "save", held)
    return entered, release


def test_cancel_after_inference_prevents_empty_analysis_persistence(rehearsal, monkeypatch):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", ObjectionProvider(empty=True))
    entered, release = hold_before_storage(monkeypatch)
    try:
        started = start(core, scope)
        assert entered.wait(3)
        assert call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, started))[
            "cancellation_accepted"
        ]
        release.set()
        assert terminal(core, scope, started)["state"] == "cancelled"
        assert counts(core, scope) == (0, 0, 0)
    finally:
        release.set()


def test_cancel_inside_objection_commit_is_truthfully_too_late(rehearsal, monkeypatch):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", ObjectionProvider())
    entered, release = threading.Event(), threading.Event()
    guard = RehearsalObjectionStore.native_guard

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return guard(*args, **kwargs)

    monkeypatch.setattr(RehearsalObjectionStore, "native_guard", held)
    try:
        started = start(core, scope)
        assert entered.wait(3)
        reply = call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, started))
        assert reply["state"] == "committing" and not reply["cancellation_accepted"]
        assert not reply["terminal"]
        release.set()
        assert terminal(core, scope, started)["state"] == "completed"
        assert counts(core, scope) == (1, 1, 0)
    finally:
        release.set()


@pytest.mark.parametrize("method", ["session.delete", "source.delete", "project.delete"])
def test_objection_worker_prevents_deletion_until_terminal(rehearsal, monkeypatch, method):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", ObjectionProvider())
    core._rehearsal_analysis_jobs._join_timeout = 0.01
    entered, release = hold_before_storage(monkeypatch)
    try:
        started = start(core, scope)
        assert entered.wait(3)
        extra = {
            "session.delete": {"session_id": scope["session_id"]},
            "source.delete": {"document_id": scope["document_id"]},
            "project.delete": {},
        }[method]
        failure = call(core, method, {"project_id": scope["project_id"]} | extra, ok=False)
        if method == "source.delete":
            assert failure["code"] == "SOURCE_DELETE_FAILED" and failure["retryable"]
            assert failure["details"]["cause_code"] == "REHEARSAL_ANALYSIS_CLEANUP_PENDING"
        else:
            assert failure["code"] == "REHEARSAL_ANALYSIS_CLEANUP_PENDING"
        assert counts(core, scope) == (0, 0, 0)
        assert started["job_id"] in core._rehearsal_analysis_jobs._jobs
        release.set()
        assert terminal(core, scope, started)["state"] == "cancelled"
        call(core, method, {"project_id": scope["project_id"]} | extra)
        assert started["job_id"] not in core._rehearsal_analysis_jobs._jobs
    finally:
        release.set()


def test_mixed_kinds_share_global_capacity_and_queued_cancellation(rehearsal, monkeypatch):
    from presenter_core.presentation.rehearsal_analysis_jobs import RehearsalAnalysisJobs

    core, scope = rehearsal
    provider = ObjectionProvider()
    monkeypatch.setattr(core._providers, "_injected_provider", provider)
    entered, release = threading.Event(), threading.Event()
    run = RehearsalAnalysisJobs._run

    def held(self, job):
        entered.set()
        assert release.wait(5)
        run(self, job)

    monkeypatch.setattr(RehearsalAnalysisJobs, "_run", held)
    started = []
    try:
        for kind in ("objections", "coverage", "objections", "coverage"):
            started.append(
                start(core, scope)
                if kind == "objections"
                else call(core, PREFIX + "start_rehearsal_analysis", coverage_params(core, scope))
            )
        assert entered.wait(3)
        assert (
            call(
                core, PREFIX + "start_rehearsal_objections_analysis", params(core, scope), ok=False
            )["code"]
            == "REHEARSAL_ANALYSIS_BUSY"
        )
        assert (
            call(core, PREFIX + "start_rehearsal_analysis", coverage_params(core, scope), ok=False)[
                "code"
            ]
            == "REHEARSAL_ANALYSIS_BUSY"
        )
        for job in started:
            assert call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, job))[
                "cancellation_accepted"
            ]
        release.set()
        for job in started:
            assert terminal(core, scope, job)["state"] == "cancelled"
        assert provider.call_count == 0 and counts(core, scope) == (0, 0, 0)
    finally:
        release.set()


@pytest.mark.parametrize("cleanup", ["close", "models"])
def test_objection_worker_blocks_core_and_model_release_until_terminal(
    rehearsal, monkeypatch, cleanup
):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", ObjectionProvider())
    core._rehearsal_analysis_jobs._join_timeout = 0.01
    entered, release = hold_before_storage(monkeypatch)
    try:
        started = start(core, scope)
        assert entered.wait(3)
        if cleanup == "close":
            assert core.close() is False and not core._closed
            assert core._last_close_error.code == "REHEARSAL_ANALYSIS_CLEANUP_PENDING"
        else:
            from presenter_core.errors import CoreDomainError

            with pytest.raises(CoreDomainError) as error:
                core._stop_active_for_model_change()
            assert error.value.code == "REHEARSAL_ANALYSIS_CLEANUP_PENDING"
        assert counts(core, scope) == (0, 0, 0)
        release.set()
        assert terminal(core, scope, started)["state"] == "cancelled"
        if cleanup == "close":
            assert core.close() is True
        else:
            core._stop_active_for_model_change()
    finally:
        release.set()


def test_invalid_objection_fingerprint_does_not_allocate_or_invoke(rehearsal, monkeypatch):
    core, scope = rehearsal
    provider = ObjectionProvider()
    monkeypatch.setattr(core._providers, "_injected_provider", provider)
    request = params(core, scope)
    for field in ("expected_context_sha256", "expected_recording_sha256"):
        failure = call(
            core,
            PREFIX + "start_rehearsal_objections_analysis",
            request | {field: "0" * 64},
            ok=False,
        )
        assert failure["code"] == "REHEARSAL_CONTEXT_CHANGED"
    assert not core._rehearsal_analysis_jobs._jobs and provider.call_count == 0


def test_paged_empty_history_survives_queue_eviction_and_recording_change(rehearsal, monkeypatch):
    import presenter_core.presentation.rehearsal_analysis_jobs as jobs

    core, scope = rehearsal
    monkeypatch.setattr(jobs, "MAX_RETAINED_JOBS", 2)
    monkeypatch.setattr(core._providers, "_injected_provider", ObjectionProvider(empty=True))
    results = []
    started_jobs = []
    for _ in range(3):
        started = start(core, scope)
        started_jobs.append(started)
        results.append(terminal(core, scope, started)["result"]["analysis_id"])
    assert len(core._rehearsal_analysis_jobs._jobs) == 2 and counts(core, scope) == (3, 0, 0)
    call(core, PREFIX + "poll_rehearsal_analysis", owner(scope, started_jobs[0]), ok=False)
    append(core, scope, "A later recording addition invalidates adoption.")
    history = []
    for offset in range(3):
        page = call(
            core,
            PREFIX + "list_rehearsal_objections_analyses",
            scope | {"offset": offset, "limit": 1},
        )
        assert page["total"] == 3 and page["has_more"] == (offset < 2)
        assert len(page["analyses"]) == 1
        item = page["analyses"][0]
        assert item["candidate_count"] == 0 and item["requires_verified_detail"]
        assert item["disposition_counts"] == {"unreviewed": 0, "rejected": 0, "applied": 0}
        assert "can_adopt" not in item and "recorded_speech" not in json.dumps(item)
        history.append(item["analysis_id"])
    assert set(history) == set(results)
    selected = {k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")}
    detail = call(
        core, PREFIX + "get_rehearsal_objections_analysis", selected | {"analysis_id": results[0]}
    )
    assert not detail["context_current"] and not detail["findings"]


@pytest.mark.parametrize("field", ["project_id", "document_id", "expected_revision_id", "job_id"])
def test_objection_poll_and_cancel_reject_foreign_owner(rehearsal, monkeypatch, field):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", ObjectionProvider())
    started = start(core, scope)
    terminal(core, scope, started)
    foreign = owner(scope, started) | {field: str(uuid.uuid4())}
    call(core, PREFIX + "poll_rehearsal_analysis", foreign, ok=False)
    call(core, PREFIX + "cancel_rehearsal_analysis", foreign, ok=False)


@pytest.mark.parametrize(
    "extra", [{"limit": 21}, {"offset": -1}, {"session_id": str(uuid.uuid4())}]
)
def test_objection_history_rejects_invalid_page_or_foreign_run(rehearsal, extra):
    core, scope = rehearsal
    call(core, PREFIX + "list_rehearsal_objections_analyses", scope | extra, ok=False)


def test_confirmed_reset_waits_for_objection_worker_before_touching_resources(
    rehearsal, monkeypatch
):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", ObjectionProvider())
    monkeypatch.setattr(core._providers, "prepare_reset_credential_cleanup", lambda: {})
    core._rehearsal_analysis_jobs._join_timeout = 0.01
    entered, release = hold_before_storage(monkeypatch)
    removed = []
    monkeypatch.setattr(core._storage, "reset_local_data", lambda **kwargs: removed.append(kwargs))
    try:
        started = start(core, scope)
        assert entered.wait(3)
        failure = call(core, "app.reset_local_data", {"confirm": True}, ok=False)
        assert failure["code"] == "REHEARSAL_ANALYSIS_CLEANUP_PENDING"
        assert not removed and counts(core, scope) == (0, 0, 0)
        assert started["job_id"] in core._rehearsal_analysis_jobs._jobs
        release.set()
        assert terminal(core, scope, started)["state"] == "cancelled"
    finally:
        release.set()
