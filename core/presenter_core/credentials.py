"""Privileged, user-scoped provider credential storage.

The renderer never sends a credential to this module.  The production store
uses Windows Credential Manager when available; the small in-memory store is
only an injected test seam and is never selected by normal application code.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Protocol, cast

OPENAI_CREDENTIAL_TARGET = "Presenter Copilot/OpenAI"
OPENROUTER_CREDENTIAL_TARGET = "Presenter Copilot/OpenRouter"
MAX_CREDENTIAL_CHARS = 8_192
MAX_CHATGPT_PLAN_VAULT_CHARS = 262_144
# DPAPI receives no prompt structure, so the no-flags path stays noninteractive.
_CHATGPT_VAULT_DPAPI_FLAGS = 0


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

    def __init__(
        self,
        target_name: str = OPENAI_CREDENTIAL_TARGET,
        username: str = "Presenter Copilot",
    ) -> None:
        if not target_name or len(target_name) > 256 or not username or len(username) > 256:
            raise ValueError("credential target metadata is invalid")
        self._target_name = target_name
        self._username = username

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

            credential = win32cred.CredRead(self._target_name, win32cred.CRED_TYPE_GENERIC)
            blob = credential.get("CredentialBlob")
            if isinstance(blob, bytes):
                value = blob.decode("utf-8")
            elif isinstance(blob, str):
                value = blob
            else:
                raise CredentialStoreUnavailable
            if not _valid_credential(value):
                raise CredentialStoreUnavailable
            return value
        except Exception as error:
            # Missing is the only safe negative result. A read/API/decode
            # failure must remain distinguishable to Reset Local Data, or a
            # credential could be left behind while the reset reports success.
            if getattr(error, "winerror", None) == self._ERROR_NOT_FOUND:
                return None
            if isinstance(error, CredentialStoreUnavailable):
                raise
            raise CredentialStoreUnavailable from error

    def write(self, value: str) -> None:
        _require_credential(value)
        if not self.is_available():
            raise CredentialStoreUnavailable
        try:
            import win32cred

            win32cred.CredWrite(
                {
                    "Type": win32cred.CRED_TYPE_GENERIC,
                    "TargetName": self._target_name,
                    "CredentialBlob": value.encode("utf-8"),
                    "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
                    "UserName": self._username,
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

            win32cred.CredDelete(self._target_name, win32cred.CRED_TYPE_GENERIC, 0)
            return True
        except Exception as error:
            # Credential Manager reports a missing target as an API error. It
            # is the one safe idempotent case; every other API failure must
            # stop reset/removal rather than leave a credential behind while
            # claiming success.
            if getattr(error, "winerror", None) == self._ERROR_NOT_FOUND:
                return False
            raise CredentialStoreUnavailable from error


class OpenRouterCredentialStore(WindowsCredentialStore):
    """Store the independent OpenRouter decision-provider credential."""

    def __init__(self) -> None:
        super().__init__(
            target_name=OPENROUTER_CREDENTIAL_TARGET,
            username="Presenter Copilot OpenRouter",
        )


class ChatGPTPlanCredentialStore:
    """Protect the multi-account ChatGPT OAuth vault with Windows DPAPI.

    The OAuth record is larger than a normal API key and contains rotating
    access, refresh, and ID tokens. Keeping one DPAPI-protected file beneath
    the app data root avoids Credential Manager's small per-entry blob limit;
    DPAPI still binds decryption to the current Windows user.
    """

    source = "windows_dpapi_user_vault"

    def __init__(self, data_root: str | Path) -> None:
        self._root = Path(data_root).resolve()
        self._path = self._root / "chatgpt-plan-credentials.dpapi"

    def is_available(self) -> bool:
        if os.name != "nt":
            return False
        try:
            import win32crypt  # type: ignore[import-untyped]

            return callable(getattr(win32crypt, "CryptProtectData", None)) and callable(
                getattr(win32crypt, "CryptUnprotectData", None)
            )
        except Exception:
            return False

    def read(self) -> str | None:
        if not self.is_available():
            return None
        if not self._root.exists():
            return None
        self._check_target()
        if not self._path.exists():
            return None
        try:
            if self._path.stat().st_size > MAX_CHATGPT_PLAN_VAULT_CHARS + 65_536:
                raise CredentialStoreUnavailable
            import win32crypt

            encrypted = self._path.read_bytes()
            _, plaintext = win32crypt.CryptUnprotectData(
                encrypted, None, None, None, _CHATGPT_VAULT_DPAPI_FLAGS
            )
            value = cast(bytes, plaintext).decode("utf-8")
            if not _valid_vault(value):
                raise CredentialStoreUnavailable
            return value
        except CredentialStoreUnavailable:
            raise
        except Exception as error:
            raise CredentialStoreUnavailable from error

    def write(self, value: str) -> None:
        if not _valid_vault(value):
            raise ValueError("ChatGPT token vault is outside the bounded format")
        if not self.is_available():
            raise CredentialStoreUnavailable
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            self._check_target()
            import win32crypt

            encrypted = win32crypt.CryptProtectData(
                value.encode("utf-8"),
                "Presenter Copilot ChatGPT plan credentials",
                None,
                None,
                None,
                _CHATGPT_VAULT_DPAPI_FLAGS,
            )
            if len(encrypted) > MAX_CHATGPT_PLAN_VAULT_CHARS + 65_536:
                raise ValueError("ChatGPT token vault is outside the bounded format")
            temporary = self._root / f".chatgpt-plan-{uuid.uuid4().hex}.tmp"
            try:
                with temporary.open("xb") as stream:
                    stream.write(encrypted)
                    stream.flush()
                    os.fsync(stream.fileno())
                self._check_target()
                os.replace(temporary, self._path)
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
        except ValueError:
            raise
        except Exception as error:
            raise CredentialStoreUnavailable from error

    def delete(self) -> bool:
        if not self.is_available():
            return False
        if not self._root.exists():
            return False
        self._check_target()
        try:
            self._path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as error:
            raise CredentialStoreUnavailable from error

    def _check_target(self) -> None:
        if (
            self._root.is_symlink()
            or not self._root.is_dir()
            or self._path.is_symlink()
            or self._path.resolve().parent != self._root.resolve()
        ):
            raise CredentialStoreUnavailable


class InMemoryChatGPTPlanCredentialStore:
    """Synthetic protected-vault seam for OAuth and reset tests."""

    source = "test_chatgpt_plan_vault"

    def __init__(self, value: str | None = None, *, available: bool = True) -> None:
        self._value = value
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def read(self) -> str | None:
        if not self._available:
            return None
        if self._value is not None and not _valid_vault(self._value):
            raise CredentialStoreUnavailable
        return self._value

    def write(self, value: str) -> None:
        if not _valid_vault(value):
            raise ValueError("ChatGPT token vault is outside the bounded format")
        if not self._available:
            raise CredentialStoreUnavailable
        self._value = value

    def delete(self) -> bool:
        if not self._available:
            return False
        existed = self._value is not None
        self._value = None
        return existed


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


def resolve_openrouter_credential(store: CredentialStore) -> str | None:
    """Prefer the OS store and retain the environment only as a bootstrap path."""
    stored = store.read()
    if stored:
        return stored
    environment = os.environ.get("OPENROUTER_API_KEY")
    return environment if _valid_credential(environment) else None


def openrouter_credential_source(store: CredentialStore) -> str:
    """Return safe OpenRouter credential source metadata without the credential."""
    if store.read():
        return store.source
    if _valid_credential(os.environ.get("OPENROUTER_API_KEY")):
        return "environment"
    return "none"


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


def _valid_vault(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= MAX_CHATGPT_PLAN_VAULT_CHARS
        and not any(ord(character) < 32 and character not in "\r\n\t" for character in value)
    )


def _require_credential(value: str) -> None:
    if not _valid_credential(value):
        raise ValueError("credential is empty or outside the bounded credential format")
