"""Deck-wide slide numbers and footer text, like PowerPoint's Header & Footer "Apply to All".

Each slide gets (or loses) slide-number and footer placeholders that point at its
layout's placeholders, so position and formatting stay inherited from the layout.
"""

from __future__ import annotations

import copy
import hashlib
import json
import posixpath
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    DRAWING_NS,
    PRESENTATION_NS,
    _parse_xml_part,
    _relationships,
    _resolve_internal_part,
    inspect_pptx_snapshot,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

P = f"{{{PRESENTATION_NS}}}"
A = f"{{{DRAWING_NS}}}"
LAYOUT_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
MAX_FOOTER_CHARS = 200


def _placeholder(shape: etree._Element) -> etree._Element | None:
    return shape.find(f"{P}nvSpPr/{P}nvPr/{P}ph")


def _typed(tree: etree._Element, kind: str) -> list[etree._Element]:
    return [
        shape
        for shape in tree.findall(f"{P}sp")
        if (ph := _placeholder(shape)) is not None and ph.get("type") == kind
    ]


def _text(shape: etree._Element) -> str:
    return "\n".join(
        "".join(t.text or "" for t in paragraph.iter(f"{A}t"))
        for paragraph in shape.findall(f"{P}txBody/{A}p")
    )


def _slide_layout(
    archive: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], slide_part: str
) -> etree._Element | None:
    directory, name = posixpath.split(slide_part)
    rels = members.get(f"{directory}/_rels/{name}.rels")
    if rels is None:
        return None
    layouts = [
        target
        for kind, target, mode in _relationships(_parse_xml_part(archive, rels)).values()
        if kind == LAYOUT_REL_TYPE and mode == "Internal"
    ]
    if len(layouts) != 1:
        return None
    part = _resolve_internal_part(directory, layouts[0])
    return _parse_xml_part(archive, members[part]) if part in members else None


def _state(archive: zipfile.ZipFile, fidelity: Any) -> list[dict[str, Any]]:
    members = {info.filename: info for info in archive.infolist()}
    rows = []
    for slide in fidelity.slides:
        root = _parse_xml_part(archive, members[slide.part_name])
        tree = root.find(f"{P}cSld/{P}spTree")
        layout = _slide_layout(archive, members, slide.part_name)
        layout_tree = layout.find(f"{P}cSld/{P}spTree") if layout is not None else None
        footers = _typed(tree, "ftr") if tree is not None else []
        rows.append(
            {
                "slide_id": slide.slide_id,
                "slide_number": slide.ordinal,
                "title_slide": layout is not None and layout.get("type") == "title",
                "number_supported": layout_tree is not None and bool(_typed(layout_tree, "sldNum")),
                "footer_supported": layout_tree is not None and bool(_typed(layout_tree, "ftr")),
                "number_shown": tree is not None and bool(_typed(tree, "sldNum")),
                "footer_text": _text(footers[0]) if len(footers) == 1 else None,
                "footer_shown": bool(footers),
            }
        )
    return rows


def _footer_shape_ids(archive: zipfile.ZipFile, fidelity: Any) -> set[tuple[str, str]]:
    members = {info.filename: info for info in archive.infolist()}
    ids = set()
    for slide in fidelity.slides:
        tree = _parse_xml_part(archive, members[slide.part_name]).find(f"{P}cSld/{P}spTree")
        if tree is None:
            continue
        for kind in ("sldNum", "ftr"):
            for shape in _typed(tree, kind):
                ids.add((slide.slide_id, shape.find(f"{P}nvSpPr/{P}cNvPr").get("id", "")))
    return ids


