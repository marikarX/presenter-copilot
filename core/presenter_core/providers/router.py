"""Small, explicit M3 reasoning routing decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import ProviderHealth, ReasoningProvider


class ReasoningRoute(StrEnum):
    NONE = "none"
    RETRIEVAL_ONLY = "retrieval_only"
    LOCAL_REASONING = "local_reasoning"
    REMOTE_REASONING = "remote_reasoning"


@dataclass(frozen=True)
class RouteDecision:
    route: ReasoningRoute
    reason: str
    provider_id: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "route": self.route.value,
            "reason": self.reason,
            "provider_id": self.provider_id,
        }


class ReasoningRouter:
    """Decide whether a bounded Teach operation may invoke a provider."""

    def decide(
        self,
        *,
        task_type: str,
        privacy_mode: str,
        remote_acknowledged: bool,
        provider: ReasoningProvider | None,
        provider_health: ProviderHealth | None,
        local_only_submission: bool = False,
    ) -> RouteDecision:
        if local_only_submission:
            return RouteDecision(ReasoningRoute.RETRIEVAL_ONLY, "local_only", None)
        if provider is None or provider_health is None:
            return RouteDecision(ReasoningRoute.RETRIEVAL_ONLY, "no_provider", None)
        if task_type not in provider.capabilities().task_types:
            return RouteDecision(
                ReasoningRoute.RETRIEVAL_ONLY,
                "provider_task_unsupported",
                None,
            )
        if provider_health.status != "ready":
            return RouteDecision(
                ReasoningRoute.RETRIEVAL_ONLY,
                provider_health.error_code or "provider_unavailable",
                None,
            )
        if provider.locality == "local":
            return RouteDecision(ReasoningRoute.LOCAL_REASONING, "local_provider", provider.id)
        if privacy_mode == "local_only":
            return RouteDecision(ReasoningRoute.RETRIEVAL_ONLY, "local_only", None)
        if not remote_acknowledged:
            return RouteDecision(
                ReasoningRoute.RETRIEVAL_ONLY,
                "remote_reasoning_acknowledgement_required",
                None,
            )
        return RouteDecision(ReasoningRoute.REMOTE_REASONING, "acknowledged_remote", provider.id)
