"""Stable domain errors returned by the Python core."""

from __future__ import annotations

from typing import Any


class CoreDomainError(Exception):
    """An expected, renderer-safe error with a stable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


def invalid_request(message: str, *, field: str | None = None) -> CoreDomainError:
    """Build a consistent request-validation error."""
    return CoreDomainError(
        "INVALID_REQUEST",
        message,
        details={"field": field} if field else {},
    )


def reject_unknown_fields(params: dict[str, Any], allowed: set[str]) -> None:
    """Reject accidental contract drift at service boundaries."""
    unknown = sorted(set(params).difference(allowed))
    if unknown:
        raise invalid_request(
            "Request contains unsupported fields.",
            field=unknown[0],
        )
