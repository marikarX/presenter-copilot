"""Explicit, network-permitted bootstrap for the pinned local ASR model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from presenter_core.asr.adapters import (
    DEFAULT_ASR_ADAPTER_ID,
    DEFAULT_ASR_MODEL_ID,
    FasterWhisperASRAdapter,
)
from presenter_core.errors import CoreDomainError
from presenter_core.storage.paths import AppPaths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download/prepare the pinned local ASR model in the app cache."
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help="Optional application data root used only to locate the shared model cache.",
    )
    args = parser.parse_args(argv)
    adapter: FasterWhisperASRAdapter | None = None
    try:
        cache_dir = AppPaths(args.data_root).asr_model_cache_directory(create=True)
        adapter = FasterWhisperASRAdapter(cache_dir=cache_dir)
        adapter.prepare_model()
        print(
            json.dumps(
                {
                    "status": "ready",
                    "operation": "explicit_model_prepare",
                    "adapter_id": DEFAULT_ASR_ADAPTER_ID,
                    "model_id": DEFAULT_ASR_MODEL_ID,
                    "model_status": adapter.model_status(),
                    "network_allowed_by_this_command": True,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except CoreDomainError as error:
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": error.code,
                    "message": error.message,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": "ASR_MODEL_PREPARE_FAILED",
                    "message": "The approved local ASR model could not be prepared.",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        if adapter is not None:
            adapter.close()


if __name__ == "__main__":
    raise SystemExit(main())
