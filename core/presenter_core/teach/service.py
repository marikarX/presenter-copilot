"""M3 Teach orchestration with durable provenance and bounded provider calls."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from time import monotonic
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.project.service import utc_now
from presenter_core.providers.context import ProviderContextBuilder
from presenter_core.providers.models import (
    KNOWLEDGE_KINDS,
    ProviderError,
    ReasoningProvider,
    ReasoningRequest,
    validate_provider_output,
)
from presenter_core.providers.router import ReasoningRoute, ReasoningRouter
from presenter_core.providers.service import ProviderService
from presenter_core.retrieval.service import HybridRetrievalService
from presenter_core.session.service import SessionService
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

MAX_TEACH_TEXT_CHARS = 4_000
MAX_KNOWLEDGE_TEXT_CHARS = 1_500

EventSink = Callable[[str, dict[str, Any]], None]


class TeachService:
    """Keep provider suggestions provisional until the user explicitly confirms."""

    def __init__(
        self,
        storage: StorageManager,
        sessions: SessionService,
        retrieval: HybridRetrievalService,
        providers: ProviderService,
        context_builder: ProviderContextBuilder,
        event_sink: EventSink | None = None,
    ) -> None:
        self._storage = storage
        self._sessions = sessions
        self._retrieval = retrieval
        self._providers = providers
        self._context_builder = context_builder
        self._router = ReasoningRouter()
        self._event_sink = event_sink

    def next_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        session = self._active_teach_session(project_id, session_id)
        with self._storage.project_database(project_id) as connection:
            pending = connection.execute(
                "SELECT id FROM teach_candidates WHERE session_id = ? AND status = 'pending'",
                (session_id,),
            ).fetchone()
            if pending is not None:
                raise CoreDomainError(
                    "TEACH_CANDIDATE_PENDING",
                    "Confirm or reject the current Teach candidate before asking another question.",
                )
            if session["teach_state"] == "candidate_ready":
                raise CoreDomainError(
                    "TEACH_ANSWER_PENDING",
                    "Save or discard the current Teach answer before asking another question.",
                )
            if session["teach_state"] == "awaiting_user":
                existing = connection.execute(
                    """
                    SELECT id, text FROM utterances
                    WHERE session_id = ? AND actor = 'ai_coach'
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (session_id,),
                ).fetchone()
                if existing is not None:
                    return self._prompt_result(
                        session,
                        str(existing["id"]),
                        str(existing["text"]),
                        "awaiting_user",
                        route="existing_prompt",
                        focus="decision_rationale",
                    )

        project = self._project_row(project_id)
        provider, health = self._provider_and_health()
        route = self._router.decide(
            task_type="teach_question",
            privacy_mode=str(session["privacy_mode"]),
            remote_acknowledged=project["remote_reasoning_acknowledged_at"] is not None,
            provider=provider,
            provider_health=health,
        )
        focus = "decision_rationale"
        reasoning_status: dict[str, Any] = {"route": route.route.value, "reason": route.reason}
        question: str
        manifest: dict[str, Any] | None = None
        if (
            route.route in {ReasoningRoute.LOCAL_REASONING, ReasoningRoute.REMOTE_REASONING}
            and provider is not None
        ):
            try:
                request, manifest = self._context_builder.build(
                    project_id=project_id,
                    task_type="teach_question",
                    question=None,
                    user_input=None,
                    privacy_mode=str(session["privacy_mode"]),
                    style_policy=str(session["style_policy"]),
                    current_slide=session["current_slide_start"],
                    provider_id=provider.id,
                    allow_private=provider.locality == "local",
                )
                result = self._run_provider(
                    project_id=project_id,
                    session_id=session_id,
                    privacy_mode=str(session["privacy_mode"]),
                    provider=provider,
                    request=request,
                    manifest=manifest,
                )
                output = validate_provider_output("teach_question", result.output)
                question = str(output["question"])
                focus = str(output["focus"])
                reasoning_status.update(
                    {
                        "provider_id": provider.id,
                        "model_id": provider.model_id,
                        "status": "ready",
                    }
                )
            except ProviderError as error:
                reasoning_status.update(
                    {
                        "route": ReasoningRoute.RETRIEVAL_ONLY.value,
                        "status": "fallback",
                        "provider_error": self._safe_provider_error(error),
                    }
                )
                question, focus = self._fallback_question(project_id)
                route = self._retrieval_only_decision(route, error.code)
        else:
            question, focus = self._fallback_question(project_id)
        utterance_id = self._persist_coach_prompt(
            project_id,
            session_id,
            question,
        )
        self._emit(
            "teach.prompt",
            {
                "project_id": project_id,
                "session_id": session_id,
                "utterance_id": utterance_id,
                "question": question,
                "focus": focus,
                "route": route.route.value,
            },
        )
        result = self._prompt_result(
            session,
            utterance_id,
            question,
            "awaiting_user",
            route=route.route.value,
            focus=focus,
        )
        result["reasoning"] = reasoning_status
        if manifest is not None:
            result["context_manifest"] = manifest
        return result

    def submit_text(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "session_id", "text", "local_only", "keep_local"},
        )
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        text = self._bounded_text(params.get("text"), "text", MAX_TEACH_TEXT_CHARS)
        local_only = params.get("local_only", params.get("keep_local", False))
        if not isinstance(local_only, bool):
            raise invalid_request("local_only must be a boolean.", field="local_only")
        session = self._active_teach_session(project_id, session_id)
        source_utterance_id = str(uuid.uuid4())
        created_at = utc_now()
        with self._storage.project_database(project_id) as connection:
            current_prompt = connection.execute(
                """
                SELECT id, text FROM utterances
                WHERE session_id = ? AND actor = 'ai_coach'
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO utterances (id, session_id, actor, text, created_at, is_final)
                VALUES (?, ?, 'user', ?, ?, 1)
                """,
                (source_utterance_id, session_id, text, created_at),
            )
            connection.commit()

        provider, health = self._provider_and_health()
        project = self._project_row(project_id)
        route = self._router.decide(
            task_type="teach_candidate",
            privacy_mode=str(session["privacy_mode"]),
            remote_acknowledged=project["remote_reasoning_acknowledged_at"] is not None,
            provider=provider,
            provider_health=health,
            local_only_submission=local_only,
        )
        response: dict[str, Any] = {
            "project_id": project_id,
            "session_id": session_id,
            "source_utterance_id": source_utterance_id,
            "state": "candidate_ready",
            "candidate": None,
            "direct_save_available": True,
            "route": route.route.value,
            "local_only": local_only,
        }
        if current_prompt is not None:
            response["prompt_utterance_id"] = current_prompt["id"]

        if (
            route.route
            in {
                ReasoningRoute.LOCAL_REASONING,
                ReasoningRoute.REMOTE_REASONING,
            }
            and provider is not None
        ):
            manifest: dict[str, Any] | None = None
            try:
                request, manifest = self._context_builder.build(
                    project_id=project_id,
                    task_type="teach_candidate",
                    question=str(current_prompt["text"]) if current_prompt is not None else None,
                    user_input=text,
                    privacy_mode=str(session["privacy_mode"]),
                    style_policy=str(session["style_policy"]),
                    current_slide=session["current_slide_start"],
                    provider_id=provider.id,
                    allow_private=provider.locality == "local",
                )
                result = self._run_provider(
                    project_id=project_id,
                    session_id=session_id,
                    privacy_mode=str(session["privacy_mode"]),
                    provider=provider,
                    request=request,
                    manifest=manifest,
                )
                output = validate_provider_output("teach_candidate", result.output)
                candidate_id = str(uuid.uuid4())
                with self._storage.project_database(project_id) as connection:
                    connection.execute(
                        """
                        INSERT INTO teach_candidates (
                            id, session_id, source_utterance_id, proposed_kind,
                            proposed_text, provider_run_id, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                        """,
                        (
                            candidate_id,
                            session_id,
                            source_utterance_id,
                            output["kind"],
                            output["text"],
                            self._latest_provider_run_id(project_id, session_id),
                            created_at,
                        ),
                    )
                    connection.execute(
                        "UPDATE sessions SET teach_state = 'candidate_ready' WHERE id = ?",
                        (session_id,),
                    )
                    connection.commit()
                response["candidate"] = {
                    "id": candidate_id,
                    "source_utterance_id": source_utterance_id,
                    "proposed_kind": output["kind"],
                    "proposed_text": output["text"],
                    "follow_up_question": output["follow_up_question"],
                    "provisional": True,
                    "created_by": "ai_suggestion",
                }
                response["reasoning"] = {
                    "route": route.route.value,
                    "provider_id": provider.id,
                    "model_id": provider.model_id,
                    "status": "ready",
                }
                response["context_manifest"] = manifest
                self._emit(
                    "teach.knowledge_candidate",
                    {
                        "project_id": project_id,
                        "session_id": session_id,
                        "candidate_id": candidate_id,
                        "source_utterance_id": source_utterance_id,
                        "proposed_kind": output["kind"],
                        "provisional": True,
                    },
                )
                return response
            except ProviderError as error:
                response["reasoning"] = {
                    "route": ReasoningRoute.RETRIEVAL_ONLY.value,
                    "status": "fallback",
                    "provider_error": self._safe_provider_error(error),
                }
        else:
            response["reasoning"] = {
                "route": route.route.value,
                "status": "direct_save_only",
                "reason": route.reason,
            }
        with self._storage.project_database(project_id) as connection:
            connection.execute(
                "UPDATE sessions SET teach_state = 'candidate_ready' WHERE id = ?",
                (session_id,),
            )
            connection.commit()
        return response

    def confirm_knowledge_item(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "session_id",
                "candidate_id",
                "source_utterance_id",
                "text",
                "kind",
                "preferred",
                "private",
                "use_live",
                "use_rehearsal",
            },
        )
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        self._active_teach_session(project_id, session_id)
        candidate_id = self._optional_uuid(params.get("candidate_id"), "candidate_id")
        source_utterance_id = self._optional_uuid(
            params.get("source_utterance_id"), "source_utterance_id"
        )
        preferred = self._flag(params, "preferred", False)
        private = self._flag(params, "private", False)
        use_live = self._flag(params, "use_live", True)
        use_rehearsal = self._flag(params, "use_rehearsal", True)
        with self._storage.project_database(project_id) as connection:
            candidate: sqlite3.Row | None = None
            if candidate_id is not None:
                candidate = connection.execute(
                    """
                    SELECT tc.*, u.actor, u.session_id AS utterance_session_id
                    FROM teach_candidates AS tc
                    JOIN utterances AS u ON u.id = tc.source_utterance_id
                    WHERE tc.id = ? AND tc.session_id = ? AND u.session_id = ?
                    """,
                    (candidate_id, session_id, session_id),
                ).fetchone()
                if candidate is None:
                    raise CoreDomainError(
                        "TEACH_CANDIDATE_NOT_FOUND",
                        "The Teach candidate was not found in this session.",
                    )
                if candidate["status"] != "pending":
                    raise CoreDomainError(
                        "TEACH_CANDIDATE_NOT_PENDING",
                        "The Teach candidate has already been decided.",
                    )
                if candidate["actor"] != "user":
                    raise CoreDomainError(
                        "TEACH_SOURCE_INVALID",
                        "Only a user utterance can support confirmed knowledge.",
                    )
                source_utterance_id = str(candidate["source_utterance_id"])
            if source_utterance_id is None:
                source = connection.execute(
                    """
                    SELECT id, actor, session_id, text FROM utterances
                    WHERE session_id = ? AND actor = 'user'
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (session_id,),
                ).fetchone()
            else:
                source = connection.execute(
                    "SELECT id, actor, session_id, text FROM utterances WHERE id = ?",
                    (source_utterance_id,),
                ).fetchone()
            if source is None or source["session_id"] != session_id or source["actor"] != "user":
                raise CoreDomainError(
                    "TEACH_SOURCE_INVALID",
                    "The confirmation source must be a user utterance in this Teach session.",
                )
            final_text = params.get("text")
            if final_text is None and candidate is not None:
                final_text = candidate["proposed_text"]
            if final_text is None:
                final_text = source["text"]
            final_text = self._bounded_text(final_text, "text", MAX_KNOWLEDGE_TEXT_CHARS)
            kind = params.get(
                "kind", candidate["proposed_kind"] if candidate is not None else "rationale"
            )
            if not isinstance(kind, str) or kind not in KNOWLEDGE_KINDS:
                raise invalid_request("kind is not supported.", field="kind")
            now = utc_now()
            statement_id = str(uuid.uuid4())
            existing_statement = connection.execute(
                """
                SELECT id FROM user_statements
                WHERE project_id = ? AND source_utterance_id = ? AND text = ?
                ORDER BY created_at LIMIT 1
                """,
                (project_id, source["id"], source["text"]),
            ).fetchone()
            if existing_statement is not None:
                statement_id = str(existing_statement["id"])
            else:
                connection.execute(
                    """
                    INSERT INTO user_statements
                        (id, project_id, origin_session_id, source_utterance_id, text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (statement_id, project_id, session_id, source["id"], source["text"], now),
                )
            knowledge_id = str(uuid.uuid4())
            created_by = "ai_suggested_user_confirmed" if candidate is not None else "user"
            connection.execute(
                """
                INSERT INTO knowledge_items (
                    id, project_id, kind, text, use_live, use_rehearsal,
                    preferred, private, created_by, origin_session_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    knowledge_id,
                    project_id,
                    kind,
                    final_text,
                    int(use_live),
                    int(use_rehearsal),
                    int(preferred),
                    int(private),
                    created_by,
                    session_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO knowledge_evidence (knowledge_item_id, provenance_type, provenance_id)
                VALUES (?, 'user_statement', ?)
                """,
                (knowledge_id, statement_id),
            )
            if candidate is not None:
                connection.execute(
                    """
                    UPDATE teach_candidates
                    SET status = 'confirmed', knowledge_item_id = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (knowledge_id, candidate_id),
                )
            connection.execute(
                "UPDATE sessions SET teach_state = 'ready_for_prompt' WHERE id = ?",
                (session_id,),
            )
            connection.commit()
            knowledge = self._knowledge_dict(connection, knowledge_id)
            statement = connection.execute(
                "SELECT * FROM user_statements WHERE id = ?", (statement_id,)
            ).fetchone()
            assert statement is not None
            statement_dict = self._statement_dict(statement)

        semantic_sync = self._synchronize_semantic_index(project_id)
        self._emit(
            "project.index_ready",
            {
                "project_id": project_id,
                "index_kind": "knowledge_item",
                "knowledge_item_id": knowledge_id,
                "status": semantic_sync["status"],
            },
        )
        return {
            "knowledge_item": knowledge,
            "user_statement": statement_dict,
            "semantic_sync": semantic_sync,
            "state": "ready_for_prompt",
        }

    def reject_knowledge_item(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "candidate_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        self._active_teach_session(project_id, session_id)
        candidate_id = self._uuid_param(params, "candidate_id")
        with self._storage.project_database(project_id) as connection:
            candidate = connection.execute(
                "SELECT * FROM teach_candidates WHERE id = ? AND session_id = ?",
                (candidate_id, session_id),
            ).fetchone()
            if candidate is None:
                raise CoreDomainError(
                    "TEACH_CANDIDATE_NOT_FOUND", "The Teach candidate was not found."
                )
            if candidate["status"] != "pending":
                raise CoreDomainError(
                    "TEACH_CANDIDATE_NOT_PENDING", "The Teach candidate has already been decided."
                )
            connection.execute(
                "UPDATE teach_candidates SET status = 'rejected' WHERE id = ?",
                (candidate_id,),
            )
            connection.execute(
                "UPDATE sessions SET teach_state = 'ready_for_prompt' WHERE id = ?",
                (session_id,),
            )
            connection.commit()
        return {
            "project_id": project_id,
            "session_id": session_id,
            "candidate_id": candidate_id,
            "rejected": True,
            "state": "ready_for_prompt",
        }

    def _run_provider(
        self,
        *,
        project_id: str,
        session_id: str,
        privacy_mode: str,
        provider: ReasoningProvider,
        request: ReasoningRequest,
        manifest: dict[str, Any],
    ) -> Any:
        run_id = str(uuid.uuid4())
        started_at = utc_now()
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
                    started_at,
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                ),
            )
            connection.commit()
        manifest_payload = dict(manifest)
        manifest_payload["provider_id"] = provider.id
        manifest_payload["provider_run_id"] = run_id
        if provider.locality == "remote":
            self._emit("privacy.remote_context_manifest", manifest_payload)
        started = monotonic()
        try:
            result = provider.generate(request)
            # Keep domain-side validation as a second boundary even when an
            # adapter already validates its own structured response. A
            # malformed injected provider must not be recorded as success.
            validate_provider_output(request.task_type, result.output)
        except ProviderError as error:
            self._finish_provider_run(
                project_id,
                run_id,
                status="error",
                error=error,
                started_monotonic=started,
            )
            raise
        except Exception as error:
            mapped = ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The reasoning provider request failed.",
                retryable=True,
            )
            self._finish_provider_run(
                project_id,
                run_id,
                status="error",
                error=mapped,
                started_monotonic=started,
            )
            raise mapped from error
        self._finish_provider_run(
            project_id,
            run_id,
            status="success",
            result=result,
            started_monotonic=started,
        )
        return result

    def _finish_provider_run(
        self,
        project_id: str,
        run_id: str,
        *,
        status: str,
        result: Any | None = None,
        error: ProviderError | None = None,
        started_monotonic: float | None = None,
    ) -> None:
        with self._storage.project_database(project_id) as connection:
            connection.execute(
                """
                UPDATE provider_runs
                SET ended_at = ?, status = ?, input_token_count = ?, output_token_count = ?,
                    latency_ms = ?, error_code = ?
                WHERE id = ?
                """,
                (
                    utc_now(),
                    status,
                    getattr(result, "input_token_count", None),
                    getattr(result, "output_token_count", None),
                    max(0, int((monotonic() - started_monotonic) * 1000))
                    if isinstance(started_monotonic, float)
                    else started_monotonic,
                    error.code if error is not None else None,
                    run_id,
                ),
            )
            connection.commit()

    def _latest_provider_run_id(self, project_id: str, session_id: str) -> str | None:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                "SELECT id FROM provider_runs WHERE session_id = ? "
                "ORDER BY started_at DESC, id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            return str(row["id"]) if row is not None else None

    def _synchronize_semantic_index(self, project_id: str) -> dict[str, Any]:
        with self._storage.project_database(project_id) as connection:
            active = connection.execute(
                "SELECT id FROM embedding_generations WHERE is_active = 1"
            ).fetchone()
        if active is None:
            return {"status": "not_built", "embedded_count": 0, "reused_count": 0}
        try:
            rebuilt = self._retrieval.rebuild({"project_id": project_id})
            return {
                "status": "ready",
                "embedded_count": rebuilt["embedded_count"],
                "reused_count": rebuilt["reused_count"],
                "generation_id": rebuilt["generation_id"],
            }
        except CoreDomainError as error:
            return {"status": "partial", "error_code": error.code}
        except Exception:
            # The confirmed KnowledgeItem is already durable. An unexpected
            # local model/index failure must not turn confirmation into a
            # failed save; the next explicit rebuild can repair the index.
            return {"status": "partial", "error_code": "INDEX_SYNC_FAILED"}

    def _active_teach_session(self, project_id: str, session_id: str) -> sqlite3.Row:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ? AND project_id = ?",
                (session_id, project_id),
            ).fetchone()
        if row is None:
            raise CoreDomainError("SESSION_NOT_FOUND", "The session was not found.")
        if row["mode"] != "teach":
            raise CoreDomainError("MODE_NOT_IMPLEMENTED", "Only Teach sessions are supported.")
        if row["status"] != "active":
            raise CoreDomainError(
                "SESSION_NOT_ACTIVE", "Teach actions require an active Teach session."
            )
        return cast(sqlite3.Row, row)

    def _project_row(self, project_id: str) -> sqlite3.Row:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
        return cast(sqlite3.Row, row)

    def _provider_and_health(self) -> tuple[ReasoningProvider | None, Any | None]:
        if not self._providers.is_enabled():
            return None, None
        provider = self._providers.current_provider()
        return provider, provider.health()

    def _fallback_question(self, project_id: str) -> tuple[str, str]:
        retrieval = self._retrieval.query(
            {
                "project_id": project_id,
                "query": "rejected option decision rationale tradeoff risk assumption",
                "limit": 6,
                "allow_private": True,
            }
        )
        conflicts = retrieval.get("conflicts")
        if isinstance(conflicts, list) and conflicts:
            conflict = conflicts[0]
            if isinstance(conflict, dict) and isinstance(conflict.get("subject"), str):
                return (
                    f"The sources disagree about {conflict['subject']}. Which value or context "
                    "is current for this project?",
                    "exact_fact_conflict",
                )
        hits = retrieval.get("hits")
        if isinstance(hits, list) and hits:
            evidence = hits[0].get("evidence") if isinstance(hits[0], dict) else None
            label = evidence.get("label") if isinstance(evidence, dict) else None
            if isinstance(label, str):
                return (
                    f"What made the option described in {label} a poor fit for this project?",
                    "decision_rationale",
                )
        return ("What decision or tradeoff behind this project should I remember?", "tradeoff")

    @staticmethod
    def _retrieval_only_decision(decision: Any, reason: str) -> Any:
        del decision
        from presenter_core.providers.router import RouteDecision

        return RouteDecision(ReasoningRoute.RETRIEVAL_ONLY, reason, None)

    def _persist_coach_prompt(self, project_id: str, session_id: str, question: str) -> str:
        utterance_id = str(uuid.uuid4())
        with self._storage.project_database(project_id) as connection:
            connection.execute(
                "INSERT INTO utterances "
                "(id, session_id, actor, text, created_at, is_final) "
                "VALUES (?, ?, 'ai_coach', ?, ?, 1)",
                (utterance_id, session_id, question, utc_now()),
            )
            connection.execute(
                "UPDATE sessions SET teach_state = 'awaiting_user' WHERE id = ?",
                (session_id,),
            )
            connection.commit()
        return utterance_id

    @staticmethod
    def _prompt_result(
        session: sqlite3.Row,
        utterance_id: str,
        question: str,
        state: str,
        *,
        route: str,
        focus: str,
    ) -> dict[str, Any]:
        return {
            "project_id": session["project_id"],
            "session_id": session["id"],
            "state": state,
            "utterance_id": utterance_id,
            "question": question,
            "focus": focus,
            "route": route,
        }

    @staticmethod
    def _knowledge_dict(connection: sqlite3.Connection, knowledge_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM knowledge_items WHERE id = ?", (knowledge_id,)
        ).fetchone()
        if row is None:
            raise CoreDomainError(
                "KNOWLEDGE_NOT_FOUND", "The project knowledge item was not found."
            )
        evidence = connection.execute(
            "SELECT provenance_type, provenance_id FROM knowledge_evidence "
            "WHERE knowledge_item_id = ?",
            (knowledge_id,),
        ).fetchall()
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "kind": row["kind"],
            "text": row["text"],
            "use_live": bool(row["use_live"]),
            "use_rehearsal": bool(row["use_rehearsal"]),
            "preferred": bool(row["preferred"]),
            "private": bool(row["private"]),
            "created_by": row["created_by"],
            "origin_session_id": row["origin_session_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "evidence": [
                {"provenance_type": item["provenance_type"], "provenance_id": item["provenance_id"]}
                for item in evidence
            ],
        }

    @staticmethod
    def _statement_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "origin_session_id": row["origin_session_id"],
            "source_utterance_id": row["source_utterance_id"],
            "text": row["text"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _safe_provider_error(error: ProviderError) -> dict[str, Any]:
        return {"code": error.code, "retryable": error.retryable}

    @staticmethod
    def _bounded_text(value: Any, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise invalid_request(f"{field} must be a bounded non-empty string.", field=field)
        if any(ord(character) < 32 and character not in "\r\n\t" for character in value):
            raise invalid_request(f"{field} contains unsupported control characters.", field=field)
        return value.strip()

    @staticmethod
    def _flag(params: dict[str, Any], field: str, default: bool) -> bool:
        value = params.get(field, default)
        if not isinstance(value, bool):
            raise invalid_request(f"{field} must be a boolean.", field=field)
        return value

    @staticmethod
    def _project_id(params: dict[str, Any]) -> str:
        value = params.get("project_id")
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _uuid_param(params: dict[str, Any], field: str) -> str:
        value = params.get(field)
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        return TeachService._normalize_uuid(value, field)

    @staticmethod
    def _optional_uuid(value: Any, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        return TeachService._normalize_uuid(value, field)

    @staticmethod
    def _normalize_uuid(value: str, field: str) -> str:
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a UUID.", field=field) from error

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)
