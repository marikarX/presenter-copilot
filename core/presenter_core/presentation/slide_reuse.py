"""Reuse a slide from another deck in the project, like PowerPoint's Reuse Slides with
"use destination theme": the slide takes the destination layout of the same type (else
the same name, else Title and Content), so it picks up the destination's design.

The slide's pictures, charts, external links and speaker notes come with it. Inherited
placeholder positions are written onto the slide so they survive the layout change.
Slides with parts that cannot be remapped safely (SmartArt, media, embedded objects,
links that jump to other slides) are refused; review comments are left behind.
"""

from __future__ import annotations

import copy
import posixpath
import shutil
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    _NS,
    NOTES_SLIDE_REL_TYPE,
    OBJECT_LIMIT,
    PACKAGE_REL_NS,
    PRESENTATION_NS,
    REL_NS,
    SLIDE_LIMIT,
    _parse_xml_part,
    _relationships,
    _resolve_internal_part,
    inspect_pptx_snapshot,
)
from presenter_core.presentation.graphic_duplication import CT, clone_chart_graph
from presenter_core.presentation.slide_sections import sync_sections

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

P = f"{{{PRESENTATION_NS}}}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
SLIDE_CT = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
NOTES_CT = "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"
IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/bmp",
    "image/tiff",
    "image/svg+xml",
    "image/x-emf",
    "image/x-wmf",
    "image/vnd.ms-photo",
}
MS_REL = "http://schemas.microsoft.com/office/2007/relationships"
PICTURE_RELS = {f"{REL_NS}/image", f"{MS_REL}/hdphoto"}
DIAGRAM_RELS = {
    f"{REL_NS}/{name}"
    for name in ("diagramData", "diagramLayout", "diagramQuickStyle", "diagramColors")
}
DRAWING_REL = f"{MS_REL}/diagramDrawing"
COMMENT_RELS = {
    f"{REL_NS}/comments",
    "http://schemas.microsoft.com/office/2018/10/relationships/comments",
}


def _reject(message: str) -> CoreDomainError:
    return CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", message)


def _rels_name(part: str) -> str:
    return f"{posixpath.dirname(part)}/_rels/{posixpath.basename(part)}.rels"


def _main_parts(archive: zipfile.ZipFile, members: dict[str, Any]) -> dict[str, list[str]]:
    """Slide masters, layouts (master order) and the notes master of a package."""
    relations = _relationships(_parse_xml_part(archive, members["ppt/_rels/presentation.xml.rels"]))
    found: dict[str, list[str]] = {"layouts": [], "notes_master": []}
    for kind, target, mode in relations.values():
        if mode.casefold() != "internal":
            continue
        part = _resolve_internal_part("ppt", target)
        if kind == f"{REL_NS}/notesMaster" and part in members:
            found["notes_master"].append(part)
        if kind != f"{REL_NS}/slideMaster" or _rels_name(part) not in members:
            continue
        for layout_kind, layout_target, layout_mode in _relationships(
            _parse_xml_part(archive, members[_rels_name(part)])
        ).values():
            layout = _resolve_internal_part(posixpath.dirname(part), layout_target)
            if (
                layout_kind == f"{REL_NS}/slideLayout"
                and layout_mode.casefold() == "internal"
                and layout in members
                and layout not in found["layouts"]
            ):
                found["layouts"].append(layout)
    return found


def _layout_key(archive: zipfile.ZipFile, members: dict[str, Any], part: str) -> tuple[str, str]:
    root = _parse_xml_part(archive, members[part])
    name = root.find("p:cSld", _NS)
    return root.get("type", "cust"), (name.get("name", "") if name is not None else "")


def _choose_layout(
    source: tuple[str, str], layouts: list[tuple[str, tuple[str, str]]]
) -> tuple[str, str]:
    kind, name = source
    tests: list[Callable[[tuple[str, str]], bool]] = [
        lambda key: kind != "cust" and key[0] == kind,
        lambda key: bool(name) and key[1].casefold() == name.casefold(),
        lambda key: key[0] == "obj",
    ]
    for test in tests:
        for part, key in layouts:
            if test(key):
                return part, key[1]
    if not layouts:
        raise _reject("The destination presentation has no slide layouts.")
    return layouts[0][0], layouts[0][1][1]


