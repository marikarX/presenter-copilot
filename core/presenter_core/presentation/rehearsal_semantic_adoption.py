"""Explicit semantic hint adoption with same-transaction recording/disposition guards."""

import json
import sqlite3
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request
from presenter_core.presentation.claims import digest
from presenter_core.presentation.rehearsal_analysis_store import (
    RehearsalAnalysisStore,
    corrupt,
    recording_state,
    snapshot_digest,
)
from presenter_core.presentation.semantics import PresentationSemanticService


class RehearsalSemanticAdoption:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics
        self._store = RehearsalAnalysisStore(semantics)

    def resolve(
        self, params: dict[str, Any], *, allow_reviewed: bool, require_context: bool
    ) -> dict[str, Any] | None:
        s = self._semantics
        project = s._project_id(params.get("project_id"))
        document = s._uuid_field(params.get("document_id"), "document_id")
        with s._storage.project_database(project) as connection:
            exists = connection.execute(
                "SELECT 1 FROM presentation_rehearsal_analyses "
                "WHERE finding_id=? AND presentation_id=?",
                (params.get("finding_id"), document),
            ).fetchone()
        if exists is None:
            return None
        item = self._store.read(
            {
                key: params[key]
                for key in ("project_id", "document_id", "expected_revision_id", "finding_id")
            }
        )
        if item["disposition"] != "unreviewed" and not allow_reviewed:
            raise CoreDomainError(
                "REHEARSAL_FINDING_REVIEWED", "This finding was already reviewed."
            )
        if require_context and not item["context_current"]:
            raise CoreDomainError(
                "REHEARSAL_CONTEXT_CHANGED",
                "The recording changed. Analyze and review the current context again.",
            )
        if require_context and item["current_slide_number"] is None:
            raise CoreDomainError(
                "REHEARSAL_SLIDE_REMOVED", "This slide is absent from the current revision."
            )
        return self.finding(item)

    @staticmethod
    def finding(item: dict[str, Any]) -> dict[str, Any]:
        snapshot = item["snapshot"]
        hint = snapshot["hint"]
        return {
            "finding_id": item["finding_id"],
            "kind": "semantic_coverage",
            "session_id": snapshot["session_id"],
            "source_id": item["analysis_id"],
            "source_revision_id": snapshot["source_revision_id"],
            "source_revision_number": item["source_revision_number"],
            "source_slide_number": snapshot["source_slide_number"],
            "slide_id": snapshot["slide_id"],
            "current_slide_number": item["current_slide_number"],
            "quote": snapshot["point"]["quote"],
            "object_id": snapshot["point"]["object_id"],
            "label": "Unverified window coverage hint",
            "disposition": item["disposition"],
            "applied_revision_id": item["applied_revision_id"],
            "current_span_status": item["current_span_status"],
            "context_current": item["context_current"],
            "semantic_review": {
                "status": hint["status"],
                "reason": hint["reason"],
                "window_index": snapshot["window_index"],
                "total_windows": snapshot["total_windows"],
                "provider_id": snapshot["provider_id"],
                "model_id": snapshot["model_id"],
                "provider_run_id": snapshot["provider_run_id"],
                "source_kind": snapshot["point"]["source_kind"],
                "recording_completeness": "unknown",
                "recorded_speech_included": False,
                "utterance_references": [
                    {"utterance_id": quote["utterance_id"], "quote_sha256": digest(quote["quote"])}
                    for quote in hint["quotes"]
                ],
                "provenance": "unverified_model_hint_from_one_recorded_window",
            },
            "_semantic_guard": {
                "snapshot_sha256": item["snapshot_sha256"],
                "recording_sha256": item["recording_sha256"],
                "can_adopt": item["can_adopt"],
            },
        }

    @staticmethod
    def require_text_target(finding: dict[str, Any], object_id: Any) -> None:
        if finding.get("kind") == "semantic_coverage" and object_id != finding["object_id"]:
            raise invalid_request("The semantic finding must target its original native object.")

    def guard(
        self,
        connection: sqlite3.Connection,
        project: str,
        document: str,
        baseline: str,
        finding: dict[str, Any],
        applied: str | None,
        *,
        require_context: bool,
    ) -> None:
        if finding.get("kind") != "semantic_coverage":
            return
        token = finding["_semantic_guard"]
        row = connection.execute(
            "SELECT * FROM presentation_rehearsal_analyses "
            "WHERE finding_id=? AND presentation_id=?",
            (finding["finding_id"], document),
        ).fetchone()
        if (
            row is None
            or row["snapshot_sha256"] != token["snapshot_sha256"]
            or (
                digest(row["snapshot_json"]) != token["snapshot_sha256"]
                or row["provider_run_id"] != finding["source_id"]
                or row["session_id"] != finding["session_id"]
                or row["source_revision_id"] != finding["source_revision_id"]
            )
        ):
            corrupt()
        snapshot = json.loads(row["snapshot_json"])
        self._store._audit(connection, snapshot, project)
        expected_head = applied or baseline
        self._semantics._require_current_presentation(connection, project, document, expected_head)
        if applied:
            parent = connection.execute(
                "SELECT parent_revision_id FROM presentation_revisions "
                "WHERE id=? AND presentation_id=?",
                (applied, document),
            ).fetchone()
            if parent is None or parent[0] != baseline:
                raise CoreDomainError(
                    "PRESENTATION_REVISION_CONFLICT", "The edit baseline changed."
                )
        reviewed = connection.execute(
            "SELECT disposition FROM presentation_rehearsal_reviews WHERE finding_id=?",
            (finding["finding_id"],),
        ).fetchone()
        actual = reviewed[0] if reviewed else "unreviewed"
        if actual != finding["disposition"]:
            raise CoreDomainError("REHEARSAL_FINDING_REVIEWED", "The finding review changed.")
        if require_context and (
            not token["can_adopt"]
            or (recording_state(connection, finding["session_id"]) != token["recording_sha256"])
        ):
            raise CoreDomainError("REHEARSAL_CONTEXT_CHANGED", "The recording changed before Save.")
        for revision in {finding["source_revision_id"], baseline}:
            native = connection.execute(
                "SELECT local_snapshot_path,sha256,byte_size FROM presentation_revisions "
                "WHERE id=? AND presentation_id=?",
                (revision, document),
            ).fetchone()
            if native is None:
                corrupt()
            path = self._semantics._storage.paths.snapshot_path(
                project, native["local_snapshot_path"], require_exists=True
            )
            if (
                path.stat().st_size != native["byte_size"]
                or snapshot_digest(path) != native["sha256"]
            ):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED", "The native source changed before Save."
                )
