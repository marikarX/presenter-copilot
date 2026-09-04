"""Milestone 8 privacy, provider resilience, and execution-boundary tests."""

from __future__ import annotations

import json
import socket
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from time import sleep
from types import SimpleNamespace
from typing import Any

import pytest

from presenter_core.ipc.core import CoreService
from presenter_core.providers.context import APPLICATION_POLICY
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.providers.models import (
    ProviderError,
    ProviderInvocation,
    ReasoningRequest,
    ReasoningResult,
    derive_context_manifest,
    question_output_schema,
)
from presenter_core.providers.openai import OpenAIReasoningProvider
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter

FIXTURE_ROOT = Path(__file__).parents[2] / "samples" / "synthetic-deck"

_COMMON_REMOTE_CONTEXT_CLASSES = {
    "application_policy",
    "current_slide_summary",
    "document_excerpt",
    "question_grounding",
    "speaker_evidence",
    "style_context",
    "style_policy",
    "task_instruction",
    "user_knowledge",
}
_REMOTE_TASK_CONTEXT_ALLOWLIST = {
    "teach_question": _COMMON_REMOTE_CONTEXT_CLASSES | {"rejected_patterns"},
    "teach_candidate": _COMMON_REMOTE_CONTEXT_CLASSES
    | {"current_user_input", "question", "rejected_patterns"},
    "challenge_question": _COMMON_REMOTE_CONTEXT_CLASSES
    | {
        "audience_context",
        "challenge_intensity",
        "conflict_metadata",
        "prior_question_context",
        "rejected_patterns",
    },
    "challenge_follow_up": _COMMON_REMOTE_CONTEXT_CLASSES
    | {
        "audience_context",
        "challenge_intensity",
        "conflict_metadata",
        "prior_question_context",
        "question",
        "rejected_patterns",
    },
    "challenge_evaluation": _COMMON_REMOTE_CONTEXT_CLASSES
    | {
        "audience_context",
        "challenge_intensity",
        "conflict_metadata",
        "current_user_input",
        "prior_question_context",
        "question",
        "rejected_patterns",
    },
    "live_cue": _COMMON_REMOTE_CONTEXT_CLASSES
    | {"conflict_metadata", "question", "rejected_patterns"},
}
_PAYLOAD_CONTEXT_CLASSES = {
    "current_slide_summary": "current_slide_summary",
    "question": "question",
    "user_input": "current_user_input",
    "untrusted_retrieved_evidence": "document_excerpt",
    "approved_user_knowledge": "user_knowledge",
    "approved_speaker_style_evidence": "speaker_evidence",
    "conflict_metadata": "conflict_metadata",
    "approved_audience_context": "audience_context",
    "challenge_intensity": "challenge_intensity",
    "prior_question_context": "prior_question_context",
    "style_policy": "style_policy",
}
_STYLE_CONTEXT_CLASSES = {
    "project_preferred_explanations": "user_knowledge",
    "approved_speaker_evidence": "speaker_evidence",
    "rejected_patterns": "rejected_patterns",
}


def _message(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "type": "request",
        "request_id": str(uuid.uuid4()),
        "method": method,
        "params": params,
    }