def _fingerprint(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def coverage(flag: str) -> str:
        values = [row[flag] for row in rows]
        return "all" if all(values) else "none" if not any(values) else "some"

    texts = {row["footer_text"] for row in rows if row["footer_shown"]}
    return {
        "slide_numbers": coverage("number_shown"),
        "footers": coverage("footer_shown"),
        "footer_text": texts.pop() if len(texts) == 1 else None,
        "supported_slides": sum(row["number_supported"] or row["footer_supported"] for row in rows),
        "slide_count": len(rows),
        "fingerprint": _fingerprint(rows),
    }


def _load(editor: PresentationEditService, params: dict[str, Any]) -> tuple[Any, ...]:
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
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
    return project, document, revision, source, path, fidelity


def get_slide_footers(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(params, {"project_id", "document_id", "expected_revision_id"})
    _project, _document, revision, source, path, fidelity = _load(editor, params)
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        rows = _state(archive, fidelity)
    return {"revision_id": revision, **_summary(rows)}


def _new_placeholder(
    layout_shape: etree._Element, shape_id: int, kind: str, ordinal: int, text: str
) -> etree._Element:
    names = {"sldNum": "Slide Number Placeholder", "ftr": "Footer Placeholder"}
    shape = etree.Element(f"{P}sp")
    nv = etree.SubElement(shape, f"{P}nvSpPr")
    etree.SubElement(nv, f"{P}cNvPr", id=str(shape_id), name=f"{names[kind]} {shape_id}")
    locks = etree.SubElement(nv, f"{P}cNvSpPr")
    etree.SubElement(locks, f"{A}spLocks", noGrp="1")
    nv_properties = etree.SubElement(nv, f"{P}nvPr")
    placeholder = etree.SubElement(nv_properties, f"{P}ph")
    layout_placeholder = _placeholder(layout_shape)
    if layout_placeholder is not None:
        for key, value in layout_placeholder.attrib.items():
            placeholder.set(key, value)
    etree.SubElement(shape, f"{P}spPr")
    body = etree.SubElement(shape, f"{P}txBody")
    etree.SubElement(body, f"{A}bodyPr")
    etree.SubElement(body, f"{A}lstStyle")
    _set_paragraph(body, kind, ordinal, text)
    return shape


def _set_paragraph(body: etree._Element, kind: str, ordinal: int, text: str) -> None:
    template = body.find(f".//{A}rPr")
    for paragraph in body.findall(f"{A}p"):
        body.remove(paragraph)
    paragraph = etree.SubElement(body, f"{A}p")
    if kind == "sldNum":
        run = etree.SubElement(
            paragraph, f"{A}fld", id="{" + str(uuid.uuid4()).upper() + "}", type="slidenum"
        )
    else:
        run = etree.SubElement(paragraph, f"{A}r")
    properties = copy.deepcopy(template) if template is not None else etree.Element(f"{A}rPr")
    properties.tag = f"{A}rPr"
    properties.set("lang", properties.get("lang", "en-US"))
    run.append(properties)
    etree.SubElement(run, f"{A}t").text = str(ordinal) if kind == "sldNum" else text


def set_slide_footers(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "expected_fingerprint",
            "slide_numbers",
            "footer_text",
            "skip_title_slides",
        },
    )
    show_numbers = params.get("slide_numbers")
    skip_title = params.get("skip_title_slides", True)
    if type(show_numbers) is not bool or type(skip_title) is not bool:
        raise invalid_request(
            "slide_numbers and skip_title_slides must be booleans.", field="slide_numbers"
        )
    footer = params.get("footer_text")
    if footer is not None:
        footer = editor._text_field(footer, "footer_text")
        if not footer.strip() or len(footer) > MAX_FOOTER_CHARS:
            raise invalid_request(
                f"footer_text must be visible text of at most {MAX_FOOTER_CHARS} characters, "
                "or null to remove footers.",
                field="footer_text",
            )
    project, document, revision, source, path, fidelity = _load(editor, params)
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        before = _state(archive, fidelity)
    if params.get("expected_fingerprint") != _fingerprint(before):
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The slide numbers or footers changed. Refresh and try again.",
            retryable=True,
        )

    def wanted(row: dict[str, Any]) -> tuple[bool, str | None]:
        excluded = skip_title and row["title_slide"]
        number = show_numbers and row["number_supported"] and not excluded
        text = footer if footer is not None and row["footer_supported"] and not excluded else None
        return number, text

    targets = {
        row["slide_id"]: wanted(row)
        for row in before
        if wanted(row) != (row["number_shown"], row["footer_text"] if row["footer_shown"] else None)
    }
    if not targets:
        return {
            "changed": False,
            "revision_id": source["revision_id"],
            "revision_number": int(source["revision_number"]),
            "sha256": source["sha256"],
            "byte_size": int(source["byte_size"]),
        }

    def write(original: Path, target: Path) -> bool:
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            members = {info.filename: info for info in archive.infolist()}
            rewritten: dict[str, bytes] = {}
            for slide in fidelity.slides:
                if slide.slide_id not in targets:
                    continue
                number, text = targets[slide.slide_id]
                root = _parse_xml_part(archive, members[slide.part_name])
                tree = root.find(f"{P}cSld/{P}spTree")
                layout = _slide_layout(archive, members, slide.part_name)
                layout_tree = layout.find(f"{P}cSld/{P}spTree") if layout is not None else None
                if tree is None or layout_tree is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED", "A slide has no usable layout."
                    )
                next_id = 1 + max(
                    (
                        int(node.get("id", "0"))
                        for node in tree.iter(f"{P}cNvPr")
                        if node.get("id", "").isdigit()
                    ),
                    default=1,
                )
                for kind, enabled, content in (
                    ("sldNum", number, ""),
                    ("ftr", text is not None, text or ""),
                ):
                    existing = _typed(tree, kind)
                    if not enabled:
                        for shape in existing:
                            tree.remove(shape)
                        continue
                    if existing:
                        if kind == "ftr" and _text(existing[0]) != content:
                            _set_paragraph(
                                existing[0].find(f"{P}txBody"), kind, slide.ordinal, content
                            )
                        continue
                    tree.append(
                        _new_placeholder(
                            _typed(layout_tree, kind)[0], next_id, kind, slide.ordinal, content
                        )
                    )
                    next_id += 1
                rewritten[slide.part_name] = etree.tostring(
                    root, encoding="UTF-8", xml_declaration=True, standalone=True
                )
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
        with zipfile.ZipFile(target) as archive:
            after = _state(archive, updated)
            changed_ids = _footer_shape_ids(archive, updated)
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            changed_ids |= _footer_shape_ids(archive, fidelity)

        def others(document_fidelity: Any) -> dict[str, Any]:
            return {
                obj.object_id: obj
                for page in document_fidelity.slides
                for obj in page.objects
                if (page.slide_id, obj.ooxml_id) not in changed_ids
            }

        if others(updated) != others(fidelity):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Content other than slide numbers and footers changed.",
            )
        for row in after:
            number, text = targets.get(
                row["slide_id"],
                (
                    next(b for b in before if b["slide_id"] == row["slide_id"])["number_shown"],
                    next(b for b in before if b["slide_id"] == row["slide_id"])["footer_text"],
                ),
            )
            if row["number_shown"] != number or (
                row["slide_id"] in targets and row["footer_text"] != text
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED",
                    "The slide numbers or footers did not pass validation.",
                )
        if [s.slide_id for s in updated.slides] != [s.slide_id for s in fidelity.slides]:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED", "The slide order changed unexpectedly."
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "slides_changed": len(targets)}
