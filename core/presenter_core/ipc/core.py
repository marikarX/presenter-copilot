"""Core request dispatcher and M1 service composition."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from typing import Any

from presenter_core import CORE_VERSION
from presenter_core.errors import CoreDomainError, reject_unknown_fields
from presenter_core.ingestion.service import IngestionService
from presenter_core.project.service import ProjectService
from presenter_core.retrieval.lexical import LexicalRetrievalService
from presenter_core.storage.service import StorageManager

from .protocol import (
    PROTOCOL_VERSION,
    SUPPORTED_EVENTS,
    SUPPORTED_METHODS,
    make_error,
    make_event,
    make_response,
)

EventSink = Callable[[dict[str, Any]], None]


class CoreService:
    """Handle requests while keeping transport and filesystem authority separate."""

    def __init__(
        self,
        clock: Callable[[], float] = monotonic,
        data_root: str | Path | None = None,
        event_sink: EventSink | None = None,
    ) -> None:
        self._clock = clock
        self._started_at = clock()
        self._shutdown_requested = False
        self._event_sink = event_sink
        self._storage = StorageManager(data_root)
        self._projects = ProjectService(self._storage)
        self._ingestion = IngestionService(self._storage, self._emit_event)
        self._retrieval = LexicalRetrievalService(self._storage)

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
            "adapters": [
                "pdf.pypdf",
                "pptx.python-pptx",
                "text.stdlib",
                "retrieval.lexical",
            ],
            "migration_status": "ready",
            "storage": {
                "app_schema_version": self._storage.app_schema_version,
                "project_schema_version": 1,
            },
        }

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        """Attach transport output after construction without coupling core to stdio."""
        self._event_sink = event_sink

    def close(self) -> None:
        """Close SQLite handles before the sidecar exits."""
        self._storage.close()

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

        try:
            return self._dispatch(request_id, method, params)
        except CoreDomainError as error:
            return make_error(
                request_id,
                error.code,
                error.message,
                retryable=error.retryable,
                details=error.details,
            )
        except Exception as error:  # pragma: no cover - final request boundary guard
            print(
                f"presenter_core request failed: {type(error).__name__}",
                file=sys.stderr,
                flush=True,
            )
            return make_error(
                request_id,
                "INTERNAL_ERROR",
                "The core could not complete the request.",
                retryable=False,
                details={},
            )

    def _dispatch(self, request_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "core.hello":
            reject_unknown_fields(params, set())
            return make_response(request_id, result=self.metadata)
        if method == "core.health":
            reject_unknown_fields(params, set())
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
            reject_unknown_fields(params, set())
            self._shutdown_requested = True
            self.close()
            return make_response(request_id, result={"status": "shutting_down"})

        if method == "project.create":
            return make_response(request_id, result=self._projects.create(params))
        if method == "project.open":
            return make_response(request_id, result=self._projects.open(params))
        if method == "project.list":
            return make_response(request_id, result=self._projects.list(params))
        if method == "project.update_settings":
            return make_response(request_id, result=self._projects.update_settings(params))
        if method == "project.delete":
            return make_response(request_id, result=self._projects.delete(params))
        if method == "source.import":
            return make_response(request_id, result=self._ingestion.import_source(params))
        if method == "source.list":
            return make_response(request_id, result=self._ingestion.list_sources(params))
        if method == "source.preview":
            return make_response(request_id, result=self._ingestion.preview_source(params))
        if method == "source.delete":
            return make_response(request_id, result=self._ingestion.delete_source(params))
        if method == "source.reindex":
            return make_response(request_id, result=self._ingestion.reindex_source(params))
        if method == "search.lexical":
            return make_response(request_id, result=self._retrieval.query(params))

        raise AssertionError(f"supported method has no handler: {method}")

    def _emit_event(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(make_event(event, payload))
