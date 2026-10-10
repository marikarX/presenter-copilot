"""Set what clicking a shape, picture or group does in a slide show: open a web link,
jump to a slide, go to the next/previous/first/last slide, or nothing."""

from __future__ import annotations

import copy
import dataclasses
import posixpath
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    DRAWING_NS,
    HYPERLINK_REL_TYPE,
    REL_NS,
    SHOW_JUMP_ACTION,
    SHOW_JUMPS,
    SLIDE_JUMP_ACTION,
    SLIDE_REL_TYPE,
    FidelityClickAction,
    _parse_xml_part,
    inspect_pptx_snapshot,
    object_click_action,
    slide_hyperlink_targets,
)
from presenter_core.presentation.text_hyperlinks import hyperlink_url

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

A = f"{{{DRAWING_NS}}}"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
KINDS = {"none", "url", "slide", "next", "previous", "first", "last"}


def _action(value: Any, field: str, slide_ids: set[str]) -> FidelityClickAction:
    if not isinstance(value, dict) or set(value) != {"kind", "url", "slide_id"}:
        raise invalid_request(f"{field} must contain kind, url and slide_id.", field=field)
    kind = value["kind"]
    if kind not in KINDS:
        raise invalid_request(f"{field}.kind must be one of {sorted(KINDS)}.", field=field)
    url = hyperlink_url(value["url"], f"{field}.url") if kind == "url" else None
    slide_id = value["slide_id"] if kind == "slide" else None
    if (kind == "url") != (url is not None) or (kind == "slide" and slide_id not in slide_ids):
        raise invalid_request(f"{field} needs a valid url or slide for its kind.", field=field)
    if kind not in {"url", "slide"} and (value["url"] is not None or value["slide_id"] is not None):
        raise invalid_request(f"{field} sets url or slide_id only for those kinds.", field=field)
    return FidelityClickAction(kind=kind, url=url, slide_id=slide_id)


def set_click_action(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "object_id",
            "expected_click_action",
            "click_action",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    object_id = editor._uuid_field(params.get("object_id"), "object_id")
    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()
    path = editor._storage.paths.snapshot_path(
        project, source["local_snapshot_path"], require_exists=True
    )
    with path.open("rb") as handle:
        fidelity = inspect_pptx_snapshot(
            handle,
            document_id=document,
            expected_sha256=source["sha256"],
            byte_size=source["byte_size"],
        )
    slide_parts = {item.slide_id: item.part_name for item in fidelity.slides}
    part_ids = {item.part_name: item.slide_id for item in fidelity.slides}
    expected = _action(
        params.get("expected_click_action"), "expected_click_action", set(slide_parts)
    )
    replacement = _action(params.get("click_action"), "click_action", set(slide_parts))
    slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
    obj = (
        next((item for item in slide.objects if item.object_id == object_id), None)
        if slide is not None
        else None
    )
    if slide is None or obj is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected object is unavailable."
        )
    if obj.click_action is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED", "This object's click action stays read-only."
        )
    if obj.click_action != expected:
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The click action changed. Refresh and try again.",
            retryable=True,
        )
    if replacement == expected:
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
            rels = _parse_xml_part(archive, members[rels_part])
            node = editor._find_object_node(
                root, ooxml_id=obj.ooxml_id, kind=obj.kind, include_group_children=True
            )
            nonvisual = node.xpath(
                "./*[local-name()='nvSpPr' or local-name()='nvPicPr' or "
                "local-name()='nvGrpSpPr']/*[local-name()='cNvPr']"
            )[0]
            targets = slide_hyperlink_targets(archive, members, slide.part_name, part_ids)
            if object_click_action(nonvisual, targets) != expected:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET",
                    "The click action changed. Refresh and try again.",
                    retryable=True,
                )
            previous = {
                link.get(f"{{{REL_NS}}}id", "") for link in nonvisual.findall(f"{A}hlinkClick")
            }
            for link in nonvisual.findall(f"{A}hlinkClick"):
                nonvisual.remove(link)
            if replacement.kind != "none":
                link = etree.Element(f"{A}hlinkClick")
                if replacement.kind in {"url", "slide"}:
                    used = {item.get("Id") for item in rels}
                    number = 1
                    while f"rId{number}" in used:
                        number += 1
                    relationship = etree.SubElement(
                        rels, f"{{{PACKAGE_REL_NS}}}Relationship", Id=f"rId{number}"
                    )
                    if replacement.kind == "url":
                        relationship.set("Type", HYPERLINK_REL_TYPE)
                        relationship.set("Target", replacement.url or "")
                        relationship.set("TargetMode", "External")
                    else:
                        relationship.set("Type", SLIDE_REL_TYPE)
                        relationship.set(
                            "Target",
                            posixpath.relpath(slide_parts[replacement.slide_id or ""], directory),
                        )
                        link.set("action", SLIDE_JUMP_ACTION)
                    link.set(f"{{{REL_NS}}}id", f"rId{number}")
                else:
                    jump = next(
                        key for key, value in SHOW_JUMPS.items() if value == replacement.kind
                    )
                    link.set(f"{{{REL_NS}}}id", "")
                    link.set("action", SHOW_JUMP_ACTION + jump)
                # Schema order: hlinkClick comes first among cNvPr's children.
                nonvisual.insert(0, link)
            referenced = {
                value
                for element in root.iter()
                for key, value in element.attrib.items()
                if key.startswith(f"{{{REL_NS}}}")
            }
            for relationship in list(rels):
                if relationship.get("Id") in previous - referenced - {""}:
                    rels.remove(relationship)
            rewritten = {
                slide.part_name: etree.tostring(
                    root, encoding="UTF-8", xml_declaration=True, standalone=True
                ),
                rels_part: etree.tostring(
                    rels, encoding="UTF-8", xml_declaration=True, standalone=True
                ),
            }
            with zipfile.ZipFile(target, "w", allowZip64=True) as output:
                output.comment = archive.comment
                for info in archive.infolist():
                    if info.filename in rewritten:
                        output.writestr(copy.copy(info), rewritten[info.filename])
                    else:
                        with (
                            archive.open(info) as reader,
                            output.open(copy.copy(info), "w") as writer,
                        ):
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
        with target.open("rb") as handle:
            updated = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=editor._sha256_path(target),
                byte_size=target.stat().st_size,
            )
        before = {o.object_id: o for page in fidelity.slides for o in page.objects}
        after = {o.object_id: o for page in updated.slides for o in page.objects}
        revised = after.get(object_id)
        if (
            revised is None
            or revised.click_action != replacement
            or dataclasses.replace(revised, click_action=obj.click_action) != obj
            or {k: v for k, v in after.items() if k != object_id}
            != {k: v for k, v in before.items() if k != object_id}
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The click action edit did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {
        **result,
        "slide_id": slide_id,
        "object_id": object_id,
        "click_action": dataclasses.asdict(replacement),
    }
