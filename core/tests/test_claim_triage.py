from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_presentation_claims import setup
from test_presentation_edit_planning import call

from presenter_core.__main__ import _explicit_developer_decision
from presenter_core.decisions.models import ChoiceAnswer, ChoiceDecisionResult
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


class Provider:
    id = "triage_fixture"
    model_id = "triage-fixture-v1"
    locality = "local"
    leaves_machine = False

    def __init__(self, choice="supports", confidence=0.99):
        self.choice, self.confidence = choice, confidence
        self.requests = []
        self.mutate = None

    def decide(self, request):
        self.requests.append(request)
        if self.mutate:
            self.mutate()
        return ChoiceDecisionResult(
            provider_id=self.id,
            model_id=self.model_id,
            latency_ms=5,
            answers={
                "relation": ChoiceAnswer(
                    name="relation", choice=self.choice, confidence=self.confidence
                )
            },
        )

    def close(self):
        pass


def params(scope, target, evidence):
    return {
        **scope,
        "object_id": target["object_id"],
        "quote": target["decision_text"],
        "chunk_id": evidence["chunk_id"],
        "expected_sha256": evidence["sha256"],
    }


@pytest.mark.parametrize(
    "choice,confidence,suggestion",
    [
        ("supports", 0.99, "supports"),
        ("supports", 0.949, "unclear"),
        ("supports", None, "unclear"),
        ("contradicts", 0.9, "contradicts"),
        ("contradicts", 0.899, "unclear"),
        ("context", 0.85, "context"),
        ("context", 0.849, "unclear"),
        ("unclear", 0.99, "unclear"),
    ],
)
def test_relation_thresholds_are_review_only_and_audits_exclude_text(
    tmp_path: Path, choice, confidence, suggestion
) -> None:
    provider = Provider(choice, confidence)
    core = CoreService(
        data_root=tmp_path / "data",
        decision_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        result = call(
            core, "presentation.workspace.triage_claim_evidence", params(scope, target, evidence)
        )
        assert result["suggestion"] == suggestion and result["abstained"] is (
            suggestion == "unclear"
        )
        assert result["requires_user_review"] is True and result["confidence_calibrated"] is False
        state = json.loads(provider.requests[0].serialized_state())
        assert state == {
            "claim_quote": target["decision_text"],
            "source_excerpt": evidence["text"],
            "claim_source_kind": "native_text",
        }
        assert (
            core._presentation_edits._current_revision_source(
                scope["project_id"], scope["document_id"]
            )["revision_id"]
            == scope["revision_id"]
        )
        assert call(core, "presentation.workspace.list_claims", scope)["items"] == []
        with core._storage.project_database(scope["project_id"]) as connection:
            row = connection.execute(
                "SELECT task_type,status,context_manifest_json FROM provider_runs WHERE id = ?",
                (result["provider_run_id"],),
            ).fetchone()
        assert (
            row["status"] == "success" and row["task_type"] == "presentation_claim_evidence_triage"
        )
        manifest = json.loads(row["context_manifest_json"])
        assert (
            evidence["text"] not in row["context_manifest_json"]
            and target["decision_text"] not in row["context_manifest_json"]
        )
        assert manifest["selected_excerpt_sha256"] == evidence["sha256"]
    finally:
        core.close()


@pytest.mark.parametrize(
    "failure",
    [
        "stale_excerpt",
        "bad_quote",
        "foreign_chunk",
        "remote",
        "changed_excerpt",
        "changed_privacy",
        "malformed",
    ],
)
def test_invalid_or_changed_pair_never_promotes_a_relation(tmp_path: Path, failure) -> None:
    provider = Provider("unknown" if failure == "malformed" else "supports")
    if failure in {"remote", "changed_privacy"}:
        provider.leaves_machine, provider.locality = True, "remote"
    core = CoreService(
        data_root=tmp_path / "data",
        decision_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        payload = params(scope, target, evidence)
        if failure == "stale_excerpt":
            payload["expected_sha256"] = "0" * 64
        if failure == "bad_quote":
            payload["quote"] = "invented"
        if failure == "foreign_chunk":
            payload["chunk_id"] = "foreign"
        if failure == "changed_privacy":
            call(
                core,
                "project.update_settings",
                {"project_id": scope["project_id"], "privacy_mode": "selected_context_cloud"},
            )
            call(core, "project.acknowledge_remote_reasoning", {"project_id": scope["project_id"]})
            provider.mutate = lambda: call(
                core,
                "project.update_settings",
                {"project_id": scope["project_id"], "privacy_mode": "local_only"},
            )
        if failure == "changed_excerpt":

            def mutate():
                with core._storage.project_database(scope["project_id"]) as connection:
                    connection.execute(
                        "UPDATE chunks SET text='Changed' WHERE id=?", (evidence["chunk_id"],)
                    )
                    connection.commit()

            provider.mutate = mutate
        error = call(core, "presentation.workspace.triage_claim_evidence", payload, ok=False)
        assert error["code"] in {
            "INVALID_REQUEST",
            "CLAIM_EVIDENCE_CHANGED",
            "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED",
            "PRIVACY_POLICY_CHANGED",
            "DECISION_PROVIDER_MALFORMED_OUTPUT",
        }
        assert len(provider.requests) == (
            1 if failure in {"changed_excerpt", "changed_privacy", "malformed"} else 0
        )
        assert not call(core, "presentation.workspace.list_claims", scope)["items"]
        if provider.requests:
            with core._storage.project_database(scope["project_id"]) as connection:
                assert (
                    connection.execute(
                        "SELECT status FROM provider_runs "
                        "WHERE task_type='presentation_claim_evidence_triage'"
                    ).fetchone()[0]
                    == "error"
                )
    finally:
        core.close()


def test_developer_fixture_requires_both_explicit_flags(monkeypatch):
    monkeypatch.setenv("PRESENTER_COPILOT_TEST_DECISION", "deterministic_fake")
    monkeypatch.delenv("PRESENTER_COPILOT_DEV_MODE", raising=False)
    assert _explicit_developer_decision() is None
    monkeypatch.setenv("PRESENTER_COPILOT_DEV_MODE", "1")
    assert _explicit_developer_decision().id == "fixture_choice"
    monkeypatch.delenv("PRESENTER_COPILOT_TEST_DECISION")
    assert _explicit_developer_decision() is None


@pytest.mark.parametrize("mode", ["correct", "low_confidence", "false_support"])
def test_synthetic_diagnostic_reports_selective_precision_and_costly_errors(mode):
    from presenter_core.tools.claim_triage_acceptance import CASES, evaluate

    class DiagnosticProvider(Provider):
        def decide(self, request):
            index = len(self.requests)
            self.choice = "supports" if mode == "false_support" else CASES[index][1]
            self.confidence = 0.1 if mode == "low_confidence" else 0.99
            return super().decide(request)

    report = evaluate(DiagnosticProvider())
    assert report["status"] == "completed" and report["confidence_calibrated"] is False
    assert report["presentation_content_used"] is False
    if mode == "low_confidence":
        assert report["coverage"] == 0 and report["abstention_rate"] == 1
        assert report["accepted_precision"] is None
    elif mode == "false_support":
        assert report["accepted_false_supports"] == len(CASES) - 4
        assert report["accepted_precision"] == 4 / len(CASES)
    else:
        assert report["raw_accuracy"] == report["accepted_precision"] == 1
        assert report["accepted_false_supports"] == 0
    serialized = json.dumps(report)
    for _, _, quote, excerpt in CASES:
        assert quote not in serialized and excerpt not in serialized
