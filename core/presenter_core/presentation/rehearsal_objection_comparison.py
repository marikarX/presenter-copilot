"""Compare verified objection candidates from two distinct ended Runs.

A comparison is unverified pairwise interpretation. It references original candidate
identities and never merges, replaces or approves their independent review dispositions.
"""

import json
import sqlite3
from collections.abc import Callable
from copy import deepcopy
from typing import Any, NoReturn

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.claims import digest
from presenter_core.presentation.rehearsal_analysis_store import recording_state
from presenter_core.presentation.rehearsal_objection_store import RehearsalObjectionStore
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.project.service import PRIVACY_MODES, utc_now
from presenter_core.providers.context import (
    APPLICATION_POLICY,
    MAX_TOTAL_CONTEXT_CHARS,
    MAX_TRUSTED_CONTENT_OVERHEAD_CHARS,
)
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.models import (
    TASK_CONTEXT_CLASS_ALLOWLIST,
    ProviderError,
    ReasoningRequest,
)
from presenter_core.providers.rehearsal_objection_equivalence_schema import (
    MAX_CANDIDATES_PER_RUN,
    RELATIONSHIPS,
    TASK_INSTRUCTION,
    TASK_TYPE,
    output_schema,
    validate_pair_output,
)
from presenter_core.providers.router import ReasoningRoute, ReasoningRouter
from presenter_core.providers.service import ProviderService

SIDES = ("left", "right")
MAX_RESULT_CHARS = 262144
QUESTION = "Compare only these selected concerns from distinct recorded Runs."
_SCOPE = {"project_id", "document_id", "expected_revision_id"}
_PREPARE_FIELDS = _SCOPE | {"left_finding_ids", "right_finding_ids"}
_SNAPSHOT_FIELDS = {
    "document_id",
    "revision_id",
    "session_id",
    "right_session_id",
    "left",
    "right",
    "analysis_snapshots",
    "context_sha256",
    "comparisons",
    "provider_run_id",
    "provider_id",
    "model_id",
    "privacy_mode",
    "requires_user_review",
}
_SIDE_FIELDS = {"session_id", "source_revision_id", "recording_sha256", "candidates"}
_CANDIDATE_FIELDS = {
    "finding_id",
    "analysis_id",
    "source_slide_number",
    "window_index",
    "concern_label",
    "answer_status",
    "concern_quotes",
    "answer_quotes",
}


def corrupt() -> NoReturn:
    raise CoreDomainError(
        "REHEARSAL_OBJECTION_COMPARISON_CORRUPT", "The stored objection comparison is invalid."
    )


