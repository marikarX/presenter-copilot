"""NDJSON stdin/stdout server for the local core sidecar."""

from __future__ import annotations

import json
from typing import TextIO

from .core import CoreService


class SidecarServer:
    """Own the transport loop and keep protocol output newline-delimited."""

    def __init__(self, stdin: TextIO, stdout: TextIO, core: CoreService | None = None) -> None:
        self._stdin = stdin
        self._stdout = stdout
        self._core = core or CoreService()

    def run(self) -> int:
        """Emit readiness, process requests, and stop after a graceful shutdown."""
        try:
            self._write(self._core.ready_event())
            for line in self._stdin:
                if not line:
                    break
                response = self._core.handle_line(line)
                if response.get("ok") is False and isinstance(response.get("error"), dict):
                    self._write(
                        self._core.error_event(
                            response["error"],
                            response.get("request_id")
                            if isinstance(response.get("request_id"), str)
                            else None,
                        )
                    )
                self._write(response)
                if self._core.shutdown_requested:
                    break
        except BrokenPipeError:
            return 0
        return 0

    def _write(self, message: dict[str, object]) -> None:
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        self._stdout.write(f"{encoded}\n")
        self._stdout.flush()
