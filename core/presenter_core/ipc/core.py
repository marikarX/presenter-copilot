"""Core request dispatcher and service composition."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from time import monotonic
from typing import Any

from presenter_core import CORE_VERSION
from presenter_core.asr.adapters import (
    DEFAULT_ASR_ADAPTER_ID,
    FasterWhisperASRAdapter,
)
from presenter_core.asr.interfaces import ASRAdapter, AudioInputAdapter
from presenter_core.asr.segmenter import VADConfig
from presenter_core.asr.service import ASRService
from presenter_core.audience.service import AudienceModelService
from presenter_core.challenge.service import ChallengeService
from presenter_core.credentials import (
    CredentialStore,
    InMemoryCredentialStore,
    OpenRouterCredentialStore,
    WindowsCredentialStore,
)
from presenter_core.decisions.models import DecisionProvider
from presenter_core.decisions.service import DecisionWorkflowService
from presenter_core.diagnostics import DiagnosticService
from presenter_core.errors import CoreDomainError, reject_unknown_fields
from presenter_core.ingestion.service import IngestionService
from presenter_core.knowledge.service import KnowledgeService
from presenter_core.live.service import AssistService
from presenter_core.live.settings import HudSettingsService
from presenter_core.model_service import ModelService
from presenter_core.presentation.adapters import PresentationAdapter
from presenter_core.presentation.claims import PresentationClaimService
from presenter_core.presentation.creation import PresentationCreationService
from presenter_core.presentation.edit_planning import PresentationEditPlanningService
from presenter_core.presentation.edit_plans import PresentationEditPlanService
from presenter_core.presentation.editing import PresentationEditService
from presenter_core.presentation.planning import PresentationPlanningService
from presenter_core.presentation.rehearsal import PresentationRehearsalService
from presenter_core.presentation.rehearsal_analysis_jobs import RehearsalAnalysisJobs
from presenter_core.presentation.rehearsal_objection_analysis import RehearsalObjectionAnalysis
from presenter_core.presentation.rehearsal_objection_comparison import (
    RehearsalObjectionComparison,
)
from presenter_core.presentation.rehearsal_semantic_analysis import RehearsalSemanticAnalysis
from presenter_core.presentation.revisions import (
    PresentationRevisionService,
    record_original_revision,
)
from presenter_core.presentation.rewrite import PresentationRewriteService
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.presentation.service import SlideStateService
from presenter_core.presentation.voice import PresentationWorkspaceVoiceService
from presenter_core.presentation.workspace_source import PresentationWorkspaceSourceService
from presenter_core.project.service import ProjectService
from presenter_core.providers.context import ProviderContextBuilder
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.models import ReasoningProvider
from presenter_core.providers.service import ProviderService
from presenter_core.retrieval.embeddings import (
    EmbeddingAdapter,
    FastEmbedAdapter,
    embedding_model_cache_dir,
)
from presenter_core.retrieval.lexical import LexicalRetrievalService
from presenter_core.retrieval.service import HybridRetrievalService
from presenter_core.run.service import RunService
from presenter_core.safe_logging import SafeLogger
from presenter_core.session.service import SessionService
from presenter_core.speaker.service import SpeakerProfileService
from presenter_core.storage.database import PROJECT_SCHEMA_VERSION
from presenter_core.storage.service import StorageManager
from presenter_core.teach.service import TeachService
from presenter_core.transcript.service import TranscriptService

from .protocol import (
    PROTOCOL_VERSION,
    SUPPORTED_EVENTS,
    SUPPORTED_METHODS,
    make_error,
    make_event,
    make_response,
)

EventSink = Callable[[dict[str, Any]], None]


class CoreService:
    """Handle requests while keeping transport and filesystem authority separate."""

    def __init__(
        self,
        clock: Callable[[], float] = monotonic,
        data_root: str | Path | None = None,
        event_sink: EventSink | None = None,
        embedding_adapter: EmbeddingAdapter | None = None,
        reasoning_provider: ReasoningProvider | None = None,
        session_app_cleanup: Callable[[str, str], None] | None = None,
        audio_input: AudioInputAdapter | None = None,
        asr_adapters: Mapping[str, ASRAdapter] | None = None,
        presentation_adapter: PresentationAdapter | None = None,
        vad_config: VADConfig | None = None,
        asr_worker_join_timeout_seconds: float | None = None,
        credential_store: CredentialStore | None = None,
        decision_provider: DecisionProvider | None = None,
        decision_credential_store: CredentialStore | None = None,
        chatgpt_plan_store: Any | None = None,
    ) -> None:
        self._clock = clock
        self._started_at = clock()
        self._shutdown_requested = False
        self._closed = False
        self._last_close_error: CoreDomainError | None = None
        self._event_sink = event_sink
        self._storage = StorageManager(data_root)
        self._logger = SafeLogger(self._storage.paths.root)
        self._presentation_workspace_sources = PresentationWorkspaceSourceService(self._storage)
        self._presentation_workspace_voice = PresentationWorkspaceVoiceService(
            self._presentation_workspace_sources
        )
        self._presentation_semantics = PresentationSemanticService(
            self._storage, self._presentation_workspace_sources
        )
        from presenter_core.presentation.checkpoints import PresentationCheckpointService

        self._presentation_checkpoints = PresentationCheckpointService(self._storage)
        self._presentation_revisions = PresentationRevisionService(self._storage)
        self._presentation_edits = PresentationEditService(self._storage)
        from presenter_core.presentation.project_assets import ProjectPictureAssetService

        self._project_picture_assets = ProjectPictureAssetService(
            self._storage, self._presentation_edits
        )
        self._presentation_edit_plans = PresentationEditPlanService(
            self._storage, self._presentation_edits, self._presentation_workspace_sources
        )
        self._presentation_rehearsal = PresentationRehearsalService(
            self._storage, self._presentation_edits
        )
        self._audience = AudienceModelService(self._storage)
        self._transcript = TranscriptService(
            self._storage,
            mapping_revalidator=self._audience.revalidate_attribution,
        )
        self._ingestion = IngestionService(
            self._storage,
            self._emit_event,
            transcript_reconciler=self._transcript.reconcile_speaker_maps,
            source_delete_hook=self._before_source_delete,
            source_reindex_hook=self._after_source_reindex,
            before_source_snapshot_delete=self._before_source_snapshot_delete,
            presentation_revision_recorder=record_original_revision,
        )
        self._presentation_creation = PresentationCreationService(self._storage, self._ingestion)
        self._retrieval = LexicalRetrievalService(self._storage)
        embedding_runtime = embedding_adapter or FastEmbedAdapter(
            cache_dir=embedding_model_cache_dir(data_root)
        )
        self._hybrid_retrieval = HybridRetrievalService(
            self._storage,
            embedding_runtime,
            self._emit_service_event,
        )
        self._speaker_profile = SpeakerProfileService(self._storage)
        self._sessions = SessionService(
            self._storage,
            style_context=self._speaker_profile.build_style_context,
            app_cleanup=session_app_cleanup,
            active_run_cleanup=self._cleanup_active_session_for_delete,
            active_run_owner=self._active_asr_owner,
            before_delete=self._before_session_delete,
        )
        self._presentation = SlideStateService(
            self._storage,
            self._sessions.validate_active_presentation_session,
            event_sink=self._emit_service_event,
            powerpoint_adapter=presentation_adapter,
        )
        self._run = RunService(
            self._storage,
            self._sessions,
            self._presentation,
            self._hybrid_retrieval,
            asr_stop=self._stop_asr,
            asr_owner=self._active_asr_owner,
            event_sink=self._emit_service_event,
            clock=self._clock,
        )
        configured_asr_adapters = dict(asr_adapters or {})
        if not configured_asr_adapters:
            default_asr = FasterWhisperASRAdapter(
                cache_dir=self._storage.paths.asr_model_cache_directory(create=True),
            )
            configured_asr_adapters = {DEFAULT_ASR_ADAPTER_ID: default_asr}
        self._asr = ASRService(
            audio_input=audio_input,
            adapters=configured_asr_adapters,
            session_validator=self._sessions.validate_active_asr_session,
            persist_final=self._run.persist_final_utterance,
            slide_snapshot=self._presentation.current_slide,
            event_sink=self._emit_service_event,
            teach_finalizer=self._finalize_teach_voice,
            workspace_session_validator=self._presentation_workspace_voice.validate_asr_session,
            vad_config=vad_config,
            **(
                {"worker_join_timeout_seconds": asr_worker_join_timeout_seconds}
                if asr_worker_join_timeout_seconds is not None
                else {}
            ),
        )
        self._presentation_workspace_voice.attach_asr(self._asr)
        self._knowledge = KnowledgeService(
            self._storage,
            after_delete=self._synchronize_semantic_index,
            after_mapping_delete=self._hybrid_retrieval.invalidate_project_mappings,
            before_delete=self._before_knowledge_delete,
        )
        effective_credential_store = credential_store or WindowsCredentialStore()
        effective_decision_credential_store = decision_credential_store or (
            InMemoryCredentialStore()
            if credential_store is not None
            else OpenRouterCredentialStore()
        )
        self._providers = ProviderService(
            self._storage,
            reasoning_provider,
            event_sink=self._emit_service_event,
            credential_store=effective_credential_store,
            decision_credential_store=effective_decision_credential_store,
            chatgpt_plan_store=chatgpt_plan_store,
        )
        self._decisions = DecisionWorkflowService(
            self._storage,
            self._presentation_workspace_sources,
            self._providers,
            effective_decision_credential_store,
            injected_provider=decision_provider,
        )
        self._context_builder = ProviderContextBuilder(
            self._storage,
            self._hybrid_retrieval,
            self._speaker_profile,
        )
        self._provider_execution = ProviderExecutionService(
            self._storage,
            self._providers,
            event_sink=self._emit_service_event,
        )
        self._rehearsal_analysis_jobs = RehearsalAnalysisJobs(
            RehearsalSemanticAnalysis(
                self._presentation_semantics, self._providers, self._provider_execution
            ),
            objections=RehearsalObjectionAnalysis(
                self._presentation_semantics, self._providers, self._provider_execution
            ),
            comparisons=RehearsalObjectionComparison(
                self._presentation_semantics, self._providers, self._provider_execution
            ),
        )
        self._presentation_rewrites = PresentationRewriteService(
            self._storage,
            self._presentation_workspace_sources,
            self._providers,
            self._provider_execution,
            self._presentation_rehearsal,
        )
        self._presentation_planning = PresentationPlanningService(
            self._storage, self._providers, self._context_builder, self._provider_execution
        )
        self._presentation_edit_planning = PresentationEditPlanningService(
            self._storage,
            self._presentation_edits,
            self._presentation_edit_plans,
            self._providers,
            self._context_builder,
            self._provider_execution,
        )
        self._teach = TeachService(
            self._storage,
            self._sessions,
            self._hybrid_retrieval,
            self._providers,
            self._context_builder,
            self._emit_service_event,
            provider_execution=self._provider_execution,
            voice_capture_active=self._teach_capture_active,
        )
        self._challenge = ChallengeService(
            self._storage,
            self._sessions,
            self._hybrid_retrieval,
            self._providers,
            self._context_builder,
            self._audience,
            self._emit_service_event,
            self._synchronize_semantic_index,
            provider_execution=self._provider_execution,
        )
        self._projects = ProjectService(
            self._storage,
            before_delete=self._before_project_delete,
        )
        self._assist = AssistService(
            self._storage,
            self._sessions,
            self._asr,
            self._presentation,
            self._hybrid_retrieval,
            self._providers,
            self._context_builder,
            event_sink=self._emit_service_event,
            clock=self._clock,
            provider_execution=self._provider_execution,
        )
        self._hud_settings = HudSettingsService(self._storage)
        self._models = ModelService(
            self._storage,
            self._asr,
            embedding_runtime,
            event_sink=self._emit_service_event,
            before_remove=self._stop_active_for_model_change,
        )
        self._diagnostics = DiagnosticService(
            self._storage,
            self._logger,
            core_status=self._diagnostic_core_status,
            models=lambda: self._models.status({}),
            provider=lambda: self._providers.status({})["provider"],
        )
        deletion_recovery = self._storage.reconcile_deletions(
            credential_cleanup=self._providers.remove_stored_credential_for_reset,
        )
        if deletion_recovery["pending_operation_ids"]:
            self._logger.event(
                "deletion.recovery_pending",
                {
                    "operation": "startup_recovery",
                    "count": len(deletion_recovery["pending_operation_ids"]),
                    "error_code": "DELETION_RECOVERY_PENDING",
                },
            )
        recovery = self._storage.reconcile_runtime()
        if recovery["provider_runs"] or recovery["sessions"]:
            self._logger.event(
                "core.recovery_reconciled",
                {
                    "operation": "startup_recovery",
                    "count": recovery["provider_runs"] + recovery["sessions"],
                },
            )

    @property
    def shutdown_requested(self) -> bool:
        """Whether the server should exit after sending the current response."""
        return self._shutdown_requested

    @property
    def metadata(self) -> dict[str, Any]:
        """Return compatibility metadata for the handshake."""
        return {
            "protocol_version": PROTOCOL_VERSION,
            "core_version": CORE_VERSION,
            "capabilities": {
                "methods": list(SUPPORTED_METHODS),
                "events": list(SUPPORTED_EVENTS),
            },
            "adapters": [
                "pdf.pypdf",
                "pptx.python-pptx",
                "text.stdlib",
                "transcript.vtt",
                "transcript.srt",
                "transcript.named-text",
                "transcript.json",
                "audience.observable-patterns",
                "embedding.fastembed",
                "retrieval.numpy",
                "retrieval.hybrid",
                "retrieval.lexical",
                "reasoning.fake",
                "provider.openai.responses",
                "decision.openrouter.jev",
                "decision.ollama.systemone",
                "decision.openai.responses-fast",
                "decision.openai.chatgpt-plan",
                "decision.local.structured-output",
                "audio.sounddevice",
                "asr.faster-whisper",
                "asr.deterministic-fake",
                "presentation.manual",
                "presentation.powerpoint.read-only",
                "debrief.deterministic-local",
            ],
            "migration_status": "ready",
            "storage": {
                "app_schema_version": self._storage.app_schema_version,
                "project_schema_version": PROJECT_SCHEMA_VERSION,
            },
        }

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        """Attach transport output after construction without coupling core to stdio."""
        self._event_sink = event_sink

    def close(self) -> bool:
        """Close only after all active Runs have crossed their safe boundary."""
        if self._closed:
            return True
        try:
            self._rehearsal_analysis_jobs.drain(closing=True)
            self._run.stop_active_runs(status="aborted")
            self._assist.stop_active_sessions(status="aborted")
            self._cancel_active_teach_capture()
            self._presentation_workspace_voice.cancel_all()
            self._teach.purge_all()
        except CoreDomainError as error:
            # Leave every service and database open.  The sidecar may exit
            # after the bounded request, but recoverable active-session state
            # must not be replaced by a fabricated terminal row.
            self._last_close_error = error
            return False
        if self._asr.close() is False:
            self._last_close_error = CoreDomainError(
                "ASR_CAPTURE_FAILED",
                "The ASR service could not release all local resources.",
                retryable=True,
            )
            return False
        self._presentation_edit_plans.close()
        self._presentation_workspace_sources.close()
        self._presentation.close()
        self._decisions.close()
        self._providers.close()
        self._hybrid_retrieval.close()
        self._storage.close()
        self._closed = True
        return True

    def ready_event(self) -> dict[str, Any]:
        """Return the startup event sent before the first request is read."""
        return make_event("core.ready", self.metadata)

    def error_event(self, error: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        """Return a non-correlated diagnostic event for a rejected envelope."""
        return make_event(
            "core.error",
            {
                "code": error["code"],
                "message": error["message"],
                "request_id": request_id,
            },
        )

    def handle_line(self, line: str) -> dict[str, Any]:
        """Parse one NDJSON line and always return a structured response."""
        try:
            message: Any = json.loads(line)
        except json.JSONDecodeError:
            return make_error(
                None,
                "MALFORMED_JSON",
                "The sidecar received a line that is not valid JSON.",
            )
        return self.handle_message(message)

    def handle_message(self, message: Any) -> dict[str, Any]:
        """Validate and dispatch one decoded request object."""
        if not isinstance(message, dict):
            return make_error(None, "INVALID_REQUEST", "Request envelope must be a JSON object.")

        request_id_value = message.get("request_id")
        request_id = request_id_value if isinstance(request_id_value, str) else None

        received_version = message.get("protocol_version")
        if received_version != PROTOCOL_VERSION or isinstance(received_version, bool):
            return make_error(
                request_id,
                "PROTOCOL_VERSION_UNSUPPORTED",
                f"Protocol version {received_version!r} is not supported.",
                details={"supported_versions": [PROTOCOL_VERSION]},
            )

        if message.get("type") != "request":
            return make_error(
                request_id,
                "INVALID_REQUEST",
                "Envelope type must be 'request'.",
            )

        if not isinstance(request_id_value, str) or not request_id_value:
            return make_error(
                None,
                "INVALID_REQUEST",
                "Request id must be a non-empty string.",
            )
        request_id = request_id_value

        method = message.get("method")
        if not isinstance(method, str) or not method:
            return make_error(request_id, "INVALID_REQUEST", "Method must be a non-empty string.")

        params = message.get("params")
        if not isinstance(params, dict):
            return make_error(request_id, "INVALID_REQUEST", "Params must be a JSON object.")

        if method not in SUPPORTED_METHODS:
            return make_error(
                request_id,
                "METHOD_NOT_FOUND",
                f"Unknown method: {method}",
                details={"method": method, "supported_methods": list(SUPPORTED_METHODS)},
            )

        try:
            return self._dispatch(request_id, method, params)
        except CoreDomainError as error:
            return make_error(
                request_id,
                error.code,
                error.message,
                retryable=error.retryable,
                details=error.details,
            )
        except Exception as error:  # pragma: no cover - final request boundary guard
            cause = (
                "MEMORY_ALLOCATION_FAILED"
                if isinstance(error, MemoryError)
                else "UNEXPECTED_IO_ERROR"
                if isinstance(error, OSError)
                else "UNEXPECTED_EXCEPTION"
            )
            self._logger.event(
                "request.failed",
                {"operation": method, "error_code": "INTERNAL_ERROR", "cause_code": cause},
            )
            return make_error(
                request_id,
                "INTERNAL_ERROR",
                "The core could not complete the request.",
                retryable=False,
                details={},
            )

    def _dispatch(self, request_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "core.hello":
            reject_unknown_fields(params, set())
            return make_response(request_id, result=self.metadata)
        if method == "core.health":
            reject_unknown_fields(params, set())
            return make_response(
                request_id,
                result={
                    "status": "ok",
                    "ready": True,
                    "protocol_version": PROTOCOL_VERSION,
                    "core_version": CORE_VERSION,
                    "uptime_ms": max(0, int((self._clock() - self._started_at) * 1000)),
                },
            )

        # The supported-method check above makes this branch unreachable unless
        # a future method is added without a handler, which should fail loudly.
        if method == "core.shutdown":
            reject_unknown_fields(params, set())
            self._shutdown_requested = True
            cleanup_safe = self.close()
            result: dict[str, Any] = {"status": "shutting_down"}
            if not cleanup_safe:
                result["cleanup_pending"] = True
                if self._last_close_error is not None:
                    result["error_code"] = self._last_close_error.code
            return make_response(request_id, result=result)

        if method == "project.create":
            return make_response(request_id, result=self._projects.create(params))
        if method == "project.open":
            project_id = params.get("project_id")
            if isinstance(project_id, str):
                self._storage.reconcile_project_runtime(project_id)
                self._presentation_edit_plans.reconcile_project(project_id)
            return make_response(request_id, result=self._projects.open(params))
        if method == "project.list":
            return make_response(request_id, result=self._projects.list(params))
        if method == "project.update_settings":
            return make_response(request_id, result=self._projects.update_settings(params))
        if method == "project.acknowledge_remote_reasoning":
            return make_response(
                request_id,
                result=self._projects.acknowledge_remote_reasoning(params),
            )
        if method == "project.delete":
            result = self._projects.delete(params)
            self._teach.purge_project(str(result["project_id"]))
            return make_response(request_id, result=result)
        if method == "source.import":
            result = self._ingestion.import_source(params)
            self._hybrid_retrieval.invalidate_project_mappings(result["document"]["project_id"])
            return make_response(request_id, result=result)
        if method == "presentation.workspace.create_from_outline":
            result = self._presentation_creation.create_from_outline(params)
            self._hybrid_retrieval.invalidate_project_mappings(result["document"]["project_id"])
            return make_response(request_id, result=result)
        if method == "source.list":
            return make_response(request_id, result=self._ingestion.list_sources(params))
        if method == "source.preview":
            return make_response(request_id, result=self._ingestion.preview_source(params))
        if method == "presentation.workspace.select_for_rehearsal":
            return make_response(
                request_id, result=self._presentation_rehearsal.select_for_rehearsal(params)
            )
        if method == "presentation.workspace.list_rehearsal_findings":
            return make_response(
                request_id, result=self._presentation_rehearsal.list_findings(params)
            )
        if method == "presentation.workspace.recurring_objections":
            return make_response(
                request_id, result=self._presentation_rehearsal.recurring_objections(params)
            )
        if method == "presentation.workspace.rehearsal_coverage":
            return make_response(request_id, result=self._presentation_rehearsal.coverage(params))
        if method == "presentation.workspace.compare_rehearsals":
            return make_response(
                request_id, result=self._presentation_rehearsal.compare_runs(params)
            )
        if method == "presentation.workspace.reject_rehearsal_finding":
            return make_response(
                request_id, result=self._presentation_rehearsal.reject_finding(params)
            )
        if method == "presentation.workspace.apply_rehearsal_edit":
            return make_response(request_id, result=self._presentation_rehearsal.apply_edit(params))
        if method == "presentation.workspace.open_source":
            return make_response(
                request_id, result=self._presentation_workspace_sources.open_source(params)
            )
        if method == "presentation.workspace.read_source":
            return make_response(
                request_id, result=self._presentation_workspace_sources.read_source(params)
            )
        if method == "presentation.workspace.close_source":
            return make_response(
                request_id, result=self._presentation_workspace_sources.close_source(params)
            )
        if method == "presentation.workspace.list_checkpoints":
            return make_response(request_id, result=self._presentation_checkpoints.list(params))
        if method == "presentation.workspace.save_checkpoint":
            return make_response(request_id, result=self._presentation_checkpoints.save(params))
        if method == "presentation.workspace.clear_checkpoint":
            return make_response(request_id, result=self._presentation_checkpoints.clear(params))
        if method == "presentation.workspace.list_revisions":
            return make_response(
                request_id, result=self._presentation_revisions.list_revisions(params)
            )
        if method == "presentation.workspace.list_text_targets":
            return make_response(
                request_id, result=self._presentation_workspace_sources.list_text_targets(params)
            )
        if method == "presentation.workspace.voice_start":
            return make_response(
                request_id, result=self._presentation_workspace_voice.start(params)
            )
        if method == "presentation.workspace.voice_stop":
            return make_response(request_id, result=self._presentation_workspace_voice.stop(params))
        if method == "presentation.workspace.voice_cancel":
            return make_response(
                request_id, result=self._presentation_workspace_voice.cancel(params)
            )
        if method == "presentation.workspace.triage_claim_evidence":
            return make_response(request_id, result=self._decisions.triage_claim_evidence(params))
        if method == "presentation.workspace.classify_slide":
            return make_response(request_id, result=self._decisions.classify_slide(params))
        if method == "presentation.workspace.list_outline_evidence_candidates":
            from presenter_core.presentation.outline_evidence import OutlineEvidenceService

            return make_response(
                request_id,
                result=OutlineEvidenceService(self._presentation_semantics).list_candidates(params),
            )
        if method in {
            "presentation.workspace.list_rehearsal_review_sessions",
            "presentation.workspace.list_rehearsal_review_messages",
            "presentation.workspace.list_rehearsal_review_slides",
            "presentation.workspace.list_rehearsal_analyses",
            "presentation.workspace.list_rehearsal_objections_analyses",
            "presentation.workspace.get_rehearsal_analysis",
        }:
            from presenter_core.presentation.rehearsal_review_inventory import (
                RehearsalReviewInventory,
            )

            inventory = RehearsalReviewInventory(self._presentation_semantics)
            handler = {
                "presentation.workspace.list_rehearsal_review_sessions": inventory.sessions,
                "presentation.workspace.list_rehearsal_review_messages": inventory.messages,
                "presentation.workspace.list_rehearsal_review_slides": inventory.slides,
                "presentation.workspace.list_rehearsal_analyses": inventory.analyses,
                "presentation.workspace.list_rehearsal_objections_analyses": (
                    inventory.objection_analyses
                ),
                "presentation.workspace.get_rehearsal_analysis": inventory.detail,
            }[method]
            return make_response(request_id, result=handler(params))
        if method in {
            "presentation.workspace.start_rehearsal_analysis",
            "presentation.workspace.poll_rehearsal_analysis",
            "presentation.workspace.cancel_rehearsal_analysis",
        }:
            jobs = self._rehearsal_analysis_jobs
            handler = {
                "presentation.workspace.start_rehearsal_analysis": jobs.start,
                "presentation.workspace.poll_rehearsal_analysis": jobs.poll,
                "presentation.workspace.cancel_rehearsal_analysis": jobs.cancel,
            }[method]
            return make_response(request_id, result=handler(params))
        if method == "presentation.workspace.prepare_rehearsal_objections_review":
            from presenter_core.presentation.rehearsal_objection_context import (
                RehearsalObjectionContext,
            )

            return make_response(
                request_id,
                result=RehearsalObjectionContext(self._presentation_semantics).prepare(params),
            )
        if method == "presentation.workspace.get_rehearsal_objections_analysis":
            from presenter_core.presentation.rehearsal_objection_adoption import (
                RehearsalObjectionAdoption,
            )

            return make_response(
                request_id,
                result=RehearsalObjectionAdoption(self._presentation_semantics).detail(params),
            )
        if method == "presentation.workspace.start_rehearsal_objections_analysis":
            return make_response(
                request_id, result=self._rehearsal_analysis_jobs.start_objections(params)
            )
        if method == "presentation.workspace.start_rehearsal_objection_comparison":
            return make_response(
                request_id, result=self._rehearsal_analysis_jobs.start_comparison(params)
            )
        if method in {
            "presentation.workspace.prepare_rehearsal_objection_comparison",
            "presentation.workspace.list_rehearsal_objection_comparisons",
            "presentation.workspace.get_rehearsal_objection_comparison",
        }:
            comparison = RehearsalObjectionComparison(self._presentation_semantics)
            handler = {
                "presentation.workspace.prepare_rehearsal_objection_comparison": (
                    comparison.prepare
                ),
                "presentation.workspace.list_rehearsal_objection_comparisons": comparison.list,
                "presentation.workspace.get_rehearsal_objection_comparison": comparison.read,
            }[method]
            return make_response(request_id, result=handler(params))
        if method == "presentation.workspace.analyze_rehearsal_coverage":
            from presenter_core.presentation.rehearsal_semantic_analysis import (
                RehearsalSemanticAnalysis,
            )

            return make_response(
                request_id,
                result=RehearsalSemanticAnalysis(
                    self._presentation_semantics,
                    self._providers,
                    self._provider_execution,
                ).analyze(params),
            )
        if method == "presentation.workspace.prepare_rehearsal_coverage_review":
            from presenter_core.presentation.rehearsal_semantic_context import (
                RehearsalSemanticContext,
            )

            return make_response(
                request_id,
                result=RehearsalSemanticContext(self._presentation_semantics).prepare(params),
            )
        if method in {
            "presentation.workspace." + name
            for name in ("list_claims", "save_claim", "remove_claim", "search_claim_evidence")
        }:
            service = PresentationClaimService(self._presentation_semantics)
            name = method.rsplit(".", 1)[1]
            handler = (
                service.search_evidence
                if name == "search_claim_evidence"
                else getattr(service, name)
            )
            return make_response(request_id, result=handler(params))
        if method == "presentation.workspace.extract_claims":
            from presenter_core.presentation.claim_extraction import (
                PresentationClaimExtractionService,
            )

            return make_response(
                request_id,
                result=PresentationClaimExtractionService(
                    self._presentation_semantics, self._providers, self._provider_execution
                ).extract_claims(params),
            )
        if method == "presentation.workspace.propose_narrative":
            from presenter_core.presentation.narrative_planning import (
                PresentationNarrativePlanningService,
            )

            return make_response(
                request_id,
                result=PresentationNarrativePlanningService(
                    self._presentation_semantics,
                    self._providers,
                    self._context_builder,
                    self._provider_execution,
                ).propose_narrative(params),
            )
        if method == "presentation.workspace.prepare_claim_scan":
            from presenter_core.presentation.claim_scan import PresentationClaimScanService

            return make_response(
                request_id,
                result=PresentationClaimScanService(
                    self._presentation_semantics
                ).prepare_claim_scan(params),
            )
        if method == "presentation.workspace.review_deck_semantics":
            from presenter_core.presentation.deck_review import PresentationDeckReviewService

            return make_response(
                request_id,
                result=PresentationDeckReviewService(
                    self._presentation_semantics
                ).review_deck_semantics(params),
            )
        if method in {
            "presentation.workspace.get_narrative",
            "presentation.workspace.save_narrative",
        }:
            from presenter_core.presentation.narrative import PresentationNarrativeService

            narrative_service = PresentationNarrativeService(self._presentation_semantics)
            return make_response(
                request_id, result=getattr(narrative_service, method.rsplit(".", 1)[1])(params)
            )
        if method in {
            "presentation.workspace.get_slide_takeaway",
            "presentation.workspace.save_slide_takeaway",
        }:
            from presenter_core.presentation.takeaways import PresentationTakeawayService

            return make_response(
                request_id,
                result=getattr(
                    PresentationTakeawayService(self._presentation_semantics),
                    method.rsplit(".", 1)[1],
                )(params),
            )
        if method == "presentation.workspace.list_slide_purposes":
            return make_response(
                request_id, result=self._presentation_semantics.list_slide_purposes(params)
            )
        if method == "presentation.workspace.save_slide_purpose":
            return make_response(
                request_id, result=self._presentation_semantics.save_slide_purpose(params)
            )
        if method == "presentation.workspace.get_outline_session":
            return make_response(request_id, result=self._presentation_planning.drafts.get(params))
        if method == "presentation.workspace.save_outline_session":
            return make_response(request_id, result=self._presentation_planning.drafts.save(params))
        if method == "presentation.workspace.clear_outline_session":
            return make_response(
                request_id, result=self._presentation_planning.drafts.clear(params)
            )
        if method == "presentation.workspace.propose_outline":
            return make_response(
                request_id,
                result=self._presentation_planning.propose_outline(params),
            )
        if method == "presentation.workspace.propose_text_rewrite":
            return make_response(
                request_id,
                result=self._presentation_rewrites.propose_text_rewrite(params),
            )
        if method == "presentation.workspace.prepare_edit_plan":
            return make_response(request_id, result=self._presentation_edit_plans.prepare(params))
        if method == "presentation.workspace.propose_edit_plan":
            return make_response(
                request_id, result=self._presentation_edit_planning.propose(params)
            )
        if method == "presentation.workspace.open_edit_plan_preview":
            return make_response(
                request_id, result=self._presentation_edit_plans.open_preview(params)
            )
        if method == "presentation.workspace.apply_edit_plan":
            result = self._presentation_edit_plans.apply(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.reject_edit_plan":
            return make_response(request_id, result=self._presentation_edit_plans.reject(params))
        if method == "presentation.workspace.replace_text_shape":
            result = self._presentation_edits.replace_text_shape(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.replace_single_run_text":
            result = self._presentation_edits.replace_single_run_text(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.format_single_run_text":
            result = self._presentation_edits.format_single_run_text(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.format_text_shape":
            result = self._presentation_edits.format_text_shape(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.format_shape_style":
            result = self._presentation_edits.format_shape_style(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.replace_speaker_notes":
            result = self._presentation_edits.replace_speaker_notes(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.transform_object":
            result = self._presentation_edits.transform_object(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.find_text":
            return make_response(request_id, result=self._presentation_edits.find_text(params))
        if method == "presentation.workspace.replace_text_all":
            result = self._presentation_edits.replace_text_all(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.set_text_hyperlink":
            result = self._presentation_edits.set_text_hyperlink(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.get_theme_fonts":
            return make_response(
                request_id, result=self._presentation_edits.get_theme_fonts(params)
            )
        if method == "presentation.workspace.set_theme_fonts":
            result = self._presentation_edits.set_theme_fonts(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.get_slide_footers":
            return make_response(
                request_id, result=self._presentation_edits.get_slide_footers(params)
            )
        if method == "presentation.workspace.set_slide_footers":
            result = self._presentation_edits.set_slide_footers(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.set_slide_transition":
            result = self._presentation_edits.set_slide_transition(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.set_slide_hidden":
            result = self._presentation_edits.set_slide_hidden(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.set_slide_background":
            result = self._presentation_edits.set_slide_background(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.rotate_object":
            result = self._presentation_edits.rotate_object(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.adjust_picture":
            result = self._presentation_edits.adjust_picture(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.crop_picture":
            result = self._presentation_edits.crop_picture(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.replace_picture_image":
            result = self._presentation_edits.replace_picture_image(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.reorder_slides":
            result = self._presentation_edits.reorder_slides(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.list_native_layouts":
            from presenter_core.presentation.layouts import PresentationLayoutService

            return make_response(
                request_id,
                result=PresentationLayoutService(
                    self._presentation_workspace_sources
                ).list_native_layouts(params),
            )
        if method == "presentation.workspace.apply_slide_layout":
            result = self._presentation_edits.apply_slide_layout(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.create_slide":
            result = self._presentation_edits.create_slide(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.duplicate_slide":
            result = self._presentation_edits.duplicate_slide(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.create_text_box":
            result = self._presentation_edits.create_text_box(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.create_picture":
            result = self._presentation_edits.create_picture(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.create_chart":
            result = self._presentation_edits.create_chart(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.list_charts":
            from presenter_core.presentation.chart_editing import PresentationChartService

            return make_response(
                request_id,
                result=PresentationChartService(self._presentation_workspace_sources).list_charts(
                    params
                ),
            )
        if method == "presentation.workspace.list_shape_fills":
            from presenter_core.presentation.shape_fills import list_shape_fills

            return make_response(
                request_id, result=list_shape_fills(self._presentation_edits, params)
            )
        if method == "presentation.workspace.replace_chart_data":
            result = self._presentation_edits.replace_chart_data(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.list_diagrams":
            from presenter_core.presentation.diagrams import PresentationDiagramService

            return make_response(
                request_id,
                result=PresentationDiagramService(
                    self._presentation_workspace_sources
                ).list_diagrams(params),
            )
        if method in {
            "presentation.workspace.create_diagram",
            "presentation.workspace.replace_diagram",
            "presentation.workspace.delete_diagram",
        }:
            result = getattr(self._presentation_edits, method.rsplit(".", 1)[-1])(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.list_text_fit_targets":
            from presenter_core.presentation.text_fit_editing import PresentationTextFitService

            return make_response(
                request_id,
                result=PresentationTextFitService(
                    self._presentation_workspace_sources
                ).list_targets(params),
            )
        if method == "presentation.workspace.list_tables":
            from presenter_core.presentation.tables import PresentationTableService

            return make_response(
                request_id,
                result=PresentationTableService(self._presentation_workspace_sources).list_tables(
                    params
                ),
            )
        if method in {
            "presentation.workspace.create_table",
            "presentation.workspace.replace_table_cells",
        }:
            operation = method.rsplit(".", 1)[-1]
            result = getattr(self._presentation_edits, operation)(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.create_shape":
            result = self._presentation_edits.create_shape(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.delete_slide":
            result = self._presentation_edits.delete_slide(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.import_project_picture":
            return make_response(
                request_id, result=self._project_picture_assets.import_picture(params)
            )
        if method == "presentation.workspace.list_project_pictures":
            return make_response(
                request_id, result=self._project_picture_assets.list_pictures(params)
            )
        if method == "presentation.workspace.read_project_picture":
            return make_response(
                request_id, result=self._project_picture_assets.read_picture(params)
            )
        if method == "presentation.workspace.delete_project_picture":
            return make_response(
                request_id, result=self._project_picture_assets.delete_picture(params)
            )
        if method == "presentation.workspace.list_picture_assets":
            return make_response(
                request_id, result=self._presentation_edits.list_picture_assets(params)
            )
        if method == "presentation.workspace.read_picture_asset":
            return make_response(
                request_id, result=self._presentation_edits.read_picture_asset(params)
            )
        if method == "presentation.workspace.change_object_layer":
            result = self._presentation_edits.change_object_layer(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.delete_object":
            result = self._presentation_edits.delete_object(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.duplicate_object":
            result = self._presentation_edits.duplicate_object(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.restore_revision":
            result = self._presentation_edits.restore_revision(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.step_revision":
            result = self._presentation_edits.step_revision(params)
            self._hybrid_retrieval.invalidate_project_mappings(str(params["project_id"]))
            return make_response(request_id, result=result)
        if method == "presentation.workspace.export_original_copy":
            return make_response(
                request_id,
                result=self._presentation_workspace_sources.export_original_copy(params),
            )
        if method == "presentation.workspace.export_current_copy":
            return make_response(
                request_id,
                result=self._presentation_workspace_sources.export_current_copy(params),
            )
        if method == "source.delete":
            result = self._ingestion.delete_source(params)
            self._hybrid_retrieval.invalidate_project_mappings(result["project_id"])
            return make_response(request_id, result=result)
        if method == "source.reindex":
            result = self._ingestion.reindex_source(params)
            self._hybrid_retrieval.invalidate_project_mappings(result["document"]["project_id"])
            return make_response(request_id, result=result)
        if method == "transcript.list_speakers":
            return make_response(request_id, result=self._transcript.list_speakers(params))
        if method == "transcript.map_speaker":
            return make_response(request_id, result=self._transcript.map_speaker(params))
        if method == "transcript.unmap_speaker":
            return make_response(request_id, result=self._transcript.unmap_speaker(params))
        if method == "audience.create":
            return make_response(request_id, result=self._audience.create(params))
        if method == "audience.update":
            return make_response(request_id, result=self._audience.update(params))
        if method == "audience.list":
            return make_response(request_id, result=self._audience.list_profiles(params))
        if method == "audience.delete":
            return make_response(request_id, result=self._audience.delete(params))
        if method == "audience.extract_observations":
            return make_response(request_id, result=self._audience.extract_observations(params))
        if method == "audience.list_observations":
            return make_response(request_id, result=self._audience.list_observations(params))
        if method == "audience.accept_observation":
            return make_response(request_id, result=self._audience.accept_observation(params))
        if method == "audience.reject_observation":
            return make_response(request_id, result=self._audience.reject_observation(params))
        if method == "audience.create_observation":
            return make_response(request_id, result=self._audience.create_observation(params))
        if method == "audience.update_observation":
            return make_response(request_id, result=self._audience.update_observation(params))
        if method == "audience.delete_observation":
            return make_response(request_id, result=self._audience.delete_observation(params))
        if method == "audience.build_context":
            return make_response(request_id, result=self._audience.build_context(params))
        if method == "search.lexical":
            return make_response(request_id, result=self._retrieval.query(params))
        if method == "retrieval.health":
            return make_response(request_id, result=self._hybrid_retrieval.health(params))
        if method == "retrieval.query":
            return make_response(request_id, result=self._hybrid_retrieval.query(params))
        if method == "retrieval.rebuild":
            return make_response(request_id, result=self._hybrid_retrieval.rebuild(params))
        if method == "session.start":
            result = self._sessions.start(params)
            session = result["session"]
            if session["mode"] == "run":
                try:
                    self._run.start(session["project_id"], session["id"])
                except Exception:
                    # The session row is not allowed to remain active when
                    # Run presentation initialization fails.
                    try:
                        self._sessions.stop(
                            {
                                "project_id": session["project_id"],
                                "session_id": session["id"],
                                "status": "error",
                            }
                        )
                    except Exception:
                        pass
                    raise
            elif session["mode"] == "live_assist":
                try:
                    self._presentation.start_live(session["project_id"], session["id"])
                except Exception:
                    try:
                        self._sessions.stop(
                            {
                                "project_id": session["project_id"],
                                "session_id": session["id"],
                                "status": "error",
                            }
                        )
                    except Exception:
                        pass
                    raise
            self._emit_event("session.started", session)
            return make_response(request_id, result=result)
        if method == "session.stop":
            session = self._sessions.get(
                {"project_id": params.get("project_id"), "session_id": params.get("session_id")}
            )["session"]
            if session["mode"] == "run":
                result = self._run.stop(params)
            elif session["mode"] == "live_assist":
                result = self._assist.stop_session(
                    str(session["project_id"]),
                    str(session["id"]),
                    status=params.get("status", "completed"),
                )
            else:
                project_id = str(session["project_id"])
                session_id = str(session["id"])
                self._cancel_active_teach_capture(project_id, session_id)
                self._teach.purge_session(project_id, session_id)
                result = self._sessions.stop(params)
            self._emit_event("session.stopped", result["session"])
            return make_response(request_id, result=result)
        if method == "session.get":
            return make_response(request_id, result=self._sessions.get(params))
        if method == "session.list":
            return make_response(request_id, result=self._sessions.list(params))
        if method == "session.delete":
            project_id = str(params.get("project_id"))
            session_id = str(params.get("session_id"))
            self._cancel_active_teach_capture(project_id, session_id)
            self._teach.purge_session(project_id, session_id)
            result = self._sessions.delete(params)
            self._teach.purge_session(str(result["project_id"]), str(result["session_id"]))
            self._assist.purge_session(str(result["project_id"]), str(result["session_id"]))
            self._presentation.purge_session(str(result["project_id"]), str(result["session_id"]))
            return make_response(request_id, result=result)
        if method == "assist.request":
            return make_response(request_id, result=self._assist.request(params))
        if method == "assist.cancel":
            return make_response(request_id, result=self._assist.cancel(params))
        if method == "cue.list":
            return make_response(request_id, result=self._assist.cues.list(params))
        if method == "cue.dismiss":
            return make_response(request_id, result=self._assist.cues.dismiss(params))
        if method == "cue.expand_sources":
            return make_response(request_id, result=self._assist.cues.expand_sources(params))
        if method == "hud.settings.get":
            return make_response(request_id, result=self._hud_settings.get(params))
        if method == "hud.settings.update":
            return make_response(request_id, result=self._hud_settings.update(params))
        if method == "asr.list_devices":
            return make_response(request_id, result=self._asr.list_devices(params))
        if method == "asr.configure":
            return make_response(request_id, result=self._asr.configure(params))
        if method == "asr.prepare_model":
            return make_response(request_id, result=self._asr.prepare_model(params))
        if method == "asr.start":
            return make_response(request_id, result=self._asr.start(params))
        if method == "asr.stop":
            return make_response(request_id, result=self._asr.stop(params))
        if method == "asr.status":
            return make_response(request_id, result=self._asr.status(params))
        if method == "models.status":
            return make_response(request_id, result=self._models.status(params))
        if method == "models.prepare":
            return make_response(request_id, result=self._models.prepare(params))
        if method == "models.remove":
            return make_response(request_id, result=self._models.remove(params))
        if method == "presentation.detect":
            return make_response(request_id, result=self._presentation.detect(params))
        if method == "presentation.set_slide":
            return make_response(request_id, result=self._presentation.set_slide(params))
        if method == "presentation.next_slide":
            return make_response(request_id, result=self._presentation.next_slide(params))
        if method == "presentation.previous_slide":
            return make_response(request_id, result=self._presentation.previous_slide(params))
        if method == "presentation.status":
            return make_response(request_id, result=self._presentation.status(params))
        if method == "run.mark_event":
            return make_response(request_id, result=self._run.mark_event(params))
        if method == "run.generate_debrief":
            return make_response(request_id, result=self._run.generate_debrief(params))
        if method == "run.get_state":
            return make_response(request_id, result=self._run.get_state(params))
        if method == "run.list_transcript":
            return make_response(request_id, result=self._run.list_transcript(params))
        if method == "run.list_timeline":
            return make_response(request_id, result=self._run.list_timeline(params))
        if method == "run.get_debrief":
            return make_response(request_id, result=self._run.get_debrief(params))
        if method == "teach.next_prompt":
            return make_response(request_id, result=self._teach.next_prompt(params))
        if method == "teach.get_state":
            return make_response(request_id, result=self._teach.get_state(params))
        if method == "teach.submit_text":
            return make_response(request_id, result=self._teach.submit_text(params))
        if method == "teach.voice_start":
            return make_response(
                request_id,
                result=self._teach.voice_start(params, self._start_teach_capture),
            )
        if method == "teach.voice_stop":
            return make_response(
                request_id,
                result=self._teach.voice_stop(
                    params,
                    self._stop_teach_capture,
                    self._cancel_teach_capture,
                ),
            )
        if method == "teach.voice_cancel":
            return make_response(
                request_id,
                result=self._teach.voice_cancel(params, self._cancel_teach_capture),
            )
        if method == "teach.discard_answer":
            return make_response(request_id, result=self._teach.discard_answer(params))
        if method == "teach.confirm_knowledge_item":
            return make_response(request_id, result=self._teach.confirm_knowledge_item(params))
        if method == "teach.reject_knowledge_item":
            return make_response(request_id, result=self._teach.reject_knowledge_item(params))
        if method == "challenge.configure":
            return make_response(request_id, result=self._challenge.configure(params))
        if method == "challenge.next_question":
            return make_response(request_id, result=self._challenge.next_question(params))
        if method == "challenge.submit_answer":
            return make_response(request_id, result=self._challenge.submit_answer(params))
        if method == "challenge.retry_question":
            return make_response(request_id, result=self._challenge.retry_question(params))
        if method == "challenge.save_preferred_answer":
            return make_response(request_id, result=self._challenge.save_preferred_answer(params))
        if method == "challenge.get_state":
            return make_response(request_id, result=self._challenge.get_state(params))
        if method == "challenge.list_history":
            return make_response(request_id, result=self._challenge.list_history(params))
        if method == "knowledge.list":
            return make_response(request_id, result=self._knowledge.list(params))
        if method == "knowledge.update_flags":
            return make_response(request_id, result=self._knowledge.update_flags(params))
        if method == "knowledge.delete":
            return make_response(request_id, result=self._knowledge.delete(params))
        if method == "speaker_profile.get":
            return make_response(request_id, result=self._speaker_profile.get(params))
        if method == "speaker_profile.list_evidence":
            return make_response(request_id, result=self._speaker_profile.list_evidence(params))
        if method == "speaker_profile.approve_evidence":
            return make_response(request_id, result=self._speaker_profile.approve_evidence(params))
        if method == "speaker_profile.remove_evidence":
            return make_response(request_id, result=self._speaker_profile.remove_evidence(params))
        if method == "speaker_profile.update_settings":
            return make_response(request_id, result=self._speaker_profile.update_settings(params))
        if method == "speaker_profile.reset":
            return make_response(request_id, result=self._speaker_profile.reset(params))
        if method in {"provider.codex.sign_in", "provider.codex.status", "provider.codex.sign_out"}:
            return make_response(
                request_id, result=self._providers.codex_auth(method.rsplit(".", 1)[1], params)
            )
        if method in {
            "provider.chatgpt_plan.sign_in",
            "provider.chatgpt_plan.status",
            "provider.chatgpt_plan.select",
            "provider.chatgpt_plan.cancel",
            "provider.chatgpt_plan.sign_out",
        }:
            return make_response(
                request_id,
                result=self._providers.chatgpt_plan_auth(method.rsplit(".", 1)[1], params),
            )
        if method == "provider.chatgpt_plan.models":
            reject_unknown_fields(params, {"refresh"})
            refresh = params.get("refresh", False)
            if not isinstance(refresh, bool):
                raise CoreDomainError(
                    "INVALID_REQUEST",
                    "refresh must be a boolean.",
                    details={"field": "refresh"},
                )
            return make_response(
                request_id,
                result={"models": self._providers.chatgpt_plan_models(force_refresh=refresh)},
            )
        if method == "provider.list":
            return make_response(request_id, result=self._providers.list(params))
        if method == "provider.configure":
            result = self._providers.configure(params)
            return make_response(request_id, result=result)
        if method == "provider.decision.status":
            return make_response(request_id, result=self._decisions.status(params))
        if method == "provider.decision.configure":
            return make_response(request_id, result=self._decisions.configure(params))
        if method == "provider.decision.credentials.status":
            return make_response(request_id, result=self._decisions.credentials_status(params))
        if method == "provider.decision.credentials.save_detected":
            return make_response(
                request_id, result=self._decisions.save_detected_credential(params)
            )
        if method == "provider.decision.credentials.remove":
            return make_response(
                request_id, result=self._decisions.remove_stored_credential(params)
            )
        if method == "provider.test":
            return make_response(request_id, result=self._providers.test(params))
        if method == "provider.status":
            return make_response(request_id, result=self._providers.status(params))
        if method == "provider.credentials.status":
            return make_response(request_id, result=self._providers.credentials_status(params))
        if method == "provider.credentials.save_detected":
            return make_response(
                request_id, result=self._providers.save_detected_credential(params)
            )
        if method == "provider.credentials.remove":
            return make_response(request_id, result=self._providers.remove_credential(params))
        if method == "diagnostics.preview":
            return make_response(request_id, result=self._diagnostics.preview(params))
        if method == "diagnostics.export":
            return make_response(request_id, result=self._diagnostics.export(params))
        if method == "app.reset_local_data":
            return make_response(request_id, result=self.reset_local_data(params))
        if method == "privacy.list_context_manifests":
            return make_response(
                request_id, result=self._provider_execution.list_context_manifests(params)
            )

        raise AssertionError(f"supported method has no handler: {method}")

    def _emit_event(self, event: str, payload: dict[str, Any]) -> None:
        safe_fields = {
            key: payload[key]
            for key in (
                "project_id",
                "session_id",
                "document_id",
                "assist_id",
                "provider_run_id",
                "status",
                "error_code",
                "provider_id",
                "model_id",
                "adapter_id",
                "phase",
                "completed",
                "total",
                "latency_ms",
                "generation_id",
            )
            if key in payload
        }
        self._logger.event(event, safe_fields)
        if self._event_sink is not None:
            self._event_sink(make_event(event, payload))

    def _emit_service_event(self, event: str, payload: dict[str, Any]) -> None:
        self._emit_event(event, payload)

    def _stop_asr(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._asr.stop(params)

    def _teach_capture_active(
        self, project_id: str, session_id: str, capture_id: str | None = None
    ) -> bool:
        return self._asr.owns_capture(
            project_id,
            session_id,
            mode="teach",
            capture_id=capture_id,
        )

    def _start_teach_capture(self, params: dict[str, Any], local_only: bool) -> dict[str, Any]:
        return self._asr.start(
            params,
            owner_mode="teach",
            voice_local_only=local_only,
        )

    def _stop_teach_capture(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._asr.stop(params, expected_mode="teach")

    def _cancel_teach_capture(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._asr.cancel(params, expected_mode="teach")

    def _cancel_active_teach_capture(
        self, project_id: str | None = None, session_id: str | None = None
    ) -> None:
        owner = self._asr.active_owner_details()
        if owner is None or owner[2] != "teach":
            return
        if project_id is not None and owner[0] != project_id:
            return
        if session_id is not None and owner[1] != session_id:
            return
        self._cancel_teach_capture({"project_id": owner[0], "session_id": owner[1]})

    def _finalize_teach_voice(
        self,
        project_id: str,
        session_id: str,
        capture_id: str,
        text: str,
        local_only: bool,
    ) -> dict[str, Any]:
        return self._teach.submit_voice_transcript(
            project_id,
            session_id,
            capture_id,
            text,
            local_only=local_only,
        )

    def _active_asr_owner(self) -> tuple[str, str] | None:
        # Session/Run services are constructed before ASR, but invoke this
        # callback only after composition is complete.
        return self._asr.active_owner()

    def _before_session_delete(self, project_id: str, session_id: str) -> None:
        self._rehearsal_analysis_jobs.drain(
            project_id=project_id, session_id=session_id, purge=True
        )

    def _cleanup_active_session_for_delete(self, project_id: str, session_id: str) -> None:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                "SELECT mode FROM sessions WHERE id = ? AND project_id = ?",
                (session_id, project_id),
            ).fetchone()
        if row is None:
            return
        if row["mode"] == "run":
            result = self._run.stop(
                {"project_id": project_id, "session_id": session_id, "status": "aborted"}
            )
        elif row["mode"] == "teach":
            self._cancel_active_teach_capture(project_id, session_id)
            self._teach.purge_session(project_id, session_id)
            result = None
        else:
            result = self._assist.stop_session(project_id, session_id, status="aborted")
        cleanup_code = result.get("cleanup_error_code") if isinstance(result, dict) else None
        if isinstance(cleanup_code, str):
            raise CoreDomainError(
                "SESSION_DELETE_RUN_CLEANUP_FAILED",
                "The active Run could not release its local resources; retry is safe.",
                retryable=True,
                details={"cleanup_error_code": cleanup_code},
            )
        self._assist.purge_session(project_id, session_id)
        self._presentation.purge_session(project_id, session_id)

    def _before_project_delete(self, project_id: str) -> None:
        """Cross-service deletion barrier executed before vault removal."""
        self._rehearsal_analysis_jobs.drain(project_id=project_id, purge=True)
        self._presentation_workspace_voice.cancel_for_project(project_id)
        self._presentation_edit_plans.close_project(project_id)
        self._presentation_workspace_sources.close_project(project_id)
        self._run.stop_project_runs({"project_id": project_id})
        self._assist.stop_project_sessions({"project_id": project_id})
        self._cancel_active_teach_capture(project_id)
        self._teach.purge_project(project_id)
        self._assist.purge_project(project_id)
        self._presentation.purge_project(project_id)
        self._hybrid_retrieval.evict_project(project_id)

    def _stop_active_for_model_change(self) -> None:
        """Model cache deletion never occurs underneath a process owner."""
        self._rehearsal_analysis_jobs.drain()
        self._run.stop_active_runs(status="aborted")
        self._assist.stop_active_sessions(status="aborted")
        self._cancel_active_teach_capture()
        self._presentation_workspace_voice.cancel_all()
        self._teach.purge_all()
        self._assist.purge_all()
        self._presentation.purge_all()
        self._hybrid_retrieval.release_model()

    def reset_local_data(self, params: dict[str, Any]) -> dict[str, Any]:
        """Perform the explicit destructive app reset after a confirmation gate."""
        reject_unknown_fields(params, {"confirm", "remove_model_cache"})
        if params.get("confirm") is not True:
            raise CoreDomainError(
                "LOCAL_DATA_RESET_CONFIRMATION_REQUIRED",
                "Reset Local Data requires explicit confirmation.",
            )
        remove_model_cache = params.get("remove_model_cache", False)
        if not isinstance(remove_model_cache, bool):
            raise CoreDomainError(
                "INVALID_REQUEST",
                "remove_model_cache must be a boolean.",
                details={"field": "remove_model_cache"},
            )
        # Probe the secure store before stopping owners or staging any local
        # state.  An unavailable store must leave the entire reset untouched.
        credential_plan = self._providers.prepare_reset_credential_cleanup()
        self._rehearsal_analysis_jobs.drain(purge=True)
        self._presentation_edit_plans.close()
        self._presentation_workspace_sources.close()
        self._run.stop_active_runs(status="aborted")
        self._assist.stop_active_sessions(status="aborted")
        self._cancel_active_teach_capture()
        self._presentation_workspace_voice.cancel_all()
        self._teach.purge_all()
        self._assist.purge_all()
        self._presentation.purge_all()
        # Reset always releases process-memory retrieval state.  This does not
        # remove the shared on-disk model unless the explicit option below is
        # selected, so retained caches remain available for a later bootstrap.
        self._hybrid_retrieval.release_model()
        if remove_model_cache:
            self._asr.release_models()
        result = self._storage.reset_local_data(
            remove_model_cache=remove_model_cache,
            credential_present=bool(credential_plan["stored_credential_present"]),
            credential_cleanup=self._providers.remove_stored_credential_for_reset,
        )
        self._logger.clear()
        result.update(credential_plan)
        result.setdefault("credentials_removed", False)
        return result

    def _diagnostic_core_status(self) -> dict[str, Any]:
        return {
            "status": "closed" if self._closed else "ready",
            "shutdown_requested": self._shutdown_requested,
            "protocol_version": PROTOCOL_VERSION,
            "core_version": CORE_VERSION,
        }

    def _before_source_delete(self, connection: Any, document_id: str) -> None:
        self._audience.before_source_delete(connection, document_id)
        self._challenge.before_source_delete(connection, document_id)
        self._assist.cues.before_source_delete(connection, document_id)
        connection.execute(
            """
            UPDATE sessions
            SET presentation_revision_id = NULL
            WHERE presentation_revision_id IN (
                SELECT id FROM presentation_revisions WHERE presentation_id = ?
            )
            """,
            (document_id,),
        )
        connection.execute(
            "UPDATE project SET current_presentation_id = NULL WHERE current_presentation_id = ?",
            (document_id,),
        )

    def _before_source_snapshot_delete(self, project_id: str, document_id: str) -> None:
        self._presentation_revisions.assert_source_deletable(project_id, document_id)
        self._rehearsal_analysis_jobs.drain(
            project_id=project_id, document_id=document_id, purge=True
        )
        self._presentation_workspace_voice.cancel_for_source(project_id, document_id)
        self._presentation_edit_plans.close_source(project_id, document_id)
        self._presentation_workspace_sources.close_source_readers(project_id, document_id)
        self._presentation_revisions.before_source_delete(project_id, document_id)

    def _after_source_reindex(
        self, connection: Any, document_id: str, previous_unit_ids: set[str]
    ) -> None:
        self._audience.after_source_reindex(connection, document_id, previous_unit_ids)
        self._challenge.after_source_reindex(connection, document_id, previous_unit_ids)
        self._assist.cues.after_source_reindex(connection, document_id, previous_unit_ids)

    def _before_knowledge_delete(self, connection: Any, knowledge_item_id: str) -> None:
        self._challenge.before_knowledge_delete(connection, knowledge_item_id)
        self._assist.cues.before_knowledge_delete(connection, knowledge_item_id)

    def _synchronize_semantic_index(self, project_id: str) -> dict[str, Any]:
        """Refresh an active index after a knowledge deletion without undoing the delete."""
        # The project rows have already committed before this best-effort
        # rebuild begins. Retire any count cached for the old mapping set even
        # when the rebuild fails and leaves that generation active.
        self._hybrid_retrieval.invalidate_project_mappings(project_id)
        with self._storage.project_database(project_id) as connection:
            active = connection.execute(
                "SELECT id FROM embedding_generations WHERE is_active = 1"
            ).fetchone()
        if active is None:
            return {"status": "not_built", "embedded_count": 0, "reused_count": 0}
        try:
            rebuilt = self._hybrid_retrieval.rebuild({"project_id": project_id})
            return {
                "status": "ready",
                "embedded_count": rebuilt["embedded_count"],
                "reused_count": rebuilt["reused_count"],
                "generation_id": rebuilt["generation_id"],
            }
        except CoreDomainError as error:
            return {"status": "partial", "error_code": error.code}
        except Exception:
            return {"status": "partial", "error_code": "INDEX_SYNC_FAILED"}
