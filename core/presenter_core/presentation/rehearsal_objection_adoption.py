"""Candidate-specific rehearsal objection adoption with atomic native Save guards."""

import sqlite3
from typing import Any

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.claims import digest
from presenter_core.presentation.rehearsal_analysis_store import recording_state
from presenter_core.presentation.rehearsal_objection_store import RehearsalObjectionStore, corrupt
from presenter_core.presentation.semantics import PresentationSemanticService


class RehearsalObjectionAdoption:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics
        self._store = RehearsalObjectionStore(semantics)

    def resolve(
        self, params: dict[str, Any], *, allow_reviewed: bool, require_context: bool
    ) -> dict[str, Any] | None:
        s = self._semantics
        project = s._project_id(params.get("project_id"))
        document = s._uuid_field(params.get("document_id"), "document_id")
        with s._storage.project_database(project) as connection:
            row = connection.execute(
                "SELECT f.provider_run_id FROM presentation_rehearsal_objection_findings f "
                "JOIN presentation_rehearsal_objection_analyses a "
                "ON a.provider_run_id=f.provider_run_id "
                "WHERE f.finding_id=? AND a.presentation_id=?",
                (params.get("finding_id"), document),
            ).fetchone()
        if row is None:
            return None
        item = self._store.read(
            {key: params[key] for key in ("project_id", "document_id", "expected_revision_id")}
            | {"analysis_id": row["provider_run_id"]}
        )
        candidate = next(
            (value for value in item["findings"] if value["finding_id"] == params["finding_id"]),
            None,
        )
        if candidate is None:
            corrupt()
        if candidate["disposition"] != "unreviewed" and not allow_reviewed:
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
        return self.finding(item, candidate)

    @staticmethod
    def finding(item: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        snapshot, observation = item["snapshot"], candidate["observation"]
        return {
            "finding_id": candidate["finding_id"],
            "kind": "semantic_objection",
            "session_id": snapshot["session_id"],
            "source_id": item["analysis_id"],
            "source_revision_id": snapshot["source_revision_id"],
            "source_revision_number": item["source_revision_number"],
            "source_slide_number": snapshot["source_slide_number"],
            "slide_id": snapshot["slide_id"],
            "current_slide_number": item["current_slide_number"],
            # Native drafts use only exact concern excerpts; labels/reasons/answers
            # stay separate unverified interpretations of this recorded window.
            "quote": "\n\n".join(quote["quote"] for quote in observation["concern_quotes"]),
            "label": "Unverified recorded-window concern",
            "disposition": candidate["disposition"],
            "applied_revision_id": candidate["applied_revision_id"],
            "context_current": item["context_current"],
            "semantic_review": {
                "concern": observation["concern"],
                "reason": observation["reason"],
                "answer_status": observation["answer_status"],
                "window_index": snapshot["window_index"],
                "total_windows": snapshot["total_windows"],
                "provider_id": snapshot["provider_id"],
                "model_id": snapshot["model_id"],
                "provider_run_id": snapshot["provider_run_id"],
                "candidate_index": candidate["candidate_index"],
                "recording_completeness": "unknown",
                "speaker_identity_verified": False,
                "asr_accuracy_verified": False,
                "recorded_speech_included": True,
                **{
                    field: [
                        {
                            "utterance_id": quote["utterance_id"],
                            "quote_sha256": digest(quote["quote"]),
                        }
                        for quote in observation[quotes]
                    ]
                    for field, quotes in (
                        ("concern_references", "concern_quotes"),
                        ("answer_references", "answer_quotes"),
                    )
                },
                "provenance": "unverified_model_hint_from_one_recorded_window",
            },
            "_objection_guard": {
                "snapshot_sha256": item["snapshot_sha256"],
                "recording_sha256": snapshot["recording_sha256"],
                "can_adopt": candidate["can_adopt"],
                "candidate_index": candidate["candidate_index"],
            },
        }

    def detail(self, params: dict[str, Any]) -> dict[str, Any]:
        item = self._store.read(params)
        for candidate in item["findings"]:
            finding = self.finding(item, candidate)
            finding.pop("_objection_guard")
            candidate["finding"] = finding
        return item

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
        if finding.get("kind") != "semantic_objection":
            return
        token = finding["_objection_guard"]
        row = connection.execute(
            "SELECT a.* FROM presentation_rehearsal_objection_analyses a "
            "JOIN presentation_rehearsal_objection_findings f "
            "ON f.provider_run_id=a.provider_run_id "
            "WHERE f.finding_id=? AND a.presentation_id=?",
            (finding["finding_id"], document),
        ).fetchone()
        if row is None or row["snapshot_sha256"] != token["snapshot_sha256"]:
            corrupt()
        snapshot = self._store.parse_row(connection, row, project)
        if (
            snapshot["provider_run_id"] != finding["source_id"]
            or snapshot["session_id"] != finding["session_id"]
            or snapshot["source_revision_id"] != finding["source_revision_id"]
            or snapshot["recording_sha256"] != token["recording_sha256"]
        ):
            corrupt()
        candidate = next(
            (
                value
                for value in self._store.candidates(connection, snapshot)
                if value["finding_id"] == finding["finding_id"]
            ),
            None,
        )
        if candidate is None or candidate["candidate_index"] != token["candidate_index"]:
            corrupt()
        if candidate["disposition"] != finding["disposition"]:
            raise CoreDomainError("REHEARSAL_FINDING_REVIEWED", "The finding review changed.")
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
        if require_context and (
            not token["can_adopt"]
            or recording_state(connection, finding["session_id"]) != token["recording_sha256"]
        ):
            raise CoreDomainError("REHEARSAL_CONTEXT_CHANGED", "The recording changed before Save.")
        # Recheck the original analysis and the actual edit baseline under the
        # native Save transaction; a later revision may have reordered the slide.
        self._store.native_guard(connection, project, snapshot)
        self._store.native_guard(connection, project, snapshot | {"revision_id": baseline})
