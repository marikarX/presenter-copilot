"""Immutable audited objection windows and independently reviewable candidates."""

import json
import sqlite3
from collections.abc import Callable
from copy import deepcopy
from typing import Any, NoReturn

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.claims import digest
from presenter_core.presentation.rehearsal_analysis_store import recording_state, snapshot_digest
from presenter_core.presentation.rehearsal_objection_context import (
    SOURCE_FIELDS,
    RehearsalObjectionContext,
    objection_context_size,
    objection_request,
)
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.project.service import PRIVACY_MODES, utc_now
from presenter_core.providers.models import TASK_CONTEXT_CLASS_ALLOWLIST
from presenter_core.providers.rehearsal_objection_schema import TASK_TYPE, validate_window_output

MAX_RESULT_CHARS = 131072
CONTEXT_FIELDS = frozenset(SOURCE_FIELDS) | {
    "revision_id",
    "current_slide_number",
    "context_sha256",
    "recording_sha256",
    "total_utterances",
    "total_windows",
    "actor_counts",
    "unmapped_session_utterances",
    "offset",
    "limit",
    "has_more",
    "windows",
    "requires_user_review",
    "has_recorded_speech",
    "recording_completeness",
    "speaker_identity_verified",
    "asr_accuracy_verified",
}
SNAPSHOT_FIELDS = CONTEXT_FIELDS | {
    "window_index",
    "hint",
    "provider_run_id",
    "provider_id",
    "model_id",
    "privacy_mode",
}
ACTORS = frozenset({"user", "unknown_audience", "ai_coach", "audience_profile"})


def corrupt() -> NoReturn:
    raise CoreDomainError(
        "REHEARSAL_OBJECTION_CORRUPT", "The stored objection analysis is invalid."
    )


