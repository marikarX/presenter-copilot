"""The single privacy and lifecycle boundary for provider execution.

Provider adapters are deliberately small.  This service owns the decisions
that must be identical for Teach, Challenge, and Live Assist: rereading the
project privacy authority, validating the actual serialized payload, creating
and finalizing ProviderRun, and translating bounded provider failures.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from time import monotonic
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.project.service import utc_now
from presenter_core.storage.service import StorageManager

from .context import (
    APPLICATION_POLICY,
    MAX_CURRENT_USER_INPUT_CHARS,
    MAX_DOCUMENT_EVIDENCE,
    MAX_SPEAKER_EVIDENCE,
    MAX_TOTAL_CONTEXT_CHARS,
    MAX_TRUSTED_CONTENT_OVERHEAD_CHARS,
    MAX_USER_KNOWLEDGE,
)
from .models import (
    ProviderError,
    ReasoningProvider,
    ReasoningRequest,
    ReasoningResult,
    derive_context_manifest,
    task_instruction_for,
    validate_provider_output,
)
from .service import ProviderService

EventSink = Callable[[str, dict[str, Any]], None]
CancellationCheck = Callable[[], bool]
OutputValidator = Callable[[dict[str, Any]], dict[str, Any]]
BeforeProvider = Callable[[str, dict[str, Any]], None]

_PAYLOAD_KEYS = frozenset(
    {
        "task_type",
        "question",
        "user_input",
        "current_slide_summary",
        "application_policy",
        "untrusted_retrieved_evidence",
        "approved_user_knowledge",
        "approved_speaker_style_evidence",
        "style_context",
        "conflict_metadata",
        "approved_audience_context",
        "challenge_intensity",
        "prior_question_context",
        "style_policy",
        "privacy_mode",
        "latency_budget_ms",
    }
)
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "api_key",
        "access_token",
        "authorization",
        "cookie",
        "credential",
        "full_corpus",
        "full_document",
        "password",
        "pcm",
        "raw_audio",
        "secret",
        "token",
    }
)
_MANIFEST_LIST_FIELDS = (
    "classes_sent",
    "source_ids",
    "knowledge_item_ids",
    "speaker_evidence_ids",
    "audience_profile_ids",
    "audience_observation_ids",
)
_MANIFEST_BOOL_FIELDS = (
    "raw_audio_sent",
    "full_document_sent",
    "full_corpus_sent",
    "private_items_sent",
)
_SAFE_ERROR_CODE = re.compile(r"^[A-Z0-9_]{1,80}$")
_CONTEXT_LIST_KEYS = (
    "untrusted_retrieved_evidence",
    "approved_user_knowledge",
    "approved_speaker_style_evidence",
    "conflict_metadata",
    "approved_audience_context",
    "prior_question_context",
)


@dataclass(frozen=True)
class ProviderExecutionResult:
    """Validated provider output plus the durable run and safe manifest."""

    result: ReasoningResult
    provider_run_id: str
    context_manifest: dict[str, Any]


class ProviderExecutionError(ProviderError):
    """A provider error carrying only the safe local ProviderRun identifier."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        provider_run_id: str | None = None,
    ) -> None:
        super().__init__(code, message, retryable=retryable, details=details)
        self.provider_run_id = provider_run_id


class _ExecutionCancelled(Exception):
    pass


class _ExecutionTimedOut(Exception):
    pass


