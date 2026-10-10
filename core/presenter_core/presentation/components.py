"""Named, reusable object selections. A component references objects on one slide of an
immutable presentation revision, so inserting it reuses the reviewed paste path."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.editing import PresentationEditService
from presenter_core.presentation.fidelity import inspect_pptx_snapshot
from presenter_core.storage.service import StorageManager

COMPONENT_LIMIT = 200


class PresentationComponentService:
    def __init__(self, storage: StorageManager, edits: PresentationEditService) -> None:
        self._storage, self._edits = storage, edits

    def _row(self, row: Any) -> dict[str, Any]:
        return {
            "component_id": row["id"],
            "name": row["name"],
            "document_id": row["presentation_id"],
            "revision_id": row["revision_id"],
            "slide_id": row["slide_id"],
            "object_ids": json.loads(row["object_ids_json"]),
            "names": json.loads(row["names_json"]),
            "created_at": row["created_at"],
        }

    def save_component(self, params: dict[str, Any]) -> dict[str, Any]:
        edits = self._edits
        reject_unknown_fields(
            params, {"project_id", "document_id", "revision_id", "slide_id", "object_ids", "name"}
        )
        project = edits._project_id(params.get("project_id"))
        document = edits._document_id(params.get("document_id"))
        revision = edits._uuid_field(params.get("revision_id"), "revision_id")
        slide_id = edits._uuid_field(params.get("slide_id"), "slide_id")
        name = edits._text_field(params.get("name"), "name").strip()
        if not name or len(name) > 120:
            raise invalid_request("Give this component a name of 1-120 characters.")
        ids = params.get("object_ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 20:
            raise invalid_request("A component holds between 1 and 20 objects.")
        ids = [edits._uuid_field(value, "object_ids") for value in ids]
        if len(set(ids)) != len(ids):
            raise invalid_request("Component objects must have distinct identities.")
        source = edits._verified_revision(project, document, revision)
        path = self._storage.paths.snapshot_path(
            project, source["local_snapshot_path"], require_exists=True
        )
        with path.open("rb") as handle:
            fidelity = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=source["sha256"],
                byte_size=source["byte_size"],
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        found = {o.object_id: o for o in slide.objects} if slide is not None else {}
        selected = [found.get(object_id) for object_id in ids]
        if slide is None or any(o is None for o in selected):
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected objects are unavailable."
            )
        # The same eligibility paste_objects enforces, so every saved component inserts.
        if any(
            o is None
            or o.kind not in {"sp", "pic", "graphicFrame", "grpSp"}
            or o.group_child
            or not o.delete_editable
            or not o.geometry_editable
            or o.geometry is None
            for o in selected
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "The selection includes objects that cannot be reused safely.",
            )
        names = [o.name for o in selected if o is not None]
        component_id = str(uuid.uuid4())
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            (count,) = connection.execute("SELECT COUNT(*) FROM presentation_components").fetchone()
            if count >= COMPONENT_LIMIT:
                raise CoreDomainError(
                    "PRESENTATION_COMPONENT_LIMIT",
                    f"A project holds at most {COMPONENT_LIMIT} components.",
                )
            connection.execute(
                "INSERT INTO presentation_components VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    component_id,
                    name,
                    document,
                    revision,
                    slide_id,
                    json.dumps(ids),
                    json.dumps(names),
                    datetime.now(UTC).isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM presentation_components WHERE id = ?", (component_id,)
            ).fetchone()
            connection.commit()
        return {"project_id": project, "component": self._row(row)}

    def list_components(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id"})
        project = self._edits._project_id(params.get("project_id"))
        with self._storage.project_database(project) as connection:
            rows = connection.execute(
                "SELECT * FROM presentation_components ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return {"project_id": project, "components": [self._row(row) for row in rows]}

    def delete_component(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "component_id"})
        project = self._edits._project_id(params.get("project_id"))
        component = self._edits._uuid_field(params.get("component_id"), "component_id")
        with self._storage.project_database(project) as connection:
            deleted = connection.execute(
                "DELETE FROM presentation_components WHERE id = ?", (component,)
            ).rowcount
            connection.commit()
        if not deleted:
            raise CoreDomainError(
                "PRESENTATION_COMPONENT_NOT_FOUND", "That component was not found."
            )
        return {"project_id": project, "component_id": component, "deleted": True}
