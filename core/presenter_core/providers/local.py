"""Core-owned, bounded Chat Completions transport for explicitly local servers."""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
from threading import Event, Lock, Timer
from time import monotonic
from urllib.parse import urlsplit

from .models import ProviderError, ProviderHealth, ProviderInvocation, ReasoningResult
from .openai import OpenAIReasoningProvider

MAX_RESPONSE_BYTES = 65_536


def validate_endpoint(value: object) -> tuple[str, bool]:
    """Accept literal loopback/RFC1918/ULA addresses; never resolve arbitrary DNS."""
    message = "Use an HTTP(S) loopback or private IP base URL without credentials or query."
    try:
        if not isinstance(value, str) or len(value) > 512 or not value:
            raise ValueError
        if any(ord(c) <= 32 or ord(c) >= 127 for c in value) or "\\" in value:
            raise ValueError
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or "?" in value
            or "#" in value
            or "%" in value
        ):
            raise ValueError
        host = "127.0.0.1" if url.hostname == "localhost" else url.hostname
        address = ipaddress.ip_address(host)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            raise ValueError
        private = any(
            address in ipaddress.ip_network(network)
            for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
        )
        if not address.is_loopback and not private:
            raise ValueError
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError
        if any(part in {".", ".."} for part in url.path.split("/")):
            raise ValueError
        authority = f"[{address}]" if address.version == 6 else str(address)
        if url.port is not None:
            authority += f":{url.port}"
        return f"{url.scheme}://{authority}{url.path.rstrip('/')}", address.is_loopback
    except (ValueError, TypeError) as error:
        raise ProviderError("PROVIDER_ENDPOINT_INVALID", message) from error


