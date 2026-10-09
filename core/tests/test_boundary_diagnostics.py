from __future__ import annotations

import json
import uuid

import pytest

from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


@pytest.mark.parametrize(
    "error,cause",
    [
        (MemoryError, "MEMORY_ALLOCATION_FAILED"),
        (OSError, "UNEXPECTED_IO_ERROR"),
        (ValueError, "UNEXPECTED_EXCEPTION"),
    ],
)
def test_unexpected_request_cause_is_logged_without_exception_content(
    tmp_path, monkeypatch, error, cause
):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:

        def fail(*_args):
            raise error("secret presentation content and credentials")

        monkeypatch.setattr(core, "_dispatch", fail)
        response = core.handle_message(
            {
                "protocol_version": 1,
                "type": "request",
                "request_id": str(uuid.uuid4()),
                "method": "core.health",
                "params": {},
            }
        )
        assert response["error"]["code"] == "INTERNAL_ERROR"
        assert response["error"]["details"] == {}
        log = (tmp_path / "data/logs/core.jsonl").read_text(encoding="utf-8")
        event = json.loads(log.splitlines()[-1])
        assert event["cause_code"] == cause and event["operation"] == "core.health"
        assert "secret presentation" not in log and "credentials" not in log
    finally:
        core.close()
