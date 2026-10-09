"""Immutable semantic rehearsal results, distinct from inference audits and adoption."""

import hashlib
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.limits import MAX_RUN_UTTERANCES_PER_SESSION
from presenter_core.presentation.claims import digest
from presenter_core.presentation.rehearsal_semantic_context import RehearsalSemanticContext
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.project.service import utc_now
from presenter_core.providers.rehearsal_coverage_schema import TASK_TYPE, validate_window_output

MAX_RESULT_CHARS = 65536
SNAPSHOT_FIELDS = frozenset(
    {
        "document_id",
        "session_id",
        "source_revision_id",
        "source_sha256",
        "slide_id",
        "source_slide_number",
        "revision_id",
        "point",
        "current_slide_number",
        "current_span_status",
        "context_sha256",
        "total_utterances",
        "total_windows",
        "unmapped_session_utterances",
        "excluded_actor_utterances",
        "offset",
        "limit",
        "has_more",
        "windows",
        "requires_user_review",
        "has_recorded_speech",
        "recording_completeness",
        "speaker_identity_verified",
        "asr_accuracy_verified",
        "window_index",
        "hint",
        "provider_run_id",
        "provider_id",
        "model_id",
    }
)
SOURCE_FIELDS = (
    "document_id",
    "session_id",
    "source_revision_id",
    "source_sha256",
    "slide_id",
    "source_slide_number",
)


def snapshot_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def finding_id(run_id: str) -> str:
    return digest(f"semantic_rehearsal_coverage\0{run_id}")


def recording_state(connection: sqlite3.Connection, session: str) -> str:
    """Transaction-compatible signature of all final speech and owning Run state."""
    owner = connection.execute(
        "SELECT id,project_id,presentation_revision_id,mode,status FROM sessions WHERE id=?",
        (session,),
    ).fetchone()
    rows = connection.execute(
        "SELECT id,text,actor,start_ms,end_ms,slide_ordinal FROM utterances "
        "WHERE session_id=? AND is_final=1 ORDER BY COALESCE(start_ms,2147483647),id LIMIT ?",
        (session, MAX_RUN_UTTERANCES_PER_SESSION + 1),
    ).fetchall()
    return digest(
        json.dumps(
            {"session": list(owner) if owner else None, "speech": [list(row) for row in rows]},
            ensure_ascii=False,
        )
    )


def corrupt() -> NoReturn:
    raise CoreDomainError("REHEARSAL_ANALYSIS_CORRUPT", "The stored rehearsal analysis is invalid.")


