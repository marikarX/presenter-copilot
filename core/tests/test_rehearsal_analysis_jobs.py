"""Actual IPC jobs, cancellation races and resource deletion barriers."""

import json
import threading
import uuid

import pytest
import test_rehearsal_coverage as coverage_tests
from test_presentation_planning import call
from test_rehearsal_semantic_analysis import CoverageProvider, params

from presenter_core.presentation.rehearsal_analysis_store import RehearsalAnalysisStore

rehearsal = coverage_tests.rehearsal
PREFIX = "presentation.workspace."


def owner(scope, started):
    return {key: scope[key] for key in ("project_id", "document_id", "expected_revision_id")} | {
        "job_id": started["job_id"]
    }


def terminal(core, scope, started):
    job = core._rehearsal_analysis_jobs._jobs[started["job_id"]]
    job.worker.join(4)
    result = call(core, PREFIX + "poll_rehearsal_analysis", owner(scope, started))
    assert result["terminal"], result
    return result


def counts(core, scope):
    with core._storage.project_database(scope["project_id"]) as db:
        return tuple(
            db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("presentation_rehearsal_analyses", "presentation_rehearsal_reviews")
        )


class HeldProvider(CoverageProvider):
    def __init__(self):
        self.entered, self.release, self.cancelled = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        super().__init__(action=self.hold)

    def hold(self):
        self.entered.set()
        assert self.release.wait(5)

    def cancel(self, invocation):
        self.cancelled.set()
        self.release.set()


def test_actual_ipc_completed_job_has_ids_only_and_late_cancel_is_not_accepted(
    rehearsal, monkeypatch
):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", CoverageProvider())
    started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
    result = terminal(core, scope, started)
    assert result["state"] == "completed" and set(result["result"]) == {"analysis_id", "finding_id"}
    assert "recorded_speech" not in json.dumps(result)
    detail = call(
        core,
        PREFIX + "get_rehearsal_analysis",
        {key: scope[key] for key in ("project_id", "document_id", "expected_revision_id")}
        | {"finding_id": result["result"]["finding_id"]},
    )
    assert detail["can_adopt"] and detail["snapshot"]["hint"]["status"] == "partially_addressed"
    assert counts(core, scope) == (1, 0)
    assert not call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, started))[
        "cancellation_accepted"
    ]


def test_cancel_held_provider_finishes_audit_without_result(rehearsal, monkeypatch):
    core, scope = rehearsal
    provider = HeldProvider()
    monkeypatch.setattr(core._providers, "_injected_provider", provider)
    try:
        started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
        assert provider.entered.wait(3)
        reply = call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, started))
        assert reply["cancellation_accepted"] and reply["cancellation_requested"]
        result = terminal(core, scope, started)
        assert result["state"] == "cancelled" and result["result"] is None
        assert provider.cancelled.is_set() and counts(core, scope) == (0, 0)
        with core._storage.project_database(scope["project_id"]) as db:
            assert db.execute("SELECT status FROM provider_runs").fetchone()[0] == "cancelled"
    finally:
        provider.release.set()


def hold_before_storage(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    save = RehearsalAnalysisStore.save

    def held(self, *args, **kwargs):
        entered.set()
        assert release.wait(5)
        return save(self, *args, **kwargs)

    monkeypatch.setattr(RehearsalAnalysisStore, "save", held)
    return entered, release


def test_cancel_after_inference_before_commit_prevents_persistence(rehearsal, monkeypatch):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", CoverageProvider())
    entered, release = hold_before_storage(monkeypatch)
    try:
        started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
        assert entered.wait(3)
        assert call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, started))[
            "cancellation_accepted"
        ]
        release.set()
        assert terminal(core, scope, started)["state"] == "cancelled"
        assert counts(core, scope) == (0, 0)
        with core._storage.project_database(scope["project_id"]) as db:
            assert db.execute("SELECT status FROM provider_runs").fetchone()[0] == "success"
    finally:
        release.set()


def test_cancel_inside_commit_reports_too_late_and_saved_result_remains(rehearsal, monkeypatch):
    import presenter_core.presentation.rehearsal_analysis_store as store

    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", CoverageProvider())
    entered, release = threading.Event(), threading.Event()
    original = store.snapshot_digest

    def held(path):
        entered.set()
        assert release.wait(5)
        return original(path)

    monkeypatch.setattr(store, "snapshot_digest", held)
    try:
        started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
        assert entered.wait(3)
        reply = call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, started))
        assert reply["state"] == "committing" and not reply["cancellation_accepted"]
        assert not reply["cancellation_requested"] and not reply["terminal"]
        release.set()
        assert terminal(core, scope, started)["state"] == "completed"
        assert counts(core, scope) == (1, 0)
    finally:
        release.set()


