"""Run the Presenter Copilot core sidecar over stdin/stdout."""

from __future__ import annotations

import sys
from io import TextIOWrapper

from .ipc.server import SidecarServer


def main() -> int:
    """Run the sidecar and keep stdout reserved for protocol messages."""
    try:
        stdin = sys.stdin
        stdout = sys.stdout
        if isinstance(stdin, TextIOWrapper):
            stdin.reconfigure(encoding="utf-8", errors="replace")
        if isinstance(stdout, TextIOWrapper):
            stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")
        return SidecarServer(stdin, stdout).run()
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # pragma: no cover - last-resort process boundary guard
        print(f"presenter_core fatal error: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
