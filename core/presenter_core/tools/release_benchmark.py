"""Aggregate metadata-only release benchmark for CPU and RTX evidence runs."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from presenter_core import CORE_VERSION
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter

REPOSITORY_ROOT = Path(__file__).parents[3]
SAFE_HARDWARE_TEXT = re.compile(r"[^A-Za-z0-9 ._()+\-/]", re.ASCII)


def _call(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": f"m9-benchmark-{method}",
            "method": method,
            "params": params,
        }
    )
    if response.get("ok") is not True:
        raise RuntimeError("benchmark request failed")
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("benchmark result was invalid")
    return result


def _git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def _system_ram_bytes() -> int | None:
    if os.name != "nt":
        return None
    try:
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    return None


def _gpu_name() -> str | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines():
        value = SAFE_HARDWARE_TEXT.sub("", line.strip())[:160].strip()
        if value:
            return value
    return None


def _hardware_profile(requested: str, gpu_name: str | None) -> str:
    if requested != "auto":
        return requested
    return "rtx_reference" if gpu_name else "cpu_only"


def _timed(operation: Callable[[], object]) -> float:
    started = perf_counter()
    operation()
    return round((perf_counter() - started) * 1000, 3)


def _deterministic_smoke() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="presenter-copilot-m9-benchmark-") as temporary:
        started = perf_counter()
        core = CoreService(
            data_root=Path(temporary) / "data",
            embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        )
        startup_ms = round((perf_counter() - started) * 1000, 3)
        try:
            project_id: str | None = None
            project_create_ms = _timed(
                lambda: _call(core, "project.create", {"name": "M9 benchmark"})
            )
            # The project id is read from a second bounded response only; no
            # source text or user data is included in the report.
            project = _call(core, "project.list", {}).get("projects")
            if isinstance(project, list) and project and isinstance(project[0], dict):
                value = project[0].get("id")
                if isinstance(value, str):
                    project_id = value
            if project_id is None:
                raise RuntimeError("benchmark project was not created")
            source = (
                REPOSITORY_ROOT
                / "samples"
                / "synthetic-deck"
                / "supporting"
                / "architecture-notes.md"
            )
            import_ms = _timed(
                lambda: _call(
                    core,
                    "source.import",
                    {"project_id": project_id, "path": str(source), "kind": "supporting"},
                )
            )
            index_ms = _timed(lambda: _call(core, "retrieval.rebuild", {"project_id": project_id}))
            query_ms = _timed(
                lambda: _call(
                    core,
                    "retrieval.query",
                    {"project_id": project_id, "query": "rollback", "limit": 5},
                )
            )
            return {
                "status": "verified",
                "scope": "deterministic-core-smoke",
                "startup_ms": startup_ms,
                "project_create_ms": project_create_ms,
                "source_import_ms": import_ms,
                "index_build_ms": index_ms,
                "warm_query_ms": query_ms,
                "automatic_question_segmentation": "not_applicable",
                "content_output": False,
            }
        finally:
            core.close()


def _model_inventory() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="presenter-copilot-m9-model-status-") as temporary:
        core = CoreService(data_root=Path(temporary) / "data")
        try:
            result = _call(core, "models.status", {})
            models = result.get("models")
            if not isinstance(models, list):
                return {"status": "unavailable", "code": "MODEL_STATUS_INVALID"}
            safe_models: list[dict[str, Any]] = []
            for item in models:
                if not isinstance(item, dict):
                    continue
                safe_models.append(
                    {
                        "kind": item.get("kind"),
                        "adapter_id": item.get("adapter_id"),
                        "model_id": item.get("model_id"),
                        "status": item.get("status"),
                        "local_only": item.get("local_only"),
                        "preparing": item.get("preparing"),
                        "error_code": item.get("error_code"),
                    }
                )
            return {
                "status": "verified",
                "network_policy": result.get("network_policy"),
                "models": safe_models,
            }
        finally:
            core.close()


def _report_reference(path: Path, expected_sha: str | None) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"status": "not_run"}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"status": "unavailable", "code": "REPORT_INVALID"}
    if not isinstance(value, dict):
        return {"status": "unavailable", "code": "REPORT_INVALID"}
    report_sha = value.get("git_sha")
    if expected_sha is not None and report_sha != expected_sha:
        return {
            "status": "stale",
            "report_git_sha": report_sha if isinstance(report_sha, str) else None,
        }
    allowed = {
        key: value[key]
        for key in (
            "status",
            "benchmark",
            "git_sha",
            "target_pass",
            "targets",
            "query_embedding",
            "matrix_search",
            "hybrid_retrieval",
            "first_partial",
            "finalization",
            "model_status",
            "model_id",
        )
        if key in value
    }
    allowed["status"] = str(value.get("status", "available"))
    return allowed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the metadata-only M9 release benchmark.")
    parser.add_argument(
        "--profile",
        choices=("auto", "cpu_only", "rtx_reference"),
        default="auto",
        help="Hardware profile to record; auto uses nvidia-smi availability.",
    )
    parser.add_argument(
        "--retrieval-report",
        type=Path,
        default=Path("artifacts") / "m2-retrieval-benchmark.json",
        help="Optional existing real retrieval benchmark report.",
    )
    parser.add_argument(
        "--asr-report",
        type=Path,
        default=Path("artifacts") / "m6-asr-benchmark.json",
        help="Optional existing real ASR benchmark report.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts") / "m9-release-benchmark.json",
        help="Metadata-only aggregate output path.",
    )
    args = parser.parse_args(argv)
    output = args.output if args.output.is_absolute() else REPOSITORY_ROOT / args.output
    retrieval_report = (
        args.retrieval_report
        if args.retrieval_report.is_absolute()
        else REPOSITORY_ROOT / args.retrieval_report
    )
    asr_report = (
        args.asr_report if args.asr_report.is_absolute() else REPOSITORY_ROOT / args.asr_report
    )
    gpu = _gpu_name()
    profile = _hardware_profile(args.profile, gpu)
    git_sha = _git_sha()
    report = {
        "benchmark": "m9-release-v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "core_version": CORE_VERSION,
        "hardware": {
            "profile": profile,
            "os": platform.platform(),
            "architecture": platform.machine(),
            "cpu_model": platform.processor() or None,
            "ram_bytes": _system_ram_bytes(),
            "gpu_name": gpu,
        },
        "execution": {
            "content_output": False,
            "network_allowed_by_this_command": False,
            "model_downloaded_by_this_command": False,
        },
        "model_inventory": _model_inventory(),
        "deterministic_smoke": _deterministic_smoke(),
        "real_benchmarks": {
            "retrieval": _report_reference(retrieval_report, git_sha),
            "asr": _report_reference(asr_report, git_sha),
        },
        "hardware_evidence": {
            "profile": "detected_only" if args.profile == "auto" else "declared_only",
            "cpu_only": "not_run",
            "rtx_reference": "detected_only" if gpu else "not_run",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
