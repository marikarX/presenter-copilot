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
from presenter_core.credentials import CredentialStore
from presenter_core.diagnostics import DiagnosticService
from presenter_core.errors import CoreDomainError, reject_unknown_fields
from presenter_core.ingestion.service import IngestionService
from presenter_core.knowledge.service import KnowledgeService
from presenter_core.live.service import AssistService
from presenter_core.live.settings import HudSettingsService
from presenter_core.model_service import ModelService
from presenter_core.presentation.adapters import PresentationAdapter
from presenter_core.presentation.service import SlideStateService
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
    ) -> None:
        self._clock = clock
        self._started_at = clock()
        self._shutdown_requested = False
        self._closed = False
        self._last_close_error: CoreDomainError | None = None
        self._event_sink = event_sink
        self._storage = StorageManager(data_root)
        self._logger = SafeLogger(self._storage.paths.root)
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
        )
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
            vad_config=vad_config,
            **(
                {"worker_join_timeout_seconds": asr_worker_join_timeout_seconds}
                if asr_worker_join_timeout_seconds is not None
                else {}
            ),
        )
        self._knowledge = KnowledgeService(
            self._storage,
            after_delete=self._synchronize_semantic_index,
            after_mapping_delete=self._hybrid_retrieval.invalidate_project_mappings,
            before_delete=self._before_knowledge_delete,
        )
        self._providers = ProviderService(
            self._storage,
            reasoning_provider,
            event_sink=self._emit_service_event,
            credential_store=credential_store,
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
            self._run.stop_active_runs(status="aborted")
            self._assist.stop_active_sessions(status="aborted")
            self._cancel_active_teach_capture()
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
        self._presentation.close()
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
            del error
            self._logger.event(
                "request.failed",
                {"operation": method, "error_code": "INTERNAL_ERROR"},
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
        if method == "source.list":
            return make_response(request_id, result=self._ingestion.list_sources(params))
        if method == "source.preview":
            return make_response(request_id, result=self._ingestion.preview_source(params))
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
        if method == "provider.list":
            return make_response(request_id, result=self._providers.list(params))
        if method == "provider.configure":
            result = self._providers.configure(params)
            return make_response(request_id, result=result)
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
        self._run.stop_project_runs({"project_id": project_id})
        self._assist.stop_project_sessions({"project_id": project_id})
        self._cancel_active_teach_capture(project_id)
        self._teach.purge_project(project_id)
        self._assist.purge_project(project_id)
        self._presentation.purge_project(project_id)
        self._hybrid_retrieval.evict_project(project_id)

    def _stop_active_for_model_change(self) -> None:
        """Model cache deletion never occurs underneath a process owner."""
        self._run.stop_active_runs(status="aborted")
        self._assist.stop_active_sessions(status="aborted")
        self._cancel_active_teach_capture()
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
        self._run.stop_active_runs(status="aborted")
        self._assist.stop_active_sessions(status="aborted")
        self._cancel_active_teach_capture()
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
