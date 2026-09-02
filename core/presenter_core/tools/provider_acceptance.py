"""Opt-in live-provider acceptance over synthetic, non-confidential content."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from presenter_core.ipc.core import CoreService
from presenter_core.providers.models import ProviderError
from presenter_core.providers.openai import OpenAIReasoningProvider
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def _call(
    core: CoreService,
    request_id: str,
    method: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": request_id,
            "method": method,
            "params": params,
        }
    )
    if response.get("ok") is not True:
        error = response.get("error", {})
        if isinstance(error, dict):
            raise ProviderError(
                str(error.get("code", "PROVIDER_REQUEST_FAILED")),
                "The provider acceptance request failed.",
            )
        raise ProviderError("PROVIDER_REQUEST_FAILED", "The provider acceptance request failed.")
    result = response.get("result")
    if not isinstance(result, dict):
        raise ProviderError("PROVIDER_MALFORMED_OUTPUT", "The core returned an invalid result.")
    return cast(dict[str, Any], result)


def _provider_run_metadata(core: CoreService, project_id: str, session_id: str) -> dict[str, Any]:
    with core._storage.project_database(project_id) as connection:
        rows = connection.execute(
            """
            SELECT provider_id, latency_ms, input_token_count, output_token_count
            FROM provider_runs
            WHERE session_id = ? AND status = 'success'
            ORDER BY started_at DESC, id DESC
            LIMIT 2
            """,
            (session_id,),
        ).fetchall()
    return {
        "provider_id": str(rows[0]["provider_id"]) if rows else "openai",
        "latency_ms": [row["latency_ms"] for row in rows],
        "input_token_count": [row["input_token_count"] for row in rows],
        "output_token_count": [row["output_token_count"] for row in rows],
    }


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "Not executed: OPENAI_API_KEY was not available. No alternate credential path was used."
        )
        return 0

    provider = OpenAIReasoningProvider()
    if provider.health().status != "ready":
        print(
            json.dumps(
                {"status": "not_executed", "reason": "OPENAI_API_KEY provider was not ready."},
                sort_keys=True,
            )
        )
        return 1

    repository_root = Path(__file__).parents[3]
    core: CoreService | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="presenter-copilot-m3-provider-") as temporary:
            core = CoreService(
                data_root=Path(temporary) / "data",
                embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
                reasoning_provider=provider,
            )
            project = _call(
                core,
                "create",
                "project.create",
                {
                    "name": "Synthetic M3 provider acceptance",
                    "privacy_mode": "selected_context_cloud",
                },
            )["project"]
            project_id = str(project["id"])
            _call(
                core,
                "acknowledge",
                "project.acknowledge_remote_reasoning",
                {"project_id": project_id},
            )
            session = _call(
                core,
                "start",
                "session.start",
                {"project_id": project_id, "mode": "teach"},
            )["session"]
            session_id = str(session["id"])
            question = _call(
                core,
                "question",
                "teach.next_prompt",
                {"project_id": project_id, "session_id": session_id},
            )
            candidate = _call(
                core,
                "candidate",
                "teach.submit_text",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "text": "The synthetic rehearsal answer favors a smaller rollback surface.",
                },
            )["candidate"]
            metadata = _provider_run_metadata(core, project_id, session_id)
            report = {
                "status": "passed" if isinstance(candidate, dict) else "failed",
                "timestamp": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "git_sha": _git_sha(repository_root),
                "provider_id": metadata["provider_id"],
                "model_id": provider.model_id,
                "question_schema_pass": isinstance(question.get("question"), str)
                and isinstance(question.get("focus"), str),
                "candidate_schema_pass": isinstance(candidate, dict)
                and isinstance(candidate.get("proposed_text"), str),
                "latency_ms": metadata["latency_ms"],
                "input_token_count": metadata["input_token_count"],
                "output_token_count": metadata["output_token_count"],
            }
            return _write_report(report)
    except ProviderError as error:
        print(json.dumps({"status": "failed", "code": error.code}, sort_keys=True), file=sys.stderr)
        return 1
    except Exception as error:  # pragma: no cover - live service boundary
        print(
            json.dumps({"status": "failed", "code": type(error).__name__}, sort_keys=True),
            file=sys.stderr,
        )
        return 1
    finally:
        if core is not None:
            core.close()


def _write_report(report: dict[str, Any]) -> int:
    output = Path(__file__).parents[3] / "artifacts" / "m3-provider-acceptance.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


def _git_sha(repository_root: Path) -> str | None:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


if __name__ == "__main__":
    raise SystemExit(main())
