from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from presenter_core.ipc.core import CoreService


def request(request_id: str, method: str, *, protocol_version: int = 1) -> dict[str, Any]:
    return {
        "protocol_version": protocol_version,
        "type": "request",
        "request_id": request_id,
        "method": method,
        "params": {},
    }


def test_shared_examples_have_protocol_v1_envelopes() -> None:
    fixture_path = Path(__file__).parents[2] / "shared" / "schemas" / "protocol-v1.examples.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert fixture["protocol_version"] == 1
    for message in fixture["messages"]:
        assert message["protocol_version"] == 1
        assert message["type"] in {"request", "response", "event"}

    ready = CoreService().ready_event()
    assert ready == fixture["messages"][1]


def test_core_hello_exposes_only_milestone_zero_capabilities() -> None:
    response = CoreService().handle_message(request("hello", "core.hello"))

    assert response["ok"] is True
    result = response["result"]
    assert result["protocol_version"] == 1
    assert result["core_version"] == "0.1.0"
    assert result["capabilities"]["methods"] == ["core.hello", "core.health", "core.shutdown"]
    assert result["capabilities"]["events"] == ["core.ready", "core.error"]
    assert result["adapters"] == []
    assert result["migration_status"] == "not_required"


def test_core_health_is_successful() -> None:
    response = CoreService(clock=lambda: 10.0).handle_message(
        request("00000000-0000-0000-0000-000000000002", "core.health")
    )

    assert response == {
        "protocol_version": 1,
        "type": "response",
        "request_id": "00000000-0000-0000-0000-000000000002",
        "ok": True,
        "result": {
            "status": "ok",
            "ready": True,
            "protocol_version": 1,
            "core_version": "0.1.0",
            "uptime_ms": 0,
        },
    }

    fixture_path = Path(__file__).parents[2] / "shared" / "schemas" / "protocol-v1.examples.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert response == fixture["messages"][4]


def test_core_shutdown_marks_server_for_clean_exit() -> None:
    core = CoreService()
    response = core.handle_message(request("shutdown", "core.shutdown"))

    assert response["ok"] is True
    assert response["result"] == {"status": "shutting_down"}
    assert core.shutdown_requested is True


def test_malformed_json_returns_structured_error_without_raising() -> None:
    response = CoreService().handle_line('{"protocol_version":')

    assert response["ok"] is False
    assert response["request_id"] is None
    assert response["error"]["code"] == "MALFORMED_JSON"


def test_unknown_method_returns_structured_error() -> None:
    response = CoreService().handle_message(request("unknown", "core.nope"))

    assert response["request_id"] == "unknown"
    assert response["ok"] is False
    assert response["error"] == {
        "code": "METHOD_NOT_FOUND",
        "message": "Unknown method: core.nope",
        "retryable": False,
        "details": {
            "method": "core.nope",
            "supported_methods": ["core.hello", "core.health", "core.shutdown"],
        },
    }


def test_incompatible_protocol_is_rejected_and_request_id_is_preserved() -> None:
    response = CoreService().handle_message(request("version", "core.health", protocol_version=99))

    assert response["request_id"] == "version"
    assert response["ok"] is False
    assert response["error"]["code"] == "PROTOCOL_VERSION_UNSUPPORTED"
