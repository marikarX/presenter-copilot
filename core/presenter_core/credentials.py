"""Privileged, user-scoped provider credential storage.

The renderer never sends a credential to this module.  The production store
uses Windows Credential Manager when available; the small in-memory store is
only an injected test seam and is never selected by normal application code.
"""

from __future__ import annotations

import os
from typing import Protocol

OPENAI_CREDENTIAL_TARGET = "Presenter Copilot/OpenAI"
MAX_CREDENTIAL_CHARS = 8_192


class CredentialStore(Protocol):
    """Minimal core-owned credential store contract."""

    source: str

    def is_available(self) -> bool: ...

    def read(self) -> str | None: ...

    def write(self, value: str) -> None: ...

    def delete(self) -> bool: ...


class WindowsCredentialStore:
    """Windows Credential Manager generic credential store.

    Imports are lazy because deterministic Linux/CI environments should still
    be able to construct the core and exercise all non-credential paths.
    """

    source = "windows_credential_manager"
    _ERROR_NOT_FOUND = 1168

    def is_available(self) -> bool:
        if os.name != "nt":
            return False
        try:
            import win32cred  # type: ignore[import-untyped]

            return callable(getattr(win32cred, "CredRead", None))
        except Exception:
            return False

    def read(self) -> str | None:
        if not self.is_available():
            return None
        try:
            import win32cred

            credential = win32cred.CredRead(OPENAI_CREDENTIAL_TARGET, win32cred.CRED_TYPE_GENERIC)
            blob = credential.get("CredentialBlob")
            if isinstance(blob, bytes):
                value = blob.decode("utf-8")
            elif isinstance(blob, str):
                value = blob
            else:
                return None
            return value if _valid_credential(value) else None
        except Exception:
            # Absence, corrupt data, and a temporarily unavailable API are all
            # intentionally indistinguishable at the renderer boundary.
            return None

    def write(self, value: str) -> None:
        _require_credential(value)
        if not self.is_available():
            raise CredentialStoreUnavailable
        try:
            import win32cred

            win32cred.CredWrite(
                {
                    "Type": win32cred.CRED_TYPE_GENERIC,
                    "TargetName": OPENAI_CREDENTIAL_TARGET,
                    "CredentialBlob": value.encode("utf-8"),
                    "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
                    "UserName": "Presenter Copilot",
                },
                0,
            )
        except Exception as error:
            # Do not include the exception string: some platform APIs echo the
            # supplied credential in their diagnostic text.
            raise CredentialStoreUnavailable from error

    def delete(self) -> bool:
        if not self.is_available():
            return False
        try:
            import win32cred

            win32cred.CredDelete(OPENAI_CREDENTIAL_TARGET, win32cred.CRED_TYPE_GENERIC, 0)
            return True
        except Exception as error:
            # Credential Manager reports a missing target as an API error. It
            # is the one safe idempotent case; every other API failure must
            # stop reset/removal rather than leave a credential behind while
            # claiming success.
            if getattr(error, "winerror", None) == self._ERROR_NOT_FOUND:
                return False
            raise CredentialStoreUnavailable from error


class InMemoryCredentialStore:
    """Synthetic credential store used by redaction/security regression tests."""

    source = "test_credential_store"

    def __init__(self, value: str | None = None, *, available: bool = True) -> None:
        self._value = value
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def read(self) -> str | None:
        return self._value if self._available and _valid_credential(self._value) else None

    def write(self, value: str) -> None:
        _require_credential(value)
        if not self._available:
            raise CredentialStoreUnavailable
        self._value = value

    def delete(self) -> bool:
        if not self._available:
            return False
        existed = self._value is not None
        self._value = None
        return existed


class CredentialStoreUnavailable(Exception):
    """Internal marker; callers map it to a stable safe domain error."""


def resolve_openai_credential(store: CredentialStore) -> str | None:
    """Prefer the OS store and retain the environment only as a bootstrap path."""
    stored = store.read()
    if stored:
        return stored
    environment = os.environ.get("OPENAI_API_KEY")
    return environment if _valid_credential(environment) else None


def credential_source(store: CredentialStore) -> str:
    """Return safe source metadata without returning the credential itself."""
    if store.read():
        return store.source
    if _valid_credential(os.environ.get("OPENAI_API_KEY")):
        return "environment"
    return "none"


def _valid_credential(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= MAX_CREDENTIAL_CHARS
        and not any(ord(character) < 32 for character in value)
    )


def _require_credential(value: str) -> None:
    if not _valid_credential(value):
        raise ValueError("credential is empty or outside the bounded credential format")
