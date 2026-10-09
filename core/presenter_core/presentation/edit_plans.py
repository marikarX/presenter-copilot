"""Review exact native edit packages before publishing one revision."""

from __future__ import annotations

import copy
import json
import re
import shutil
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.creation import PresentationCreationService
from presenter_core.presentation.editing import PresentationEditService
from presenter_core.presentation.transactions import (
    PresentationTransactionService,
    StagedPresentationPlan,
)
from presenter_core.presentation.workspace_source import PresentationWorkspaceSourceService
from presenter_core.project.service import utc_now
from presenter_core.storage.service import StorageManager

PLAN_TTL_SECONDS = 15 * 60.0
MAX_REVIEW_PLANS = 4
_PRIVATE_PACKAGE = re.compile(
    r"^(?:\.edit-plan-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"|\.edit-stage-[0-9a-f]{32}-[1-9][0-9]*)\.pptx$"
)


@dataclass
class _ReviewPlan:
    project_id: str
    document_id: str
    baseline_revision_id: str
    summary: str
    package: StagedPresentationPlan
    operations: list[dict[str, Any]]
    expires_at: float
    readers: set[str] = field(default_factory=set)
    provider_run_id: str | None = None
    operation_evidence: tuple[tuple[str, ...], ...] = ()
    planner_draft: dict[str, Any] | None = None


