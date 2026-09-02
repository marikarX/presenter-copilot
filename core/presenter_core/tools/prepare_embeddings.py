"""Explicit, network-permitted local embedding model bootstrap command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from presenter_core.retrieval.embeddings import FastEmbedAdapter, embedding_model_cache_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download/prepare the pinned local embedding model in the app cache."
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help="Optional application data root used only to locate the shared model cache.",
    )
    args = parser.parse_args(argv)
    adapter = FastEmbedAdapter(
        cache_dir=embedding_model_cache_dir(args.data_root),
        local_files_only=False,
    )
    health = adapter.prepare()
    if health.status != "ready":
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": health.error_code or "EMBEDDING_MODEL_UNAVAILABLE",
                    "message": "The pinned local embedding model could not be prepared.",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "ready",
                "operation": "explicit_model_prepare",
                "adapter_id": health.adapter_id,
                "model_id": health.model_id,
                "model_fingerprint": health.model_fingerprint,
                "dimension": health.dimension,
                "model_load_ms": health.model_load_ms,
                "network_allowed_by_this_command": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    adapter.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
