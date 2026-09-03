"""Feature-detected, read-only presentation state adapters."""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

from presenter_core.errors import CoreDomainError


@dataclass(frozen=True)
class PresentationInfo:
    """The bounded project presentation identity used for PowerPoint matching."""

    document_id: str
    original_name: str
    slide_count: int


@dataclass(frozen=True)
class PresentationSnapshot:
    """Safe read-only state obtained from an already-running slideshow."""

    file_name: str
    slide_count: int
    current_slide: int


class PowerPointFacade(Protocol):
    def snapshot(self) -> PresentationSnapshot | None: ...


class PresentationAdapter(Protocol):
    @property
    def id(self) -> str: ...

    def detect(self, presentation: PresentationInfo | None) -> dict[str, Any]: ...

    def current_slide(self, presentation: PresentationInfo) -> int: ...

    def close(self) -> None: ...


class ManualPresentationAdapter:
    """Marker adapter for internal slide tracking; it never touches PowerPoint."""

    @property
    def id(self) -> str:
        return "manual"

    def detect(self, presentation: PresentationInfo | None) -> dict[str, Any]:
        return {
            "available": True,
            "mode": "manual",
            "reason": "MANUAL_TRACKING",
            "current_slide": None,
        }

    def current_slide(self, presentation: PresentationInfo) -> int:
        raise CoreDomainError(
            "PRESENTATION_STATE_UNAVAILABLE",
            "Manual tracking has no external current-slide source.",
        )

    def close(self) -> None:
        return


class PowerPointPresentationAdapter:
    """Read an existing PowerPoint slideshow without launching or editing it."""

    def __init__(self, facade: PowerPointFacade | None = None) -> None:
        self._facade = facade or PowerPointComFacade()

    @property
    def id(self) -> str:
        return "powerpoint"

    def detect(self, presentation: PresentationInfo | None) -> dict[str, Any]:
        if presentation is None or presentation.slide_count < 1:
            return self._fallback("NO_PROJECT_PRESENTATION")
        if os.name != "nt" and isinstance(self._facade, PowerPointComFacade):
            return self._fallback("POWERPOINT_UNAVAILABLE")
        try:
            snapshot = self._facade.snapshot()
        except Exception:
            return self._fallback("POWERPOINT_UNAVAILABLE")
        if snapshot is None:
            return self._fallback("POWERPOINT_NO_ACTIVE_SLIDESHOW")
        if snapshot.file_name.casefold() != Path(presentation.original_name).name.casefold():
            return self._fallback("POWERPOINT_DECK_MISMATCH")
        if snapshot.slide_count != presentation.slide_count:
            return self._fallback("POWERPOINT_SLIDE_COUNT_MISMATCH")
        if not 1 <= snapshot.current_slide <= presentation.slide_count:
            return self._fallback("POWERPOINT_INVALID_SLIDE")
        return {
            "available": True,
            "mode": "powerpoint",
            "reason": "POWERPOINT_MATCHED",
            "current_slide": snapshot.current_slide,
        }

    def current_slide(self, presentation: PresentationInfo) -> int:
        try:
            snapshot = self._facade.snapshot()
        except Exception as exc:
            raise CoreDomainError(
                "POWERPOINT_STATE_UNAVAILABLE",
                "The PowerPoint slideshow is no longer available.",
                retryable=True,
            ) from exc
        if snapshot is None:
            raise CoreDomainError(
                "POWERPOINT_STATE_UNAVAILABLE",
                "The PowerPoint slideshow is no longer available.",
                retryable=True,
            )
        if (
            snapshot.file_name.casefold() != Path(presentation.original_name).name.casefold()
            or snapshot.slide_count != presentation.slide_count
            or not 1 <= snapshot.current_slide <= presentation.slide_count
        ):
            raise CoreDomainError(
                "POWERPOINT_STATE_UNAVAILABLE",
                "The running PowerPoint slideshow no longer matches this project.",
                retryable=True,
            )
        return snapshot.current_slide

    def close(self) -> None:
        close = getattr(self._facade, "close", None)
        if callable(close):
            close()

    @staticmethod
    def _fallback(reason: str) -> dict[str, Any]:
        return {
            "available": False,
            "mode": "manual",
            "reason": reason,
            "current_slide": None,
        }


class PowerPointComFacade:
    """Small COM probe; all failures collapse to an unavailable snapshot."""

    def snapshot(self) -> PresentationSnapshot | None:
        if os.name != "nt":
            return None
        pythoncom_lib: Any | None = None
        initialized = False
        try:
            pythoncom_lib = import_module("pythoncom")
            win32com_client = import_module("win32com.client")

            pythoncom_lib.CoInitialize()
            initialized = True
            application = win32com_client.GetActiveObject("PowerPoint.Application")
            windows = application.SlideShowWindows
            if int(windows.Count) < 1:
                return None
            window = windows.Item(1)
            view = window.View
            presentation = window.Presentation
            file_name = Path(str(presentation.FullName)).name[:260]
            slide_count = int(presentation.Slides.Count)
            current_slide = int(view.Slide.SlideIndex)
            if slide_count < 1 or current_slide < 1:
                return None
            return PresentationSnapshot(file_name, slide_count, current_slide)
        except Exception:
            return None
        finally:
            if initialized and pythoncom_lib is not None:
                try:
                    pythoncom_lib.CoUninitialize()
                except Exception:
                    pass


class FakePowerPointFacade:
    """Deterministic COM substitute for CI and contract tests."""

    def __init__(self, snapshot: PresentationSnapshot | None = None) -> None:
        self.current = snapshot
        self.fail = False

    def snapshot(self) -> PresentationSnapshot | None:
        if self.fail:
            raise RuntimeError("fake COM failure")
        return self.current

    def close(self) -> None:
        return