def reuse_slide(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import (
        _MAX_OOXML_SLIDE_ID,
        _PRESENTATION_SLIDE_REL_TYPE,
        PresentationEditService,
        _verified_source_archive,
    )

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "source_document_id",
            "source_revision_id",
            "source_slide_id",
            "position",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    baseline = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    source_document = editor._document_id(params.get("source_document_id"))
    source_revision = editor._uuid_field(params.get("source_revision_id"), "source_revision_id")
    source_slide_id = editor._uuid_field(params.get("source_slide_id"), "source_slide_id")
    position = params.get("position")
    if source_document == document:
        raise invalid_request("Use Duplicate slide to copy a slide within the same deck.")
    copied = editor._verified_revision(project, source_document, source_revision)
    copied_path = editor._storage.paths.snapshot_path(
        project, copied["local_snapshot_path"], require_exists=True
    )
    current = editor._current_revision_source(project, document)
    if current["revision_id"] != baseline:
        raise editor._revision_conflict()
    current_path = editor._storage.paths.snapshot_path(
        project, current["local_snapshot_path"], require_exists=True
    )

    def inspect(path: Path, document_id: str, metadata: Any) -> Any:
        with path.open("rb") as handle:
            return inspect_pptx_snapshot(
                handle,
                document_id=document_id,
                expected_sha256=metadata["sha256"],
                byte_size=metadata["byte_size"],
            )

    source_doc = inspect(copied_path, source_document, copied)
    target_doc = inspect(current_path, document, current)
    slide = next((s for s in source_doc.slides if s.slide_id == source_slide_id), None)
    if slide is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The slide to reuse is unavailable."
        )
    if type(position) is not int or not 1 <= position <= len(target_doc.slides) + 1:
        raise invalid_request("position must be a slide position in this deck.", field="position")
    if (source_doc.slide_width_emu, source_doc.slide_height_emu) != (
        target_doc.slide_width_emu,
        target_doc.slide_height_emu,
    ):
        raise _reject("Slides can be reused only between decks with the same slide size.")
    if len(target_doc.slides) >= SLIDE_LIMIT or (
        target_doc.object_count + len(slide.objects) > OBJECT_LIMIT
    ):
        raise CoreDomainError(
            "PRESENTATION_EDIT_RESOURCE_LIMIT",
            "This presentation cannot contain another slide safely.",
        )
    outcome: dict[str, Any] = {}

    def write(original: Path, destination: Path) -> None:
        outcome.clear()
        with (
            _verified_source_archive(
                original, expected_sha256=current["sha256"], expected_byte_size=current["byte_size"]
            ) as target_archive,
            _verified_source_archive(
                copied_path,
                expected_sha256=copied["sha256"],
                expected_byte_size=copied["byte_size"],
            ) as source_archive,
        ):
            tm = {i.filename: i for i in target_archive.infolist()}
            sm = {i.filename: i for i in source_archive.infolist()}
            if _rels_name(slide.part_name) not in sm:
                raise _reject("This slide is missing the relationships needed to reuse it.")
            root = _parse_xml_part(source_archive, sm[slide.part_name])
            source_rels = _relationships(
                _parse_xml_part(source_archive, sm[_rels_name(slide.part_name)])
            )
            types = _parse_xml_part(target_archive, tm["[Content_Types].xml"])
            source_types = _parse_xml_part(source_archive, sm["[Content_Types].xml"])
            overrides = {
                n.get("PartName", "").lstrip("/"): n.get("ContentType")
                for n in source_types.findall(f"{{{CT}}}Override")
            }
            defaults = {
                n.get("Extension"): n.get("ContentType")
                for n in source_types.findall(f"{{{CT}}}Default")
            }
            new_part = PresentationEditService._unique_package_part(tm, "ppt/slides", "slide")
            rels = etree.Element(f"{{{PACKAGE_REL_NS}}}Relationships", nsmap={None: PACKAGE_REL_NS})
            additions: dict[str, bytes] = {}

            def relate(kind: str, target: str, external: bool = False) -> str:
                rid = f"rId{len(rels) + 1}"
                attrs = {"Id": rid, "Type": kind, "Target": target}
                if external:
                    attrs["TargetMode"] = "External"
                etree.SubElement(rels, f"{{{PACKAGE_REL_NS}}}Relationship", **attrs)
                return rid

            # Layout: the destination's equivalent, so the slide takes its design.
            layout_relation = [r for r in source_rels.values() if r[0] == f"{REL_NS}/slideLayout"]
            if len(layout_relation) != 1:
                raise _reject("This slide does not use a supported layout structure.")
            source_layout = _resolve_internal_part("ppt/slides", layout_relation[0][1])
            if source_layout not in sm:
                raise _reject("This slide's layout is missing.")
            target_parts = _main_parts(target_archive, tm)
            layout, layout_name = _choose_layout(
                _layout_key(source_archive, sm, source_layout),
                [(part, _layout_key(target_archive, tm, part)) for part in target_parts["layouts"]],
            )
            relate(f"{REL_NS}/slideLayout", posixpath.relpath(layout, "ppt/slides"))

            # Inherited placeholder positions become explicit before the layout changes.
            for obj in slide.objects:
                if not obj.geometry_inherited or obj.geometry is None:
                    continue
                node = editor._find_object_node(root, ooxml_id=obj.ooxml_id, kind=obj.kind)
                properties = node.find("p:spPr", _NS)
                if properties is None:
                    raise _reject("A placeholder on this slide has no shape properties.")
                transform = etree.Element(f"{A}xfrm")
                geometry = obj.geometry
                etree.SubElement(transform, f"{A}off", x=str(geometry.x_emu), y=str(geometry.y_emu))
                etree.SubElement(
                    transform,
                    f"{A}ext",
                    cx=str(geometry.width_emu),
                    cy=str(geometry.height_emu),
                )
                properties.insert(0, transform)

            # Custom table styles must exist identically in the destination.
            def catalog(archive: zipfile.ZipFile, members: dict[str, Any]) -> dict[str, bytes]:
                rels_part = members["ppt/_rels/presentation.xml.rels"]
                found = [
                    _resolve_internal_part("ppt", r[1])
                    for r in _relationships(_parse_xml_part(archive, rels_part)).values()
                    if r[0] == f"{REL_NS}/tableStyles" and r[2].casefold() == "internal"
                ]
                if not found or found[0] not in members:
                    return {}
                return {
                    n.get("styleId"): etree.tostring(n, method="c14n")
                    for n in _parse_xml_part(archive, members[found[0]])
                }

            styles = {n.text for n in root.iter(f"{A}tableStyleId")}
            if styles:
                source_catalog, target_catalog = (
                    catalog(source_archive, sm),
                    catalog(target_archive, tm),
                )
                if any(
                    style in source_catalog and source_catalog[style] != target_catalog.get(style)
                    for style in styles
                ):
                    raise _reject("A table on this slide uses a custom style the deck lacks.")

            # Copy a part with the pictures and links it refers to under a fresh name.
            copies: dict[str, str] = {}

            def copy_part(part: str, pictures_only: bool) -> str:
                if part in copies:
                    return copies[part]
                extension = posixpath.splitext(part)[1].lower()
                content_type = overrides.get(part) or defaults.get(extension.lstrip("."))
                if (
                    part not in sm
                    or not content_type
                    or (pictures_only and content_type not in IMAGE_TYPES)
                ):
                    raise _reject("A picture or diagram on this slide cannot be copied.")
                new = posixpath.join(
                    posixpath.dirname(part), f"copilot-reuse-{uuid.uuid4().hex}{extension}"
                )
                copies[part] = new
                if _rels_name(part) in sm:
                    part_rels = _parse_xml_part(source_archive, sm[_rels_name(part)])
                    for relationship in part_rels:
                        kind = relationship.get("Type", "")
                        if relationship.get("TargetMode", "Internal").casefold() == "external":
                            if kind != f"{REL_NS}/hyperlink":
                                raise _reject("A diagram on this slide links outside the deck.")
                            continue
                        if kind not in PICTURE_RELS:
                            raise _reject("A diagram on this slide uses unsupported parts.")
                        child = _resolve_internal_part(
                            posixpath.dirname(part), relationship.get("Target", "")
                        )
                        relationship.set(
                            "Target",
                            posixpath.relpath(copy_part(child, True), posixpath.dirname(new)),
                        )
                    additions[_rels_name(new)] = etree.tostring(
                        part_rels, encoding="UTF-8", xml_declaration=True, standalone=True
                    )
                additions[new] = source_archive.read(sm[part])
                etree.SubElement(
                    types, f"{{{CT}}}Override", PartName="/" + new, ContentType=content_type
                )
                return new

            # Remap every relationship the slide XML refers to.
            mapped: dict[str, str] = {}
            diagram_data: list[str] = []
            for element in root.iter():
                if element.tag == "{http://schemas.openxmlformats.org/drawingml/2006/chart}chart":
                    continue
                for attribute, value in list(element.attrib.items()):
                    if not attribute.startswith(f"{{{REL_NS}}}") or value == "":
                        continue
                    if value in mapped:
                        element.set(attribute, mapped[value])
                        continue
                    relation = source_rels.get(value)
                    if relation is None:
                        raise _reject("This slide refers to a missing package part.")
                    kind, target, mode = relation
                    internal = mode.casefold() == "internal"
                    if internal and (kind in PICTURE_RELS or kind in DIAGRAM_RELS):
                        part = _resolve_internal_part("ppt/slides", target)
                        new = copy_part(part, kind in PICTURE_RELS)
                        if kind == f"{REL_NS}/diagramData":
                            diagram_data.append(new)
                        rid = relate(kind, posixpath.relpath(new, "ppt/slides"))
                    elif kind == f"{REL_NS}/hyperlink" and not internal:
                        rid = relate(kind, target, external=True)
                    elif kind == f"{REL_NS}/slide":
                        raise _reject("This slide links to other slides in its deck.")
                    else:
                        raise _reject(
                            "This slide contains content (such as media or an embedded "
                            "object) that cannot be reused yet."
                        )
                    mapped[value] = rid
                    element.set(attribute, rid)
            # A SmartArt's cached drawing is named from its data part through a slide
            # relationship, so it gets a new slide relationship and the data points to it.
            for data_part in diagram_data:
                data_root = etree.fromstring(additions[data_part])
                for extension in data_root.xpath(".//*[local-name()='dataModelExt'][@relId]"):
                    relation = source_rels.get(extension.get("relId"))
                    if relation is None or relation[0] != DRAWING_REL:
                        raise _reject("A diagram on this slide has an unsupported drawing.")
                    drawing = copy_part(_resolve_internal_part("ppt/slides", relation[1]), False)
                    rid = relate(DRAWING_REL, posixpath.relpath(drawing, "ppt/slides"))
                    mapped[extension.get("relId")] = rid
                    extension.set("relId", rid)
                additions[data_part] = etree.tostring(
                    data_root, encoding="UTF-8", xml_declaration=True, standalone=True
                )
            unreferenced = {
                rid: relation
                for rid, relation in source_rels.items()
                if rid not in mapped
                and relation[0]
                not in {f"{REL_NS}/slideLayout", NOTES_SLIDE_REL_TYPE, f"{REL_NS}/chart"}
                | COMMENT_RELS
            }
            if any(
                r[0] not in PICTURE_RELS | {f"{REL_NS}/hyperlink"} for r in unreferenced.values()
            ):
                raise _reject("This slide carries package parts that cannot be reused yet.")

            charts: dict[str, str] = {}
            for frame in root.iter(f"{P}graphicFrame"):
                cloned = clone_chart_graph(
                    source_archive,
                    new_part,
                    frame,
                    slide_relationships=rels,
                    content_types_root=types,
                    cloned_parts=charts,
                    source_slide_part=slide.part_name,
                )
                # The slide's relationships and content types are written once, below.
                cloned = {
                    name: payload
                    for name, payload in cloned.items()
                    if name not in {_rels_name(new_part), "[Content_Types].xml"}
                }
                if any(name in tm or name in additions for name in cloned):
                    raise _reject("A copied chart would overwrite an existing part.")
                additions.update(cloned)

            # Speaker notes travel; a deck without a notes master takes the source's.
            notes_copied = False
            new_notes_master: str | None = None
            notes_relation = [r for r in source_rels.values() if r[0] == NOTES_SLIDE_REL_TYPE]
            if notes_relation and slide.speaker_notes and not target_parts["notes_master"]:
                source_notes = _resolve_internal_part("ppt/slides", notes_relation[0][1])
                master = next(
                    (
                        _resolve_internal_part(posixpath.dirname(source_notes), r[1])
                        for r in (
                            _relationships(
                                _parse_xml_part(source_archive, sm[_rels_name(source_notes)])
                            ).values()
                            if _rels_name(source_notes) in sm
                            else []
                        )
                        if r[0] == f"{REL_NS}/notesMaster" and r[2].casefold() == "internal"
                    ),
                    None,
                )
                master_rels = (
                    _relationships(_parse_xml_part(source_archive, sm[_rels_name(master)]))
                    if master is not None and master in sm and _rels_name(master) in sm
                    else None
                )
                if master_rels is not None and all(
                    r[0] == f"{REL_NS}/theme" and r[2].casefold() == "internal"
                    for r in master_rels.values()
                ):
                    assert master is not None
                    token = uuid.uuid4().hex
                    new_notes_master = f"ppt/notesMasters/copilot-reuse-{token}.xml"
                    copied_rels = etree.Element(
                        f"{{{PACKAGE_REL_NS}}}Relationships", nsmap={None: PACKAGE_REL_NS}
                    )
                    for index, (rid, relation) in enumerate(master_rels.items()):
                        theme = _resolve_internal_part(posixpath.dirname(master), relation[1])
                        if theme not in sm:
                            new_notes_master = None
                            break
                        new_theme = f"ppt/theme/copilot-reuse-{token}-{index}.xml"
                        additions[new_theme] = source_archive.read(sm[theme])
                        etree.SubElement(
                            types,
                            f"{{{CT}}}Override",
                            PartName="/" + new_theme,
                            ContentType="application/vnd.openxmlformats-officedocument.theme+xml",
                        )
                        etree.SubElement(
                            copied_rels,
                            f"{{{PACKAGE_REL_NS}}}Relationship",
                            Id=rid,
                            Type=relation[0],
                            Target=posixpath.relpath(new_theme, "ppt/notesMasters"),
                        )
                    if new_notes_master is not None:
                        additions[new_notes_master] = source_archive.read(sm[master])
                        additions[_rels_name(new_notes_master)] = etree.tostring(
                            copied_rels, encoding="UTF-8", xml_declaration=True, standalone=True
                        )
                        etree.SubElement(
                            types,
                            f"{{{CT}}}Override",
                            PartName="/" + new_notes_master,
                            ContentType="application/vnd.openxmlformats-officedocument."
                            "presentationml.notesMaster+xml",
                        )
                        target_parts["notes_master"].append(new_notes_master)
            if notes_relation and slide.speaker_notes and target_parts["notes_master"]:
                source_notes = _resolve_internal_part("ppt/slides", notes_relation[0][1])
                notes_root = (
                    _parse_xml_part(source_archive, sm[source_notes])
                    if source_notes in sm
                    else None
                )
                if notes_root is not None and not notes_root.xpath(
                    ".//@r:id | .//@r:embed | .//@r:link", namespaces=_NS
                ):
                    notes_part = PresentationEditService._unique_package_part(
                        tm, "ppt/notesSlides", "notesSlide"
                    )
                    notes_rels = etree.Element(
                        f"{{{PACKAGE_REL_NS}}}Relationships", nsmap={None: PACKAGE_REL_NS}
                    )
                    for index, (kind, target) in enumerate(
                        (
                            (
                                f"{REL_NS}/notesMaster",
                                posixpath.relpath(
                                    target_parts["notes_master"][0], "ppt/notesSlides"
                                ),
                            ),
                            (f"{REL_NS}/slide", posixpath.relpath(new_part, "ppt/notesSlides")),
                        ),
                        start=1,
                    ):
                        etree.SubElement(
                            notes_rels,
                            f"{{{PACKAGE_REL_NS}}}Relationship",
                            Id=f"rId{index}",
                            Type=kind,
                            Target=target,
                        )
                    additions[notes_part] = etree.tostring(
                        notes_root, encoding="UTF-8", xml_declaration=True, standalone=True
                    )
                    additions[_rels_name(notes_part)] = etree.tostring(
                        notes_rels, encoding="UTF-8", xml_declaration=True, standalone=True
                    )
                    etree.SubElement(
                        types, f"{{{CT}}}Override", PartName="/" + notes_part, ContentType=NOTES_CT
                    )
                    relate(NOTES_SLIDE_REL_TYPE, posixpath.relpath(notes_part, "ppt/slides"))
                    notes_copied = True

            # Add the slide to the destination's slide list at the requested position.
            presentation = _parse_xml_part(target_archive, tm["ppt/presentation.xml"])
            presentation_rels = _parse_xml_part(
                target_archive, tm["ppt/_rels/presentation.xml.rels"]
            )
            slide_list = presentation.find("p:sldIdLst", _NS)
            if slide_list is None:
                slide_list = etree.Element(f"{P}sldIdLst")
                masters = presentation.find("p:notesMasterIdLst", _NS)
                anchor = (
                    masters if masters is not None else presentation.find("p:sldMasterIdLst", _NS)
                )
                anchor.addnext(slide_list)
            previous_order = [item.get("id", "") for item in slide_list]
            numbers = [int(value) for value in previous_order]
            new_id = max([255, *numbers]) + 1
            if new_id > _MAX_OOXML_SLIDE_ID:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_RESOURCE_LIMIT",
                    "This presentation cannot allocate another slide identifier.",
                )
            relation_id = PresentationEditService._new_relationship_id(
                set(_relationships(presentation_rels)), "SlideReuse"
            )
            etree.SubElement(
                presentation_rels,
                f"{{{PACKAGE_REL_NS}}}Relationship",
                Id=relation_id,
                Type=_PRESENTATION_SLIDE_REL_TYPE,
                Target=posixpath.relpath(new_part, "ppt"),
            )
            if new_notes_master is not None:
                master_id = PresentationEditService._new_relationship_id(
                    set(_relationships(presentation_rels)), "NotesMasterReuse"
                )
                etree.SubElement(
                    presentation_rels,
                    f"{{{PACKAGE_REL_NS}}}Relationship",
                    Id=master_id,
                    Type=f"{REL_NS}/notesMaster",
                    Target=posixpath.relpath(new_notes_master, "ppt"),
                )
                declared = etree.Element(f"{P}notesMasterIdLst")
                etree.SubElement(declared, f"{P}notesMasterId").set(f"{{{REL_NS}}}id", master_id)
                presentation.find("p:sldMasterIdLst", _NS).addnext(declared)
            reference = etree.Element(f"{P}sldId", id=str(new_id))
            reference.set(f"{{{REL_NS}}}id", relation_id)
            slide_list.insert(position - 1, reference)
            sync_sections(presentation, previous_order)
            etree.SubElement(
                types, f"{{{CT}}}Override", PartName="/" + new_part, ContentType=SLIDE_CT
            )
            additions[new_part] = etree.tostring(
                root, encoding="UTF-8", xml_declaration=True, standalone=True
            )
            additions[_rels_name(new_part)] = etree.tostring(
                rels, encoding="UTF-8", xml_declaration=True, standalone=True
            )
            additions["ppt/presentation.xml"] = etree.tostring(
                presentation, encoding="UTF-8", xml_declaration=True, standalone=True
            )
            additions["ppt/_rels/presentation.xml.rels"] = etree.tostring(
                presentation_rels, encoding="UTF-8", xml_declaration=True, standalone=True
            )
            additions["[Content_Types].xml"] = etree.tostring(
                types, encoding="UTF-8", xml_declaration=True, standalone=True
            )
            if len(tm.keys() | additions.keys()) > 2048:
                raise _reject("The presentation would exceed the safe part limit.")
            with zipfile.ZipFile(destination, "w", allowZip64=True) as output:
                output.comment = target_archive.comment
                for info in target_archive.infolist():
                    payload = additions.pop(info.filename, None)
                    if payload is not None:
                        output.writestr(copy.copy(info), payload)
                    else:
                        with (
                            target_archive.open(info) as reader,
                            output.open(copy.copy(info), "w") as writer,
                        ):
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
                for name, payload in additions.items():
                    output.writestr(
                        zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)),
                        payload,
                        compress_type=zipfile.ZIP_DEFLATED,
                    )
            outcome.update(layout_name=layout_name, notes_copied=notes_copied)
        updated = inspect(
            destination,
            document,
            {"sha256": editor._sha256_path(destination), "byte_size": destination.stat().st_size},
        )
        order = [s.slide_id for s in target_doc.slides]
        after = [s.slide_id for s in updated.slides]
        created = [s for s in updated.slides if s.slide_id not in order]
        before_objects = {o.object_id: o for s in target_doc.slides for o in s.objects}
        after_objects = {
            o.object_id: o for s in updated.slides if s.slide_id in order for o in s.objects
        }

        def shape(obj: Any) -> Any:
            # Identity, layout inheritance and editability belong to the new slide.
            # An inherited placeholder reports no rotation; written explicitly it reads 0.
            turn = obj.rotation
            rotation = (
                (turn.rotation, turn.flip_horizontal, turn.flip_vertical)
                if turn
                else (0, False, False)
            )
            return (obj.name, obj.kind, obj.text, obj.geometry, obj.alt_text, rotation)

        valid = (
            len(created) == 1
            and [s for s in after if s != created[0].slide_id] == order
            and after.index(created[0].slide_id) == position - 1
            and before_objects == after_objects
            and sorted(map(shape, created[0].objects), key=repr)
            == sorted(map(shape, slide.objects), key=repr)
            and created[0].hidden == slide.hidden
        )
        if not valid:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED", "The reused slide did not pass validation."
            )
        outcome["created_slide_id"] = created[0].slide_id

    result = editor._commit_revision(project, document, baseline, current, write)
    return {**result, **outcome}
