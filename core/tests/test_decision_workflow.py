"""Core privacy and provenance boundaries for the typed decision workflow."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from presenter_core.credentials import (
    InMemoryChatGPTPlanCredentialStore,
    InMemoryCredentialStore,
)
from presenter_core.decisions.models import (
    ChoiceAnswer,
    ChoiceDecisionRequest,
    ChoiceDecisionResult,
)
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter

FIXTURE_ROOT = Path(__file__).parents[2] / "samples" / "synthetic-deck"


class _DecisionProvider:
    id = "fixture_choice"
    model_id = "fixture-choice-v1"

    def __init__(self, *, leaves_machine: bool = False) -> None:
        self.locality = "remote" if leaves_machine else "local"
        self._leaves_machine = leaves_machine
        self.requests: list[ChoiceDecisionRequest] = []

    @property
    def leaves_machine(self) -> bool:
        return self._leaves_machine

    def decide(self, request: ChoiceDecisionRequest) -> ChoiceDecisionResult:
        self.requests.append(request)
        return ChoiceDecisionResult(
            provider_id=self.id,
            model_id=self.model_id,
            latency_ms=4,
            answers={
                "purpose": ChoiceAnswer(
                    name="purpose",
                    choice="opening",
                    confidence=0.82,
                    probabilities={"opening": 0.82, "unclear": 0.18},
                )
            },
        )

    def close(self) -> None:
        return None


def _call(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
    )
    assert response["ok"] is True, response
    result = response["result"]
    assert isinstance(result, dict)
    return result


def _error(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
    )
    assert response["ok"] is False, response
    error = response["error"]
    assert isinstance(error, dict)
    return error


def _presentation_context(core: CoreService, *, privacy_mode: str = "local_only") -> dict[str, str]:
    project = _call(
        core,
        "project.create",
        {"name": "Decision workflow fixture", "privacy_mode": privacy_mode},
    )["project"]
    project_id = str(project["id"])
    imported = _call(
        core,
        "source.import",
        {
            "project_id": project_id,
            "kind": "presentation",
            "path": str((FIXTURE_ROOT / "deck" / "presentation.pptx").resolve()),
        },
    )["document"]
    opened = _call(
        core,
        "presentation.workspace.open_source",
        {"project_id": project_id, "document_id": imported["id"]},
    )
    return {
        "project_id": project_id,
        "document_id": str(imported["id"]),
        "revision_id": str(opened["revision_id"]),
    }


def _classify_params(context: dict[str, str]) -> dict[str, Any]:
    return {
        **context,
        "slide_number": 1,
    }


def test_slide_purpose_uses_bounded_text_and_records_only_safe_manifest(tmp_path: Path) -> None:
    provider = _DecisionProvider()
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        decision_provider=provider,
        decision_credential_store=InMemoryCredentialStore(),
    )
    try:
        context = _presentation_context(core)
        result = _call(
            core,
            "presentation.workspace.classify_slide",
            _classify_params(context),
        )

        assert result == {
            "provider_run_id": result["provider_run_id"],
            "revision_id": context["revision_id"],
            "slide_id": result["slide_id"],
            "slide_number": 1,
            "purpose": "opening",
            "confidence": 0.82,
            "probabilities": {"opening": 0.82, "unclear": 0.18},
            "provider_id": provider.id,
            "model_id": provider.model_id,
            "latency_ms": 4,
            "requires_user_review": True,
        }
        assert len(provider.requests) == 1
        request = provider.requests[0]
        assert set(request.state) == {"slide_text"}
        assert isinstance(request.state["slide_text"], tuple)
        assert all(
            isinstance(value, str) and value.strip() for value in request.state["slide_text"]
        )
        serialized_input = request.serialized_request()
        assert context["project_id"] not in serialized_input
        assert context["document_id"] not in serialized_input
        assert context["revision_id"] not in serialized_input
        assert str((FIXTURE_ROOT / "deck" / "presentation.pptx").resolve()) not in serialized_input

        with core._storage.project_database(context["project_id"]) as connection:  # type: ignore[attr-defined]
            row = connection.execute(
                "SELECT provider_id, privacy_mode, status, context_manifest_json "
                "FROM provider_runs WHERE id = ?",
                (result["provider_run_id"],),
            ).fetchone()
        assert row is not None
        manifest = json.loads(row["context_manifest_json"])
        assert row["provider_id"] == provider.id
        assert row["privacy_mode"] == "local_only"
        assert row["status"] == "success"
        assert manifest["provider_content_boundary"] == "selected_slide_text"
        assert manifest["classes_sent"] == ["presentation_text"]
        assert manifest["source_ids"] == [context["document_id"]]
        assert manifest["presentation_revision_ids"] == [context["revision_id"]]
        assert manifest["full_document_sent"] is False
        assert manifest["full_corpus_sent"] is False
        assert "slide_text" not in manifest
        assert "Northstar migration decision" not in json.dumps(manifest)
    finally:
        core.close()


def test_ollama_digest_is_recorded_as_content_free_run_provenance(tmp_path: Path) -> None:
    provider = _DecisionProvider()
    provider.id = "ollama_systemone"
    provider.model_id = f"tev1:4b-q4_K_M@sha256:{'a' * 64}"
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        decision_provider=provider,
        decision_credential_store=InMemoryCredentialStore(),
    )
    try:
        context = _presentation_context(core)
        result = _call(
            core,
            "presentation.workspace.classify_slide",
            _classify_params(context),
        )
        assert result["model_id"] == provider.model_id
        with core._storage.project_database(context["project_id"]) as connection:  # type: ignore[attr-defined]
            row = connection.execute(
                "SELECT context_manifest_json FROM provider_runs WHERE id = ?",
                (result["provider_run_id"],),
            ).fetchone()
        assert row is not None
        manifest = json.loads(row["context_manifest_json"])
        assert manifest["resolved_model_id"] == provider.model_id
        assert "Northstar migration decision" not in json.dumps(manifest)
    finally:
        core.close()


def test_slide_purpose_is_user_confirmed_persisted_and_revision_scoped(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        decision_provider=_DecisionProvider(),
        decision_credential_store=InMemoryCredentialStore(),
    )
    context: dict[str, str] | None = None
    try:
        context = _presentation_context(core)
        decision = _call(
            core,
            "presentation.workspace.classify_slide",
            _classify_params(context),
        )
        assert isinstance(decision["slide_id"], str)
        empty = _call(
            core,
            "presentation.workspace.list_slide_purposes",
            context,
        )
        assert empty == {"revision_id": context["revision_id"], "items": []}

        saved = _call(
            core,
            "presentation.workspace.save_slide_purpose",
            {
                **context,
                "slide_id": decision["slide_id"],
                "slide_number": 1,
                # A user may confirm or correct the model suggestion.
                "purpose": "evidence",
            },
        )
        assert saved == {
            "revision_id": context["revision_id"],
            "slide_id": decision["slide_id"],
            "purpose": "evidence",
            "provenance": "user_confirmed",
            "created_at": saved["created_at"],
            "updated_at": saved["updated_at"],
        }
        listed = _call(
            core,
            "presentation.workspace.list_slide_purposes",
            context,
        )
        assert listed["items"] == [
            {
                "slide_id": decision["slide_id"],
                "revision_id": context["revision_id"],
                "purpose": "evidence",
                "provenance": "user_confirmed",
                "created_at": saved["updated_at"],
                "updated_at": saved["updated_at"],
            }
        ]

        targets = _call(
            core,
            "presentation.workspace.list_text_targets",
            {**context, "slide_number": 1},
        )
        target = next(item for item in targets["targets"] if item["single_run_editable"])
        changed = _call(
            core,
            "presentation.workspace.replace_single_run_text",
            {
                "project_id": context["project_id"],
                "document_id": context["document_id"],
                "expected_revision_id": context["revision_id"],
                "operation_type": "replace_single_run_text",
                "slide_id": targets["slide_id"],
                "object_id": target["object_id"],
                "expected_text": target["current_text"],
                "replacement_text": "Revised slide text",
            },
        )
        next_context = {**context, "revision_id": changed["revision_id"]}
        assert (
            _error(
                core,
                "presentation.workspace.list_slide_purposes",
                context,
            )["code"]
            == "PRESENTATION_REVISION_CONFLICT"
        )
        assert _call(
            core,
            "presentation.workspace.list_slide_purposes",
            next_context,
        ) == {"revision_id": changed["revision_id"], "items": []}

        stale_save = _error(
            core,
            "presentation.workspace.save_slide_purpose",
            {
                **context,
                "slide_id": decision["slide_id"],
                "slide_number": 1,
                "purpose": "evidence",
            },
        )
        assert stale_save["code"] == "PRESENTATION_REVISION_CONFLICT"

        _call(
            core,
            "presentation.workspace.restore_revision",
            {
                "project_id": context["project_id"],
                "document_id": context["document_id"],
                "expected_revision_id": changed["revision_id"],
                "revision_id": context["revision_id"],
            },
        )
        restored = _call(
            core,
            "presentation.workspace.list_slide_purposes",
            context,
        )
        assert restored["items"][0]["purpose"] == "evidence"
        core.close()
        core = CoreService(
            data_root=data_root,
            embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        )
        restarted = _call(
            core,
            "presentation.workspace.list_slide_purposes",
            context,
        )
        assert restarted == restored
    finally:
        core.close()


def test_slide_purpose_rejects_invalid_values_and_mismatched_slide_ids(
    tmp_path: Path,
) -> None:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        context = _presentation_context(core)
        first = _call(
            core,
            "presentation.workspace.list_text_targets",
            {**context, "slide_number": 1},
        )
        second = _call(
            core,
            "presentation.workspace.list_text_targets",
            {**context, "slide_number": 2},
        )
        base = {
            **context,
            "slide_id": first["slide_id"],
            "slide_number": 1,
            "purpose": "opening",
        }
        assert (
            _error(
                core,
                "presentation.workspace.save_slide_purpose",
                {**base, "purpose": "untrusted"},
            )["code"]
            == "INVALID_REQUEST"
        )
        mismatch = _error(
            core,
            "presentation.workspace.save_slide_purpose",
            {**base, "slide_id": second["slide_id"]},
        )
        assert mismatch["code"] == "PRESENTATION_SEMANTIC_SLIDE_MISMATCH"
        with core._storage.project_database(context["project_id"]) as connection:  # type: ignore[attr-defined]
            count = connection.execute(
                "SELECT COUNT(*) FROM presentation_slide_purposes"
            ).fetchone()[0]
        assert count == 0
    finally:
        core.close()


def test_remote_decision_is_blocked_before_call_or_audit_run_in_local_only(
    tmp_path: Path,
) -> None:
    provider = _DecisionProvider(leaves_machine=True)
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        decision_provider=provider,
        decision_credential_store=InMemoryCredentialStore(),
    )
    try:
        context = _presentation_context(core)
        error = _error(
            core,
            "presentation.workspace.classify_slide",
            _classify_params(context),
        )
        assert error["code"] == "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED"
        assert provider.requests == []
        with core._storage.project_database(context["project_id"]) as connection:  # type: ignore[attr-defined]
            count = connection.execute(
                "SELECT COUNT(*) FROM provider_runs WHERE task_type = 'presentation_slide_purpose'"
            ).fetchone()[0]
        assert count == 0
    finally:
        core.close()


def test_selected_native_decisions_respects_privacy_and_explicit_review(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[dict[str, Any]] = []

    def poster(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
        assert url == "https://api.openai.com/v1/decisions"
        assert headers["Authorization"] == "Bearer synthetic-native-key"
        payload = json.loads(body)
        calls.append(payload)
        return 200, json.dumps(
            {
                "model": "gpt-6-luna",
                "answers": [
                    {
                        "type": "choice",
                        "name": question["name"],
                        "choice": "opening",
                        "confidence": 0.82,
                        "probabilities": [
                            {
                                "value": option["value"],
                                "probability": 1 if option["value"] == "opening" else 0,
                            }
                            for option in question["choices"]
                        ],
                    }
                    for question in payload["questions"]
                ],
            }
        ).encode()

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("presenter_core.decisions.openai_decisions._post_json", poster)
    core = CoreService(
        data_root=tmp_path / "native",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=InMemoryCredentialStore("synthetic-native-key"),
        decision_credential_store=InMemoryCredentialStore(),
    )
    try:
        _call(core, "provider.decision.configure", {"provider_id": "openai_decisions"})
        local = _presentation_context(core)
        assert (
            _error(core, "presentation.workspace.classify_slide", _classify_params(local))["code"]
            == "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED"
        )
        cloud = _presentation_context(core, privacy_mode="selected_context_cloud")
        assert (
            _error(core, "presentation.workspace.classify_slide", _classify_params(cloud))["code"]
            == "PRIVACY_REMOTE_ACK_REQUIRED"
        )
        assert calls == []
        _call(core, "project.acknowledge_remote_reasoning", {"project_id": cloud["project_id"]})
        result = _call(core, "presentation.workspace.classify_slide", _classify_params(cloud))
        assert result["provider_id"] == "openai_decisions"
        assert result["requires_user_review"] is True
        assert result["confidence"] == 0.82
        assert len(calls) == 1
        assert set(json.loads(calls[0]["input"])) == {"slide_text"}
        assert _call(core, "presentation.workspace.list_slide_purposes", cloud)["items"] == []
        with core._storage.project_database(cloud["project_id"]) as connection:
            row = connection.execute(
                "SELECT provider_id, context_manifest_json FROM provider_runs WHERE id = ?",
                (result["provider_run_id"],),
            ).fetchone()
        assert row is not None and row["provider_id"] == "openai_decisions"
        assert "synthetic-native-key" not in row["context_manifest_json"]
        for text in json.loads(calls[0]["input"])["slide_text"]:
            assert text not in row["context_manifest_json"]
    finally:
        core.close()


def test_acknowledged_selected_context_cloud_allows_selected_text_only(tmp_path: Path) -> None:
    provider = _DecisionProvider(leaves_machine=True)
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        decision_provider=provider,
        decision_credential_store=InMemoryCredentialStore(),
    )
    try:
        context = _presentation_context(core, privacy_mode="selected_context_cloud")
        _call(core, "project.acknowledge_remote_reasoning", {"project_id": context["project_id"]})
        result = _call(
            core,
            "presentation.workspace.classify_slide",
            _classify_params(context),
        )
        assert result["requires_user_review"] is True
        assert len(provider.requests) == 1
        with core._storage.project_database(context["project_id"]) as connection:  # type: ignore[attr-defined]
            row = connection.execute(
                "SELECT privacy_mode, context_manifest_json FROM provider_runs WHERE id = ?",
                (result["provider_run_id"],),
            ).fetchone()
        assert row is not None
        assert row["privacy_mode"] == "selected_context_cloud"
        assert json.loads(row["context_manifest_json"])["classes_sent"] == ["presentation_text"]
    finally:
        core.close()


def test_provider_identity_mismatch_is_audited_as_invalid_output(tmp_path: Path) -> None:
    provider = _DecisionProvider()
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        decision_provider=provider,
        decision_credential_store=InMemoryCredentialStore(),
    )
    try:
        context = _presentation_context(core)

        def mismatch(request: ChoiceDecisionRequest) -> ChoiceDecisionResult:
            provider.requests.append(request)
            return ChoiceDecisionResult(
                provider_id="other_provider",
                model_id=provider.model_id,
                latency_ms=1,
                answers={"purpose": ChoiceAnswer(name="purpose", choice="opening")},
            )

        provider.decide = mismatch  # type: ignore[method-assign]
        error = _error(
            core,
            "presentation.workspace.classify_slide",
            _classify_params(context),
        )
        assert error["code"] == "DECISION_PROVIDER_MALFORMED_OUTPUT"
        with core._storage.project_database(context["project_id"]) as connection:  # type: ignore[attr-defined]
            row = connection.execute(
                "SELECT status, error_code FROM provider_runs "
                "WHERE task_type = 'presentation_slide_purpose'"
            ).fetchone()
        assert row is not None
        assert row["status"] == "error"
        assert row["error_code"] == "DECISION_PROVIDER_MALFORMED_OUTPUT"
    finally:
        core.close()


def test_decision_settings_and_openrouter_credentials_keep_secrets_in_core(
    tmp_path: Path, monkeypatch: Any
) -> None:
    store = InMemoryCredentialStore()
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=InMemoryCredentialStore(),
        decision_credential_store=store,
    )
    secret = "decision-workflow-secret"
    try:
        initial = _call(core, "provider.decision.status", {})
        assert initial["selected_provider_id"] == "disabled"
        listed_ids = {item["provider_id"] for item in initial["providers"]}
        assert "openai_fast" in listed_ids
        assert "openai_ultrafast" in listed_ids
        assert "openai_decisions" in listed_ids
        native = next(
            item for item in initial["providers"] if item["provider_id"] == "openai_decisions"
        )
        assert native["model_id"] == "gpt-6-luna"
        assert native["leaves_machine"] is True
        assert (
            _call(
                core,
                "provider.decision.configure",
                {
                    "provider_id": "openai_decisions",
                },
            )["selected_provider_id"]
            == "openai_decisions"
        )
        assert core._providers.decision_provider("openai_decisions").id == "openai_decisions"
        assert "ollama_systemone" in listed_ids
        ollama = next(
            item for item in initial["providers"] if item["provider_id"] == "ollama_systemone"
        )
        assert ollama["leaves_machine"] is False
        assert ollama["model_id"] == "tev1:4b"
        assert [option["model_id"] for option in ollama["model_options"]] == [
            "nimble:9b",
            "nimble:9b-q4_K_M",
            "nimble:latest",
            "tev1:4b",
            "tev1:4b-q4_K_M",
            "tev1:latest",
            "tev1:0.8b",
        ]
        ultrafast = next(
            item for item in initial["providers"] if item["provider_id"] == "openai_ultrafast"
        )
        assert ultrafast["model_id"] == "gpt-6-astra"
        assert store.read() is None

        configured_ultrafast = _call(
            core,
            "provider.decision.configure",
            {"provider_id": "openai_ultrafast"},
        )
        assert configured_ultrafast["selected_provider_id"] == "openai_ultrafast"

        configured_ollama = _call(
            core,
            "provider.decision.configure",
            {"provider_id": "ollama_systemone", "model_id": "tev1:0.8b"},
        )
        assert configured_ollama["selected_provider_id"] == "ollama_systemone"
        assert configured_ollama["ollama_model_id"] == "tev1:0.8b"

        configured_ollama_latest = _call(
            core,
            "provider.decision.configure",
            {"provider_id": "ollama_systemone", "model_id": "nimble:latest"},
        )
        assert configured_ollama_latest["selected_provider_id"] == "ollama_systemone"
        assert configured_ollama_latest["ollama_model_id"] == "nimble:latest"

        unsupported_model = _error(
            core,
            "provider.decision.configure",
            {"provider_id": "ollama_systemone", "model_id": "qwen3.5"},
        )
        assert unsupported_model["code"] == "INVALID_REQUEST"

        configured = _call(
            core,
            "provider.decision.configure",
            {"provider_id": "openrouter_jev"},
        )
        assert configured["selected_provider_id"] == "openrouter_jev"
        assert configured["ollama_model_id"] == "nimble:latest"
        assert store.read() is None

        monkeypatch.setenv("OPENROUTER_API_KEY", secret)
        detected = _call(core, "provider.decision.credentials.status", {})
        assert detected["environment_detected"] is True
        assert detected["credential_source"] == "environment"
        saved = _call(core, "provider.decision.credentials.save_detected", {})
        assert saved["saved"] is True
        assert saved["credential_source"] == store.source
        assert store.read() == secret

        serialized = json.dumps([initial, configured, detected, saved])
        assert secret not in serialized

        removed = _call(core, "provider.decision.credentials.remove", {})
        assert removed["credentials_removed"] is True
        assert removed["credential_source"] == "environment"
        assert store.read() is None
        assert secret not in json.dumps(removed)
    finally:
        core.close()


def test_chatgpt_plan_decisions_use_separate_auth_and_account_model_catalog(
    tmp_path: Path,
) -> None:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=InMemoryCredentialStore(),
        decision_credential_store=InMemoryCredentialStore(),
        chatgpt_plan_store=InMemoryChatGPTPlanCredentialStore(),
    )
    try:
        auth = _call(core, "provider.chatgpt_plan.status", {})
        assert auth == {
            "state": "signed_out",
            "error_code": None,
            "credential_store_available": True,
            "active_account_id": None,
            "accounts": [],
        }
        assert _call(core, "provider.chatgpt_plan.models", {}) == {"models": []}

        status = _call(core, "provider.decision.status", {})
        plan_provider = next(
            item for item in status["providers"] if item["provider_id"] == "openai_chatgpt_plan"
        )
        assert plan_provider["configured"] is False
        assert plan_provider["leaves_machine"] is True

        error = _error(
            core,
            "provider.decision.configure",
            {"provider_id": "openai_chatgpt_plan", "model_id": "untrusted-model"},
        )
        assert error["code"] == "INVALID_REQUEST"
    finally:
        core.close()
