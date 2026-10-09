"""Review-only narrative analysis of a concrete verified deck and draft intent."""

from __future__ import annotations

import json
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.narrative import PresentationNarrativeService
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.providers.context import ProviderContextBuilder
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.models import ProviderError, validate_provider_output
from presenter_core.providers.router import ReasoningRoute, ReasoningRouter
from presenter_core.providers.service import ProviderService

TASK_TYPE = "presentation_narrative_review"


class PresentationNarrativePlanningService:
    def __init__(
        self,
        semantics: PresentationSemanticService,
        providers: ProviderService,
        context: ProviderContextBuilder,
        execution: ProviderExecutionService,
    ) -> None:
        self._semantics, self._providers = semantics, providers
        self._context, self._execution = context, execution
        self._narrative = PresentationNarrativeService(semantics)

    def propose_narrative(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "revision_id",
                "fields",
                "expected_record_token",
                "instruction",
                "start_slide",
                "slide_count",
            },
        )
        fields = self._narrative.validate_fields(params.get("fields"))
        instruction = params.get(
            "instruction", "Analyze the narrative and suggest clearer deck intent."
        )
        if (
            not isinstance(instruction, str)
            or not instruction.strip()
            or len(instruction) > 500
            or "\x00" in instruction
        ):
            raise invalid_request("Supply an instruction of 1-500 characters.")
        start, count = params.get("start_slide", 1), params.get("slide_count", 40)
        if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= 5000:
            raise invalid_request("start_slide must be an integer from 1 to 5000.")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 40:
            raise invalid_request("slide_count must be an integer from 1 to 40.")
        if "expected_record_token" not in params:
            raise invalid_request("Supply the narrative record token from the current view.")
        expected = params["expected_record_token"]
        if expected is not None:
            expected = self._semantics._uuid_field(expected, "expected_record_token")
        scope = {key: params.get(key) for key in ("project_id", "document_id", "revision_id")}
        project, document, revision, native = (
            self._semantics._workspace_sources.read_revision_inventory(scope)
        )
        state = self._narrative.get_narrative(scope)
        if state["record_token"] != expected:
            raise CoreDomainError(
                "PRESENTATION_NARRATIVE_CONFLICT",
                "Narrative changed. Reload before requesting a suggestion.",
                retryable=True,
            )
        selected = native.slides[start - 1 : start - 1 + count]
        if not selected:
            raise invalid_request("The start slide is outside this deck.")
        slides, shortened = [], []
        for slide in selected:
            text = "\n".join(obj.text for obj in slide.objects if isinstance(obj.text, str))
            notes = slide.speaker_notes or ""
            if len(text) > 600 or len(notes) > 120:
                shortened.append(slide.ordinal)
            slides.append(
                {
                    "slide_id": slide.slide_id,
                    "ordinal": slide.ordinal,
                    "text_excerpt": text[:600],
                    "notes_excerpt": notes[:120],
                    "text_shortened": len(text) > 600,
                    "notes_shortened": len(notes) > 120,
                }
            )
        analysis_scope = {
            "start_slide": selected[0].ordinal,
            "end_slide": selected[-1].ordinal,
            "total_slides": len(native.slides),
            "covered_slide_count": len(selected),
            "omitted_slide_count": len(native.slides) - len(selected),
            "shortened_slide_numbers": shortened,
            "visual_content_not_analyzed": True,
        }
        snapshot = {
            "revision_id": revision,
            "draft_fields": fields,
            "slides": slides,
            "analysis_scope": analysis_scope,
        }
        with self._semantics._storage.project_database(project) as connection:
            policy = connection.execute(
                "SELECT privacy_mode, remote_reasoning_acknowledged_at FROM project WHERE id=?",
                (project,),
            ).fetchone()
        provider, health = self._providers.current_provider_and_health()
        route = ReasoningRouter().decide(
            task_type=TASK_TYPE,
            privacy_mode=policy["privacy_mode"],
            remote_acknowledged=policy["remote_reasoning_acknowledged_at"] is not None,
            provider=provider,
            provider_health=health,
        )
        if route.route == ReasoningRoute.RETRIEVAL_ONLY or provider is None:
            codes = {
                "local_only": "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED",
                "remote_reasoning_acknowledgement_required": "PRIVACY_REMOTE_ACK_REQUIRED",
                "provider_task_unsupported": "PROVIDER_TASK_UNSUPPORTED",
            }
            raise CoreDomainError(
                codes.get(route.reason, "PROVIDER_UNCONFIGURED"),
                "Configure an allowed, ready reasoning provider in Settings to suggest narrative.",
            )
        request, _ = self._context.build(
            project_id=project,
            task_type=TASK_TYPE,
            question=instruction,
            user_input=None,
            privacy_mode=policy["privacy_mode"],
            style_policy="preserve_voice",
            provider_id=provider.id,
            allow_private=False,
            retrieval_query=(fields["objective"] + " " + fields["thesis"] + " " + instruction)[
                :500
            ],
            presentation_revision_id=revision,
            presentation_narrative_snapshot=snapshot,
            latency_budget_ms=30_000,
        )
        supplied = {
            str(item["evidence_id"]): item
            for item in (*request.evidence, *request.preferred_user_explanations)
        }
        by_id = {slide.slide_id: slide.ordinal for slide in selected}

        def current() -> None:
            with self._semantics._storage.project_database(project) as connection:
                final_policy = connection.execute(
                    "SELECT privacy_mode, remote_reasoning_acknowledged_at FROM project WHERE id=?",
                    (project,),
                ).fetchone()
            if final_policy["privacy_mode"] != policy["privacy_mode"] or (
                final_policy["remote_reasoning_acknowledged_at"] is not None
            ) != (policy["remote_reasoning_acknowledged_at"] is not None):
                raise CoreDomainError(
                    "PRIVACY_POLICY_CHANGED",
                    "Project privacy changed during narrative analysis. Review settings and retry.",
                    retryable=True,
                )
            latest = self._narrative.get_narrative(scope)
            if latest["record_token"] != expected:
                raise CoreDomainError(
                    "PRESENTATION_NARRATIVE_CONFLICT",
                    "Narrative changed during suggestion. Reload and retry.",
                    retryable=True,
                )
            _, _, _, checked = self._semantics._workspace_sources.read_revision_inventory(scope)
            if checked.source_sha256 != native.source_sha256:
                raise CoreDomainError("SOURCE_SNAPSHOT_CHANGED", "The analyzed deck changed.")

        def validate(output: dict[str, Any]) -> dict[str, Any]:
            checked = validate_provider_output(TASK_TYPE, output)
            ids = [item["slide_id"] for item in checked["findings"]]
            if len(ids) != len(set(ids)) or any(i not in by_id for i in ids):
                raise ProviderError(
                    "PROVIDER_MALFORMED_OUTPUT", "A narrative finding targets an unsupplied slide."
                )
            if any(e not in supplied for item in checked["findings"] for e in item["evidence_ids"]):
                raise ProviderError(
                    "PROVIDER_MALFORMED_OUTPUT", "Narrative cites evidence that was not supplied."
                )
            current()
            return checked

        def before(_run_id: str, _manifest: dict[str, Any]) -> None:
            current()

        result = self._execution.execute(
            project_id=project,
            session_id=None,
            provider=provider,
            request=request,
            before_provider=before,
            output_validator=validate,
        )
        return {
            **result.result.output,
            "findings": [
                {**item, "slide_number": by_id[item["slide_id"]]}
                for item in result.result.output["findings"]
            ],
            "revision_id": revision,
            "expected_record_token": expected,
            "analysis_scope": analysis_scope,
            "provider_run_id": result.provider_run_id,
            "provider_id": provider.id,
            "model_id": provider.model_id,
            "requires_user_review": True,
            "slide_takeaways": json.loads(request.current_slide_summary or "{}").get(
                "slide_takeaways"
            ),
            "reviewed_claim_context": json.loads(request.current_slide_summary or "{}").get(
                "reviewed_claim_context"
            ),
            "evidence": [
                {
                    "evidence_id": key,
                    "text": value.get("text", ""),
                    "source_locator": value.get("source_locator"),
                }
                for key, value in supplied.items()
            ],
        }
