"""Native shape fill edits preserve all XML outside the selected fill."""

from __future__ import annotations

import copy
import hashlib
import re
import shutil
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.chart_fills import (
    _fills,
    _native_fill,
    describe_fill,
    validate_fill,
)
from presenter_core.presentation.fidelity import (
    _ordered_property_children_supported,
    _parse_xml_part,
    inspect_pptx_snapshot,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
ORDER = {
    "xfrm": 0,
    "prstGeom": 1,
    "custGeom": 1,
    "noFill": 2,
    "solidFill": 2,
    "gradFill": 2,
    "blipFill": 2,
    "pattFill": 2,
    "grpFill": 2,
    "ln": 3,
    "effectLst": 4,
    "effectDag": 4,
    "scene3d": 5,
    "sp3d": 6,
    "extLst": 7,
}


def inspect_fill(shape: Any) -> dict[str, Any]:
    reason = "Only top-level native shapes with one supported property container are editable."
    if shape is not None:
        props = shape.findall("p:spPr", NS)
        if not shape.findall("p:nvSpPr/p:nvPr/p:ph", NS) and len(props) == 1:
            fills = _fills(props[0])
            if (
                _ordered_property_children_supported(props[0], ORDER, repeatable_ranks=set())
                and len(fills) <= 1
            ):
                if not fills or etree.QName(fills[0]).localname in {
                    "noFill",
                    "solidFill",
                    "gradFill",
                }:
                    return {
                        "editable": True,
                        "reason": None,
                        "fingerprint": hashlib.sha256(
                            etree.tostring(shape, method="c14n")
                        ).hexdigest(),
                        "fill": describe_fill(props[0]),
                    }
                reason = "Picture, pattern and inherited group fills stay read-only."
    return {
        "editable": False,
        "reason": reason,
        "fingerprint": None,
        "fill": {"kind": "native_custom"},
    }


def _shape(root: Any, identity: str) -> Any:
    values = root.xpath(
        "p:cSld/p:spTree/p:sp[p:nvSpPr/p:cNvPr/@id=$identity]", namespaces=NS, identity=identity
    )
    return values[0] if len(values) == 1 else None


def shape_fill_inventory(
    editor: PresentationEditService, project: str, document: str, revision: str, number: int
) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()
    original = editor._storage.paths.snapshot_path(
        project, source["local_snapshot_path"], require_exists=True
    )
    with original.open("rb") as handle:
        fidelity = inspect_pptx_snapshot(
            handle,
            document_id=document,
            expected_sha256=source["sha256"],
            byte_size=source["byte_size"],
        )
    slide = next((v for v in fidelity.slides if v.ordinal == number), None)
    if slide is None:
        raise invalid_request("Choose a slide in this presentation.")
    with _verified_source_archive(
        original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
        items = [
            {
                "object_id": obj.object_id,
                "name": obj.name,
                **inspect_fill(_shape(root, obj.ooxml_id)),
            }
            for obj in slide.objects[:100]
            if obj.kind == "sp"
        ]
    return {"revision_id": revision, "slide_id": slide.slide_id, "items": items}


def list_shape_fills(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    reject_unknown_fields(params, {"project_id", "document_id", "revision_id", "slide_number"})
    number = params.get("slide_number")
    if type(number) is not int or not 1 <= number <= 5000:
        raise invalid_request("Choose a slide number from1 to5000.")
    return shape_fill_inventory(
        editor,
        editor._project_id(params.get("project_id")),
        editor._document_id(params.get("document_id")),
        editor._uuid_field(params.get("revision_id"), "revision_id"),
        number,
    )


def set_shape_fill(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "object_id",
            "expected_fingerprint",
            "fill",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    object_id = editor._uuid_field(params.get("object_id"), "object_id")
    fingerprint = params.get("expected_fingerprint")
    if not isinstance(fingerprint, str) or not re.fullmatch("[0-9a-f]{64}", fingerprint):
        raise invalid_request("Provide the verified shape fill fingerprint.")
    fill = validate_fill(params.get("fill"))
    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()

    def write(original: Path, target: Path) -> bool | None:
        with original.open("rb") as handle:
            before = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=source["sha256"],
                byte_size=source["byte_size"],
            )
        slide = next((v for v in before.slides if v.slide_id == slide_id), None)
        obj = next((v for v in slide.objects if v.object_id == object_id), None) if slide else None
        if slide is None or obj is None or obj.kind != "sp":
            raise CoreDomainError("PRESENTATION_EDIT_TARGET_NOT_FOUND", "The shape is unavailable.")
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            shape = _shape(root, obj.ooxml_id)
            info = inspect_fill(shape)
            if not info["editable"]:
                raise CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", info["reason"])
            if info["fingerprint"] != fingerprint:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET", "The shape changed. Reload its fill."
                )
            original_xml = copy.deepcopy(root)
            props = shape.find("p:spPr", NS)
            previous = _fills(props)
            previous_index = props.index(previous[0]) if previous else None
            previous_fill = copy.deepcopy(previous[0]) if previous else None
            for node in previous:
                props.remove(node)
            index = next(
                (
                    i
                    for i, node in enumerate(props)
                    if etree.QName(node).localname not in {"xfrm", "prstGeom", "custGeom"}
                ),
                len(props),
            )
            props.insert(index, _native_fill(fill))
            if etree.tostring(original_xml, method="c14n") == etree.tostring(root, method="c14n"):
                return False
            proof = copy.deepcopy(root)
            proof_props = _shape(proof, obj.ooxml_id).find("p:spPr", NS)
            for node in _fills(proof_props):
                proof_props.remove(node)
            if previous_fill is not None:
                proof_props.insert(previous_index, previous_fill)
            if etree.tostring(original_xml, method="c14n") != etree.tostring(proof, method="c14n"):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED", "Fill editing changed other slide XML."
                )
            expected_slide = etree.tostring(root, method="c14n")
            payload = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
            with zipfile.ZipFile(target, "w") as output:
                output.comment = archive.comment
                for member in archive.infolist():
                    if member.filename == slide.part_name:
                        output.writestr(copy.copy(member), payload)
                    else:
                        with (
                            archive.open(member) as reader,
                            output.open(copy.copy(member), "w") as writer,
                        ):
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
        with target.open("rb") as handle:
            after = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=editor._sha256_path(target),
                byte_size=target.stat().st_size,
            )
        revised_slide = next((v for v in after.slides if v.slide_id == slide_id), None)
        revised_obj = (
            next((v for v in revised_slide.objects if v.object_id == object_id), None)
            if revised_slide
            else None
        )
        if revised_obj is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED", "The shape identity changed."
            )
        expected_obj = replace(obj, shape_style=revised_obj.shape_style)
        expected_slides = tuple(
            replace(
                v, objects=tuple(expected_obj if o.object_id == object_id else o for o in v.objects)
            )
            if v.slide_id == slide_id
            else v
            for v in before.slides
        )
        if after.slides != expected_slides:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Shape fill changed other presentation content.",
            )
        with zipfile.ZipFile(target) as archive:
            if (
                etree.tostring(
                    _parse_xml_part(archive, archive.getinfo(slide.part_name)), method="c14n"
                )
                != expected_slide
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED",
                    "The selected fill failed package verification.",
                )
        return None

    return editor._commit_revision(project, document, revision, source, write)