def sha(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def candidate_id(run: str, index: int, observation: dict[str, Any]) -> str:
    canonical = json.dumps(observation, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return digest(f"{TASK_TYPE}\0{run}\0{index}\0{digest(canonical)}")


def validate_snapshot(value: Any) -> dict[str, Any]:
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
        for field in ("source_sha256", "context_sha256", "recording_sha256"):
            if not sha(value[field]):
                corrupt()
        for field in ("provider_id", "model_id"):
            text = value[field]
            if not isinstance(text, str) or not 0 < len(text) <= 200 or "\x00" in text:
                corrupt()
        if value["privacy_mode"] not in PRIVACY_MODES:
            corrupt()
        for field in (
            "source_slide_number",
            "total_utterances",
            "total_windows",
            "unmapped_session_utterances",
            "offset",
            "limit",
            "window_index",
        ):
            if type(value[field]) is not int or not 0 <= value[field] <= 10000:
                corrupt()
        if (
            not 1 <= value["source_slide_number"] <= 5000
            or not 1 <= value["total_windows"] <= value["total_utterances"]
            or value["total_utterances"] > value["total_windows"] * 4
            or not 0 <= value["window_index"] < value["total_windows"]
            or value["offset"] != value["window_index"]
            or value["limit"] != 1
        ):
            corrupt()
        if value["current_slide_number"] is not None and (
            type(value["current_slide_number"]) is not int
            or not 1 <= value["current_slide_number"] <= 5000
        ):
            corrupt()
        if type(value["has_more"]) is not bool or value["has_more"] != (
            value["window_index"] + 1 < value["total_windows"]
        ):
            corrupt()
        for field in ("requires_user_review", "has_recorded_speech"):
            if value[field] is not True:
                corrupt()
        if (
            value["speaker_identity_verified"] is not False
            or value["asr_accuracy_verified"] is not False
            or value["recording_completeness"] != "unknown"
        ):
            corrupt()
        actors = value["actor_counts"]
        if (
            not isinstance(actors, dict)
            or not set(actors) <= ACTORS
            or any(type(n) is not int or not 0 < n <= 10000 for n in actors.values())
            or sum(actors.values()) != value["total_utterances"]
        ):
            corrupt()
        windows = value["windows"]
        if not isinstance(windows, list) or len(windows) != 1:
            corrupt()
        window = windows[0]
        if (
            not isinstance(window, dict)
            or set(window) != {"index", "utterances", "serialized_context_chars"}
            or type(window["index"]) is not int
            or window["index"] != value["window_index"]
            or type(window["serialized_context_chars"]) is not int
        ):
            corrupt()
        speech = window["utterances"]
        if not isinstance(speech, list) or not 1 <= len(speech) <= 4:
            corrupt()
        identities = set()
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
            if (
                identity != item["utterance_id"]
                or identity in identities
                or item["actor"] not in ACTORS
            ):
                corrupt()
            identities.add(identity)
            text = item["text"]
            if (
                not isinstance(text, str)
                or not text.strip()
                or "\x00" in text
                or len(text) > 4000
                or digest(text) != item["sha256"]
            ):
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
        request = objection_request(
            {k: value[k] for k in SOURCE_FIELDS}, speech, value["privacy_mode"]
        )
        actual = objection_context_size(request)
        if not 0 < actual <= 12000 or actual != window["serialized_context_chars"]:
            corrupt()
        validate_window_output(value["hint"], speech)
    except (KeyError, TypeError, ValueError, CoreDomainError):
        corrupt()
    return deepcopy(value)


class RehearsalObjectionStore:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics, self._storage = semantics, semantics._storage
        self._context = RehearsalObjectionContext(semantics)

    @staticmethod
    def audit(connection: sqlite3.Connection, result: dict[str, Any], project: str) -> None:
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
            or run["task_type"] != TASK_TYPE
            or run["session_id"] != result["session_id"]
            or run["provider_id"] != result["provider_id"]
            or run["privacy_mode"] != result["privacy_mode"]
            or session["mode"] != "run"
            or session["status"] == "active"
            or session["project_id"] != project
            or session["presentation_revision_id"] != result["source_revision_id"]
        ):
            corrupt()
        try:
            manifest = json.loads(run["context_manifest_json"])
            packet = objection_request(
                {k: result[k] for k in SOURCE_FIELDS},
                result["windows"][0]["utterances"],
                result["privacy_mode"],
            )
            if (
                manifest["source_ids"] != [result["document_id"]]
                or manifest["presentation_revision_ids"] != [result["source_revision_id"]]
                or manifest["rehearsal_session_ids"] != [result["session_id"]]
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

    def native_guard(
        self, connection: sqlite3.Connection, project: str, result: dict[str, Any]
    ) -> None:
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
            if path.stat().st_size != row["byte_size"] or snapshot_digest(path) != row["sha256"]:
                raise CoreDomainError("SOURCE_SNAPSHOT_CHANGED", "The native snapshot changed.")
            if (
                revision == result["source_revision_id"]
                and row["sha256"] != result["source_sha256"]
            ):
                corrupt()

    def save(
        self,
        project: str,
        result: dict[str, Any],
        *,
        transaction_guard: Callable[[sqlite3.Connection], None],
    ) -> dict[str, Any]:
        result = validate_snapshot(result)
        prepared = self._context.prepare(
            {
                "project_id": project,
                "document_id": result["document_id"],
                "expected_revision_id": result["revision_id"],
                "session_id": result["session_id"],
                "slide_id": result["slide_id"],
                "offset": result["window_index"],
                "limit": 1,
            }
        )
        if prepared != {k: result[k] for k in CONTEXT_FIELDS}:
            raise CoreDomainError(
                "REHEARSAL_CONTEXT_CHANGED", "Prepare the current recorded context again."
            )
        raw = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(raw) > MAX_RESULT_CHARS:
            raise invalid_request("This objection analysis exceeds its durable result limit.")
        findings = [
            candidate_id(result["provider_run_id"], i, item)
            for i, item in enumerate(result["hint"]["observations"])
        ]
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.audit(connection, result, project)
            self._semantics._require_current_presentation(
                connection, project, result["document_id"], result["revision_id"]
            )
            transaction_guard(connection)
            if recording_state(connection, result["session_id"]) != result["recording_sha256"]:
                raise CoreDomainError(
                    "REHEARSAL_CONTEXT_CHANGED", "The recording changed before storage."
                )
            self.native_guard(connection, project, result)
            connection.execute(
                "INSERT INTO presentation_rehearsal_objection_analyses "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    result["provider_run_id"],
                    result["document_id"],
                    result["session_id"],
                    result["source_revision_id"],
                    result["revision_id"],
                    result["context_sha256"],
                    result["recording_sha256"],
                    result["window_index"],
                    result["privacy_mode"],
                    raw,
                    digest(raw),
                    utc_now(),
                ),
            )
            connection.executemany(
                "INSERT INTO presentation_rehearsal_objection_findings VALUES (?,?,?)",
                [(identity, result["provider_run_id"], i) for i, identity in enumerate(findings)],
            )
            connection.commit()
        return {**result, "analysis_id": result["provider_run_id"], "finding_ids": findings}

    def parse_row(
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
            ("session_id", "session_id"),
            ("source_revision_id", "source_revision_id"),
            ("revision_id", "baseline_revision_id"),
            ("context_sha256", "context_sha256"),
            ("recording_sha256", "recording_sha256"),
            ("window_index", "window_index"),
            ("privacy_mode", "privacy_mode"),
        ):
            if result[key] != row[field]:
                corrupt()
        self.audit(connection, result, project)
        self.candidates(connection, result)
        return result

    @staticmethod
    def candidates(connection: sqlite3.Connection, result: dict[str, Any]) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT f.finding_id,f.candidate_index,r.disposition,r.applied_revision_id,"
            "r.presentation_id AS review_document,r.session_id AS review_session,"
            "r.source_revision_id AS review_source "
            "FROM presentation_rehearsal_objection_findings f "
            "LEFT JOIN presentation_rehearsal_reviews r ON r.finding_id=f.finding_id "
            "WHERE f.provider_run_id=? ORDER BY f.candidate_index",
            (result["provider_run_id"],),
        ).fetchall()
        observations = result["hint"]["observations"]
        if len(rows) != len(observations):
            corrupt()
        findings = []
        for index, (row, observation) in enumerate(zip(rows, observations, strict=True)):
            if row["candidate_index"] != index or row["finding_id"] != candidate_id(
                result["provider_run_id"], index, observation
            ):
                corrupt()
            if row["disposition"] is not None and (
                row["review_document"] != result["document_id"]
                or row["review_session"] != result["session_id"]
                or row["review_source"] != result["source_revision_id"]
            ):
                corrupt()
            findings.append(
                {
                    "finding_id": row["finding_id"],
                    "candidate_index": index,
                    "observation": deepcopy(observation),
                    "disposition": row["disposition"] or "unreviewed",
                    "applied_revision_id": row["applied_revision_id"],
                }
            )
        return findings

    def read(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "document_id", "expected_revision_id", "analysis_id"}
        )
        s = self._semantics
        project = s._project_id(params.get("project_id"))
        document = s._uuid_field(params.get("document_id"), "document_id")
        revision = s._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
        identity = s._uuid_field(params.get("analysis_id"), "analysis_id")
        with self._storage.project_database(project) as connection:
            s._require_current_presentation(connection, project, document, revision)
            row = connection.execute(
                "SELECT * FROM presentation_rehearsal_objection_analyses "
                "WHERE provider_run_id=? AND presentation_id=?",
                (identity, document),
            ).fetchone()
            if row is None:
                raise CoreDomainError(
                    "REHEARSAL_FINDING_NOT_FOUND", "The objection analysis is unavailable."
                )
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
        original_slide = next(
            (slide for slide in original.slides if slide.slide_id == result["slide_id"]), None
        )
        if (
            original.source_sha256 != result["source_sha256"]
            or original_slide is None
            or original_slide.ordinal != result["source_slide_number"]
        ):
            corrupt()
        current = s._workspace_sources.read_revision_inventory(
            {
                "project_id": project,
                "document_id": document,
                "revision_id": revision,
            }
        )[-1]
        current_slide = next(
            (slide for slide in current.slides if slide.slide_id == result["slide_id"]), None
        )
        fresh = before_recording == result["recording_sha256"]
        if fresh:
            prepared = self._context.prepare(
                {
                    "project_id": project,
                    "document_id": document,
                    "expected_revision_id": revision,
                    "session_id": result["session_id"],
                    "slide_id": result["slide_id"],
                    "offset": result["window_index"],
                    "limit": 1,
                },
                window_privacy_mode=result["privacy_mode"],
            )
            # Current ordinal/head can change while original recorded context stays valid.
            comparable = CONTEXT_FIELDS - {"revision_id", "current_slide_number"}
            if any(prepared[key] != result[key] for key in comparable):
                corrupt()
        with self._storage.project_database(project) as connection:
            s._require_current_presentation(connection, project, document, revision)
            latest = connection.execute(
                "SELECT * FROM presentation_rehearsal_objection_analyses "
                "WHERE provider_run_id=? AND presentation_id=?",
                (identity, document),
            ).fetchone()
            if latest is None or latest["snapshot_sha256"] != row["snapshot_sha256"]:
                corrupt()
            self.parse_row(connection, latest, project)
            after_recording = recording_state(connection, result["session_id"])
            fresh = fresh and after_recording == before_recording
            findings = self.candidates(connection, result)
        for finding in findings:
            finding["can_adopt"] = (
                fresh and current_slide is not None and finding["disposition"] == "unreviewed"
            )
        return {
            "analysis_id": identity,
            "snapshot": result,
            "source_revision_number": source_number,
            "snapshot_sha256": row["snapshot_sha256"],
            "recording_sha256": after_recording,
            "revision_id": revision,
            "current_slide_number": current_slide.ordinal if current_slide else None,
            "context_current": fresh,
            "findings": findings,
            "requires_user_review": True,
        }
