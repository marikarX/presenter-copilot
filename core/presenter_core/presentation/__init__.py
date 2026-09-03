"""Project-scoped manual and read-only PowerPoint presentation state."""

from .adapters import (
    FakePowerPointFacade,
    ManualPresentationAdapter,
    PowerPointPresentationAdapter,
    PresentationInfo,
    PresentationSnapshot,
)
from .service import SlideStateService

__all__ = [
    "FakePowerPointFacade",
    "ManualPresentationAdapter",
    "PowerPointPresentationAdapter",
    "PresentationInfo",
    "PresentationSnapshot",
    "SlideStateService",
]