class ProviderExecutionService:
    """Execute one bounded provider request under one privacy authority."""

    def __init__(
        self,
        storage: StorageManager,
        providers: ProviderService,
        event_sink: EventSink | None = None,
    ) -> None:
        self._storage = storage
        self._providers = providers
        self._event_sink = event_sink

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        self._event_sink = event_sink

    def execute(
        self,
        *,
        project_id: str,
        session_id: str | None,
        provider: ReasoningProvider,
        request: ReasoningRequest,
        cancellation_check: CancellationCheck | None = None,
        output_validator: OutputValidator | None = None,
        before_provider: BeforeProvider | None = None,
    ) -> ProviderExecutionResult:
        """Run a request without holding a SQLite transaction over I/O."""
        initial_mode, initial_ack = self._project_authority(project_id)
        self._validate_authority(
            request=request,
            provider=provider,
            privacy_mode=initial_mode,
            remote_acknowledged=initial_ack,
        )
        health = self._providers.health(provider)
        if health.status != "ready" and not health.retryable:
            raise ProviderError(
                health.error_code or "PROVIDER_UNAVAILABLE",
                "The selected reasoning provider is not ready.",
                retryable=health.retryable,
            )
        if request.task_type not in provider.capabilities().task_types:
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The selected reasoning provider does not support this task.",
            )

        payload = request.to_payload()
        self._validate_payload(request, payload, provider)
        manifest = derive_context_manifest(request, provider_id=provider.id, payload=payload)
        self._validate_claimed_manifest(request.context_manifest, manifest)

        run_id = str(uuid.uuid4())
        started = monotonic()
        try:
            self._start_provider_run(
                project_id=project_id,
                session_id=session_id,
                request=request,
                privacy_mode=initial_mode,
                provider=provider,
                manifest=manifest,
                run_id=run_id,
            )
        except CoreDomainError:
            raise

        try:
            if provider.locality == "remote":
                self._emit(
                    "privacy.remote_context_manifest",
                    {
                        **manifest,
                        "provider_id": provider.id,
                        "provider_run_id": run_id,
                    },
                )
            # The project row is the authority immediately before the adapter
            # call. The initial route decision and session state are not enough.
            current_mode, current_ack = self._project_authority(project_id)
            self._validate_authority(
                request=request,
                provider=provider,
                privacy_mode=current_mode,
                remote_acknowledged=current_ack,
            )
            if cancellation_check is not None and cancellation_check():
                raise _ExecutionCancelled
            if before_provider is not None:
                before_provider(run_id, manifest)
            if cancellation_check is not None and cancellation_check():
                raise _ExecutionCancelled
            result = self._invoke_with_budget(
                provider,
                request,
                cancellation_check=cancellation_check,
            )
            if cancellation_check is not None and cancellation_check():
                raise _ExecutionCancelled
            if not isinstance(result, ReasoningResult) or not isinstance(result.output, dict):
                raise ProviderError(
                    "PROVIDER_MALFORMED_OUTPUT",
                    "The reasoning provider returned malformed structured output.",
                )
            output = validate_provider_output(
                request.task_type,
                result.output,
                conflict_metadata=request.conflict_metadata,
            )
            if output_validator is not None:
                output = output_validator(output)
            if cancellation_check is not None and cancellation_check():
                raise _ExecutionCancelled
            result = replace(result, output=output)
        except _ExecutionCancelled:
            error = ProviderExecutionError(
                "PROVIDER_CANCELLED",
                "The reasoning result was cancelled before it became eligible.",
                retryable=True,
                provider_run_id=run_id,
            )
            self._finish_provider_run(
                project_id, run_id, status="cancelled", error=error, started=started
            )
            raise error from None
        except _ExecutionTimedOut:
            error = ProviderExecutionError(
                "PROVIDER_TIMEOUT",
                "The reasoning provider timed out within the bounded request budget.",
                retryable=True,
                provider_run_id=run_id,
            )
            self._finish_provider_run(
                project_id, run_id, status="error", error=error, started=started
            )
            self._providers.record_failure(provider, error)
            raise error from None
        except ProviderError as error:
            execution_error = self._with_run_id(error, run_id)
            self._finish_provider_run(
                project_id,
                run_id,
                status="error",
                error=execution_error,
                started=started,
            )
            if not execution_error.code.startswith("PRIVACY_"):
                self._providers.record_failure(provider, execution_error)
            raise execution_error from None
        except CoreDomainError as error:
            execution_error = ProviderExecutionError(
                error.code,
                error.message,
                retryable=error.retryable,
                details=error.details,
                provider_run_id=run_id,
            )
            self._finish_provider_run(
                project_id,
                run_id,
                status="error",
                error=execution_error,
                started=started,
            )
            raise execution_error from None
        except Exception as error:
            mapped = ProviderExecutionError(
                "PROVIDER_REQUEST_FAILED",
                "The reasoning provider request failed.",
                retryable=True,
                provider_run_id=run_id,
            )
            self._finish_provider_run(
                project_id, run_id, status="error", error=mapped, started=started
            )
            self._providers.record_failure(provider, mapped)
            raise mapped from error

        self._finish_provider_run(
            project_id, run_id, status="success", result=result, started=started
        )
        self._providers.record_success(provider)
        return ProviderExecutionResult(
            result=result,
            provider_run_id=run_id,
            context_manifest=manifest,
        )

    def list_context_manifests(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return only bounded ProviderRun metadata and sanitized manifests."""
        reject_unknown_fields(params, {"project_id", "session_id", "limit", "offset"})
        project_id = params.get("project_id")
        if not isinstance(project_id, str) or not project_id.strip():
            raise invalid_request("project_id must be a non-empty string.", field="project_id")
        session_id = params.get("session_id")
        if session_id is not None:
            session_id = self._uuid(session_id, "session_id")
        limit = self._bounded_int(params.get("limit", 10), "limit", 1, 25)
        offset = self._bounded_int(params.get("offset", 0), "offset", 0, 10_000)
        where = ""
        values: list[Any] = []
        if session_id is not None:
            where = " WHERE session_id = ?"
            values.append(session_id)
        with self._storage.project_database(project_id) as connection:
            total_row = connection.execute(
                f"SELECT COUNT(*) AS count FROM provider_runs{where}", values
            ).fetchone()
            rows = connection.execute(
                "SELECT id, session_id, task_type, provider_id, privacy_mode, started_at, "
                "ended_at, status, input_token_count, output_token_count, latency_ms, "
                "context_manifest_json, error_code FROM provider_runs"
                f"{where} ORDER BY started_at DESC, id DESC LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
        total = int(total_row["count"]) if total_row is not None else 0
        manifests = [self._history_row(row) for row in rows]
        return {
            "project_id": project_id,
            "session_id": session_id,
            "manifests": manifests,
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(manifests) < total,
        }

    def _invoke_with_budget(
        self,
        provider: ReasoningProvider,
        request: ReasoningRequest,
        *,
        cancellation_check: CancellationCheck | None,
    ) -> ReasoningResult:
        budget_ms = request.latency_budget_ms
        if not isinstance(budget_ms, int) or budget_ms <= 0:
            raise _ExecutionTimedOut
        result: list[ReasoningResult] = []
        failure: list[BaseException] = []
        finished = threading.Event()

        def invoke() -> None:
            try:
                result.append(provider.generate(request))
            except BaseException as error:  # pass adapter failures back to the boundary
                failure.append(error)
            finally:
                finished.set()

        worker = threading.Thread(target=invoke, name="provider-execution", daemon=True)
        worker.start()
        deadline = monotonic() + budget_ms / 1000.0
        while not finished.wait(timeout=0.025):
            if cancellation_check is not None and cancellation_check():
                raise _ExecutionCancelled
            if monotonic() >= deadline:
                raise _ExecutionTimedOut
        if cancellation_check is not None and cancellation_check():
            raise _ExecutionCancelled
        if failure:
            error = failure[0]
            if isinstance(error, ProviderError):
                raise error
            if isinstance(error, CoreDomainError):
                raise error
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The reasoning provider request failed.",
                retryable=True,
            ) from error
        if not result:
            raise ProviderError(
                "PROVIDER_MALFORMED_OUTPUT",
                "The reasoning provider returned no structured result.",
            )
        return result[0]

    def _start_provider_run(
        self,
        *,
        project_id: str,
        session_id: str | None,
        request: ReasoningRequest,
        privacy_mode: str,
        provider: ReasoningProvider,
        manifest: dict[str, Any],
        run_id: str,
    ) -> None:
        with self._storage.project_database(project_id) as connection:
            connection.execute(
                """
                INSERT INTO provider_runs (
                    id, session_id, task_type, provider_id, privacy_mode,
                    started_at, status, context_manifest_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'started', ?)
                """,
                (
                    run_id,
                    session_id,
                    request.task_type,
                    provider.id,
                    privacy_mode,
                    utc_now(),
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                ),
            )
            connection.commit()

    def _finish_provider_run(
        self,
        project_id: str,
        run_id: str,
        *,
        status: str,
        result: ReasoningResult | None = None,
        error: ProviderError | None = None,
        started: float,
    ) -> None:
        with self._storage.project_database(project_id) as connection:
            connection.execute(
                """
                UPDATE provider_runs
                SET ended_at = ?, status = ?, input_token_count = ?, output_token_count = ?,
                    latency_ms = ?, error_code = ?
                WHERE id = ? AND status = 'started'
                """,
                (
                    utc_now(),
                    status,
                    result.input_token_count if result is not None else None,
                    result.output_token_count if result is not None else None,
                    max(0, int((monotonic() - started) * 1000)),
                    error.code if error is not None else None,
                    run_id,
                ),
            )
            connection.commit()

    def _validate_authority(
        self,
        *,
        request: ReasoningRequest,
        provider: ReasoningProvider,
        privacy_mode: str,
        remote_acknowledged: bool,
    ) -> None:
        if request.privacy_mode != privacy_mode:
            raise ProviderExecutionError(
                "PRIVACY_POLICY_CHANGED",
                "Project privacy changed while the provider context was being prepared; retry.",
                retryable=True,
                details={"privacy_mode": privacy_mode},
            )
        if provider.locality not in {"local", "remote"}:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                "The selected provider has an unsupported locality.",
                retryable=True,
            )
        if provider.locality == "remote" and privacy_mode == "local_only":
            raise ProviderExecutionError(
                "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED",
                "Local Only blocks remote reasoning for this project.",
                details={"privacy_mode": privacy_mode, "provider_id": provider.id},
            )
        if provider.locality == "remote" and not remote_acknowledged:
            raise ProviderExecutionError(
                "PRIVACY_REMOTE_ACK_REQUIRED",
                "Explicit project acknowledgement is required before remote reasoning.",
                details={"privacy_mode": privacy_mode},
            )

    def _validate_payload(
        self,
        request: ReasoningRequest,
        payload: dict[str, Any],
        provider: ReasoningProvider,
    ) -> None:
        if set(payload) != _PAYLOAD_KEYS:
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The reasoning payload did not match the core provider contract.",
            )
        if (
            payload.get("task_type") != request.task_type
            or payload.get("latency_budget_ms") != request.latency_budget_ms
            or not isinstance(payload.get("task_type"), str)
            or not isinstance(payload.get("latency_budget_ms"), int)
        ):
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The serialized reasoning payload did not match the request.",
            )
        if request.application_policy != APPLICATION_POLICY:
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The reasoning request policy is not core-owned.",
            )
        if request.task_instruction != task_instruction_for(request.task_type):
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The reasoning task instruction is not core-owned.",
            )
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if (
            len(serialized)
            + len(APPLICATION_POLICY)
            + len(request.task_instruction or "")
            + MAX_TRUSTED_CONTENT_OVERHEAD_CHARS
            > MAX_TOTAL_CONTEXT_CHARS
        ):
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The reasoning payload exceeded the bounded context contract.",
            )
        for key in payload:
            if self._contains_forbidden_key(key, payload[key]):
                raise ProviderError(
                    "PROVIDER_REQUEST_FAILED",
                    "The reasoning payload contained a forbidden credential or raw-media field.",
                )

        if not isinstance(payload.get("style_context"), Mapping):
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The reasoning payload style context was malformed.",
            )
        try:
            context_lists = {
                key: self._strict_dict_list(payload[key], key) for key in _CONTEXT_LIST_KEYS
            }
        except ValueError as error:
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The reasoning payload contained malformed context records.",
            ) from error
        evidence = context_lists["untrusted_retrieved_evidence"]
        knowledge = context_lists["approved_user_knowledge"]
        speaker = context_lists["approved_speaker_style_evidence"]
        conflicts = context_lists["conflict_metadata"]
        audience = context_lists["approved_audience_context"]
        prior = context_lists["prior_question_context"]
        if len(evidence) > MAX_DOCUMENT_EVIDENCE:
            raise ProviderError("PROVIDER_REQUEST_FAILED", "Too much document evidence was sent.")
        if len(knowledge) > MAX_USER_KNOWLEDGE:
            raise ProviderError("PROVIDER_REQUEST_FAILED", "Too much user knowledge was sent.")
        if len(speaker) > MAX_SPEAKER_EVIDENCE or len(conflicts) > 3 or len(prior) > 3:
            raise ProviderError("PROVIDER_REQUEST_FAILED", "Too much contextual history was sent.")
        observation_count = 0
        for profile in audience:
            observations = profile.get("observations", [])
            if not isinstance(observations, list) or any(
                not isinstance(observation, dict) for observation in observations
            ):
                raise ProviderError(
                    "PROVIDER_REQUEST_FAILED",
                    "The audience context observations were malformed.",
                )
            observation_count += len(observations)
        if len(audience) > 3 or observation_count > 24:
            raise ProviderError("PROVIDER_REQUEST_FAILED", "Too much audience context was sent.")
        if request.task_type == "live_cue" and prior:
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "Live Assist cannot send prior question or transcript context.",
            )
        if (
            isinstance(payload.get("user_input"), str)
            and request.task_type == "challenge_evaluation"
        ):
            if len(payload["user_input"]) > MAX_CURRENT_USER_INPUT_CHARS:
                raise ProviderError(
                    "PROVIDER_REQUEST_FAILED",
                    "The current Challenge answer exceeded the bounded input contract.",
                )
        private_items = [item for item in [*evidence, *knowledge] if item.get("private")]
        if provider.locality == "remote" and (
            private_items or self._contains_private_marker(payload)
        ):
            raise ProviderExecutionError(
                "PRIVACY_PRIVATE_CONTEXT_BLOCKED",
                "Private KnowledgeItems are never eligible for remote reasoning.",
                details={"private_item_count": len(private_items)},
            )
        if payload.get("privacy_mode") != request.privacy_mode:
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The serialized reasoning payload privacy mode did not match the request.",
            )

    @staticmethod
    def _contains_forbidden_key(key: Any, value: Any) -> bool:
        if isinstance(key, str) and key.casefold() in _FORBIDDEN_PAYLOAD_KEYS:
            return True
        if isinstance(value, Mapping):
            return any(
                ProviderExecutionService._contains_forbidden_key(child_key, child_value)
                for child_key, child_value in value.items()
            )
        if isinstance(value, list):
            return any(
                ProviderExecutionService._contains_forbidden_key("", child) for child in value
            )
        return False

    @staticmethod
    def _contains_private_marker(value: Any) -> bool:
        if isinstance(value, Mapping):
            if value.get("private"):
                return True
            return any(
                ProviderExecutionService._contains_private_marker(child) for child in value.values()
            )
        if isinstance(value, list):
            return any(ProviderExecutionService._contains_private_marker(child) for child in value)
        return False

    @staticmethod
    def _strict_dict_list(value: Any, field: str) -> list[dict[str, Any]]:
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError(field)
        return [dict(item) for item in value]

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
    def _validate_claimed_manifest(
        claimed: dict[str, Any],
        derived: dict[str, Any],
    ) -> None:
        if claimed and claimed != derived:
            raise ProviderError(
                "PRIVACY_MANIFEST_MISMATCH",
                "The claimed provider context manifest did not match the final payload.",
            )

    @staticmethod
    def _with_run_id(error: ProviderError, run_id: str) -> ProviderExecutionError:
        return ProviderExecutionError(
            error.code,
            error.message,
            retryable=error.retryable,
            details=error.details,
            provider_run_id=run_id,
        )

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)

    def _history_row(self, row: Any) -> dict[str, Any]:
        try:
            raw_manifest = json.loads(str(row["context_manifest_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            raw_manifest = {}
        manifest = self._safe_manifest(raw_manifest)
        error_code = row["error_code"]
        safe_error_code = (
            str(error_code)[:80]
            if isinstance(error_code, str) and _SAFE_ERROR_CODE.fullmatch(error_code)
            else None
        )
        return {
            "provider_run_id": str(row["id"]),
            "session_id": str(row["session_id"]) if row["session_id"] is not None else None,
            "task_type": str(row["task_type"])[:80],
            "provider_id": str(row["provider_id"])[:80],
            "privacy_mode": str(row["privacy_mode"])[:40],
            "started_at": str(row["started_at"])[:80],
            "ended_at": str(row["ended_at"])[:80] if row["ended_at"] is not None else None,
            "status": str(row["status"])[:20],
            "input_token_count": row["input_token_count"],
            "output_token_count": row["output_token_count"],
            "latency_ms": row["latency_ms"],
            "error_code": safe_error_code,
            "context_manifest": manifest,
        }

    @staticmethod
    def _safe_manifest(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            return {}
        safe: dict[str, Any] = {}
        for key in ("provider_content_boundary", "provider_id", "task_type", "privacy_mode"):
            item = value.get(key)
            if isinstance(item, str):
                safe[key] = item[:120]
        for key in _MANIFEST_LIST_FIELDS:
            item = value.get(key)
            if isinstance(item, list):
                safe[key] = [str(entry)[:120] for entry in item if isinstance(entry, str)][:25]
        for key in _MANIFEST_BOOL_FIELDS:
            item = value.get(key)
            if isinstance(item, bool):
                safe[key] = item
        for key in ("prior_question_count", "bounded_context_chars"):
            item = value.get(key)
            if isinstance(item, int) and item >= 0:
                safe[key] = min(item, MAX_TOTAL_CONTEXT_CHARS)
        return safe

    @staticmethod
    def _bounded_int(value: Any, field: str, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise invalid_request(
                f"{field} must be an integer between {minimum} and {maximum}.", field=field
            )
        return int(value)

    @staticmethod
    def _uuid(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a UUID.", field=field) from error
