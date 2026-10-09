"""Read bounded reusable raster assets from a verified presentation revision."""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from PIL import Image

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService


def picture_assets(
    editor: PresentationEditService, params: dict[str, Any], *, read: bool
) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {"project_id", "document_id", "expected_revision_id", "asset_id" if read else "cursor"},
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()
    cursor = params.get("cursor", 0)
    asset_id = params.get("asset_id")
    if read:
        if (
            not isinstance(asset_id, str)
            or len(asset_id) != 64
            or any(c not in "0123456789abcdef" for c in asset_id)
        ):
            raise invalid_request("Choose a picture from this revision.")
    elif type(cursor) is not int or cursor < 0:
        raise invalid_request("Provide a valid picture cursor.")
    path = editor._storage.paths.snapshot_path(
        project, source["local_snapshot_path"], require_exists=True
    )
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        candidates = sorted(
            (
                info
                for info in archive.infolist()
                if info.filename.startswith("ppt/media/") and not info.is_dir()
            ),
            key=lambda info: info.filename,
        )

        def identity(name: str) -> str:
            return hashlib.sha256((str(source["sha256"]) + "\0" + name).encode("utf-8")).hexdigest()

        if read:
            chosen = next(
                (info for info in candidates if identity(info.filename) == asset_id), None
            )
            if chosen is None:
                raise CoreDomainError(
                    "PRESENTATION_ASSET_NOT_FOUND",
                    "This picture is unavailable in the selected revision.",
                )
            selected = [chosen]
        else:
            if cursor > len(candidates):
                raise invalid_request("The picture cursor is outside this revision.")
            selected = candidates[cursor:]
        assets: list[dict[str, Any]] = []
        skipped = 0
        consumed = cursor
        budget = 16 * 1024 * 1024
        for info in selected:
            if len(assets) >= 20 or consumed - cursor >= 100:
                break
            if info.file_size > budget and info.file_size <= 4 * 1024 * 1024:
                break
            consumed += 1
            if not 1 <= info.file_size <= 4 * 1024 * 1024 or PurePosixPath(
                info.filename
            ).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                if read:
                    raise invalid_request("Choose a single-frame PNG or JPEG no larger than 4 MiB.")
                skipped += 1
                continue
            budget -= info.file_size
            encoded = base64.b64encode(archive.read(info)).decode("ascii")
            try:
                data, image_format = editor._replacement_image_field(encoded)
            except CoreDomainError:
                if read:
                    raise
                skipped += 1
                continue
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                metadata = {
                    "asset_id": identity(info.filename),
                    "name": PurePosixPath(info.filename).name,
                    "mime_type": "image/png" if image_format == "PNG" else "image/jpeg",
                    "byte_size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "width": width,
                    "height": height,
                }
                if read:
                    return {"revision_id": revision, **metadata, "image_base64": encoded}
                image.thumbnail((128, 128))
                thumb = io.BytesIO()
                image.convert("RGBA").save(thumb, format="PNG")
                assets.append(
                    {
                        **metadata,
                        "thumbnail_base64": base64.b64encode(thumb.getvalue()).decode("ascii"),
                    }
                )
        return {
            "revision_id": revision,
            "assets": assets,
            "skipped": skipped,
            "has_more": consumed < len(candidates),
            "next_cursor": consumed if consumed < len(candidates) else None,
        }
