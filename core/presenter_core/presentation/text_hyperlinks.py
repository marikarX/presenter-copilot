"""Add, change or remove one external click link across a text shape's runs."""

from __future__ import annotations

import copy
import posixpath
import shutil
import urllib.parse
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    DRAWING_NS,
    HYPERLINK_REL_TYPE,
    REL_NS,
    FidelityHyperlink,
    _parse_xml_part,
    inspect_pptx_snapshot,
    shape_hyperlink,
    slide_hyperlink_targets,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

A = f"{{{DRAWING_NS}}}"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MAX_URL_CHARS = 2048
_FOLLOWING_LINK = {f"{A}hlinkMouseOver", f"{A}rtl", f"{A}extLst"}


def hyperlink_url(value: Any, field: str) -> str | None:
    """Only web and mail links; never file, script or relative targets."""
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= MAX_URL_CHARS
        or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        )
    ):
        raise invalid_request(f"{field} must be a link without spaces.", field=field)
    parsed = urllib.parse.urlsplit(value)
    scheme = parsed.scheme.lower()
    if not (
        scheme in {"http", "https"} and parsed.netloc or scheme == "mailto" and "@" in parsed.path
    ):
        raise invalid_request(f"{field} must be an http, https or mailto link.", field=field)
    return value


def set_text_hyperlink(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "object_id",
            "expected_text",
            "expected_url",
            "replacement_url",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    object_id = editor._uuid_field(params.get("object_id"), "object_id")
    expected_text = params.get("expected_text")
    if not isinstance(expected_text, str):
        raise invalid_request("expected_text must be a string.", field="expected_text")
    expected = FidelityHyperlink(url=hyperlink_url(params.get("expected_url"), "expected_url"))
    replacement = FidelityHyperlink(
        url=hyperlink_url(params.get("replacement_url"), "replacement_url")
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
    obj = (
        next((item for item in slide.objects if item.object_id == object_id), None)
        if slide
        else None
    )
    if slide is None or obj is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected text is unavailable."
        )
    if obj.hyperlink is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            "This text uses mixed, internal or hover links that stay read-only.",
        )
    if obj.text != expected_text or obj.hyperlink != expected:
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The text or its link changed. Refresh the preview and try again.",
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
            if rels_part not in members:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED", "This slide has no relationship part."
                )
            root = _parse_xml_part(archive, members[slide.part_name])
            rels = _parse_xml_part(archive, members[rels_part])
            node = editor._find_shape(root, obj.ooxml_id)
            if shape_hyperlink(
                node, slide_hyperlink_targets(archive, members, slide.part_name)
            ) != (expected):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET",
                    "The text link changed. Refresh the preview and try again.",
                    retryable=True,
                )
            runs = node.xpath(
                "./p:txBody/a:p/a:r | ./p:txBody/a:p/a:fld",
                namespaces={
                    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
                    "a": DRAWING_NS,
                },
            )
            previous: set[str] = set()
            for run in runs:
                properties = run.find(f"{A}rPr")
                if properties is None:
                    continue
                for link in properties.findall(f"{A}hlinkClick"):
                    previous.add(link.get(f"{{{REL_NS}}}id", ""))
                    properties.remove(link)
            if replacement.url is not None:
                used = {item.get("Id") for item in rels}
                number = 1
                while f"rId{number}" in used:
                    number += 1
                relationship_id = f"rId{number}"
                etree.SubElement(
                    rels,
                    f"{{{PACKAGE_REL_NS}}}Relationship",
                    Id=relationship_id,
                    Type=HYPERLINK_REL_TYPE,
                    Target=replacement.url,
                    TargetMode="External",
                )
                for run in runs:
                    properties = run.find(f"{A}rPr")
                    if properties is None:
                        properties = etree.Element(f"{A}rPr")
                        run.insert(0, properties)
                    link = etree.Element(f"{A}hlinkClick")
                    link.set(f"{{{REL_NS}}}id", relationship_id)
                    properties.insert(
                        next(
                            (
                                index
                                for index, child in enumerate(properties)
                                if child.tag in _FOLLOWING_LINK
                            ),
                            len(properties),
                        ),
                        link,
                    )
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
        revised_slide = next((item for item in updated.slides if item.slide_id == slide_id), None)
        revised = (
            next((item for item in revised_slide.objects if item.object_id == object_id), None)
            if revised_slide
            else None
        )
        if (
            revised is None
            or revised.hyperlink != replacement
            or revised.text != obj.text
            or [item.object_id for item in revised_slide.objects]  # type: ignore[union-attr]
            != [item.object_id for item in slide.objects]
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The text link edit did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "slide_id": slide_id, "object_id": object_id, "url": replacement.url}
