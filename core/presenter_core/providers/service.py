"""Non-secret provider configuration and provider lifecycle."""

from __future__ import annotations

from typing import Any

from presenter_core.errors import invalid_request, reject_unknown_fields
from presenter_core.project.service import utc_now
from presenter_core.storage.service import StorageManager

from .models import (
    ProviderError,
    ReasoningProvider,
    ReasoningRequest,
    question_output_schema,
)
from .openai import DEFAULT_OPENAI_MODEL, OpenAIReasoningProvider


class ProviderService:
    """Own safe provider metadata while keeping secrets in the core environment."""

    def __init__(self, storage: StorageManager, provider: ReasoningProvider | None = None) -> None:
        self._storage = storage
        self._injected_provider = provider
        self._openai_instance: OpenAIReasoningProvider | None = None

    def list(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        if self._injected_provider is not None:
            provider = self._injected_provider
            return {"providers": [self._provider_dict(provider, enabled=True)]}
        provider = self._openai_provider()
        row = self._config_row("openai")
        enabled = bool(row["enabled"]) if row is not None else bool(provider.health().configured)
        return {"providers": [self._provider_dict(provider, enabled=enabled)]}

    def configure(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"provider_id", "enabled", "model_id"})
        provider_id = params.get("provider_id", "openai")
        if provider_id != "openai":
            raise invalid_request(
                "Only the OpenAI reference provider is configurable in M3.", field="provider_id"
            )
        enabled = params.get("enabled", True)
        if not isinstance(enabled, bool):
            raise invalid_request("enabled must be a boolean.", field="enabled")
        model_id = params.get("model_id", DEFAULT_OPENAI_MODEL)
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id.strip()) > 120:
            raise invalid_request("model_id must be a non-empty bounded string.", field="model_id")
        if any(ord(character) < 32 for character in model_id):
            raise invalid_request(
                "model_id contains unsupported control characters.", field="model_id"
            )
        model_id = model_id.strip()
        now = utc_now()
        with self._storage.app_database() as connection:
            connection.execute(
                """
                INSERT INTO provider_configurations
                    (
                        provider_id, enabled, model_id, credential_source,
                        safe_config_json, created_at, updated_at
                    )
                VALUES ('openai', ?, ?, 'environment', '{}', ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    model_id = excluded.model_id,
                    credential_source = 'environment',
                    safe_config_json = '{}',
                    updated_at = excluded.updated_at
                """,
                (int(enabled), model_id, now, now),
            )
            connection.commit()
        return {"provider": self._provider_dict(self._openai_provider(), enabled=enabled)}

    def status(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"provider_id"})
        provider_id = params.get("provider_id", "openai")
        if provider_id != "openai" and self._injected_provider is None:
            raise invalid_request("The requested provider is not supported.", field="provider_id")
        provider = (
            self.current_provider()
            if self._injected_provider is not None
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
        health = provider.health()
        if health.status != "ready":
            raise ProviderError(
                health.error_code or "PROVIDER_UNAVAILABLE",
                "The provider is not ready for a synthetic contract test.",
                retryable=health.retryable,
            )
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
            privacy_mode="local_only",
            output_schema=question_output_schema(),
            latency_budget_ms=5_000,
            application_policy="Synthetic provider contract test only.",
        )
        result = provider.generate(request)
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
        return self._openai_provider()

    def close(self) -> None:
        """Release an injected or cached provider without exposing credentials."""
        if self._injected_provider is not None:
            self._injected_provider.close()
        if self._openai_instance is not None:
            self._openai_instance.close()
            self._openai_instance = None

    def is_enabled(self) -> bool:
        if self._injected_provider is not None:
            return True
        row = self._config_row("openai")
        if row is not None:
            return bool(row["enabled"])
        return self._openai_provider().health().configured

    def _openai_provider(self) -> OpenAIReasoningProvider:
        row = self._config_row("openai")
        model_id = str(row["model_id"]) if row is not None else DEFAULT_OPENAI_MODEL
        if self._openai_instance is not None and self._openai_instance.model_id == model_id:
            return self._openai_instance
        if self._openai_instance is not None:
            self._openai_instance.close()
        self._openai_instance = OpenAIReasoningProvider(model_id=model_id)
        return self._openai_instance

    def _config_row(self, provider_id: str) -> Any | None:
        with self._storage.app_database() as connection:
            return connection.execute(
                "SELECT * FROM provider_configurations WHERE provider_id = ?",
                (provider_id,),
            ).fetchone()

    @staticmethod
    def _provider_dict(provider: ReasoningProvider, *, enabled: bool) -> dict[str, Any]:
        health = provider.health()
        return {
            "provider_id": provider.id,
            "enabled": enabled,
            "model_id": provider.model_id,
            "credential_source": "environment" if provider.id == "openai" else "test",
            "safe_config": {},
            "health": health.to_dict(),
            "capabilities": provider.capabilities().to_dict(),
        }