def _sha(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def validate_snapshot(value: Any) -> dict[str, Any]:
    """Strict shape and quote authority for the immutable stored window."""
    if not isinstance(value, dict) or set(value) != SNAPSHOT_FIELDS:
        corrupt()
    try:
        for field in (
            "document_id",
            "session_id",
            "source_revision_id",
            "slide_id",
            "revision_id",
            "provider_run_id",
        ):
            if PresentationSemanticService._uuid_field(value[field], field) != value[field]:
                corrupt()
        for field in ("source_sha256", "context_sha256"):
            if not _sha(value[field]):
                corrupt()
        for field in ("provider_id", "model_id"):
            if not isinstance(value[field], str) or not 0 < len(value[field]) <= 200:
                corrupt()
        for field in (
            "source_slide_number",
            "total_utterances",
            "total_windows",
            "unmapped_session_utterances",
            "excluded_actor_utterances",
            "window_index",
            "offset",
            "limit",
        ):
            if type(value[field]) is not int or not 0 <= value[field] <= 10000:
                corrupt()
        if not 1 <= value["source_slide_number"] <= 5000 or not value["total_windows"]:
            corrupt()
        if not value["total_utterances"] or value["window_index"] >= value["total_windows"]:
            corrupt()
        if value["offset"] != value["window_index"] or value["limit"] != 1:
            corrupt()
        if value["current_slide_number"] is not None and (
            type(value["current_slide_number"]) is not int
            or not 1 <= value["current_slide_number"] <= 5000
        ):
            corrupt()
        if value["current_span_status"] not in {"unchanged", "changed", "missing"}:
            corrupt()
        for field in ("requires_user_review", "has_recorded_speech"):
            if value[field] is not True:
                corrupt()
        for field in ("speaker_identity_verified", "asr_accuracy_verified"):
            if value[field] is not False:
                corrupt()
        if value["recording_completeness"] != "unknown" or type(value["has_more"]) is not bool:
            corrupt()
        point = value["point"]
        if not isinstance(point, dict) or set(point) != {
            "object_id",
            "quote",
            "source_kind",
            "object_sha256",
            "quote_sha256",
        }:
            corrupt()
        PresentationSemanticService._uuid_field(point["object_id"], "object_id")
        if point["source_kind"] not in {"native_text", "native_table_cells", "native_chart_cache"}:
            corrupt()
        if not isinstance(point["quote"], str) or not 0 < len(point["quote"]) <= 2000:
            corrupt()
        if not _sha(point["object_sha256"]) or point["quote_sha256"] != digest(point["quote"]):
            corrupt()
        windows = value["windows"]
        if not isinstance(windows, list) or len(windows) != 1:
            corrupt()
        window = windows[0]
        if (
            not isinstance(window, dict)
            or set(window) != {"index", "utterances", "serialized_context_chars"}
            or window["index"] != value["window_index"]
        ):
            corrupt()
        if (
            type(window["serialized_context_chars"]) is not int
            or not 0 < window["serialized_context_chars"] <= 12000
        ):
            corrupt()
        speech = window["utterances"]
        if not isinstance(speech, list) or not 1 <= len(speech) <= 4:
            corrupt()
        ids = set()
        for item in speech:
            if not isinstance(item, dict) or set(item) != {
                "utterance_id",
                "text",
                "sha256",
                "actor",
                "start_ms",
                "end_ms",
            }:
                corrupt()
            identity = PresentationSemanticService._uuid_field(item["utterance_id"], "utterance_id")
            if identity in ids or item["actor"] != "user":
                corrupt()
            ids.add(identity)
            if not isinstance(item["text"], str) or not 0 < len(item["text"]) <= 4000:
                corrupt()
            if item["sha256"] != digest(item["text"]):
                corrupt()
            for field in ("start_ms", "end_ms"):
                if item[field] is not None and (type(item[field]) is not int or item[field] < 0):
                    corrupt()
            if (
                item["start_ms"] is not None
                and item["end_ms"] is not None
                and item["end_ms"] < item["start_ms"]
            ):
                corrupt()
        validate_window_output(value["hint"], speech)
    except (KeyError, TypeError, ValueError, CoreDomainError) as error:
        if isinstance(error, CoreDomainError) and error.code == "REHEARSAL_ANALYSIS_CORRUPT":
            raise
        corrupt()
    return value


class RehearsalAnalysisStore:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics
        self._storage = semantics._storage

    @staticmethod
    def _audit(connection: sqlite3.Connection, result: dict[str, Any], project: str) -> None:
        run = connection.execute(
            "SELECT * FROM provider_runs WHERE id=?", (result["provider_run_id"],)
        ).fetchone()
        session = connection.execute(
            "SELECT * FROM sessions WHERE id=?", (result["session_id"],)
        ).fetchone()
        if (
            run is None
            or session is None
            or run["status"] != "success"
            or (
                run["task_type"] != TASK_TYPE
                or run["session_id"] != result["session_id"]
                or run["provider_id"] != result["provider_id"]
                or session["mode"] != "run"
                or session["status"] == "active"
                or session["presentation_revision_id"] != result["source_revision_id"]
                or session["project_id"] != project
            )
        ):
            corrupt()
        try:
            manifest = json.loads(run["context_manifest_json"])
            if manifest["source_ids"] != [result["document_id"]] or (
                manifest["presentation_revision_ids"] != [result["source_revision_id"]]
                or manifest["rehearsal_session_ids"] != [result["session_id"]]
                or manifest["task_type"] != TASK_TYPE
            ):
                corrupt()
        except (KeyError, TypeError, ValueError):
            corrupt()

    def save(
        self,
        project: str,
        result: dict[str, Any],
        *,
        transaction_guard: Callable[[sqlite3.Connection], None],
    ) -> dict[str, Any]:
        validate_snapshot(result)
        raw = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(raw) > MAX_RESULT_CHARS:
            raise invalid_request("This analysis exceeds its durable result limit.")
        identity = finding_id(result["provider_run_id"])
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._audit(connection, result, project)
            self._semantics._require_current_presentation(
                connection, project, result["document_id"], result["revision_id"]
            )
            transaction_guard(connection)
            # Recheck both managed native snapshots under the database write lock.
            for revision in {result["source_revision_id"], result["revision_id"]}:
                row = connection.execute(
                    "SELECT local_snapshot_path,sha256,byte_size FROM presentation_revisions "
                    "WHERE id=? AND presentation_id=?",
                    (revision, result["document_id"]),
                ).fetchone()
                if row is None:
                    corrupt()
                path = self._storage.paths.snapshot_path(
                    project, row["local_snapshot_path"], require_exists=True
                )
                if (
                    path.stat().st_size != row["byte_size"]
                    or snapshot_digest(path) != row["sha256"]
                ):
                    raise CoreDomainError("SOURCE_SNAPSHOT_CHANGED", "The native snapshot changed.")
            connection.execute(
                "INSERT INTO presentation_rehearsal_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    result["provider_run_id"],
                    identity,
                    result["document_id"],
                    result["session_id"],
                    result["source_revision_id"],
                    result["revision_id"],
                    result["context_sha256"],
                    result["window_index"],
                    raw,
                    digest(raw),
                    utc_now(),
                ),
            )
            connection.commit()
        return {**result, "analysis_id": result["provider_run_id"], "finding_id": identity}

    def parse_row(
        self, connection: sqlite3.Connection, row: sqlite3.Row, project: str
    ) -> dict[str, Any]:
        raw = row["snapshot_json"]
        if len(raw) > MAX_RESULT_CHARS or digest(raw) != row["snapshot_sha256"]:
            corrupt()
        try:
            result = validate_snapshot(json.loads(raw))
        except (ValueError, TypeError):
            corrupt()
        for key, field in (
            ("provider_run_id", "provider_run_id"),
            ("document_id", "presentation_id"),
            ("session_id", "session_id"),
            ("source_revision_id", "source_revision_id"),
            ("revision_id", "baseline_revision_id"),
            ("context_sha256", "context_sha256"),
            ("window_index", "window_index"),
        ):
            if result[key] != row[field]:
                corrupt()
        if finding_id(result["provider_run_id"]) != row["finding_id"]:
            corrupt()
        self._audit(connection, result, project)
        return result

    def read(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "document_id", "expected_revision_id", "finding_id"}
        )
        s = self._semantics
        project = s._project_id(params.get("project_id"))
        document = s._uuid_field(params.get("document_id"), "document_id")
        revision = s._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
        identity = params.get("finding_id")
        if not _sha(identity):
            raise invalid_request("Choose a durable rehearsal finding.")
        with self._storage.project_database(project) as connection:
            s._require_current_presentation(connection, project, document, revision)
            row = connection.execute(
                "SELECT a.*,r.disposition,r.applied_revision_id "
                "FROM presentation_rehearsal_analyses a "
                "LEFT JOIN presentation_rehearsal_reviews r ON r.finding_id=a.finding_id "
                "WHERE a.finding_id=? AND a.presentation_id=?",
                (identity, document),
            ).fetchone()
            if row is None:
                raise CoreDomainError("REHEARSAL_FINDING_NOT_FOUND", "The analysis is unavailable.")
            result = self.parse_row(connection, row, project)
            before_recording = recording_state(connection, result["session_id"])
            source_number = connection.execute(
                "SELECT revision_number FROM presentation_revisions "
                "WHERE id=? AND presentation_id=?",
                (result["source_revision_id"], document),
            ).fetchone()[0]
        original = s._workspace_sources.read_revision_inventory(
            {
                "project_id": project,
                "document_id": document,
                "revision_id": result["source_revision_id"],
            },
            current_only=False,
        )[-1]
        slide = next(
            (item for item in original.slides if item.slide_id == result["slide_id"]), None
        )
        if (
            original.source_sha256 != result["source_sha256"]
            or slide is None
            or slide.ordinal != result["source_slide_number"]
        ):
            corrupt()
        targets = cast(
            list[dict[str, Any]],
            original.text_targets(slide.ordinal, limit=len(slide.objects))["semantic_targets"],
        )
        target = next(
            (item for item in targets if item["object_id"] == result["point"]["object_id"]), None
        )
        point = result["point"]
        if (
            target is None
            or target["source_kind"] != point["source_kind"]
            or digest(target["decision_text"]) != point["object_sha256"]
        ):
            corrupt()
        text, quote = target["decision_text"], point["quote"]
        if text.find(quote) < 0 or text.find(quote, text.find(quote) + 1) >= 0:
            corrupt()
        current = RehearsalSemanticContext(s).prepare(
            {
                "project_id": project,
                "document_id": document,
                "expected_revision_id": revision,
                "session_id": result["session_id"],
                "slide_id": result["slide_id"],
                "object_id": point["object_id"],
                "quote": quote,
                "offset": result["window_index"],
                "limit": 1,
            }
        )
        fresh = current["context_sha256"] == result["context_sha256"]
        if fresh and (
            not current["windows"]
            or (current["windows"][0]["utterances"] != result["windows"][0]["utterances"])
        ):
            corrupt()
        with self._storage.project_database(project) as connection:
            s._require_current_presentation(connection, project, document, revision)
            after_recording = recording_state(connection, result["session_id"])
            fresh = fresh and after_recording == before_recording
        return {
            "analysis_id": result["provider_run_id"],
            "finding_id": identity,
            "snapshot": result,
            "source_revision_number": source_number,
            "snapshot_sha256": row["snapshot_sha256"],
            "recording_sha256": after_recording,
            "revision_id": revision,
            "context_current": fresh,
            "current_slide_number": current["current_slide_number"],
            "current_span_status": current["current_span_status"],
            "disposition": row["disposition"] or "unreviewed",
            "applied_revision_id": row["applied_revision_id"],
            "can_adopt": fresh
            and current["current_slide_number"] is not None
            and row["disposition"] is None,
            "requires_user_review": True,
        }
