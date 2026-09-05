"""E09 transport and execution tests use only a disposable loopback HTTP server."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import sleep
from typing import Any

import pytest
from test_m8_privacy import _call, _direct_question_request, _error, _project, _seed_source

from presenter_core.ipc.core import CoreService
from presenter_core.providers.codex import CodexReasoningProvider
from presenter_core.providers.local import LocalReasoningProvider, validate_endpoint
from presenter_core.providers.models import ProviderError, ProviderInvocation
from presenter_core.providers.router import ReasoningRouter
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


@pytest.fixture
def server():
    state: dict[str, Any] = {
        "status": 200,
        "delay": 0,
        "body": json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "question": "Why this decision?",
                                    "focus": "decision_rationale",
                                }
                            )
                        },
                    }
                ],
            }
        ).encode(),
        "calls": [],
        "started": threading.Event(),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            state["calls"].append(
                (
                    self.path,
                    dict(self.headers),
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                )
            )
            state["started"].set()
            sleep(state["delay"])
            self.send_response(state["status"])
            self.send_header("Content-Length", str(len(state["body"])))
            self.send_header("Location", "https://example.com/forbidden")
            self.end_headers()
            try:
                self.wfile.write(state["body"])
            except OSError:
                pass

        def log_message(self, *_args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    state["endpoint"] = f"http://127.0.0.1:{httpd.server_port}/v1"
    yield state
    httpd.shutdown()
    httpd.server_close()
    worker.join(2)


@pytest.fixture
def core(tmp_path: Path):
    service = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=4)
    )
    yield service
    service.close()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com/v1",
        "file:///tmp/model",
        "ftp://127.0.0.1",
        "http://0.0.0.0",
        "http://169.254.169.254",
        "http://100.64.0.1",
        "http://224.0.0.1",
        "http://[::]",
        "http://[::ffff:127.0.0.1]",
        "http://[fe80::1%25eth0]",
        "http://localhost.evil/v1",
        "http://user:password@127.0.0.1/v1",
        "http://127.0.0.1/v1?token=secret",
        "http://127.0.0.1/#fragment",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1/../v1",
        "http://127.0.0.1\\@example.com",
        " http://localhost",
        "http://localhost\n",
        "http://2130706433",
        "http://127.1",
        "",
        None,
    ],
)
def test_endpoint_rejected(endpoint):
    with pytest.raises(ProviderError, match="HTTP") as error:
        validate_endpoint(endpoint)
    assert error.value.code == "PROVIDER_ENDPOINT_INVALID"


@pytest.mark.parametrize(
    "endpoint,loopback",
    [
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:1234/v1", True),
        ("http://[::1]/v1", True),
        ("https://192.168.1.2/v1", False),
        ("http://10.0.0.2/v1", False),
        ("https://[fd00::1]/v1", False),
    ],
)
def test_endpoint_accepted(endpoint, loopback):
    normalized, actual = validate_endpoint(endpoint)
    assert actual is loopback
    assert "localhost" not in normalized


def configure(core, endpoint):
    return _call(
        core,
        "provider.configure",
        {
            "provider_id": "local_openai",
            "enabled": True,
            "model_id": "fixture-model",
            "endpoint": endpoint,
        },
    )


def test_success_configuration_health_and_no_renderer_credential(core, server, monkeypatch):
    monkeypatch.setenv("PRESENTER_LOCAL_API_KEY", "local-secret-fixture")
    monkeypatch.setenv("OPENAI_API_KEY", "cloud-secret-fixture")
    monkeypatch.setenv("HTTP_PROXY", "http://192.0.2.1:9")
    configured = configure(core, server["endpoint"])
    assert configured["provider"]["health"]["error_code"] == "PROVIDER_NOT_TESTED"
    result = _call(core, "provider.test", {"provider_id": "local_openai"})
    status = _call(core, "provider.status", {})
    providers = _call(core, "provider.list", {})["providers"]
    assert result["status"] == "ready"
    assert status["provider"]["provider_id"] == "local_openai"
    assert providers[0]["health"]["status"] == "ready"
    assert sum(p["enabled"] for p in providers) == 1
    assert "secret-fixture" not in json.dumps([result, status, providers, configured])
    with core._storage.app_database() as db:
        assert "secret-fixture" not in str(
            [tuple(row) for row in db.execute("SELECT * FROM provider_configurations")]
        )
    path, headers, body = server["calls"][0]
    assert path == "/v1/chat/completions"
    assert headers["Authorization"] == "Bearer local-secret-fixture"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["max_tokens"] == 2048
    assert "tools" not in body
    for field in ("api_key", "credential", "access_token"):
        assert _error(core, "provider.configure", {"provider_id": "local_openai", field: "secret"})


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"{}",
        b"x" * 65537,
        json.dumps(
            {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}
        ).encode(),
        json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}).encode(),
    ],
    ids=["non-json", "missing-choices", "oversized", "truncated", "invalid-schema"],
)
def test_malformed_output(core, server, body):
    configure(core, server["endpoint"])
    server["body"] = body
    error = _error(core, "provider.test", {})
    assert error["code"] == "PROVIDER_MALFORMED_OUTPUT"
    assert _call(core, "provider.status", {})["provider"]["health"]["status"] == "unavailable"


@pytest.mark.parametrize(
    "status,code",
    [
        (302, "PROVIDER_UNAVAILABLE"),
        (503, "PROVIDER_UNAVAILABLE"),
        (401, "PROVIDER_AUTH_FAILED"),
        (429, "PROVIDER_RATE_LIMITED"),
    ],
)
def test_safe_http_errors_without_redirect(core, server, status, code):
    configure(core, server["endpoint"])
    server["status"] = status
    server["body"] = b"private provider error"
    error = _error(core, "provider.test", {})
    assert error["code"] == code
    assert "private provider error" not in json.dumps(error)
    assert len(server["calls"]) == 1


@pytest.mark.parametrize(
    "endpoint,mode,ack,allowed",
    [
        ("http://127.0.0.1/v1", "local_only", False, True),
        ("http://192.168.1.2/v1", "local_only", True, False),
        ("http://192.168.1.2/v1", "selected_context_cloud", False, False),
        ("http://192.168.1.2/v1", "selected_context_cloud", True, True),
    ],
)
def test_privacy_router(endpoint, mode, ack, allowed):
    provider = LocalReasoningProvider(endpoint=endpoint, model_id="fixture")
    decision = ReasoningRouter().decide(
        task_type="teach_question",
        privacy_mode=mode,
        remote_acknowledged=ack,
        provider=provider,
        provider_health=provider.health(),
    )
    assert (decision.route == "local_reasoning") is allowed
    assert provider.locality == "local"


def test_lan_cannot_bypass_execution_authority(core):
    provider = LocalReasoningProvider(endpoint="http://192.168.1.2/v1", model_id="fixture")
    project = _project(core, "local_only")
    with pytest.raises(ProviderError) as error:
        core._provider_execution.execute(
            project_id=project,
            session_id=None,
            provider=provider,
            request=_direct_question_request(),
        )
    assert error.value.code == "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED"


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_cancellation_finalizes_once(core, server, cancel):
    configure(core, server["endpoint"])
    server["delay"] = 0.25
    project = _project(core, "local_only")
    with pytest.raises(ProviderError) as error:
        core._provider_execution.execute(
            project_id=project,
            session_id=None,
            provider=core._providers.current_provider(),
            request=_direct_question_request(latency_budget_ms=1000 if cancel else 50),
            cancellation_check=server["started"].is_set if cancel else None,
        )
    assert error.value.code == ("PROVIDER_CANCELLED" if cancel else "PROVIDER_TIMEOUT")
    sleep(0.3)
    with core._storage.project_database(project) as db:
        rows = db.execute("SELECT status, error_code, ended_at FROM provider_runs").fetchall()
    assert len(rows) == 1
    assert rows[0]["error_code"] == error.value.code
    assert rows[0]["ended_at"]


def test_unavailable_retrieval_fallback_no_cloud_escalation(core, monkeypatch):
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    configure(core, f"http://127.0.0.1:{port}/v1")
    project = _project(core, "local_only")
    _seed_source(core, project)
    session = _call(core, "session.start", {"project_id": project, "mode": "teach"})["session"][
        "id"
    ]
    prompt = _call(core, "teach.next_prompt", {"project_id": project, "session_id": session})
    assert prompt["reasoning"]["route"] == "retrieval_only"
    assert _call(core, "provider.status", {})["provider"]["provider_id"] == "local_openai"
    assert _call(core, "provider.status", {})["provider"]["health"]["status"] == "unavailable"


def test_codex_boundary_is_inert(core, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "not-entitlement")
    provider = CodexReasoningProvider()
    assert not provider.health().configured
    assert provider.leaves_machine
    with pytest.raises(ProviderError) as error:
        provider.generate(
            ProviderInvocation(request=_direct_question_request(), serialized_input_text="{}")
        )
    assert error.value.code == "PROVIDER_UNSUPPORTED"
    assert _error(core, "provider.configure", {"provider_id": "codex", "model_id": "fixture"})
    assert _call(core, "provider.status", {"provider_id": "codex"})["provider"]["enabled"] is False


def test_lan_manifest_precedes_transport_and_private_context_is_blocked(core, server, monkeypatch):
    import http.client
    from urllib.parse import urlsplit

    # Simulate the LAN transport on loopback; no LAN host is contacted by this test.
    original = http.client.HTTPConnection
    port = urlsplit(server["endpoint"]).port
    monkeypatch.setattr(
        http.client,
        "HTTPConnection",
        lambda *_args, **kwargs: original("127.0.0.1", port, **kwargs),
    )
    configure(core, "http://192.168.1.2/v1")
    project = _project(core, "selected_context_cloud")
    _call(core, "project.acknowledge_remote_reasoning", {"project_id": project})
    provider = core._providers.current_provider()
    request = _direct_question_request(privacy_mode="selected_context_cloud")
    before: list[dict[str, Any]] = []
    core._provider_execution.execute(
        project_id=project,
        session_id=None,
        provider=provider,
        request=request,
        before_provider=lambda _id, manifest: before.append(manifest),
    )
    assert before
    assert server["calls"][0][2]["messages"][1]["content"] == request.serialized_input()
    with core._storage.project_database(project) as db:
        row = db.execute("SELECT status, context_manifest_json FROM provider_runs").fetchone()
    assert row["status"] == "success"
    manifest = json.loads(row["context_manifest_json"])
    assert manifest["private_items_sent"] is False
    assert "application_policy" in manifest["classes_sent"]
    with pytest.raises(ProviderError) as error:
        core._provider_execution.execute(
            project_id=project,
            session_id=None,
            provider=provider,
            request=_direct_question_request(
                privacy_mode="selected_context_cloud",
                preferred_user_explanations=({"private": True, "text": "private fixture"},),
            ),
        )
    assert error.value.code == "PRIVACY_PRIVATE_CONTEXT_BLOCKED"
    assert len(server["calls"]) == 1


def test_shutdown_closes_active_transport(core, server):
    configure(core, server["endpoint"])
    provider = core._providers.current_provider()
    server["delay"] = 1
    failures = []

    def run():
        try:
            provider.generate(
                ProviderInvocation(request=_direct_question_request(), serialized_input_text="{}")
            )
        except ProviderError as error:
            failures.append(error.code)

    worker = threading.Thread(target=run)
    worker.start()
    assert server["started"].wait(2)
    transports = tuple(provider._connections)
    assert transports
    provider.close()
    # Windows select can take the remaining socket budget to observe a close
    # from another thread. Shutdown itself must not wait for that worker.
    worker.join(1.5)
    assert not worker.is_alive()
    assert all(transport.fileno() == -1 for transport in transports)
    assert failures == ["PROVIDER_CANCELLED"]


def test_reconfiguration_discards_old_health_and_preserves_selection(core, server):
    configure(core, server["endpoint"])
    old = core._providers.current_provider()
    configure(core, "http://127.0.0.1:9/v1")
    core._providers.record_success(old)
    assert (
        _call(core, "provider.status", {})["provider"]["health"]["error_code"]
        == "PROVIDER_NOT_TESTED"
    )
    _call(
        core,
        "provider.configure",
        {"provider_id": "openai", "model_id": "fixture", "enabled": True},
    )
    providers = _call(core, "provider.list", {})["providers"]
    assert [p["provider_id"] for p in providers if p["enabled"]] == ["openai"]