class PresentationEditPlanService:
    """Own transient previews; durable history is written only with the final commit."""

    def __init__(
        self,
        storage: StorageManager,
        edits: PresentationEditService,
        sources: PresentationWorkspaceSourceService,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._storage = storage
        self._edits = edits
        self._sources = sources
        self._transactions = PresentationTransactionService(storage, edits)
        self._clock = clock
        self._plans: dict[str, _ReviewPlan] = {}

    def reconcile_project(self, project_id: str) -> None:
        """Remove abandoned private packages on project access, after a process crash.

        The exact generated filename patterns, trusted vault mapping, non-symlink
        checks and registered-snapshot exclusions constrain every removal. Live
        review plans are retained. No exported or imported user files are touched.
        """
        self._storage.project_paths(project_id)
        directory = self._storage.paths.safe_sources_directory(project_id)
        with self._storage.project_database(project_id) as connection:
            registered = {
                row[0]
                for row in connection.execute(
                    "SELECT local_snapshot_path FROM documents UNION "
                    "SELECT local_snapshot_path FROM presentation_revisions"
                )
            }
        live = {plan.package.path for plan in self._plans.values()}
        for candidate in directory.iterdir():
            if (
                _PRIVATE_PACKAGE.fullmatch(candidate.name)
                and not candidate.is_symlink()
                and candidate.is_file()
                and candidate not in live
                and f"sources/{candidate.name}" not in registered
            ):
                path = self._storage.paths.snapshot_path(
                    project_id, f"sources/{candidate.name}", require_exists=True
                )
                self._edits._unlink_managed(path)

    def prepare(
        self,
        params: dict[str, Any],
        *,
        resolve_operation: Callable[[PresentationEditService, str, dict[str, Any]], dict[str, Any]]
        | None = None,
        provider_run_id: str | None = None,
        operation_evidence: tuple[tuple[str, ...], ...] = (),
    ) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "document_id", "expected_revision_id", "summary", "operations"}
        )
        project_id, document_id, revision_id = self._scope(params)
        self.reconcile_project(project_id)
        summary = PresentationCreationService._text(params.get("summary"), "summary", 500)
        operations = copy.deepcopy(params.get("operations"))
        if not isinstance(operations, list):
            raise invalid_request("operations must be a list.", field="operations")
        if provider_run_id is not None and len(operation_evidence) != len(operations):
            raise invalid_request("Each provider operation requires provenance metadata.")
        self._expire()
        if len(self._plans) >= MAX_REVIEW_PLANS:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PLAN_LIMIT", "Discard an existing edit preview first."
            )
        plan_id = str(uuid.uuid4())
        target = self._storage.paths.snapshot_path(project_id, f"sources/.edit-plan-{plan_id}.pptx")
        if target.exists() or target.is_symlink():
            raise CoreDomainError("PRESENTATION_REVISION_PATH_INVALID", "Preview path is in use.")
        try:
            resolved: list[dict[str, Any]] = []

            def resolve(
                editor: PresentationEditService, kind: str, values: dict[str, Any]
            ) -> dict[str, Any]:
                bound = resolve_operation(editor, kind, values) if resolve_operation else values
                resolved.append({"type": kind, "params": copy.deepcopy(bound)})
                return bound

            with self._transactions.stage(
                project_id=project_id,
                document_id=document_id,
                expected_revision_id=revision_id,
                operations=operations,
                resolve_operation=resolve,
            ) as staged:
                shutil.copyfile(staged.path, target)
                package = StagedPresentationPlan(
                    target, staged.sha256, staged.byte_size, staged.changed, staged.outcomes
                )
            self._plans[plan_id] = _ReviewPlan(
                project_id,
                document_id,
                revision_id,
                summary,
                package,
                resolved,
                self._clock() + PLAN_TTL_SECONDS,
                provider_run_id=provider_run_id,
                operation_evidence=operation_evidence,
            )
        except (CoreDomainError, OSError):
            self._edits._unlink_managed(target)
            raise
        return {
            "plan_id": plan_id,
            "baseline_revision_id": revision_id,
            "summary": summary,
            "changed": package.changed,
            "sha256": package.sha256,
            "byte_size": package.byte_size,
            "operations": copy.deepcopy(resolved),
            "requires_user_review": True,
            "expires_in_seconds": int(PLAN_TTL_SECONDS),
        }

    def open_preview(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id", "plan_id"})
        plan_id, plan = self._get(params)
        source = self._current(plan)
        reader = self._sources.open_verified_snapshot(
            plan.project_id,
            plan.document_id,
            {
                "revision_id": plan.baseline_revision_id,
                "revision_kind": "edit_plan_preview",
                "revision_number": source["revision_number"],
                "local_snapshot_path": f"sources/{plan.package.path.name}",
                "sha256": plan.package.sha256,
                "byte_size": plan.package.byte_size,
            },
        )
        plan.readers.add(reader["session_id"])
        return {**reader, "plan_id": plan_id, "is_edit_plan_preview": True}

    def apply(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "document_id", "plan_id", "reviewed_sha256", "confirm"}
        )
        plan_id, plan = self._get(params)
        self._current(plan)
        if plan.provider_run_id is not None:
            with self._storage.project_database(plan.project_id) as connection:
                run = connection.execute(
                    "SELECT task_type, status FROM provider_runs WHERE id = ?",
                    (plan.provider_run_id,),
                ).fetchone()
            if (
                run is None
                or run["task_type"] != "presentation_edit_plan"
                or run["status"] != "success"
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_PLAN_PROVENANCE_INVALID",
                    "The successful planning run is unavailable. Propose the edits again.",
                )
        if (
            params.get("confirm") is not True
            or params.get("reviewed_sha256") != plan.package.sha256
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_PLAN_REVIEW_REQUIRED",
                "Review this exact preview before applying.",
            )
        if not plan.readers:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PLAN_REVIEW_REQUIRED", "Open the proposed deck preview first."
            )
        metadata = [
            {
                key: item[key]
                for key in (
                    "type",
                    "changed",
                    "slide_id",
                    "object_id",
                    "created_slide_id",
                    "created_object_id",
                    "created_object_ids",
                    "selected_object_ids",
                )
                if key in item
            }
            for item in plan.package.outcomes
        ]
        if plan.provider_run_id is not None:
            for index, item in enumerate(metadata):
                item["provider_run_id"] = plan.provider_run_id
                item["evidence_ids"] = list(plan.operation_evidence[index])

        def audit(connection: sqlite3.Connection, revision_id: str) -> None:
            connection.execute(
                "INSERT INTO presentation_edit_transactions "
                "(revision_id, presentation_id, baseline_revision_id, "
                "operation_metadata_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    revision_id,
                    plan.document_id,
                    plan.baseline_revision_id,
                    json.dumps(metadata),
                    utc_now(),
                ),
            )

        result = self._transactions.publish(
            project_id=plan.project_id,
            document_id=plan.document_id,
            expected_revision_id=plan.baseline_revision_id,
            staged=plan.package,
            on_commit=audit,
        )
        self._drop(plan_id)
        return {**result, "plan_id": plan_id}

    def reject(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id", "plan_id"})
        plan_id, _plan = self._get(params)
        self._drop(plan_id)
        return {"rejected": True, "plan_id": plan_id}

    def close_source(self, project_id: str, document_id: str) -> None:
        for plan_id, plan in tuple(self._plans.items()):
            if (plan.project_id, plan.document_id) == (project_id, document_id):
                self._drop(plan_id)
        self.reconcile_project(project_id)

    def close_project(self, project_id: str) -> None:
        for plan_id, plan in tuple(self._plans.items()):
            if plan.project_id == project_id:
                self._drop(plan_id)

    def close(self) -> None:
        for plan_id in tuple(self._plans):
            self._drop(plan_id)

    def _get(self, params: dict[str, Any]) -> tuple[str, _ReviewPlan]:
        project_id = self._edits._project_id(params.get("project_id"))
        document_id = self._edits._uuid_field(params.get("document_id"), "document_id")
        plan_id = self._edits._uuid_field(params.get("plan_id"), "plan_id")
        self._expire()
        plan = self._plans.get(plan_id)
        if plan is None or (plan.project_id, plan.document_id) != (project_id, document_id):
            raise CoreDomainError(
                "PRESENTATION_EDIT_PLAN_NOT_FOUND", "Edit preview is unavailable or expired."
            )
        return plan_id, plan

    def _current(self, plan: _ReviewPlan) -> sqlite3.Row | dict[str, Any]:
        source = self._edits._current_revision_source(plan.project_id, plan.document_id)
        if source["revision_id"] != plan.baseline_revision_id:
            raise self._edits._revision_conflict()
        return source

    def _scope(self, params: dict[str, Any]) -> tuple[str, str, str]:
        return (
            self._edits._project_id(params.get("project_id")),
            self._edits._uuid_field(params.get("document_id"), "document_id"),
            self._edits._uuid_field(params.get("expected_revision_id"), "expected_revision_id"),
        )

    def _expire(self) -> None:
        for plan_id, plan in tuple(self._plans.items()):
            if plan.expires_at <= self._clock():
                self._drop(plan_id)

    def _drop(self, plan_id: str) -> None:
        plan = self._plans.pop(plan_id)
        for session_id in plan.readers:
            self._sources.close_source(
                {
                    "project_id": plan.project_id,
                    "document_id": plan.document_id,
                    "session_id": session_id,
                }
            )
        self._edits._unlink_managed(plan.package.path)
