from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

CORE_DIR = Path(__file__).parents[1]
FIXTURE_ROOT = Path(__file__).parents[2] / "samples" / "synthetic-deck"


def read_message(process: subprocess.Popen[str]) -> dict[str, Any]:
    assert process.stdout is not None
    line = process.stdout.readline()
    assert line, "sidecar exited before sending a protocol message"
    return json.loads(line)


def send_request(
    process: subprocess.Popen[str],
    request_id: str,
    method: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    assert process.stdin is not None
    process.stdin.write(
        json.dumps(
            {
                "protocol_version": 1,
                "type": "request",
                "request_id": request_id,
                "method": method,
                "params": params,
            }
        )
        + "\n"
    )
    process.stdin.flush()
    events: list[dict[str, Any]] = []
    while True:
        message = read_message(process)
        if message.get("type") == "event":
            events.append(message)
            continue
        if message.get("request_id") == request_id:
            return message, events


def start_sidecar(data_root: Path) -> subprocess.Popen[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(CORE_DIR)
    environment["PRESENTER_COPILOT_DATA_ROOT"] = str(data_root)
    return subprocess.Popen(
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


def test_spawned_sidecar_persists_m1_state_across_restart(tmp_path: Path) -> None:
    data_root = tmp_path / "sidecar-data"
    sources = [
        (FIXTURE_ROOT / "deck" / "presentation.pptx", "presentation"),
        (FIXTURE_ROOT / "supporting" / "cost-model.pdf", "supporting"),
        (FIXTURE_ROOT / "supporting" / "architecture-notes.md", "supporting"),
    ]
    first = start_sidecar(data_root)
    project_id = ""
    imported_ids: list[str] = []
    try:
        ready = read_message(first)
        assert ready["event"] == "core.ready"
        assert ready["payload"]["migration_status"] == "ready"
        created, _ = send_request(first, "create", "project.create", {"name": "Sidecar acceptance"})
        assert created["ok"] is True
        project_id = created["result"]["project"]["id"]
        for index, (path, kind) in enumerate(sources):
            imported, events = send_request(
                first,
                f"import-{index}",
                "source.import",
                {"project_id": project_id, "path": str(path.resolve()), "kind": kind},
            )
            assert imported["ok"] is True
            imported_ids.append(imported["result"]["document"]["id"])
            progress = [event for event in events if event["event"] == "source.import_progress"]
            assert progress
            assert all("text" not in event["payload"] for event in progress)
            assert all(str(data_root) not in json.dumps(event) for event in progress)
        shutdown, _ = send_request(first, "shutdown", "core.shutdown", {})
        assert shutdown["ok"] is True
        assert first.wait(timeout=5) == 0
    finally:
        if first.poll() is None:
            first.terminate()
            first.wait(timeout=5)

    second = start_sidecar(data_root)
    try:
        ready_again = read_message(second)
        assert ready_again["event"] == "core.ready"
        listed, _ = send_request(second, "list", "project.list", {})
        assert listed["result"]["projects"][0]["id"] == project_id
        opened, _ = send_request(second, "open", "project.open", {"project_id": project_id})
        assert opened["result"]["project"]["name"] == "Sidecar acceptance"
        sources_response, _ = send_request(
            second,
            "sources",
            "source.list",
            {"project_id": project_id},
        )
        assert len(sources_response["result"]["sources"]) == 3
        preview, _ = send_request(
            second,
            "preview",
            "source.preview",
            {"project_id": project_id, "document_id": imported_ids[1], "limit": 1},
        )
        assert preview["result"]["units"][0]["provenance"]["label"] == "cost-model.pdf p.1"
        reindexed, _ = send_request(
            second,
            "reindex",
            "source.reindex",
            {"project_id": project_id, "document_id": imported_ids[0]},
        )
        assert reindexed["ok"] is True
        deleted, _ = send_request(
            second,
            "delete-source",
            "source.delete",
            {"project_id": project_id, "document_id": imported_ids[2]},
        )
        assert deleted["result"]["deleted"] is True
        delete_project, _ = send_request(
            second,
            "delete-project",
            "project.delete",
            {"project_id": project_id},
        )
        assert delete_project["result"]["deleted"] is True
        shutdown, _ = send_request(second, "shutdown-again", "core.shutdown", {})
        assert shutdown["ok"] is True
        assert second.wait(timeout=5) == 0
    finally:
        if second.poll() is None:
            second.terminate()
            second.wait(timeout=5)
