"""Presenter-owned official Codex App Server. Authentication stays inside Codex."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import tomllib
import webbrowser
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from .codex_policy import (
    CODEX_MODEL,
    FEATURES,
    PRESENTER_POLICY,
    SUPPORTED_VERSIONS,
    runtime_config,
)
from .models import (
    TASK_CONTEXT_CLASS_ALLOWLIST,
    ProviderCapabilities,
    ProviderError,
    ProviderHealth,
    ProviderInvocation,
    ReasoningProvider,
    ReasoningResult,
    task_instruction_for,
    validate_provider_output,
)

MAX_FRAME = 1_048_576
EXPECTED_TOOLS_HASH = "d9a54d5b4e2242dfacdf694392585780497bb68be9f98cbfac801ce231ec512c"


def isolation_error() -> ProviderError:
    return ProviderError("CODEX_ISOLATION_FAILED", "Codex containment could not be verified.")


def map_turn_error(error: Any) -> ProviderError:
    info = error.get("codexErrorInfo") if isinstance(error, dict) else None
    status = None
    if isinstance(info, dict):
        for detail in info.values():
            if isinstance(detail, dict):
                status = detail.get("httpStatusCode")
    if info == "unauthorized" or status == 401:
        return ProviderError("PROVIDER_AUTH_FAILED", "ChatGPT authentication was rejected.")
    if info in ("usageLimitExceeded", "sessionBudgetExceeded"):
        return ProviderError("PROVIDER_QUOTA_EXCEEDED", "ChatGPT usage limit reached.")
    if info == "rateLimitExceeded" or status == 429:
        return ProviderError("PROVIDER_RATE_LIMITED", "ChatGPT rate limit reached.", retryable=True)
    if info == "badRequest":
        message = error.get("message", "") if isinstance(error, dict) else ""
        if isinstance(message, str) and "schema" in message.casefold():
            return ProviderError("CODEX_SCHEMA_REJECTED", "Codex rejected the output schema.")
        return ProviderError("CODEX_BAD_REQUEST", "Codex rejected the inference configuration.")
    return ProviderError("PROVIDER_REQUEST_FAILED", "Codex reasoning failed.", retryable=True)


def validate_observed_tools(tools: Any) -> None:
    """Used by the pinned-runtime probe, not an invented live catalog RPC."""
    if not isinstance(tools, list):
        raise isolation_error()
    if (
        tools
        and hashlib.sha256(
            json.dumps(tools, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        != EXPECTED_TOOLS_HASH
    ):
        raise isolation_error()
    for namespace in tools:
        if not isinstance(namespace, dict) or namespace.get("name") != "skills":
            raise isolation_error()
        if namespace.get("type") != "namespace":
            raise isolation_error()
        functions = namespace.get("tools")
        if not isinstance(functions, list) or not functions:
            raise isolation_error()
        if any(
            not isinstance(tool, dict)
            or tool.get("type") != "function"
            or tool.get("name") not in {"list", "read"}
            for tool in functions
        ):
            raise isolation_error()


def minimal_environment(root: Path) -> dict[str, str]:
    # No inherited CODEX_*, OPENAI_*, proxies, PATH, or user profile locations.
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    for key, subdir in {
        "CODEX_HOME": "home",
        "HOME": "profile",
        "USERPROFILE": "profile",
        "APPDATA": "profile/appdata",
        "LOCALAPPDATA": "profile/localappdata",
        "TEMP": "tmp",
        "TMP": "tmp",
    }.items():
        path = root / subdir
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    return env


class AppServer:
    """Bounded stdio transport, one owner, no renderer or general-purpose RPC access."""

    def __init__(self, executable: str | None = None) -> None:
        candidate = (
            executable or os.environ.get("PRESENTER_CODEX_EXECUTABLE") or shutil.which("codex")
        )
        if not candidate or not Path(candidate).is_file():
            raise ProviderError(
                "CODEX_NOT_INSTALLED", "Install a supported official Codex runtime."
            )
        self._temporary = tempfile.TemporaryDirectory(prefix="presenter-codex-")
        self.root = Path(self._temporary.name).resolve()
        self.cwd = self.root / "empty"
        self.cwd.mkdir()
        self.env = minimal_environment(self.root)
        self.home = self.root / "home"
        self.config = runtime_config()
        (self.home / "config.toml").write_text(self.config, encoding="utf-8")
        self._closed = False
        self._fault = threading.Event()
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._serial = 0
        self.events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1024)
        self.login_result: tuple[str | None, bool] | None = None
        self.process: subprocess.Popen[bytes] | None = None
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            path = str(Path(candidate).resolve())
            version = (
                subprocess.run(
                    [path, "--version"],
                    cwd=self.cwd,
                    env=self.env,
                    capture_output=True,
                    timeout=5,
                    check=True,
                    creationflags=flags,
                )
                .stdout.decode("utf-8")
                .strip()
                .removeprefix("codex-cli ")
            )
            if version not in SUPPORTED_VERSIONS:
                raise ProviderError(
                    "CODEX_VERSION_UNSUPPORTED", "This Codex version is not validated."
                )
            self.version = version
            self.binary_sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            self.process = subprocess.Popen(
                [path, "app-server", "--stdio", "--strict-config"],
                cwd=self.cwd,
                env=self.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            threading.Thread(target=self._read, daemon=True, name="codex-stdio").start()
            initialized = self.rpc(
                "initialize",
                {
                    "clientInfo": {"name": "presenter_copilot", "version": "0.1.0"},
                    "capabilities": {"experimentalApi": True},
                },
            )
            if Path(initialized.get("codexHome", "")).resolve() != self.home:
                raise isolation_error()
            self._send({"method": "initialized"})
            self.inspect()
        except Exception as error:
            self.close()
            if isinstance(error, ProviderError):
                raise
            raise ProviderError(
                "CODEX_UNAVAILABLE", "The isolated Codex runtime could not start."
            ) from None

    def _send(self, message: dict[str, Any]) -> None:
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        if len(data) > MAX_FRAME or self._closed or self._fault.is_set():
            raise isolation_error()
        with self._write_lock:
            if self.process is None or self.process.stdin is None:
                raise isolation_error()
            try:
                self.process.stdin.write(data)
                self.process.stdin.flush()
            except (OSError, ValueError):
                raise ProviderError("CODEX_UNAVAILABLE", "Codex disconnected.") from None

    def _read(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while not self._closed:
                line = self.process.stdout.readline(MAX_FRAME + 1)
                if not line:
                    break
                if len(line) > MAX_FRAME or not line.endswith(b"\n"):
                    break
                message = json.loads(line)
                if not isinstance(message, dict):
                    break
                # No approvals, token-refresh delegation, tools or filesystem RPCs.
                if "method" in message and "id" in message:
                    break
                if "id" in message:
                    with self._pending_lock:
                        target = self._pending.get(message["id"])
                    if target is not None:
                        target.put_nowait(message)
                else:
                    if message.get("method") == "account/login/completed":
                        params = message.get("params", {})
                        self.login_result = (params.get("loginId"), params.get("success") is True)
                        continue
                    self.events.put_nowait(message)
        except (ValueError, OSError, queue.Full, TypeError):
            pass
        finally:
            self._fault.set()
            if self.process.poll() is None:
                self.process.terminate()

    def rpc(self, method: str, params: dict[str, Any], timeout: float = 5) -> dict[str, Any]:
        with self._pending_lock:
            self._serial += 1
            serial = self._serial
            reply: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[serial] = reply
        try:
            self._send({"id": serial, "method": method, "params": params})
            deadline = monotonic() + timeout
            while monotonic() < deadline:
                try:
                    message = reply.get(timeout=min(0.05, max(0.001, deadline - monotonic())))
                    if "error" in message:
                        raise ProviderError(
                            "PROVIDER_REQUEST_FAILED", "Codex rejected the request."
                        )
                    result = message.get("result")
                    if not isinstance(result, dict):
                        raise isolation_error()
                    return result
                except queue.Empty:
                    if self._fault.is_set():
                        raise isolation_error() from None
            raise ProviderError("PROVIDER_TIMEOUT", "Codex timed out.", retryable=True)
        finally:
            with self._pending_lock:
                self._pending.pop(serial, None)

    def inspect(self) -> None:
        if (self.home / "config.toml").read_text(encoding="utf-8") != self.config:
            raise isolation_error()
        if any(self.cwd.iterdir()):
            raise isolation_error()
        response = self.rpc("config/read", {"includeLayers": True})
        config = response.get("config", {})
        layers = response.get("layers")
        if not isinstance(layers, list) or not layers:
            raise isolation_error()
        owned = False
        for layer in layers:
            name = layer.get("name", {})
            if name.get("type") == "user":
                if Path(name.get("file", "")).resolve() != self.home / "config.toml":
                    raise isolation_error()
                if layer.get("config") != tomllib.loads(self.config):
                    raise isolation_error()
                owned = True
            elif layer.get("config"):
                raise isolation_error()
        if not owned:
            raise isolation_error()
        expected = {
            "model": CODEX_MODEL,
            "model_provider": "openai",
            "project_doc_max_bytes": 0,
            "web_search": "disabled",
            "include_environment_context": False,
            "include_permissions_instructions": False,
            "include_apps_instructions": False,
            "include_collaboration_mode_instructions": False,
            "developer_instructions": "",
            "features": {k: v for k, v in FEATURES.items() if k != "apps_mcp_path_override"},
            "forced_login_method": "chatgpt",
            "cli_auth_credentials_store": "file",
        }
        if any(config.get(key) != value for key, value in expected.items()):
            raise isolation_error()
        if config.get("skills") != {"bundled": {"enabled": False}, "include_instructions": False}:
            raise isolation_error()
        if config.get("mcp_servers") or config.get("plugins"):
            raise isolation_error()
        # These calls inspect available sources, not a claimed exhaustive tool inventory.
        skills = self.rpc("skills/list", {"cwds": [str(self.cwd)], "forceReload": True})
        entries = skills.get("data")
        if not isinstance(entries, list) or len(entries) != 1:
            raise isolation_error()
        for entry in entries:
            if entry.get("skills") != [] or entry.get("errors") != []:
                raise isolation_error()
        mcp = self.rpc("mcpServerStatus/list", {})
        if mcp.get("data") != [] or mcp.get("nextCursor"):
            raise isolation_error()

    def new_thread(self, task_type: str = "teach_question") -> str:
        self.inspect()
        result = self.rpc(
            "thread/start",
            {
                "model": CODEX_MODEL,
                "modelProvider": "openai",
                "ephemeral": True,
                "baseInstructions": PRESENTER_POLICY
                + "\n"
                + (task_instruction_for(task_type) or ""),
                "developerInstructions": "",
                "environments": [],
                "dynamicTools": [],
                "runtimeWorkspaceRoots": [],
                "cwd": str(self.cwd),
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "allowProviderModelFallback": False,
            },
        )
        if (
            result.get("instructionSources") != []
            or result.get("runtimeWorkspaceRoots") != []
            or result.get("model") != CODEX_MODEL
            or result.get("modelProvider") != "openai"
            or result.get("approvalPolicy") != "never"
            or result.get("sandbox") != {"type": "readOnly", "networkAccess": False}
            or result.get("thread", {}).get("ephemeral") is not True
        ):
            raise isolation_error()
        return str(result["thread"]["id"])

    def close(self) -> None:
        self._closed = True
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None:
                    stream.close()
        # Delete only this process's randomly allocated runtime, never inspect auth files.
        try:
            self._temporary.cleanup()
        except OSError:
            pass


class CodexReasoningProvider(ReasoningProvider):
    id = "codex_chatgpt"
    locality = "remote"
    model_id = CODEX_MODEL

    def __init__(self) -> None:
        self._server: AppServer | None = None
        self._lock = threading.RLock()
        self._generation = threading.Lock()
        self._signed_in = False
        self._login_id: str | None = None
        self._error: str | None = None
        self._cancellations: dict[int, threading.Event] = {}

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(True, False, True, tuple(TASK_CONTEXT_CLASS_ALLOWLIST))

    def cancel(self, invocation: ProviderInvocation) -> None:
        self._cancellations.setdefault(id(invocation), threading.Event()).set()

    def health(self) -> ProviderHealth:
        if self._server and self._server._fault.is_set():
            self._signed_in = False
            self._error = "CODEX_UNAVAILABLE"
        return ProviderHealth(
            self.id,
            self.locality,
            self.model_id,
            "unavailable" if self._error else "ready" if self._signed_in else "unconfigured",
            self._signed_in,
            self._error or (None if self._signed_in else "PROVIDER_UNCONFIGURED"),
        )

    def auth_status(self) -> dict[str, Any]:
        with self._lock:
            if self._server is not None:
                try:
                    login_result = self._server.login_result
                    if login_result and login_result[0] == self._login_id and not login_result[1]:
                        self._error = "CODEX_LOGIN_FAILED"
                        self._login_id = None
                    self._server.login_result = None
                    result = self._server.rpc("account/read", {"refreshToken": False})
                    account = result.get("account")
                    self._signed_in = isinstance(account, dict) and account.get("type") == "chatgpt"
                    if account is not None and not self._signed_in:
                        raise isolation_error()
                    if self._signed_in:
                        self._login_id = None
                except ProviderError as error:
                    self._error = error.code
                    self._signed_in = False
            return {
                "state": "error"
                if self._error
                else "signed_in"
                if self._signed_in
                else "signing_in"
                if self._login_id
                else "signed_out",
                "error_code": self._error,
                "runtime_version": self._server.version if self._server else None,
            }

    def sign_in(self) -> dict[str, Any]:
        with self._lock:
            if self._server is None:
                self._server = AppServer()
            self._error = None
            if self.auth_status()["state"] in {"signed_in", "signing_in"}:
                return self.auth_status()
            try:
                self._server.inspect()
                result = self._server.rpc("account/login/start", {"type": "chatgpt"})
                url = result.get("authUrl")
                if not isinstance(url, str) or len(url) > 16384:
                    raise isolation_error()
                parsed = urlsplit(url)
                if parsed.scheme != "https" or parsed.hostname not in {
                    "auth.openai.com",
                    "chatgpt.com",
                }:
                    raise isolation_error()
                if parsed.username or parsed.password or parsed.port not in {None, 443}:
                    raise isolation_error()
                self._login_id = result.get("loginId")
                if result.get("type") != "chatgpt" or not isinstance(self._login_id, str):
                    raise isolation_error()
                # The renderer never receives the OAuth URL, state, code, email or tokens.
                if not webbrowser.open(url):
                    raise ProviderError("CODEX_LOGIN_FAILED", "The sign-in browser could not open.")
            except (ProviderError, ValueError) as error:
                self._error = (
                    error.code if isinstance(error, ProviderError) else "CODEX_LOGIN_FAILED"
                )
                self.close()
                raise ProviderError(self._error, "Codex sign-in could not start.") from None
            return self.auth_status()

    def sign_out(self) -> dict[str, Any]:
        with self._lock:
            try:
                if self._server:
                    if self._login_id:
                        self._server.rpc("account/login/cancel", {"loginId": self._login_id})
                    self._server.rpc("account/logout", {})
            finally:
                self.close()
            self._error = None
            return self.auth_status()

    def generate(self, invocation: ProviderInvocation) -> ReasoningResult:
        request = invocation.request
        if request.privacy_mode == "local_only":
            raise ProviderError("PRIVACY_REMOTE_BLOCKED", "Local Only blocks Codex reasoning.")
        if request.task_type not in TASK_CONTEXT_CLASS_ALLOWLIST:
            raise ProviderError("PROVIDER_REQUEST_FAILED", "Unsupported reasoning task.")
        started = monotonic()
        budget = min(120.0, request.latency_budget_ms / 1000)
        cancelled = self._cancellations.setdefault(id(invocation), threading.Event())
        if budget <= 0 or not self._generation.acquire(timeout=max(0, budget)):
            self._cancellations.pop(id(invocation), None)
            raise ProviderError("PROVIDER_TIMEOUT", "Codex is busy.", retryable=True)
        server: AppServer | None = None
        thread_id: str | None = None
        try:
            if cancelled.is_set():
                raise ProviderError("PROVIDER_CANCELLED", "Codex request cancelled.")
            if self.auth_status()["state"] != "signed_in" or self._server is None:
                raise ProviderError(
                    "PROVIDER_AUTH_FAILED", "Sign in to ChatGPT for Codex reasoning."
                )
            server = self._server
            thread_id = server.new_thread(request.task_type)
            if cancelled.is_set():
                raise ProviderError("PROVIDER_CANCELLED", "Codex request cancelled.")
            if monotonic() - started >= budget:
                raise ProviderError("PROVIDER_TIMEOUT", "Codex exceeded the request budget.")
            turn = server.rpc(
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": invocation.serialized_input()}],
                    "outputSchema": request.output_schema,
                    "environments": [],
                },
            )["turn"]
            output: str | None = None
            while monotonic() - started < budget:
                if cancelled.is_set():
                    server.rpc("turn/interrupt", {"threadId": thread_id, "turnId": turn["id"]})
                    raise ProviderError("PROVIDER_CANCELLED", "Codex request cancelled.")
                if server._fault.is_set():
                    raise isolation_error()
                try:
                    event = server.events.get(timeout=0.05)
                except queue.Empty:
                    continue
                params = event.get("params", {})
                if params.get("threadId") != thread_id:
                    continue
                method = event.get("method")
                if method in {"item/started", "item/completed"}:
                    item = params.get("item", {})
                    if item.get("type") not in {"userMessage", "agentMessage", "reasoning"}:
                        # Unexpected observable capability: stop; never promote its output.
                        raise isolation_error()
                    if method == "item/completed" and item.get("type") == "agentMessage":
                        output = item.get("text")
                if method == "turn/completed":
                    if params.get("turn", {}).get("status") != "completed":
                        raise map_turn_error(params.get("turn", {}).get("error"))
                    if not isinstance(output, str) or len(output) > 65536:
                        raise ProviderError(
                            "PROVIDER_MALFORMED_OUTPUT", "Codex returned invalid output."
                        )
                    try:
                        validated = validate_provider_output(
                            request.task_type,
                            json.loads(output),
                            conflict_metadata=request.conflict_metadata,
                        )
                    except (ValueError, TypeError):
                        raise ProviderError(
                            "PROVIDER_MALFORMED_OUTPUT", "Codex returned invalid JSON."
                        ) from None
                    return ReasoningResult(
                        output=validated, latency_ms=int((monotonic() - started) * 1000)
                    )
            server.rpc("turn/interrupt", {"threadId": thread_id, "turnId": turn["id"]})
            raise ProviderError(
                "PROVIDER_TIMEOUT", "Codex exceeded the request budget.", retryable=True
            )
        except ProviderError as error:
            if error.code == "CODEX_ISOLATION_FAILED":
                self._error = error.code
                self.close()
            raise
        finally:
            if server and thread_id and not server._closed:
                try:
                    server.rpc("thread/unsubscribe", {"threadId": thread_id})
                except ProviderError:
                    server.close()
            self._generation.release()
            self._cancellations.pop(id(invocation), None)

    def close(self) -> None:
        for event in tuple(self._cancellations.values()):
            event.set()
        self._signed_in = False
        self._login_id = None
        server, self._server = self._server, None
        if server:
            server.close()
