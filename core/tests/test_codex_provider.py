"""Deterministic Codex auth, output, drift and execution-boundary regressions."""

from __future__ import annotations

import json
import queue
import threading
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from presenter_core.providers.codex import (
    AppServer,
    CodexReasoningProvider,
    map_turn_error,
    minimal_environment,
    validate_observed_tools,
)
from presenter_core.providers.codex_policy import CODEX_MODEL, FEATURES, runtime_config
from presenter_core.providers.models import (
    ProviderError,
    ProviderInvocation,
    ReasoningRequest,
    question_output_schema,
)


def invocation(**changes):
    request = ReasoningRequest(
        task_type="teach_question",
        question=None,
        user_input=None,
        current_slide_summary=None,
        evidence=(),
        preferred_user_explanations=(),
        speaker_evidence=(),
        style_context={},
        conflict_metadata=(),
        style_policy="preserve_voice",
        privacy_mode="selected_context_cloud",
        output_schema=question_output_schema(),
        application_policy="Synthetic policy",
        latency_budget_ms=1000,
    )
    request = replace(request, **changes)
    return ProviderInvocation(request, request.serialized_input())


class FakeServer:
    version = "0.153.4"
    _closed = False
    login_result = None

    def __init__(self, *, account=None, output=None, item_type="agentMessage", complete=True):
        self.calls = []
        self.events = queue.Queue()
        self._fault = threading.Event()
        self.account = account or {"type": "chatgpt", "email": "private@example.test"}
        self.output = output or '{"question":"Why?","focus":"why_now"}'
        self.item_type = item_type
        self.complete = complete

    def inspect(self):
        self.calls.append(("inspect", {}))

    def new_thread(self, task_type="teach_question"):
        self.inspect()
        return "thread"

    def rpc(self, method, params, timeout=5):
        self.calls.append((method, params))
        if method == "account/read":
            return {"account": None if self.account == "signed_out" else self.account}
        if method == "account/login/start":
            return {
                "type": "chatgpt",
                "loginId": "private-id",
                "authUrl": "https://auth.openai.com/authorize?state=private",
            }
        if method == "turn/start":
            self.events.put(
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": "thread",
                        "item": {"type": self.item_type, "text": self.output},
                    },
                }
            )
            if self.complete:
                self.events.put(
                    {
                        "method": "turn/completed",
                        "params": {"threadId": "thread", "turn": {"status": "completed"}},
                    }
                )
            return {"turn": {"id": "turn"}}
        return {}

    def close(self):
        self._closed = True


def provider(server):
    adapter = CodexReasoningProvider()
    adapter._server = server
    return adapter


def test_payload_is_execution_serialization():
    server = FakeServer()
    packet = invocation()
    result = provider(server).generate(packet)
    assert result.output["question"] == "Why?"
    sent = next(p for m, p in server.calls if m == "turn/start")
    assert sent["input"] == [{"type": "text", "text": packet.serialized_input()}]
    assert sent["outputSchema"] == question_output_schema()
    assert sent["environments"] == []
    assert server.calls[-1][0] == "thread/unsubscribe"


def test_local_only_never_touches_server():
    server = FakeServer()
    with pytest.raises(ProviderError, match="Local Only"):
        provider(server).generate(invocation(privacy_mode="local_only"))
    assert server.calls == []


@pytest.mark.parametrize(
    "output",
    ["not JSON", '{"question":"secret"}', '{"question":"Why?","focus":"why_now","extra":true}'],
)
def test_output_validation(output):
    with pytest.raises(ProviderError):
        provider(FakeServer(output=output)).generate(invocation())


@pytest.mark.parametrize(
    "item_type", ["commandExecution", "fileChange", "webSearch", "mcpToolCall", "unknownFutureTool"]
)
def test_observed_sensitive_capability_closes_runtime(item_type):
    server = FakeServer(item_type=item_type)
    with pytest.raises(ProviderError) as error:
        provider(server).generate(invocation())
    assert error.value.code == "CODEX_ISOLATION_FAILED"
    assert server._closed


def test_native_cancellation():
    server = FakeServer(complete=False)
    adapter = provider(server)
    packet = invocation()
    errors = []

    def run():
        try:
            adapter.generate(packet)
        except ProviderError as error:
            errors.append(error.code)

    worker = threading.Thread(target=run)
    worker.start()
    for _ in range(100):
        if any(m == "turn/start" for m, _ in server.calls):
            break
        threading.Event().wait(0.005)
    adapter.cancel(packet)
    worker.join(2)
    assert errors == ["PROVIDER_CANCELLED"]
    assert any(m == "turn/interrupt" for m, _ in server.calls)


