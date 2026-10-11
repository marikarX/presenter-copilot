"""Set a slide's own background: a solid color, a two-color linear gradient, a picture
from the project library stretched over the slide, or the layout background."""

from __future__ import annotations

import base64
import copy
import posixpath
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    DRAWING_NS,
    PACKAGE_REL_NS,
    PRESENTATION_NS,
    REL_NS,
    FidelityBackground,
    _parse_xml_part,
    inspect_pptx_snapshot,
    slide_background,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

P = f"{{{PRESENTATION_NS}}}"
A = f"{{{DRAWING_NS}}}"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
STATES = {"inherited", "theme_reference", "solid", "gradient", "picture", "custom"}


def background_payload(background: FidelityBackground) -> dict[str, Any]:
    return {
        "state": background.state,
        "color": background.color,
        "end_color": background.end_color,
        "angle": background.angle,
    }


def _expected(value: Any) -> FidelityBackground:
    if not isinstance(value, dict) or not {"state", "color"} <= set(value) <= {
        "state",
        "color",
        "end_color",
        "angle",
    }:
        raise invalid_request(
            "expected_background must contain state and color.", field="expected_background"
        )
    state, color = value["state"], value["color"]
    end, angle = value.get("end_color"), value.get("angle")
    valid = state in STATES and (
        (state in {"inherited", "theme_reference", "picture", "custom"} and color is None)
        or (state == "solid" and isinstance(color, str) and COLOR.fullmatch(color))
        or (state == "gradient" and isinstance(color, str) and COLOR.fullmatch(color))
    )
    if state == "gradient":
        valid = valid and isinstance(end, str) and bool(COLOR.fullmatch(end))
        valid = valid and type(angle) is int and 0 <= angle < 360
    elif end is not None or angle is not None:
        valid = False
    if not valid:
        raise invalid_request(
            "expected_background is not a supported background.", field="expected_background"
        )
    return FidelityBackground(state=state, color=color, end_color=end, angle=angle)


def _replacement(params: dict[str, Any]) -> tuple[FidelityBackground, str | None]:
    color = params.get("replacement_color")
    gradient = params.get("replacement_gradient")
    picture = params.get("replacement_picture_asset_id")
    if sum(value is not None for value in (color, gradient, picture)) > 1:
        raise invalid_request("Choose one background: a color, a gradient or a picture.")
    if color is not None:
        if not isinstance(color, str) or not COLOR.fullmatch(color):
            raise invalid_request(
                "replacement_color must be a #RRGGBB color or null to use the layout background.",
                field="replacement_color",
            )
        return FidelityBackground(state="solid", color=color.upper()), None
    if gradient is not None:
        if (
            not isinstance(gradient, dict)
            or set(gradient) != {"start", "end", "angle"}
            or not all(
                isinstance(gradient[k], str) and COLOR.fullmatch(gradient[k])
                for k in ("start", "end")
            )
            or type(gradient["angle"]) is not int
            or not 0 <= gradient["angle"] < 360
        ):
            raise invalid_request(
                "replacement_gradient needs start and end #RRGGBB colors and an angle 0-359.",
                field="replacement_gradient",
            )
        return (
            FidelityBackground(
                state="gradient",
                color=gradient["start"].upper(),
                end_color=gradient["end"].upper(),
                angle=gradient["angle"],
            ),
            None,
        )
    if picture is not None:
        if not isinstance(picture, str):
            raise invalid_request(
                "Choose a picture from this project's library.",
                field="replacement_picture_asset_id",
            )
        return FidelityBackground(state="picture"), picture
    return FidelityBackground(state="inherited"), None


