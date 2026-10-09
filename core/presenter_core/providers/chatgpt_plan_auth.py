"""Sign in with ChatGPT plan usage for local, open-source decision requests.

This flow is intentionally separate from the Codex App Server identity used
for free-form reasoning. OAuth, tokens, account records, and model catalogs
remain in the privileged Core process.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import re
import secrets
import threading
import time
import uuid
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt

from presenter_core.credentials import (
    MAX_CHATGPT_PLAN_VAULT_CHARS,
    ChatGPTPlanCredentialStore,
    CredentialStoreUnavailable,
)
from presenter_core.errors import CoreDomainError, invalid_request

AUTH_ORIGIN = "https://auth.openai.com"
ISSUER = "https://auth.openai.com"
DISCOVERY_URL = f"{AUTH_ORIGIN}/.well-known/openid-configuration"
AUTHORIZE_ENDPOINT = f"{AUTH_ORIGIN}/api/accounts/authorize"
TOKEN_ENDPOINT = f"{AUTH_ORIGIN}/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
MODEL_LIST_ENDPOINT = f"{RESOURCE}/models"
APP_NAME = "Presenter Copilot"
OAUTH_SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
MAX_AUTH_RESPONSE_BYTES = 256 * 1024
MAX_ACCESS_TOKEN_CHARS = 16_384
MAX_CODE_CHARS = 4_096
MAX_MODEL_COUNT = 500
AUTH_TIMEOUT_SECONDS = 600
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")

HttpClientFactory = Callable[[], httpx.Client]
BrowserOpen = Callable[[str], bool]


@dataclass(frozen=True)
class _SignInAttempt:
    state: str
    nonce: str
    verifier: str
    redirect_uri: str
    client_id: str
    host_id: str
    target_account_id: str | None
    started_at: float


class ChatGPTPlanAuthService:
    """Own OAuth state, refresh, model listing, and revocation for this host."""

    def __init__(
        self,
        data_root: str | Path,
        store: Any | None = None,
        *,
        http_client_factory: HttpClientFactory | None = None,
        browser_open: BrowserOpen = webbrowser.open,
        clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store or ChatGPTPlanCredentialStore(data_root)
        self._http_client_factory = http_client_factory or _http_client
        self._browser_open = browser_open
        self._clock = clock
        self._monotonic = monotonic_clock
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._vault_cache: dict[str, Any] | None = None
        self._pending: _SignInAttempt | None = None
        self._pending_server: http.server.HTTPServer | None = None
        self._pending_thread: threading.Thread | None = None
        self._pending_done = threading.Event()
        self._cancel_pending = threading.Event()
        self._error_code: str | None = None
        self._model_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
        self._discovery_cache: tuple[float, dict[str, Any]] | None = None
        self._jwks_cache: tuple[float, dict[str, Any]] | None = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            available = False
            try:
                available = bool(self._store.is_available())
                vault = self._read_vault() if available else self._empty_vault()
            except CoreDomainError as error:
                return {
                    "state": "error",
                    "error_code": error.code,
                    "credential_store_available": available,
                    "active_account_id": None,
                    "accounts": [],
                }
            active_id = vault.get("active_account_id")
            accounts = [
                {
                    "account_id": account["account_id"],
                    "email": account.get("email"),
                    "connected": _is_connected(account),
                    "active": account["account_id"] == active_id,
                }
                for account in vault["accounts"]
            ]
            active = _find_account(vault, active_id)
            state = (
                "signing_in"
                if self._pending is not None
                else "signed_in"
                if _is_connected(active)
                else "signed_out"
            )
            return {
                "state": "error" if self._error_code else state,
                "error_code": self._error_code,
                "credential_store_available": available,
                "active_account_id": active_id,
                "accounts": accounts,
            }

    def sign_in(self, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        unknown = set(params).difference({"account_id"})
        if unknown:
            raise invalid_request("The sign-in request contains unsupported fields.")
        target_account_id = params.get("account_id")
        if target_account_id is not None and (
            not isinstance(target_account_id, str) or len(target_account_id) != 36
        ):
            raise invalid_request("account_id must identify a saved ChatGPT account.")
        if not self._store.is_available():
            raise CoreDomainError(
                "CHATGPT_CREDENTIAL_STORE_UNAVAILABLE",
                "A protected Windows token store is required for ChatGPT plan sign-in.",
                retryable=True,
            )
        with self._lock:
            if self._pending is not None:
                return self.status()
            vault = self._read_vault()
            if self._store.read() is None:
                # Persist the stable host identifier before the first browser
                # authorization attempt, then reuse it on later sign-ins.
                self._write_vault(vault)
            if target_account_id is not None and _find_account(vault, target_account_id) is None:
                raise invalid_request(
                    "The selected ChatGPT account is not saved.", field="account_id"
                )
            host_id = vault["host_id"]
            server = _callback_server(self, target_account_id)
            port = int(server.server_address[1])
            redirect_uri = f"http://127.0.0.1:{port}/auth/callback"
            verifier = _b64url(secrets.token_bytes(48))
            challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
            state = _b64url(secrets.token_bytes(32))
            nonce = _b64url(secrets.token_bytes(32))
            account = _find_account(vault, target_account_id)
            client_id = account["client_id"] if account is not None else "dynamic_agent_client"
            attempt = _SignInAttempt(
                state=state,
                nonce=nonce,
                verifier=verifier,
                redirect_uri=redirect_uri,
                client_id=client_id,
                host_id=host_id,
                target_account_id=target_account_id,
                started_at=self._monotonic(),
            )
            self._pending = attempt
            self._pending_server = server
            self._pending_done.clear()
            self._cancel_pending.clear()
            self._error_code = None
            query = {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": OAUTH_SCOPE,
                "resource": RESOURCE,
                "ext_agent_host_id": host_id,
                "state": state,
                "nonce": nonce,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
            }
            if account is None:
                query["agent_name_hint"] = APP_NAME
            else:
                if account.get("id_token"):
                    query["id_token_hint"] = account["id_token"]
                if account.get("email"):
                    query["login_hint"] = account["email"]
            authorization_url = f"{AUTHORIZE_ENDPOINT}?{urlencode(query)}"
            self._pending_thread = threading.Thread(
                target=self._serve_and_finish,
                args=(server, attempt, authorization_url),
                daemon=True,
                name="chatgpt-plan-oauth",
            )
            self._pending_thread.start()
            return self.status()

    def select_account(self, params: Mapping[str, Any]) -> dict[str, Any]:
        params = dict(params)
        if set(params) != {"account_id"}:
            raise invalid_request("The account selection is invalid.")
        account_id = params["account_id"]
        if not isinstance(account_id, str) or len(account_id) != 36:
            raise invalid_request("account_id must identify a saved ChatGPT account.")
        with self._lock:
            if self._pending is not None:
                raise CoreDomainError(
                    "CHATGPT_LOGIN_IN_PROGRESS",
                    "Finish or cancel the current ChatGPT sign-in before switching accounts.",
                    retryable=True,
                )
            vault = self._read_vault()
            if _find_account(vault, account_id) is None:
                raise invalid_request(
                    "The selected ChatGPT account is not saved.", field="account_id"
                )
            vault["active_account_id"] = account_id
            self._write_vault(vault)
            self._model_cache.clear()
            self._error_code = None
            return self.status()

    def cancel_sign_in(self) -> dict[str, Any]:
        with self._lock:
            if self._pending is not None:
                self._cancel_pending.set()
                server = self._pending_server
                if server is not None:
                    try:
                        server.server_close()
                    except OSError:
                        pass
            return self.status()

    def sign_out(self) -> dict[str, Any]:
        thread: threading.Thread | None = None
        with self._lock:
            if self._pending is not None:
                self._cancel_pending.set()
                if self._pending_server is not None:
                    try:
                        self._pending_server.server_close()
                    except OSError:
                        pass
                thread = self._pending_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=8)
        with self._lock:
            if self._pending is not None:
                raise CoreDomainError(
                    "CHATGPT_LOGIN_IN_PROGRESS",
                    "The current ChatGPT sign-in is still closing; try again shortly.",
                    retryable=True,
                )
            vault = self._read_vault()
            active = _find_account(vault, vault.get("active_account_id"))
            if active is None or not _is_connected(active):
                self._error_code = None
                return {**self.status(), "remote_revocation_confirmed": True}
            refresh_token = active["refresh_token"]
            confirmed = self._revoke(active["client_id"], refresh_token)
            for key in ("access_token", "refresh_token", "id_token", "expires_at", "scopes"):
                active.pop(key, None)
            self._write_vault(vault)
            self._model_cache.pop(active["account_id"], None)
            self._error_code = None if confirmed else "CHATGPT_REMOTE_REVOCATION_UNCONFIRMED"
            return {**self.status(), "remote_revocation_confirmed": confirmed}

    def access_token(self) -> str:
        with self._lock:
            vault = self._read_vault()
            account_id = vault.get("active_account_id")
        if not isinstance(account_id, str):
            raise CoreDomainError(
                "CHATGPT_ACCOUNT_NOT_CONNECTED",
                "Sign in with ChatGPT and allow ChatGPT plan usage before using this provider.",
            )
        return self._access_token_for(account_id)

    def model_options(self, *, force_refresh: bool = False) -> list[dict[str, str]]:
        with self._lock:
            vault = self._read_vault()
            account_id = vault.get("active_account_id")
            if not isinstance(account_id, str):
                return []
            cached = self._model_cache.get(account_id)
            if cached and not force_refresh and cached[0] > self._monotonic():
                return [dict(item) for item in cached[1]]
        token = self._access_token_for(account_id)
        data = self._request_json(
            "GET",
            MODEL_LIST_ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
            max_bytes=MAX_AUTH_RESPONSE_BYTES,
            error_code="CHATGPT_MODEL_LIST_FAILED",
        )
        raw_models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(raw_models, list) or len(raw_models) > MAX_MODEL_COUNT:
            raise CoreDomainError(
                "CHATGPT_MODEL_LIST_INVALID", "The ChatGPT model catalog is invalid."
            )
        options: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in raw_models:
            if not isinstance(item, dict) or item.get("visibility") != "list":
                continue
            model_id = item.get("slug")
            display_name = item.get("display_name")
            if (
                not isinstance(model_id, str)
                or not _MODEL_ID.fullmatch(model_id)
                or model_id in seen
                or not isinstance(display_name, str)
                or not display_name.strip()
                or len(display_name) > 120
                or any(ord(character) < 32 for character in display_name)
            ):
                continue
            seen.add(model_id)
            options.append({"model_id": model_id, "label": display_name.strip()})
        with self._lock:
            self._model_cache[account_id] = (self._monotonic() + 600.0, options)
        return [dict(item) for item in options]

    def clear_for_reset(self) -> dict[str, bool]:
        """Revoke saved sessions where possible, then delete the local vault."""
        thread: threading.Thread | None = None
        with self._lock:
            self._cancel_pending.set()
            if self._pending_server is not None:
                try:
                    self._pending_server.server_close()
                except OSError:
                    pass
            thread = self._pending_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=8)
        with self._lock:
            if self._pending is not None:
                raise CoreDomainError(
                    "CHATGPT_LOGIN_IN_PROGRESS",
                    "The current ChatGPT sign-in is still closing; retry the reset shortly.",
                    retryable=True,
                )
            vault = self._read_vault()
            connected = [account for account in vault["accounts"] if _is_connected(account)]
            revocation_results = [
                self._revoke(account["client_id"], account["refresh_token"])
                for account in connected
            ]
            revocation_confirmed = all(revocation_results)
            try:
                removed = bool(self._store.delete())
            except (CredentialStoreUnavailable, OSError) as error:
                raise CoreDomainError(
                    "CREDENTIAL_STORE_UNAVAILABLE",
                    "The protected ChatGPT token vault could not be removed.",
                    retryable=True,
                ) from error
            self._vault_cache = None
            self._model_cache.clear()
            self._error_code = None
            return {"removed": removed, "remote_revocation_confirmed": revocation_confirmed}

    def stored_vault_present(self) -> bool:
        """Fail closed if the protected vault cannot be inspected for reset."""
        if not self._store.is_available():
            raise CoreDomainError(
                "CHATGPT_CREDENTIAL_STORE_UNAVAILABLE",
                "The protected ChatGPT token store is unavailable.",
                retryable=True,
            )
        try:
            return self._store.read() is not None
        except (CredentialStoreUnavailable, OSError) as error:
            raise CoreDomainError(
                "CHATGPT_CREDENTIAL_STORE_UNAVAILABLE",
                "The protected ChatGPT token store could not be read.",
                retryable=True,
            ) from error

    def close(self) -> None:
        self.cancel_sign_in()
        thread = self._pending_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=8)
        with self._lock:
            self._vault_cache = None
            self._model_cache.clear()

    def _serve_and_finish(
        self,
        server: http.server.HTTPServer,
        attempt: _SignInAttempt,
        authorization_url: str,
    ) -> None:
        callback = _CallbackCapture()
        server.__dict__["_presenter_callback_capture"] = callback
        try:
            if not self._browser_open(authorization_url):
                raise CoreDomainError(
                    "CHATGPT_BROWSER_OPEN_FAILED", "The ChatGPT sign-in browser could not open."
                )
            deadline = self._monotonic() + AUTH_TIMEOUT_SECONDS
            server.timeout = 0.5
            while (
                not callback.done.is_set()
                and not self._cancel_pending.is_set()
                and self._monotonic() < deadline
            ):
                try:
                    server.handle_request()
                except OSError:
                    if self._cancel_pending.is_set():
                        break
                    raise
            if self._cancel_pending.is_set():
                code = "CHATGPT_LOGIN_CANCELLED"
            elif not callback.done.is_set():
                code = "CHATGPT_LOGIN_TIMEOUT"
            elif callback.error:
                code = "CHATGPT_LOGIN_DENIED"
            elif callback.code:
                self._complete_authorization(attempt, callback)
                code = None
            else:
                code = "CHATGPT_LOGIN_FAILED"
            with self._lock:
                self._error_code = code
        except CoreDomainError as error:
            with self._lock:
                self._error_code = (
                    "CHATGPT_LOGIN_CANCELLED" if self._cancel_pending.is_set() else error.code
                )
        except Exception:
            with self._lock:
                self._error_code = "CHATGPT_LOGIN_FAILED"
        finally:
            try:
                server.server_close()
            except OSError:
                pass
            with self._lock:
                if self._pending is attempt:
                    self._pending = None
                    self._pending_server = None
                    self._pending_thread = None
                self._cancel_pending.clear()
                self._pending_done.set()

    def _complete_authorization(self, attempt: _SignInAttempt, callback: _CallbackCapture) -> None:
        if self._cancel_pending.is_set():
            raise CoreDomainError("CHATGPT_LOGIN_CANCELLED", "ChatGPT sign-in was cancelled.")
        if not callback.code or not 1 <= len(callback.code) <= MAX_CODE_CHARS:
            raise CoreDomainError("CHATGPT_LOGIN_FAILED", "ChatGPT sign-in returned no code.")
        issued_client_id = callback.client_id
        if attempt.target_account_id is not None:
            if issued_client_id and issued_client_id != attempt.client_id:
                raise CoreDomainError(
                    "CHATGPT_ACCOUNT_MISMATCH", "ChatGPT returned a different saved account."
                )
            issued_client_id = attempt.client_id
        elif not isinstance(issued_client_id, str) or not _valid_client_id(issued_client_id):
            raise CoreDomainError(
                "CHATGPT_CLIENT_REGISTRATION_FAILED",
                "ChatGPT did not return a registered client ID.",
            )
        token_response = self._request_json(
            "POST",
            TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "client_id": issued_client_id,
                "code": callback.code,
                "code_verifier": attempt.verifier,
                "redirect_uri": attempt.redirect_uri,
                "resource": RESOURCE,
            },
            max_bytes=MAX_AUTH_RESPONSE_BYTES,
            error_code="CHATGPT_TOKEN_EXCHANGE_FAILED",
        )
        if self._cancel_pending.is_set():
            raise CoreDomainError("CHATGPT_LOGIN_CANCELLED", "ChatGPT sign-in was cancelled.")
        tokens = _validate_token_response(token_response)
        claims = self._validate_id_token(tokens["id_token"], issued_client_id, attempt.nonce)
        if self._cancel_pending.is_set():
            raise CoreDomainError("CHATGPT_LOGIN_CANCELLED", "ChatGPT sign-in was cancelled.")
        scopes = tokens["scopes"]
        if "chatgpt.tokens.use.direct" not in scopes or "offline_access" not in scopes:
            raise CoreDomainError(
                "CHATGPT_PLAN_PERMISSION_REQUIRED",
                "Allow ChatGPT plan usage in the sign-in window before using this provider.",
            )
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject or len(subject) > 512:
            raise CoreDomainError(
                "CHATGPT_IDENTITY_INVALID", "ChatGPT identity could not be verified."
            )
        email = claims.get("email")
        if not isinstance(email, str) or len(email) > 320 or any(ord(c) < 32 for c in email):
            email = None
        with self._lock:
            if self._cancel_pending.is_set():
                raise CoreDomainError("CHATGPT_LOGIN_CANCELLED", "ChatGPT sign-in was cancelled.")
            vault = self._read_vault()
            if vault.get("host_id") != attempt.host_id:
                raise CoreDomainError("CHATGPT_HOST_CHANGED", "The ChatGPT host identity changed.")
            account = _find_account(vault, attempt.target_account_id)
            if attempt.target_account_id is not None:
                if account is None or account["client_id"] != issued_client_id:
                    raise CoreDomainError(
                        "CHATGPT_ACCOUNT_MISMATCH", "ChatGPT returned a different saved account."
                    )
                if account["subject"] != subject:
                    raise CoreDomainError(
                        "CHATGPT_ACCOUNT_MISMATCH", "ChatGPT returned a different saved account."
                    )
            else:
                account = {
                    "account_id": str(uuid.uuid4()),
                    "issuer": ISSUER,
                    "subject": subject,
                    "client_id": issued_client_id,
                    "email": email,
                }
                vault["accounts"].append(account)
            account.update(
                {
                    "email": email,
                    "id_token": tokens["id_token"],
                    "access_token": tokens["access_token"],
                    "refresh_token": tokens["refresh_token"],
                    "expires_at": self._clock() + tokens["expires_in"],
                    "scopes": scopes,
                    "saved_at": int(self._clock()),
                }
            )
            vault["active_account_id"] = account["account_id"]
            self._write_vault(vault)
            self._model_cache.clear()

    def _validate_id_token(self, token: str, client_id: str, nonce: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise ValueError("unsupported token header")
            jwks = self._jwks()
            key = _jwks_key(jwks, header["kid"])
            if key is None:
                self._jwks_cache = None
                key = _jwks_key(self._jwks(), header["kid"])
            if key is None:
                raise ValueError("signing key not found")
            claims = jwt.decode(
                token,
                key=jwt.PyJWK.from_dict(key).key,
                algorithms=["RS256"],
                audience=client_id,
                issuer=ISSUER,
                options={"require": ["sub", "exp", "iat", "nonce"]},
                leeway=5,
            )
            if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
                raise ValueError("nonce mismatch")
            return claims
        except Exception as error:
            raise CoreDomainError(
                "CHATGPT_ID_TOKEN_INVALID", "ChatGPT identity could not be verified."
            ) from error

    def _discovery(self) -> dict[str, Any]:
        cached = self._discovery_cache
        if cached and cached[0] > self._monotonic():
            return cached[1]
        data = self._request_json(
            "GET",
            DISCOVERY_URL,
            max_bytes=64 * 1024,
            error_code="CHATGPT_DISCOVERY_FAILED",
        )
        if not isinstance(data, dict) or data.get("issuer") != ISSUER:
            raise CoreDomainError(
                "CHATGPT_DISCOVERY_INVALID", "OpenAI identity metadata is invalid."
            )
        for field in ("jwks_uri", "revocation_endpoint"):
            _require_auth_endpoint(data.get(field))
        self._discovery_cache = (self._monotonic() + 3600.0, data)
        return data

    def _jwks(self) -> dict[str, Any]:
        cached = self._jwks_cache
        if cached and cached[0] > self._monotonic():
            return cached[1]
        url = cast(str, self._discovery()["jwks_uri"])
        data = self._request_json(
            "GET",
            url,
            max_bytes=128 * 1024,
            error_code="CHATGPT_JWKS_FAILED",
        )
        if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
            raise CoreDomainError("CHATGPT_JWKS_INVALID", "OpenAI signing keys are invalid.")
        self._jwks_cache = (self._monotonic() + 3600.0, data)
        return data

    def _access_token_for(self, account_id: str, *, force_refresh: bool = False) -> str:
        with self._refresh_lock:
            with self._lock:
                vault = self._read_vault()
                account = _find_account(vault, account_id)
                if not _is_connected(account):
                    raise CoreDomainError(
                        "CHATGPT_ACCOUNT_NOT_CONNECTED",
                        "Sign in with ChatGPT and allow plan usage before using this provider.",
                    )
                assert account is not None
                if not force_refresh and account["expires_at"] > self._clock() + 60:
                    return cast(str, account["access_token"])
                client_id = account["client_id"]
                refresh_token = account["refresh_token"]
            response = self._request_json(
                "POST",
                TOKEN_ENDPOINT,
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "refresh_token": refresh_token,
                    "resource": RESOURCE,
                },
                max_bytes=MAX_AUTH_RESPONSE_BYTES,
                error_code="CHATGPT_TOKEN_REFRESH_FAILED",
            )
            refreshed = _validate_refresh_response(response)
            with self._lock:
                vault = self._read_vault()
                account = _find_account(vault, account_id)
                if (
                    account is None
                    or not _is_connected(account)
                    or account["client_id"] != client_id
                ):
                    raise CoreDomainError(
                        "CHATGPT_ACCOUNT_NOT_CONNECTED",
                        "The selected ChatGPT account is no longer connected.",
                    )
                assert account is not None
                scopes = refreshed["scopes"] or account["scopes"]
                if "chatgpt.tokens.use.direct" not in scopes:
                    raise CoreDomainError(
                        "CHATGPT_PLAN_PERMISSION_REQUIRED",
                        "ChatGPT plan usage permission is no longer available.",
                    )
                account.update(
                    {
                        "access_token": refreshed["access_token"],
                        "refresh_token": refreshed["refresh_token"] or account["refresh_token"],
                        "expires_at": self._clock() + refreshed["expires_in"],
                        "scopes": scopes,
                        "saved_at": int(self._clock()),
                    }
                )
                self._write_vault(vault)
                self._model_cache.pop(account_id, None)
                return cast(str, account["access_token"])

    def _revoke(self, client_id: str, refresh_token: str) -> bool:
        try:
            endpoint = cast(str, self._discovery()["revocation_endpoint"])
        except CoreDomainError:
            return False
        for attempt in range(3):
            try:
                with self._http_client_factory() as client:
                    response = client.post(
                        endpoint,
                        data={
                            "token": refresh_token,
                            "token_type_hint": "refresh_token",
                            "client_id": client_id,
                        },
                    )
                if response.status_code == 200:
                    return True
                if response.status_code < 500 and response.status_code != 429:
                    return False
            except httpx.HTTPError:
                pass
            if attempt < 2:
                time.sleep(0.1 * (2**attempt))
        return False

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        max_bytes: int,
        error_code: str,
    ) -> Any:
        if not _is_allowed_url(url):
            raise CoreDomainError(error_code, "The OpenAI endpoint is not trusted.")
        try:
            with self._http_client_factory() as client:
                with client.stream(method, url, headers=headers, data=data) as response:
                    if response.status_code < 200 or response.status_code >= 300:
                        raise _http_error(error_code, response.status_code)
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            raise CoreDomainError(
                                error_code, "The OpenAI response exceeded the safe size limit."
                            )
        except CoreDomainError:
            raise
        except (httpx.HTTPError, OSError, ValueError) as error:
            raise CoreDomainError(
                error_code,
                "The OpenAI identity service could not be reached.",
                retryable=True,
            ) from error
        try:
            result = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CoreDomainError(error_code, "The OpenAI response was invalid JSON.") from error
        if not isinstance(result, dict):
            raise CoreDomainError(error_code, "The OpenAI response was invalid JSON.")
        return cast(dict[str, Any], result)

    def _read_vault(self) -> dict[str, Any]:
        try:
            raw = self._store.read()
        except (CredentialStoreUnavailable, OSError) as error:
            raise CoreDomainError(
                "CHATGPT_CREDENTIAL_STORE_UNAVAILABLE",
                "The protected ChatGPT token vault could not be read.",
                retryable=True,
            ) from error
        if raw is None:
            return self._empty_vault()
        if not isinstance(raw, str) or len(raw) > MAX_CHATGPT_PLAN_VAULT_CHARS:
            raise CoreDomainError(
                "CHATGPT_VAULT_INVALID", "The protected ChatGPT token vault is invalid."
            )
        try:
            vault = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise CoreDomainError(
                "CHATGPT_VAULT_INVALID", "The protected ChatGPT token vault is invalid."
            ) from error
        _validate_vault(vault)
        self._vault_cache = vault
        return cast(dict[str, Any], vault)

    def _write_vault(self, vault: dict[str, Any]) -> None:
        _validate_vault(vault)
        try:
            raw = json.dumps(vault, ensure_ascii=False, separators=(",", ":"))
            if len(raw) > MAX_CHATGPT_PLAN_VAULT_CHARS:
                raise ValueError("ChatGPT token vault exceeded its safe size limit")
            self._store.write(raw)
        except (CredentialStoreUnavailable, OSError) as error:
            raise CoreDomainError(
                "CHATGPT_CREDENTIAL_STORE_UNAVAILABLE",
                "The protected ChatGPT token vault could not be saved.",
                retryable=True,
            ) from error
        except ValueError as error:
            raise CoreDomainError(
                "CHATGPT_VAULT_INVALID",
                "The protected ChatGPT token vault exceeds its safe size limit.",
            ) from error
        self._vault_cache = vault

    @staticmethod
    def _empty_vault() -> dict[str, Any]:
        return {
            "version": 1,
            "host_id": f"urn:uuid:{uuid.uuid4()}",
            "active_account_id": None,
            "accounts": [],
        }


class _CallbackCapture:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.code: str | None = None
        self.error: str | None = None
        self.client_id: str | None = None


def _callback_server(
    owner: ChatGPTPlanAuthService, target_account_id: str | None
) -> http.server.HTTPServer:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlsplit(self.path)
            if parsed.path != "/auth/callback":
                self._respond(404, "This Presenter Copilot sign-in callback is not available.")
                return
            try:
                values = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=12)
            except ValueError:
                self._respond(
                    400, "The sign-in response could not be validated. Return to Presenter Copilot."
                )
                return
            allowed = {"code", "state", "error", "scope", "client_id"}
            if set(values).difference(allowed) or any(len(items) != 1 for items in values.values()):
                self._respond(
                    400, "The sign-in response could not be validated. Return to Presenter Copilot."
                )
                return
            attempt = owner._pending
            state = values.get("state", [""])[0]
            capture = getattr(self.server, "_presenter_callback_capture", None)
            if (
                attempt is None
                or attempt.target_account_id != target_account_id
                or not secrets.compare_digest(state, attempt.state)
                or not isinstance(capture, _CallbackCapture)
            ):
                self._respond(
                    400, "The sign-in response could not be validated. Return to Presenter Copilot."
                )
                return
            code = values.get("code", [""])[0]
            error = values.get("error", [""])[0]
            client_id = values.get("client_id", [""])[0]
            if (not code and not error) or len(code) > MAX_CODE_CHARS or len(error) > 128:
                self._respond(
                    400, "The sign-in response could not be validated. Return to Presenter Copilot."
                )
                return
            capture.code = code or None
            capture.error = error or None
            capture.client_id = client_id or None
            capture.done.set()
            self._respond(200, "Sign-in response received. Return to Presenter Copilot.")

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._respond(405, "This Presenter Copilot sign-in callback is not available.")

        def log_message(self, _format: str, *args: Any) -> None:
            # The request target contains the short-lived authorization code.
            return

        def _respond(self, status: int, message: str) -> None:
            body = (
                "<!doctype html><meta charset=utf-8><title>Presenter Copilot</title>"
                f"<p>{message}</p>"
            ).encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

    class Server(http.server.HTTPServer):
        allow_reuse_address = False
        request_queue_size = 4

    return Server(("127.0.0.1", 0), Handler)


def _validate_token_response(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CoreDomainError(
            "CHATGPT_TOKEN_RESPONSE_INVALID", "ChatGPT returned invalid sign-in credentials."
        )
    access = value.get("access_token")
    refresh = value.get("refresh_token")
    id_token = value.get("id_token")
    token_type = value.get("token_type")
    expires_in = value.get("expires_in")
    scope = value.get("scope")
    if (
        not _valid_token(access)
        or not _valid_token(refresh)
        or not _valid_token(id_token)
        or not isinstance(token_type, str)
        or token_type.casefold() != "bearer"
        or isinstance(expires_in, bool)
        or not isinstance(expires_in, int)
        or not 60 <= expires_in <= 86_400
        or not isinstance(scope, str)
        or len(scope) > 2048
    ):
        raise CoreDomainError(
            "CHATGPT_TOKEN_RESPONSE_INVALID", "ChatGPT returned invalid sign-in credentials."
        )
    scopes = sorted(set(scope.split()))
    return {
        "access_token": access,
        "refresh_token": refresh,
        "id_token": id_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scopes": scopes,
    }


def _validate_refresh_response(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CoreDomainError("CHATGPT_TOKEN_REFRESH_FAILED", "ChatGPT could not renew sign-in.")
    access = value.get("access_token")
    refresh = value.get("refresh_token")
    expires_in = value.get("expires_in")
    scope = value.get("scope")
    token_type = value.get("token_type", "Bearer")
    if (
        not _valid_token(access)
        or (refresh is not None and not _valid_token(refresh))
        or isinstance(expires_in, bool)
        or not isinstance(expires_in, int)
        or not 60 <= expires_in <= 86_400
        or not isinstance(token_type, str)
        or token_type.casefold() != "bearer"
        or (scope is not None and (not isinstance(scope, str) or len(scope) > 2048))
    ):
        raise CoreDomainError("CHATGPT_TOKEN_REFRESH_FAILED", "ChatGPT could not renew sign-in.")
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": expires_in,
        "scopes": sorted(set(scope.split())) if isinstance(scope, str) else None,
    }


def _validate_vault(value: Any) -> None:
    host_id = value.get("host_id") if isinstance(value, dict) else None
    try:
        host_uuid = (
            uuid.UUID(host_id.removeprefix("urn:uuid:")) if isinstance(host_id, str) else None
        )
    except (ValueError, AttributeError):
        host_uuid = None
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "host_id", "active_account_id", "accounts"}
        or value.get("version") != 1
        or not isinstance(host_uuid, uuid.UUID)
        or host_id != f"urn:uuid:{host_uuid}"
        or not isinstance(value.get("accounts"), list)
        or len(value["accounts"]) > 32
    ):
        raise CoreDomainError(
            "CHATGPT_VAULT_INVALID", "The protected ChatGPT token vault is invalid."
        )
    seen: set[str] = set()
    for account in value["accounts"]:
        base_fields = {"account_id", "issuer", "subject", "client_id", "email"}
        token_fields = {
            "id_token",
            "access_token",
            "refresh_token",
            "expires_at",
            "scopes",
        }
        allowed_fields = base_fields | token_fields | {"saved_at"}
        if (
            not isinstance(account, dict)
            or not set(account).issubset(allowed_fields)
            or not base_fields.issubset(account)
            or not isinstance(account.get("account_id"), str)
            or not isinstance(account.get("client_id"), str)
            or not _valid_client_id(account["client_id"])
            or account.get("issuer") != ISSUER
            or not isinstance(account.get("subject"), str)
            or not account["subject"]
            or len(account["subject"]) > 512
            or account["account_id"] in seen
        ):
            raise CoreDomainError(
                "CHATGPT_VAULT_INVALID", "The protected ChatGPT token vault is invalid."
            )
        try:
            parsed_account_id = uuid.UUID(account["account_id"])
        except (ValueError, AttributeError):
            parsed_account_id = None
        if (
            not isinstance(parsed_account_id, uuid.UUID)
            or str(parsed_account_id) != account["account_id"]
        ):
            raise CoreDomainError(
                "CHATGPT_VAULT_INVALID", "The protected ChatGPT token vault is invalid."
            )
        seen.add(account["account_id"])
        email = account.get("email")
        if email is not None and (
            not isinstance(email, str) or len(email) > 320 or any(ord(c) < 32 for c in email)
        ):
            raise CoreDomainError(
                "CHATGPT_VAULT_INVALID", "The protected ChatGPT token vault is invalid."
            )
        present = token_fields.intersection(account)
        if present and (present != token_fields or not _is_connected(account)):
            raise CoreDomainError(
                "CHATGPT_VAULT_INVALID", "The protected ChatGPT token vault is invalid."
            )
        if "saved_at" in account and (
            not isinstance(account["saved_at"], int) or isinstance(account["saved_at"], bool)
        ):
            raise CoreDomainError(
                "CHATGPT_VAULT_INVALID", "The protected ChatGPT token vault is invalid."
            )
    active_id = value.get("active_account_id")
    if active_id is not None and (not isinstance(active_id, str) or active_id not in seen):
        raise CoreDomainError(
            "CHATGPT_VAULT_INVALID", "The protected ChatGPT token vault is invalid."
        )


def _is_connected(account: Any) -> bool:
    return (
        isinstance(account, dict)
        and all(
            _valid_token(account.get(key)) for key in ("id_token", "access_token", "refresh_token")
        )
        and isinstance(account.get("expires_at"), (int, float))
        and not isinstance(account.get("expires_at"), bool)
        and isinstance(account.get("scopes"), list)
        and all(isinstance(scope, str) and len(scope) <= 128 for scope in account["scopes"])
        and isinstance(account.get("saved_at"), int)
        and "chatgpt.tokens.use.direct" in account["scopes"]
    )


def _find_account(vault: dict[str, Any], account_id: Any) -> dict[str, Any] | None:
    if not isinstance(account_id, str):
        return None
    return next(
        (account for account in vault["accounts"] if account.get("account_id") == account_id),
        None,
    )


def _valid_token(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= MAX_ACCESS_TOKEN_CHARS
        and all(ord(character) >= 33 and ord(character) <= 126 for character in value)
    )


def _valid_client_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 8 <= len(value) <= 256
        and value.startswith("oaiapp_")
        and all(character.isalnum() or character in "_-" for character in value)
    )


def _jwks_key(jwks: Mapping[str, Any], kid: str) -> dict[str, Any] | None:
    keys = jwks.get("keys")
    if not isinstance(keys, list) or len(keys) > 32:
        return None
    for key in keys:
        if (
            isinstance(key, dict)
            and key.get("kid") == kid
            and key.get("kty") == "RSA"
            and key.get("use", "sig") == "sig"
            and key.get("alg", "RS256") == "RS256"
        ):
            return key
    return None


def _require_auth_endpoint(value: Any) -> None:
    if not _is_allowed_url(value) or urlsplit(value).hostname != "auth.openai.com":
        raise CoreDomainError("CHATGPT_DISCOVERY_INVALID", "OpenAI identity metadata is invalid.")


def _is_allowed_url(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 2_048:
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and parsed.hostname in {"auth.openai.com", "api.openai.com"}
            and parsed.port in {None, 443}
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
        )
    except ValueError:
        return False


def _http_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(5.0, connect=3.0),
        follow_redirects=False,
        trust_env=False,
    )


def _http_error(code: str, status_code: int) -> CoreDomainError:
    if status_code == 401:
        code = "CHATGPT_AUTH_REJECTED"
        message = "OpenAI rejected the ChatGPT plan credential. Sign in again."
    elif status_code == 429:
        code = "CHATGPT_RATE_LIMITED"
        message = "The ChatGPT plan usage limit or rate limit was reached."
    elif status_code >= 500:
        message = "The OpenAI service is temporarily unavailable."
    else:
        message = "The OpenAI service rejected the request."
    return CoreDomainError(code, message, retryable=status_code == 429 or status_code >= 500)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
