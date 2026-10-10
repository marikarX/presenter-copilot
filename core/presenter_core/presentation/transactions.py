"""Stage validated native edits and publish them as one atomic revision."""

from __future__ import annotations

import shutil
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.editing import PresentationEditService
from presenter_core.presentation.fidelity import inspect_pptx_snapshot
from presenter_core.storage.service import StorageManager

MAX_PLAN_OPERATIONS = 20
PLAN_OPERATIONS = frozenset(
    {
        "replace_text_shape",
        "format_text_shape",
        "format_shape_style",
        "replace_speaker_notes",
        "transform_object",
        "change_object_layer",
        "crop_picture",
        "adjust_picture",
        "rotate_object",
        "set_slide_background",
        "set_slide_hidden",
        "set_text_hyperlink",
        "replace_picture_image",
        "reorder_slides",
        "apply_slide_layout",
        "create_slide",
        "create_authored_slide",
        "duplicate_slide",
        "create_text_box",
        "create_picture",
        "create_shape",
        "create_table",
        "create_chart",
        "create_diagram",
        "replace_diagram",
        "delete_diagram",
        "replace_chart_data",
        "reshape_chart",
        "set_chart_legend",
        "set_chart_labels",
        "set_chart_axis",
        "set_chart_color",
        "set_chart_fill",
        "set_shape_fill",
        "set_chart_marker",
        "replace_table_cells",
        "reshape_table",
        "format_table_cells",
        "set_table_borders",
        "merge_table_cells",
        "fit_table_rows",
        "fit_text_shape",
        "split_table_cells",
        "delete_slide",
        "delete_object",
        "duplicate_object",
        "paste_objects",
        "group_objects",
        "ungroup_object",
    }
)


@dataclass(frozen=True)
class StagedPresentationPlan:
    path: Path
    sha256: str
    byte_size: int
    changed: bool
    outcomes: tuple[dict[str, Any], ...]


class _StagingEditor(PresentationEditService):
    """Use the ordinary validators/writers without granting their commit path.

    Only revision lookup and commit are overridden. The allowlist excludes
    history/navigation operations, which have their own database mutations.
    All remaining public edit methods reach persistence through _commit_revision.
    """

    def __init__(
        self,
        storage: StorageManager,
        project_id: str,
        document_id: str,
        source: sqlite3.Row | dict[str, Any],
    ) -> None:
        super().__init__(storage)
        self.project_id = project_id
        self.document_id = document_id
        self.source = dict(source)
        self.baseline = str(source["revision_id"])
        self.prefix = uuid.uuid4().hex
        self.sequence = 0
        self.owned_paths: set[Path] = set()

    def _current_revision_source(self, project_id: str, document_id: str) -> dict[str, Any]:
        if (project_id, document_id) != (self.project_id, self.document_id):
            raise invalid_request("Every edit must belong to the selected presentation.")
        return dict(self.source)

    def _commit_revision(
        self,
        project_id: str,
        document_id: str,
        expected_revision_id: str,
        source: sqlite3.Row | dict[str, Any],
        write_package: Callable[[Path, Path], bool | None],
        *,
        on_commit: Callable[[sqlite3.Connection, str], None] | None = None,
    ) -> dict[str, Any]:
        self._current_revision_source(project_id, document_id)
        if expected_revision_id != self.baseline or on_commit is not None:
            raise invalid_request("A staged edit cannot change revision authority.")
        original = self._storage.paths.snapshot_path(
            project_id, str(source["local_snapshot_path"]), require_exists=True
        )
        self.sequence += 1
        relative = f"sources/.edit-stage-{self.prefix}-{self.sequence}.pptx"
        target = self._storage.paths.snapshot_path(project_id, relative)
        if target.exists() or target.is_symlink():
            raise CoreDomainError(
                "PRESENTATION_REVISION_PATH_INVALID", "A staging path is already in use."
            )
        self.owned_paths.add(target)
        changed = write_package(original, target)
        if changed is False:
            return {
                "changed": False,
                "revision_id": self.baseline,
                "revision_number": source["revision_number"],
                "sha256": source["sha256"],
                "byte_size": source["byte_size"],
            }
        digest, size = self._sha256_path(target), target.stat().st_size
        self.source.update(local_snapshot_path=relative, sha256=digest, byte_size=size)
        # Keep disk use bounded to the current stage and the original snapshot.
        if original in self.owned_paths:
            self._unlink_managed(original)
            if not original.exists():
                self.owned_paths.remove(original)
        return {
            "changed": True,
            "revision_id": self.baseline,
            "revision_number": source["revision_number"],
            "sha256": digest,
            "byte_size": size,
        }

    def close(self) -> None:
        for path in self.owned_paths:
            self._unlink_managed(path)
        self.owned_paths.clear()


