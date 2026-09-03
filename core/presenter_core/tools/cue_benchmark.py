"""Metadata-only Live Assist cue latency benchmark."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import DeterministicFakeAudioInput
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.adapters import ManualPresentationAdapter
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter

QUERY_COUNT = 20
BENCHMARK_QUERY = "$980,000"


def _call(
    core: CoreService,
    method: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
    )
    if response.get("ok") is not True:
        error = response.get("error", {})
        raise RuntimeError(
            f"{error.get('code', 'ERROR')}: {error.get('message', 'request failed')}"
        )
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("CUE_BENCHMARK_FAILED: core returned an invalid result")
    return result


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=np.float64), percentile))


def _timing_summary(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": round(_percentile(values, 50), 3),
        "p95_ms": round(_percentile(values, 95), 3),
        "max_ms": round(max(values) if values else 0.0, 3),
    }


def _git_sha(repository_root: Path) -> str | None:
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


def _seed_known_fact(core: CoreService, project_id: str, repository_root: Path) -> None:
    _call(
        core,
        "source.import",
        {
            "project_id": project_id,
            "kind": "supporting",
            "path": str(
                repository_root / "samples" / "synthetic-deck" / "supporting" / "cost-model.pdf"
            ),
        },
    )
    _call(core, "retrieval.rebuild", {"project_id": project_id})


def main(argv: list[str] | None = None) -> int:
    del argv
    repository_root = Path(__file__).parents[3]
    output_path = repository_root / "artifacts" / "m7-cue-benchmark.json"
    events: list[tuple[str, dict[str, Any], float]] = []
    events_lock = threading.Lock()

    def on_event(envelope: dict[str, Any]) -> None:
        event = envelope.get("event")
        payload = envelope.get("payload")
        if event in {"assist.retrieval_ready", "cue.partial", "cue.ready"} and isinstance(
            payload, dict
        ):
            with events_lock:
                events.append((str(event), dict(payload), perf_counter()))

    with tempfile.TemporaryDirectory(prefix="presenter-copilot-m7-cue-") as temporary:
        core = CoreService(
            data_root=Path(temporary) / "data",
            embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
            reasoning_provider=DeterministicFakeReasoningProvider(locality="local"),
            audio_input=DeterministicFakeAudioInput(),
            asr_adapters={"deterministic-fake": DeterministicFakeASRAdapter()},
            presentation_adapter=ManualPresentationAdapter(),
            event_sink=on_event,
        )
        try:
            project_id = _call(core, "project.create", {"name": "M7 cue benchmark"})["project"][
                "id"
            ]
            _seed_known_fact(core, project_id, repository_root)
            session_id = _call(
                core,
                "session.start",
                {"project_id": project_id, "mode": "live_assist", "current_slide_start": 1},
            )["session"]["id"]

            retrieval_times: list[float] = []
            first_useful_times: list[float] = []
            ready_times: list[float] = []
            progressive_times: list[float] = []
            for _ in range(QUERY_COUNT):
                trigger_started = perf_counter()
                started = _call(
                    core,
                    "assist.request",
                    {
                        "project_id": project_id,
                        "session_id": session_id,
                        "question": BENCHMARK_QUERY,
                        "trigger": "hotkey",
                    },
                )
                assist_id = str(started["assist_id"])
                if not core._assist.wait_for_idle(5.0):
                    raise RuntimeError("CUE_BENCHMARK_FAILED: assist worker did not become idle")
                with events_lock:
                    sample_events = [
                        (event, payload, observed_at)
                        for event, payload, observed_at in events
                        if payload.get("assist_id") == assist_id
                    ]
                retrieval = next(
                    (
                        observed_at
                        for event, _, observed_at in sample_events
                        if event == "assist.retrieval_ready"
                    ),
                    None,
                )
                progressive = next(
                    (
                        observed_at
                        for event, _, observed_at in sample_events
                        if event == "cue.partial"
                    ),
                    None,
                )
                useful = next(
                    (
                        observed_at
                        for event, payload, observed_at in sample_events
                        if event == "cue.ready"
                        and payload.get("state") == "final"
                        and payload.get("route") == "retrieval_only"
                    ),
                    None,
                )
                ready = next(
                    (
                        observed_at
                        for event, _, observed_at in sample_events
                        if event == "cue.ready"
                    ),
                    None,
                )
                if retrieval is None or useful is None or ready is None:
                    raise RuntimeError(
                        "CUE_BENCHMARK_FAILED: the deterministic cue path did not emit "
                        "all timing events"
                    )
                retrieval_times.append((retrieval - trigger_started) * 1000)
                first_useful_times.append((useful - trigger_started) * 1000)
                ready_times.append((ready - trigger_started) * 1000)
                if progressive is not None:
                    progressive_times.append((progressive - trigger_started) * 1000)

            benchmark = {
                "timestamp": datetime.now(UTC).isoformat(),
                "implementation_sha": _git_sha(repository_root),
                "os": platform.platform(),
                "python_version": platform.python_version(),
                "machine": platform.machine() or None,
                "cpu_model": platform.processor() or None,
                "embedding_adapter": "deterministic-test-v1",
                "sample_count": QUERY_COUNT,
                "trigger": "hotkey",
                "progressive_partial": _timing_summary(progressive_times),
                "trigger_to_retrieval_ready": _timing_summary(retrieval_times),
                "trigger_to_first_useful_cue": _timing_summary(first_useful_times),
                "trigger_to_ready": _timing_summary(ready_times),
                "target_p50_ms": 1200.0,
                "target_p95_ms": 2500.0,
                "target_pass": _percentile(first_useful_times, 50) <= 1200.0
                and _percentile(first_useful_times, 95) <= 2500.0,
                "first_useful_definition": "first final retrieval_only cue.ready event",
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(benchmark, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(benchmark, indent=2, sort_keys=True))
            return 0
        except RuntimeError as error:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "code": "CUE_BENCHMARK_FAILED",
                        "message": str(error),
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 1
        finally:
            core.close()


if __name__ == "__main__":
    raise SystemExit(main())
