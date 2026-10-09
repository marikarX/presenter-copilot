"""Real execution guards context/privacy and never adopts or edits analysis hints."""

import json

import pytest
import test_rehearsal_coverage as coverage_tests
from test_presentation_planning import call
from test_rehearsal_semantic_context import prepare, selection

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.rehearsal_semantic_analysis import RehearsalSemanticAnalysis
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.providers.models import ReasoningResult
from presenter_core.providers.service import ProviderService

rehearsal = coverage_tests.rehearsal


class CoverageProvider(DeterministicFakeReasoningProvider):
    def __init__(self, *, locality="local", action=None, invented=False):
        super().__init__(locality=locality)
        self.action, self.invented = action, invented

    def generate(self, invocation):
        result = super().generate(invocation)
        if self.action:
            self.action()
        speech = json.loads(invocation.request.current_slide_summary)["recorded_speech"]
        return ReasoningResult(
            output={
                "status": "partially_addressed",
                "reason": "Review this window only; the hint is unverified.",
                "quotes": [
                    {
                        "utterance_id": speech[0]["utterance_id"],
                        "quote": "invented" if self.invented else speech[0]["text"],
                    }
                ],
            },
            latency_ms=result.latency_ms,
        )


def analysis(core, provider):
    providers = ProviderService(core._storage, provider)
    return RehearsalSemanticAnalysis(
        core._presentation_semantics, providers, ProviderExecutionService(core._storage, providers)
    )


def params(core, scope):
    chosen = selection(core, scope)
    return chosen | {
        "expected_context_sha256": prepare(core, chosen)["context_sha256"],
        "window_index": 0,
    }


def test_execution_manifest_and_no_native_or_knowledge_adoption(rehearsal):
    core, scope = rehearsal
    provider = CoverageProvider()
    result = analysis(core, provider).analyze(params(core, scope))
    assert result["hint"]["status"] == "partially_addressed" and result["requires_user_review"]
    assert result["recording_completeness"] == "unknown"
    with core._storage.project_database(scope["project_id"]) as db:
        row = db.execute(
            "SELECT status,session_id,context_manifest_json FROM provider_runs WHERE id=?",
            (result["provider_run_id"],),
        ).fetchone()
        assert row["status"] == "success" and row["session_id"] == scope["session_id"]
        manifest = json.loads(row["context_manifest_json"])
        assert manifest["presentation_revision_ids"] == [scope["expected_revision_id"]]
        assert manifest["rehearsal_session_ids"] == [scope["session_id"]]
        assert result["hint"]["quotes"][0]["quote"] not in row["context_manifest_json"]
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_reviews").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM presentation_claims").fetchone()[0] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"expected_context_sha256": "0" * 64},
        {"expected_context_sha256": "bad"},
        {"window_index": True},
        {"window_index": 1},
        {"window_index": -1},
        {"speech": "caller-provided authority"},
    ],
)
def test_invalid_preparation_never_invokes_provider(rehearsal, change):
    core, scope = rehearsal
    provider = CoverageProvider()
    with pytest.raises(CoreDomainError):
        analysis(core, provider).analyze(params(core, scope) | change)
    assert provider.call_count == 0


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("speech", "REHEARSAL_CONTEXT_CHANGED"),
        ("privacy", "PRIVACY_POLICY_CHANGED"),
        ("head", "PRESENTATION_REVISION_CONFLICT"),
        ("invented", "PROVIDER_MALFORMED_OUTPUT"),
    ],
)
def test_rejects_changed_authority_and_false_quotes(rehearsal, mutation, code):
    core, scope = rehearsal
    chosen = params(core, scope)

    def mutate():
        if mutation == "head":
            _, _, _, inventory = core._presentation_workspace_sources.read_revision_inventory(
                {
                    "project_id": scope["project_id"],
                    "document_id": scope["document_id"],
                    "revision_id": scope["expected_revision_id"],
                }
            )
            call(
                core,
                "presentation.workspace.reorder_slides",
                {
                    **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
                    "ordered_slide_ids": [slide.slide_id for slide in reversed(inventory.slides)],
                },
            )
            return
        with core._storage.project_database(scope["project_id"]) as db:
            if mutation == "speech":
                db.execute(
                    "UPDATE utterances SET text='late changed speech' WHERE session_id=?",
                    (scope["session_id"],),
                )
            elif mutation == "privacy":
                db.execute(
                    "UPDATE project SET privacy_mode='selected_context_cloud' WHERE id=?",
                    (scope["project_id"],),
                )
            db.commit()

    provider = CoverageProvider(action=mutate, invented=mutation == "invented")
    with pytest.raises(CoreDomainError) as error:
        analysis(core, provider).analyze(chosen)
    assert error.value.code == code
    with core._storage.project_database(scope["project_id"]) as db:
        row = db.execute("SELECT status,error_code FROM provider_runs").fetchone()
        assert row["status"] == "error" and row["error_code"] == code


def test_remote_local_only_and_cancellation_never_invoke(rehearsal):
    core, scope = rehearsal
    chosen = params(core, scope)
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute(
            "UPDATE project SET privacy_mode='local_only' WHERE id=?", (scope["project_id"],)
        )
        db.commit()
    provider = CoverageProvider(locality="remote")
    with pytest.raises(CoreDomainError) as error:
        analysis(core, provider).analyze(chosen)
    assert error.value.code == "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED" and provider.call_count == 0
    local = CoverageProvider()
    with pytest.raises(CoreDomainError) as error:
        analysis(core, local).analyze(chosen, cancellation_check=lambda: True)
    assert error.value.code == "PROVIDER_CANCELLED" and local.call_count == 0