class PresentationTransactionService:
    def __init__(self, storage: StorageManager, edits: PresentationEditService) -> None:
        self._storage = storage
        self._edits = edits

    @contextmanager
    def stage(
        self,
        *,
        project_id: str,
        document_id: str,
        expected_revision_id: str,
        operations: list[dict[str, Any]],
        resolve_operation: Callable[[PresentationEditService, str, dict[str, Any]], dict[str, Any]]
        | None = None,
    ) -> Iterator[StagedPresentationPlan]:
        if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_PLAN_OPERATIONS:
            raise invalid_request(
                "An edit plan needs between 1 and 20 operations.", field="operations"
            )
        source = self._edits._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._edits._revision_conflict()
        editor = _StagingEditor(self._storage, project_id, document_id, source)
        outcomes: list[dict[str, Any]] = []

        def reference(value: Any, field: str) -> Any:
            if not isinstance(value, dict):
                return value
            if set(value) != {"created_by"}:
                raise invalid_request("An edit target reference needs only created_by.")
            step = value["created_by"]
            if type(step) is not int or not 1 <= step <= len(outcomes):
                raise invalid_request("An edit target must reference an earlier creation step.")
            key = "created_object_id" if field == "object_id" else "created_slide_id"
            identity = outcomes[step - 1].get(key)
            if not isinstance(identity, str):
                raise invalid_request("The referenced step did not create this kind of target.")
            return identity

        try:
            for operation in operations:
                if not isinstance(operation, dict):
                    raise invalid_request(
                        "Each edit operation must be an object.", field="operations"
                    )
                reject_unknown_fields(operation, {"type", "params"})
                kind, params = operation.get("type"), operation.get("params")
                if (
                    not isinstance(kind, str)
                    or kind not in PLAN_OPERATIONS
                    or not isinstance(params, dict)
                ):
                    raise invalid_request(
                        "This edit operation is not supported.", field="operations"
                    )
                if {"project_id", "document_id", "expected_revision_id"}.intersection(params):
                    raise invalid_request("Operation parameters cannot override the plan's scope.")
                params = dict(params)
                for field in ("slide_id", "layout_source_slide_id", "object_id"):
                    if field in params:
                        params[field] = reference(params[field], field)
                if kind == "group_objects" and isinstance(params.get("objects"), list):
                    params["objects"] = [
                        {**item, "object_id": reference(item.get("object_id"), "object_id")}
                        if isinstance(item, dict)
                        else item
                        for item in params["objects"]
                    ]
                if isinstance(params.get("ordered_slide_ids"), list):
                    params["ordered_slide_ids"] = [
                        reference(value, "slide_id") for value in params["ordered_slide_ids"]
                    ]
                if resolve_operation is not None:
                    params = resolve_operation(editor, kind, params)
                result = getattr(editor, kind)(
                    {
                        **params,
                        "project_id": project_id,
                        "document_id": document_id,
                        "expected_revision_id": expected_revision_id,
                    }
                )
                outcomes.append({"type": kind, **result})
            path = self._storage.paths.snapshot_path(
                project_id, str(editor.source["local_snapshot_path"]), require_exists=True
            )
            # Validate the final composition, including interactions between edits.
            with path.open("rb") as handle:
                inspect_pptx_snapshot(
                    handle,
                    document_id=document_id,
                    expected_sha256=str(editor.source["sha256"]),
                    byte_size=int(editor.source["byte_size"]),
                )
            current = self._edits._current_revision_source(project_id, document_id)
            if current["revision_id"] != expected_revision_id:
                raise self._edits._revision_conflict()
            yield StagedPresentationPlan(
                path,
                str(editor.source["sha256"]),
                int(editor.source["byte_size"]),
                any(item["changed"] for item in outcomes),
                tuple(outcomes),
            )
        finally:
            editor.close()

    def apply(
        self,
        *,
        project_id: str,
        document_id: str,
        expected_revision_id: str,
        operations: list[dict[str, Any]],
        on_commit: Callable[[sqlite3.Connection, str], None] | None = None,
    ) -> dict[str, Any]:
        with self.stage(
            project_id=project_id,
            document_id=document_id,
            expected_revision_id=expected_revision_id,
            operations=operations,
        ) as staged:
            return self.publish(
                project_id=project_id,
                document_id=document_id,
                expected_revision_id=expected_revision_id,
                staged=staged,
                on_commit=on_commit,
            )

    def publish(
        self,
        *,
        project_id: str,
        document_id: str,
        expected_revision_id: str,
        staged: StagedPresentationPlan,
        on_commit: Callable[[sqlite3.Connection, str], None] | None = None,
    ) -> dict[str, Any]:
        """Publish the exact reviewed bytes, with a final integrity and head check."""
        source = self._edits._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._edits._revision_conflict()
        # Require an authoritative flat managed snapshot even for internal callers.
        path = self._storage.paths.snapshot_path(
            project_id, f"sources/{staged.path.name}", require_exists=True
        )
        if path != staged.path:
            raise invalid_request("The preview does not belong to this project.")
        with path.open("rb") as handle:
            inspect_pptx_snapshot(
                handle,
                document_id=document_id,
                expected_sha256=staged.sha256,
                byte_size=staged.byte_size,
            )

        def write(_original: Path, target: Path) -> bool:
            if not staged.changed:
                return False
            try:
                shutil.copyfile(path, target)
                if (
                    target.stat().st_size != staged.byte_size
                    or self._edits._sha256_path(target) != staged.sha256
                ):
                    raise CoreDomainError(
                        "SOURCE_SNAPSHOT_CHANGED", "The reviewed preview changed."
                    )
            except (OSError, CoreDomainError):
                self._edits._unlink_managed(target)
                raise
            return True

        result = self._edits._commit_revision(
            project_id, document_id, expected_revision_id, source, write, on_commit=on_commit
        )
        return {
            **result,
            "operations": [
                {
                    key: outcome[key]
                    for key in (
                        "type",
                        "changed",
                        "object_id",
                        "slide_id",
                        "created_slide_id",
                        "created_object_id",
                        "created_object_ids",
                        "selected_object_ids",
                    )
                    if key in outcome
                }
                for outcome in staged.outcomes
            ],
        }
