"""Revision-bound rehearsal findings and explicitly reviewed edits."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.limits import MAX_DEBRIEF_UTTERANCES, MAX_RUN_MARKERS_PER_SESSION
from presenter_core.presentation.editing import PresentationEditService
from presenter_core.presentation.fidelity import inspect_pptx_snapshot
from presenter_core.presentation.rehearsal_objection_adoption import RehearsalObjectionAdoption
from presenter_core.presentation.rehearsal_semantic_adoption import RehearsalSemanticAdoption
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.presentation.workspace_source import PresentationWorkspaceSourceService
from presenter_core.project.service import utc_now
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager


class PresentationRehearsalService:
    def __init__(self, storage: StorageManager, edits: PresentationEditService) -> None:
        self._storage = storage
        self._edits = edits
        semantics = PresentationSemanticService(
            storage, PresentationWorkspaceSourceService(storage)
        )
        self._semantic_adoption = RehearsalSemanticAdoption(semantics)
        self._objection_adoption = RehearsalObjectionAdoption(semantics)

    def select_for_rehearsal(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id", "expected_revision_id"})
        project_id, document_id, revision_id = self._scope(params)
        with self._storage.project_database(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._current(connection, document_id, revision_id)
            if connection.execute(
                "SELECT 1 FROM sessions WHERE status = 'active' AND mode IN ('run', 'live_assist')"
            ).fetchone():
                raise CoreDomainError(
                    "PRESENTATION_SESSION_ACTIVE", "End the active rehearsal first."
                )
            connection.execute(
                "UPDATE project SET current_presentation_id = ? WHERE id = ?",
                (document_id, project_id),
            )
            connection.commit()
        return {"document_id": document_id, "revision_id": revision_id}

    def list_findings(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._list_findings(params)

    def _list_findings(
        self,
        params: dict[str, Any],
        *,
        objections_only: bool = False,
        finding_id: str | None = None,
    ) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id", "expected_revision_id"})
        project_id, document_id, revision_id = self._scope(params)
        with self._storage.project_database(project_id) as connection:
            current = self._current(connection, document_id, revision_id)
            sessions = connection.execute(
                "SELECT s.id, s.started_at, s.presentation_revision_id, r.revision_number, "
                "r.local_snapshot_path, r.sha256, r.byte_size, b.debrief_json "
                "FROM sessions s JOIN presentation_revisions r "
                "ON r.id = s.presentation_revision_id "
                "LEFT JOIN run_debriefs b ON b.session_id = s.id "
                "WHERE s.mode = 'run' AND s.status != 'active' AND r.presentation_id = ? "
                "ORDER BY s.started_at DESC, s.id DESC LIMIT 11",
                (document_id,),
            ).fetchall()
            reviews = {
                str(row["finding_id"]): dict(row)
                for row in connection.execute(
                    "SELECT * FROM presentation_rehearsal_reviews WHERE presentation_id = ?",
                    (document_id,),
                )
            }
        maps = {revision_id: self._slide_map(project_id, document_id, current)}
        current_ordinals = {slide_id: ordinal for ordinal, slide_id in maps[revision_id].items()}
        cap = 10_000 if objections_only or finding_id is not None else 300
        findings: list[dict[str, Any]] = []
        summaries: list[dict[str, Any]] = []
        for session in sessions[:10]:
            source_revision = str(session["presentation_revision_id"])
            summaries.append(
                {
                    "session_id": session["id"],
                    "started_at": session["started_at"],
                    "revision_id": source_revision,
                    "revision_number": session["revision_number"],
                    "debrief_available": session["debrief_json"] is not None,
                }
            )
            if session["debrief_json"] is None:
                continue
            if source_revision not in maps:
                maps[source_revision] = self._slide_map(project_id, document_id, session)
            try:
                debrief = json.loads(session["debrief_json"])
            except (ValueError, TypeError) as error:
                raise CoreDomainError(
                    "RUN_DEBRIEF_CORRUPT", "The rehearsal debrief is invalid."
                ) from error
            if not isinstance(debrief, dict):
                raise CoreDomainError("RUN_DEBRIEF_CORRUPT", "The rehearsal debrief is invalid.")
            for category, kind, id_field, text_field in (
                ("markers", "marked", "id", "note"),
                ("long_segments", "long_explanation", "utterance_id", "excerpt"),
                ("evidence_review_candidates", "evidence_review", "utterance_id", "excerpt"),
                ("best_explanation_candidates", "spoken_explanation", "utterance_id", "excerpt"),
            ):
                if objections_only and kind != "marked":
                    continue
                candidates = debrief.get(category, [])
                if not isinstance(candidates, list):
                    continue
                bound = (
                    MAX_DEBRIEF_UTTERANCES
                    if finding_id is not None
                    else MAX_RUN_MARKERS_PER_SESSION
                    if objections_only
                    else 100
                )
                for item in candidates[:bound]:
                    if not isinstance(item, dict) or not isinstance(item.get(id_field), str):
                        continue
                    if objections_only and item.get("marker_type") != "objection":
                        continue
                    source_id = str(item[id_field])
                    ordinal = item.get("slide_ordinal")
                    slide_id = (
                        maps[source_revision].get(ordinal) if isinstance(ordinal, int) else None
                    )
                    identity = hashlib.sha256(
                        f"{session['id']}\0{kind}\0{source_id}".encode()
                    ).hexdigest()
                    if finding_id is not None and identity != finding_id:
                        continue
                    review = reviews.get(identity)
                    findings.append(
                        {
                            "finding_id": identity,
                            "kind": kind,
                            "session_id": session["id"],
                            "source_id": source_id,
                            "source_revision_id": source_revision,
                            "source_revision_number": session["revision_number"],
                            "source_slide_number": ordinal,
                            "slide_id": slide_id,
                            "current_slide_number": current_ordinals.get(slide_id)
                            if slide_id is not None
                            else None,
                            "quote": str(item.get(text_field) or "")[:2_000],
                            "label": str(item.get("marker_type") or item.get("status") or kind),
                            "disposition": review["disposition"] if review else "unreviewed",
                            "applied_revision_id": review["applied_revision_id"]
                            if review
                            else None,
                        }
                    )
                    if len(findings) >= cap:
                        break
                if len(findings) >= cap:
                    break
            if len(findings) >= cap:
                break
        return {
            "document_id": document_id,
            "revision_id": revision_id,
            "sessions": summaries,
            "findings": findings,
            "truncated": len(sessions) > 10 or len(findings) >= cap,
        }

    def recurring_objections(self, params: dict[str, Any]) -> dict[str, Any]:
        """Group exact user-marked objections across distinct ended rehearsals."""
        from presenter_core.presentation.recurring_objections import group_objections

        reject_unknown_fields(
            params, {"project_id", "document_id", "expected_revision_id", "offset", "limit"}
        )
        offset, limit = params.get("offset", 0), params.get("limit", 20)
        if (
            type(offset) is not int
            or not 0 <= offset <= 10000
            or type(limit) is not int
            or not 1 <= limit <= 20
        ):
            raise invalid_request("Choose a valid recurring-objection page (1–20 groups).")
        scope = {
            key: params.get(key) for key in ("project_id", "document_id", "expected_revision_id")
        }
        project, document, revision = self._scope(scope)
        listed = self._list_findings(scope, objections_only=True)
        groups, excluded = group_objections(document, listed["findings"])
        with self._storage.project_database(project) as connection:
            self._current(connection, document, revision)
        return {
            "document_id": document,
            "revision_id": revision,
            "groups": groups[offset : offset + limit],
            "total_groups": len(groups),
            "offset": offset,
            "limit": limit,
            "sessions_checked": len(listed["sessions"]),
            "truncated": listed["truncated"],
            "ungrouped_objections": excluded,
        }

    def coverage(self, params: dict[str, Any]) -> dict[str, Any]:
        """Inspect source-native text density and recorded observations, without inference."""
        from presenter_core.limits import MAX_SLIDE_EVENTS_PER_SESSION
        from presenter_core.presentation.rehearsal_coverage import inspect_coverage

        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "session_id",
                "offset",
                "limit",
                "sort",
                "filter",
            },
        )
        project, document, revision = self._scope(params)
        session_id = self._edits._uuid_field(params.get("session_id"), "session_id")
        offset, limit = params.get("offset", 0), params.get("limit", 20)
        sort, filter_by = params.get("sort", "slide"), params.get("filter", "all")
        if (
            type(offset) is not int
            or not 0 <= offset <= 10000
            or type(limit) is not int
            or not 1 <= limit <= 50
        ):
            raise invalid_request("Choose a valid coverage page (1–50 rows).")
        if sort not in ("slide", "native_words") or filter_by not in (
            "all",
            "no_speech",
            "no_visit",
        ):
            raise invalid_request("Choose a supported coverage sort and filter.")
        with self._storage.project_database(project) as connection:
            current = self._current(connection, document, revision)
            session = connection.execute(
                "SELECT s.id AS session_id, s.started_at, s.presentation_revision_id, "
                "r.revision_number, r.local_snapshot_path, r.sha256, r.byte_size, b.debrief_json "
                "FROM sessions s JOIN presentation_revisions r "
                "ON r.id = s.presentation_revision_id "
                "JOIN run_debriefs b ON b.session_id = s.id "
                "WHERE s.id = ? AND s.mode = 'run' AND s.status != 'active' "
                "AND r.presentation_id = ?",
                (session_id, document),
            ).fetchone()
            if session is None:
                raise CoreDomainError(
                    "REHEARSAL_COVERAGE_UNAVAILABLE",
                    "Choose an ended rehearsal with a debrief for this deck.",
                )
            events = connection.execute(
                "SELECT slide_ordinal FROM slide_state_events WHERE session_id = ? LIMIT ?",
                (session_id, MAX_SLIDE_EVENTS_PER_SESSION + 1),
            ).fetchall()
            if len(events) > MAX_SLIDE_EVENTS_PER_SESSION:
                raise CoreDomainError(
                    "REHEARSAL_COVERAGE_UNAVAILABLE",
                    "The rehearsal timeline exceeds its supported limit.",
                )
        result = inspect_coverage(
            self._storage,
            project,
            document,
            current,
            session,
            events,
            offset=offset,
            limit=limit,
            sort=sort,
            filter_by=filter_by,
        )
        with self._storage.project_database(project) as connection:
            self._current(connection, document, revision)
        return result

    def compare_runs(self, params: dict[str, Any]) -> dict[str, Any]:
        """Compare stored observations, scoped to one deck and frozen revisions."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "baseline_session_id",
                "comparison_session_id",
            },
        )
        project, document, revision = self._scope(params)
        ids = [
            self._edits._uuid_field(params.get(field), field)
            for field in ("baseline_session_id", "comparison_session_id")
        ]
        if ids[0] == ids[1]:
            raise invalid_request("Choose two different rehearsals.")
        with self._storage.project_database(project) as connection:
            current = self._current(connection, document, revision)
            rows = connection.execute(
                "SELECT s.id AS session_id, s.started_at, s.presentation_revision_id, "
                "r.revision_number, r.local_snapshot_path, r.sha256, r.byte_size, b.debrief_json "
                "FROM sessions s JOIN presentation_revisions r "
                "ON r.id = s.presentation_revision_id "
                "JOIN run_debriefs b ON b.session_id = s.id "
                "WHERE s.id IN (?, ?) AND s.mode = 'run' AND s.status != 'active' "
                "AND r.presentation_id = ?",
                (*ids, document),
            ).fetchall()
        if len(rows) != 2:
            raise CoreDomainError(
                "REHEARSAL_COMPARISON_UNAVAILABLE",
                "Choose two ended rehearsals with debriefs for this deck.",
            )
        by_id = {str(row["session_id"]): row for row in rows}
        categories = (
            "markers",
            "long_segments",
            "evidence_review_candidates",
            "best_explanation_candidates",
        )
        fields = ("speaking_time_ms", "word_count", "utterance_count", *categories)
        current_map = self._slide_map(project, document, current)
        current_ordinals = {identity: ordinal for ordinal, identity in current_map.items()}
        snapshots: list[dict[str, Any]] = []
        bounded_candidates = False
        for session_id in ids:
            row = by_id[session_id]
            mapping = self._slide_map(project, document, row)
            try:
                raw = row["debrief_json"]
                if not isinstance(raw, str) or len(raw) > 8 * 1024 * 1024:
                    raise ValueError("Debrief size")
                debrief = json.loads(raw)
                summary = debrief["session"]
                if (
                    summary["session_id"] != session_id
                    or not isinstance(debrief["algorithm_version"], str)
                    or not debrief["algorithm_version"]
                ):
                    raise ValueError("Debrief identity")
                totals = {
                    name: summary[name] for name in ("duration_ms", "word_count", "utterance_count")
                }
                if any(type(value) is not int or value < 0 for value in totals.values()):
                    raise ValueError("Debrief metrics")
                counts = {identity: dict.fromkeys(fields, 0) for identity in mapping.values()}
                unmapped = dict.fromkeys(fields, 0)
                per_slide = debrief["per_slide"]
                if not isinstance(per_slide, list) or len(per_slide) > 5001:
                    raise ValueError("Debrief slides")
                for item in per_slide:
                    ordinal = item.get("slide_ordinal")
                    identity = mapping.get(ordinal) if type(ordinal) is int else None
                    target = counts.get(identity) if identity is not None else None
                    target = target if target is not None else unmapped
                    for field in fields[:3]:
                        value = item[field]
                        if type(value) is not int or value < 0:
                            raise ValueError("Slide metric")
                        target[field] += value
                for category in categories:
                    candidates = debrief[category]
                    if not isinstance(candidates, list) or len(candidates) > MAX_DEBRIEF_UTTERANCES:
                        raise ValueError("Debrief candidates")
                    totals[category] = len(candidates)
                    # Existing generators cap evidence candidates at 100 and best
                    # explanations at 8. A full list may omit additional candidates.
                    if (
                        (category == "markers" and len(candidates) >= MAX_RUN_MARKERS_PER_SESSION)
                        or (category == "evidence_review_candidates" and len(candidates) >= 100)
                        or (category == "best_explanation_candidates" and len(candidates) >= 8)
                    ):
                        bounded_candidates = True
                    for item in candidates:
                        ordinal = item.get("slide_ordinal")
                        identity = mapping.get(ordinal) if type(ordinal) is int else None
                        target = counts.get(identity) if identity is not None else None
                        target = target if target is not None else unmapped
                        target[category] += 1
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                raise CoreDomainError(
                    "RUN_DEBRIEF_CORRUPT", "A rehearsal debrief contains invalid comparison data."
                ) from error
            snapshots.append(
                {
                    "session_id": session_id,
                    "started_at": row["started_at"],
                    "revision_id": row["presentation_revision_id"],
                    "revision_number": row["revision_number"],
                    "algorithm_version": debrief.get("algorithm_version"),
                    "totals": totals,
                    "ordinals": {identity: ordinal for ordinal, identity in mapping.items()},
                    "counts": counts,
                    "unmapped": unmapped,
                }
            )
        baseline, comparison = snapshots
        identities = list(
            dict.fromkeys([*current_ordinals, *baseline["counts"], *comparison["counts"]])
        )
        slides = []
        for identity in identities[:200]:
            before, after = baseline["counts"].get(identity), comparison["counts"].get(identity)
            slides.append(
                {
                    "slide_id": identity,
                    "current_slide_number": current_ordinals.get(identity),
                    "baseline_slide_number": baseline["ordinals"].get(identity),
                    "comparison_slide_number": comparison["ordinals"].get(identity),
                    "baseline": before,
                    "comparison": after,
                    "delta": {field: after[field] - before[field] for field in fields}
                    if before is not None and after is not None
                    else None,
                }
            )
        with self._storage.project_database(project) as connection:
            self._current(connection, document, revision)
        return {
            "document_id": document,
            "revision_id": revision,
            "baseline": {
                key: baseline[key]
                for key in (
                    "session_id",
                    "started_at",
                    "revision_id",
                    "revision_number",
                    "algorithm_version",
                    "totals",
                    "unmapped",
                )
            },
            "comparison": {
                key: comparison[key]
                for key in (
                    "session_id",
                    "started_at",
                    "revision_id",
                    "revision_number",
                    "algorithm_version",
                    "totals",
                    "unmapped",
                )
            },
            "delta": {
                field: comparison["totals"][field] - baseline["totals"][field]
                for field in baseline["totals"]
            },
            "slides": slides,
            "truncated": len(identities) > 200,
            "candidate_counts_may_be_capped": bounded_candidates,
            "algorithm_versions_match": baseline["algorithm_version"]
            == comparison["algorithm_version"],
        }

    def reject_finding(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "document_id", "expected_revision_id", "finding_id", "reopen"}
        )
        project_id, document_id, revision_id = self._scope(params)
        reopen = params.get("reopen", False)
        if not isinstance(reopen, bool):
            raise invalid_request("reopen must be a boolean.", field="reopen")
        finding = self._finding(params, allow_reviewed=reopen, require_context=False)
        with self._storage.project_database(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._current(connection, document_id, revision_id)
            self._guard(
                connection,
                project_id,
                document_id,
                revision_id,
                finding,
                None,
                require_context=False,
            )
            if reopen:
                removed = connection.execute(
                    "DELETE FROM presentation_rehearsal_reviews "
                    "WHERE finding_id = ? AND disposition = 'rejected'",
                    (finding["finding_id"],),
                )
                if removed.rowcount != 1:
                    raise CoreDomainError(
                        "REHEARSAL_FINDING_REVIEWED", "Only a dismissed finding can be reopened."
                    )
            else:
                self._record(connection, document_id, revision_id, finding, None)
            connection.commit()
        return {
            "finding_id": finding["finding_id"],
            "disposition": "unreviewed" if reopen else "rejected",
        }

    def apply_edit(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "finding_id",
                "edit_kind",
                "slide_id",
                "object_id",
                "expected_text",
                "replacement_text",
            },
        )
        project_id, document_id, revision_id = self._scope(params)
        finding = self._finding(params)
        if finding["slide_id"] is None or finding["slide_id"] != params.get("slide_id"):
            raise invalid_request(
                "The edit must target the finding's original slide.", field="slide_id"
            )
        if finding["current_slide_number"] is None:
            raise CoreDomainError(
                "REHEARSAL_SLIDE_REMOVED", "This slide is absent from the current revision."
            )
        edit = {
            key: params[key]
            for key in (
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "expected_text",
                "replacement_text",
            )
            if key in params
        }

        def record(connection: sqlite3.Connection, applied_revision: str) -> None:
            self._guard(
                connection,
                project_id,
                document_id,
                revision_id,
                finding,
                applied_revision,
                require_context=True,
            )
            self._record(connection, document_id, revision_id, finding, applied_revision)

        if params.get("edit_kind") == "text":
            self._semantic_adoption.require_text_target(finding, params.get("object_id"))
            edit["object_id"] = params.get("object_id")
            edit["operation_type"] = "replace_text_shape"
            result = self._edits.replace_text_shape(edit, on_commit=record)
        elif params.get("edit_kind") == "notes":
            if "object_id" in params:
                raise invalid_request("Notes edits do not take an object_id.", field="object_id")
            result = self._edits.replace_speaker_notes(edit, on_commit=record)
        else:
            raise invalid_request("Choose a text or notes edit.", field="edit_kind")
        return {**result, "finding_id": finding["finding_id"]}

    def resolve_finding(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._finding(params)

    def _finding(
        self, params: dict[str, Any], *, allow_reviewed: bool = False, require_context: bool = True
    ) -> dict[str, Any]:
        finding_id = params.get("finding_id")
        if not isinstance(finding_id, str) or len(finding_id) != 64:
            raise invalid_request("A finding_id is required.", field="finding_id")
        semantic = self._semantic_adoption.resolve(
            params,
            allow_reviewed=allow_reviewed,
            require_context=require_context,
        )
        if semantic is not None:
            return semantic
        objection = self._objection_adoption.resolve(
            params, allow_reviewed=allow_reviewed, require_context=require_context
        )
        if objection is not None:
            return objection
        listed = self._list_findings(
            {
                key: params[key]
                for key in (
                    "project_id",
                    "document_id",
                    "expected_revision_id",
                )
                if key in params
            },
            finding_id=finding_id,
        )
        for finding in listed["findings"]:
            if finding["finding_id"] == finding_id:
                if finding["disposition"] != "unreviewed" and not allow_reviewed:
                    raise CoreDomainError(
                        "REHEARSAL_FINDING_REVIEWED", "This finding was already reviewed."
                    )
                return dict(finding)
        raise CoreDomainError(
            "REHEARSAL_FINDING_NOT_FOUND", "The finding is unavailable. Refresh the findings."
        )

    def _guard(
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
        for adoption in (self._semantic_adoption, self._objection_adoption):
            adoption.guard(
                connection,
                project,
                document,
                baseline,
                finding,
                applied,
                require_context=require_context,
            )

    @staticmethod
    def _record(
        connection: sqlite3.Connection,
        document_id: str,
        baseline: str,
        finding: dict[str, Any],
        applied: str | None,
    ) -> None:
        if connection.execute(
            "SELECT 1 FROM presentation_rehearsal_reviews WHERE finding_id = ?",
            (finding["finding_id"],),
        ).fetchone():
            raise CoreDomainError(
                "REHEARSAL_FINDING_REVIEWED", "This finding was already reviewed."
            )
        connection.execute(
            "INSERT INTO presentation_rehearsal_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                finding["finding_id"],
                finding["session_id"],
                document_id,
                finding["source_revision_id"],
                baseline,
                applied,
                "applied" if applied else "rejected",
                utc_now(),
            ),
        )

    def _scope(self, params: dict[str, Any]) -> tuple[str, str, str]:
        if not isinstance(params.get("project_id"), str):
            raise invalid_request("project_id must be a UUID.", field="project_id")
        project_id = normalize_project_id(params["project_id"])
        identifiers: list[str] = []
        for field in ("document_id", "expected_revision_id"):
            try:
                identifiers.append(str(uuid.UUID(params[field])))
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                raise invalid_request(f"{field} must be a UUID.", field=field) from error
        with self._storage.project_database(project_id) as connection:
            if not connection.execute(
                "SELECT 1 FROM documents WHERE id = ? AND project_id = ? "
                "AND kind = 'presentation' AND parse_status = 'ready'",
                (identifiers[0], project_id),
            ).fetchone():
                raise CoreDomainError("SOURCE_NOT_FOUND", "The presentation is unavailable.")
        return project_id, identifiers[0], identifiers[1]

    @staticmethod
    def _current(connection: sqlite3.Connection, document_id: str, revision_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT r.* FROM presentation_revision_heads h JOIN presentation_revisions r "
            "ON r.id = h.revision_id AND r.presentation_id = h.presentation_id "
            "WHERE h.presentation_id = ?",
            (document_id,),
        ).fetchone()
        if row is None or row["id"] != revision_id:
            raise CoreDomainError(
                "PRESENTATION_REVISION_CONFLICT",
                "The presentation changed. Reopen it before continuing.",
            )
        return cast(sqlite3.Row, row)

    def _slide_map(self, project_id: str, document_id: str, row: sqlite3.Row) -> dict[int, str]:
        path = self._storage.paths.snapshot_path(
            project_id, row["local_snapshot_path"], require_exists=True
        )
        with path.open("rb") as handle:
            fidelity = inspect_pptx_snapshot(
                handle,
                document_id=document_id,
                expected_sha256=row["sha256"],
                byte_size=row["byte_size"],
            )
        return {slide.ordinal: slide.slide_id for slide in fidelity.slides}
