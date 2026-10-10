"""Slide sections (PowerPoint 2010 p14:sectionLst): named, contiguous runs of slides.

Every slide-list writer calls sync_sections so sections follow deletes, inserts
and reorders the way PowerPoint's slide sorter does. set_slide_sections renames,
splits, merges or removes sections.
"""

from __future__ import annotations

import bisect
import copy
import hashlib
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    PRESENTATION_NS,
    _parse_xml_part,
    inspect_pptx_snapshot,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

P = f"{{{PRESENTATION_NS}}}"
P14_NS = "http://schemas.microsoft.com/office/powerpoint/2010/main"
P14 = f"{{{P14_NS}}}"
SECTION_EXT_URI = "{521415D9-36F7-43E2-AB2F-B90AF26B5E84}"
MAX_SECTIONS = 200
MAX_NAME = 120


def _section_list(root: etree._Element) -> etree._Element | None:
    found = root.xpath(
        "./p:extLst/p:ext[@uri=$uri]/p14:sectionLst",
        namespaces={"p": PRESENTATION_NS, "p14": P14_NS},
        uri=SECTION_EXT_URI,
    )
    return found[0] if found else None


def _main_order(root: etree._Element) -> list[str]:
    return [item.get("id", "") for item in root.findall(f"{P}sldIdLst/{P}sldId")]


def _stable(positions: list[int]) -> set[int]:
    """Indexes (into positions) of one longest increasing subsequence."""
    tails: list[int] = []
    tail_index: list[int] = []
    parent = [-1] * len(positions)
    for index, value in enumerate(positions):
        at = bisect.bisect_left(tails, value)
        if at == len(tails):
            tails.append(value)
            tail_index.append(index)
        else:
            tails[at] = value
            tail_index[at] = index
        parent[index] = tail_index[at - 1] if at else -1
    result: set[int] = set()
    cursor = tail_index[-1] if tail_index else -1
    while cursor != -1:
        result.add(cursor)
        cursor = parent[cursor]
    return result


def sync_sections(root: etree._Element, previous_order: list[str]) -> etree._Element:
    """Keep sections a partition of the slide list after it changed; returns root.

    Slides still in their original relative order keep their section; moved or new
    slides join the section of the slide before them (or after, at the start).
    """
    sections = _section_list(root)
    if sections is None:
        return root
    order = _main_order(root)
    groups = [section for section in sections.findall(f"{P14}section") if section is not None]
    owner = {
        slide.get("id"): index
        for index, section in enumerate(groups)
        for slide in section.findall(f"{P14}sldIdLst/{P14}sldId")
    }
    previous = {slide_id: index for index, slide_id in enumerate(previous_order)}
    candidates = [
        (index, previous[slide_id])
        for index, slide_id in enumerate(order)
        if slide_id in previous and slide_id in owner
    ]
    stable = {candidates[i][0] for i in _stable([position for _, position in candidates])}
    assigned: list[int | None] = [
        owner[slide_id] if index in stable else None for index, slide_id in enumerate(order)
    ]
    for index in range(len(order)):
        if assigned[index] is None and index:
            assigned[index] = assigned[index - 1]
    following = next((value for value in assigned if value is not None), 0)
    assigned = [following if value is None else value for value in assigned]
    for index, section in enumerate(groups):
        slide_list = section.find(f"{P14}sldIdLst")
        if slide_list is None:
            slide_list = etree.SubElement(section, f"{P14}sldIdLst")
        for child in list(slide_list):
            slide_list.remove(child)
        for slide_id, value in zip(order, assigned, strict=True):
            if value == index:
                etree.SubElement(slide_list, f"{P14}sldId", id=slide_id)
    return root


def _state(root: etree._Element, fidelity_slides: list[Any]) -> dict[str, Any]:
    sections = _section_list(root)
    by_native = {slide.ooxml_slide_id: slide.slide_id for slide in fidelity_slides}
    data = b"" if sections is None else etree.tostring(sections, method="c14n")
    fingerprint = hashlib.sha256(data + "|".join(_main_order(root)).encode()).hexdigest()
    if sections is None:
        return {"sections": [], "editable": True, "reason": None, "fingerprint": fingerprint}
    result = []
    listed: list[str] = []
    for section in sections:
        if not isinstance(section.tag, str):
            continue
        if section.tag != f"{P14}section":
            return {
                "sections": [],
                "editable": False,
                "reason": "This presentation's sections use an unsupported format.",
                "fingerprint": fingerprint,
            }
        ids = [slide.get("id", "") for slide in section.findall(f"{P14}sldIdLst/{P14}sldId")]
        listed.extend(ids)
        result.append(
            {
                "section_id": section.get("id", ""),
                "name": section.get("name", ""),
                "slide_ids": [by_native[value] for value in ids if value in by_native],
            }
        )
    consistent = listed == _main_order(root)
    return {
        "sections": result,
        "editable": True,
        "reason": None if consistent else "Saving rebuilds sections to match the slide order.",
        "fingerprint": fingerprint,
    }


def _load(editor: PresentationEditService, params: dict[str, Any]) -> tuple[Any, ...]:
    from presenter_core.presentation.editing import _verified_source_archive

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
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        root = _parse_xml_part(archive, archive.getinfo("ppt/presentation.xml"))
    return project, document, revision, source, fidelity, root


