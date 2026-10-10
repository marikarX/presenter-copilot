"""Give a slide without a title one (PowerPoint Accessibility Checker: "Missing slide title").

An empty title placeholder receives the text; otherwise a title placeholder is added first
in reading order and inherits its position from the layout or master.
"""

from __future__ import annotations

import copy
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    DRAWING_NS,
    PRESENTATION_NS,
    _parse_xml_part,
    inspect_pptx_snapshot,
    placeholder_geometry_map,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

P = f"{{{PRESENTATION_NS}}}"
A = f"{{{DRAWING_NS}}}"
MAX_TITLE = 255


def _title_shapes(root: etree._Element) -> list[etree._Element]:
    return [
        shape
        for shape in root.iter(f"{P}sp")
        if (placeholder := shape.find(f"{P}nvSpPr/{P}nvPr/{P}ph")) is not None
        and placeholder.get("type") in {"title", "ctrTitle"}
    ]


def _title_text(root: etree._Element) -> str:
    return " ".join("".join(shape.itertext()).strip() for shape in _title_shapes(root)).strip()


def _write_text(shape: etree._Element, text: str) -> None:
    body = shape.find(f"{P}txBody")
    if body is None:
        body = etree.SubElement(shape, f"{P}txBody")
    for child in list(body):
        if child.tag == f"{A}p":
            body.remove(child)
    if body.find(f"{A}bodyPr") is None:
        body.insert(0, etree.Element(f"{A}bodyPr"))
    if body.find(f"{A}lstStyle") is None:
        body.insert(1, etree.Element(f"{A}lstStyle"))
    paragraph = etree.SubElement(body, f"{A}p")
    run = etree.SubElement(paragraph, f"{A}r")
    etree.SubElement(run, f"{A}rPr", lang="en-US", dirty="0")
    etree.SubElement(run, f"{A}t").text = text


def set_slide_title(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params, {"project_id", "document_id", "expected_revision_id", "slide_id", "title"}
    )
    title = params.get("title")
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title) > MAX_TITLE
        or any(ord(character) < 32 for character in title)
    ):
        raise invalid_request(
            f"title must be one line of text up to {MAX_TITLE} characters.", field="title"
        )
    title = title.strip()
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
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
    slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
    if slide is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
        )

    def write(original: Path, target: Path) -> bool:
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            if _title_text(root):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET",
                    "This slide already has a title. Refresh and edit it instead.",
                    retryable=True,
                )
            existing = _title_shapes(root)
            if existing:
                _write_text(existing[0], title)
            else:
                tree = root.find(f"{P}cSld/{P}spTree")
                if tree is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED", "This slide has no shape tree."
                    )
                ids = [
                    int(value)
                    for value in tree.xpath(".//p:cNvPr/@id", namespaces={"p": PRESENTATION_NS})
                    if str(value).isdigit()
                ]
                shape = etree.Element(f"{P}sp")
                nonvisual = etree.SubElement(shape, f"{P}nvSpPr")
                etree.SubElement(
                    nonvisual, f"{P}cNvPr", id=str(max(ids, default=1) + 1), name="Title"
                )
                locks = etree.SubElement(nonvisual, f"{P}cNvSpPr")
                etree.SubElement(locks, f"{A}spLocks", noGrp="1")
                properties = etree.SubElement(nonvisual, f"{P}nvPr")
                etree.SubElement(properties, f"{P}ph", type="title")
                shape_properties = etree.SubElement(shape, f"{P}spPr")
                inherited = placeholder_geometry_map(
                    archive, {i.filename: i for i in archive.infolist()}, slide.part_name
                )
                if not ({"title", "ctrTitle"} & set(inherited.get("type", {}))):
                    # PowerPoint gives a placeholder no position unless the layout has a
                    # matching one: place it where the master's title sits.
                    master = inherited.get("master", {}).get("title")
                    if master is None:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_UNSUPPORTED",
                            "This slide's layout and master have no title position.",
                        )
                    transform = etree.SubElement(shape_properties, f"{A}xfrm")
                    etree.SubElement(transform, f"{A}off", x=str(master.x_emu), y=str(master.y_emu))
                    etree.SubElement(
                        transform,
                        f"{A}ext",
                        cx=str(master.width_emu),
                        cy=str(master.height_emu),
                    )
                _write_text(shape, title)
                # First drawable child: screen readers read the title first.
                anchor = next(
                    (child for child in tree if child.tag not in {f"{P}nvGrpSpPr", f"{P}grpSpPr"}),
                    None,
                )
                if anchor is None:
                    tree.append(shape)
                else:
                    anchor.addprevious(shape)
            rewritten = etree.tostring(
                root, encoding="UTF-8", xml_declaration=True, standalone=True
            )
            with zipfile.ZipFile(target, "w", allowZip64=True) as output:
                output.comment = archive.comment
                for info in archive.infolist():
                    if info.filename == slide.part_name:
                        output.writestr(copy.copy(info), rewritten)
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
        revised = next((item for item in updated.slides if item.slide_id == slide_id), None)
        before = {o.object_id: o for page in fidelity.slides for o in page.objects}
        after = {o.object_id: o for page in updated.slides for o in page.objects}
        with zipfile.ZipFile(target) as archive:
            written = (
                _title_text(_parse_xml_part(archive, archive.getinfo(revised.part_name)))
                if revised is not None
                else ""
            )
        unchanged = all(
            after.get(identity) is not None and (after[identity].text == obj.text or obj.text == "")
            for identity, obj in before.items()
        )
        if written != title or not unchanged:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The slide title edit did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "slide_id": slide_id, "title": title}
