"""Protocol v1 envelope builders and constants.

The sidecar writes only objects made by this module to stdout. Diagnostic
messages belong on stderr at the process boundary instead.
"""

from __future__ import annotations

from typing import Any, Final

PROTOCOL_VERSION: Final = 1
REQUEST_TYPE: Final = "request"
RESPONSE_TYPE: Final = "response"
EVENT_TYPE: Final = "event"

SUPPORTED_METHODS: Final[tuple[str, ...]] = (
    "core.hello",
    "core.health",
    "core.shutdown",
    "project.create",
    "project.open",
    "project.list",
    "project.update_settings",
    "project.delete",
    "source.import",
    "source.list",
    "source.preview",
    "source.delete",
    "source.reindex",
    "search.lexical",
)
SUPPORTED_EVENTS: Final[tuple[str, ...]] = (
    "core.ready",
    "core.error",
    "source.import_progress",
    "source.import_error",
    "project.index_progress",
    "project.index_ready",
)


def make_response(
    request_id: str | None,
    *,
    result: Any = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a response and enforce the mutually exclusive success/error shape."""
    if (result is None) == (error is None):
        raise ValueError("exactly one of result or error must be supplied")

    response: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "type": RESPONSE_TYPE,
        "request_id": request_id,
        "ok": error is None,
    }
    if error is None:
        response["result"] = result
    else:
        response["error"] = error
    return response


def make_error(
    request_id: str | None,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured protocol error response."""
    return make_response(
        request_id,
        error={
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": details or {},
        },
    )


def make_event(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Build a protocol event envelope."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "type": EVENT_TYPE,
        "event": event,
        "payload": payload,
    }
