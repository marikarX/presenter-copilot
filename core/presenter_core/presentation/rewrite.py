"""Review-only single-target text rewrite proposals for Presentation Workspace."""

from __future__ import annotations

import json
import uuid
from typing import Any, NoReturn

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.rehearsal import PresentationRehearsalService
from presenter_core.presentation.rehearsal_semantic_adoption import RehearsalSemanticAdoption
from presenter_core.presentation.workspace_source import PresentationWorkspaceSourceService
from presenter_core.providers.context import APPLICATION_POLICY
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.models import (
    DEFAULT_REASONING_LATENCY_BUDGET_MS,
    ReasoningRequest,
    output_schema_for,
    task_instruction_for,
)
from presenter_core.providers.router import ReasoningRoute, ReasoningRouter
from presenter_core.providers.service import ProviderService
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

TASK_TYPE = "presentation_text_rewrite"
MAX_REWRITE_INSTRUCTION_CHARS = 500
MAX_REWRITE_SOURCE_CHARS = 2_000


class PresentationRewriteService:
    """Propose one safe text replacement without granting providers edit access."""

    def __init__(
        self,
        storage: StorageManager,
        workspace_sources: PresentationWorkspaceSourceService,
        providers: ProviderService,
        execution: ProviderExecutionService,
        rehearsal: PresentationRehearsalService | None = None,
    ) -> None:
        self._storage = storage
        self._workspace_sources = workspace_sources
        self._providers = providers
        self._execution = execution
        self._router = ReasoningRouter()
        self._rehearsal = rehearsal

    def propose_text_rewrite(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_number",
                "object_id",
                "instruction",
                "rehearsal_finding_id",
            },
        )
        project_value = params.get("project_id")
        if not isinstance(project_value, str):
            raise invalid_request("project_id must be a UUID.", field="project_id")
        project_id = normalize_project_id(project_value)
        document_id = self._uuid_field(params.get("document_id"), "document_id")
        revision_id = self._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
        object_id = self._uuid_field(params.get("object_id"), "object_id")
        slide_number = self._slide_number(params.get("slide_number"))
        instruction = self._instruction(params.get("instruction"))

        selected = self._selected_text(
            project_id,
            document_id,
            revision_id,
            slide_number,
            object_id,
        )
        finding: dict[str, Any] | None = None
        finding_id = params.get("rehearsal_finding_id")
        finding_params = {
            "project_id": project_id,
            "document_id": document_id,
            "expected_revision_id": revision_id,
            "finding_id": finding_id,
        }
        if finding_id is not None:
            if self._rehearsal is None:
                raise CoreDomainError(
                    "REHEARSAL_FINDING_NOT_FOUND", "Rehearsal findings are unavailable."
                )
            finding = self._rehearsal.resolve_finding(finding_params)
            RehearsalSemanticAdoption.require_text_target(finding, object_id)
            if finding["slide_id"] != selected["slide_id"]:
                raise invalid_request(
                    "The finding belongs to another slide.", field="rehearsal_finding_id"
                )
        privacy_mode, remote_acknowledged = self._project_authority(project_id)
        provider, health = self._providers.current_provider_and_health()
        route = self._router.decide(
            task_type=TASK_TYPE,
            privacy_mode=privacy_mode,
            remote_acknowledged=remote_acknowledged,
            provider=provider,
            provider_health=health,
        )
        if route.route == ReasoningRoute.RETRIEVAL_ONLY or provider is None:
            self._raise_route_error(route.reason, health)

        selected_text = str(selected["text"])
        request = ReasoningRequest(
            task_type=TASK_TYPE,
            question=instruction,
            user_input=None,
            current_slide_summary=json.dumps(
                {
                    "selected_text": selected_text,
                    **(
                        {
                            "rehearsal_finding": {
                                "kind": finding["kind"],
                                "quote": finding["quote"],
                                "provenance": "rehearsal_candidate_requires_user_review",
                                **(
                                    {"semantic_review": finding["semantic_review"]}
                                    if finding["kind"]
                                    in {"semantic_coverage", "semantic_objection"}
                                    else {}
                                ),
                            }
                        }
                        if finding is not None
                        else {}
                    ),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            evidence=(),
            preferred_user_explanations=(),
            speaker_evidence=(),
            style_context={},
            conflict_metadata=(),
            style_policy="preserve_voice",
            privacy_mode=privacy_mode,
            output_schema=output_schema_for(TASK_TYPE),
            latency_budget_ms=DEFAULT_REASONING_LATENCY_BUDGET_MS,
            application_policy=APPLICATION_POLICY,
            task_instruction=task_instruction_for(TASK_TYPE),
            source_ids=(document_id,),
            presentation_revision_ids=tuple(
                dict.fromkeys((revision_id, str(finding["source_revision_id"])))
            )
            if finding
            else (revision_id,),
            rehearsal_session_ids=(str(finding["session_id"]),) if finding else (),
            rehearsal_finding_ids=(str(finding["finding_id"]),) if finding else (),
        )

        def assert_current_context() -> None:
            self._assert_selection_current(
                project_id,
                document_id,
                revision_id,
                slide_number,
                object_id,
                selected_text,
            )
            if finding is not None and self._rehearsal is not None:
                self._rehearsal.resolve_finding(finding_params)

        def validate_current_selection(output: dict[str, Any]) -> dict[str, Any]:
            # Keep stale proposals out of successful ProviderRun history too.
            assert_current_context()
            return output

        execution_result = self._execution.execute(
            project_id=project_id,
            session_id=None,
            provider=provider,
            request=request,
            output_validator=validate_current_selection,
            before_provider=lambda _run_id, _manifest: assert_current_context(),
        )
        # Recheck once more after run finalization, including the narrow window
        # between output validation and the successful ProviderRun commit.
        assert_current_context()
        output = execution_result.result.output
        return {
            "provider_run_id": execution_result.provider_run_id,
            "document_id": document_id,
            "revision_id": revision_id,
            "slide_id": selected["slide_id"],
            "slide_number": slide_number,
            "object_id": object_id,
            "current_text": selected_text,
            "replacement_text": output["replacement_text"],
            "edit_summary": output["edit_summary"],
            "provider_id": provider.id,
            "model_id": provider.model_id,
            "latency_ms": execution_result.result.latency_ms,
            "requires_user_review": True,
        }

    def _selected_text(
        self,
        project_id: str,
        document_id: str,
        revision_id: str,
        slide_number: int,
        object_id: str,
    ) -> dict[str, Any]:
        selected = self._workspace_sources.list_text_targets(
            {
                "project_id": project_id,
                "document_id": document_id,
                "revision_id": revision_id,
                "slide_number": slide_number,
            }
        )
        targets = selected.get("targets")
        if not isinstance(targets, list):
            raise CoreDomainError(
                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                "The selected presentation text target could not be verified.",
            )
        target = next(
            (
                item
                for item in targets
                if isinstance(item, dict) and item.get("object_id") == object_id
            ),
            None,
        )
        if target is None:
            raise CoreDomainError(
                "PRESENTATION_REWRITE_TARGET_UNSUPPORTED",
                "Select a supported text shape before requesting a rewrite.",
            )
        text = target.get("current_text")
        editable = (
            target.get("single_run_editable") is True or target.get("uniform_run_editable") is True
        )
        if (
            not editable
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > MAX_REWRITE_SOURCE_CHARS
            or "\n" in text
            or "\r" in text
        ):
            raise CoreDomainError(
                "PRESENTATION_REWRITE_TARGET_UNSUPPORTED",
                "This text shape is outside the supported single-paragraph rewrite scope.",
            )
        slide_id = selected.get("slide_id")
        if not isinstance(slide_id, str):
            raise CoreDomainError(
                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                "The selected slide identity could not be verified.",
            )
        return {"text": text, "slide_id": slide_id}

    def _assert_selection_current(
        self,
        project_id: str,
        document_id: str,
        revision_id: str,
        slide_number: int,
        object_id: str,
        expected_text: str,
    ) -> None:
        selected = self._selected_text(
            project_id,
            document_id,
            revision_id,
            slide_number,
            object_id,
        )
        if selected["text"] != expected_text:
            raise CoreDomainError(
                "PRESENTATION_REVISION_CONFLICT",
                "The selected text changed while the rewrite was running. Refresh and retry.",
                retryable=True,
            )

    def _project_authority(self, project_id: str) -> tuple[str, bool]:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                "SELECT privacy_mode, remote_reasoning_acknowledged_at FROM project WHERE id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
        return str(row["privacy_mode"]), row["remote_reasoning_acknowledged_at"] is not None

    @staticmethod
    def _raise_route_error(reason: str, health: Any | None) -> NoReturn:
        if reason == "local_only":
            raise CoreDomainError(
                "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED",
                "Local Only blocks the selected reasoning provider for rewrite proposals.",
            )
        if reason == "remote_reasoning_acknowledgement_required":
            raise CoreDomainError(
                "PRIVACY_REMOTE_ACK_REQUIRED",
                "Acknowledge remote reasoning in project privacy settings "
                "before requesting a rewrite.",
            )
        if reason == "provider_task_unsupported":
            raise CoreDomainError(
                "PROVIDER_TASK_UNSUPPORTED",
                "The selected reasoning provider does not support text rewrite proposals.",
            )
        if health is not None and health.error_code:
            raise CoreDomainError(
                health.error_code,
                "The selected reasoning provider is not available for this rewrite.",
                retryable=health.retryable,
            )
        raise CoreDomainError(
            "PROVIDER_UNCONFIGURED",
            "Configure a reasoning provider before requesting a text rewrite.",
        )

    @staticmethod
    def _uuid_field(value: object, field: str) -> str:
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a UUID.", field=field) from error

    @staticmethod
    def _slide_number(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5_000:
            raise invalid_request("slide_number must be between 1 and 5000.", field="slide_number")
        return value

    @staticmethod
    def _instruction(value: object) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > MAX_REWRITE_INSTRUCTION_CHARS
            or "\x00" in value
        ):
            raise invalid_request(
                "instruction must contain 1 to 500 characters.", field="instruction"
            )
        return value.strip()
