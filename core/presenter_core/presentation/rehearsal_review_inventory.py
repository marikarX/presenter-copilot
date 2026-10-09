"""Bounded original Run message selectors and immutable semantic result readers."""

from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.claims import digest
from presenter_core.presentation.rehearsal_analysis_store import RehearsalAnalysisStore
from presenter_core.presentation.rehearsal_objection_store import RehearsalObjectionStore
from presenter_core.presentation.rehearsal_semantic_adoption import RehearsalSemanticAdoption
from presenter_core.presentation.semantics import PresentationSemanticService


class RehearsalReviewInventory:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics
        self._storage = semantics._storage

    def _scope(self, params: dict[str, Any], extra: set[str]) -> tuple[str, str, str]:
        reject_unknown_fields(params, {"project_id", "document_id", "expected_revision_id"} | extra)
        s = self._semantics
        values = (
            s._project_id(params.get("project_id")),
            s._uuid_field(params.get("document_id"), "document_id"),
            s._uuid_field(params.get("expected_revision_id"), "expected_revision_id"),
        )
        self._current(*values)
        return values

    def _current(self, project: str, document: str, revision: str) -> None:
        with self._storage.project_database(project) as connection:
            self._semantics._require_current_presentation(connection, project, document, revision)

    @staticmethod
    def _page(params: dict[str, Any]) -> tuple[int, int]:
        offset, limit = params.get("offset", 0), params.get("limit", 20)
        if type(offset) is not int or not 0 <= offset <= 1000000:
            raise invalid_request("Choose a valid review page offset.")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise invalid_request("Choose between 1 and 20 review items per page.")
        return offset, limit

    def _session(self, project: str, document: str, identity: Any) -> dict[str, Any]:
        session = self._semantics._uuid_field(identity, "session_id")
        with self._storage.project_database(project) as connection:
            row = connection.execute(
                "SELECT s.id,s.presentation_revision_id,s.started_at,s.ended_at,r.revision_number "
                "FROM sessions s JOIN presentation_revisions r ON r.id=s.presentation_revision_id "
                "WHERE s.id=? AND s.project_id=? AND r.presentation_id=? "
                "AND s.mode='run' AND s.status!='active'",
                (session, project, document),
            ).fetchone()
        if row is None:
            raise CoreDomainError(
                "REHEARSAL_ANALYSIS_UNAVAILABLE", "Choose an owned ended Run for this deck."
            )
        return dict(row)

    def sessions(self, params: dict[str, Any]) -> dict[str, Any]:
        project, document, revision = self._scope(params, {"offset", "limit"})
        offset, limit = self._page(params)
        where = "s.project_id=? AND r.presentation_id=? AND s.mode='run' AND s.status!='active'"
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN")
            total = connection.execute(
                "SELECT COUNT(*) FROM sessions s JOIN presentation_revisions r "
                "ON r.id=s.presentation_revision_id WHERE " + where,
                (project, document),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT s.id AS session_id,s.started_at,s.ended_at,r.id AS source_revision_id,"
                "r.revision_number AS source_revision_number,"
                "EXISTS(SELECT 1 FROM run_debriefs b WHERE b.session_id=s.id) AS debrief_available "
                "FROM sessions s JOIN presentation_revisions r ON r.id=s.presentation_revision_id "
                "WHERE " + where + " ORDER BY s.started_at DESC,s.id DESC LIMIT ? OFFSET ?",
                (project, document, limit, offset),
            ).fetchall()
        self._current(project, document, revision)
        return {
            "document_id": document,
            "revision_id": revision,
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + limit < total,
            "sessions": [
                {**dict(row), "debrief_available": bool(row["debrief_available"])} for row in rows
            ],
        }

    def slides(self, params: dict[str, Any]) -> dict[str, Any]:
        project, document, revision = self._scope(params, {"session_id", "offset", "limit"})
        offset, limit = self._page(params)
        session = self._session(project, document, params.get("session_id"))
        source = self._semantics._workspace_sources.read_revision_inventory(
            {
                "project_id": project,
                "document_id": document,
                "revision_id": session["presentation_revision_id"],
            },
            current_only=False,
        )[-1]
        current = self._semantics._workspace_sources.read_revision_inventory(
            {"project_id": project, "document_id": document, "revision_id": revision}
        )[-1]
        ordinals = {slide.slide_id: slide.ordinal for slide in current.slides}
        items = [
            {
                "slide_id": slide.slide_id,
                "source_slide_number": slide.ordinal,
                "current_slide_number": ordinals.get(slide.slide_id),
            }
            for slide in source.slides[offset : offset + limit]
        ]
        if self._session(project, document, session["id"]) != session:
            raise CoreDomainError(
                "REHEARSAL_CONTEXT_CHANGED", "The Run changed while selecting its original slides."
            )
        self._current(project, document, revision)
        return {
            "document_id": document,
            "revision_id": revision,
            "session_id": session["id"],
            "source_revision_id": session["presentation_revision_id"],
            "source_revision_number": session["revision_number"],
            "offset": offset,
            "limit": limit,
            "total": len(source.slides),
            "has_more": offset + limit < len(source.slides),
            "slides": items,
        }

    def messages(self, params: dict[str, Any]) -> dict[str, Any]:
        project, document, revision = self._scope(
            params, {"session_id", "slide_id", "offset", "limit"}
        )
        offset, limit = self._page(params)
        session = self._session(project, document, params.get("session_id"))
        filter_slide = (
            self._semantics._uuid_field(params["slide_id"], "slide_id")
            if "slide_id" in params
            else None
        )
        source_scope = {"project_id": project, "document_id": document, "revision_id": revision}
        current = self._semantics._workspace_sources.read_revision_inventory(source_scope)[-1]
        source = (
            current
            if session["presentation_revision_id"] == revision
            else (
                self._semantics._workspace_sources.read_revision_inventory(
                    source_scope | {"revision_id": session["presentation_revision_id"]},
                    current_only=False,
                )[-1]
            )
        )
        current_slides = {slide.slide_id: slide for slide in current.slides}
        source_slides = [
            slide
            for slide in source.slides
            if filter_slide is None or slide.slide_id == filter_slide
        ]
        if filter_slide is not None and not source_slides:
            raise invalid_request("Choose a slide in the original recording snapshot.")
        items = []
        total = excluded = 0
        for slide in source_slides:
            represented = source.text_targets(slide.ordinal, limit=len(slide.objects))
            excluded += int(cast(int, represented["semantic_excluded_objects"]))
            targets = cast(list[dict[str, Any]], represented["semantic_targets"])
            present = current_slides.get(slide.slide_id)
            current_objects = {obj.object_id: obj for obj in present.objects} if present else {}
            for target in targets:
                if offset <= total < offset + limit:
                    obj = current_objects.get(target["object_id"])
                    text = target["decision_text"]
                    status = (
                        "missing"
                        if obj is None
                        else (
                            "unchanged"
                            if obj.semantic_source_kind == target["source_kind"]
                            and digest(obj.text) == digest(text)
                            else "changed"
                        )
                    )
                    items.append(
                        {
                            "slide_id": slide.slide_id,
                            "object_id": target["object_id"],
                            "source_slide_number": slide.ordinal,
                            "name": target["name"][:200],
                            "source_kind": target["source_kind"],
                            "text": text,
                            "object_sha256": digest(text),
                            "whole_message_selectable": len(text) <= 2000,
                            "current_slide_number": present.ordinal if present else None,
                            "current_span_status": status,
                            "current_text_editable": bool(
                                obj
                                and (
                                    obj.single_run_text_edit_candidate
                                    or obj.uniform_run_text_edit_candidate
                                )
                            ),
                        }
                    )
                total += 1
        if self._session(project, document, session["id"]) != session:
            raise CoreDomainError(
                "REHEARSAL_CONTEXT_CHANGED", "The recording scope changed during selection."
            )
        self._current(project, document, revision)
        return {
            "document_id": document,
            "revision_id": revision,
            "session_id": session["id"],
            "source_revision_id": session["presentation_revision_id"],
            "source_sha256": source.source_sha256,
            "source_revision_number": session["revision_number"],
            "total": total,
            "excluded_objects": excluded,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total,
            "messages": items,
            "requires_user_selection": True,
        }

    def analyses(self, params: dict[str, Any]) -> dict[str, Any]:
        project, document, revision = self._scope(params, {"session_id", "offset", "limit"})
        offset, limit = self._page(params)
        session = self._session(project, document, params.get("session_id"))
        store = RehearsalAnalysisStore(self._semantics)
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN")
            total = connection.execute(
                "SELECT COUNT(*) FROM presentation_rehearsal_analyses "
                "WHERE presentation_id=? AND session_id=?",
                (document, session["id"]),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT a.*,r.disposition,r.applied_revision_id "
                "FROM presentation_rehearsal_analyses a "
                "LEFT JOIN presentation_rehearsal_reviews r ON r.finding_id=a.finding_id "
                "WHERE a.presentation_id=? AND a.session_id=? "
                "ORDER BY a.created_at DESC,a.provider_run_id DESC "
                "LIMIT ? OFFSET ?",
                (document, session["id"], limit, offset),
            ).fetchall()
            items = []
            for row in rows:
                snapshot = store.parse_row(connection, row, project)
                items.append(
                    {
                        "analysis_id": row["provider_run_id"],
                        "finding_id": row["finding_id"],
                        "slide_id": snapshot["slide_id"],
                        "object_id": snapshot["point"]["object_id"],
                        "source_slide_number": snapshot["source_slide_number"],
                        "window_index": row["window_index"],
                        "total_windows": snapshot["total_windows"],
                        "context_sha256": row["context_sha256"],
                        "status": snapshot["hint"]["status"],
                        "reason": snapshot["hint"]["reason"],
                        "provider_id": snapshot["provider_id"],
                        "model_id": snapshot["model_id"],
                        "created_at": row["created_at"],
                        "disposition": row["disposition"] or "unreviewed",
                        "requires_user_review": True,
                        "requires_verified_detail": True,
                    }
                )
        if self._session(project, document, session["id"]) != session:
            raise CoreDomainError(
                "REHEARSAL_CONTEXT_CHANGED", "The recording scope changed during listing."
            )
        self._current(project, document, revision)
        return {
            "document_id": document,
            "revision_id": revision,
            "session_id": session["id"],
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + limit < total,
            "analyses": items,
        }

    def objection_analyses(self, params: dict[str, Any]) -> dict[str, Any]:
        project, document, revision = self._scope(params, {"session_id", "offset", "limit"})
        offset, limit = self._page(params)
        session = self._session(project, document, params.get("session_id"))
        store = RehearsalObjectionStore(self._semantics)
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN")
            total = connection.execute(
                "SELECT COUNT(*) FROM presentation_rehearsal_objection_analyses "
                "WHERE presentation_id=? AND session_id=?",
                (document, session["id"]),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM presentation_rehearsal_objection_analyses "
                "WHERE presentation_id=? AND session_id=? "
                "ORDER BY created_at DESC,provider_run_id DESC LIMIT ? OFFSET ?",
                (document, session["id"], limit, offset),
            ).fetchall()
            items = []
            for row in rows:
                snapshot = store.parse_row(connection, row, project)
                findings = store.candidates(connection, snapshot)
                items.append(
                    {
                        "analysis_id": row["provider_run_id"],
                        "slide_id": snapshot["slide_id"],
                        "source_slide_number": snapshot["source_slide_number"],
                        "window_index": row["window_index"],
                        "total_windows": snapshot["total_windows"],
                        "candidate_count": len(findings),
                        "disposition_counts": {
                            state: sum(item["disposition"] == state for item in findings)
                            for state in ("unreviewed", "rejected", "applied")
                        },
                        "provider_id": snapshot["provider_id"],
                        "model_id": snapshot["model_id"],
                        "created_at": row["created_at"],
                        "requires_user_review": True,
                        "requires_verified_detail": True,
                    }
                )
        if self._session(project, document, session["id"]) != session:
            raise CoreDomainError(
                "REHEARSAL_CONTEXT_CHANGED", "The recording scope changed during listing."
            )
        self._current(project, document, revision)
        return {
            "document_id": document,
            "revision_id": revision,
            "session_id": session["id"],
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + limit < total,
            "analyses": items,
        }

    def detail(self, params: dict[str, Any]) -> dict[str, Any]:
        item = RehearsalAnalysisStore(self._semantics).read(params)
        finding = RehearsalSemanticAdoption.finding(item)
        finding.pop("_semantic_guard")
        return {
            key: value
            for key, value in item.items()
            if key not in {"recording_sha256", "snapshot_sha256"}
        } | {
            "finding": finding,
        }
