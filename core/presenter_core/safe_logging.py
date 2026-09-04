"""Allowlisted structured logging for the Python core boundary.

The core's stdout is a protocol transport and must never be used for ordinary
diagnostics.  This module deliberately accepts only a small set of scalar
metadata fields instead of accepting arbitrary messages and attempting to
redact them afterwards.
"""

from __future__ import annotations

import json
import re
import threading
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SAFE_LOG_FIELDS = frozenset(
    {
        "project_id",
        "session_id",
        "document_id",
        "assist_id",
        "provider_run_id",
        "event",
        "status",
        "error_code",
        "cause_code",
        "provider_id",
        "model_id",
        "adapter_id",
        "operation",
        "phase",
        "count",
        "completed",
        "total",
        "size_bytes",
        "duration_ms",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "retryable",
        "generation_id",
        "schema_version",
        "attempt",
        "exit_code",
        "signal",
    }
)
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.:/-]{1,160}$")
_SENSITIVE_VALUE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|bearer|credential|password|secret|sk-[a-z0-9])"
)
_ID_FIELDS = frozenset(
    {
        "project_id",
        "session_id",
        "document_id",
        "assist_id",
        "provider_run_id",
        "generation_id",
    }
)
_STRING_FIELDS = (
    SAFE_LOG_FIELDS
    - _ID_FIELDS
    - {
        "count",
        "completed",
        "total",
        "size_bytes",
        "duration_ms",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "retryable",
        "schema_version",
        "attempt",
        "exit_code",
    }
)
MAX_RECENT_LOGS = 100


def _safe_scalar(field: str, value: Any) -> str | int | bool | None:
    """Return one bounded allowlisted scalar, or omit it with ``None``."""
    if value is None:
        return None
    if field in _ID_FIELDS or field in _STRING_FIELDS:
        if (
            not isinstance(value, str)
            or not _SAFE_NAME.fullmatch(value)
            or _SENSITIVE_VALUE.search(value) is not None
        ):
            return None
        return value
    if field == "signal":
        if (
            not isinstance(value, str)
            or not _SAFE_NAME.fullmatch(value)
            or _SENSITIVE_VALUE.search(value) is not None
        ):
            return None
        return value
    if field == "retryable":
        return bool(value) if isinstance(value, bool) else None
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if (
        field
        in {
            "count",
            "completed",
            "total",
            "size_bytes",
            "duration_ms",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "schema_version",
            "attempt",
            "exit_code",
        }
        and value >= 0
    ):
        return min(int(value), 2**63 - 1)
    return None


class SafeLogger:
    """Write metadata-only JSONL records outside the protocol stream."""

    def __init__(self, data_root: str | Path, *, max_recent: int = MAX_RECENT_LOGS) -> None:
        root = Path(data_root).expanduser().resolve()
        self._root = root
        self._log_path = root / "logs" / "core.jsonl"
        self._lock = threading.RLock()
        self._recent: deque[dict[str, Any]] = deque(maxlen=max(1, int(max_recent)))

    @property
    def path(self) -> Path:
        """Return the internal path for lifecycle cleanup, never for renderer IPC."""
        return self._log_path

    def event(self, event_name: str, fields: dict[str, Any] | None = None) -> None:
        """Record only safe fields; arbitrary messages and exception bodies are discarded."""
        if (
            not isinstance(event_name, str)
            or not _SAFE_NAME.fullmatch(event_name)
            or _SENSITIVE_VALUE.search(event_name) is not None
        ):
            event_name = "invalid_event"
        record: dict[str, Any] = {
            "timestamp": datetime.now(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "event": event_name,
        }
        for key, value in (fields or {}).items():
            if key not in SAFE_LOG_FIELDS or key == "event":
                continue
            safe = _safe_scalar(key, value)
            if safe is not None:
                record[key] = safe
        encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        with self._lock:
            self._recent.append(dict(record))
            try:
                if not self._safe_log_location(create=True):
                    return
                with self._log_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(encoded)
                    handle.write("\n")
            except OSError:
                # Logging is advisory.  A read/write failure must never alter
                # a domain result or corrupt the NDJSON protocol.
                pass

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return a copy of recent allowlisted records for diagnostics."""
        bounded = max(0, min(int(limit), self._recent.maxlen or MAX_RECENT_LOGS))
        with self._lock:
            return [dict(item) for item in list(self._recent)[-bounded:]] if bounded else []

    def clear(self) -> None:
        """Remove the logger's own file without following a log-file symlink."""
        with self._lock:
            self._recent.clear()
            try:
                if not self._safe_log_location(create=False):
                    return
                if self._log_path.is_symlink():
                    return
                if self._log_path.exists() and self._log_path.is_file():
                    self._log_path.unlink()
            except OSError:
                pass

    def _safe_log_location(self, *, create: bool) -> bool:
        """Validate the fixed log directory and file without following links."""
        directory = self._log_path.parent
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            return False
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        if (
            not directory.exists()
            or directory.is_symlink()
            or not directory.is_dir()
            or directory.resolve() != self._root / "logs"
        ):
            return False
        return not (
            self._log_path.is_symlink()
            or (self._log_path.exists() and not self._log_path.is_file())
        )
