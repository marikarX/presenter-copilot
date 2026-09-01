"""Milestone 0 core lifecycle handlers."""

from __future__ import annotations

import json
from collections.abc import Callable
from time import monotonic
from typing import Any

from presenter_core import CORE_VERSION

from .protocol import (
    PROTOCOL_VERSION,
    SUPPORTED_EVENTS,
    SUPPORTED_METHODS,
    make_error,
    make_event,
    make_response,
)


class CoreService:
    """Handle validated lifecycle requests without owning transport concerns."""

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._started_at = clock()
        self._shutdown_requested = False

    @property
    def shutdown_requested(self) -> bool:
        """Whether the server should exit after sending the current response."""
        return self._shutdown_requested

    @property
    def metadata(self) -> dict[str, Any]:
        """Return compatibility metadata for the handshake."""
        return {
            "protocol_version": PROTOCOL_VERSION,
            "core_version": CORE_VERSION,
            "capabilities": {
                "methods": list(SUPPORTED_METHODS),
                "events": list(SUPPORTED_EVENTS),
            },
            "adapters": [],
            "migration_status": "not_required",
        }

    def ready_event(self) -> dict[str, Any]:
        """Return the startup event sent before the first request is read."""
        return make_event("core.ready", self.metadata)

    def error_event(self, error: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        """Return a non-correlated diagnostic event for a rejected envelope."""
        return make_event(
            "core.error",
            {
                "code": error["code"],
                "message": error["message"],
                "request_id": request_id,
            },
        )

    def handle_line(self, line: str) -> dict[str, Any]:
        """Parse one NDJSON line and always return a structured response."""
        try:
            message: Any = json.loads(line)
        except json.JSONDecodeError:
            return make_error(
                None,
                "MALFORMED_JSON",
                "The sidecar received a line that is not valid JSON.",
            )
        return self.handle_message(message)

    def handle_message(self, message: Any) -> dict[str, Any]:
        """Validate and dispatch one decoded request object."""
        if not isinstance(message, dict):
            return make_error(None, "INVALID_REQUEST", "Request envelope must be a JSON object.")

        request_id_value = message.get("request_id")
        request_id = request_id_value if isinstance(request_id_value, str) else None

        received_version = message.get("protocol_version")
        if received_version != PROTOCOL_VERSION or isinstance(received_version, bool):
            return make_error(
                request_id,
                "PROTOCOL_VERSION_UNSUPPORTED",
                f"Protocol version {received_version!r} is not supported.",
                details={"supported_versions": [PROTOCOL_VERSION]},
            )

        if message.get("type") != "request":
            return make_error(
                request_id,
                "INVALID_REQUEST",
                "Envelope type must be 'request'.",
            )

        if not isinstance(request_id_value, str) or not request_id_value:
            return make_error(
                None,
                "INVALID_REQUEST",
                "Request id must be a non-empty string.",
            )
        request_id = request_id_value

        method = message.get("method")
        if not isinstance(method, str) or not method:
            return make_error(request_id, "INVALID_REQUEST", "Method must be a non-empty string.")

        params = message.get("params")
        if not isinstance(params, dict):
            return make_error(request_id, "INVALID_REQUEST", "Params must be a JSON object.")

        if method not in SUPPORTED_METHODS:
            return make_error(
                request_id,
                "METHOD_NOT_FOUND",
                f"Unknown method: {method}",
                details={"method": method, "supported_methods": list(SUPPORTED_METHODS)},
            )

        return self._dispatch(request_id, method, params)

    def _dispatch(self, request_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        del params  # Lifecycle methods do not currently accept method-specific fields.
        if method == "core.hello":
            return make_response(request_id, result=self.metadata)
        if method == "core.health":
            return make_response(
                request_id,
                result={
                    "status": "ok",
                    "ready": True,
                    "protocol_version": PROTOCOL_VERSION,
                    "core_version": CORE_VERSION,
                    "uptime_ms": max(0, int((self._clock() - self._started_at) * 1000)),
                },
            )

        # The supported-method check above makes this branch unreachable unless
        # a future method is added without a handler, which should fail loudly.
        if method == "core.shutdown":
            self._shutdown_requested = True
            return make_response(request_id, result={"status": "shutting_down"})

        raise AssertionError(f"supported method has no handler: {method}")