def get_slide_sections(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    reject_unknown_fields(params, {"project_id", "document_id", "expected_revision_id"})
    _project, _document, revision, _source, fidelity, root = _load(editor, params)
    return {
        "revision_id": revision,
        "slide_ids": [slide.slide_id for slide in fidelity.slides],
        **_state(root, list(fidelity.slides)),
    }


def _requested(value: Any, slide_ids: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_SECTIONS:
        raise invalid_request(
            f"sections must be a list of at most {MAX_SECTIONS} entries.", field="sections"
        )
    result = []
    for entry in value:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"section_id", "name", "first_slide_id"}
            or not isinstance(entry["name"], str)
            or not entry["name"].strip()
            or len(entry["name"]) > MAX_NAME
            or any(ord(character) < 32 for character in entry["name"])
            or not (entry["section_id"] is None or isinstance(entry["section_id"], str))
            or entry["first_slide_id"] not in slide_ids
        ):
            raise invalid_request(
                "Each section needs section_id (or null), a name of up to "
                f"{MAX_NAME} characters and the first_slide_id of a current slide.",
                field="sections",
            )
        result.append({**entry, "name": entry["name"].strip()})
    starts = [slide_ids.index(entry["first_slide_id"]) for entry in result]
    if result and (starts[0] != 0 or starts != sorted(set(starts))):
        raise invalid_request(
            "Sections must start at the first slide and follow slide order without overlap.",
            field="sections",
        )
    known = [entry["section_id"] for entry in result if entry["section_id"] is not None]
    if len(set(known)) != len(known):
        raise invalid_request("Each section_id can appear only once.", field="sections")
    return result


def set_slide_sections(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {"project_id", "document_id", "expected_revision_id", "expected_fingerprint", "sections"},
    )
    project, document, revision, source, fidelity, root = _load(editor, params)
    slides = list(fidelity.slides)
    slide_ids = [slide.slide_id for slide in slides]
    requested = _requested(params.get("sections"), slide_ids)
    before = _state(root, slides)
    if before["fingerprint"] != params.get("expected_fingerprint"):
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The slide sections changed. Refresh and try again.",
            retryable=True,
        )
    if not before["editable"]:
        raise CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", before["reason"])
    existing_ids = {section["section_id"] for section in before["sections"]}
    if any(
        entry["section_id"] is not None and entry["section_id"] not in existing_ids
        for entry in requested
    ):
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "A section changed. Refresh and try again.",
            retryable=True,
        )
    native = [slide.ooxml_slide_id for slide in slides]
    starts = [slide_ids.index(entry["first_slide_id"]) for entry in requested]
    wanted = [
        {
            "name": entry["name"],
            "slide_ids": slide_ids[start : (starts + [len(slides)])[index + 1]],
        }
        for index, (entry, start) in enumerate(zip(requested, starts, strict=True))
    ]
    if (
        wanted
        == [
            {"name": section["name"], "slide_ids": section["slide_ids"]}
            for section in before["sections"]
        ]
        and before["reason"] is None
    ):
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
            presentation = _parse_xml_part(archive, archive.getinfo("ppt/presentation.xml"))
            if _state(presentation, slides)["fingerprint"] != before["fingerprint"]:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET",
                    "The slide sections changed. Refresh and try again.",
                    retryable=True,
                )
            current = _section_list(presentation)
            extension = None if current is None else current.getparent()
            if requested:
                if extension is None:
                    extensions = presentation.find(f"{P}extLst")
                    if extensions is None:
                        extensions = etree.SubElement(presentation, f"{P}extLst")
                    extension = etree.Element(f"{P}ext", uri=SECTION_EXT_URI)
                    extensions.insert(0, extension)
                elif current is not None:
                    extension.remove(current)
                section_list = etree.SubElement(
                    extension, f"{P14}sectionLst", nsmap={"p14": P14_NS}
                )
                for index, (entry, start) in enumerate(zip(requested, starts, strict=True)):
                    end = (starts + [len(slides)])[index + 1]
                    identity = entry["section_id"] or "{" + str(uuid.uuid4()).upper() + "}"
                    section = etree.SubElement(
                        section_list, f"{P14}section", name=entry["name"], id=identity
                    )
                    ids = etree.SubElement(section, f"{P14}sldIdLst")
                    for value in native[start:end]:
                        etree.SubElement(ids, f"{P14}sldId", id=value)
            elif extension is not None:
                extensions = extension.getparent()
                extensions.remove(extension)
                if not len(extensions):
                    presentation.remove(extensions)
            rewritten = etree.tostring(
                presentation, encoding="UTF-8", xml_declaration=True, standalone=True
            )
            with zipfile.ZipFile(target, "w", allowZip64=True) as output:
                output.comment = archive.comment
                for info in archive.infolist():
                    if info.filename == "ppt/presentation.xml":
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
        with zipfile.ZipFile(target) as archive:
            after = _state(
                _parse_xml_part(archive, archive.getinfo("ppt/presentation.xml")),
                list(updated.slides),
            )
        if (
            [{"name": s["name"], "slide_ids": s["slide_ids"]} for s in after["sections"]] != wanted
            or after["reason"] is not None
            or updated.slides != fidelity.slides
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The slide section edit did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "sections": wanted}
