"""Reproducible 50k-vector local retrieval benchmark with metadata-only output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import FastEmbedAdapter, embedding_model_cache_dir
from presenter_core.retrieval.index import NumpyEmbeddingIndex

VECTOR_COUNT = 50_000
QUERY_COUNT = 20
MATRIX_BATCH_SIZE = 2_048


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
        raise RuntimeError(
            f"{error.get('code', 'ERROR')}: {error.get('message', 'request failed')}"
        )
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("RETRIEVAL_BENCHMARK_FAILED: core returned an invalid result")
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


def _current_process_memory_bytes() -> int | None:
    try:
        import psutil  # type: ignore[import-untyped]

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except (ImportError, OSError, AttributeError):
        return None


def _system_ram_bytes() -> int | None:
    """Read total physical RAM on Windows without adding a benchmark dependency."""
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


def _prepare_synthetic_project(
    core: CoreService,
    project_id: str,
    matrix_path: Path,
    *,
    dimension: int,
    model_id: str,
    model_fingerprint: str,
    adapter_id: str,
) -> tuple[str, np.ndarray[Any, Any]]:
    document_id = str(uuid.uuid4())
    source_unit_id = str(uuid.uuid4())
    generation_id = str(uuid.uuid4())
    with core._storage.project_database(project_id) as connection:
        connection.execute(
            """
            INSERT INTO documents (
                id, project_id, kind, original_name, local_snapshot_path,
                source_uri, sha256, mime_type, parser_id, imported_at,
                parse_status, parse_error_code, parse_error_message,
                byte_size, metadata_json
            ) VALUES (?, ?, 'supporting', 'benchmark.txt', NULL, NULL, ?, 'text/plain',
                      'benchmark.synthetic', 'now', 'ready', NULL, NULL, 0, '{}')
            """,
            (document_id, project_id, "b" * 64),
        )
        connection.execute(
            """
            INSERT INTO source_units (
                id, document_id, unit_type, ordinal, title, start_ms,
                end_ms, speaker_label, text, metadata_json
            ) VALUES (?, ?, 'section', 1, 'Benchmark', NULL, NULL, NULL, 'synthetic', '{}')
            """,
            (source_unit_id, document_id),
        )
        connection.commit()

    matrix = NumpyEmbeddingIndex.create_staging_matrix(
        matrix_path,
        rows=VECTOR_COUNT,
        dimension=dimension,
    )
    generator = np.random.default_rng(20260901)
    chunk_rows: list[tuple[Any, ...]] = []
    vector_rows: list[tuple[Any, ...]] = []
    for start in range(0, VECTOR_COUNT, MATRIX_BATCH_SIZE):
        end = min(VECTOR_COUNT, start + MATRIX_BATCH_SIZE)
        values = generator.standard_normal((end - start, dimension), dtype=np.float32)
        norms = np.linalg.norm(values, axis=1, keepdims=True)
        matrix[start:end] = values / norms
        for row_index in range(start, end):
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"m2-benchmark:{row_index}"))
            text_value = f"seeded benchmark chunk {row_index}"
            chunk_rows.append(
                (
                    chunk_id,
                    source_unit_id,
                    row_index,
                    text_value,
                    None,
                    f"{generation_id}:{chunk_id}",
                    text_value,
                    "now",
                )
            )
            vector_rows.append(
                (
                    generation_id,
                    chunk_id,
                    "chunk",
                    chunk_id,
                    project_id,
                    "document",
                    row_index,
                    hashlib.sha256(text_value.encode()).hexdigest(),
                )
            )
    NumpyEmbeddingIndex.flush_and_fsync(matrix, matrix_path)
    del matrix

    with core._storage.project_database(project_id) as connection:
        connection.executemany(
            """
            INSERT INTO chunks (
                id, source_unit_id, chunk_index, text, token_count,
                embedding_key, lexical_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            chunk_rows,
        )
        connection.execute(
            """
            INSERT INTO embedding_generations (
                id, adapter_id, model_id, model_fingerprint, dimension,
                matrix_relative_path, matrix_row_count, is_active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'now')
            """,
            (
                generation_id,
                adapter_id,
                model_id,
                model_fingerprint,
                dimension,
                f"embeddings/{matrix_path.name}",
                VECTOR_COUNT,
            ),
        )
        connection.executemany(
            """
            INSERT INTO embedding_vectors (
                generation_id, vector_id, entity_type, entity_id, project_id,
                source_class, row_index, content_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            vector_rows,
        )
        connection.commit()

    matrix_loaded = NumpyEmbeddingIndex.load_matrix(
        matrix_path,
        expected_rows=VECTOR_COUNT,
        expected_dimension=dimension,
    )
    return generation_id, matrix_loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark 50,000-vector local retrieval.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts") / "m2-retrieval-benchmark.json",
        help="Metadata-only JSON output path.",
    )
    parser.add_argument(
        "--model-data-root",
        type=Path,
        help="Optional application root containing the already-prepared model cache.",
    )
    args = parser.parse_args(argv)
    repository_root = Path(__file__).parents[3]
    output_path = args.output if args.output.is_absolute() else repository_root / args.output
    adapter = FastEmbedAdapter(
        cache_dir=embedding_model_cache_dir(args.model_data_root),
        local_files_only=True,
    )
    with tempfile.TemporaryDirectory(prefix="presenter-copilot-m2-benchmark-") as temporary:
        core = CoreService(
            data_root=Path(temporary) / "data",
            embedding_adapter=adapter,
        )
        matrix: np.ndarray[Any, Any] | None = None
        try:
            project_id = _call(core, "create", "project.create", {"name": "M2 benchmark"})[
                "project"
            ]["id"]
            project_paths = core._storage.paths.project(project_id)
            matrix_path = project_paths.embeddings / "vectors-benchmark.npy"
            adapter_health = adapter.health()
            if adapter_health.status != "ready" or adapter_health.dimension is None:
                raise RuntimeError("EMBEDDING_MODEL_UNAVAILABLE: prepare the model first")
            _, matrix = _prepare_synthetic_project(
                core,
                project_id,
                matrix_path,
                dimension=adapter_health.dimension,
                model_id=adapter_health.model_id,
                model_fingerprint=adapter_health.model_fingerprint or "",
                adapter_id=adapter_health.adapter_id,
            )

            query_texts = [f"synthetic retrieval query {index}" for index in range(QUERY_COUNT)]
            query_embedding_times: list[float] = []
            query_vectors: list[np.ndarray[Any, Any]] = []
            for query_text in query_texts:
                started = perf_counter()
                query_vectors.append(adapter.embed_query(query_text))
                query_embedding_times.append((perf_counter() - started) * 1000)

            eligible_rows = np.arange(VECTOR_COUNT, dtype=np.int64)
            NumpyEmbeddingIndex.cosine_search(
                matrix,
                query_vectors[0],
                eligible_rows=eligible_rows,
                limit=10,
            )
            matrix_search_times: list[float] = []
            for query_vector in query_vectors:
                started = perf_counter()
                NumpyEmbeddingIndex.cosine_search(
                    matrix,
                    query_vector,
                    eligible_rows=eligible_rows,
                    limit=10,
                )
                matrix_search_times.append((perf_counter() - started) * 1000)

            for index in range(3):
                _call(
                    core,
                    f"warmup-{index}",
                    "retrieval.query",
                    {"project_id": project_id, "query": query_texts[index], "limit": 10},
                )
            hybrid_times: list[float] = []
            for index, query_text in enumerate(query_texts):
                started = perf_counter()
                _call(
                    core,
                    f"hybrid-{index}",
                    "retrieval.query",
                    {"project_id": project_id, "query": query_text, "limit": 10},
                )
                hybrid_times.append((perf_counter() - started) * 1000)

            benchmark = {
                "timestamp": datetime.now(UTC).isoformat(),
                "git_sha": _git_sha(repository_root),
                "os": platform.platform(),
                "python_version": platform.python_version(),
                "cpu_model": platform.processor() or None,
                "ram_bytes": _system_ram_bytes(),
                "embedding_model_id": adapter_health.model_id,
                "model_fingerprint": adapter_health.model_fingerprint,
                "dimension": adapter_health.dimension,
                "vector_count": VECTOR_COUNT,
                "query_count": QUERY_COUNT,
                "cold_model_load_ms": adapter_health.model_load_ms,
                "query_embedding": _timing_summary(query_embedding_times),
                "matrix_search": _timing_summary(matrix_search_times),
                "hybrid_retrieval": _timing_summary(hybrid_times),
                "peak_process_memory_bytes": _current_process_memory_bytes(),
                "target_p95_ms": 250.0,
                "target_pass": _percentile(hybrid_times, 95) <= 250.0,
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
                        "code": "RETRIEVAL_BENCHMARK_FAILED",
                        "message": str(error),
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 1
        finally:
            core.close()
            if isinstance(matrix, np.memmap):
                mmap_handle = getattr(matrix, "_mmap", None)
                if mmap_handle is not None:
                    mmap_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