def _call(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(_message(method, params))
    assert response["ok"] is True, response
    result = response["result"]
    assert isinstance(result, dict)
    return result


def _error(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(_message(method, params))
    assert response["ok"] is False, response
    error = response["error"]
    assert isinstance(error, dict)
    return error


def _has_disclosed_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _payload_context_classes(request: ReasoningRequest, payload: dict[str, Any]) -> set[str]:
    classes = {"application_policy", "style_context"}
    if request.task_instruction:
        classes.add("task_instruction")
    for field, context_class in _PAYLOAD_CONTEXT_CLASSES.items():
        if _has_disclosed_value(payload.get(field)):
            classes.add(context_class)
    style_context = payload.get("style_context")
    if isinstance(style_context, dict):
        for field, context_class in _STYLE_CONTEXT_CLASSES.items():
            if _has_disclosed_value(style_context.get(field)):
                classes.add(context_class)
    return classes


def _project(core: CoreService, privacy_mode: str) -> str:
    result = _call(
        core,
        "project.create",
        {"name": "M8 privacy fixture", "privacy_mode": privacy_mode},
    )
    return str(result["project"]["id"])


def _seed_source(core: CoreService, project_id: str) -> None:
    _call(
        core,
        "source.import",
        {
            "project_id": project_id,
            "kind": "supporting",
            "path": str(FIXTURE_ROOT / "supporting" / "architecture-notes.md"),
        },
    )
    _call(core, "retrieval.rebuild", {"project_id": project_id})


def _challenge_profile(core: CoreService, project_id: str) -> str:
    result = _call(
        core,
        "audience.create",
        {
            "project_id": project_id,
            "display_name": "M8 reviewer",
            "role": "CFO",
            "organization": "ExampleCo",
            "user_notes": "Cost evidence only.",
        },
    )
    return str(result["profile"]["id"])


def test_m8_local_only_has_a_low_level_network_denial_and_no_remote_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A configured remote provider cannot bypass Local Only in any task path."""

    def blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access is forbidden in the Local Only test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket.socket, "send", blocked)
    monkeypatch.setattr(socket.socket, "sendall", blocked)
    monkeypatch.setattr(socket.socket, "sendto", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)

    provider = DeterministicFakeReasoningProvider(locality="remote")
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
    )
    try:
        project_id = _project(core, "local_only")
        _seed_source(core, project_id)

        teach_session = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "teach"})["session"][
                "id"
            ]
        )
        prompt = _call(
            core,
            "teach.next_prompt",
            {"project_id": project_id, "session_id": teach_session},
        )
        assert prompt["route"] == "retrieval_only"
        assert provider.call_count == 0
        _call(
            core,
            "teach.submit_text",
            {
                "project_id": project_id,
                "session_id": teach_session,
                "text": "Keep the answer local to this project.",
            },
        )

        challenge_session = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "challenge"})[
                "session"
            ]["id"]
        )
        profile_id = _challenge_profile(core, project_id)
        _call(
            core,
            "challenge.configure",
            {
                "project_id": project_id,
                "session_id": challenge_session,
                "audience_profile_ids": [profile_id],
            },
        )
        challenge_error = _error(
            core,
            "challenge.next_question",
            {"project_id": project_id, "session_id": challenge_session},
        )
        assert challenge_error["code"] == "CHALLENGE_REASONING_UNAVAILABLE"

        live_session = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "live_assist"})[
                "session"
            ]["id"]
        )
        assist = _call(
            core,
            "assist.request",
            {
                "project_id": project_id,
                "session_id": live_session,
                "question": "Explain the warm standby ownership boundary.",
            },
        )
        assert core._assist.wait_for_idle(5.0)  # type: ignore[attr-defined]
        assert assist["assist_id"]
        assert provider.call_count == 0
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 0
    finally:
        core.close()


class _ObservedProvider(DeterministicFakeReasoningProvider):
    def __init__(self) -> None:
        super().__init__(locality="remote")
        self.observations: list[dict[str, Any]] = []
        self.manifest_event_seen: Callable[[str], dict[str, Any] | None] | None = None

    def generate(self, request: ReasoningRequest) -> ReasoningResult:
        assert self.manifest_event_seen is not None
        observed = self.manifest_event_seen(request.task_type)
        assert observed is not None
        self.observations.append(
            {
                "task_type": request.task_type,
                "status": observed["status"],
                "manifest": observed["manifest"],
                "request_manifest": dict(request.context_manifest),
            }
        )
        return super().generate(request)


def test_m8_remote_tasks_capture_exact_metadata_manifest_before_generate(tmp_path: Path) -> None:
    provider = _ObservedProvider()
    event_lock = threading.Lock()
    order: list[str] = []
    manifest_snapshots: dict[str, dict[str, Any]] = {}
    core_ref: list[CoreService] = []

    def on_event(envelope: dict[str, Any]) -> None:
        event = str(envelope["event"])
        payload = dict(envelope["payload"])
        if event != "privacy.remote_context_manifest":
            return
        run_id = str(payload["provider_run_id"])
        with core_ref[0]._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            row = connection.execute(
                "SELECT status, context_manifest_json FROM provider_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        assert row is not None
        with event_lock:
            order.extend(["run_started", "manifest_event"])
            manifest_snapshots[str(payload["task_type"])] = {
                "status": str(row["status"]),
                "manifest": json.loads(str(row["context_manifest_json"])),
            }

    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
        event_sink=on_event,
    )
    core_ref.append(core)
    provider.manifest_event_seen = lambda task_type: manifest_snapshots.get(task_type)
    try:
        project_id = _project(core, "selected_context_cloud")
        _call(
            core,
            "project.acknowledge_remote_reasoning",
            {"project_id": project_id},
        )
        _seed_source(core, project_id)

        teach_session = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "teach"})["session"][
                "id"
            ]
        )
        teach_prompt = _call(
            core,
            "teach.next_prompt",
            {"project_id": project_id, "session_id": teach_session},
        )
        _call(
            core,
            "teach.submit_text",
            {
                "project_id": project_id,
                "session_id": teach_session,
                "text": "The warm standby preserves a tested recovery boundary.",
            },
        )

        challenge_session = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "challenge"})[
                "session"
            ]["id"]
        )
        profile_id = _challenge_profile(core, project_id)
        _call(
            core,
            "challenge.configure",
            {
                "project_id": project_id,
                "session_id": challenge_session,
                "audience_profile_ids": [profile_id],
                "intensity": "skeptical",
            },
        )
        challenge_question = _call(
            core,
            "challenge.next_question",
            {"project_id": project_id, "session_id": challenge_session},
        )["question"]
        _call(
            core,
            "challenge.submit_answer",
            {
                "project_id": project_id,
                "session_id": challenge_session,
                "question_id": challenge_question["id"],
                "text": "The warm standby recovery plan is supported by the architecture notes.",
            },
        )
        follow_up = _call(
            core,
            "challenge.next_question",
            {
                "project_id": project_id,
                "session_id": challenge_session,
                "follow_up_to_question_id": challenge_question["id"],
            },
        )
        assert follow_up["question"]["parent_question_id"] == challenge_question["id"]

        live_session = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "live_assist"})[
                "session"
            ]["id"]
        )
        live = _call(
            core,
            "assist.request",
            {
                "project_id": project_id,
                "session_id": live_session,
                "question": "Explain the warm standby ownership boundary.",
                "trigger": "button",
            },
        )
        assert core._assist.wait_for_idle(5.0)  # type: ignore[attr-defined]
        assert live["assist_id"]

        expected_task_types = {
            "teach_question",
            "teach_candidate",
            "challenge_question",
            "challenge_follow_up",
            "challenge_evaluation",
            "live_cue",
        }
        assert {item["task_type"] for item in provider.observations} == expected_task_types
        assert len(provider.requests) == len(provider.request_objects) == len(expected_task_types)
        for request, payload in zip(provider.request_objects, provider.requests, strict=True):
            allowed_classes = _REMOTE_TASK_CONTEXT_ALLOWLIST[request.task_type]
            disclosed_classes = _payload_context_classes(request, payload)
            assert disclosed_classes <= allowed_classes
            observation = next(
                item for item in provider.observations if item["task_type"] == request.task_type
            )
            assert set(observation["manifest"]["classes_sent"]) <= allowed_classes
        for observation in provider.observations:
            assert observation["status"] == "started"
            assert observation["manifest"] == observation["request_manifest"]
            serialized_manifest = json.dumps(observation["manifest"], ensure_ascii=False)
            assert "warm standby" not in serialized_manifest.casefold()
            assert '"text"' not in serialized_manifest.casefold()
        assert teach_prompt["context_manifest"] == next(
            item["manifest"]
            for item in provider.observations
            if item["task_type"] == "teach_question"
        )
        with event_lock:
            assert order
            assert order[0:2] == ["run_started", "manifest_event"]
        history = _call(
            core,
            "privacy.list_context_manifests",
            {"project_id": project_id, "limit": 2, "offset": 0},
        )
        assert history["total"] >= 6
        assert len(history["manifests"]) == 2
        assert history["has_more"] is True
        history_text = json.dumps(history, ensure_ascii=False).casefold()
        assert "warm standby" not in history_text
        assert '"text"' not in history_text
        assert "secret body" not in history_text
    finally:
        core.close()


def _direct_question_request(
    *,
    privacy_mode: str = "local_only",
    latency_budget_ms: int = 1_000,
    context_manifest: dict[str, Any] | None = None,
    preferred_user_explanations: tuple[dict[str, Any], ...] = (),
    style_context: dict[str, Any] | None = None,
    audience_context: tuple[dict[str, Any], ...] = (),
    challenge_intensity: str | None = None,
    prior_question_context: tuple[dict[str, Any], ...] = (),
) -> ReasoningRequest:
    return ReasoningRequest(
        task_type="teach_question",
        question=None,
        user_input=None,
        current_slide_summary=None,
        evidence=(),
        preferred_user_explanations=preferred_user_explanations,
        speaker_evidence=(),
        style_context=style_context if style_context is not None else {"policy": "preserve_voice"},
        conflict_metadata=(),
        style_policy="preserve_voice",
        privacy_mode=privacy_mode,
        output_schema=question_output_schema(),
        latency_budget_ms=latency_budget_ms,
        application_policy=APPLICATION_POLICY,
        context_manifest=context_manifest or {},
        audience_context=audience_context,
        challenge_intensity=challenge_intensity,
        prior_question_context=prior_question_context,
    )


def test_m8_manifest_is_derived_from_the_actual_final_payload() -> None:
    request = _direct_question_request()
    payload = request.to_payload()
    payload["untrusted_retrieved_evidence"] = [
        {"evidence_id": "actual-evidence", "source_id": "actual-source", "text": "bounded"}
    ]
    manifest = derive_context_manifest(request, provider_id="fake-test", payload=payload)
    assert manifest["source_ids"] == ["actual-source"]
    assert manifest["bounded_context_chars"] == len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    assert "actual-evidence" not in json.dumps(manifest)


def test_m8_nested_request_mutation_fails_closed_before_provider(tmp_path: Path) -> None:
    provider = DeterministicFakeReasoningProvider(locality="remote")
    events: list[dict[str, Any]] = []
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
        event_sink=events.append,
    )
    style_context = {
        "policy": "preserve_voice",
        "rejected_patterns": [{"id": "pattern-1", "text": "Keep this concise."}],
    }
    request = _direct_question_request(
        privacy_mode="selected_context_cloud",
        style_context=style_context,
    )
    widened_text = "MUTATED_SECRET_WIDENED_AFTER_VALIDATION"

    def mutate_request(_run_id: str, _manifest: dict[str, Any]) -> None:
        style_context["rejected_patterns"][0]["text"] = widened_text

    try:
        project_id = _project(core, "selected_context_cloud")
        _call(core, "project.acknowledge_remote_reasoning", {"project_id": project_id})
        with pytest.raises(ProviderError) as changed:
            core._provider_execution.execute(  # type: ignore[attr-defined]
                project_id=project_id,
                session_id=None,
                provider=provider,
                request=request,
                before_provider=mutate_request,
            )
        assert changed.value.code == "PRIVACY_PAYLOAD_CHANGED"
        assert changed.value.message == "The reasoning payload changed after validation; retry."
        assert changed.value.details == {"task_type": "teach_question"}
        assert widened_text not in json.dumps(changed.value.details)
        assert provider.call_count == 0

        manifest_events = [
            event for event in events if event.get("event") == "privacy.remote_context_manifest"
        ]
        assert len(manifest_events) == 1
        event_payload = dict(manifest_events[0]["payload"])
        stored_manifest = {
            key: value for key, value in event_payload.items() if key != "provider_run_id"
        }
        assert widened_text not in json.dumps(event_payload, ensure_ascii=False)
        assert '"text"' not in json.dumps(event_payload, ensure_ascii=False)

        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            rows = connection.execute(
                "SELECT status, error_code, ended_at, context_manifest_json FROM provider_runs"
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["status"] == "error"
        assert rows[0]["error_code"] == "PRIVACY_PAYLOAD_CHANGED"
        assert rows[0]["ended_at"] is not None
        assert json.loads(str(rows[0]["context_manifest_json"])) == stored_manifest
    finally:
        core.close()


def test_m8_openai_adapter_submits_execution_snapshot_verbatim(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    captured_invocations: list[ProviderInvocation] = []

    class Responses:
        def create(self, **kwargs: Any) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(
                output_text=json.dumps(
                    {"question": "What tradeoff mattered?", "focus": "tradeoff"}
                ),
                usage=SimpleNamespace(input_tokens=3, output_tokens=2),
            )

    client = SimpleNamespace(responses=Responses())

    class ObservedOpenAIProvider(OpenAIReasoningProvider):
        def generate(self, invocation: ProviderInvocation) -> ReasoningResult:
            captured_invocations.append(invocation)
            return super().generate(invocation)

    provider = ObservedOpenAIProvider(
        api_key="synthetic-test-key",
        client_factory=lambda **_kwargs: client,
    )
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
    )
    request = _direct_question_request(privacy_mode="selected_context_cloud")
    canonical_payload = request.to_payload()
    canonical_serialized = json.dumps(canonical_payload, ensure_ascii=False, separators=(",", ":"))
    try:
        project_id = _project(core, "selected_context_cloud")
        _call(core, "project.acknowledge_remote_reasoning", {"project_id": project_id})
        core._provider_execution.execute(  # type: ignore[attr-defined]
            project_id=project_id,
            session_id=None,
            provider=provider,
            request=request,
        )
        assert len(captured_invocations) == 1
        submitted = calls[0]["input"][1]["content"][0]["text"]
        assert submitted == canonical_serialized
        assert submitted == captured_invocations[0].serialized_input()
        assert submitted == json.dumps(
            captured_invocations[0].to_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        assert "output_schema" not in submitted
    finally:
        core.close()


@pytest.mark.parametrize(
    ("context_class", "request_kwargs"),
    [
        (
            "audience_context",
            {
                "audience_context": (
                    {"id": "audience-1", "observations": [{"id": "observation-1"}]},
                )
            },
        ),
        ("challenge_intensity", {"challenge_intensity": "skeptical"}),
        (
            "prior_question_context",
            {"prior_question_context": ({"question_id": "prior-1", "text": "Earlier"},)},
        ),
    ],
)
def test_m8_task_context_policy_blocks_misrouted_teach_context(
    tmp_path: Path,
    context_class: str,
    request_kwargs: dict[str, Any],
) -> None:
    provider = DeterministicFakeReasoningProvider(locality="remote")
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
    )
    try:
        project_id = _project(core, "selected_context_cloud")
        _call(core, "project.acknowledge_remote_reasoning", {"project_id": project_id})
        with pytest.raises(ProviderError) as blocked:
            core._provider_execution.execute(  # type: ignore[attr-defined]
                project_id=project_id,
                session_id=None,
                provider=provider,
                request=_direct_question_request(
                    privacy_mode="selected_context_cloud", **request_kwargs
                ),
            )
        assert blocked.value.code == "PRIVACY_CONTEXT_CLASS_BLOCKED"
        assert blocked.value.details["task_type"] == "teach_question"
        assert blocked.value.details["context_class"] == context_class
        assert provider.call_count == 0
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 0
    finally:
        core.close()


def test_m8_final_guard_rejects_misrouted_remote_and_private_context(tmp_path: Path) -> None:
    provider = DeterministicFakeReasoningProvider(locality="remote")
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
    )
    try:
        local_project = _project(core, "local_only")
        with pytest.raises(ProviderError) as local_error:
            core._provider_execution.execute(  # type: ignore[attr-defined]
                project_id=local_project,
                session_id=None,
                provider=provider,
                request=_direct_question_request(),
            )
        assert local_error.value.code == "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED"
        assert provider.call_count == 0

        cloud_project = _project(core, "selected_context_cloud")
        with pytest.raises(ProviderError) as ack_error:
            core._provider_execution.execute(  # type: ignore[attr-defined]
                project_id=cloud_project,
                session_id=None,
                provider=provider,
                request=_direct_question_request(privacy_mode="selected_context_cloud"),
            )
        assert ack_error.value.code == "PRIVACY_REMOTE_ACK_REQUIRED"
        assert provider.call_count == 0

        _call(
            core,
            "project.acknowledge_remote_reasoning",
            {"project_id": cloud_project},
        )
        private_request = _direct_question_request(
            privacy_mode="selected_context_cloud",
            preferred_user_explanations=(
                {
                    "evidence_id": "private-evidence",
                    "knowledge_item_id": "private-knowledge",
                    "source_type": "user_statement",
                    "private": True,
                    "text": "private project note",
                },
            ),
        )
        with pytest.raises(ProviderError) as private_error:
            core._provider_execution.execute(  # type: ignore[attr-defined]
                project_id=cloud_project,
                session_id=None,
                provider=provider,
                request=private_request,
            )
        assert private_error.value.code == "PRIVACY_PRIVATE_CONTEXT_BLOCKED"
        assert provider.call_count == 0
        with core._storage.project_database(cloud_project) as connection:  # type: ignore[attr-defined]
            assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 0
    finally:
        core.close()


def test_m8_manifest_mismatch_fails_closed_before_provider_run(tmp_path: Path) -> None:
    provider = DeterministicFakeReasoningProvider(locality="remote")
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
    )
    try:
        project_id = _project(core, "selected_context_cloud")
        _call(core, "project.acknowledge_remote_reasoning", {"project_id": project_id})
        request = _direct_question_request(
            privacy_mode="selected_context_cloud",
            context_manifest={"private_items_sent": False},
        )
        with pytest.raises(ProviderError) as mismatch:
            core._provider_execution.execute(  # type: ignore[attr-defined]
                project_id=project_id,
                session_id=None,
                provider=provider,
                request=request,
            )
        assert mismatch.value.code == "PRIVACY_MANIFEST_MISMATCH"
        assert provider.call_count == 0
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 0
    finally:
        core.close()


def test_m8_current_project_mode_wins_over_active_session(tmp_path: Path) -> None:
    provider = DeterministicFakeReasoningProvider(locality="remote")
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
    )
    try:
        project_id = _project(core, "selected_context_cloud")
        _call(core, "project.acknowledge_remote_reasoning", {"project_id": project_id})
        _seed_source(core, project_id)
        session_id = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "teach"})["session"][
                "id"
            ]
        )
        _call(
            core,
            "project.update_settings",
            {"project_id": project_id, "privacy_mode": "local_only"},
        )
        prompt = _call(
            core,
            "teach.next_prompt",
            {"project_id": project_id, "session_id": session_id},
        )
        assert prompt["route"] == "retrieval_only"
        assert provider.call_count == 0
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 0
    finally:
        core.close()


def test_m8_retryable_provider_failure_can_recover_and_auth_failure_stays_blocked(
    tmp_path: Path,
) -> None:
    provider = DeterministicFakeReasoningProvider(locality="local", failure_code="PROVIDER_TIMEOUT")
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
    )
    try:
        project_id = _project(core, "local_only")
        _seed_source(core, project_id)
        first_session = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "teach"})["session"][
                "id"
            ]
        )
        first_prompt = _call(
            core,
            "teach.next_prompt",
            {"project_id": project_id, "session_id": first_session},
        )
        assert first_prompt["reasoning"]["status"] == "fallback"
        status = _call(core, "provider.status", {})["provider"]["health"]
        assert status["status"] == "unavailable"
        assert status["error_code"] == "PROVIDER_TIMEOUT"
        assert status["retryable"] is True

        provider.failure_code = None
        second_session = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "teach"})["session"][
                "id"
            ]
        )
        second_prompt = _call(
            core,
            "teach.next_prompt",
            {"project_id": project_id, "session_id": second_session},
        )
        assert second_prompt["reasoning"]["status"] == "ready"
        assert _call(core, "provider.status", {})["provider"]["health"]["status"] == "ready"

        provider.failure_code = "PROVIDER_AUTH_FAILED"
        third_session = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "teach"})["session"][
                "id"
            ]
        )
        _call(
            core,
            "teach.next_prompt",
            {"project_id": project_id, "session_id": third_session},
        )
        auth_status = _call(core, "provider.status", {})["provider"]["health"]
        assert auth_status["status"] == "auth_failed"
        assert auth_status["retryable"] is False
        calls_after_auth = provider.call_count
        provider.failure_code = None
        fourth_session = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "teach"})["session"][
                "id"
            ]
        )
        blocked_prompt = _call(
            core,
            "teach.next_prompt",
            {"project_id": project_id, "session_id": fourth_session},
        )
        assert blocked_prompt["reasoning"]["route"] == "retrieval_only"
        assert provider.call_count == calls_after_auth

        provider_test = _call(core, "provider.test", {})
        assert provider_test["status"] == "ready"
        assert _call(core, "provider.status", {})["provider"]["health"]["status"] == "ready"
    finally:
        core.close()


class _SlowProvider(DeterministicFakeReasoningProvider):
    def __init__(self) -> None:
        super().__init__(locality="local")
        self.started = threading.Event()
        self.release = threading.Event()

    def generate(self, request: ReasoningRequest) -> ReasoningResult:
        self.started.set()
        self.release.wait(1.0)
        return super().generate(request)


def test_m8_timeout_finalizes_once_and_keeps_provider_call_outside_transaction(
    tmp_path: Path,
) -> None:
    provider = _SlowProvider()
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
    )
    try:
        project_id = _project(core, "local_only")
        with pytest.raises(ProviderError) as timeout:
            core._provider_execution.execute(  # type: ignore[attr-defined]
                project_id=project_id,
                session_id=None,
                provider=provider,
                request=_direct_question_request(latency_budget_ms=50),
            )
        assert provider.started.is_set()
        assert timeout.value.code == "PROVIDER_TIMEOUT"
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            row = connection.execute(
                "SELECT status, error_code, ended_at FROM provider_runs"
            ).fetchone()
            count = connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0]
        assert count == 1
        assert row["status"] == "error"
        assert row["error_code"] == "PROVIDER_TIMEOUT"
        assert row["ended_at"] is not None
        provider.release.set()
        sleep(0.05)
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 1
    finally:
        provider.release.set()
        core.close()


class _BlockingProvider(DeterministicFakeReasoningProvider):
    def __init__(self) -> None:
        super().__init__(locality="local")
        self.started = threading.Event()
        self.release = threading.Event()

    def generate(self, request: ReasoningRequest) -> ReasoningResult:
        self.started.set()
        self.release.wait(5.0)
        return super().generate(request)


def test_m8_logical_live_cancel_finalizes_provider_run_as_cancelled(tmp_path: Path) -> None:
    provider = _BlockingProvider()
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
    )
    try:
        project_id = _project(core, "local_only")
        _seed_source(core, project_id)
        session_id = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "live_assist"})[
                "session"
            ]["id"]
        )
        assist = _call(
            core,
            "assist.request",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question": "Explain the warm standby ownership boundary.",
            },
        )
        assert provider.started.wait(5.0)
        _call(
            core,
            "assist.cancel",
            {
                "project_id": project_id,
                "session_id": session_id,
                "assist_id": assist["assist_id"],
            },
        )
        assert core._assist.wait_for_idle(5.0)  # type: ignore[attr-defined]
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            row = connection.execute(
                "SELECT status, error_code FROM provider_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        assert row is not None
        assert row["status"] == "cancelled"
        assert row["error_code"] == "PROVIDER_CANCELLED"
    finally:
        provider.release.set()
        core.close()
