from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from presenter_core.ipc.core import CoreService
from presenter_core.ipc.protocol import SUPPORTED_METHODS


def request(request_id: str, method: str, *, protocol_version: int = 1) -> dict[str, Any]:
    return {
        "protocol_version": protocol_version,
        "type": "request",
        "request_id": request_id,
        "method": method,
        "params": {},
    }


def test_shared_examples_have_protocol_v1_envelopes(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parents[2] / "shared" / "schemas" / "protocol-v1.examples.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert fixture["protocol_version"] == 1
    for message in fixture["messages"]:
        assert message["protocol_version"] == 1
        assert message["type"] in {"request", "response", "event"}

    core = CoreService(data_root=tmp_path / "data")
    ready = core.ready_event()
    core.close()
    assert ready == fixture["messages"][1]


def test_core_hello_exposes_implemented_capabilities(tmp_path: Path) -> None:
    core = CoreService(data_root=tmp_path / "data")
    response = core.handle_message(request("hello", "core.hello"))
    core.close()

    assert response["ok"] is True
    result = response["result"]
    assert result["protocol_version"] == 1
    assert result["core_version"] == "0.1.0"
    assert "project.create" in result["capabilities"]["methods"]
    assert "source.import" in result["capabilities"]["methods"]
    assert "search.lexical" in result["capabilities"]["methods"]
    assert {
        "transcript.list_speakers",
        "transcript.map_speaker",
        "transcript.unmap_speaker",
        "audience.create",
        "audience.update",
        "audience.list",
        "audience.delete",
        "audience.extract_observations",
        "audience.list_observations",
        "audience.accept_observation",
        "audience.reject_observation",
        "audience.create_observation",
        "audience.update_observation",
        "audience.delete_observation",
        "audience.build_context",
    }.issubset(result["capabilities"]["methods"])
    assert "source.import_progress" in result["capabilities"]["events"]
    assert result["adapters"] == [
        "pdf.pypdf",
        "pptx.python-pptx",
        "text.stdlib",
        "transcript.vtt",
        "transcript.srt",
        "transcript.named-text",
        "transcript.json",
        "audience.observable-patterns",
        "embedding.fastembed",
        "retrieval.numpy",
        "retrieval.hybrid",
        "retrieval.lexical",
        "reasoning.fake",
        "provider.openai.responses",
    ]
    assert result["migration_status"] == "ready"
    assert result["storage"] == {"app_schema_version": 2, "project_schema_version": 4}


def test_core_health_is_successful(tmp_path: Path) -> None:
    core = CoreService(clock=lambda: 10.0, data_root=tmp_path / "data")
    response = core.handle_message(request("00000000-0000-0000-0000-000000000002", "core.health"))
    core.close()

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


def test_core_shutdown_marks_server_for_clean_exit(tmp_path: Path) -> None:
    core = CoreService(data_root=tmp_path / "data")
    response = core.handle_message(request("shutdown", "core.shutdown"))

    assert response["ok"] is True
    assert response["result"] == {"status": "shutting_down"}
    assert core.shutdown_requested is True


def test_malformed_json_returns_structured_error_without_raising(tmp_path: Path) -> None:
    core = CoreService(data_root=tmp_path / "data")
    response = core.handle_line('{"protocol_version":')
    core.close()

    assert response["ok"] is False
    assert response["request_id"] is None
    assert response["error"]["code"] == "MALFORMED_JSON"


def test_unknown_method_returns_structured_error(tmp_path: Path) -> None:
    core = CoreService(data_root=tmp_path / "data")
    response = core.handle_message(request("unknown", "core.nope"))
    core.close()

    assert response["request_id"] == "unknown"
    assert response["ok"] is False
    assert response["error"] == {
        "code": "METHOD_NOT_FOUND",
        "message": "Unknown method: core.nope",
        "retryable": False,
        "details": {
            "method": "core.nope",
            "supported_methods": [
                *SUPPORTED_METHODS,
            ],
        },
    }


def test_incompatible_protocol_is_rejected_and_request_id_is_preserved(tmp_path: Path) -> None:
    core = CoreService(data_root=tmp_path / "data")
    response = core.handle_message(request("version", "core.health", protocol_version=99))
    core.close()

    assert response["request_id"] == "version"
    assert response["ok"] is False
    assert response["error"]["code"] == "PROTOCOL_VERSION_UNSUPPORTED"
