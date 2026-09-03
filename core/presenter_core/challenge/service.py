"""Bounded, project-local Challenge orchestration."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from time import monotonic
from typing import Any, cast

from presenter_core.audience.service import AudienceModelService
from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.ingestion.service import provenance_label
from presenter_core.project.service import utc_now
from presenter_core.providers.context import ProviderContextBuilder
from presenter_core.providers.models import (
    CHALLENGE_INTENSITIES,
    MAX_PROVIDER_EVIDENCE_IDS,
    MAX_PROVIDER_MISSING_POINTS,
    MAX_PROVIDER_OBSERVATION_IDS,
    ProviderError,
    ReasoningProvider,
    ReasoningRequest,
    has_conflict_basis,
    validate_provider_output,
)
from presenter_core.providers.router import ReasoningRoute, ReasoningRouter
from presenter_core.providers.service import ProviderService
from presenter_core.retrieval.service import HybridRetrievalService
from presenter_core.session.service import SessionService
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

EventSink = Callable[[str, dict[str, Any]], None]
IndexSynchronizer = Callable[[str], dict[str, Any]]

MAX_ANSWER_CHARS = 4_000
MAX_QUESTION_CHARS = 500
MAX_RATIONALE_CHARS = 1_000
MAX_HISTORY_PAGE_SIZE = 25
MAX_HISTORY_OFFSET = 10_000
MAX_PRIOR_QUESTIONS = 3
MAX_QUESTIONS_PER_SESSION = 100
MAX_ANSWER_VERSIONS_PER_QUESTION = 10
MAX_SLIDE_RANGE = 200
MAX_ESTIMATED_SECONDS = 3_600

CHALLENGE_SCOPES = frozenset({"full_deck", "slide_range"})


class ChallengeService:
    """Own Challenge persistence, transitions, context, and provider calls."""

    def __init__(
        self,
        storage: StorageManager,
        sessions: SessionService,
        retrieval: HybridRetrievalService,
        providers: ProviderService,
        context_builder: ProviderContextBuilder,
        audience: AudienceModelService,
        event_sink: EventSink | None = None,
        index_synchronizer: IndexSynchronizer | None = None,
    ) -> None:
        self._storage = storage
        self._sessions = sessions
        self._retrieval = retrieval
        self._providers = providers
        self._context_builder = context_builder
        self._audience = audience
        self._router = ReasoningRouter()
        self._event_sink = event_sink
        self._index_synchronizer = index_synchronizer

    def configure(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "session_id",
                "audience_profile_ids",
                "intensity",
                "allow_follow_ups",
                "scope",
                "slide_start",
                "slide_end",
            },
        )
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        profile_ids = self._profile_ids(params.get("audience_profile_ids"))
        intensity = params.get("intensity", "normal")
        if not isinstance(intensity, str) or intensity not in CHALLENGE_INTENSITIES:
            raise CoreDomainError(
                "CHALLENGE_CONFIG_INVALID",
                "Challenge intensity is not supported.",
                details={"field": "intensity"},
            )
        allow_follow_ups = params.get("allow_follow_ups", True)
        if not isinstance(allow_follow_ups, bool):
            raise CoreDomainError(
                "CHALLENGE_CONFIG_INVALID",
                "allow_follow_ups must be a boolean.",
                details={"field": "allow_follow_ups"},
            )
        scope = params.get("scope", "full_deck")
        if not isinstance(scope, str) or scope not in CHALLENGE_SCOPES:
            raise CoreDomainError(
                "CHALLENGE_CONFIG_INVALID",
                "Challenge scope is not supported.",
                details={"field": "scope"},
            )
        slide_start, slide_end = self._slide_range(params, scope)
        now = utc_now()
        with self._storage.project_database(project_id) as connection:
            session = self._session_row(connection, project_id, session_id)
            if session["mode"] != "challenge":
                raise CoreDomainError(
                    "CHALLENGE_CONFIG_INVALID",
                    "The selected session is not a Challenge session.",
                )
            if session["status"] != "active":
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "Challenge configuration requires an active session.",
                )
            profiles = self._profile_rows(connection, project_id, profile_ids)
            if len(profiles) != len(profile_ids) or any(
                not bool(row["active"]) for row in profiles
            ):
                raise CoreDomainError(
                    "CHALLENGE_AUDIENCE_INVALID",
                    "Every selected audience profile must belong to this project and be active.",
                )
            presentation = connection.execute(
                """
                SELECT MIN(su.ordinal) AS first_ordinal, MAX(su.ordinal) AS last_ordinal
                FROM source_units AS su
                JOIN documents AS d ON d.id = su.document_id
                WHERE d.project_id = ? AND d.kind = 'presentation'
                  AND d.parse_status = 'ready' AND su.unit_type = 'slide'
                """,
                (project_id,),
            ).fetchone()
            if scope == "slide_range":
                if (
                    presentation is None
                    or presentation["first_ordinal"] is None
                    or presentation["last_ordinal"] is None
                    or slide_start is None
                    or slide_end is None
                    or slide_start < int(presentation["first_ordinal"])
                    or slide_end > int(presentation["last_ordinal"])
                ):
                    raise CoreDomainError(
                        "CHALLENGE_CONFIG_INVALID",
                        "The selected slide range is outside the current presentation.",
                    )
            existing = connection.execute(
                "SELECT 1 FROM challenge_configurations WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if existing is not None:
                question_count = connection.execute(
                    "SELECT COUNT(*) FROM questions WHERE session_id = ?", (session_id,)
                ).fetchone()
                if question_count is not None and int(question_count[0]) > 0:
                    raise CoreDomainError(
                        "CHALLENGE_STATE_INVALID",
                        "Challenge configuration cannot change after a question has "
                        "been generated.",
                    )
                connection.execute(
                    "DELETE FROM challenge_audiences WHERE session_id = ?", (session_id,)
                )
                connection.execute(
                    """
                    UPDATE challenge_configurations
                    SET intensity = ?, allow_follow_ups = ?, scope = ?, slide_start = ?,
                        slide_end = ?, state = 'ready_for_question', updated_at = ?
                    WHERE session_id = ?
                    """,
                    (
                        intensity,
                        int(allow_follow_ups),
                        scope,
                        slide_start,
                        slide_end,
                        now,
                        session_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO challenge_configurations (
                        session_id, intensity, allow_follow_ups, scope, slide_start,
                        slide_end, state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'ready_for_question', ?, ?)
                    """,
                    (
                        session_id,
                        intensity,
                        int(allow_follow_ups),
                        scope,
                        slide_start,
                        slide_end,
                        now,
                        now,
                    ),
                )
            connection.executemany(
                """
                INSERT INTO challenge_audiences (
                    id, session_id, audience_profile_id, selection_order,
                    display_name_snapshot, role_snapshot, organization_snapshot, selected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(uuid.uuid4()),
                        session_id,
                        row["id"],
                        order,
                        row["display_name"],
                        row["role"],
                        row["organization"],
                        now,
                    )
                    for order, row in enumerate(profiles)
                ],
            )
            connection.commit()
        result = self.get_state({"project_id": project_id, "session_id": session_id})
        result["configured"] = True
        return result

    def next_question(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "session_id", "follow_up_to_question_id"},
        )
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        follow_up_id = self._optional_uuid(
            params.get("follow_up_to_question_id"), "follow_up_to_question_id"
        )
        session = self._active_challenge_session(project_id, session_id)
        with self._storage.project_database(project_id) as connection:
            config = self._config_row(connection, session_id)
            current = self._latest_question(connection, session_id)
            if follow_up_id is not None:
                if not bool(config["allow_follow_ups"]):
                    raise CoreDomainError(
                        "CHALLENGE_FOLLOW_UP_DISABLED",
                        "Follow-up questions are disabled for this Challenge session.",
                    )
                if (
                    config["state"] != "evaluated"
                    or current is None
                    or str(current["id"]) != follow_up_id
                ):
                    raise CoreDomainError(
                        "CHALLENGE_STATE_INVALID",
                        "A follow-up requires the currently evaluated Challenge question.",
                    )
                parent = current
                profile_id = parent["asked_by_audience_profile_id"]
                if not isinstance(profile_id, str):
                    raise CoreDomainError(
                        "CHALLENGE_AUDIENCE_INVALID",
                        "The original audience profile is no longer usable for a follow-up.",
                    )
                task_type = "challenge_follow_up"
                expected_state = "evaluated"
            else:
                if config["state"] not in {"ready_for_question", "evaluated"}:
                    raise CoreDomainError(
                        "CHALLENGE_STATE_INVALID",
                        "Challenge cannot ask another question while an answer is pending.",
                        details={"state": config["state"]},
                    )
                audience_rows = self._usable_audience_rows(connection, session_id)
                if not audience_rows:
                    raise CoreDomainError(
                        "CHALLENGE_AUDIENCE_INVALID",
                        "No selected active audience profiles remain usable; select an "
                        "active profile.",
                    )
                root_count = connection.execute(
                    "SELECT COUNT(*) FROM questions WHERE session_id = ? "
                    "AND parent_question_id IS NULL",
                    (session_id,),
                ).fetchone()
                profile_id = str(
                    audience_rows[int(root_count[0]) % len(audience_rows)]["audience_profile_id"]
                )
                parent = None
                task_type = "challenge_question"
                expected_state = str(config["state"])
            if not isinstance(profile_id, str):
                raise CoreDomainError(
                    "CHALLENGE_AUDIENCE_INVALID",
                    "The selected audience profile is no longer usable.",
                )
            profile = connection.execute(
                "SELECT * FROM audience_profiles WHERE id = ? AND project_id = ? AND active = 1",
                (profile_id, project_id),
            ).fetchone()
            if profile is None:
                raise CoreDomainError(
                    "CHALLENGE_AUDIENCE_INVALID",
                    "The selected audience profile is no longer usable; select an active profile.",
                )
            question_count = connection.execute(
                "SELECT COUNT(*) FROM questions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if question_count is not None and int(question_count[0]) >= MAX_QUESTIONS_PER_SESSION:
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "This Challenge session reached its bounded question limit.",
                    details={"max_questions": MAX_QUESTIONS_PER_SESSION},
                )
            prior_context = self._prior_question_context(connection, session_id)
            intensity = str(config["intensity"])
            slide_start = config["slide_start"]
            slide_end = config["slide_end"]
        project = self._project_row(project_id)
        audience_context = self._audience.build_context(
            {"project_id": project_id, "audience_profile_ids": [profile_id]}
        )
        provider, health = self._provider_and_health()
        route = self._route(
            project,
            provider,
            health,
            task_type=task_type,
        )
        if (
            route.route not in {ReasoningRoute.LOCAL_REASONING, ReasoningRoute.REMOTE_REASONING}
            or provider is None
        ):
            raise CoreDomainError(
                "CHALLENGE_REASONING_UNAVAILABLE",
                "No permitted reasoning provider is available for this Challenge operation.",
                retryable=True,
                details={"route": route.route.value, "reason": route.reason},
            )
        request, manifest = self._context_builder.build(
            project_id=project_id,
            task_type=task_type,
            question=str(parent["text"]) if parent is not None else None,
            user_input=None,
            privacy_mode=str(project["privacy_mode"]),
            style_policy=str(session["style_policy"]),
            current_slide=(
                int(session["current_slide_start"])
                if session["current_slide_start"] is not None
                else None
            ),
            provider_id=provider.id,
            allow_private=provider.locality == "local",
            retrieval_query=self._audience_query(audience_context, intensity),
            slide_start=int(slide_start) if slide_start is not None else None,
            slide_end=int(slide_end) if slide_end is not None else None,
            audience_context=audience_context,
            challenge_intensity=intensity,
            prior_question_context=prior_context,
        )
        if not request.grounding_evidence:
            raise CoreDomainError(
                "CHALLENGE_CONTEXT_INSUFFICIENT",
                "Challenge needs usable project evidence before it can generate a question.",
            )
        result, provider_run_id = self._run_provider(
            project_id=project_id,
            session_id=session_id,
            privacy_mode=str(project["privacy_mode"]),
            provider=provider,
            request=request,
            manifest=manifest,
        )
        output = validate_provider_output(
            task_type,
            result.output,
            conflict_metadata=request.conflict_metadata,
        )
        supplied_evidence = self._supplied_evidence_map(request)
        supplied_observations = self._supplied_observation_ids(request, profile_id)
        evidence_ids = [str(item) for item in output["evidence_ids"]]
        observation_ids = [str(item) for item in output["audience_observation_ids"]]
        if (
            not evidence_ids
            or len(evidence_ids) > MAX_PROVIDER_EVIDENCE_IDS
            or not set(evidence_ids).issubset(supplied_evidence)
            or len(observation_ids) > MAX_PROVIDER_OBSERVATION_IDS
            or not set(observation_ids).issubset(supplied_observations)
        ):
            raise CoreDomainError(
                "CHALLENGE_OUTPUT_INVALID",
                "The Challenge provider cited evidence or audience observations "
                "outside its context.",
            )
        with self._storage.project_database(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_config = self._config_row(connection, session_id)
            latest = self._latest_question(connection, session_id)
            if str(current_config["state"]) != expected_state:
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "Challenge state changed while the question was being generated.",
                )
            if follow_up_id is not None and (latest is None or str(latest["id"]) != follow_up_id):
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "The follow-up parent question is no longer current.",
                )
            self._revalidate_generated_audience_context(
                connection,
                project_id=project_id,
                profile_id=profile_id,
                observation_ids=observation_ids,
            )
            if (
                connection.execute(
                    "SELECT 1 FROM questions WHERE session_id = ? "
                    "AND lower(text) = lower(?) LIMIT 1",
                    (session_id, output["question"]),
                ).fetchone()
                is not None
            ):
                raise CoreDomainError(
                    "CHALLENGE_OUTPUT_INVALID",
                    "The Challenge provider repeated an earlier question.",
                )
            canonical_refs = []
            for evidence_id in evidence_ids:
                reference = self._canonical_evidence(
                    connection,
                    project_id,
                    evidence_id,
                    allow_private=str(project["privacy_mode"]) == "local_only"
                    or provider.locality == "local",
                )
                supplied = supplied_evidence.get(evidence_id)
                if reference is None or supplied is None:
                    raise CoreDomainError(
                        "CHALLENGE_OUTPUT_INVALID",
                        "A Challenge question cited unavailable evidence.",
                    )
                canonical_refs.append(reference)
            question_id = str(uuid.uuid4())
            now = utc_now()
            connection.execute(
                """
                INSERT INTO questions (
                    id, session_id, asked_by_audience_profile_id, parent_question_id,
                    provider_run_id, audience_display_name_snapshot, audience_role_snapshot,
                    text, origin, rationale, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'simulated', ?, ?)
                """,
                (
                    question_id,
                    session_id,
                    profile_id,
                    follow_up_id,
                    provider_run_id,
                    profile["display_name"],
                    profile["role"],
                    self._bounded_core_text(output["question"], "question", MAX_QUESTION_CHARS),
                    self._bounded_core_text(output["rationale"], "rationale", MAX_RATIONALE_CHARS),
                    now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO question_evidence (
                    question_id, evidence_id, source_type, source_id, source_unit_id,
                    label, available
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                [
                    (
                        question_id,
                        reference["evidence_id"],
                        reference["source_type"],
                        reference["source_id"],
                        reference["source_unit_id"],
                        reference["label"],
                    )
                    for reference in canonical_refs
                ],
            )
            if observation_ids:
                current_observation_ids = {
                    str(row["id"])
                    for row in connection.execute(
                        """
                        SELECT ao.id FROM audience_observations AS ao
                        JOIN audience_profiles AS ap ON ap.id = ao.audience_profile_id
                        WHERE ao.audience_profile_id = ? AND ap.project_id = ?
                        """,
                        (profile_id, project_id),
                    ).fetchall()
                }
                connection.executemany(
                    """
                    INSERT INTO question_audience_observations (
                        question_id, observation_id, available
                    )
                    VALUES (?, ?, ?)
                    """,
                    [
                        (question_id, item, int(item in current_observation_ids))
                        for item in observation_ids
                    ],
                )
            transitioned = connection.execute(
                """
                UPDATE challenge_configurations
                SET state = 'awaiting_answer', updated_at = ?
                WHERE session_id = ? AND state = ?
                """,
                (now, session_id, expected_state),
            )
            if transitioned.rowcount != 1:
                connection.rollback()
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "Challenge state changed while the question was being saved.",
                )
            connection.commit()
            question = self._question_dict(connection, question_id, project_id)
        event_payload = {
            "project_id": project_id,
            "session_id": session_id,
            "question_id": question_id,
            "audience_profile_id": profile_id,
            "parent_question_id": follow_up_id,
            "route": route.route.value,
        }
        self._emit("challenge.question", event_payload)
        return {
            "project_id": project_id,
            "session_id": session_id,
            "state": "awaiting_answer",
            "question": question,
            "reasoning": {
                "route": route.route.value,
                "reason": route.reason,
                "provider_id": provider.id,
                "model_id": provider.model_id,
                "status": "ready",
            },
            "context_manifest": manifest,
        }

    def submit_answer(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "question_id", "text"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        question_id = self._uuid_param(params, "question_id")
        answer_text = self._bounded_text(params.get("text"), "text", MAX_ANSWER_CHARS)
        session = self._active_challenge_session(project_id, session_id)
        with self._storage.project_database(project_id) as connection:
            config = self._config_row(connection, session_id)
            question = connection.execute(
                "SELECT * FROM questions WHERE id = ? AND session_id = ?",
                (question_id, session_id),
            ).fetchone()
            if question is None:
                raise CoreDomainError(
                    "CHALLENGE_QUESTION_NOT_FOUND",
                    "The Challenge question was not found in this session.",
                )
            latest = self._latest_question(connection, session_id)
            if (
                config["state"] != "awaiting_answer"
                or latest is None
                or str(latest["id"]) != question_id
            ):
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "Submit an answer only for the current awaiting Challenge question.",
                    details={"state": config["state"]},
                )
            prior_context = self._prior_question_context(
                connection, session_id, exclude_question_id=question_id
            )
            profile_id = question["asked_by_audience_profile_id"]
            intensity = str(config["intensity"])
            slide_start = config["slide_start"]
            slide_end = config["slide_end"]
        project = self._project_row(project_id)
        audience_context = (
            self._audience.build_context(
                {"project_id": project_id, "audience_profile_ids": [str(profile_id)]}
            )
            if isinstance(profile_id, str) and self._profile_is_active(project_id, str(profile_id))
            else {"project_id": project_id, "profiles": []}
        )
        provider, health = self._provider_and_health()
        route = self._route(project, provider, health, task_type="challenge_evaluation")
        if (
            route.route not in {ReasoningRoute.LOCAL_REASONING, ReasoningRoute.REMOTE_REASONING}
            or provider is None
        ):
            raise CoreDomainError(
                "CHALLENGE_REASONING_UNAVAILABLE",
                "No permitted reasoning provider is available for this Challenge evaluation.",
                retryable=True,
                details={"route": route.route.value, "reason": route.reason},
            )
        with self._storage.project_database(project_id) as connection:
            question_grounding = self._question_grounding(
                connection,
                project_id,
                question_id,
                allow_private=provider.locality == "local",
            )
        request, manifest = self._context_builder.build(
            project_id=project_id,
            task_type="challenge_evaluation",
            question=str(question["text"]),
            user_input=answer_text,
            privacy_mode=str(project["privacy_mode"]),
            style_policy=str(session["style_policy"]),
            current_slide=(
                int(session["current_slide_start"])
                if session["current_slide_start"] is not None
                else None
            ),
            provider_id=provider.id,
            allow_private=provider.locality == "local",
            retrieval_query=f"{str(question['text'])} {answer_text}"[:500],
            slide_start=int(slide_start) if slide_start is not None else None,
            slide_end=int(slide_end) if slide_end is not None else None,
            audience_context=audience_context,
            challenge_intensity=intensity,
            prior_question_context=prior_context,
            additional_grounding_evidence=question_grounding,
        )
        if not request.grounding_evidence:
            raise CoreDomainError(
                "CHALLENGE_CONTEXT_INSUFFICIENT",
                "Challenge needs usable project evidence before it can evaluate an answer.",
            )
        result, provider_run_id = self._run_provider(
            project_id=project_id,
            session_id=session_id,
            privacy_mode=str(project["privacy_mode"]),
            provider=provider,
            request=request,
            manifest=manifest,
        )
        output = validate_provider_output(
            "challenge_evaluation",
            result.output,
            conflict_metadata=request.conflict_metadata,
        )
        supplied_evidence = self._supplied_evidence_map(request)
        supported_ids = [str(item) for item in output["supported_evidence_ids"]]
        if len(supported_ids) > MAX_PROVIDER_EVIDENCE_IDS or not set(supported_ids).issubset(
            supplied_evidence
        ):
            raise CoreDomainError(
                "CHALLENGE_OUTPUT_INVALID",
                "The Challenge evaluation cited evidence outside its context.",
            )
        if len(output["missing_points"]) > MAX_PROVIDER_MISSING_POINTS:
            raise CoreDomainError(
                "CHALLENGE_OUTPUT_INVALID",
                "The Challenge evaluation returned too many missing points.",
            )
        evaluation = self._normalize_evaluation(output, request, answer_text=answer_text)
        with self._storage.project_database(project_id) as connection:
            current_config = self._config_row(connection, session_id)
            latest = self._latest_question(connection, session_id)
            if (
                current_config["state"] != "awaiting_answer"
                or latest is None
                or str(latest["id"]) != question_id
            ):
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "Challenge state changed while the answer was being evaluated.",
                )
            answer_refs = []
            for evidence_id in supported_ids:
                reference = self._canonical_evidence(
                    connection,
                    project_id,
                    evidence_id,
                    allow_private=str(project["privacy_mode"]) == "local_only"
                    or provider.locality == "local",
                )
                if reference is None:
                    raise CoreDomainError(
                        "CHALLENGE_OUTPUT_INVALID",
                        "The Challenge evaluation cited evidence that is no longer available.",
                    )
                answer_refs.append(reference)
            existing_versions = connection.execute(
                "SELECT COUNT(*) FROM answer_versions WHERE question_id = ?", (question_id,)
            ).fetchone()
            if (
                existing_versions is not None
                and int(existing_versions[0]) >= MAX_ANSWER_VERSIONS_PER_QUESTION
            ):
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "This question reached its bounded answer-version limit.",
                    details={"max_answer_versions": MAX_ANSWER_VERSIONS_PER_QUESTION},
                )
            answer_id = str(uuid.uuid4())
            now = utc_now()
            connection.execute(
                """
                INSERT INTO answer_versions (
                    id, question_id, session_id, provider_run_id, text, origin, preferred,
                    correctness_score, directness_score, completeness_score, concision_score,
                    style_match_score, source_support_status, source_support_feedback,
                    evaluation_json, created_at
                ) VALUES (?, ?, ?, ?, ?, 'user_typed', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    answer_id,
                    question_id,
                    session_id,
                    provider_run_id,
                    answer_text,
                    evaluation["correctness"]["score"],
                    evaluation["directness"]["score"],
                    evaluation["completeness"]["score"],
                    evaluation["concision"]["score"],
                    evaluation["style_match"]["score"],
                    evaluation["source_support"]["status"],
                    evaluation["source_support"]["feedback"],
                    json.dumps(
                        evaluation, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                    ),
                    now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO answer_evidence (
                    answer_version_id, evidence_id, source_type, source_id, source_unit_id,
                    label, available
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                [
                    (
                        answer_id,
                        reference["evidence_id"],
                        reference["source_type"],
                        reference["source_id"],
                        reference["source_unit_id"],
                        reference["label"],
                    )
                    for reference in answer_refs
                ],
            )
            transitioned = connection.execute(
                """
                UPDATE challenge_configurations
                SET state = 'evaluated', updated_at = ?
                WHERE session_id = ? AND state = 'awaiting_answer'
                """,
                (now, session_id),
            )
            if transitioned.rowcount != 1:
                connection.rollback()
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "Challenge state changed while the answer was being saved.",
                )
            connection.commit()
            answer = self._answer_dict(connection, answer_id)
        self._emit(
            "challenge.evaluation",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question_id": question_id,
                "answer_version_id": answer_id,
                "source_support_status": evaluation["source_support"]["status"],
                "scores": {
                    name: evaluation[name]["score"]
                    for name in (
                        "correctness",
                        "directness",
                        "completeness",
                        "concision",
                        "style_match",
                    )
                },
            },
        )
        return {
            "project_id": project_id,
            "session_id": session_id,
            "state": "evaluated",
            "answer_version": answer,
            "evaluation": evaluation,
            "reasoning": {
                "route": route.route.value,
                "reason": route.reason,
                "provider_id": provider.id,
                "model_id": provider.model_id,
                "status": "ready",
            },
            "context_manifest": manifest,
        }

    def retry_question(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "question_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        question_id = self._uuid_param(params, "question_id")
        self._active_challenge_session(project_id, session_id)
        with self._storage.project_database(project_id) as connection:
            config = self._config_row(connection, session_id)
            question = connection.execute(
                "SELECT id FROM questions WHERE id = ? AND session_id = ?",
                (question_id, session_id),
            ).fetchone()
            latest = self._latest_question(connection, session_id)
            if question is None:
                raise CoreDomainError(
                    "CHALLENGE_QUESTION_NOT_FOUND",
                    "The Challenge question was not found in this session.",
                )
            if config["state"] != "evaluated" or latest is None or str(latest["id"]) != question_id:
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "Retry is available only for the currently evaluated question.",
                )
            connection.execute(
                "UPDATE challenge_configurations SET state = 'awaiting_answer', "
                "updated_at = ? WHERE session_id = ?",
                (utc_now(), session_id),
            )
            connection.commit()
        return self.get_state({"project_id": project_id, "session_id": session_id})

    def save_preferred_answer(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "session_id", "question_id", "answer_version_id"},
        )
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        question_id = self._uuid_param(params, "question_id")
        answer_id = self._uuid_param(params, "answer_version_id")
        self._active_challenge_session(project_id, session_id)
        existing_knowledge_id: str | None = None
        with self._storage.project_database(project_id) as connection:
            config = self._config_row(connection, session_id)
            question = connection.execute(
                "SELECT id FROM questions WHERE id = ? AND session_id = ?",
                (question_id, session_id),
            ).fetchone()
            answer = connection.execute(
                """
                SELECT * FROM answer_versions
                WHERE id = ? AND question_id = ? AND session_id = ?
                """,
                (answer_id, question_id, session_id),
            ).fetchone()
            latest = self._latest_question(connection, session_id)
            if question is None:
                raise CoreDomainError(
                    "CHALLENGE_QUESTION_NOT_FOUND",
                    "The Challenge question was not found in this session.",
                )
            if answer is None:
                raise CoreDomainError(
                    "CHALLENGE_ANSWER_NOT_FOUND",
                    "The Challenge answer version was not found in this session.",
                )
            if config["state"] != "evaluated" or latest is None or str(latest["id"]) != question_id:
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "Save a preferred answer only after evaluating the current question.",
                )
            promotion = connection.execute(
                "SELECT * FROM challenge_answer_promotions WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            if promotion is not None and str(promotion["answer_version_id"]) == answer_id:
                existing_knowledge_id = str(promotion["knowledge_item_id"])
                knowledge = connection.execute(
                    "SELECT * FROM knowledge_items WHERE id = ? AND project_id = ?",
                    (existing_knowledge_id, project_id),
                ).fetchone()
                if knowledge is not None:
                    connection.execute(
                        "UPDATE knowledge_items SET use_live = 1, use_rehearsal = 1, "
                        "preferred = 1, updated_at = ? WHERE id = ? AND project_id = ?",
                        (utc_now(), existing_knowledge_id, project_id),
                    )
                    connection.execute(
                        "UPDATE answer_versions SET preferred = 0 WHERE question_id = ?",
                        (question_id,),
                    )
                    connection.execute(
                        "UPDATE answer_versions SET preferred = 1 WHERE id = ?", (answer_id,)
                    )
                    connection.commit()
                    return {
                        "project_id": project_id,
                        "session_id": session_id,
                        "question_id": question_id,
                        "answer_version_id": answer_id,
                        "preferred": True,
                        "knowledge_item": self._knowledge_dict(connection, knowledge["id"]),
                        "semantic_sync": {"status": "not_needed"},
                    }
                connection.execute(
                    "DELETE FROM challenge_answer_promotions WHERE question_id = ?",
                    (question_id,),
                )
            elif promotion is not None:
                old_knowledge_id = str(promotion["knowledge_item_id"])
                old_statement_ids = [
                    str(row["provenance_id"])
                    for row in connection.execute(
                        """
                        SELECT provenance_id FROM knowledge_evidence
                        WHERE knowledge_item_id = ? AND provenance_type = 'user_statement'
                        """,
                        (old_knowledge_id,),
                    ).fetchall()
                ]
                connection.execute(
                    "DELETE FROM challenge_answer_promotions WHERE question_id = ?",
                    (question_id,),
                )
                connection.execute(
                    "DELETE FROM embedding_vectors WHERE entity_type = 'knowledge_item' "
                    "AND entity_id = ?",
                    (old_knowledge_id,),
                )
                connection.execute(
                    "DELETE FROM knowledge_items WHERE id = ? AND project_id = ?",
                    (old_knowledge_id, project_id),
                )
                self._delete_orphan_statements(connection, old_statement_ids)
            connection.execute(
                "UPDATE answer_versions SET preferred = 0 WHERE question_id = ?", (question_id,)
            )
            connection.execute(
                "UPDATE answer_versions SET preferred = 1 WHERE id = ?", (answer_id,)
            )
            now = utc_now()
            statement_id = str(uuid.uuid4())
            knowledge_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO user_statements (
                    id, project_id, origin_session_id, source_utterance_id, text, created_at
                ) VALUES (?, ?, ?, NULL, ?, ?)
                """,
                (statement_id, project_id, session_id, answer["text"], now),
            )
            connection.execute(
                """
                INSERT INTO knowledge_items (
                    id, project_id, kind, text, use_live, use_rehearsal, preferred, private,
                    created_by, origin_session_id, created_at, updated_at
                ) VALUES (?, ?, 'answer', ?, 1, 1, 1, 0, 'user', ?, ?, ?)
                """,
                (knowledge_id, project_id, answer["text"], session_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO knowledge_evidence (knowledge_item_id, provenance_type, provenance_id)
                VALUES (?, 'user_statement', ?)
                """,
                (knowledge_id, statement_id),
            )
            connection.execute(
                """
                INSERT INTO challenge_answer_promotions (
                    question_id, answer_version_id, knowledge_item_id, promoted_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (question_id, answer_id, knowledge_id, now, now),
            )
            connection.commit()
            knowledge = self._knowledge_dict(connection, knowledge_id)
        semantic_sync = (
            self._index_synchronizer(project_id)
            if self._index_synchronizer is not None
            else {"status": "not_requested"}
        )
        self._emit(
            "project.index_ready",
            {
                "project_id": project_id,
                "index_kind": "knowledge_item",
                "knowledge_item_id": knowledge_id,
                "status": semantic_sync.get("status"),
            },
        )
        return {
            "project_id": project_id,
            "session_id": session_id,
            "question_id": question_id,
            "answer_version_id": answer_id,
            "preferred": True,
            "knowledge_item": knowledge,
            "semantic_sync": semantic_sync,
        }

    def get_state(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        with self._storage.project_database(project_id) as connection:
            session = self._session_row(connection, project_id, session_id)
            if session["mode"] != "challenge":
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "The selected session is not a Challenge session.",
                )
            config_row = connection.execute(
                "SELECT * FROM challenge_configurations WHERE session_id = ?", (session_id,)
            ).fetchone()
            audiences = self._audience_summaries(connection, session_id)
            current = self._latest_question(connection, session_id)
            state = "unconfigured" if config_row is None else str(config_row["state"])
            current_question = (
                self._question_dict(connection, str(current["id"]), project_id) if current else None
            )
            latest_answer = (
                connection.execute(
                    """
                    SELECT id FROM answer_versions
                    WHERE question_id = ?
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (current["id"],),
                ).fetchone()
                if current is not None
                else None
            )
            answer_result = (
                self._answer_dict(connection, str(latest_answer["id"]))
                if latest_answer is not None
                else None
            )
            config = self._config_dict(config_row) if config_row is not None else None
            actions = (
                self._valid_actions(state, bool(config_row and config_row["allow_follow_ups"]))
                if str(session["status"]) == "active"
                else []
            )
        availability = self._availability(project_id, task_type="challenge_question")
        return {
            "project_id": project_id,
            "session_id": session_id,
            "session_status": str(session["status"]),
            "state": state,
            "config": config,
            "audiences": audiences,
            "current_question": current_question,
            "latest_answer_version": answer_result,
            "valid_next_actions": actions,
            "reasoning": availability,
        }

    def list_history(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id", "limit", "offset"})
        project_id = self._project_id(params)
        session_id = self._uuid_param(params, "session_id")
        limit = self._bounded_integer(params.get("limit", 20), "limit", 1, MAX_HISTORY_PAGE_SIZE)
        offset = self._bounded_integer(params.get("offset", 0), "offset", 0, MAX_HISTORY_OFFSET)
        with self._storage.project_database(project_id) as connection:
            session = self._session_row(connection, project_id, session_id)
            if session["mode"] != "challenge":
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "The selected session is not a Challenge session.",
                )
            rows = connection.execute(
                """
                SELECT id FROM questions
                WHERE session_id = ?
                ORDER BY created_at, id
                LIMIT ? OFFSET ?
                """,
                (session_id, limit + 1, offset),
            ).fetchall()
            has_more = len(rows) > limit
            rows = rows[:limit]
            history = [
                self._history_question_dict(connection, str(row["id"]), project_id) for row in rows
            ]
            total_row = connection.execute(
                "SELECT COUNT(*) FROM questions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return {
            "project_id": project_id,
            "session_id": session_id,
            "items": history,
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "total": int(total_row[0]) if total_row is not None else 0,
        }

    def before_source_delete(self, connection: sqlite3.Connection, document_id: str) -> None:
        """Invalidate Challenge references before source rows cascade."""
        unit_ids = {
            str(row["id"])
            for row in connection.execute(
                "SELECT id FROM source_units WHERE document_id = ?", (document_id,)
            ).fetchall()
        }
        self._invalidate_source_refs(connection, document_id, unit_ids)

    def after_source_reindex(
        self,
        connection: sqlite3.Connection,
        document_id: str,
        previous_unit_ids: set[str],
    ) -> None:
        """Invalidate references to source units replaced by a re-index."""
        self._invalidate_source_refs(connection, document_id, previous_unit_ids)

    def before_knowledge_delete(
        self, connection: sqlite3.Connection, knowledge_item_id: str
    ) -> None:
        """Invalidate Challenge refs before a KnowledgeItem is deleted."""
        statement_ids = {
            str(row["provenance_id"])
            for row in connection.execute(
                """
                SELECT provenance_id FROM knowledge_evidence
                WHERE knowledge_item_id = ? AND provenance_type = 'user_statement'
                """,
                (knowledge_item_id,),
            ).fetchall()
        }
        clauses = ["evidence_id = ?"]
        parameters: list[Any] = [knowledge_item_id]
        if statement_ids:
            placeholders = ", ".join("?" for _ in statement_ids)
            clauses.append(f"source_id IN ({placeholders})")
            parameters.extend(sorted(statement_ids))
        predicate = " OR ".join(clauses)
        connection.execute(
            f"UPDATE question_evidence SET available = 0 WHERE {predicate}", parameters
        )
        connection.execute(
            f"UPDATE answer_evidence SET available = 0 WHERE {predicate}", parameters
        )

    def _run_provider(
        self,
        *,
        project_id: str,
        session_id: str,
        privacy_mode: str,
        provider: ReasoningProvider,
        request: ReasoningRequest,
        manifest: dict[str, Any],
    ) -> tuple[Any, str]:
        run_id = str(uuid.uuid4())
        started_at = utc_now()
        with self._storage.project_database(project_id) as connection:
            current_project = connection.execute(
                "SELECT privacy_mode FROM project WHERE id = ?", (project_id,)
            ).fetchone()
            if current_project is None:
                raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
            if str(current_project["privacy_mode"]) != privacy_mode:
                raise CoreDomainError(
                    "CHALLENGE_STATE_INVALID",
                    "Project privacy changed while Challenge context was being prepared; retry.",
                )
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
            validate_provider_output(
                request.task_type,
                result.output,
                conflict_metadata=request.conflict_metadata,
            )
        except ProviderError as error:
            self._finish_provider_run(
                project_id, run_id, status="error", error=error, started_monotonic=started
            )
            raise
        except Exception as error:
            mapped = ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The Challenge reasoning request failed.",
                retryable=True,
            )
            self._finish_provider_run(
                project_id, run_id, status="error", error=mapped, started_monotonic=started
            )
            raise mapped from error
        self._finish_provider_run(
            project_id, run_id, status="success", result=result, started_monotonic=started
        )
        return result, run_id

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

    def _active_challenge_session(self, project_id: str, session_id: str) -> sqlite3.Row:
        with self._storage.project_database(project_id) as connection:
            row = self._session_row(connection, project_id, session_id)
        if row["mode"] != "challenge":
            raise CoreDomainError(
                "CHALLENGE_STATE_INVALID",
                "The selected session is not a Challenge session.",
            )
        if row["status"] != "active":
            raise CoreDomainError(
                "SESSION_NOT_ACTIVE",
                "Challenge mutations require an active Challenge session.",
            )
        return row

    def _route(
        self,
        project: sqlite3.Row,
        provider: ReasoningProvider | None,
        health: Any | None,
        *,
        task_type: str,
    ) -> Any:
        return self._router.decide(
            task_type=task_type,
            privacy_mode=str(project["privacy_mode"]),
            remote_acknowledged=project["remote_reasoning_acknowledged_at"] is not None,
            provider=provider,
            provider_health=health,
        )

    def _provider_and_health(self) -> tuple[ReasoningProvider | None, Any | None]:
        if not self._providers.is_enabled():
            return None, None
        provider = self._providers.current_provider()
        return provider, provider.health()

    def _availability(self, project_id: str, *, task_type: str) -> dict[str, Any]:
        project = self._project_row(project_id)
        provider, health = self._provider_and_health()
        route = self._route(project, provider, health, task_type=task_type)
        return {
            "route": route.route.value,
            "reason": route.reason,
            "provider_id": provider.id if provider is not None else None,
            "provider_status": health.status if health is not None else "unavailable",
            "privacy_mode": project["privacy_mode"],
        }

    def _project_row(self, project_id: str) -> sqlite3.Row:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _session_row(
        connection: sqlite3.Connection, project_id: str, session_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM sessions WHERE id = ? AND project_id = ?",
            (session_id, project_id),
        ).fetchone()
        if row is None:
            raise CoreDomainError("SESSION_NOT_FOUND", "The session was not found.")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _config_row(connection: sqlite3.Connection, session_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM challenge_configurations WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise CoreDomainError(
                "CHALLENGE_CONFIG_INVALID",
                "Configure the Challenge session before using it.",
            )
        return cast(sqlite3.Row, row)

    @staticmethod
    def _latest_question(connection: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute(
                """
                SELECT * FROM questions
                WHERE session_id = ?
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone(),
        )

    @staticmethod
    def _usable_audience_rows(connection: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
        return list(
            connection.execute(
                """
                SELECT ca.*, ap.display_name, ap.role, ap.organization, ap.active
                FROM challenge_audiences AS ca
                JOIN audience_profiles AS ap ON ap.id = ca.audience_profile_id
                WHERE ca.session_id = ? AND ap.active = 1
                ORDER BY ca.selection_order
                """,
                (session_id,),
            ).fetchall()
        )

    @staticmethod
    def _profile_rows(
        connection: sqlite3.Connection, project_id: str, profile_ids: list[str]
    ) -> list[sqlite3.Row]:
        placeholders = ", ".join("?" for _ in profile_ids)
        rows = list(
            connection.execute(
                f"SELECT * FROM audience_profiles WHERE project_id = ? AND id IN ({placeholders})",
                [project_id, *profile_ids],
            ).fetchall()
        )
        by_id = {str(row["id"]): row for row in rows}
        return [by_id[profile_id] for profile_id in profile_ids if profile_id in by_id]

    def _audience_summaries(
        self, connection: sqlite3.Connection, session_id: str
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT ca.*, ap.display_name, ap.role, ap.organization, ap.active
            FROM challenge_audiences AS ca
            LEFT JOIN audience_profiles AS ap ON ap.id = ca.audience_profile_id
            WHERE ca.session_id = ?
            ORDER BY ca.selection_order
            """,
            (session_id,),
        ).fetchall()
        return [
            {
                "id": row["audience_profile_id"],
                "display_name": row["display_name"] or row["display_name_snapshot"],
                "role": row["role"] if row["display_name"] is not None else row["role_snapshot"],
                "organization": (
                    row["organization"]
                    if row["display_name"] is not None
                    else row["organization_snapshot"]
                ),
                "active": bool(row["active"]) if row["active"] is not None else False,
                "available": row["audience_profile_id"] is not None and bool(row["active"]),
                "selection_order": int(row["selection_order"]),
            }
            for row in rows
        ]

    def _question_dict(
        self,
        connection: sqlite3.Connection,
        question_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            raise CoreDomainError(
                "CHALLENGE_QUESTION_NOT_FOUND", "The Challenge question was not found."
            )
        profile_id = row["asked_by_audience_profile_id"]
        profile = (
            connection.execute(
                "SELECT display_name, role, organization, active "
                "FROM audience_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
            if profile_id is not None
            else None
        )
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "audience_profile_id": profile_id,
            "audience": {
                "id": profile_id,
                "display_name": profile["display_name"]
                if profile is not None
                else row["audience_display_name_snapshot"],
                "role": profile["role"] if profile is not None else row["audience_role_snapshot"],
                "organization": profile["organization"] if profile is not None else None,
                "available": profile is not None and bool(profile["active"]),
                "historical": profile is None,
            },
            "parent_question_id": row["parent_question_id"],
            "text": row["text"],
            "origin": row["origin"],
            "rationale": row["rationale"],
            "evidence": self._evidence_refs(
                connection, "question_evidence", "question_id", question_id
            ),
            "audience_observations": self._observation_refs(connection, question_id, project_id),
            "created_at": row["created_at"],
        }

    def _history_question_dict(
        self, connection: sqlite3.Connection, question_id: str, project_id: str
    ) -> dict[str, Any]:
        result = self._question_dict(connection, question_id, project_id)
        answer_rows = connection.execute(
            """
            SELECT id FROM answer_versions
            WHERE question_id = ?
            ORDER BY created_at, id
            LIMIT ?
            """,
            (question_id, MAX_ANSWER_VERSIONS_PER_QUESTION),
        ).fetchall()
        result["answer_versions"] = [
            self._answer_dict(connection, str(row["id"])) for row in answer_rows
        ]
        return result

    def _answer_dict(self, connection: sqlite3.Connection, answer_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM answer_versions WHERE id = ?", (answer_id,)
        ).fetchone()
        if row is None:
            raise CoreDomainError(
                "CHALLENGE_ANSWER_NOT_FOUND", "The Challenge answer was not found."
            )
        evaluation: dict[str, Any] | None = None
        if isinstance(row["evaluation_json"], str):
            try:
                parsed = json.loads(str(row["evaluation_json"]))
                if isinstance(parsed, dict):
                    evaluation = parsed
            except json.JSONDecodeError:
                evaluation = None
        return {
            "id": row["id"],
            "question_id": row["question_id"],
            "session_id": row["session_id"],
            "text": row["text"],
            "origin": row["origin"],
            "preferred": bool(row["preferred"]),
            "evaluation": evaluation,
            "evidence": self._evidence_refs(
                connection, "answer_evidence", "answer_version_id", answer_id
            ),
            "created_at": row["created_at"],
        }

    def _evidence_refs(
        self,
        connection: sqlite3.Connection,
        table: str,
        key_column: str,
        key: str,
    ) -> list[dict[str, Any]]:
        if table not in {"question_evidence", "answer_evidence"}:
            raise AssertionError("unsupported Challenge evidence table")
        rows = connection.execute(
            f"""
            SELECT evidence_id, source_type, source_id, source_unit_id, label, available
            FROM {table} WHERE {key_column} = ?
            ORDER BY rowid LIMIT ?
            """,
            (key, MAX_PROVIDER_EVIDENCE_IDS),
        ).fetchall()
        return [self._evidence_ref_dict(connection, row) for row in rows]

    def _evidence_ref_dict(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> dict[str, Any]:
        available = bool(row["available"]) and self._evidence_is_available(connection, row)
        return {
            "evidence_id": row["evidence_id"],
            "source_type": row["source_type"],
            "source_id": row["source_id"],
            "source_unit_id": row["source_unit_id"],
            "label": row["label"] if available else "Source unavailable",
            "available": available,
        }

    @staticmethod
    def _evidence_is_available(connection: sqlite3.Connection, row: sqlite3.Row) -> bool:
        if row["source_type"] == "user_statement":
            found = connection.execute(
                """
                SELECT 1
                FROM knowledge_items AS k
                JOIN knowledge_evidence AS ke ON ke.knowledge_item_id = k.id
                JOIN user_statements AS us ON us.id = ke.provenance_id
                WHERE k.id = ? AND ke.provenance_type = 'user_statement'
                  AND us.id = ?
                """,
                (row["evidence_id"], row["source_id"]),
            ).fetchone()
            return found is not None
        found = connection.execute(
            """
            SELECT 1
            FROM chunks AS c
            JOIN source_units AS su ON su.id = c.source_unit_id
            JOIN documents AS d ON d.id = su.document_id
            WHERE c.id = ? AND d.id = ? AND su.id = ? AND d.parse_status = 'ready'
            """,
            (row["evidence_id"], row["source_id"], row["source_unit_id"]),
        ).fetchone()
        return found is not None

    def _observation_refs(
        self,
        connection: sqlite3.Connection,
        question_id: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        question = connection.execute(
            "SELECT asked_by_audience_profile_id FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()
        current_observation_ids: set[str] = set()
        profile_id = question["asked_by_audience_profile_id"] if question is not None else None
        if isinstance(profile_id, str):
            try:
                current_context = self._audience.build_context_for_connection(
                    connection,
                    project_id=project_id,
                    audience_profile_ids=[profile_id],
                )
            except CoreDomainError:
                current_context = {"profiles": []}
            for profile in current_context.get("profiles", []):
                if not isinstance(profile, dict) or str(profile.get("id")) != profile_id:
                    continue
                current_observation_ids = {
                    str(observation["id"])
                    for observation in profile.get("observations", [])
                    if isinstance(observation, dict) and isinstance(observation.get("id"), str)
                }
                break
        rows = connection.execute(
            """
            SELECT observation_id, available FROM question_audience_observations
            WHERE question_id = ? ORDER BY rowid LIMIT ?
            """,
            (question_id, MAX_PROVIDER_OBSERVATION_IDS),
        ).fetchall()
        return [
            {
                "observation_id": row["observation_id"],
                "available": bool(row["available"])
                and str(row["observation_id"]) in current_observation_ids,
            }
            for row in rows
        ]

    def _config_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "session_id": row["session_id"],
            "intensity": row["intensity"],
            "allow_follow_ups": bool(row["allow_follow_ups"]),
            "scope": row["scope"],
            "slide_start": row["slide_start"],
            "slide_end": row["slide_end"],
            "state": row["state"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _valid_actions(state: str, allow_follow_ups: bool) -> list[str]:
        if state == "ready_for_question":
            return ["challenge.next_question"]
        if state == "awaiting_answer":
            return ["challenge.submit_answer"]
        if state == "evaluated":
            actions = [
                "challenge.retry_question",
                "challenge.next_question",
                "challenge.save_preferred_answer",
            ]
            if allow_follow_ups:
                actions.insert(2, "challenge.follow_up")
            return actions
        return []

    def _prior_question_context(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        *,
        exclude_question_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["q.session_id = ?"]
        parameters: list[Any] = [session_id]
        if exclude_question_id is not None:
            clauses.append("q.id <> ?")
            parameters.append(exclude_question_id)
        rows = connection.execute(
            """
            SELECT q.id, q.text, q.rationale,
                   (SELECT av.text FROM answer_versions AS av
                    WHERE av.question_id = q.id ORDER BY av.created_at DESC,
                          av.id DESC LIMIT 1) AS answer_text
            FROM questions AS q
            WHERE """
            + " AND ".join(clauses)
            + " ORDER BY q.created_at DESC, q.id DESC LIMIT ?",
            [*parameters, MAX_PRIOR_QUESTIONS],
        ).fetchall()
        return [
            {
                "question_id": row["id"],
                "question": str(row["text"])[:MAX_QUESTION_CHARS],
                "answer": str(row["answer_text"])[:600] if row["answer_text"] else None,
                "rationale": str(row["rationale"])[:300],
            }
            for row in reversed(rows)
        ]

    def _question_grounding(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        question_id: str,
        *,
        allow_private: bool,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT evidence_id, source_type, source_id, source_unit_id, label
            FROM question_evidence WHERE question_id = ? AND available = 1
            ORDER BY rowid LIMIT ?
            """,
            (question_id, MAX_PROVIDER_EVIDENCE_IDS),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            canonical = self._canonical_evidence(
                connection,
                project_id,
                str(row["evidence_id"]),
                allow_private=allow_private,
            )
            if canonical is not None:
                result.append(canonical)
        return result

    def _canonical_evidence(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        evidence_id: str,
        *,
        allow_private: bool,
    ) -> dict[str, Any] | None:
        chunk = connection.execute(
            """
            SELECT c.id AS evidence_id, c.text, su.id AS source_unit_id,
                   su.unit_type, su.ordinal, su.start_ms, su.end_ms,
                   su.speaker_label, d.id AS source_id, d.original_name,
                   d.kind, d.parse_status
            FROM chunks AS c
            JOIN source_units AS su ON su.id = c.source_unit_id
            JOIN documents AS d ON d.id = su.document_id
            WHERE c.id = ? AND d.project_id = ? AND d.parse_status = 'ready'
            """,
            (evidence_id, project_id),
        ).fetchone()
        if chunk is not None:
            source_type = "transcript" if chunk["kind"] == "transcript" else "document"
            return {
                "evidence_id": str(chunk["evidence_id"]),
                "source_type": source_type,
                "source_id": str(chunk["source_id"]),
                "source_unit_id": str(chunk["source_unit_id"]),
                "label": provenance_label(
                    chunk["original_name"],
                    chunk["unit_type"],
                    chunk["ordinal"],
                    start_ms=chunk["start_ms"],
                    end_ms=chunk["end_ms"],
                    speaker_label=chunk["speaker_label"],
                    transcript=source_type == "transcript",
                ),
                "text": str(chunk["text"]),
                "private": False,
            }
        knowledge = connection.execute(
            """
            SELECT k.id AS evidence_id, k.text AS knowledge_text, k.kind,
                   k.private, k.preferred, us.id AS source_id
            FROM knowledge_items AS k
            JOIN knowledge_evidence AS ke
              ON ke.knowledge_item_id = k.id AND ke.provenance_type = 'user_statement'
            JOIN user_statements AS us ON us.id = ke.provenance_id
            WHERE k.id = ? AND k.project_id = ?
              AND k.use_rehearsal = 1
            ORDER BY us.id LIMIT 1
            """,
            (evidence_id, project_id),
        ).fetchone()
        if knowledge is None or (bool(knowledge["private"]) and not allow_private):
            return None
        return {
            "evidence_id": str(knowledge["evidence_id"]),
            "source_type": "user_statement",
            "source_id": str(knowledge["source_id"]),
            "source_unit_id": None,
            "label": (
                "Your practiced answer"
                if knowledge["kind"] == "answer"
                else "Your Teach explanation"
            ),
            "text": str(knowledge["knowledge_text"]),
            "private": bool(knowledge["private"]),
            "knowledge_item_id": str(knowledge["evidence_id"]),
            "preferred": bool(knowledge["preferred"]),
        }

    @staticmethod
    def _supplied_evidence_map(request: ReasoningRequest) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in (
            *request.evidence,
            *request.preferred_user_explanations,
            *request.grounding_evidence,
        ):
            evidence_id = item.get("evidence_id")
            if isinstance(evidence_id, str):
                result.setdefault(evidence_id, item)
        return result

    @staticmethod
    def _supplied_observation_ids(request: ReasoningRequest, profile_id: str) -> set[str]:
        result: set[str] = set()
        for profile in request.audience_context:
            if str(profile.get("id")) != profile_id:
                continue
            for observation in profile.get("observations", []):
                if isinstance(observation, dict) and isinstance(observation.get("id"), str):
                    result.add(str(observation["id"]))
        return result

    @staticmethod
    def _normalize_evaluation(
        output: dict[str, Any],
        request: ReasoningRequest,
        *,
        answer_text: str,
    ) -> dict[str, Any]:
        evaluation = {
            key: dict(value) if isinstance(value, dict) else value for key, value in output.items()
        }
        word_count = len(answer_text.split())
        evaluation["word_count"] = word_count
        evaluation["estimated_speaking_seconds"] = round(
            min(MAX_ESTIMATED_SECONDS, word_count / 130 * 60), 1
        )
        preferred_seconds = request.style_context.get("preferred_answer_seconds")
        evaluation["preferred_answer_seconds"] = (
            int(preferred_seconds)
            if isinstance(preferred_seconds, int) and not isinstance(preferred_seconds, bool)
            else None
        )
        if not request.speaker_evidence:
            evaluation["style_match"] = {
                "score": None,
                "feedback": "Not enough style evidence to assess style match.",
            }
        if has_conflict_basis(request.conflict_metadata):
            evaluation["source_support"] = {
                "status": "conflicted",
                "feedback": "Relevant project evidence contains a conflict; state the "
                "ambiguity explicitly.",
            }
        evaluation["missing_points"] = [
            str(item)[:300] for item in output["missing_points"][:MAX_PROVIDER_MISSING_POINTS]
        ]
        evaluation["supported_evidence_ids"] = [
            str(item) for item in output["supported_evidence_ids"][:MAX_PROVIDER_EVIDENCE_IDS]
        ]
        preferred = next(
            (
                str(item["text"])[:800]
                for item in request.preferred_user_explanations
                if item.get("preferred") is True and isinstance(item.get("text"), str)
            ),
            None,
        )
        if preferred is not None:
            evaluation["strongest_prior_phrasing"] = preferred
        return evaluation

    @staticmethod
    def _audience_query(audience_context: dict[str, Any], intensity: str) -> str:
        parts = [intensity, "decision rationale cost risk tradeoff evidence"]
        for profile in audience_context.get("profiles", []):
            if not isinstance(profile, dict):
                continue
            for key in ("role", "organization", "user_supplied_notes"):
                value = profile.get(key)
                if isinstance(value, str):
                    parts.append(value)
            for observation in profile.get("observations", []):
                if isinstance(observation, dict) and isinstance(observation.get("text"), str):
                    parts.append(observation["text"])
        return " ".join(parts)[:500]

    def _profile_is_active(self, project_id: str, profile_id: str) -> bool:
        with self._storage.project_database(project_id) as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM audience_profiles WHERE id = ? AND project_id = ? "
                    "AND active = 1",
                    (profile_id, project_id),
                ).fetchone()
                is not None
            )

    def _revalidate_generated_audience_context(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        profile_id: str,
        observation_ids: list[str],
    ) -> None:
        """Reapply M4's current profile/observation rules before question insertion."""
        try:
            current_context = self._audience.build_context_for_connection(
                connection,
                project_id=project_id,
                audience_profile_ids=[profile_id],
            )
        except CoreDomainError as error:
            raise CoreDomainError(
                "CHALLENGE_CONTEXT_STALE",
                "The selected AudienceContext changed while the question was being generated; "
                "retry with current audience state.",
            ) from error
        profiles = [
            profile
            for profile in current_context.get("profiles", [])
            if isinstance(profile, dict) and str(profile.get("id")) == profile_id
        ]
        if len(profiles) != 1:
            raise CoreDomainError(
                "CHALLENGE_CONTEXT_STALE",
                "The selected audience profile is no longer active; retry with current audience "
                "state.",
            )
        current_observation_ids = {
            str(observation["id"])
            for observation in profiles[0].get("observations", [])
            if isinstance(observation, dict) and isinstance(observation.get("id"), str)
        }
        if not set(observation_ids).issubset(current_observation_ids):
            raise CoreDomainError(
                "CHALLENGE_CONTEXT_STALE",
                "An audience observation became stale while the question was being generated; "
                "retry with current audience state.",
            )

    def _invalidate_source_refs(
        self, connection: sqlite3.Connection, document_id: str, unit_ids: set[str]
    ) -> None:
        predicates = ["source_id = ?"]
        parameters: list[Any] = [document_id]
        if unit_ids:
            placeholders = ", ".join("?" for _ in unit_ids)
            predicates.append(f"source_unit_id IN ({placeholders})")
            parameters.extend(sorted(unit_ids))
        predicate = " OR ".join(predicates)
        connection.execute(
            f"UPDATE question_evidence SET available = 0 WHERE {predicate}", parameters
        )
        connection.execute(
            f"UPDATE answer_evidence SET available = 0 WHERE {predicate}", parameters
        )

    @staticmethod
    def _delete_orphan_statements(connection: sqlite3.Connection, statement_ids: list[str]) -> None:
        for statement_id in statement_ids:
            connection.execute(
                """
                DELETE FROM user_statements
                WHERE id = ? AND NOT EXISTS (
                    SELECT 1 FROM knowledge_evidence
                    WHERE provenance_type = 'user_statement' AND provenance_id = user_statements.id
                )
                """,
                (statement_id,),
            )

    @staticmethod
    def _profile_ids(value: Any) -> list[str]:
        if not isinstance(value, list) or not 1 <= len(value) <= 3:
            raise CoreDomainError(
                "CHALLENGE_AUDIENCE_INVALID",
                "Select between 1 and 3 unique active audience profiles.",
            )
        result: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise CoreDomainError(
                    "CHALLENGE_AUDIENCE_INVALID",
                    "Audience profile IDs must be UUIDs.",
                )
            normalized = ChallengeService._normalize_uuid(item, "audience_profile_ids")
            if normalized in result:
                raise CoreDomainError(
                    "CHALLENGE_AUDIENCE_INVALID",
                    "Audience profiles must be unique.",
                )
            result.append(normalized)
        return result

    @staticmethod
    def _slide_range(params: dict[str, Any], scope: str) -> tuple[int | None, int | None]:
        start_value = params.get("slide_start")
        end_value = params.get("slide_end")
        if scope == "full_deck":
            if start_value is not None or end_value is not None:
                raise CoreDomainError(
                    "CHALLENGE_CONFIG_INVALID",
                    "Full-deck Challenge scope cannot include a slide range.",
                )
            return None, None
        if start_value is None or end_value is None:
            raise CoreDomainError(
                "CHALLENGE_CONFIG_INVALID",
                "A slide-range Challenge requires slide_start and slide_end.",
            )
        start = ChallengeService._bounded_integer(start_value, "slide_start", 1, 10_000)
        end = ChallengeService._bounded_integer(end_value, "slide_end", 1, 10_000)
        if end < start or end - start + 1 > MAX_SLIDE_RANGE:
            raise CoreDomainError(
                "CHALLENGE_CONFIG_INVALID",
                "The Challenge slide range is invalid or too large.",
            )
        return start, end

    @staticmethod
    def _bounded_text(value: Any, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise invalid_request(f"{field} must be a bounded non-empty string.", field=field)
        if any(ord(character) < 32 and character not in "\r\n\t" for character in value):
            raise invalid_request(f"{field} contains unsupported control characters.", field=field)
        return value.strip()

    @staticmethod
    def _bounded_core_text(value: Any, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise CoreDomainError(
                "CHALLENGE_OUTPUT_INVALID",
                f"Challenge {field} exceeded its bounded output limit.",
            )
        if any(ord(character) < 32 and character not in "\r\n\t" for character in value):
            raise CoreDomainError(
                "CHALLENGE_OUTPUT_INVALID",
                f"Challenge {field} contains unsupported control characters.",
            )
        return value.strip()

    @staticmethod
    def _bounded_integer(value: Any, field: str, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise invalid_request(f"{field} must be between {minimum} and {maximum}.", field=field)
        return int(value)

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
        return ChallengeService._normalize_uuid(value, field)

    @staticmethod
    def _optional_uuid(value: Any, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        return ChallengeService._normalize_uuid(value, field)

    @staticmethod
    def _normalize_uuid(value: str, field: str) -> str:
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a UUID.", field=field) from error

    @staticmethod
    def _knowledge_dict(connection: sqlite3.Connection, knowledge_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM knowledge_items WHERE id = ?", (knowledge_id,)
        ).fetchone()
        if row is None:
            raise CoreDomainError(
                "KNOWLEDGE_NOT_FOUND", "The promoted knowledge item was not found."
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
                {
                    "provenance_type": item["provenance_type"],
                    "provenance_id": item["provenance_id"],
                }
                for item in evidence
            ],
        }

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)
