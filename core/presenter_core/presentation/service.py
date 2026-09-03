"""Project-scoped slide state, timeline persistence, and manual fallback."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.limits import MAX_SLIDE_EVENTS_PER_SESSION
from presenter_core.project.service import utc_now
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

from .adapters import (
    ManualPresentationAdapter,
    PowerPointPresentationAdapter,
    PresentationAdapter,
    PresentationInfo,
)

EventSink = Callable[[str, dict[str, Any]], None]
SessionValidator = Callable[[str, str], dict[str, Any]]


@dataclass
class _ActivePresentation:
    project_id: str
    session_id: str
    info: PresentationInfo | None
    mode: str
    reason: str
    current_slide: int | None
    slide_count: int | None
    started_monotonic: float = field(default_factory=monotonic)
    watcher_stop: threading.Event = field(default_factory=threading.Event)
    watcher: threading.Thread | None = None


class SlideStateService:
    """Persist only actual slide changes and keep PowerPoint read-only."""

    def __init__(
        self,
        storage: StorageManager,
        session_validator: SessionValidator,
        *,
        event_sink: EventSink | None = None,
        powerpoint_adapter: PresentationAdapter | None = None,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        self._storage = storage
        self._session_validator = session_validator
        self._event_sink = event_sink
        self._powerpoint = powerpoint_adapter or PowerPointPresentationAdapter()
        self._manual = ManualPresentationAdapter()
        self._poll_interval_seconds = poll_interval_seconds
        self._lock = threading.RLock()
        self._runs: dict[tuple[str, str], _ActivePresentation] = {}
        self._closed = False

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        self._event_sink = event_sink

    def start_run(self, project_id: str, session_id: str) -> dict[str, Any]:
        project_id = self._project_id(project_id)
        session_id = self._session_id(session_id)
        session = self._validate_run(project_id, session_id)
        key = (project_id, session_id)
        with self._lock:
            existing = self._runs.get(key)
            if existing is not None:
                return self._status_locked(existing)
            if self._closed:
                raise CoreDomainError(
                    "PRESENTATION_STATE_UNAVAILABLE", "Presentation state is shut down."
                )

        info = self._presentation_info(project_id)
        detection = self._powerpoint.detect(info)
        use_powerpoint = bool(detection.get("available")) and detection.get("mode") == "powerpoint"
        mode = "powerpoint" if use_powerpoint else "manual"
        reason = str(detection.get("reason") or "MANUAL_TRACKING")
        current = (
            detection.get("current_slide") if use_powerpoint else session.get("current_slide_start")
        )
        current_slide = self._valid_slide(current, info.slide_count if info else None)
        if current_slide is None and mode == "manual" and info is not None and info.slide_count > 0:
            current_slide = 1
        active = _ActivePresentation(
            project_id=project_id,
            session_id=session_id,
            info=info,
            mode=mode,
            reason=reason,
            current_slide=None,
            slide_count=info.slide_count if info else None,
        )
        with self._lock:
            self._runs[key] = active
        try:
            if current_slide is not None:
                self._persist_slide(active, current_slide, source=mode, timestamp_ms=0)
            if mode == "powerpoint" and info is not None:
                self._start_watcher(active)
        except Exception:
            with self._lock:
                self._runs.pop(key, None)
            raise
        self._emit_status(active)
        return self.status({"project_id": project_id, "session_id": session_id})

    def detect(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        self._validate_run(project_id, session_id)
        key = (project_id, session_id)
        with self._lock:
            active = self._runs.get(key)
        if active is None:
            return self.start_run(project_id, session_id)

        info = self._presentation_info(project_id)
        detection = self._powerpoint.detect(info)
        if detection.get("available") and detection.get("mode") == "powerpoint":
            current = self._valid_slide(
                detection.get("current_slide"), info.slide_count if info else None
            )
            if current is None:
                self._switch_to_manual(active, "POWERPOINT_INVALID_SLIDE")
            else:
                with self._lock:
                    active.info = info
                    active.slide_count = info.slide_count if info else None
                    active.mode = "powerpoint"
                    active.reason = str(detection.get("reason") or "POWERPOINT_MATCHED")
                if active.current_slide != current:
                    self._persist_slide(active, current, source="powerpoint")
                self._start_watcher(active)
                self._emit_status(active)
        else:
            self._switch_to_manual(active, str(detection.get("reason") or "POWERPOINT_UNAVAILABLE"))
        return self.status({"project_id": project_id, "session_id": session_id})

    def set_slide(self, params: dict[str, Any]) -> dict[str, Any]:
        project_id, session_id, slide = self._slide_request(params)
        active = self._active_run(project_id, session_id)
        if active.mode == "powerpoint":
            self._switch_to_manual(active, "MANUAL_OVERRIDE")
        normalized = self._valid_slide(slide, active.slide_count)
        if normalized is None:
            raise invalid_request(
                "slide_ordinal is outside the current presentation.", field="slide_ordinal"
            )
        self._persist_slide(active, normalized, source="manual")
        return self.status({"project_id": project_id, "session_id": session_id})

    def next_slide(self, params: dict[str, Any]) -> dict[str, Any]:
        project_id, session_id = self._navigation_request(params)
        active = self._active_run(project_id, session_id)
        if active.mode == "powerpoint":
            self._switch_to_manual(active, "MANUAL_OVERRIDE")
        current = active.current_slide or 1
        next_slide = current + 1
        if active.slide_count is not None:
            next_slide = min(active.slide_count, next_slide)
        self._persist_slide(active, next_slide, source="manual")
        return self.status({"project_id": project_id, "session_id": session_id})

    def previous_slide(self, params: dict[str, Any]) -> dict[str, Any]:
        project_id, session_id = self._navigation_request(params)
        active = self._active_run(project_id, session_id)
        if active.mode == "powerpoint":
            self._switch_to_manual(active, "MANUAL_OVERRIDE")
        current = active.current_slide or 1
        self._persist_slide(active, max(1, current - 1), source="manual")
        return self.status({"project_id": project_id, "session_id": session_id})

    def status(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params.get("project_id"))
        session_id = self._session_id(params.get("session_id"))
        key = (project_id, session_id)
        with self._lock:
            active = self._runs.get(key)
            if active is not None:
                return self._status_locked(active)
        self._validate_session_scope(project_id, session_id)
        info = self._presentation_info(project_id)
        latest = self._latest_slide(project_id, session_id)
        return {
            "project_id": project_id,
            "session_id": session_id,
            "mode": "manual",
            "reason": "RUN_NOT_ACTIVE",
            "current_slide": self._valid_slide(latest, info.slide_count if info else None),
            "slide_count": info.slide_count if info else None,
            "tracking": "stopped",
        }

    def current_slide(self, project_id: str, session_id: str) -> int | None:
        project_id = self._project_id(project_id)
        session_id = self._session_id(session_id)
        with self._lock:
            active = self._runs.get((project_id, session_id))
            if active is not None:
                return active.current_slide
        info = self._presentation_info(project_id)
        return self._valid_slide(
            self._latest_slide(project_id, session_id), info.slide_count if info else None
        )

    def stop_run(self, project_id: str, session_id: str) -> None:
        key = (self._project_id(project_id), self._session_id(session_id))
        with self._lock:
            active = self._runs.get(key)
            if active is None:
                return
            active.watcher_stop.set()
            watcher = active.watcher
        if watcher is not None and watcher is not threading.current_thread():
            watcher.join(timeout=1.0)
        with self._lock:
            self._runs.pop(key, None)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            keys = list(self._runs)
        for project_id, session_id in keys:
            self.stop_run(project_id, session_id)
        try:
            self._powerpoint.close()
        except Exception:
            pass
        self._manual.close()

    def _start_watcher(self, active: _ActivePresentation) -> None:
        with self._lock:
            if active.watcher is not None and active.watcher.is_alive():
                return
            active.watcher_stop.clear()
            watcher = threading.Thread(
                target=self._watch_powerpoint,
                args=(active,),
                name="presenter-copilot-powerpoint",
                daemon=True,
            )
            active.watcher = watcher
            watcher.start()

    def _watch_powerpoint(self, active: _ActivePresentation) -> None:
        if active.info is None:
            return
        while not active.watcher_stop.wait(self._poll_interval_seconds):
            with self._lock:
                if self._runs.get((active.project_id, active.session_id)) is not active:
                    return
                if active.mode != "powerpoint":
                    return
            try:
                current = self._powerpoint.current_slide(active.info)
            except CoreDomainError as error:
                self._switch_to_manual(active, error.code)
                return
            if self._valid_slide(current, active.slide_count) is None:
                self._switch_to_manual(active, "POWERPOINT_INVALID_SLIDE")
                return
            if current != active.current_slide:
                try:
                    self._persist_slide(active, current, source="powerpoint")
                except CoreDomainError:
                    self._switch_to_manual(active, "PRESENTATION_TIMELINE_FAILED")
                    return

    def _switch_to_manual(self, active: _ActivePresentation, reason: str) -> None:
        with self._lock:
            if self._runs.get((active.project_id, active.session_id)) is not active:
                return
            was_powerpoint = active.mode == "powerpoint"
            active.mode = "manual"
            active.reason = reason
            active.watcher_stop.set()
            watcher = active.watcher
        if was_powerpoint and watcher is not None and watcher is not threading.current_thread():
            watcher.join(timeout=1.0)
        self._emit_status(active)

    def _persist_slide(
        self,
        active: _ActivePresentation,
        slide_ordinal: int,
        *,
        source: str,
        timestamp_ms: int | None = None,
    ) -> None:
        if source not in {"powerpoint", "manual"}:
            raise ValueError("unsupported M6 slide source")
        with self._lock:
            if self._runs.get((active.project_id, active.session_id)) is not active:
                return
            if active.current_slide == slide_ordinal:
                return
            if timestamp_ms is None:
                timestamp_ms = max(0, int((monotonic() - active.started_monotonic) * 1_000))
        with self._storage.project_database(active.project_id) as connection:
            session = connection.execute(
                "SELECT status, mode FROM sessions WHERE id = ? AND project_id = ?",
                (active.session_id, active.project_id),
            ).fetchone()
            if session is None or session["mode"] != "run" or session["status"] != "active":
                return
            count_row = connection.execute(
                "SELECT COUNT(*) FROM slide_state_events WHERE session_id = ?",
                (active.session_id,),
            ).fetchone()
            if count_row is not None and int(count_row[0]) >= MAX_SLIDE_EVENTS_PER_SESSION:
                raise CoreDomainError(
                    "RUN_SESSION_LIMIT_REACHED",
                    "The Run slide timeline reached its safety bound.",
                )
            latest = connection.execute(
                "SELECT slide_ordinal, timestamp_ms FROM slide_state_events "
                "WHERE session_id = ? ORDER BY timestamp_ms DESC, id DESC LIMIT 1",
                (active.session_id,),
            ).fetchone()
            if latest is not None and int(latest["slide_ordinal"]) == slide_ordinal:
                with self._lock:
                    active.current_slide = slide_ordinal
                return
            if latest is not None:
                timestamp_ms = max(int(timestamp_ms), int(latest["timestamp_ms"]))
            connection.execute(
                """
                INSERT INTO slide_state_events
                    (id, session_id, slide_ordinal, timestamp_ms, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    active.session_id,
                    slide_ordinal,
                    timestamp_ms,
                    source,
                    utc_now(),
                ),
            )
            connection.commit()
        with self._lock:
            active.current_slide = slide_ordinal
            active.reason = "POWERPOINT_MATCHED" if source == "powerpoint" else active.reason
        self._emit(
            "presentation.slide_changed",
            {
                "session_id": active.session_id,
                "slide_ordinal": slide_ordinal,
                "timestamp_ms": timestamp_ms,
                "source": source,
            },
        )

    def _status_locked(self, active: _ActivePresentation) -> dict[str, Any]:
        return {
            "project_id": active.project_id,
            "session_id": active.session_id,
            "mode": active.mode,
            "reason": active.reason,
            "current_slide": active.current_slide,
            "slide_count": active.slide_count,
            "tracking": "active",
        }

    def _emit_status(self, active: _ActivePresentation) -> None:
        self._emit("presentation.status_changed", self._status_locked(active))

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)

    def _active_run(self, project_id: str, session_id: str) -> _ActivePresentation:
        self._validate_run(project_id, session_id)
        with self._lock:
            active = self._runs.get((project_id, session_id))
        if active is None:
            active = self._start_for_active_request(project_id, session_id)
        return active

    def _start_for_active_request(self, project_id: str, session_id: str) -> _ActivePresentation:
        self.start_run(project_id, session_id)
        with self._lock:
            active = self._runs.get((project_id, session_id))
        if active is None:
            raise CoreDomainError(
                "PRESENTATION_STATE_UNAVAILABLE", "Run presentation state is unavailable."
            )
        return active

    def _validate_run(self, project_id: str, session_id: str) -> dict[str, Any]:
        try:
            return self._session_validator(project_id, session_id)
        except CoreDomainError as error:
            raise CoreDomainError(
                "PRESENTATION_SESSION_INVALID",
                "Presentation state requires an active Run session.",
                details={"reason": error.code},
            ) from error

    def _validate_session_scope(self, project_id: str, session_id: str) -> None:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                "SELECT id FROM sessions WHERE id = ? AND project_id = ?",
                (session_id, project_id),
            ).fetchone()
            if row is None:
                raise CoreDomainError("SESSION_NOT_FOUND", "The session was not found.")

    def _presentation_info(self, project_id: str) -> PresentationInfo | None:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                """
                SELECT d.id, d.original_name, COUNT(DISTINCT su.ordinal) AS slide_count
                FROM project p
                JOIN documents d ON d.id = p.current_presentation_id
                LEFT JOIN source_units su ON su.document_id = d.id
                    AND su.unit_type IN ('slide', 'page')
                    AND su.ordinal IS NOT NULL
                WHERE p.id = ? AND d.project_id = ? AND d.kind = 'presentation'
                GROUP BY d.id, d.original_name
                """,
                (project_id, project_id),
            ).fetchone()
        if row is None or int(row["slide_count"]) < 1:
            return None
        return PresentationInfo(str(row["id"]), str(row["original_name"]), int(row["slide_count"]))

    def _latest_slide(self, project_id: str, session_id: str) -> int | None:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                "SELECT slide_ordinal FROM slide_state_events WHERE session_id = ? "
                "ORDER BY timestamp_ms DESC, id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        return int(row[0]) if row is not None else None

    @staticmethod
    def _valid_slide(value: Any, slide_count: int | None) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return None
        if slide_count is not None and value > slide_count:
            return None
        return cast(int, value)

    @staticmethod
    def _project_id(value: Any) -> str:
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _session_id(value: Any) -> str:
        if not isinstance(value, str):
            raise invalid_request("session_id must be a UUID.", field="session_id")
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise invalid_request("session_id must be a UUID.", field="session_id") from exc

    @classmethod
    def _navigation_request(cls, params: dict[str, Any]) -> tuple[str, str]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        return cls._project_id(params.get("project_id")), cls._session_id(params.get("session_id"))

    @classmethod
    def _slide_request(cls, params: dict[str, Any]) -> tuple[str, str, int]:
        reject_unknown_fields(params, {"project_id", "session_id", "slide_ordinal"})
        project_id, session_id = cls._navigation_request(params)
        value = params.get("slide_ordinal")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise invalid_request(
                "slide_ordinal must be a positive integer.", field="slide_ordinal"
            )
        return project_id, session_id, value
