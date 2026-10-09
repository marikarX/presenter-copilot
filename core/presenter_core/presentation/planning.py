"""Evidence-aware, review-only narrative and outline planning."""

from __future__ import annotations

import json
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.creation import PresentationCreationService
from presenter_core.presentation.outline_drafts import OutlineDraftService
from presenter_core.providers.context import ProviderContextBuilder
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.models import ProviderError, validate_provider_output
from presenter_core.providers.router import ReasoningRoute, ReasoningRouter
from presenter_core.providers.service import ProviderService
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

TASK_TYPE = "presentation_outline"


class PresentationPlanningService:
    def __init__(
        self,
        storage: StorageManager,
        providers: ProviderService,
        context: ProviderContextBuilder,
        execution: ProviderExecutionService,
    ) -> None:
        self._storage = storage
        self._providers = providers
        self._context = context
        self._execution = execution
        self.drafts = OutlineDraftService(storage)

    def propose_outline(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "objective",
                "audience",
                "briefing",
                "slide_count",
                "instruction",
                "prior_outline",
            },
        )
        if not isinstance(params.get("project_id"), str):
            raise invalid_request("project_id must be a UUID.", field="project_id")
        project_id = normalize_project_id(params["project_id"])
        objective = PresentationCreationService._text(params.get("objective"), "objective", 500)
        audience = PresentationCreationService._text(params.get("audience"), "audience", 300)
        briefing = PresentationCreationService._text(
            params.get("briefing", ""), "briefing", 2000, allow_empty=True
        )
        instruction = PresentationCreationService._text(
            params.get("instruction", "Plan a clear narrative for this presentation."),
            "instruction",
            500,
        )
        count = params.get("slide_count", 6)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 40:
            raise invalid_request("Choose between 1 and 40 slides.", field="slide_count")
        prior = params.get("prior_outline")
        if prior is not None:
            # A previous draft is data, never an instruction or approved knowledge.
            prior = validate_provider_output(TASK_TYPE, prior)
        with self._storage.project_database(project_id) as connection:
            project = connection.execute(
                "SELECT privacy_mode, remote_reasoning_acknowledged_at FROM project WHERE id = ?",
                (project_id,),
            ).fetchone()
        if project is None:
            raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
        privacy_mode = str(project["privacy_mode"])
        provider, health = self._providers.current_provider_and_health()
        route = ReasoningRouter().decide(
            task_type=TASK_TYPE,
            privacy_mode=privacy_mode,
            remote_acknowledged=project["remote_reasoning_acknowledged_at"] is not None,
            provider=provider,
            provider_health=health,
        )
        if route.route == ReasoningRoute.RETRIEVAL_ONLY or provider is None:
            if route.reason == "local_only":
                raise CoreDomainError(
                    "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED", "Local Only blocks this provider."
                )
            if route.reason == "remote_reasoning_acknowledgement_required":
                raise CoreDomainError(
                    "PRIVACY_REMOTE_ACK_REQUIRED",
                    "Acknowledge remote reasoning in project settings first.",
                )
            if route.reason == "provider_task_unsupported":
                raise CoreDomainError(
                    "PROVIDER_TASK_UNSUPPORTED", "This provider cannot plan presentation outlines."
                )
            raise CoreDomainError(
                health.error_code if health and health.error_code else "PROVIDER_UNCONFIGURED",
                "Configure a ready reasoning provider in Settings to plan an outline.",
                retryable=bool(health and health.retryable),
            )
        brief = json.dumps(
            {
                "objective": objective,
                "audience": audience,
                "briefing": briefing,
                "slide_count": count,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        request, _manifest = self._context.build(
            project_id=project_id,
            task_type=TASK_TYPE,
            question=instruction,
            user_input=brief,
            privacy_mode=privacy_mode,
            style_policy="preserve_voice",
            provider_id=provider.id,
            allow_private=False,
            retrieval_query=f"{objective} {briefing}"[:500],
            latency_budget_ms=30_000,
            presentation_draft=prior,
        )
        if request.user_input != brief or request.question != instruction:
            raise CoreDomainError(
                "PRESENTATION_PLAN_CONTEXT_TOO_LARGE", "Shorten the briefing before planning."
            )
        supplied = {
            str(item["evidence_id"]): item
            for item in (*request.evidence, *request.preferred_user_explanations)
            if isinstance(item.get("evidence_id"), str)
        }

        def validate_outline(output: dict[str, Any]) -> dict[str, Any]:
            checked = validate_provider_output(TASK_TYPE, output)
            if len(checked["slides"]) != count:
                raise ProviderError(
                    "PROVIDER_MALFORMED_OUTPUT", "The outline has the wrong slide count."
                )
            if any(
                evidence_id not in supplied
                for slide in checked["slides"]
                for evidence_id in slide["evidence_ids"]
            ):
                raise ProviderError(
                    "PROVIDER_MALFORMED_OUTPUT", "The outline cites evidence that was not supplied."
                )
            return checked

        result = self._execution.execute(
            project_id=project_id,
            session_id=None,
            provider=provider,
            request=request,
            output_validator=validate_outline,
        )
        proposal = {
            **result.result.output,
            "provider_run_id": result.provider_run_id,
            "provider_id": provider.id,
            "model_id": provider.model_id,
            "requires_user_review": True,
            "evidence": [
                {
                    "evidence_id": evidence_id,
                    "text": item.get("text", ""),
                    "source_type": item.get("source_type"),
                    "source_locator": item.get("source_locator"),
                }
                for evidence_id, item in supplied.items()
            ],
        }

        self.drafts.capture(
            project_id,
            proposal,
            {
                "objective": objective,
                "audience": audience,
                "briefing": briefing,
                "slide_count": count,
                "instruction": instruction,
                "prior_outline": prior,
            },
        )
        return proposal