@pytest.mark.parametrize(
    "field", ["project_id", "document_id", "expected_revision_id", "job_id", "caller_speech"]
)
def test_poll_and_cancel_reject_foreign_or_extra_scope(rehearsal, monkeypatch, field):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", CoverageProvider())
    started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
    terminal(core, scope, started)
    wrong = owner(scope, started) | {field: str(uuid.uuid4())}
    call(core, PREFIX + "poll_rehearsal_analysis", wrong, ok=False)
    call(core, PREFIX + "cancel_rehearsal_analysis", wrong, ok=False)


def test_stale_native_head_does_not_prevent_cancellation(rehearsal, monkeypatch):
    core, scope = rehearsal
    provider = HeldProvider()
    monkeypatch.setattr(core._providers, "_injected_provider", provider)
    try:
        started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
        assert provider.entered.wait(3)
        slides = call(core, PREFIX + "rehearsal_coverage", scope)["slides"]
        call(
            core,
            PREFIX + "reorder_slides",
            {key: scope[key] for key in ("project_id", "document_id", "expected_revision_id")}
            | {"ordered_slide_ids": [slide["slide_id"] for slide in slides][::-1]},
        )
        assert call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, started))[
            "cancellation_accepted"
        ]
        assert terminal(core, scope, started)["state"] == "cancelled"
        assert counts(core, scope) == (0, 0)
    finally:
        provider.release.set()


@pytest.mark.parametrize("method", ["session.delete", "source.delete", "project.delete"])
def test_deletion_cancels_owned_job_on_ended_run_before_resource_removal(
    rehearsal, monkeypatch, method
):
    core, scope = rehearsal
    provider = HeldProvider()
    monkeypatch.setattr(core._providers, "_injected_provider", provider)
    try:
        started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
        assert provider.entered.wait(3)
        extra = {
            "session.delete": {"session_id": scope["session_id"]},
            "source.delete": {"document_id": scope["document_id"]},
            "project.delete": {},
        }[method]
        job = core._rehearsal_analysis_jobs._jobs[started["job_id"]]
        call(core, method, {"project_id": scope["project_id"]} | extra)
        assert (
            not job.worker.is_alive() and job.state == "cancelled" and provider.cancelled.is_set()
        )
        assert started["job_id"] not in core._rehearsal_analysis_jobs._jobs
    finally:
        provider.release.set()


def test_cleanup_timeout_keeps_core_resources_open_until_worker_is_terminal(rehearsal, monkeypatch):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", CoverageProvider())
    core._rehearsal_analysis_jobs._join_timeout = 0.01
    entered, release = hold_before_storage(monkeypatch)
    try:
        started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
        assert entered.wait(3)
        assert core.close() is False and not core._closed
        assert core._last_close_error.code == "REHEARSAL_ANALYSIS_CLEANUP_PENDING"
        assert counts(core, scope) == (0, 0)
        release.set()
        assert terminal(core, scope, started)["state"] == "cancelled"
        assert core.close() is True
    finally:
        release.set()


def test_start_invalid_context_does_not_allocate_or_invoke(rehearsal, monkeypatch):
    core, scope = rehearsal
    provider = CoverageProvider()
    monkeypatch.setattr(core._providers, "_injected_provider", provider)
    call(
        core,
        PREFIX + "start_rehearsal_analysis",
        params(core, scope) | {"expected_context_sha256": "0" * 64},
        ok=False,
    )
    assert not core._rehearsal_analysis_jobs._jobs and provider.call_count == 0


def test_cancel_queued_worker_never_invokes_provider(rehearsal, monkeypatch):
    from presenter_core.presentation.rehearsal_analysis_jobs import RehearsalAnalysisJobs

    core, scope = rehearsal
    provider = CoverageProvider()
    monkeypatch.setattr(core._providers, "_injected_provider", provider)
    entered, release = threading.Event(), threading.Event()
    run = RehearsalAnalysisJobs._run

    def held(self, job):
        entered.set()
        assert release.wait(5)
        run(self, job)

    monkeypatch.setattr(RehearsalAnalysisJobs, "_run", held)
    try:
        started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
        assert entered.wait(3)
        assert call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, started))[
            "cancellation_accepted"
        ]
        release.set()
        assert terminal(core, scope, started)["state"] == "cancelled"
        assert provider.call_count == 0 and counts(core, scope) == (0, 0)
    finally:
        release.set()


