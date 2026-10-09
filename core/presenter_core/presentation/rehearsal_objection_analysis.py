"""Execute explicit, window-scoped rehearsal hints against freshly verified context."""

from collections.abc import Callable
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.limits import MAX_RUN_UTTERANCES_PER_SESSION
from presenter_core.presentation.rehearsal_analysis_store import recording_state
from presenter_core.presentation.rehearsal_objection_context import (
    RehearsalObjectionContext,
    objection_context_size,
    objection_request,
)
from presenter_core.presentation.rehearsal_objection_store import (
    RehearsalObjectionStore,
)
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.providers.context import MAX_TOTAL_CONTEXT_CHARS
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.rehearsal_objection_schema import TASK_TYPE, validate_window_output
from presenter_core.providers.router import ReasoningRoute, ReasoningRouter
from presenter_core.providers.service import ProviderService


class RehearsalObjectionAnalysis:
    def __init__(
        self,
        semantics: PresentationSemanticService,
        providers: ProviderService,
        execution: ProviderExecutionService,
    ) -> None:
        self._semantics, self._providers, self._execution = semantics, providers, execution
        self._context = RehearsalObjectionContext(semantics)

    def prepare_analysis(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], int]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "session_id",
                "slide_id",
                "expected_context_sha256",
                "expected_recording_sha256",
                "window_index",
            },
        )
        fingerprint, index = params.get("expected_context_sha256"), params.get("window_index")
        recording = params.get("expected_recording_sha256")
        if (
            not isinstance(recording, str)
            or len(recording) != 64
            or any(c not in "0123456789abcdef" for c in recording)
        ):
            raise invalid_request("Prepare the exact recording before objection analysis.")
        if (
            not isinstance(fingerprint, str)
            or len(fingerprint) != 64
            or any(char not in "0123456789abcdef" for char in fingerprint)
        ):
            raise invalid_request("Prepare the exact rehearsal context before analysis.")
        if type(index) is not int or not 0 <= index <= MAX_RUN_UTTERANCES_PER_SESSION:
            raise invalid_request("Choose a prepared speech window.")
        selection = {
            key: value
            for key, value in params.items()
            if key not in {"expected_context_sha256", "expected_recording_sha256", "window_index"}
        }
        selection.update({"offset": index, "limit": 1})
        prepared = self._context.prepare(selection)
        if prepared["context_sha256"] != fingerprint or prepared["recording_sha256"] != recording:
            raise CoreDomainError(
                "REHEARSAL_CONTEXT_CHANGED",
                "The recorded context changed. Prepare it again.",
                retryable=True,
            )
        if not prepared["windows"]:
            raise invalid_request("Choose an available recorded speech window.")
        return selection, prepared, index

    def analyze(
        self,
        params: dict[str, Any],
        *,
        cancellation_check: Callable[[], bool] | None = None,
        before_persist: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        if cancellation_check is not None and cancellation_check():
            raise CoreDomainError("PROVIDER_CANCELLED", "The analysis was cancelled.")
        selection, prepared, index = self.prepare_analysis(params)
        project = self._semantics._project_id(params.get("project_id"))

        def policy() -> tuple[str, bool]:
            with self._semantics._storage.project_database(project) as connection:
                row = connection.execute(
                    "SELECT privacy_mode,remote_reasoning_acknowledged_at FROM project WHERE id=?",
                    (project,),
                ).fetchone()
            return str(row["privacy_mode"]), row["remote_reasoning_acknowledged_at"] is not None

        initial_policy = policy()
        with self._semantics._storage.project_database(project) as connection:
            initial_recording = recording_state(connection, prepared["session_id"])
        provider, health = self._providers.current_provider_and_health()
        route = ReasoningRouter().decide(
            task_type=TASK_TYPE,
            privacy_mode=initial_policy[0],
            remote_acknowledged=initial_policy[1],
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
                "Configure an allowed, ready reasoning provider in Settings.",
            )
        window = prepared["windows"][0]
        source = {
            key: prepared[key]
            for key in (
                "document_id",
                "session_id",
                "source_revision_id",
                "source_sha256",
                "slide_id",
                "source_slide_number",
            )
        }
        request = objection_request(source, window["utterances"], initial_policy[0])
        if objection_context_size(request) > MAX_TOTAL_CONTEXT_CHARS:
            raise invalid_request("The prepared speech exceeds the serialized context budget.")

        def current() -> None:
            if policy() != initial_policy:
                raise CoreDomainError(
                    "PRIVACY_POLICY_CHANGED",
                    "Project privacy changed during analysis. Review and retry.",
                    retryable=True,
                )
            if self._context.prepare(selection) != prepared:
                raise CoreDomainError(
                    "REHEARSAL_CONTEXT_CHANGED",
                    "The rehearsal context changed during analysis. Prepare again.",
                    retryable=True,
                )

        def validate(output: dict[str, Any]) -> dict[str, Any]:
            current()
            return validate_window_output(output, window["utterances"])

        executed = self._execution.execute(
            project_id=project,
            session_id=prepared["session_id"],
            provider=provider,
            request=request,
            cancellation_check=cancellation_check,
            before_provider=lambda _id, _manifest: current(),
            output_validator=validate,
        )
        current()
        result = {
            **prepared,
            "window_index": index,
            "hint": executed.result.output,
            "provider_run_id": executed.provider_run_id,
            "provider_id": provider.id,
            "model_id": provider.model_id,
            "privacy_mode": initial_policy[0],
            "requires_user_review": True,
        }

        def transaction_guard(connection: Any) -> None:
            row = connection.execute(
                "SELECT privacy_mode,remote_reasoning_acknowledged_at FROM project WHERE id=?",
                (project,),
            ).fetchone()
            if (
                str(row["privacy_mode"]),
                row["remote_reasoning_acknowledged_at"] is not None,
            ) != initial_policy:
                raise CoreDomainError(
                    "PRIVACY_POLICY_CHANGED", "Project privacy changed before storage."
                )
            if recording_state(connection, prepared["session_id"]) != initial_recording:
                raise CoreDomainError(
                    "REHEARSAL_CONTEXT_CHANGED", "Recorded context changed before storage."
                )
            if cancellation_check is not None and cancellation_check():
                raise CoreDomainError(
                    "PROVIDER_CANCELLED", "The analysis was cancelled before storage."
                )

            if before_persist is not None:
                before_persist()

        return RehearsalObjectionStore(self._semantics).save(
            project,
            result,
            transaction_guard=transaction_guard,
        )
