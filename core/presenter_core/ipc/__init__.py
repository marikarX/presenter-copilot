"""Versioned stdio IPC for the Presenter Copilot core."""

from .core import CoreService
from .protocol import PROTOCOL_VERSION

__all__ = ["CoreService", "PROTOCOL_VERSION"]
