"""Immutable, project-local raster uploads independent of presentation revisions."""

from __future__ import annotations

import base64
import hashlib
import io
from datetime import UTC, datetime
from typing import Any

from PIL import Image

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.editing import PresentationEditService
from presenter_core.storage.service import StorageManager


class ProjectPictureAssetService:
    def __init__(self, storage: StorageManager, edits: PresentationEditService) -> None:
        self._storage, self._edits = storage, edits

    def _id(self, value: Any) -> str:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise invalid_request("Choose a valid project picture.")
        return value

    def _metadata(self, row: Any, *, thumbnail: bool) -> dict[str, Any]:
        data = bytes(row["image_bytes"])
        if len(data) != row["byte_size"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise CoreDomainError(
                "PROJECT_ASSET_CHANGED", "The stored project picture failed its integrity check."
            )
        encoded = base64.b64encode(data).decode("ascii")
        self._edits._replacement_image_field(encoded)
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            result = {
                key: row[key] for key in ("asset_id", "name", "sha256", "mime_type", "byte_size")
            }
            result.update(width=width, height=height)
            if thumbnail:
                image.thumbnail((128, 128))
                output = io.BytesIO()
                image.convert("RGBA").save(output, format="PNG")
                result["thumbnail_base64"] = base64.b64encode(output.getvalue()).decode("ascii")
            else:
                result["image_base64"] = encoded
            return result

    def import_picture(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "name", "image_base64"})
        project = self._edits._project_id(params.get("project_id"))
        name = self._edits._text_field(params.get("name"), "name").strip()
        if not name or len(name) > 120:
            raise invalid_request("Give this picture a name of 1-120 characters.")
        data, image_format = self._edits._replacement_image_field(params.get("image_base64"))
        sha = hashlib.sha256(data).hexdigest()
        asset_id = hashlib.sha256((project + "\0" + sha).encode("utf-8")).hexdigest()
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM project_picture_assets WHERE sha256 = ?", (sha,)
            ).fetchone()
            if existing is None:
                count, size = connection.execute(
                    "SELECT COUNT(*), COALESCE(SUM(byte_size), 0) FROM project_picture_assets"
                ).fetchone()
                if count >= 200 or size + len(data) > 64 * 1024 * 1024:
                    raise CoreDomainError(
                        "PROJECT_ASSET_LIMIT",
                        "Project pictures are limited to 200 images and 64 MiB total.",
                    )
                connection.execute(
                    "INSERT INTO project_picture_assets VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        asset_id,
                        name,
                        sha,
                        "image/png" if image_format == "PNG" else "image/jpeg",
                        len(data),
                        data,
                        datetime.now(UTC).isoformat(),
                    ),
                )
            row = connection.execute(
                "SELECT * FROM project_picture_assets WHERE sha256 = ?", (sha,)
            ).fetchone()
            result = self._metadata(row, thumbnail=True)
            connection.commit()
        return {"project_id": project, "created": existing is None, "asset": result}

    def list_pictures(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "cursor"})
        project = self._edits._project_id(params.get("project_id"))
        cursor = params.get("cursor", 0)
        if type(cursor) is not int or cursor < 0:
            raise invalid_request("Provide a valid project picture cursor.")
        with self._storage.project_database(project) as connection:
            total = connection.execute("SELECT COUNT(*) FROM project_picture_assets").fetchone()[0]
            if cursor > total:
                raise invalid_request("The project picture cursor is outside the library.")
            rows = connection.execute(
                "SELECT * FROM project_picture_assets "
                "ORDER BY created_at, asset_id LIMIT 20 OFFSET ?",
                (cursor,),
            ).fetchall()
            assets, budget = [], 16 * 1024 * 1024
            for row in rows:
                if row["byte_size"] > budget:
                    break
                assets.append(self._metadata(row, thumbnail=True))
                budget -= row["byte_size"]
        next_cursor = cursor + len(assets)
        return {
            "project_id": project,
            "assets": assets,
            "skipped": 0,
            "has_more": next_cursor < total,
            "next_cursor": next_cursor if next_cursor < total else None,
        }

    def read_picture(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "asset_id"})
        project, asset_id = (
            self._edits._project_id(params.get("project_id")),
            self._id(params.get("asset_id")),
        )
        with self._storage.project_database(project) as connection:
            row = connection.execute(
                "SELECT * FROM project_picture_assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            if row is None:
                raise CoreDomainError(
                    "PROJECT_ASSET_NOT_FOUND", "This picture is not in the selected project."
                )
            return {"project_id": project, **self._metadata(row, thumbnail=False)}

    def delete_picture(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "asset_id", "expected_sha256", "confirm"})
        project, asset_id = (
            self._edits._project_id(params.get("project_id")),
            self._id(params.get("asset_id")),
        )
        if params.get("confirm") is not True:
            raise invalid_request("Confirm removing the picture from this project library.")
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM project_picture_assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            if row is None:
                raise CoreDomainError(
                    "PROJECT_ASSET_NOT_FOUND", "This picture is not in the selected project."
                )
            if row["sha256"] != params.get("expected_sha256"):
                raise invalid_request("The selected picture changed.")
            connection.execute("DELETE FROM project_picture_assets WHERE asset_id = ?", (asset_id,))
            connection.commit()
        return {"project_id": project, "asset_id": asset_id, "deleted": True}
