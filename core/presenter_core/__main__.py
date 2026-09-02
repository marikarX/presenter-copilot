"""Run the Presenter Copilot core sidecar over stdin/stdout."""

from __future__ import annotations

import os
import sys
from io import TextIOWrapper

from .ipc.core import CoreService
from .ipc.server import SidecarServer
from .providers.fake import DeterministicFakeReasoningProvider
from .providers.models import ReasoningProvider


def _explicit_developer_provider() -> ReasoningProvider | None:
    """Return the fake provider only for an explicit local developer smoke run.

    The normal sidecar path remains the OpenAI reference adapter.  Requiring
    both flags prevents a missing production credential from silently changing
    the provider or privacy behavior, while still making the built desktop UI
    testable without a real provider credential.
    """
    if (
        os.environ.get("PRESENTER_COPILOT_DEV_MODE") == "1"
        and os.environ.get("PRESENTER_COPILOT_TEST_PROVIDER") == "deterministic_fake"
    ):
        return DeterministicFakeReasoningProvider(
            locality="local",
            model_id="fake-challenge-v1",
        )
    return None


def main() -> int:
    """Run the sidecar and keep stdout reserved for protocol messages."""
    try:
        stdin = sys.stdin
        stdout = sys.stdout
        if isinstance(stdin, TextIOWrapper):
            stdin.reconfigure(encoding="utf-8", errors="replace")
        if isinstance(stdout, TextIOWrapper):
            stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
        return SidecarServer(
            stdin,
            stdout,
            core=CoreService(reasoning_provider=_explicit_developer_provider()),
        ).run()
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # pragma: no cover - last-resort process boundary guard
        print(f"presenter_core fatal error: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