def test_cancel_between_domain_check_and_committing_state_wins(rehearsal, monkeypatch):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", CoverageProvider())
    entered, release = threading.Event(), threading.Event()
    analysis = core._rehearsal_analysis_jobs._analysis
    analyze = analysis.analyze

    def delayed(*args, before_persist, **kwargs):
        def held():
            entered.set()
            assert release.wait(5)
            before_persist()

        return analyze(*args, before_persist=held, **kwargs)

    monkeypatch.setattr(analysis, "analyze", delayed)
    try:
        started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
        assert entered.wait(3)
        assert call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, started))[
            "cancellation_accepted"
        ]
        release.set()
        assert terminal(core, scope, started)["state"] == "cancelled"
        assert counts(core, scope) == (0, 0)
    finally:
        release.set()


def test_capacity_rejects_fifth_live_job_and_retention_keeps_durable_history(
    rehearsal, monkeypatch
):
    import presenter_core.presentation.rehearsal_analysis_jobs as jobs

    core, scope = rehearsal
    provider = HeldProvider()
    monkeypatch.setattr(core._providers, "_injected_provider", provider)
    request = params(core, scope)
    started = []
    try:
        for _ in range(4):
            started.append(call(core, PREFIX + "start_rehearsal_analysis", request))
        assert (
            call(core, PREFIX + "start_rehearsal_analysis", request, ok=False)["code"]
            == "REHEARSAL_ANALYSIS_BUSY"
        )
        for job in started:
            call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, job))
        provider.release.set()
        for job in started:
            assert terminal(core, scope, job)["state"] == "cancelled"
        assert counts(core, scope) == (0, 0)
    finally:
        provider.release.set()
    monkeypatch.setattr(jobs, "MAX_RETAINED_JOBS", 2)
    monkeypatch.setattr(core._providers, "_injected_provider", CoverageProvider())
    completed = []
    for _ in range(3):
        job = call(core, PREFIX + "start_rehearsal_analysis", request)
        completed.append((job, terminal(core, scope, job)))
    assert len(core._rehearsal_analysis_jobs._jobs) == 2
    call(core, PREFIX + "poll_rehearsal_analysis", owner(scope, completed[0][0]), ok=False)
    assert counts(core, scope) == (3, 0)
    history = call(core, PREFIX + "list_rehearsal_analyses", scope)
    assert {item["finding_id"] for item in history["analyses"]} == {
        item[1]["result"]["finding_id"] for item in completed
    }


def test_core_close_cancels_and_joins_active_job(rehearsal, monkeypatch):
    core, scope = rehearsal
    provider = HeldProvider()
    monkeypatch.setattr(core._providers, "_injected_provider", provider)
    try:
        started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
        assert provider.entered.wait(3)
        job = core._rehearsal_analysis_jobs._jobs[started["job_id"]]
        assert core.close() is True
        assert not job.worker.is_alive() and job.state == "cancelled"
        assert provider.cancelled.is_set()
        assert not core._rehearsal_analysis_jobs._jobs
    finally:
        provider.release.set()


@pytest.mark.parametrize("method", ["session.delete", "source.delete", "project.delete"])
def test_cleanup_timeout_prevents_deletion_and_keeps_job_owner(rehearsal, monkeypatch, method):
    core, scope = rehearsal
    monkeypatch.setattr(core._providers, "_injected_provider", CoverageProvider())
    core._rehearsal_analysis_jobs._join_timeout = 0.01
    entered, release = hold_before_storage(monkeypatch)
    try:
        started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
        assert entered.wait(3)
        extra = {
            "session.delete": {"session_id": scope["session_id"]},
            "source.delete": {"document_id": scope["document_id"]},
            "project.delete": {},
        }[method]
        call(core, method, {"project_id": scope["project_id"]} | extra, ok=False)
        assert started["job_id"] in core._rehearsal_analysis_jobs._jobs
        assert counts(core, scope) == (0, 0)
        with core._storage.project_database(scope["project_id"]) as db:
            assert db.execute(
                "SELECT id FROM sessions WHERE id=?", (scope["session_id"],)
            ).fetchone()
            assert db.execute(
                "SELECT id FROM documents WHERE id=?", (scope["document_id"],)
            ).fetchone()
        release.set()
        assert terminal(core, scope, started)["state"] == "cancelled"
    finally:
        release.set()


def test_model_cleanup_cancels_job_before_releasing_models(rehearsal, monkeypatch):
    core, scope = rehearsal
    provider = HeldProvider()
    monkeypatch.setattr(core._providers, "_injected_provider", provider)
    try:
        started = call(core, PREFIX + "start_rehearsal_analysis", params(core, scope))
        assert provider.entered.wait(3)
        core._stop_active_for_model_change()
        assert terminal(core, scope, started)["state"] == "cancelled"
        assert counts(core, scope) == (0, 0)
    finally:
        provider.release.set()
