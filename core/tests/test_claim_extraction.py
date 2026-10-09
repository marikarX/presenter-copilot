"""Discovery never binds an unreviewed claim or grants a provider write authority."""

import copy
import json
import uuid
from pathlib import Path

import pytest
from test_presentation_claims import setup
from test_presentation_edit_planning import PlanProvider, call

from presenter_core.ipc.core import CoreService
from presenter_core.providers.models import ProviderError, validate_provider_output
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def core_with_provider(tmp_path, locality="local"):
    provider = PlanProvider(locality=locality)
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    scope, target, evidence = setup(core, tmp_path)
    return core, provider, scope, target, evidence


def test_review_only_exact_binding_and_content_free_audit(tmp_path: Path):
    core, provider, scope, target, _ = core_with_provider(tmp_path)
    try:
        response = call(
            core,
            "presentation.workspace.extract_claims",
            {**scope, "object_ids": [target["object_id"]]},
        )
        assert response["requires_user_review"] and response["revision_id"] == scope["revision_id"]
        item = response["candidates"][0]
        assert (
            item["quote"] == target["current_text"]
            and item["start"] == 0
            and item["end"] == len(item["quote"])
        )
        assert not call(core, "presentation.workspace.list_claims", scope)["items"]
        request = provider.request_objects[-1]
        assert (
            not request.evidence
            and not request.preferred_user_explanations
            and not request.speaker_evidence
        )
        packet = json.loads(request.current_slide_summary)
        assert packet == {
            "objects": [
                {
                    "object_id": target["object_id"],
                    "text": target["current_text"],
                    "source_kind": "native_text",
                }
            ]
        }
        with core._storage.project_database(scope["project_id"]) as connection:
            row = connection.execute(
                "SELECT status,context_manifest_json FROM provider_runs WHERE id=?",
                (response["provider_run_id"],),
            ).fetchone()
        assert row["status"] == "success" and item["quote"] not in row["context_manifest_json"]
        saved = call(
            core,
            "presentation.workspace.save_claim",
            {
                **scope,
                "object_id": item["object_id"],
                "quote": item["quote"],
                "evidence": [],
                "confirm": True,
            },
        )
        claim = call(core, "presentation.workspace.list_claims", scope)["items"][0]
        assert (
            claim["claim_id"] == saved["claim_id"]
            and claim["provenance"] == "user_confirmed"
            and claim["coverage"] == "unlinked"
        )
    finally:
        core.close()


@pytest.mark.parametrize("bad", ["unknown", "paraphrase", "duplicate", "confidence", "kind"])
def test_unbound_or_malformed_provider_quotes_rejected(tmp_path: Path, bad: str):
    core, provider, scope, target, _ = core_with_provider(tmp_path)

    def modify(output, _invocation):
        item = output["candidates"][0]
        if bad == "unknown":
            item["object_id"] = str(uuid.uuid4())
        if bad == "paraphrase":
            item["quote"] = "An invented pilot assertion"
        if bad == "duplicate":
            output["candidates"].append(copy.deepcopy(item))
        if bad == "confidence":
            item["confidence"] = True
        if bad == "kind":
            item["kind"] = "verified_fact"

    provider.modifier = modify
    try:
        error = call(
            core,
            "presentation.workspace.extract_claims",
            {**scope, "object_ids": [target["object_id"]]},
            ok=False,
        )
        assert error["code"] == "PROVIDER_MALFORMED_OUTPUT"
        assert not call(core, "presentation.workspace.list_claims", scope)["items"]
        with core._storage.project_database(scope["project_id"]) as connection:
            assert (
                connection.execute(
                    "SELECT status FROM provider_runs ORDER BY started_at DESC LIMIT 1"
                ).fetchone()[0]
                == "error"
            )
    finally:
        core.close()


@pytest.mark.parametrize("ids", [[], ["wrong"], [str(uuid.uuid4())], [str(uuid.uuid4())] * 9])
def test_invalid_selection_never_reaches_provider(tmp_path: Path, ids):
    core, provider, scope, _target, _ = core_with_provider(tmp_path)
    try:
        call(core, "presentation.workspace.extract_claims", {**scope, "object_ids": ids}, ok=False)
        assert not provider.requests
    finally:
        core.close()