def set_slide_background(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive
    from presenter_core.presentation.project_assets import ProjectPictureAssetService

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "expected_background",
            "replacement_color",
            "replacement_gradient",
            "replacement_picture_asset_id",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    expected = _expected(params.get("expected_background"))
    replacement, asset_id = _replacement(params)
    picture: dict[str, Any] | None = None
    if asset_id is not None:
        picture = ProjectPictureAssetService(editor._storage, editor).read_picture(
            {"project_id": project, "asset_id": asset_id}
        )
    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()
    source_path = editor._storage.paths.snapshot_path(
        project, source["local_snapshot_path"], require_exists=True
    )
    with source_path.open("rb") as handle:
        fidelity = inspect_pptx_snapshot(
            handle,
            document_id=document,
            expected_sha256=source["sha256"],
            byte_size=source["byte_size"],
        )
    slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
    if slide is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
        )
    if slide.background is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            "This slide's background is not well formed and stays read-only.",
        )
    if slide.background != expected:
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The slide background changed. Refresh the preview and try again.",
            retryable=True,
        )
    # Any picture differs from the current one; other states compare by value.
    if replacement == expected and picture is None:
        return {
            "changed": False,
            "revision_id": source["revision_id"],
            "revision_number": int(source["revision_number"]),
            "sha256": source["sha256"],
            "byte_size": int(source["byte_size"]),
        }
    directory, name = posixpath.split(slide.part_name)
    rels_part = f"{directory}/_rels/{name}.rels"

    def write(original: Path, target: Path) -> bool:
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            members = {info.filename: info for info in archive.infolist()}
            root = _parse_xml_part(archive, members[slide.part_name])
            if slide_background(root) != expected:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET",
                    "The slide background changed. Refresh the preview and try again.",
                    retryable=True,
                )
            common = root.find(f"{P}cSld")
            if common is None:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED", "This slide has no common slide data."
                )
            rels = (
                _parse_xml_part(archive, members[rels_part])
                if rels_part in members
                else etree.Element(
                    f"{{{PACKAGE_REL_NS}}}Relationships", nsmap={None: PACKAGE_REL_NS}
                )
            )
            # A replaced background picture's relationship goes with it.
            previous = {
                value
                for old in common.findall(f"{P}bg")
                for element in old.iter()
                for key, value in element.attrib.items()
                if key.startswith(f"{{{REL_NS}}}")
            }
            for existing in common.findall(f"{P}bg"):
                common.remove(existing)
            additions: dict[str, bytes] = {}
            types = None
            if replacement.state != "inherited":
                background = etree.Element(f"{P}bg")
                properties = etree.SubElement(background, f"{P}bgPr")
                if replacement.state == "solid":
                    fill = etree.SubElement(properties, f"{A}solidFill")
                    etree.SubElement(fill, f"{A}srgbClr", val=(replacement.color or "")[1:])
                elif replacement.state == "gradient":
                    fill = etree.SubElement(properties, f"{A}gradFill", rotWithShape="1")
                    stops = etree.SubElement(fill, f"{A}gsLst")
                    for position, value in (
                        ("0", replacement.color),
                        ("100000", replacement.end_color),
                    ):
                        stop = etree.SubElement(stops, f"{A}gs", pos=position)
                        etree.SubElement(stop, f"{A}srgbClr", val=(value or "")[1:])
                    etree.SubElement(
                        fill,
                        f"{A}lin",
                        ang=str((replacement.angle or 0) * 60000),
                        scaled="0",
                    )
                else:
                    assert picture is not None
                    extension = ".png" if picture["mime_type"] == "image/png" else ".jpeg"
                    media = f"ppt/media/copilot-background-{uuid.uuid4().hex}{extension}"
                    additions[media] = base64.b64decode(picture["image_base64"])
                    used = {item.get("Id") for item in rels}
                    number = 1
                    while f"rIdBackground{number}" in used:
                        number += 1
                    rid = f"rIdBackground{number}"
                    etree.SubElement(
                        rels,
                        f"{{{PACKAGE_REL_NS}}}Relationship",
                        Id=rid,
                        Type=f"{REL_NS}/image",
                        Target=posixpath.relpath(media, directory),
                    )
                    types = _parse_xml_part(archive, members["[Content_Types].xml"])
                    etree.SubElement(
                        types,
                        f"{{{CT}}}Override",
                        PartName="/" + media,
                        ContentType=picture["mime_type"],
                    )
                    fill = etree.SubElement(properties, f"{A}blipFill", dpi="0", rotWithShape="1")
                    etree.SubElement(fill, f"{A}blip").set(f"{{{REL_NS}}}embed", rid)
                    etree.SubElement(fill, f"{A}srcRect")
                    etree.SubElement(etree.SubElement(fill, f"{A}stretch"), f"{A}fillRect")
                etree.SubElement(properties, f"{A}effectLst")
                common.insert(0, background)
            referenced = {
                value
                for element in root.iter()
                for key, value in element.attrib.items()
                if key.startswith(f"{{{REL_NS}}}")
            }
            for relationship in list(rels):
                if relationship.get("Id") in previous - referenced:
                    rels.remove(relationship)
            rewritten = {
                slide.part_name: etree.tostring(
                    root, encoding="UTF-8", xml_declaration=True, standalone=True
                ),
            }
            if previous or additions:
                rewritten[rels_part] = etree.tostring(
                    rels, encoding="UTF-8", xml_declaration=True, standalone=True
                )
            if types is not None:
                rewritten["[Content_Types].xml"] = etree.tostring(
                    types, encoding="UTF-8", xml_declaration=True, standalone=True
                )
            with zipfile.ZipFile(target, "w", allowZip64=True) as output:
                output.comment = archive.comment
                for info in archive.infolist():
                    payload = rewritten.pop(info.filename, None)
                    if payload is not None:
                        output.writestr(copy.copy(info), payload)
                    else:
                        with (
                            archive.open(info) as reader,
                            output.open(copy.copy(info), "w") as writer,
                        ):
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
                for part, payload in {**rewritten, **additions}.items():
                    output.writestr(part, payload, compress_type=zipfile.ZIP_DEFLATED)
        with target.open("rb") as handle:
            updated = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=editor._sha256_path(target),
                byte_size=target.stat().st_size,
            )
        revised = next((item for item in updated.slides if item.slide_id == slide_id), None)
        if (
            revised is None
            or revised.background != replacement
            or [item.slide_id for item in updated.slides]
            != [item.slide_id for item in fidelity.slides]
            or {item.object_id: item for page in updated.slides for item in page.objects}
            != {item.object_id: item for page in fidelity.slides for item in page.objects}
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The slide background edit did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "slide_id": slide_id, "background": background_payload(replacement)}
