"""Manual real-model acceptance over the distributable synthetic fixture."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from time import monotonic
from typing import Any, cast

from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import FastEmbedAdapter, embedding_model_cache_dir

FIXTURE_ROOT = Path(__file__).parents[3] / "samples" / "synthetic-deck"


def _call(
    core: CoreService, request_id: str, method: str, params: dict[str, Any]
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
        raise RuntimeError(
            f"{error.get('code', 'ERROR')}: {error.get('message', 'request failed')}"
        )
    return cast(dict[str, Any], response["result"])


def _acceptance_cases() -> list[dict[str, Any]]:
    goldens = json.loads(
        (FIXTURE_ROOT / "expected" / "retrieval-goldens.json").read_text(encoding="utf-8")
    )
    return list(goldens.get("semantic_targets", [])) + list(goldens.get("hybrid_targets", []))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run real local FastEmbed retrieval acceptance.")
    parser.add_argument(
        "--model-data-root",
        type=Path,
        help="Optional application root containing the already-prepared model cache.",
    )
    args = parser.parse_args(argv)
    adapter = FastEmbedAdapter(
        cache_dir=embedding_model_cache_dir(args.model_data_root),
        local_files_only=True,
    )
    with tempfile.TemporaryDirectory(prefix="presenter-copilot-m2-acceptance-") as temporary:
        core = CoreService(data_root=Path(temporary) / "data", embedding_adapter=adapter)
        try:
            project_id = _call(core, "create", "project.create", {"name": "M2 acceptance"})[
                "project"
            ]["id"]
            sources = [
                (FIXTURE_ROOT / "deck" / "presentation.pptx", "presentation"),
                (FIXTURE_ROOT / "supporting" / "cost-model.pdf", "supporting"),
                (FIXTURE_ROOT / "supporting" / "architecture-notes.md", "supporting"),
            ]
            for index, (source, kind) in enumerate(sources):
                _call(
                    core,
                    f"import-{index}",
                    "source.import",
                    {"project_id": project_id, "path": str(source.resolve()), "kind": kind},
                )
            build_started = monotonic()
            rebuilt = _call(
                core,
                "rebuild",
                "retrieval.rebuild",
                {"project_id": project_id},
            )
            build_ms = (monotonic() - build_started) * 1000
            health = _call(
                core,
                "health",
                "retrieval.health",
                {"project_id": project_id},
            )
            results: list[dict[str, Any]] = []
            passed = 0
            for index, case in enumerate(_acceptance_cases()):
                params: dict[str, Any] = {
                    "project_id": project_id,
                    "query": case["query"],
                    "limit": int(case.get("top_k", 3)),
                }
                for field in ("current_slide", "slide_window", "source_types"):
                    if field in case:
                        params[field] = case[field]
                query_result = _call(core, f"query-{index}", "retrieval.query", params)
                labels = [hit["evidence"]["label"] for hit in query_result["hits"]]
                expected = list(case.get("expected_labels", [case.get("expected_label")]))
                expected = [label for label in expected if label]
                case_passed = all(
                    label in labels[: int(case.get("top_k", 3))] for label in expected
                )
                if case.get("conflict"):
                    case_passed = case_passed and bool(query_result["conflicts"])
                passed += int(case_passed)
                results.append(
                    {
                        "query_name": case.get("name", case["query"]),
                        "expected_labels": expected,
                        "observed_labels": labels,
                        "conflict_detected": bool(query_result["conflicts"]),
                        "passed": case_passed,
                        "latency_ms": query_result["latency_ms"],
                    }
                )
            report = {
                "status": "passed" if passed == len(results) else "failed",
                "adapter_id": health["adapter_id"],
                "model_id": health["model_id"],
                "model_fingerprint": health["model_fingerprint"],
                "dimension": health["dimension"],
                "model_load_ms": health["model_load_ms"],
                "build_ms": round(build_ms, 3),
                "indexed_chunks": rebuilt["indexed_count"],
                "golden_passed": passed,
                "golden_total": len(results),
                "queries": results,
            }
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report["status"] == "passed" else 1
        except RuntimeError as error:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "code": "EMBEDDING_ACCEPTANCE_FAILED",
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