def test_privacy_changed_during_extraction_rejects_result(tmp_path: Path):
    core, provider, scope, target, _ = core_with_provider(tmp_path)

    def change(_output, _invocation):
        with core._storage.project_database(scope["project_id"]) as connection:
            connection.execute(
                "UPDATE project SET privacy_mode='selected_context_cloud' WHERE id=?",
                (scope["project_id"],),
            )
            connection.commit()

    provider.modifier = change
    try:
        error = call(
            core,
            "presentation.workspace.extract_claims",
            {**scope, "object_ids": [target["object_id"]]},
            ok=False,
        )
        assert error["code"] == "PRIVACY_POLICY_CHANGED"
        assert not call(core, "presentation.workspace.list_claims", scope)["items"]
    finally:
        core.close()


def test_schema_empty_abstention_and_nonfinite_confidence():
    assert (
        validate_provider_output(
            "presentation_claim_extraction", {"summary": "No candidates.", "candidates": []}
        )["candidates"]
        == []
    )
    with pytest.raises(ProviderError):
        validate_provider_output(
            "presentation_claim_extraction",
            {
                "summary": "",
                "candidates": [
                    {
                        "object_id": str(uuid.uuid4()),
                        "quote": "A claim",
                        "kind": "factual",
                        "reason": "",
                        "confidence": float("nan"),
                    }
                ],
            },
        )


def test_remote_extraction_respects_local_only_before_disclosure(tmp_path: Path):
    core, provider, scope, target, _ = core_with_provider(tmp_path, locality="remote")
    try:
        error = call(
            core,
            "presentation.workspace.extract_claims",
            {**scope, "object_ids": [target["object_id"]]},
            ok=False,
        )
        assert error["code"] == "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED"
        assert not provider.requests
    finally:
        core.close()


def test_revision_changed_during_extraction_has_no_success_or_binding(tmp_path: Path):
    from test_presentation_narrative import change

    core, provider, scope, target, _ = core_with_provider(tmp_path)
    provider.modifier = lambda _output, _invocation: change(core, scope, target)
    try:
        error = call(
            core,
            "presentation.workspace.extract_claims",
            {**scope, "object_ids": [target["object_id"]]},
            ok=False,
        )
        assert error["code"] == "PRESENTATION_REVISION_CONFLICT"
        with core._storage.project_database(scope["project_id"]) as connection:
            assert connection.execute("SELECT COUNT(*) FROM presentation_claims").fetchone()[0] == 0
            assert (
                connection.execute(
                    "SELECT status FROM provider_runs ORDER BY started_at DESC LIMIT 1"
                ).fetchone()[0]
                == "error"
            )
    finally:
        core.close()


@pytest.fixture
def extraction_server():
    import test_local_provider

    yield from test_local_provider.server.__wrapped__()


def test_strict_local_transport_and_empty_result(tmp_path: Path, extraction_server):
    from test_local_provider import configure

    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, target, _ = setup(core, tmp_path)
        configure(core, extraction_server["endpoint"])
        call(core, "provider.test", {"provider_id": "local_openai"})
        extraction_server["body"] = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {"summary": "No substantive claims found.", "candidates": []}
                            )
                        },
                    }
                ]
            }
        ).encode()
        result = call(
            core,
            "presentation.workspace.extract_claims",
            {**scope, "object_ids": [target["object_id"]]},
        )
        assert not result["candidates"] and result["provider_id"] == "local_openai"
        _, _, body = extraction_server["calls"][-1]
        assert body["max_tokens"] == 4096 and "tools" not in body
        assert body["response_format"]["json_schema"]["name"] == "presentation_claim_extraction"
        assert body["response_format"]["json_schema"]["strict"] is True
        assert not call(core, "presentation.workspace.list_claims", scope)["items"]
    finally:
        core.close()