def test_timeout_interrupts():
    server = FakeServer(complete=False)
    with pytest.raises(ProviderError) as error:
        provider(server).generate(invocation(latency_budget_ms=60))
    assert error.value.code == "PROVIDER_TIMEOUT"
    assert any(m == "turn/interrupt" for m, _ in server.calls)


def test_managed_auth_only_and_safe_projection():
    server = FakeServer(account="signed_out")
    adapter = provider(server)
    with patch("presenter_core.providers.codex.webbrowser.open", return_value=True) as browser:
        status = adapter.sign_in()
    assert status["state"] == "signing_in"
    assert ("account/login/start", {"type": "chatgpt"}) in server.calls
    assert browser.call_count == 1
    assert "private" not in json.dumps(status)
    server.account = {"type": "chatgpt", "email": "private@example.test", "token": "not-returned"}
    assert adapter.auth_status()["state"] == "signed_in"
    assert "private" not in json.dumps(adapter.auth_status())
    assert adapter.sign_out()["state"] == "signed_out"
    assert ("account/logout", {}) in server.calls
    assert server._closed


@pytest.mark.parametrize("account", [{"type": "apiKey"}, {"type": "chatgptAuthTokens"}])
def test_unexpected_auth_mode_is_not_ready(account):
    assert provider(FakeServer(account=account)).auth_status()["state"] == "error"


def test_minimal_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("CODEX_HOME", "other-home")
    monkeypatch.setenv("HTTPS_PROXY", "other-proxy")
    env = minimal_environment(tmp_path)
    assert not {"OPENAI_API_KEY", "HTTPS_PROXY", "PATH"} & env.keys()
    assert Path(env["CODEX_HOME"]).is_relative_to(tmp_path)
    assert Path(env["USERPROFILE"]).is_relative_to(tmp_path)


@pytest.mark.parametrize(
    "tools",
    [
        None,
        {},
        [{"name": "shell", "type": "namespace", "tools": []}],
        [{"name": "skills", "type": "namespace", "tools": [{"type": "function", "name": "write"}]}],
    ],
)
def test_tool_drift_rejected(tools):
    with pytest.raises(ProviderError):
        validate_observed_tools(tools)


def test_config_and_instruction_drift(tmp_path):
    server = AppServer.__new__(AppServer)
    server.home = tmp_path / "home"
    server.home.mkdir()
    server.cwd = tmp_path / "empty"
    server.cwd.mkdir()
    server.config = runtime_config()
    (server.home / "config.toml").write_text(server.config)
    config = {
        "model": CODEX_MODEL,
        "model_provider": "openai",
        "project_doc_max_bytes": 0,
        "web_search": "disabled",
        "include_environment_context": False,
        "include_permissions_instructions": False,
        "include_apps_instructions": False,
        "include_collaboration_mode_instructions": False,
        "developer_instructions": "",
        "features": {k: v for k, v in FEATURES.items() if k != "apps_mcp_path_override"},
        "forced_login_method": "chatgpt",
        "cli_auth_credentials_store": "file",
        "skills": {"bundled": {"enabled": False}, "include_instructions": False},
    }
    import tomllib

    def rpc(method, params):
        if method == "config/read":
            return {
                "config": config,
                "layers": [
                    {
                        "name": {"type": "user", "file": str(server.home / "config.toml")},
                        "config": tomllib.loads(server.config),
                    }
                ],
            }
        return {"data": [{"skills": [], "errors": []}] if method == "skills/list" else []}

    with patch.object(server, "rpc", side_effect=rpc):
        server.inspect()
        config["include_environment_context"] = True
        with pytest.raises(ProviderError):
            server.inspect()


def test_selection_and_auth_ipc_rejects_credentials(tmp_path, monkeypatch):
    from presenter_core.providers.service import ProviderService
    from presenter_core.storage.service import StorageManager

    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    storage = StorageManager(tmp_path)
    service = ProviderService(storage)
    try:
        service.configure({"provider_id": "codex_chatgpt", "model_id": CODEX_MODEL})
        assert service.current_provider().id == "codex_chatgpt"
        assert service.current_provider_and_health()[1].status == "unconfigured"
        assert [p["provider_id"] for p in service.list({})["providers"] if p["enabled"]] == [
            "codex_chatgpt"
        ]
        from presenter_core.errors import CoreDomainError

        with pytest.raises(CoreDomainError):
            service.codex_auth("sign_in", {"token": "forbidden"})
        service._codex.close()
        assert service.current_provider().id == "codex_chatgpt"
    finally:
        service.close()
        storage.close()


