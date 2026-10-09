"""Paste supported native objects from an immutable presentation revision."""

from __future__ import annotations

import copy
import posixpath
import shutil
import uuid
import zipfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    _NS,
    OBJECT_LIMIT,
    PACKAGE_REL_NS,
    REL_NS,
    _parse_xml_part,
    _relationships,
    _resolve_internal_part,
    inspect_pptx_snapshot,
)
from presenter_core.presentation.graphic_duplication import CT, clone_chart_graph


def paste_objects(editor: Any, params: dict[str, Any]) -> dict[str, Any]:
    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "source_document_id",
            "source_revision_id",
            "source_slide_id",
            "object_ids",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    baseline = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    source_document = editor._document_id(params.get("source_document_id"))
    source_revision = editor._uuid_field(params.get("source_revision_id"), "source_revision_id")
    source_slide = editor._uuid_field(params.get("source_slide_id"), "source_slide_id")
    target_slide = editor._uuid_field(params.get("slide_id"), "slide_id")
    ids = params.get("object_ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 20:
        raise invalid_request("Copy between 1 and 20 supported objects.")
    ids = [editor._uuid_field(value, "object_ids") for value in ids]
    if len(set(ids)) != len(ids):
        raise invalid_request("Copied objects must have distinct identities.")
    copied = editor._verified_revision(project, source_document, source_revision)
    copied_path = editor._storage.paths.snapshot_path(
        project, copied["local_snapshot_path"], require_exists=True
    )
    current = editor._current_revision_source(project, document)
    if current["revision_id"] != baseline:
        raise editor._revision_conflict()
    result_ids: list[str] = []

    def write(original: Path, destination: Path) -> None:
        result_ids.extend(
            write_paste(
                editor,
                original,
                destination,
                document=document,
                current=current,
                copied_path=copied_path,
                copied=copied,
                source_document=source_document,
                source_slide=source_slide,
                target_slide=target_slide,
                ids=ids,
            )
        )

    result = editor._commit_revision(project, document, baseline, current, write)
    return {**result, "created_object_ids": result_ids}


def write_paste(
    editor: Any,
    original: Path,
    destination: Path,
    *,
    document: str,
    current: Any,
    copied_path: Path,
    copied: Any,
    source_document: str,
    source_slide: str,
    target_slide: str,
    ids: list[str],
) -> list[str]:
    from presenter_core.ingestion.security import (
        MAX_ARCHIVE_EXPANDED_BYTES,
        MAX_SOURCE_BYTES,
        preflight_source,
    )
    from presenter_core.presentation.editing import (
        _MAX_OOXML_SHAPE_ID,
        _MAX_XML_PART_BYTES,
        _next_ooxml_shape_id,
        _verified_source_archive,
    )

    def reject(message: str) -> CoreDomainError:
        return CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", message)

    def inspect(path: Path, document_id: str, metadata: Any) -> Any:
        with path.open("rb") as handle:
            return inspect_pptx_snapshot(
                handle,
                document_id=document_id,
                expected_sha256=metadata["sha256"],
                byte_size=metadata["byte_size"],
            )

    source = inspect(copied_path, source_document, copied)
    target = inspect(original, document, current)
    source_info = next((s for s in source.slides if s.slide_id == source_slide), None)
    target_info = next((s for s in target.slides if s.slide_id == target_slide), None)
    if source_info is None or target_info is None:
        raise reject("The copied or destination slide is unavailable.")
    selected = [o for o in source_info.objects if o.object_id in ids]
    if len(selected) != len(ids) or any(
        o.kind not in {"sp", "pic", "graphicFrame", "grpSp"}
        or not o.delete_editable
        or not o.geometry_editable
        or o.geometry is None
        for o in selected
    ):
        raise reject("The clipboard includes objects that cannot be pasted safely.")
    with _verified_source_archive(
        copied_path, expected_sha256=copied["sha256"], expected_byte_size=copied["byte_size"]
    ) as archive:
        selection_root = _parse_xml_part(archive, archive.getinfo(source_info.part_name))
        selection_size = sum(
            len(
                editor._find_object_node(selection_root, ooxml_id=o.ooxml_id, kind=o.kind).xpath(
                    ".//p:cNvPr", namespaces=_NS
                )
            )
            for o in selected
        )
    if target.object_count + selection_size > OBJECT_LIMIT:
        raise reject("Pasting these objects would exceed the presentation object limit.")
    left = min(o.geometry.x_emu for o in selected)
    top = min(o.geometry.y_emu for o in selected)
    right = max(o.geometry.x_emu + o.geometry.width_emu for o in selected)
    bottom = max(o.geometry.y_emu + o.geometry.height_emu for o in selected)
    if right - left > target.slide_width_emu or bottom - top > target.slide_height_emu:
        raise reject("The copied selection is larger than the destination slide.")
    # Preserve physical size and relative spacing, translating the entire selection together.
    dx = max(-left, min(228600, target.slide_width_emu - right))
    dy = max(-top, min(228600, target.slide_height_emu - bottom))
    names: list[str] = []
    native_ids: list[str] = []
    geometries: list[dict[str, int]] = []
    subtree_ids: list[list[str]] = []
    source_subtrees: list[list[Any]] = []
    expected_xml: list[bytes] = []
    with (
        _verified_source_archive(
            original, expected_sha256=current["sha256"], expected_byte_size=current["byte_size"]
        ) as target_archive,
        _verified_source_archive(
            copied_path, expected_sha256=copied["sha256"], expected_byte_size=copied["byte_size"]
        ) as source_archive,
    ):
        target_members = {i.filename: i for i in target_archive.infolist()}
        source_members = {i.filename: i for i in source_archive.infolist()}
        root = _parse_xml_part(target_archive, target_members[target_info.part_name])
        source_root = _parse_xml_part(source_archive, source_members[source_info.part_name])
        tree = root.find("p:cSld/p:spTree", _NS)
        if tree is None:
            raise reject("The destination has no native object tree.")
        rel_name = posixpath.join(
            posixpath.dirname(target_info.part_name),
            "_rels",
            posixpath.basename(target_info.part_name) + ".rels",
        )
        rels = (
            _parse_xml_part(target_archive, target_members[rel_name])
            if rel_name in target_members
            else etree.Element(f"{{{PACKAGE_REL_NS}}}Relationships", nsmap={None: PACKAGE_REL_NS})
        )
        _relationships(rels)
        source_rel_name = posixpath.join(
            posixpath.dirname(source_info.part_name),
            "_rels",
            posixpath.basename(source_info.part_name) + ".rels",
        )
        source_relations = (
            _relationships(_parse_xml_part(source_archive, source_members[source_rel_name]))
            if source_rel_name in source_members
            else {}
        )
        types = _parse_xml_part(target_archive, target_members["[Content_Types].xml"])
        source_types = _parse_xml_part(source_archive, source_members["[Content_Types].xml"])
        content_types = {
            n.get("PartName", "").lstrip("/"): n.get("ContentType")
            for n in source_types.findall(f"{{{CT}}}Override")
        }
        defaults = {
            n.get("Extension"): n.get("ContentType")
            for n in source_types.findall(f"{{{CT}}}Default")
        }
        additions: dict[str, bytes] = {}
        mapped_images: dict[str, str] = {}
        mapped_charts: dict[str, str] = {}
        for obj in selected:
            node = copy.deepcopy(
                editor._find_object_node(source_root, ooxml_id=obj.ooxml_id, kind=obj.kind)
            )
            for style_id in node.findall(".//a:tableStyleId", _NS):

                def catalog(archive: zipfile.ZipFile, members: Any) -> Any:
                    main_rels = "ppt/_rels/presentation.xml.rels"
                    if main_rels not in members:
                        return []
                    relationships = _relationships(_parse_xml_part(archive, members[main_rels]))
                    references = [
                        r for r in relationships.values() if r[0] == f"{REL_NS}/tableStyles"
                    ]
                    if not references:
                        return []
                    if len(references) != 1 or references[0][2].casefold() != "internal":
                        raise reject("This table has an unsupported style catalog.")
                    part = _resolve_internal_part("ppt", references[0][1])
                    if part not in members:
                        raise reject("This table has a missing style catalog.")
                    return _parse_xml_part(archive, members[part])

                custom = next(
                    (
                        n
                        for n in catalog(source_archive, source_members)
                        if n.get("styleId") == style_id.text
                    ),
                    None,
                )
                if custom is not None:
                    matching = next(
                        (
                            n
                            for n in catalog(target_archive, target_members)
                            if n.get("styleId") == style_id.text
                        ),
                        None,
                    )
                    if matching is None or etree.tostring(custom, method="c14n") != etree.tostring(
                        matching, method="c14n"
                    ):
                        raise reject(
                            "This table needs a custom style unavailable in the destination."
                        )
            native = node.find(
                {
                    "sp": "p:nvSpPr/p:cNvPr",
                    "pic": "p:nvPicPr/p:cNvPr",
                    "graphicFrame": "p:nvGraphicFramePr/p:cNvPr",
                    "grpSp": "p:nvGrpSpPr/p:cNvPr",
                }[obj.kind],
                _NS,
            )
            if native is None:
                raise reject("The copied object has no native identity.")
            identity = _next_ooxml_shape_id(tree)
            name = editor._duplicate_object_name(root, obj.name)
            native.set("id", identity)
            native.set("name", name)
            # IDs are slide-wide, including nested groups, and cannot be shared by copies.
            allocated = [identity]
            next_identity = int(identity) + 1
            identities = node.findall(".//p:cNvPr", _NS)
            source_by_id = {o.ooxml_id: o for o in source_info.objects}
            # The root ID was just replaced; descendant IDs still belong to the source.
            source_subtrees.append(
                [obj if item is native else source_by_id[item.get("id")] for item in identities]
            )
            if int(identity) + len(identities) - 1 > _MAX_OOXML_SHAPE_ID:
                raise reject("The slide cannot allocate identities for this group.")
            for child_identity in identities:
                if child_identity is native:
                    continue
                child_identity.set("id", str(next_identity))
                allocated.append(str(next_identity))
                next_identity += 1
            subtree_ids.append(allocated)
            offset = node.find(
                "p:xfrm/a:off"
                if obj.kind == "graphicFrame"
                else ("p:grpSpPr/a:xfrm/a:off" if obj.kind == "grpSp" else "p:spPr/a:xfrm/a:off"),
                _NS,
            )
            if offset is None:
                raise reject("The copied object has no supported transform.")
            geometry = asdict(obj.geometry)
            geometry.update(x_emu=geometry["x_emu"] + dx, y_emu=geometry["y_emu"] + dy)
            offset.set("x", str(geometry["x_emu"]))
            offset.set("y", str(geometry["y_emu"]))
            # Resolve every relationship attribute: missing/unknown dependencies fail before commit.
            for element in node.iter():
                for attribute, value in list(element.attrib.items()):
                    if not attribute.startswith(f"{{{REL_NS}}}"):
                        continue
                    if (
                        element.tag
                        == "{http://schemas.openxmlformats.org/drawingml/2006/chart}chart"
                    ):
                        continue
                    relation = source_relations.get(value)
                    if relation is None:
                        raise reject("A copied object has a missing package dependency.")
                    kind, reference, mode = relation
                    rid = "rIdCopilot" + uuid.uuid4().hex
                    if kind == f"{REL_NS}/image" and mode.casefold() == "internal":
                        part = _resolve_internal_part(
                            posixpath.dirname(source_info.part_name), reference
                        )
                        if part not in source_members:
                            raise reject("A copied image is missing.")
                        if part not in mapped_images:
                            new = (
                                "ppt/media/copilot-paste-"
                                + uuid.uuid4().hex
                                + posixpath.splitext(part)[1]
                            )
                            if new in target_members:
                                raise reject("A copied image identity is already in use.")
                            content_type = content_types.get(part) or defaults.get(
                                posixpath.splitext(part)[1].lstrip(".")
                            )
                            if content_type not in {"image/png", "image/jpeg"}:
                                raise reject(
                                    "Only embedded PNG and JPEG image dependencies can be pasted."
                                )
                            additions[new] = source_archive.read(source_members[part])
                            mapped_images[part] = new
                            etree.SubElement(
                                types,
                                f"{{{CT}}}Override",
                                PartName="/" + new,
                                ContentType=content_type,
                            )
                        reference = posixpath.relpath(
                            mapped_images[part], posixpath.dirname(target_info.part_name)
                        )
                    elif kind != f"{REL_NS}/hyperlink" or mode.casefold() != "external":
                        raise reject("A copied object has an unsupported package dependency.")
                    attrs = {"Id": rid, "Type": kind, "Target": reference}
                    if mode.casefold() == "external":
                        attrs["TargetMode"] = "External"
                    etree.SubElement(rels, f"{{{PACKAGE_REL_NS}}}Relationship", **attrs)
                    element.set(attribute, rid)
            # Clone every native chart frame, including those nested in groups.
            chart_frames = (
                [node] if obj.kind == "graphicFrame" else node.findall(".//p:graphicFrame", _NS)
            )
            for frame in chart_frames:
                cloned = clone_chart_graph(
                    source_archive,
                    target_info.part_name,
                    frame,
                    slide_relationships=rels,
                    content_types_root=types,
                    cloned_parts=mapped_charts,
                    source_slide_part=source_info.part_name,
                )
                if any(
                    name in target_members or name in additions
                    for name in cloned
                    if name not in {rel_name, "[Content_Types].xml"}
                ):
                    raise reject("A cloned chart dependency would overwrite an existing part.")
                additions.update(cloned)
            tree.append(node)
            expected_xml.append(etree.tostring(node, method="c14n", exclusive=True))
            names.append(name)
            native_ids.append(identity)
            geometries.append(geometry)
        additions[target_info.part_name] = etree.tostring(
            root, encoding="UTF-8", xml_declaration=True, standalone=True
        )
        additions[rel_name] = etree.tostring(
            rels, encoding="UTF-8", xml_declaration=True, standalone=True
        )
        additions["[Content_Types].xml"] = etree.tostring(
            types, encoding="UTF-8", xml_declaration=True, standalone=True
        )
        if any(
            len(v) > _MAX_XML_PART_BYTES
            for k, v in additions.items()
            if k.endswith((".xml", ".rels"))
        ):
            raise reject("The pasted package exceeds safe XML limits.")
        if len(target_members.keys() | additions.keys()) > 2048:
            raise reject("The pasted package exceeds safe part limits.")
        expanded = sum(i.file_size for i in target_members.values()) + sum(
            len(payload) - (target_members[name].file_size if name in target_members else 0)
            for name, payload in additions.items()
        )
        if expanded > MAX_ARCHIVE_EXPANDED_BYTES:
            raise reject("The pasted presentation exceeds the safe expanded package limit.")
        with zipfile.ZipFile(destination, "w", allowZip64=True) as output:
            output.comment = target_archive.comment
            for info in target_archive.infolist():
                payload = additions.pop(info.filename, None)
                if payload is not None:
                    output.writestr(copy.copy(info), payload)
                else:
                    with (
                        target_archive.open(info) as source_handle,
                        output.open(copy.copy(info), "w") as target_handle,
                    ):
                        shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
            for name, payload in additions.items():
                output.writestr(name, payload)
    if destination.stat().st_size > MAX_SOURCE_BYTES:
        raise reject("The pasted presentation exceeds the safe source size limit.")
    preflight_source(destination, "pptx")
    revised = inspect(
        destination,
        document,
        {"sha256": editor._sha256_path(destination), "byte_size": destination.stat().st_size},
    )
    if [s.slide_id for s in revised.slides] != [s.slide_id for s in target.slides]:
        raise reject("Pasting changed slide order or identity.")
    result_ids: list[str] = []
    for old, fresh in zip(target.slides, revised.slides, strict=True):
        existing = fresh.objects[: len(old.objects)]
        if existing != old.objects or (old.slide_id != target_slide and fresh != old):
            raise reject("Pasting changed an existing slide object.")
        if old.slide_id == target_slide:
            new_objects = fresh.objects[len(old.objects) :]
            if len(new_objects) != selection_size:
                raise reject("Pasted object count did not match the selection.")
            with zipfile.ZipFile(destination) as archive:
                revised_root = _parse_xml_part(archive, archive.getinfo(target_info.part_name))
            cursor = 0
            for source_object, name, identity, geometry, allocated, originals, native_xml in zip(
                selected,
                names,
                native_ids,
                geometries,
                subtree_ids,
                source_subtrees,
                expected_xml,
                strict=True,
            ):
                node = editor._find_object_node(
                    revised_root, ooxml_id=identity, kind=source_object.kind
                )
                if etree.tostring(node, method="c14n", exclusive=True) != native_xml:
                    raise reject("The pasted native subtree changed during publication.")
                subtree = new_objects[cursor : cursor + len(allocated)]
                if [o.ooxml_id for o in subtree] != allocated:
                    raise reject("The pasted group identities failed validation.")
                for index, (member, original_member) in enumerate(
                    zip(subtree, originals, strict=True)
                ):
                    expected_member = replace(
                        original_member,
                        object_id=member.object_id,
                        ooxml_id=member.ooxml_id,
                        name=name if index == 0 else original_member.name,
                        geometry=member.geometry if index == 0 else original_member.geometry,
                    )
                    # Fingerprints include namespace context, offsets and remapped references.
                    # Canonical subtree validation checks XML; compare semantic fields here.
                    for field in ("shape_style", "text_style"):
                        old_style, fresh_style = (
                            getattr(expected_member, field),
                            getattr(member, field),
                        )
                        if old_style is not None and fresh_style is not None:
                            expected_member = replace(
                                expected_member,
                                **{field: replace(old_style, fingerprint=fresh_style.fingerprint)},
                            )
                    if member != expected_member:
                        raise reject("Pasting changed native group content or child geometry.")
                created = subtree[0]
                cursor += len(allocated)
                if (
                    created.name != name
                    or created.ooxml_id != identity
                    or created.kind != source_object.kind
                    or created.text != source_object.text
                    or not created.geometry_editable
                    or created.geometry is None
                    or asdict(created.geometry) != geometry
                ):
                    raise reject("The pasted object failed native validation.")
                result_ids.append(created.object_id)
    return result_ids