def _sha(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _finding_ids(value: Any, side: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= MAX_CANDIDATES_PER_RUN
        or not all(_sha(item) for item in value)
        or len(set(value)) != len(value)
    ):
        raise invalid_request(
            f"Choose between 1 and {MAX_CANDIDATES_PER_RUN} distinct {side} Run candidates."
        )
    return list(value)


def provider_summary(prepared: dict[str, Any]) -> dict[str, Any]:
    """Only selected candidate excerpts and unverified labels reach the provider."""
    return {
        side: {
            "session_id": prepared[side]["session_id"],
            "source_revision_id": prepared[side]["source_revision_id"],
            "candidates": [
                {key: candidate[key] for key in sorted(_CANDIDATE_FIELDS - {"analysis_id"})}
                for candidate in prepared[side]["candidates"]
            ],
        }
        for side in SIDES
    }


def comparison_request(prepared: dict[str, Any], privacy: str) -> ReasoningRequest:
    left, right = prepared["left"], prepared["right"]
    return ReasoningRequest(
        task_type=TASK_TYPE,
        question=QUESTION,
        user_input=None,
        current_slide_summary=json.dumps(provider_summary(prepared), ensure_ascii=False),
        evidence=(),
        preferred_user_explanations=(),
        speaker_evidence=(),
        style_context={},
        conflict_metadata=(),
        style_policy="preserve_voice",
        privacy_mode=privacy,
        output_schema=output_schema(),
        latency_budget_ms=30000,
        application_policy=APPLICATION_POLICY,
        task_instruction=TASK_INSTRUCTION,
        source_ids=(prepared["document_id"],),
        presentation_revision_ids=(left["source_revision_id"], right["source_revision_id"]),
        rehearsal_session_ids=(left["session_id"], right["session_id"]),
        rehearsal_finding_ids=tuple(
            candidate["finding_id"] for side in SIDES for candidate in prepared[side]["candidates"]
        ),
    )


def comparison_context_size(request: ReasoningRequest) -> int:
    return (
        len(request.serialized_input())
        + len(APPLICATION_POLICY)
        + len(TASK_INSTRUCTION)
        + MAX_TRUSTED_CONTENT_OVERHEAD_CHARS
    )


def _side_ids(side: dict[str, Any]) -> list[str]:
    return [candidate["finding_id"] for candidate in side["candidates"]]


def validate_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _SNAPSHOT_FIELDS:
        corrupt()
    try:
        for field in ("document_id", "revision_id", "session_id", "right_session_id"):
            if PresentationSemanticService._uuid_field(value[field], field) != value[field]:
                corrupt()
        if (
            PresentationSemanticService._uuid_field(value["provider_run_id"], "provider_run_id")
            != (value["provider_run_id"])
        ):
            corrupt()
        if value["session_id"] == value["right_session_id"]:
            corrupt()
        if not _sha(value["context_sha256"]) or value["privacy_mode"] not in PRIVACY_MODES:
            corrupt()
        if value["requires_user_review"] is not True:
            corrupt()
        for field in ("provider_id", "model_id"):
            text = value[field]
            if not isinstance(text, str) or not 0 < len(text) <= 200 or "\x00" in text:
                corrupt()
        analyses = value["analysis_snapshots"]
        if not isinstance(analyses, dict) or not all(
            _sha(digest_value) for digest_value in analyses.values()
        ):
            corrupt()
        referenced = set()
        for side, session in (("left", value["session_id"]), ("right", value["right_session_id"])):
            item = value[side]
            if not isinstance(item, dict) or set(item) != _SIDE_FIELDS:
                corrupt()
            if item["session_id"] != session or not _sha(item["recording_sha256"]):
                corrupt()
            PresentationSemanticService._uuid_field(item["source_revision_id"], "revision")
            candidates = item["candidates"]
            if not isinstance(candidates, list) or not 1 <= len(candidates) <= 4:
                corrupt()
            for candidate in candidates:
                if not isinstance(candidate, dict) or set(candidate) != _CANDIDATE_FIELDS:
                    corrupt()
                if candidate["analysis_id"] not in analyses:
                    corrupt()
                referenced.add(candidate["analysis_id"])
        if referenced != set(analyses):
            corrupt()
        expected = context_digest(value)
        if expected != value["context_sha256"]:
            corrupt()
        validated = validate_pair_output(
            {"comparisons": value["comparisons"]},
            _side_ids(value["left"]),
            _side_ids(value["right"]),
        )
        if validated["comparisons"] != value["comparisons"]:
            corrupt()
    except (KeyError, TypeError, ValueError, CoreDomainError, ProviderError):
        corrupt()
    return deepcopy(value)


def context_digest(prepared: dict[str, Any]) -> str:
    keys = (
        "document_id",
        "revision_id",
        "session_id",
        "right_session_id",
        "left",
        "right",
        "analysis_snapshots",
    )
    return digest(_canonical({key: prepared[key] for key in keys}))


class RehearsalObjectionComparison:
    def __init__(
        self,
        semantics: PresentationSemanticService,
        providers: ProviderService | None = None,
        execution: ProviderExecutionService | None = None,
    ) -> None:
        self._semantics, self._providers, self._execution = semantics, providers, execution
        self._storage = semantics._storage
        self._store = RehearsalObjectionStore(semantics)

    # Preparation -----------------------------------------------------------------

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, _PREPARE_FIELDS)
        s = self._semantics
        project = s._project_id(params.get("project_id"))
        document = s._uuid_field(params.get("document_id"), "document_id")
        revision = s._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
        selected = {side: _finding_ids(params.get(f"{side}_finding_ids"), side) for side in SIDES}
        if set(selected["left"]) & set(selected["right"]):
            raise invalid_request("A candidate cannot be compared with itself.")
        with self._storage.project_database(project) as connection:
            s._require_current_presentation(connection, project, document, revision)
            owners: dict[str, str] = {}
            for identity in selected["left"] + selected["right"]:
                row = connection.execute(
                    "SELECT f.provider_run_id FROM presentation_rehearsal_objection_findings f "
                    "JOIN presentation_rehearsal_objection_analyses a "
                    "ON a.provider_run_id=f.provider_run_id "
                    "WHERE f.finding_id=? AND a.presentation_id=?",
                    (identity, document),
                ).fetchone()
                if row is None:
                    raise CoreDomainError(
                        "REHEARSAL_FINDING_NOT_FOUND",
                        "A selected objection candidate is unavailable for this deck.",
                    )
                owners[identity] = str(row["provider_run_id"])
        scope = {"project_id": project, "document_id": document, "expected_revision_id": revision}
        details = {
            analysis: self._store.read(scope | {"analysis_id": analysis})
            for analysis in sorted(set(owners.values()))
        }
        prepared: dict[str, Any] = {
            "document_id": document,
            "revision_id": revision,
            "analysis_snapshots": {
                analysis: detail["snapshot_sha256"] for analysis, detail in details.items()
            },
        }
        for side in SIDES:
            sessions = {details[owners[i]]["snapshot"]["session_id"] for i in selected[side]}
            if len(sessions) != 1:
                raise invalid_request(f"Choose {side} candidates from one ended Run.")
            candidates = []
            for identity in selected[side]:
                detail = details[owners[identity]]
                if not detail["context_current"]:
                    raise CoreDomainError(
                        "REHEARSAL_CONTEXT_CHANGED",
                        "A selected Run recording changed. Compare candidates whose "
                        "original recording is unchanged.",
                        retryable=True,
                    )
                snapshot = detail["snapshot"]
                finding = next(f for f in detail["findings"] if f["finding_id"] == identity)
                actors = {
                    utterance["utterance_id"]: utterance["actor"]
                    for utterance in snapshot["windows"][0]["utterances"]
                }
                observation = finding["observation"]
                candidates.append(
                    {
                        "finding_id": identity,
                        "analysis_id": owners[identity],
                        "source_slide_number": snapshot["source_slide_number"],
                        "window_index": snapshot["window_index"],
                        "concern_label": observation["concern"],
                        "answer_status": observation["answer_status"],
                        **{
                            field: [
                                {
                                    "utterance_id": quote["utterance_id"],
                                    "quote": quote["quote"],
                                    "recorded_actor": actors[quote["utterance_id"]],
                                }
                                for quote in observation[field]
                            ]
                            for field in ("concern_quotes", "answer_quotes")
                        },
                    }
                )
            first = details[owners[selected[side][0]]]
            prepared[side] = {
                "session_id": first["snapshot"]["session_id"],
                "source_revision_id": first["snapshot"]["source_revision_id"],
                "recording_sha256": first["recording_sha256"],
                "candidates": candidates,
            }
        if prepared["left"]["session_id"] == prepared["right"]["session_id"]:
            raise invalid_request("Choose candidates from two distinct ended Runs.")
        prepared["session_id"] = prepared["left"]["session_id"]
        prepared["right_session_id"] = prepared["right"]["session_id"]
        prepared["context_sha256"] = context_digest(prepared)
        request = comparison_request(prepared, "local_only")
        if comparison_context_size(request) > MAX_TOTAL_CONTEXT_CHARS:
            raise invalid_request("The selected candidates exceed the comparison context budget.")
        return {
            **prepared,
            "requires_user_review": True,
            "speaker_identity_verified": False,
            "asr_accuracy_verified": False,
            "recording_completeness": "unknown",
        }

    def prepare_analysis(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], None]:
        # Owned jobs add both canonical Run identities; they must match preparation.
        owned = {"session_id", "right_session_id"}
        reject_unknown_fields(params, _PREPARE_FIELDS | owned | {"expected_context_sha256"})
        fingerprint = params.get("expected_context_sha256")
        if not _sha(fingerprint):
            raise invalid_request("Prepare the exact candidate comparison before starting.")
        selection = {key: value for key, value in params.items() if key in _PREPARE_FIELDS}
        prepared = self.prepare(selection)
        if prepared["context_sha256"] != fingerprint or any(
            key in params and params[key] != prepared[key] for key in owned
        ):
            raise CoreDomainError(
                "REHEARSAL_CONTEXT_CHANGED",
                "The selected candidates changed. Prepare the comparison again.",
                retryable=True,
            )
        return selection, prepared, None

    # Execution -------------------------------------------------------------------

    def _policy(self, project: str) -> tuple[str, bool]:
        with self._storage.project_database(project) as connection:
            row = connection.execute(
                "SELECT privacy_mode,remote_reasoning_acknowledged_at FROM project WHERE id=?",
                (project,),
            ).fetchone()
        return str(row["privacy_mode"]), row["remote_reasoning_acknowledged_at"] is not None

    def analyze(
        self,
        params: dict[str, Any],
        *,
        cancellation_check: Callable[[], bool] | None = None,
        before_persist: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        if self._providers is None or self._execution is None:
            raise CoreDomainError(
                "REHEARSAL_ANALYSIS_UNAVAILABLE", "Objection comparison is unavailable."
            )
        if cancellation_check is not None and cancellation_check():
            raise CoreDomainError("PROVIDER_CANCELLED", "The comparison was cancelled.")
        selection, prepared, _ = self.prepare_analysis(params)
        project = self._semantics._project_id(params.get("project_id"))
        initial_policy = self._policy(project)
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
        request = comparison_request(prepared, initial_policy[0])
        left_ids, right_ids = _side_ids(prepared["left"]), _side_ids(prepared["right"])

        def current() -> None:
            if self._policy(project) != initial_policy:
                raise CoreDomainError(
                    "PRIVACY_POLICY_CHANGED",
                    "Project privacy changed during comparison. Review and retry.",
                    retryable=True,
                )
            if self.prepare(selection) != prepared:
                raise CoreDomainError(
                    "REHEARSAL_CONTEXT_CHANGED",
                    "A selected Run or candidate changed during comparison. Prepare again.",
                    retryable=True,
                )

        def validate(output: dict[str, Any]) -> dict[str, Any]:
            current()
            return validate_pair_output(output, left_ids, right_ids)

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
            key: prepared[key]
            for key in (
                "document_id",
                "revision_id",
                "session_id",
                "right_session_id",
                "left",
                "right",
                "analysis_snapshots",
                "context_sha256",
            )
        } | {
            "comparisons": validate_pair_output(executed.result.output, left_ids, right_ids)[
                "comparisons"
            ],
            "provider_run_id": executed.provider_run_id,
            "provider_id": provider.id,
            "model_id": provider.model_id,
            "privacy_mode": initial_policy[0],
            "requires_user_review": True,
        }

        def transaction_guard(connection: sqlite3.Connection) -> None:
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
            if cancellation_check is not None and cancellation_check():
                raise CoreDomainError(
                    "PROVIDER_CANCELLED", "The comparison was cancelled before storage."
                )
            if before_persist is not None:
                before_persist()

        return self.save(project, result, transaction_guard=transaction_guard)

    # Storage ---------------------------------------------------------------------

    @staticmethod
    def audit(connection: sqlite3.Connection, result: dict[str, Any], project: str) -> None:
        run = connection.execute(
            "SELECT * FROM provider_runs WHERE id=?", (result["provider_run_id"],)
        ).fetchone()
        if (
            run is None
            or run["status"] != "success"
            or run["task_type"] != TASK_TYPE
            or run["session_id"] != result["session_id"]
            or run["provider_id"] != result["provider_id"]
            or run["privacy_mode"] != result["privacy_mode"]
        ):
            corrupt()
        for side in SIDES:
            session = connection.execute(
                "SELECT * FROM sessions WHERE id=?", (result[side]["session_id"],)
            ).fetchone()
            if (
                session is None
                or session["mode"] != "run"
                or session["status"] == "active"
                or session["project_id"] != project
                or session["presentation_revision_id"] != result[side]["source_revision_id"]
            ):
                corrupt()
        try:
            manifest = json.loads(run["context_manifest_json"])
            packet = comparison_request(result, result["privacy_mode"])
            if (
                manifest["source_ids"] != [result["document_id"]]
                or manifest["presentation_revision_ids"]
                != sorted({result[side]["source_revision_id"] for side in SIDES})
                or manifest["rehearsal_session_ids"]
                != sorted(result[side]["session_id"] for side in SIDES)
                or manifest["rehearsal_finding_ids"]
                != sorted(i for side in SIDES for i in _side_ids(result[side]))
                or manifest["task_type"] != TASK_TYPE
                or manifest["privacy_mode"] != result["privacy_mode"]
                or not set(manifest["classes_sent"]) <= TASK_CONTEXT_CLASS_ALLOWLIST[TASK_TYPE]
                or manifest["bounded_context_chars"] != len(packet.serialized_input())
                or manifest["raw_audio_sent"] is not False
                or manifest["private_items_sent"] is not False
            ):
                corrupt()
        except (KeyError, TypeError, ValueError):
            corrupt()

    @staticmethod
    def _originals_unchanged(connection: sqlite3.Connection, result: dict[str, Any]) -> bool:
        for analysis, snapshot_sha in result["analysis_snapshots"].items():
            row = connection.execute(
                "SELECT snapshot_sha256 FROM presentation_rehearsal_objection_analyses "
                "WHERE provider_run_id=? AND presentation_id=?",
                (analysis, result["document_id"]),
            ).fetchone()
            if row is None or row["snapshot_sha256"] != snapshot_sha:
                return False
        return all(
            recording_state(connection, result[side]["session_id"])
            == result[side]["recording_sha256"]
            for side in SIDES
        )

    def save(
        self,
        project: str,
        result: dict[str, Any],
        *,
        transaction_guard: Callable[[sqlite3.Connection], None],
    ) -> dict[str, Any]:
        result = validate_snapshot(result)
        raw = _canonical(result)
        if len(raw) > MAX_RESULT_CHARS:
            raise invalid_request("This comparison exceeds its durable result limit.")
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.audit(connection, result, project)
            self._semantics._require_current_presentation(
                connection, project, result["document_id"], result["revision_id"]
            )
            transaction_guard(connection)
            if not self._originals_unchanged(connection, result):
                raise CoreDomainError(
                    "REHEARSAL_CONTEXT_CHANGED",
                    "A selected Run recording or original analysis changed before storage.",
                    retryable=True,
                )
            connection.execute(
                "INSERT INTO presentation_rehearsal_objection_comparisons "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    result["provider_run_id"],
                    result["document_id"],
                    result["session_id"],
                    result["right_session_id"],
                    result["revision_id"],
                    result["context_sha256"],
                    result["privacy_mode"],
                    raw,
                    digest(raw),
                    utc_now(),
                ),
            )
            connection.executemany(
                "INSERT INTO presentation_rehearsal_objection_comparison_candidates "
                "VALUES (?,?,?,?)",
                [
                    (result["provider_run_id"], identity, side, position)
                    for side in SIDES
                    for position, identity in enumerate(_side_ids(result[side]))
                ],
            )
            connection.commit()
        return {**result, "comparison_id": result["provider_run_id"]}

    def _parse_row(
        self, connection: sqlite3.Connection, row: sqlite3.Row, project: str
    ) -> dict[str, Any]:
        raw = row["snapshot_json"]
        if (
            not isinstance(raw, str)
            or len(raw) > MAX_RESULT_CHARS
            or digest(raw) != row["snapshot_sha256"]
        ):
            corrupt()
        try:
            result = validate_snapshot(json.loads(raw))
        except (TypeError, ValueError):
            corrupt()
        for key, field in (
            ("provider_run_id", "provider_run_id"),
            ("document_id", "presentation_id"),
            ("session_id", "left_session_id"),
            ("right_session_id", "right_session_id"),
            ("revision_id", "baseline_revision_id"),
            ("context_sha256", "context_sha256"),
            ("privacy_mode", "privacy_mode"),
        ):
            if result[key] != row[field]:
                corrupt()
        references = connection.execute(
            "SELECT finding_id,side,position "
            "FROM presentation_rehearsal_objection_comparison_candidates "
            "WHERE provider_run_id=? ORDER BY side,position",
            (result["provider_run_id"],),
        ).fetchall()
        expected = sorted(
            (side, position, identity)
            for side in SIDES
            for position, identity in enumerate(_side_ids(result[side]))
        )
        if sorted((r["side"], r["position"], r["finding_id"]) for r in references) != expected:
            corrupt()
        self.audit(connection, result, project)
        return result

    def list(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, _SCOPE | {"session_id", "offset", "limit"})
        s = self._semantics
        project = s._project_id(params.get("project_id"))
        document = s._uuid_field(params.get("document_id"), "document_id")
        revision = s._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
        offset, limit = params.get("offset", 0), params.get("limit", 20)
        if type(offset) is not int or not 0 <= offset <= 1000000:
            raise invalid_request("Choose a valid review page offset.")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise invalid_request("Choose between 1 and 20 review items per page.")
        session = params.get("session_id")
        where, values = "presentation_id=?", [document]
        if session is not None:
            session = s._uuid_field(session, "session_id")
            where += " AND (left_session_id=? OR right_session_id=?)"
            values += [session, session]
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN")
            s._require_current_presentation(connection, project, document, revision)
            total = connection.execute(
                f"SELECT COUNT(*) FROM presentation_rehearsal_objection_comparisons WHERE {where}",
                values,
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM presentation_rehearsal_objection_comparisons WHERE {where} "
                "ORDER BY created_at DESC,provider_run_id DESC LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
            items = []
            for row in rows:
                result = self._parse_row(connection, row, project)
                items.append(
                    {
                        "comparison_id": result["provider_run_id"],
                        "session_id": result["session_id"],
                        "right_session_id": result["right_session_id"],
                        "left_candidate_count": len(result["left"]["candidates"]),
                        "right_candidate_count": len(result["right"]["candidates"]),
                        "relationship_counts": {
                            name: sum(
                                item["relationship"] == name for item in result["comparisons"]
                            )
                            for name in RELATIONSHIPS
                        },
                        "provider_id": result["provider_id"],
                        "model_id": result["model_id"],
                        "created_at": row["created_at"],
                        "requires_user_review": True,
                        "requires_verified_detail": True,
                    }
                )
        return {
            "document_id": document,
            "revision_id": revision,
            "session_id": session,
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + limit < total,
            "comparisons": items,
        }

    def read(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, _SCOPE | {"comparison_id"})
        s = self._semantics
        project = s._project_id(params.get("project_id"))
        document = s._uuid_field(params.get("document_id"), "document_id")
        revision = s._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
        identity = s._uuid_field(params.get("comparison_id"), "comparison_id")
        with self._storage.project_database(project) as connection:
            s._require_current_presentation(connection, project, document, revision)
            row = connection.execute(
                "SELECT * FROM presentation_rehearsal_objection_comparisons "
                "WHERE provider_run_id=? AND presentation_id=?",
                (identity, document),
            ).fetchone()
            if row is None:
                raise CoreDomainError(
                    "REHEARSAL_FINDING_NOT_FOUND", "The objection comparison is unavailable."
                )
            result = self._parse_row(connection, row, project)
            created_at = row["created_at"]
        scope = {"project_id": project, "document_id": document, "expected_revision_id": revision}
        # Each original candidate is resolved through its own verified analysis, so
        # dispositions and adoption eligibility stay independent of this comparison.
        originals = {
            analysis: self._store.read(scope | {"analysis_id": analysis})
            for analysis in sorted(result["analysis_snapshots"])
        }
        context_current = all(
            originals[analysis]["snapshot_sha256"] == snapshot_sha
            and originals[analysis]["context_current"]
            for analysis, snapshot_sha in result["analysis_snapshots"].items()
        ) and all(
            originals[c["analysis_id"]]["recording_sha256"] == result[side]["recording_sha256"]
            for side in SIDES
            for c in result[side]["candidates"]
        )
        candidates: dict[str, dict[str, Any]] = {}
        for side in SIDES:
            for candidate in result[side]["candidates"]:
                original = originals[candidate["analysis_id"]]
                finding = next(
                    (f for f in original["findings"] if f["finding_id"] == candidate["finding_id"]),
                    None,
                )
                if finding is None:
                    corrupt()
                candidates[candidate["finding_id"]] = {
                    **deepcopy(candidate),
                    "side": side,
                    "session_id": result[side]["session_id"],
                    "disposition": finding["disposition"],
                    "applied_revision_id": finding["applied_revision_id"],
                    "can_adopt": finding["can_adopt"],
                    "current_slide_number": original["current_slide_number"],
                    "context_current": original["context_current"],
                }
        with self._storage.project_database(project) as connection:
            s._require_current_presentation(connection, project, document, revision)
            latest = connection.execute(
                "SELECT snapshot_sha256 FROM presentation_rehearsal_objection_comparisons "
                "WHERE provider_run_id=? AND presentation_id=?",
                (identity, document),
            ).fetchone()
            if latest is None or latest["snapshot_sha256"] != row["snapshot_sha256"]:
                corrupt()
        return {
            "comparison_id": identity,
            "revision_id": revision,
            "baseline_revision_id": result["revision_id"],
            "session_id": result["session_id"],
            "right_session_id": result["right_session_id"],
            "provider_id": result["provider_id"],
            "model_id": result["model_id"],
            "privacy_mode": result["privacy_mode"],
            "created_at": created_at,
            "context_current": context_current,
            "left_finding_ids": _side_ids(result["left"]),
            "right_finding_ids": _side_ids(result["right"]),
            "candidates": candidates,
            "comparisons": deepcopy(result["comparisons"]),
            "interpretation_verified": False,
            "establishes_absence": False,
            "speaker_identity_verified": False,
            "asr_accuracy_verified": False,
            "requires_user_review": True,
        }
