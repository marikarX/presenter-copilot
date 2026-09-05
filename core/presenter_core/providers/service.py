"""Non-secret provider configuration and provider lifecycle."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from presenter_core.credentials import (
    CredentialStore,
    CredentialStoreUnavailable,
    WindowsCredentialStore,
    credential_source,
    resolve_openai_credential,
)
from presenter_core.errors import invalid_request, reject_unknown_fields
from presenter_core.project.service import utc_now
from presenter_core.storage.service import StorageManager

from .local import LocalReasoningProvider, validate_endpoint
from .models import (
    ProviderError,
    ProviderHealth,
    ProviderInvocation,
    ReasoningProvider,
    ReasoningRequest,
    question_output_schema,
)
from .openai import DEFAULT_OPENAI_MODEL, OpenAIReasoningProvider

EventSink = Callable[[str, dict[str, Any]], None]


class ProviderService:
    """Own safe provider metadata while keeping secrets in the core environment."""

    def __init__(
        self,
        storage: StorageManager,
        provider: ReasoningProvider | None = None,
        event_sink: EventSink | None = None,
        credential_store: CredentialStore | None = None,
    ) -> None:
        self._storage = storage
        self._injected_provider = provider
        self._credential_store = credential_store or WindowsCredentialStore()
        self._openai_instance: OpenAIReasoningProvider | None = None
        self._local_instance: LocalReasoningProvider | None = None
        self._runtime_health: dict[str, ProviderHealth] = {}
        self._event_sink = event_sink

    def list(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        if self._injected_provider is not None:
            provider = self._injected_provider
            return {"providers": [self._provider_dict(provider, enabled=True)]}
        provider = self._openai_provider()
        row = self._config_row("openai")
        enabled = (
            bool(row["enabled"]) if row is not None else bool(self.health(provider).configured)
        )
        local = self._local_provider()
        local_row = self._config_row(local.id)
        providers = [
            self._provider_dict(provider, enabled=enabled),
            self._provider_dict(local, enabled=bool(local_row and local_row["enabled"])),
        ]
        providers.sort(key=lambda item: not item["enabled"])
        return {"providers": providers}

    def configure(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"provider_id", "enabled", "model_id", "endpoint"})
        provider_id = params.get("provider_id", "openai")
        if provider_id not in {"openai", "local_openai"}:
            raise invalid_request(
                "The requested provider is not configurable.", field="provider_id"
            )
        enabled = params.get("enabled", True)
        if not isinstance(enabled, bool):
            raise invalid_request("enabled must be a boolean.", field="enabled")
        model_id = params.get("model_id", DEFAULT_OPENAI_MODEL if provider_id == "openai" else "")
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id.strip()) > 120:
            raise invalid_request("model_id must be a non-empty bounded string.", field="model_id")
        if any(ord(character) < 32 for character in model_id):
            raise invalid_request(
                "model_id contains unsupported control characters.", field="model_id"
            )
        model_id = model_id.strip()
        now = utc_now()
        safe_config = {}
        if provider_id == "local_openai":
            endpoint, _ = validate_endpoint(params.get("endpoint"))
            safe_config["endpoint"] = endpoint
        elif "endpoint" in params:
            raise invalid_request("OpenAI uses its official endpoint.", field="endpoint")
        safe_credential_source = (
            self._credential_source() if provider_id == "openai" else "environment"
        )
        with self._storage.app_database() as connection:
            if enabled:
                connection.execute("UPDATE provider_configurations SET enabled = 0")
                # Persist the old implicit API default as disabled when selecting another adapter.
                if provider_id != "openai":
                    connection.execute(
                        "INSERT OR IGNORE INTO provider_configurations VALUES "
                        "('openai', 0, ?, 'environment', '{}', ?, ?)",
                        (DEFAULT_OPENAI_MODEL, now, now),
                    )
            connection.execute(
                """
                INSERT INTO provider_configurations
                    (
                        provider_id, enabled, model_id, credential_source,
                        safe_config_json, created_at, updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    model_id = excluded.model_id,
                    credential_source = excluded.credential_source,
                    safe_config_json = excluded.safe_config_json,
                    updated_at = excluded.updated_at
                """,
                (
                    provider_id,
                    int(enabled),
                    model_id,
                    safe_credential_source,
                    json.dumps(safe_config),
                    now,
                    now,
                ),
            )
            connection.commit()
        self._runtime_health.pop(provider_id, None)
        provider = (
            self._local_provider() if provider_id == "local_openai" else self._openai_provider()
        )
        result = {"provider": self._provider_dict(provider, enabled=enabled)}
        self._emit("provider.status_changed", result)
        return result

    def credentials_status(self, params: dict[str, Any]) -> dict[str, Any]:
        """Expose only safe credential source/configured metadata."""
        reject_unknown_fields(params, {"provider_id"})
        provider_id = params.get("provider_id", "openai")
        if provider_id != "openai":
            raise invalid_request(
                "Only the OpenAI reference provider is supported.", field="provider_id"
            )
        source = self._credential_source()
        return {
            "provider_id": "openai",
            "credential_source": source,
            "configured": bool(resolve_openai_credential(self._credential_store)),
            "secure_store_available": self._credential_store.is_available(),
            "environment_detected": bool(os.environ.get("OPENAI_API_KEY")),
        }

    def save_detected_credential(self, params: dict[str, Any]) -> dict[str, Any]:
        """Save the core environment credential without accepting plaintext IPC input."""
        reject_unknown_fields(params, {"provider_id"})
        provider_id = params.get("provider_id", "openai")
        if provider_id != "openai":
            raise invalid_request(
                "Only the OpenAI reference provider is supported.", field="provider_id"
            )
        detected = os.environ.get("OPENAI_API_KEY")
        if not detected:
            return {
                "provider_id": "openai",
                "saved": False,
                "detected": False,
                "credential_source": self._credential_source(),
            }
        if not self._credential_store.is_available():
            raise ProviderError(
                "CREDENTIAL_STORE_UNAVAILABLE",
                "A secure operating-system credential store is unavailable.",
                retryable=True,
            )
        try:
            self._credential_store.write(detected)
        except (CredentialStoreUnavailable, ValueError) as error:
            raise ProviderError(
                "CREDENTIAL_STORE_UNAVAILABLE",
                "The credential could not be saved to the secure operating-system store.",
                retryable=True,
            ) from error
        self._runtime_health.pop("openai", None)
        self._update_credential_source()
        return {
            "provider_id": "openai",
            "saved": True,
            "detected": True,
            "credential_source": self._credential_source(),
        }

    def remove_credential(self, params: dict[str, Any]) -> dict[str, Any]:
        """Remove the app/provider credential from the OS store; environment is untouched."""
        reject_unknown_fields(params, {"provider_id"})
        provider_id = params.get("provider_id", "openai")
        if provider_id != "openai":
            raise invalid_request(
                "Only the OpenAI reference provider is supported.", field="provider_id"
            )
        if not self._credential_store.is_available():
            raise ProviderError(
                "CREDENTIAL_STORE_UNAVAILABLE",
                "A secure operating-system credential store is unavailable.",
                retryable=True,
            )
        try:
            removed = self._credential_store.delete()
        except Exception as error:
            raise ProviderError(
                "CREDENTIAL_STORE_UNAVAILABLE",
                "The credential could not be removed from the secure operating-system store.",
                retryable=True,
            ) from error
        if self._openai_instance is not None:
            self._openai_instance.close()
        self._runtime_health.pop("openai", None)
        self._update_credential_source()
        return {
            "provider_id": "openai",
            "removed": bool(removed),
            "credential_source": self._credential_source(),
            "environment_still_detected": bool(os.environ.get("OPENAI_API_KEY")),
        }

    def prepare_reset_credential_cleanup(self) -> dict[str, Any]:
        """Preflight the OS store before any destructive local-data operation."""
        try:
            available = self._credential_store.is_available()
        except Exception as error:
            raise ProviderError(
                "CREDENTIAL_STORE_UNAVAILABLE",
                "A secure operating-system credential store is unavailable.",
                retryable=True,
            ) from error
        if not available:
            raise ProviderError(
                "CREDENTIAL_STORE_UNAVAILABLE",
                "A secure operating-system credential store is unavailable.",
                retryable=True,
            )
        try:
            stored = self._credential_store.read()
        except Exception as error:
            raise ProviderError(
                "CREDENTIAL_STORE_UNAVAILABLE",
                "The secure operating-system credential store could not be read.",
                retryable=True,
            ) from error
        return {
            "stored_credential_present": bool(stored),
            "credential_cleanup_established": True,
            "environment_credential_detected": bool(os.environ.get("OPENAI_API_KEY")),
            "environment_credential_retained": True,
        }

    def remove_stored_credential_for_reset(
        self, plan: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Remove and verify only the OS entry; environment credentials stay external."""
        del plan
        preflight = self.prepare_reset_credential_cleanup()
        stored_present = bool(preflight["stored_credential_present"])
        removed = False
        if stored_present:
            try:
                self._credential_store.delete()
                remaining = self._credential_store.read()
            except Exception as error:
                raise ProviderError(
                    "CREDENTIAL_CLEANUP_INCOMPLETE",
                    "The stored credential could not be removed and verified; retry is safe.",
                    retryable=True,
                ) from error
            if remaining:
                raise ProviderError(
                    "CREDENTIAL_CLEANUP_INCOMPLETE",
                    "The stored credential could not be removed and verified; retry is safe.",
                    retryable=True,
                )
            removed = True
        if self._openai_instance is not None:
            self._openai_instance.close()
        self._runtime_health.pop("openai", None)
        self._update_credential_source()
        return {
            **preflight,
            "credentials_removed": removed,
        }

    def status(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"provider_id"})
        provider_id = params.get("provider_id")
        if provider_id not in {None, "openai", "local_openai"} and self._injected_provider is None:
            raise invalid_request("The requested provider is not supported.", field="provider_id")
        provider = (
            self.current_provider()
            if self._injected_provider is not None or provider_id is None
            else self._local_provider()
            if provider_id == "local_openai"
            else self._openai_provider()
        )
        row = self._config_row(provider.id)
        enabled = True if self._injected_provider is not None else bool(row and row["enabled"])
        return {"provider": self._provider_dict(provider, enabled=enabled)}

    def test(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"provider_id"})
        requested_provider_id = params.get("provider_id")
        provider = self.current_provider()
        if requested_provider_id is not None and requested_provider_id != provider.id:
            raise invalid_request("The requested provider is not active.", field="provider_id")
        request = ReasoningRequest(
            task_type="teach_question",
            question="Which decision should be clarified?",
            user_input=None,
            current_slide_summary=None,
            evidence=({"class": "synthetic_evidence", "text": "Synthetic project decision."},),
            preferred_user_explanations=(),
            speaker_evidence=(),
            style_context={"policy": "preserve_voice", "examples": []},
            conflict_metadata=(),
            style_policy="preserve_voice",
            privacy_mode="selected_context_cloud" if provider.leaves_machine else "local_only",
            output_schema=question_output_schema(),
            latency_budget_ms=5_000,
            application_policy="Synthetic provider contract test only.",
        )
        try:
            result = provider.generate(
                ProviderInvocation(
                    request=request,
                    serialized_input_text=request.serialized_input(),
                )
            )
        except ProviderError as error:
            self.record_failure(provider, error)
            raise
        except Exception as error:
            mapped = ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The reasoning provider request failed.",
                retryable=True,
            )
            self.record_failure(provider, mapped)
            raise mapped from error
        self.record_success(provider)
        return {
            "provider_id": provider.id,
            "model_id": provider.model_id,
            "status": "ready",
            "structured_output": result.output,
            "latency_ms": result.latency_ms,
        }

    def current_provider(self) -> ReasoningProvider:
        if self._injected_provider is not None:
            return self._injected_provider
        row = self._config_row("local_openai")
        if row is not None and row["enabled"]:
            return self._local_provider()
        return self._openai_provider()

    def current_provider_and_health(self) -> tuple[ReasoningProvider | None, ProviderHealth | None]:
        """Return the selected provider only when the configuration enables it."""
        if not self.is_enabled():
            return None, None
        provider = self.current_provider()
        return provider, self.health(provider)

    def health(self, provider: ReasoningProvider | None = None) -> ProviderHealth:
        """Return base health overlaid with this process's recent safe outcome."""
        selected = provider or self.current_provider()
        base = selected.health()
        runtime = self._runtime_health.get(selected.id)
        if runtime is None:
            return base
        if runtime.model_id != selected.model_id or runtime.locality != selected.locality:
            self._runtime_health.pop(selected.id, None)
            return base
        # A missing environment credential remains authoritative even if a
        # previous provider instance succeeded earlier in this process.
        if base.status == "unconfigured":
            return base
        return runtime

    def record_success(self, provider: ReasoningProvider) -> None:
        if isinstance(provider, LocalReasoningProvider) and provider is not self._local_instance:
            if provider is not self._injected_provider:
                return
        health = ProviderHealth(
            provider_id=provider.id,
            locality=provider.locality,
            model_id=provider.model_id,
            status="ready",
            configured=True,
        )
        self._runtime_health[provider.id] = health
        self._emit_status(provider)

    def record_failure(self, provider: ReasoningProvider, error: ProviderError) -> None:
        if isinstance(provider, LocalReasoningProvider) and provider is not self._local_instance:
            if provider is not self._injected_provider:
                return
        if error.code == "PROVIDER_CANCELLED":
            return
        status, retryable, configured = {
            "PROVIDER_UNCONFIGURED": ("unconfigured", False, False),
            "PROVIDER_AUTH_FAILED": ("auth_failed", False, True),
            "PROVIDER_QUOTA_EXCEEDED": ("quota_exhausted", False, True),
            "PROVIDER_RATE_LIMITED": ("rate_limited", True, True),
            "PROVIDER_TIMEOUT": ("unavailable", True, True),
            "PROVIDER_UNAVAILABLE": ("unavailable", True, True),
            "PROVIDER_REQUEST_FAILED": ("unavailable", True, True),
            "PROVIDER_MALFORMED_OUTPUT": ("unavailable", False, True),
        }.get(error.code, ("unavailable", error.retryable, True))
        health_error_code = error.code
        if error.code in {"CHALLENGE_OUTPUT_INVALID", "ASSIST_OUTPUT_INVALID"}:
            health_error_code = "PROVIDER_MALFORMED_OUTPUT"
        health = ProviderHealth(
            provider_id=provider.id,
            locality=provider.locality,
            model_id=provider.model_id,
            status=status,
            configured=configured,
            error_code=health_error_code,
            retryable=retryable,
        )
        self._runtime_health[provider.id] = health
        self._emit_status(provider)

    def close(self) -> None:
        """Release an injected or cached provider without exposing credentials."""
        if self._injected_provider is not None:
            self._injected_provider.close()
        if self._openai_instance is not None:
            self._openai_instance.close()
            self._openai_instance = None
        if self._local_instance is not None:
            self._local_instance.close()
            self._local_instance = None
        self._runtime_health.clear()

    def is_enabled(self) -> bool:
        if self._injected_provider is not None:
            return True
        row = self._config_row(self.current_provider().id)
        if row is not None:
            return bool(row["enabled"])
        return self._openai_provider().health().configured

    def _local_provider(self) -> LocalReasoningProvider:
        row = self._config_row("local_openai")
        config = json.loads(row["safe_config_json"]) if row is not None else {}
        endpoint = config.get("endpoint", "")
        model = row["model_id"] if row is not None else ""
        if (
            self._local_instance is None
            or self._local_instance.endpoint != endpoint
            or self._local_instance.model_id != model
        ):
            if self._local_instance is not None:
                self._local_instance.close()
            self._local_instance = LocalReasoningProvider(endpoint=endpoint, model_id=model)
        return self._local_instance

    def _openai_provider(self) -> OpenAIReasoningProvider:
        row = self._config_row("openai")
        model_id = str(row["model_id"]) if row is not None else DEFAULT_OPENAI_MODEL
        if self._openai_instance is not None and self._openai_instance.model_id == model_id:
            return self._openai_instance
        if self._openai_instance is not None:
            self._openai_instance.close()
            self._runtime_health.pop("openai", None)
        self._openai_instance = OpenAIReasoningProvider(
            model_id=model_id,
            credential_resolver=lambda: resolve_openai_credential(self._credential_store),
        )
        return self._openai_instance

    def _config_row(self, provider_id: str) -> Any | None:
        with self._storage.app_database() as connection:
            return connection.execute(
                "SELECT * FROM provider_configurations WHERE provider_id = ?",
                (provider_id,),
            ).fetchone()

    def _provider_dict(self, provider: ReasoningProvider, *, enabled: bool) -> dict[str, Any]:
        health = self.health(provider)
        return {
            "provider_id": provider.id,
            "enabled": enabled,
            "model_id": provider.model_id,
            "credential_source": self._credential_source()
            if provider.id == "openai"
            else "environment"
            if provider.id == "local_openai"
            else "test",
            "safe_config": {
                "endpoint": provider.endpoint,
                "leaves_machine": provider.leaves_machine,
            }
            if isinstance(provider, LocalReasoningProvider)
            else {},
            "health": health.to_dict(),
            "capabilities": provider.capabilities().to_dict(),
        }

    def _emit_status(self, provider: ReasoningProvider) -> None:
        self._emit(
            "provider.status_changed",
            {
                "provider": self._provider_dict(
                    provider, enabled=self.is_enabled() and self.current_provider() is provider
                )
            },
        )

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)

    def _credential_source(self) -> str:
        return credential_source(self._credential_store)

    def _update_credential_source(self) -> None:
        """Keep only source metadata in app.db; never persist the credential."""
        with self._storage.app_database() as connection:
            row = connection.execute(
                "SELECT provider_id FROM provider_configurations WHERE provider_id = 'openai'"
            ).fetchone()
            if row is not None:
                connection.execute(
                    "UPDATE provider_configurations SET credential_source = ?, updated_at = ? "
                    "WHERE provider_id = 'openai'",
                    (self._credential_source(), utc_now()),
                )
                connection.commit()
