"""Bounded owned jobs with truthful cancellation and a linearized persistence boundary."""

import re
import threading
import uuid
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Literal

from presenter_core.errors import CoreDomainError, reject_unknown_fields
from presenter_core.presentation.rehearsal_objection_analysis import RehearsalObjectionAnalysis
from presenter_core.presentation.rehearsal_objection_comparison import (
    RehearsalObjectionComparison,
)
from presenter_core.presentation.rehearsal_semantic_analysis import RehearsalSemanticAnalysis
from presenter_core.providers.models import ProviderError

MAX_ACTIVE_JOBS = 4
MAX_RETAINED_JOBS = 32
TERMINAL = {"completed", "cancelled", "failed"}
Kind = Literal["coverage", "objections", "comparison"]
RESULT_FIELDS: dict[str, tuple[str, ...]] = {
    "coverage": ("analysis_id", "finding_id"),
    "objections": ("analysis_id", "finding_ids"),
    "comparison": ("comparison_id",),
}


@dataclass
class _Job:
    identity: str
    params: dict[str, Any]
    analysis_kind: Kind = "coverage"
    state: str = "queued"
    cancellation: threading.Event = field(default_factory=threading.Event)
    worker: threading.Thread | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class RehearsalAnalysisJobs:
    def __init__(
        self,
        analysis: RehearsalSemanticAnalysis,
        *,
        objections: RehearsalObjectionAnalysis | None = None,
        comparisons: RehearsalObjectionComparison | None = None,
        join_timeout: float = 2.0,
    ) -> None:
        self._analysis = analysis
        self._objections = objections
        self._comparisons = comparisons
        self._lock = threading.Lock()
        self._jobs: dict[str, _Job] = {}
        self._accepting = True
        self._join_timeout = join_timeout

    @staticmethod
    def _live(job: _Job) -> bool:
        return bool(job.worker and job.worker.is_alive())

    def _snapshot(self, job: _Job) -> dict[str, Any]:
        live = self._live(job)
        return {
            "job_id": job.identity,
            "analysis_kind": job.analysis_kind,
            **{
                key: job.params[key]
                for key in ("project_id", "document_id", "expected_revision_id", "session_id")
            },
            **(
                {"right_session_id": job.params["right_session_id"]}
                if job.analysis_kind == "comparison"
                else {}
            ),
            "state": "finishing" if live and job.state in TERMINAL else job.state,
            "terminal": not live and job.state in TERMINAL,
            "cancellation_requested": job.cancellation.is_set(),
            "can_cancel": live and job.state in {"queued", "running", "cancelling"},
            "result": job.result if not live else None,
            "error": job.error if not live else None,
        }

    def start_objections(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._start(params, analysis_kind="objections")

    def start_comparison(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._start(params, analysis_kind="comparison")

    def start(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._start(params, analysis_kind="coverage")

    def _start(self, params: dict[str, Any], *, analysis_kind: Kind) -> dict[str, Any]:
        # All kinds share live capacity, retention, cancellation and resource barriers.
        analysis = self._service(analysis_kind)
        # Read-only preparation rejects foreign/stale/invalid input before allocating.
        _, prepared, _ = analysis.prepare_analysis(params)
        canonical = {
            **params,
            "project_id": analysis._semantics._project_id(params.get("project_id")),
            "document_id": prepared["document_id"],
            "expected_revision_id": prepared["revision_id"],
            "session_id": prepared["session_id"],
        }
        if analysis_kind == "comparison":
            # A comparison owns both Runs: deleting either one must wait for it.
            canonical["right_session_id"] = prepared["right_session_id"]
        else:
            canonical["slide_id"] = prepared["slide_id"]
        if analysis_kind == "coverage":
            canonical["object_id"] = prepared["point"]["object_id"]
        with self._lock:
            if not self._accepting:
                raise CoreDomainError("REHEARSAL_ANALYSIS_CLOSED", "Analysis jobs are closing.")
            if sum(self._live(job) for job in self._jobs.values()) >= MAX_ACTIVE_JOBS:
                raise CoreDomainError(
                    "REHEARSAL_ANALYSIS_BUSY",
                    "Wait for an active analysis to finish.",
                    retryable=True,
                )
            while len(self._jobs) >= MAX_RETAINED_JOBS:
                oldest = next(
                    (
                        key
                        for key, job in self._jobs.items()
                        if not self._live(job) and job.state in TERMINAL
                    ),
                    None,
                )
                if oldest is None:
                    raise CoreDomainError(
                        "REHEARSAL_ANALYSIS_BUSY",
                        "Wait for an active analysis to finish.",
                        retryable=True,
                    )
                del self._jobs[oldest]
            job = _Job(str(uuid.uuid4()), canonical, analysis_kind=analysis_kind)
            job.worker = threading.Thread(
                target=self._run, args=(job,), name="rehearsal-analysis", daemon=True
            )
            self._jobs[job.identity] = job
            try:
                job.worker.start()
            except Exception:
                del self._jobs[job.identity]
                raise CoreDomainError(
                    "REHEARSAL_ANALYSIS_START_FAILED", "The analysis worker could not start."
                ) from None
            return self._snapshot(job)

    def _service(
        self, kind: Kind
    ) -> RehearsalSemanticAnalysis | RehearsalObjectionAnalysis | RehearsalObjectionComparison:
        if kind == "coverage":
            return self._analysis
        if kind == "comparison":
            if self._comparisons is None:
                raise CoreDomainError(
                    "REHEARSAL_ANALYSIS_UNAVAILABLE", "Objection comparison is unavailable."
                )
            return self._comparisons
        if self._objections is None:
            raise CoreDomainError(
                "REHEARSAL_ANALYSIS_UNAVAILABLE", "Objection analysis is unavailable."
            )
        return self._objections

    def _owned(self, params: dict[str, Any]) -> _Job:
        fields = {"project_id", "document_id", "expected_revision_id", "job_id"}
        reject_unknown_fields(params, fields)
        semantics = self._analysis._semantics
        project = semantics._project_id(params.get("project_id"))
        document = semantics._uuid_field(params.get("document_id"), "document_id")
        revision = semantics._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
        identity = semantics._uuid_field(params.get("job_id"), "job_id")
        job = self._jobs.get(identity)
        if job is None or (project, document, revision) != tuple(
            job.params[key] for key in ("project_id", "document_id", "expected_revision_id")
        ):
            raise CoreDomainError(
                "REHEARSAL_ANALYSIS_JOB_UNAVAILABLE",
                "This analysis job is unavailable for the selected deck.",
            )
        return job

    def poll(self, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self._snapshot(self._owned(params))

    def cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            job = self._owned(params)
            accepted = self._request_cancel(job)
            return {**self._snapshot(job), "cancellation_accepted": accepted}

    def _request_cancel(self, job: _Job) -> bool:
        if self._live(job) and job.state in {"queued", "running", "cancelling"}:
            job.cancellation.set()
            job.state = "cancelling"
            return True
        return False

    def _run(self, job: _Job) -> None:
        def committing() -> None:
            # Called inside the storage transaction, with no database operations here.
            # Cancel and this state change share a lock: accepted Cancel wins before
            # persistence, otherwise Cancel truthfully reports too late.
            with self._lock:
                if job.cancellation.is_set():
                    raise CoreDomainError(
                        "PROVIDER_CANCELLED", "The analysis was cancelled before storage."
                    )
                job.state = "committing"

        try:
            with self._lock:
                if not job.cancellation.is_set():
                    job.state = "running"
            result = self._service(job.analysis_kind).analyze(
                job.params, cancellation_check=job.cancellation.is_set, before_persist=committing
            )
            with self._lock:
                job.result = {key: result[key] for key in RESULT_FIELDS[job.analysis_kind]}
                job.state = "completed"
        except (CoreDomainError, ProviderError) as error:
            code = (
                error.code
                if re.fullmatch(r"[A-Z0-9_]{1,80}", error.code)
                else "REHEARSAL_ANALYSIS_FAILED"
            )
            with self._lock:
                job.state = "cancelled" if code == "PROVIDER_CANCELLED" else "failed"
                job.error = {
                    "code": code,
                    "message": "The analysis did not produce a saved result.",
                    "retryable": error.retryable,
                }
        except Exception:
            with self._lock:
                job.state = "failed"
                job.error = {
                    "code": "REHEARSAL_ANALYSIS_FAILED",
                    "message": "The analysis did not produce a saved result.",
                    "retryable": False,
                }

    def drain(
        self,
        *,
        project_id: str | None = None,
        document_id: str | None = None,
        session_id: str | None = None,
        closing: bool = False,
        purge: bool = False,
    ) -> None:
        with self._lock:
            if closing:
                self._accepting = False
            jobs = [
                job
                for job in self._jobs.values()
                if all(
                    value is None or job.params[key] == value
                    for key, value in (
                        ("project_id", project_id),
                        ("document_id", document_id),
                    )
                )
                and (
                    session_id is None
                    or session_id in {job.params["session_id"], job.params.get("right_session_id")}
                )
            ]
            for job in jobs:
                self._request_cancel(job)
        deadline = monotonic() + self._join_timeout
        for job in jobs:
            assert job.worker is not None
            if self._live(job):
                job.worker.join(max(0.0, deadline - monotonic()))
        if any(self._live(job) for job in jobs):
            raise CoreDomainError(
                "REHEARSAL_ANALYSIS_CLEANUP_PENDING",
                "An analysis worker is still finishing. "
                "Retry cleanup before removing its resources.",
                retryable=True,
            )
        if purge or closing:
            with self._lock:
                for job in jobs:
                    self._jobs.pop(job.identity, None)
