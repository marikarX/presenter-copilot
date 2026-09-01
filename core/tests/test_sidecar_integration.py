from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

CORE_DIR = Path(__file__).parents[1]


def read_message(process: subprocess.Popen[str]) -> dict[str, Any]:
    assert process.stdout is not None
    line = process.stdout.readline()
    assert line, "sidecar exited before sending a protocol message"
    return json.loads(line)


def write_request(process: subprocess.Popen[str], request_id: str, method: str) -> None:
    assert process.stdin is not None
    process.stdin.write(
        json.dumps(
            {
                "protocol_version": 1,
                "type": "request",
                "request_id": request_id,
                "method": method,
                "params": {},
            }
        )
        + "\n"
    )
    process.stdin.flush()


def send_request(process: subprocess.Popen[str], request_id: str, method: str) -> dict[str, Any]:
    write_request(process, request_id, method)
    return read_message(process)


def test_real_sidecar_lifecycle_round_trip() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(CORE_DIR)
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "presenter_core"],
        cwd=CORE_DIR,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )

    try:
        ready = read_message(process)
        assert ready["type"] == "event"
        assert ready["event"] == "core.ready"
        assert ready["payload"]["protocol_version"] == 1

        write_request(process, "unknown", "core.nope")
        error_event = read_message(process)
        assert error_event["event"] == "core.error"
        assert error_event["payload"]["request_id"] == "unknown"
        unknown = read_message(process)
        assert unknown["request_id"] == "unknown"
        assert unknown["error"]["code"] == "METHOD_NOT_FOUND"

        hello = send_request(process, "hello", "core.hello")
        assert hello["ok"] is True
        assert hello["request_id"] == "hello"

        health = send_request(process, "health", "core.health")
        assert health["ok"] is True
        assert health["result"]["status"] == "ok"

        shutdown = send_request(process, "shutdown", "core.shutdown")
        assert shutdown["ok"] is True
        assert shutdown["result"] == {"status": "shutting_down"}

        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
