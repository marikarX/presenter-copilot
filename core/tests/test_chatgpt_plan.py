"""Synthetic Sign in with ChatGPT and plan-decision contract tests."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from presenter_core.credentials import (
    ChatGPTPlanCredentialStore,
    InMemoryChatGPTPlanCredentialStore,
)
from presenter_core.decisions import ChoiceDecisionRequest, ChoiceQuestion, DecisionError
from presenter_core.decisions.openai_chatgpt_plan import (
    RESPONSES_ENDPOINT,
    OpenAIChatGPTPlanDecisionProvider,
)
from presenter_core.errors import CoreDomainError
from presenter_core.providers.chatgpt_plan_auth import (
    APP_NAME,
    AUTHORIZE_ENDPOINT,
    DISCOVERY_URL,
    ISSUER,
    MODEL_LIST_ENDPOINT,
    OAUTH_SCOPE,
    RESOURCE,
    TOKEN_ENDPOINT,
    ChatGPTPlanAuthService,
    _CallbackCapture,
    _SignInAttempt,
)


def _decision_request() -> ChoiceDecisionRequest:
    return ChoiceDecisionRequest(
        state={"slide_text": ["Revenue grew 12 percent."]},
        questions=(
            ChoiceQuestion(
                name="slide_purpose",
                instructions="Choose the best supported purpose for this slide.",
                criteria={
                    "decision": "The slide asks for a decision.",
                    "evidence": "The slide provides supporting evidence.",
                },
            ),
        ),
    )


class _OAuthHarness:
    def __init__(self, *, scope: str = OAUTH_SCOPE) -> None:
        self.scope = scope
        self.opened_urls: list[str] = []
        self.exchanges: list[dict[str, list[str]]] = []
        self.revocations: list[dict[str, list[str]]] = []
        self.refreshes: list[dict[str, list[str]]] = []
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_jwk = json.loads(
            jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key())
        )
        self.public_jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
        self.transport = httpx.MockTransport(self._handle)
        self.auth: ChatGPTPlanAuthService | None = None

    def client(self) -> httpx.Client:
        return httpx.Client(
            transport=self.transport,
            timeout=5,
            follow_redirects=False,
            trust_env=False,
        )

    def open_browser(self, url: str) -> bool:
        self.opened_urls.append(url)
        return True

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == DISCOVERY_URL:
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "jwks_uri": f"{ISSUER}/oauth/jwks",
                    "revocation_endpoint": f"{ISSUER}/api/accounts/oauth/revoke",
                },
                request=request,
            )
        if request.url.path == "/oauth/jwks":
            return httpx.Response(200, json={"keys": [self.public_jwk]}, request=request)
        if str(request.url) == TOKEN_ENDPOINT:
            form = parse_qs(request.content.decode("utf-8"))
            if form.get("grant_type") == ["authorization_code"]:
                self.exchanges.append(form)
                client_id = form["client_id"][0]
                verifier = form["code_verifier"][0]
                authorize_query = parse_qs(urlsplit(self.opened_urls[-1]).query)
                expected_challenge = (
                    base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
                    .rstrip(b"=")
                    .decode("ascii")
                )
                if authorize_query.get("code_challenge") != [expected_challenge]:
                    return httpx.Response(400, json={"error": "invalid_grant"}, request=request)
                identity_token = jwt.encode(
                    {
                        "iss": ISSUER,
                        "aud": client_id,
                        "sub": f"subject-{client_id}",
                        "email": f"{client_id}@example.test",
                        "iat": int(time.time()),
                        "exp": int(time.time()) + 3_600,
                        "nonce": authorize_query["nonce"][0],
                    },
                    self.private_key,
                    algorithm="RS256",
                    headers={"kid": "test-key"},
                )
                return httpx.Response(
                    200,
                    json={
                        "access_token": f"access-{client_id}",
                        "refresh_token": f"refresh-{client_id}",
                        "id_token": identity_token,
                        "token_type": "Bearer",
                        "expires_in": 3_600,
                        "scope": self.scope,
                    },
                    request=request,
                )
            self.refreshes.append(form)
            return httpx.Response(
                200,
                json={
                    "access_token": "rotated-access-token",
                    "refresh_token": "rotated-refresh-token",
                    "token_type": "Bearer",
                    "expires_in": 3_600,
                    "scope": self.scope,
                },
                request=request,
            )
        if request.url.path == "/api/accounts/oauth/revoke":
            self.revocations.append(parse_qs(request.content.decode("utf-8")))
            return httpx.Response(200, request=request)
        if str(request.url) == MODEL_LIST_ENDPOINT:
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"slug": "gpt-6-luna", "display_name": "GPT-6 Luna", "visibility": "list"},
                        {
                            "slug": "hidden-preview",
                            "display_name": "Hidden",
                            "visibility": "internal",
                        },
                    ]
                },
                request=request,
            )
        return httpx.Response(404, json={"error": "not_found"}, request=request)

    def make_auth(self, store: InMemoryChatGPTPlanCredentialStore) -> ChatGPTPlanAuthService:
        self.auth = ChatGPTPlanAuthService(
            Path("unused-test-root"),
            store,
            http_client_factory=self.client,
            browser_open=self.open_browser,
        )
        return self.auth

    def wait_for_browser_url(self) -> str:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.opened_urls:
                return self.opened_urls[-1]
            time.sleep(0.01)
        raise AssertionError("The OAuth flow did not open the browser")

    def complete_login(self, client_id: str) -> None:
        authorize_url = self.wait_for_browser_url()
        query = parse_qs(urlsplit(authorize_url).query)
        assert urlsplit(authorize_url).scheme == "https"
        assert urlsplit(authorize_url).netloc == "auth.openai.com"
        assert urlsplit(authorize_url).path == urlsplit(AUTHORIZE_ENDPOINT).path
        assert query["client_id"] == ["dynamic_agent_client"]
        assert query["agent_name_hint"] == [APP_NAME]
        assert query["scope"] == [OAUTH_SCOPE]
        assert query["resource"] == [RESOURCE]
        callback = _callback_url(query, code="test-code", client_id=client_id)
        with urlopen(callback, timeout=3) as response:  # noqa: S310 - loopback URI from the app
            assert response.status == 200
            assert b"Return to Presenter Copilot" in response.read()
        status = self.wait_for_status()
        assert status["state"] == "signed_in", status

    def wait_for_status(self) -> dict[str, Any]:
        assert self.auth is not None
        deadline = time.monotonic() + 3
        status = self.auth.status()
        while status["state"] == "signing_in" and time.monotonic() < deadline:
            time.sleep(0.01)
            status = self.auth.status()
        return status


def test_chatgpt_plan_auth_keeps_accounts_separate_refreshes_and_signs_out() -> None:
    harness = _OAuthHarness()
    store = InMemoryChatGPTPlanCredentialStore()
    auth = harness.make_auth(store)
    try:
        assert auth.sign_in()["state"] == "signing_in"
        harness.complete_login("oaiapp_presenter_one")
        first_status = auth.status()
        first_id = first_status["active_account_id"]
        assert len(first_status["accounts"]) == 1
        assert first_status["accounts"][0]["email"] == "oaiapp_presenter_one@example.test"

        assert auth.sign_in()["state"] == "signing_in"
        assert auth.status()["active_account_id"] == first_id
        harness.complete_login("oaiapp_presenter_two")
        two_accounts = auth.status()
        assert len(two_accounts["accounts"]) == 2
        assert two_accounts["active_account_id"] != first_id
        assert {item["email"] for item in two_accounts["accounts"]} == {
            "oaiapp_presenter_one@example.test",
            "oaiapp_presenter_two@example.test",
        }

        selected = auth.select_account({"account_id": first_id})
        assert selected["active_account_id"] == first_id
        assert auth.model_options() == [{"model_id": "gpt-6-luna", "label": "GPT-6 Luna"}]

        vault = json.loads(store.read() or "{}")
        first = next(item for item in vault["accounts"] if item["account_id"] == first_id)
        first["expires_at"] = time.time() - 1
        store.write(json.dumps(vault, separators=(",", ":")))
        assert auth.access_token() == "rotated-access-token"
        refreshed = json.loads(store.read() or "{}")
        first = next(item for item in refreshed["accounts"] if item["account_id"] == first_id)
        assert first["refresh_token"] == "rotated-refresh-token"
        assert len(harness.refreshes) == 1

        first_authorize_query = parse_qs(urlsplit(harness.opened_urls[0]).query)
        assert harness.exchanges[0]["redirect_uri"] == first_authorize_query["redirect_uri"]
        assert "dynamic_agent_client" not in [item["client_id"] for item in refreshed["accounts"]]
        assert all(
            "access_token" not in item and "refresh_token" not in item
            for item in auth.status()["accounts"]
        )
        signed_out = auth.sign_out()
        assert signed_out["remote_revocation_confirmed"] is True
        assert auth.status()["state"] == "signed_out"
        assert len(harness.revocations) == 1
        assert auth.status()["accounts"][0]["connected"] is False
    finally:
        auth.close()


def test_chatgpt_plan_auth_does_not_store_tokens_without_plan_permission() -> None:
    harness = _OAuthHarness(scope="openid profile email offline_access resource.invoke")
    store = InMemoryChatGPTPlanCredentialStore()
    auth = harness.make_auth(store)
    try:
        auth.sign_in()
        status = harness.wait_for_browser_url()
        query = parse_qs(urlsplit(status).query)
        callback = _callback_url(query, code="test-code", client_id="oaiapp_no_plan")
        with urlopen(callback, timeout=3) as response:  # noqa: S310 - loopback URI from the app
            assert response.status == 200
            response.read()
        result = harness.wait_for_status()
        assert result["state"] == "error"
        assert result["error_code"] == "CHATGPT_PLAN_PERMISSION_REQUIRED"
        assert result["accounts"] == []
        saved = json.loads(store.read() or "{}")
        assert saved["accounts"] == []
    finally:
        auth.close()


def test_chatgpt_plan_auth_rejects_wrong_state_and_cancels_pending_login() -> None:
    harness = _OAuthHarness()
    store = InMemoryChatGPTPlanCredentialStore()
    auth = harness.make_auth(store)
    try:
        auth.sign_in()
        authorize_url = harness.wait_for_browser_url()
        query = parse_qs(urlsplit(authorize_url).query)
        callback = _callback_url(
            query, code="test-code", client_id="oaiapp_rejected", state="wrong-state"
        )
        try:
            urlopen(callback, timeout=3)  # noqa: S310 - loopback URI from the app
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("A callback with the wrong OAuth state was accepted")
        auth.cancel_sign_in()
        result = harness.wait_for_status()
        assert result["state"] == "error"
        assert result["error_code"] == "CHATGPT_LOGIN_CANCELLED"
        assert not harness.exchanges
    finally:
        auth.close()


def test_chatgpt_plan_auth_does_not_persist_if_cancel_arrives_before_vault_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryChatGPTPlanCredentialStore()
    auth = ChatGPTPlanAuthService(Path("unused-test-root"), store)
    vault = auth._empty_vault()
    store.write(json.dumps(vault, separators=(",", ":")))
    attempt = _SignInAttempt(
        state="test-state",
        nonce="test-nonce",
        verifier="test-verifier",
        redirect_uri="http://127.0.0.1:12345/auth/callback",
        client_id="dynamic_agent_client",
        host_id=vault["host_id"],
        target_account_id=None,
        started_at=time.monotonic(),
    )
    callback = _CallbackCapture()
    callback.code = "authorization-code"
    callback.client_id = "oaiapp_testclient"
    cancellation_checks = 0

    def cancel_at_commit_boundary() -> bool:
        nonlocal cancellation_checks
        cancellation_checks += 1
        return cancellation_checks >= 4

    monkeypatch.setattr(auth._cancel_pending, "is_set", cancel_at_commit_boundary)
    monkeypatch.setattr(
        auth,
        "_request_json",
        lambda *_args, **_kwargs: {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "id_token": "identity-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": OAUTH_SCOPE,
        },
    )
    monkeypatch.setattr(
        auth,
        "_validate_id_token",
        lambda *_args: {"sub": "subject-1", "email": "person@example.test"},
    )

    with pytest.raises(CoreDomainError) as error:
        auth._complete_authorization(attempt, callback)

    assert error.value.code == "CHATGPT_LOGIN_CANCELLED"
    assert json.loads(store.read() or "{}")["accounts"] == []


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI integration")
def test_chatgpt_plan_vault_roundtrips_under_windows_dpapi(tmp_path: Path) -> None:
    store = ChatGPTPlanCredentialStore(tmp_path)
    assert store.is_available()
    value = json.dumps(
        {
            "version": 1,
            "host_id": f"urn:uuid:{uuid.uuid4()}",
            "active_account_id": None,
            "accounts": [],
        },
        separators=(",", ":"),
    )

    store.write(value)

    path = tmp_path / "chatgpt-plan-credentials.dpapi"
    encrypted = path.read_bytes()
    assert value.encode("utf-8") not in encrypted
    assert store.read() == value
    assert store.delete() is True
    assert store.read() is None


def _callback_url(
    query: dict[str, list[str]],
    *,
    code: str,
    client_id: str,
    state: str | None = None,
) -> str:
    params = {
        "code": code,
        "state": state or query["state"][0],
        "client_id": client_id,
    }
    return f"{query['redirect_uri'][0]}?{urlencode(params)}"


def _sse(events: list[dict[str, Any]]) -> bytes:
    return b"".join(
        f"data: {json.dumps(event, separators=(',', ':'))}\n\n".encode() for event in events
    )


def test_chatgpt_plan_decision_uses_preview_safe_stream_payload() -> None:
    captured: list[dict[str, Any]] = []
    output = json.dumps({"slide_purpose": {"choice": "evidence"}}, separators=(",", ":"))
    stream = _sse(
        [
            {"type": "response.output_text.delta", "delta": output},
            {
                "type": "response.completed",
                "response": {"status": "completed", "model": "gpt-6-luna"},
            },
        ]
    )

    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == RESPONSES_ENDPOINT
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=stream, request=request)

    provider = OpenAIChatGPTPlanDecisionProvider(
        access_token_resolver=lambda: "synthetic-access-token",
        model_id="gpt-6-luna",
        client_factory=lambda: httpx.Client(
            transport=httpx.MockTransport(handle), follow_redirects=False, trust_env=False
        ),
    )
    result = provider.decide(_decision_request())
    assert result.answers["slide_purpose"].choice == "evidence"
    assert result.provider_id == "openai_chatgpt_plan"
    payload = captured[0]
    assert payload["model"] == "gpt-6-luna"
    assert payload["store"] is False
    assert payload["stream"] is True
    assert payload["tools"] == []
    assert payload["input"] == [
        {"role": "user", "content": _decision_request().serialized_request()}
    ]
    assert "max_output_tokens" not in payload
    assert "previous_response_id" not in payload
    assert all(item["role"] != "system" for item in payload["input"])


def test_chatgpt_plan_decision_requires_completed_stream_and_maps_shared_quota() -> None:
    def make_provider(events: list[dict[str, Any]]) -> OpenAIChatGPTPlanDecisionProvider:
        stream = _sse(events)

        def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=stream, request=request)

        return OpenAIChatGPTPlanDecisionProvider(
            access_token_resolver=lambda: "synthetic-access-token",
            model_id="gpt-6-luna",
            client_factory=lambda: httpx.Client(
                transport=httpx.MockTransport(handle), follow_redirects=False, trust_env=False
            ),
        )

    with pytest.raises(DecisionError) as incomplete:
        make_provider(
            [{"type": "response.output_text.delta", "delta": '{"slide_purpose":'}]
        ).decide(_decision_request())
    assert incomplete.value.code == "DECISION_PROVIDER_INCOMPLETE"

    with pytest.raises(DecisionError) as quota:
        make_provider(
            [
                {
                    "type": "response.failed",
                    "response": {"error": {"code": "subscription_sharing_usage_limit_exceeded"}},
                }
            ]
        ).decide(_decision_request())
    assert quota.value.code == "DECISION_PROVIDER_QUOTA_EXCEEDED"