class LocalReasoningProvider(OpenAIReasoningProvider):
    """Share task capabilities/errors, but never use the cloud SDK or its credentials."""

    id = "local_openai"
    locality = "local"

    def __init__(self, *, endpoint: str = "", model_id: str = "") -> None:
        super().__init__(model_id=model_id)
        self._connections: set[socket.socket] = set()
        self._connections_lock = Lock()
        self._closed = Event()
        self.endpoint = ""
        self._loopback = False
        if endpoint:
            self.endpoint, self._loopback = validate_endpoint(endpoint)

    @property
    def leaves_machine(self) -> bool:
        return not self._loopback

    def health(self) -> ProviderHealth:
        configured = bool(self.endpoint and self.model_id)
        return ProviderHealth(
            provider_id=self.id,
            locality=self.locality,
            model_id=self.model_id,
            configured=configured,
            status="unavailable" if configured else "unconfigured",
            error_code="PROVIDER_NOT_TESTED" if configured else "PROVIDER_UNCONFIGURED",
            retryable=configured,
        )

    def close(self) -> None:
        """Shutdown interrupts only this adapter's active connections."""
        with self._connections_lock:
            self._closed.set()
            connections = tuple(self._connections)
        for connection in connections:
            self._close_socket(connection)

    @staticmethod
    def _close_socket(connection: socket.socket) -> None:
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        connection.close()

    def generate(self, invocation: ProviderInvocation) -> ReasoningResult:
        from .models import validate_provider_output

        if self._closed.is_set():
            raise ProviderError("PROVIDER_CANCELLED", "The local provider was closed.")
        if not self.endpoint or not self.model_id:
            raise ProviderError("PROVIDER_UNCONFIGURED", "Configure a local endpoint and model.")
        endpoint, loopback = validate_endpoint(self.endpoint)
        request = invocation.request
        if request.privacy_mode == "local_only" and not loopback:
            raise ProviderError(
                "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED", "Local Only blocks LAN inference."
            )
        url = urlsplit(endpoint)
        timeout = self._effective_timeout_seconds(request)
        connection_type = (
            http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
        )
        connection = connection_type(url.hostname or "", url.port, timeout=timeout)
        headers = {"Content-Type": "application/json"}
        credential = os.environ.get("PRESENTER_LOCAL_API_KEY")
        if credential:
            if len(credential) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in credential):
                raise ProviderError("PROVIDER_AUTH_FAILED", "Invalid local provider credential.")
            headers["Authorization"] = f"Bearer {credential}"
        body = json.dumps(
            {
                "model": self.model_id,
                "messages": [
                    {
                        "role": "system",
                        "content": request.application_policy
                        + "\n"
                        + (request.task_instruction or ""),
                    },
                    {"role": "user", "content": invocation.serialized_input()},
                ],
                "stream": False,
                "max_tokens": 2048,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.task_type,
                        "strict": True,
                        "schema": request.output_schema,
                    },
                },
            }
        ).encode("utf-8")
        started = monotonic()
        transport: socket.socket | None = None
        watchdog: Timer | None = None
        response: http.client.HTTPResponse | None = None
        try:
            connection.connect()
            transport = connection.sock
            if transport is None or monotonic() - started >= timeout:
                raise TimeoutError
            with self._connections_lock:
                if self._closed.is_set():
                    raise ProviderError("PROVIDER_CANCELLED", "The local provider was closed.")
                self._connections.add(transport)
            watchdog = Timer(timeout - (monotonic() - started), self._close_socket, (transport,))
            watchdog.daemon = True
            watchdog.start()
            connection.request("POST", url.path + "/chat/completions", body, headers)
            response = connection.getresponse()
            if self._closed.is_set():
                raise ProviderError("PROVIDER_CANCELLED", "The local provider was closed.")
            if response.status != 200:
                code = {
                    401: "PROVIDER_AUTH_FAILED",
                    403: "PROVIDER_AUTH_FAILED",
                    429: "PROVIDER_RATE_LIMITED",
                }.get(response.status, "PROVIDER_UNAVAILABLE")
                raise ProviderError(
                    code,
                    "The local provider rejected the request.",
                    retryable=response.status not in {401, 403},
                )
            data = bytearray()
            while True:
                remaining = timeout - (monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError
                # read1 returns after one underlying read, allowing a total deadline
                # even when a server drips bytes without completing the body.
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(8192, MAX_RESPONSE_BYTES + 1 - len(data)))
                if self._closed.is_set():
                    raise ProviderError("PROVIDER_CANCELLED", "The local provider was closed.")
                data.extend(chunk)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise ValueError
                if not chunk:
                    break
            packet = json.loads(data)
            choice = packet["choices"][0]
            if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
                raise ValueError
            if choice.get("finish_reason") != "stop" or choice["message"].get("tool_calls"):
                raise ValueError
            output = validate_provider_output(
                request.task_type,
                json.loads(choice["message"]["content"]),
                conflict_metadata=request.conflict_metadata,
            )
            return ReasoningResult(
                output=output,
                input_token_count=None,
                output_token_count=None,
                latency_ms=int((monotonic() - started) * 1000),
            )
        except ProviderError:
            raise
        except TimeoutError as error:
            if self._closed.is_set():
                raise ProviderError(
                    "PROVIDER_CANCELLED", "The local provider was closed."
                ) from error
            raise ProviderError(
                "PROVIDER_TIMEOUT", "The local provider timed out.", retryable=True
            ) from error
        except (OSError, http.client.HTTPException) as error:
            if self._closed.is_set():
                raise ProviderError(
                    "PROVIDER_CANCELLED", "The local provider was closed."
                ) from error
            if monotonic() - started >= timeout:
                raise ProviderError(
                    "PROVIDER_TIMEOUT", "The local provider timed out.", retryable=True
                ) from error
            raise ProviderError(
                "PROVIDER_UNAVAILABLE", "The local endpoint is unavailable.", retryable=True
            ) from error
        except (ValueError, TypeError, KeyError, IndexError) as error:
            raise ProviderError(
                "PROVIDER_MALFORMED_OUTPUT", "Invalid local structured output."
            ) from error
        finally:
            if watchdog is not None:
                watchdog.cancel()
            if response is not None:
                response.close()
            connection.close()
            with self._connections_lock:
                if transport is not None:
                    self._connections.discard(transport)