@pytest.mark.parametrize(
    "info,code",
    [
        ("unauthorized", "PROVIDER_AUTH_FAILED"),
        ("usageLimitExceeded", "PROVIDER_QUOTA_EXCEEDED"),
        ("rateLimitExceeded", "PROVIDER_RATE_LIMITED"),
        ({"httpConnectionFailed": {"httpStatusCode": 401}}, "PROVIDER_AUTH_FAILED"),
        ("other", "PROVIDER_REQUEST_FAILED"),
    ],
)
def test_error_mapping_never_exposes_body(info, code):
    error = map_turn_error({"codexErrorInfo": info, "message": "SENSITIVE_RAW_BODY"})
    assert error.code == code
    assert "SENSITIVE" not in error.message


def test_failed_login_notification_is_safe():
    server = FakeServer(account="signed_out")
    adapter = provider(server)
    adapter._login_id = "attempt"
    server.login_result = ("attempt", False)
    assert adapter.auth_status() == {
        "state": "error",
        "error_code": "CODEX_LOGIN_FAILED",
        "runtime_version": "0.153.4",
    }


@pytest.mark.parametrize("kind", ["oversize", "server_request", "invalid_json", "eof"])
def test_untrusted_transport_frames_fail_closed(kind):
    import io
    from types import SimpleNamespace

    from presenter_core.providers.codex import MAX_FRAME

    frame = {
        "oversize": b"x" * (MAX_FRAME + 1),
        "server_request": b'{"id":1,"method":"account/chatgptAuthTokens/refresh"}\n',
        "invalid_json": b"not json\n",
        "eof": b"",
    }[kind]
    server = AppServer.__new__(AppServer)
    server._closed = False
    server._fault = threading.Event()
    server.events = queue.Queue()
    terminated = []
    server.process = SimpleNamespace(
        stdout=io.BytesIO(frame), poll=lambda: None, terminate=lambda: terminated.append(True)
    )
    server._read()
    assert server._fault.is_set() and terminated == [True]
    assert server.events.empty()


@pytest.mark.parametrize("mode", ["success", "cancel", "invalid", "local_only"])
def test_execution_manifests_and_exactly_once_finalization(tmp_path, mode):
    from test_m8_privacy import _call, _direct_question_request, _project

    from presenter_core.ipc.core import CoreService
    from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter

    server = FakeServer(complete=mode != "cancel", output="broken" if mode == "invalid" else None)
    adapter = provider(server)
    adapter._signed_in = True
    core = CoreService(
        data_root=tmp_path,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=adapter,
    )
    try:
        project_id = _project(
            core, "local_only" if mode == "local_only" else "selected_context_cloud"
        )
        if mode != "local_only":
            _call(core, "project.acknowledge_remote_reasoning", {"project_id": project_id})
        request = _direct_question_request(
            privacy_mode="selected_context_cloud", latency_budget_ms=1000
        )

        def before(run_id, manifest):
            with core._storage.project_database(project_id) as connection:
                assert (
                    connection.execute(
                        "SELECT COUNT(*) FROM provider_runs WHERE id=?", (run_id,)
                    ).fetchone()[0]
                    == 1
                )
            assert manifest["bounded_context_chars"] == len(request.serialized_input())

        def execute():
            return core._provider_execution.execute(
                project_id=project_id,
                session_id=None,
                provider=adapter,
                request=request,
                before_provider=before,
                cancellation_check=lambda: mode == "cancel"
                and any(m == "turn/start" for m, _ in server.calls),
            )

        if mode == "success":
            assert execute().result.output["question"] == "Why?"
        else:
            with pytest.raises(ProviderError):
                execute()
        with core._storage.project_database(project_id) as connection:
            rows = connection.execute("SELECT status, ended_at FROM provider_runs").fetchall()
        if mode == "local_only":
            assert not rows and not server.calls
        else:
            assert len(rows) == 1 and rows[0]["ended_at"]
            assert (
                rows[0]["status"]
                == {"success": "success", "cancel": "cancelled", "invalid": "error"}[mode]
            )
    finally:
        core.close()
