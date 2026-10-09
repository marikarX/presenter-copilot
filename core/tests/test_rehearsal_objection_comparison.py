"""Cross-Run comparisons reference original candidates and own both Run lifetimes."""

import json
import threading
import uuid

import pytest
import test_rehearsal_coverage as coverage_tests
from test_presentation_planning import call
from test_rehearsal_analysis_jobs import owner, terminal
from test_rehearsal_objection_context import append
from test_rehearsal_objection_store import ObjectionProvider, params

from presenter_core.presentation.rehearsal_objection_comparison import (
    RehearsalObjectionComparison,
)
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.providers.models import ReasoningResult
from presenter_core.providers.rehearsal_objection_equivalence_schema import TASK_TYPE

rehearsal = coverage_tests.rehearsal
PREFIX = "presentation.workspace."
TABLES = (
    "presentation_rehearsal_objection_comparisons",
    "presentation_rehearsal_objection_comparison_candidates",
    "presentation_rehearsal_reviews",
)


class CompareProvider(ObjectionProvider):
    """Detection fixture plus a comparison fixture that marks the first pair equivalent."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.comparison_requests = []

    def generate(self, invocation):
        if invocation.request.task_type != TASK_TYPE:
            return super().generate(invocation)
        self.comparison_requests.append(invocation.request)
        result = DeterministicFakeReasoningProvider.generate(self, invocation)
        output = json.loads(json.dumps(result.output))
        output["comparisons"][0]["relationship"] = "equivalent"
        output["comparisons"][0]["reason"] = "Fixture: both ask who approves the pilot."
        return ReasoningResult(output=output, latency_ms=result.latency_ms)


def second_run(core, scope, text="Who signs off on the pilot budget?"):
    session = call(
        core,
        "session.start",
        {
            "project_id": scope["project_id"],
            "mode": "run",
            "current_slide_start": 1,
            "expected_presentation_revision_id": scope["expected_revision_id"],
        },
    )["session"]["id"]
    other = {**scope, "session_id": session}
    append(core, other, text, actor="user", start=500)
    call(core, "session.stop", {"project_id": scope["project_id"], "session_id": session})
    return other


def detect(core, scope):
    started = call(core, PREFIX + "start_rehearsal_objections_analysis", params(core, scope))
    result = terminal(core, scope, started)
    assert result["state"] == "completed", result
    return result["result"]["finding_ids"]


def selection(scope, left, right):
    return {k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")} | {
        "left_finding_ids": left,
        "right_finding_ids": right,
    }


def counts(core, scope):
    with core._storage.project_database(scope["project_id"]) as db:
        return tuple(db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES)


@pytest.fixture
def two_runs(rehearsal, monkeypatch):
    core, scope = rehearsal
    provider = CompareProvider(multi=True)
    append(core, scope, "Who approves the pilot?", actor="unknown_audience")
    monkeypatch.setattr(core._providers, "_injected_provider", provider)
    other = second_run(core, scope)
    append(core, other, "What does the rollout cost?", actor="unknown_audience", start=900)
    left, right = detect(core, scope), detect(core, other)
    assert len(left) == 2 and len(right) == 2
    return core, scope, other, left, right, provider


def start(core, scope, left, right):
    prepared = call(
        core, PREFIX + "prepare_rehearsal_objection_comparison", selection(scope, left, right)
    )
    return prepared, call(
        core,
        PREFIX + "start_rehearsal_objection_comparison",
        selection(scope, left, right) | {"expected_context_sha256": prepared["context_sha256"]},
    )


def test_actual_ipc_compares_distinct_runs_without_merging_review_authority(two_runs):
    core, scope, other, left, right, provider = two_runs
    prepared, started = start(core, scope, left, right)
    assert prepared["session_id"] == scope["session_id"]
    assert prepared["right_session_id"] == other["session_id"]
    assert not prepared["speaker_identity_verified"] and prepared["requires_user_review"]
    assert started["analysis_kind"] == "comparison"
    assert started["right_session_id"] == other["session_id"]
    finished = terminal(core, scope, started)
    assert finished["state"] == "completed" and set(finished["result"]) == {"comparison_id"}
    comparison = finished["result"]["comparison_id"]

    request = provider.comparison_requests[-1]
    summary = json.loads(request.current_slide_summary)
    assert [c["finding_id"] for c in summary["left"]["candidates"]] == left
    assert [c["finding_id"] for c in summary["right"]["candidates"]] == right
    assert "private notes excluded" not in request.current_slide_summary
    assert set(request.rehearsal_session_ids) == {scope["session_id"], other["session_id"]}

    scoped = {k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")}
    listed = call(core, PREFIX + "list_rehearsal_objection_comparisons", scoped)
    assert listed["total"] == 1
    item = listed["comparisons"][0]
    assert item["comparison_id"] == comparison
    assert item["relationship_counts"] == {
        "equivalent": 1,
        "related": 0,
        "distinct": 0,
        "unclear": 3,
    }
    for session in (scope["session_id"], other["session_id"]):
        assert (
            call(
                core,
                PREFIX + "list_rehearsal_objection_comparisons",
                scoped | {"session_id": session},
            )["total"]
            == 1
        )

    detail = call(
        core, PREFIX + "get_rehearsal_objection_comparison", scoped | {"comparison_id": comparison}
    )
    assert detail["context_current"] and detail["requires_user_review"]
    assert not detail["interpretation_verified"] and not detail["establishes_absence"]
    assert detail["left_finding_ids"] == left and detail["right_finding_ids"] == right
    assert len(detail["comparisons"]) == 4
    first = detail["comparisons"][0]
    assert (first["left_finding_id"], first["right_finding_id"]) == (left[0], right[0])
    assert first["relationship"] == "equivalent"
    assert all(c["disposition"] == "unreviewed" for c in detail["candidates"].values())
    assert all(c["can_adopt"] for c in detail["candidates"].values())
    assert {c["side"] for c in detail["candidates"].values()} == {"left", "right"}
    assert counts(core, scope) == (1, 4, 0)


def test_dispositions_remain_independent_of_the_comparison(two_runs):
    core, scope, other, left, right, _ = two_runs
    _, started = start(core, scope, left, right)
    comparison = terminal(core, scope, started)["result"]["comparison_id"]
    scoped = {k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")}
    call(core, PREFIX + "reject_rehearsal_finding", scoped | {"finding_id": left[0]})
    detail = call(
        core, PREFIX + "get_rehearsal_objection_comparison", scoped | {"comparison_id": comparison}
    )
    assert detail["candidates"][left[0]]["disposition"] == "rejected"
    assert not detail["candidates"][left[0]]["can_adopt"]
    # The equivalent counterpart keeps its own, unchanged disposition.
    assert detail["candidates"][right[0]]["disposition"] == "unreviewed"
    assert detail["candidates"][right[0]]["can_adopt"]
    assert counts(core, scope) == (1, 4, 1)


@pytest.mark.parametrize(
    "case", ["same_run", "overlap", "too_many", "empty", "foreign", "stale_fingerprint"]
)
def test_invalid_or_stale_selections_are_rejected_before_jobs(two_runs, case):
    core, scope, other, left, right, _ = two_runs
    chosen = {
        "same_run": (left[:1], left[1:]),
        "overlap": (left, [left[0]]),
        "too_many": (left + right, right),
        "empty": ([], right),
        "foreign": (left, ["f" * 64]),
        "stale_fingerprint": (left, right),
    }[case]
    values = selection(scope, *chosen)
    if case == "stale_fingerprint":
        values["expected_context_sha256"] = "0" * 64
        failure = call(core, PREFIX + "start_rehearsal_objection_comparison", values, ok=False)
        assert failure["code"] == "REHEARSAL_CONTEXT_CHANGED"
    else:
        call(core, PREFIX + "prepare_rehearsal_objection_comparison", values, ok=False)
    assert not any(
        job.analysis_kind == "comparison" for job in core._rehearsal_analysis_jobs._jobs.values()
    )
    assert counts(core, scope) == (0, 0, 0)


def test_changed_recording_blocks_start_and_marks_saved_comparison_historical(two_runs):
    core, scope, other, left, right, _ = two_runs
    prepared = call(
        core, PREFIX + "prepare_rehearsal_objection_comparison", selection(scope, left, right)
    )
    added = append(core, other, "A late appended utterance.", start=5000)
    failure = call(
        core,
        PREFIX + "start_rehearsal_objection_comparison",
        selection(scope, left, right) | {"expected_context_sha256": prepared["context_sha256"]},
        ok=False,
    )
    assert failure["code"] == "REHEARSAL_CONTEXT_CHANGED"
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute("DELETE FROM utterances WHERE id=?", (added,))
        db.commit()
    _, started = start(core, scope, left, right)
    comparison = terminal(core, scope, started)["result"]["comparison_id"]
    append(core, other, "Another late utterance.", start=6000)
    scoped = {k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")}
    detail = call(
        core, PREFIX + "get_rehearsal_objection_comparison", scoped | {"comparison_id": comparison}
    )
    assert not detail["context_current"]
    assert detail["candidates"][left[0]]["context_current"]
    assert not detail["candidates"][right[0]]["context_current"]
    assert not detail["candidates"][right[0]]["can_adopt"]
    assert detail["right_finding_ids"] == right  # original identities are retained


@pytest.mark.parametrize("side", ["left", "right"])
def test_deleting_either_run_waits_for_worker_then_cascades(two_runs, monkeypatch, side):
    core, scope, other, left, right, _ = two_runs
    core._rehearsal_analysis_jobs._join_timeout = 0.01
    entered, release = threading.Event(), threading.Event()
    save = RehearsalObjectionComparison.save

    def held(self, *args, **kwargs):
        entered.set()
        assert release.wait(5)
        return save(self, *args, **kwargs)

    monkeypatch.setattr(RehearsalObjectionComparison, "save", held)
    session = scope["session_id"] if side == "left" else other["session_id"]
    try:
        _, started = start(core, scope, left, right)
        assert entered.wait(3)
        failure = call(
            core,
            "session.delete",
            {"project_id": scope["project_id"], "session_id": session},
            ok=False,
        )
        assert failure["code"] == "REHEARSAL_ANALYSIS_CLEANUP_PENDING"
        release.set()
        assert terminal(core, scope, started)["state"] == "cancelled"
        assert counts(core, scope) == (0, 0, 0)
    finally:
        release.set()
    monkeypatch.setattr(RehearsalObjectionComparison, "save", save)
    _, started = start(core, scope, left, right)
    assert terminal(core, scope, started)["state"] == "completed"
    assert counts(core, scope) == (1, 4, 0)
    call(core, "session.delete", {"project_id": scope["project_id"], "session_id": session})
    assert counts(core, scope)[:2] == (0, 0)
    remaining = other if side == "left" else scope
    with core._storage.project_database(scope["project_id"]) as db:
        kept = db.execute(
            "SELECT COUNT(*) FROM presentation_rehearsal_objection_analyses WHERE session_id=?",
            (remaining["session_id"],),
        ).fetchone()[0]
    assert kept == 1  # the other Run's original analysis is untouched


def test_cancel_before_storage_persists_nothing(two_runs, monkeypatch):
    core, scope, other, left, right, _ = two_runs
    entered, release = threading.Event(), threading.Event()
    save = RehearsalObjectionComparison.save

    def held(self, *args, **kwargs):
        entered.set()
        assert release.wait(5)
        return save(self, *args, **kwargs)

    monkeypatch.setattr(RehearsalObjectionComparison, "save", held)
    try:
        _, started = start(core, scope, left, right)
        assert entered.wait(3)
        reply = call(core, PREFIX + "cancel_rehearsal_analysis", owner(scope, started))
        assert reply["cancellation_accepted"]
        release.set()
        assert terminal(core, scope, started)["state"] == "cancelled"
        assert counts(core, scope) == (0, 0, 0)
    finally:
        release.set()


def test_tampered_snapshot_is_reported_corrupt(two_runs):
    core, scope, other, left, right, _ = two_runs
    _, started = start(core, scope, left, right)
    comparison = terminal(core, scope, started)["result"]["comparison_id"]
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute(
            "UPDATE presentation_rehearsal_objection_comparisons SET snapshot_sha256=? "
            "WHERE provider_run_id=?",
            ("0" * 64, comparison),
        )
        db.commit()
    scoped = {k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")}
    failure = call(
        core,
        PREFIX + "get_rehearsal_objection_comparison",
        scoped | {"comparison_id": comparison},
        ok=False,
    )
    assert failure["code"] == "REHEARSAL_OBJECTION_COMPARISON_CORRUPT"
    call(
        core,
        PREFIX + "get_rehearsal_objection_comparison",
        scoped | {"comparison_id": str(uuid.uuid4())},
        ok=False,
    )
