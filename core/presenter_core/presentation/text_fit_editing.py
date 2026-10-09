"""Atomic package-preserving native text fitting through existing revision transactions."""

from __future__ import annotations

import copy
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import _NS, FidelityGeometry, inspect_pptx_snapshot
from presenter_core.presentation.text_fit import apply_fit, calculate, validate_body
from presenter_core.presentation.text_inheritance import TextInheritance


def supported_shape(shape: Any) -> bool:
    body = shape.find("p:txBody", _NS)
    if (
        body is None
        or len(shape.findall("p:txBody", _NS)) != 1
        or shape.xpath(
            ".//a:extLst | .//p:extLst | .//a:hlinkClick | .//a:hlinkMouseOver", namespaces=_NS
        )
    ):
        return False
    allowed = {f"{{{_NS['a']}}}{n}" for n in ["bodyPr", "lstStyle", "p"]}
    paragraphs = body.findall("a:p", _NS)
    if (
        not 1 <= len(paragraphs) <= 128
        or any(n.tag not in allowed for n in body)
        or len(body.findall("a:bodyPr", _NS)) > 1
        or len(body.findall("a:lstStyle", _NS)) > 1
    ):
        return False
    props = body.find("a:bodyPr", _NS)
    if (
        props is not None
        and sum(
            etree.QName(n).localname in {"noAutofit", "normAutofit", "spAutoFit"} for n in props
        )
        > 1
    ):
        return False
    for p in paragraphs:
        allowed = {f"{{{_NS['a']}}}{n}" for n in ["pPr", "r", "br", "endParaRPr"]}
        if (
            any(n.tag not in allowed for n in p)
            or len(p.findall("a:pPr", _NS)) > 1
            or len(p.findall("a:endParaRPr", _NS)) > 1
        ):
            return False
        pp, end = p.find("a:pPr", _NS), p.find("a:endParaRPr", _NS)
        if (pp is not None and p[0] is not pp) or (end is not None and p[-1] is not end):
            return False
        for run in p.findall("a:r", _NS):
            if [n.tag for n in run] not in [
                [f"{{{_NS['a']}}}t"],
                [f"{{{_NS['a']}}}rPr", f"{{{_NS['a']}}}t"],
            ]:
                return False
        if any(len(br) or br.attrib for br in p.findall("a:br", _NS)):
            return False
    return True


def inspect_fit(reader: TextInheritance, shape: Any, *, text: str) -> dict[str, Any]:
    """Read a bounded target's resolved dependencies; feasibility is checked at preview."""
    result: dict[str, Any] = {"editable": False, "reason": None}
    try:
        if len(text) > 2000 or not supported_shape(shape):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This native text structure requires manual fitting.",
            )
        references = reader.slide.xpath(
            "./p:timing//@spid | .//a:stCxn/@id | .//a:endCxn/@id", namespaces=_NS
        )
        identity = shape.find("p:nvSpPr/p:cNvPr", _NS)
        if identity is None or identity.get("id") in references:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "Connector or animation dependencies prevent text fitting.",
            )
        if shape.getparent() is not reader.slide.find("p:cSld/p:spTree", _NS):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED", "Grouped text requires manual fitting."
            )
        resolved = reader.resolve(shape)
        x, y, width, height, _, _ = validate_body(resolved)
        # Use the same wrapping policy as fitting, but never mutate the detached resolution.
        probe = copy.deepcopy(resolved)
        probe.body.find("a:bodyPr", _NS).set("wrap", "square")
        from presenter_core.presentation.text_fit import measure

        try:
            measure(probe)
        except CoreDomainError as error:
            if error.code != "INVALID_REQUEST":
                raise
        cached = resolved.body.find("a:bodyPr/a:normAutofit", _NS)
        result.update(
            editable=True,
            fingerprint=resolved.fingerprint,
            geometry_pt={
                "left": x / 12700,
                "top": y / 12700,
                "width": width / 12700,
                "height": height / 12700,
            },
            paragraphs=list(resolved.paragraphs),
            cached_font_scale=int(cached.get("fontScale", "100000")) / 100000
            if cached is not None
            else 1,
        )
    except CoreDomainError as error:
        result["reason"] = error.message
    return result


class PresentationTextFitService:
    def __init__(self, sources: Any) -> None:
        self._sources = sources

    def list_targets(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.editing import _verified_source_archive

        reject_unknown_fields(params, {"project_id", "document_id", "revision_id", "slide_number"})
        project, document, revision, native = self._sources.read_revision_inventory(
            {k: v for k, v in params.items() if k != "slide_number"}
        )
        ordinal = params.get("slide_number")
        if type(ordinal) is not int or not 1 <= ordinal <= len(native.slides):
            raise invalid_request("Choose a slide number.")
        slide = native.slides[ordinal - 1]
        with self._sources._storage.project_database(project) as connection:
            row = connection.execute(
                "SELECT local_snapshot_path, sha256, byte_size FROM presentation_revisions "
                "WHERE id=? AND presentation_id=?",
                (revision, document),
            ).fetchone()
        if row is None:
            raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found.")
        path = self._sources._storage.paths.snapshot_path(
            project, row["local_snapshot_path"], require_exists=True
        )
        items = []
        with _verified_source_archive(
            path, expected_sha256=row["sha256"], expected_byte_size=row["byte_size"]
        ) as archive:
            reader = TextInheritance(archive, slide.part_name)
            for obj in slide.objects:
                if obj.kind != "sp":
                    continue
                shapes = reader.slide.xpath(
                    ".//p:sp[p:nvSpPr/p:cNvPr/@id=$identity]", namespaces=_NS, identity=obj.ooxml_id
                )
                if len(shapes) != 1:
                    continue
                items.append(
                    {
                        "object_id": obj.object_id,
                        "name": obj.name,
                        "text": obj.text,
                        **inspect_fit(reader, shapes[0], text=obj.text),
                    }
                )
        return {"revision_id": revision, "slide_id": slide.slide_id, "targets": items}


def unmanaged(shape: Any) -> bytes:
    clone = copy.deepcopy(shape)
    body_props = clone.find("p:txBody/a:bodyPr", _NS)
    if body_props is not None:
        body_props.attrib.pop("wrap", None)
    for node in clone.findall("p:spPr/a:xfrm", _NS):
        node.getparent().remove(node)
    for node in clone.findall("p:txBody/a:bodyPr/*", _NS):
        if etree.QName(node).localname in {"noAutofit", "normAutofit", "spAutoFit"}:
            node.getparent().remove(node)
    for node in (
        clone.findall(".//a:rPr", _NS)
        + clone.findall(".//a:defRPr", _NS)
        + clone.findall(".//a:endParaRPr", _NS)
    ):
        node.attrib.pop("sz", None)
        if not node.attrib and not len(node):
            node.getparent().remove(node)
    for node in clone.findall("p:txBody/a:p/a:pPr", _NS) + clone.findall("p:txBody/a:bodyPr", _NS):
        if not node.attrib and not len(node):
            node.getparent().remove(node)
    return bytes(etree.tostring(clone, method="c14n"))


def fit_text(editor: Any, params: dict[str, Any]) -> dict[str, Any]:
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
            "strategy",
            "minimum_size_pt",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    object_id = editor._uuid_field(params.get("object_id"), "object_id")
    fingerprint = params.get("expected_fingerprint")
    if not isinstance(fingerprint, str) or not re.fullmatch("[a-f0-9]{64}", fingerprint):
        raise invalid_request("Provide the resolved text fitting fingerprint.")
    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()
    outcome: dict[str, Any] = {}

    def write(original: Path, target: Path) -> bool:
        with original.open("rb") as handle:
            before = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=source["sha256"],
                byte_size=source["byte_size"],
            )
        slide = next((s for s in before.slides if s.slide_id == slide_id), None)
        obj = next((o for o in slide.objects if o.object_id == object_id), None) if slide else None
        if obj is None or obj.kind != "sp" or len(obj.text) > 2000:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED", "Select a supported native text shape."
            )
        assert slide is not None
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            reader = TextInheritance(archive, slide.part_name)
            shape = editor._find_shape(reader.slide, obj.ooxml_id)
            if not supported_shape(shape):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED",
                    "This native text structure requires manual fitting.",
                )
            references = reader.slide.xpath(
                "./p:timing//@spid | .//a:stCxn/@id | .//a:endCxn/@id", namespaces=_NS
            )
            if obj.ooxml_id in references:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED",
                    "Connector or animation dependencies prevent text fitting.",
                )
            if shape.getparent() is not reader.slide.find("p:cSld/p:spTree", _NS):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED", "Grouped text requires manual fitting."
                )
            resolved = reader.resolve(shape)
            if resolved.fingerprint != fingerprint:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET", "Text fitting dependencies changed."
                )
            old_geometry = validate_body(resolved)
            measured = calculate(
                resolved,
                params.get("strategy"),
                params.get("minimum_size_pt"),
                before.slide_height_emu,
            )
            geometry = FidelityGeometry(
                old_geometry[0], old_geometry[1], old_geometry[2], measured.height_emu
            )
            editor._validate_geometry_bounds(
                geometry,
                slide_width_emu=before.slide_width_emu,
                slide_height_emu=before.slide_height_emu,
                field="fitted_geometry",
            )
            expected = unmanaged(shape)
            if not apply_fit(shape, resolved, measured):
                return False
            if unmanaged(shape) != expected:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED", "Text fitting changed unmanaged content."
                )
            outcome.update(
                height_pt=measured.height_emu / 12700,
                font_scale=measured.font_scale,
                measured_height_pt=measured.measured_height_pt,
            )
            payload = etree.tostring(
                reader.slide, encoding="UTF-8", xml_declaration=True, standalone=True
            )
            if len(payload) > 2 * 1024 * 1024:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_RESOURCE_LIMIT", "The fitted slide exceeds the XML limit."
                )
            expected_shape = etree.tostring(shape, method="c14n")
            with zipfile.ZipFile(target, "w") as output:
                output.comment = archive.comment
                for member in archive.infolist():
                    if member.filename == slide.part_name:
                        output.writestr(copy.copy(member), payload)
                    else:
                        with (
                            archive.open(member) as incoming,
                            output.open(copy.copy(member), "w") as outgoing,
                        ):
                            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
        with target.open("rb") as handle:
            after = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=editor._sha256_path(target),
                byte_size=target.stat().st_size,
            )
        updated = next(s for s in after.slides if s.slide_id == slide_id)
        if (
            len(before.slides) != len(after.slides)
            or any(
                a != b
                for a, b in zip(before.slides, after.slides, strict=True)
                if a.slide_id != slide_id
            )
            or len(updated.objects) != len(slide.objects)
            or any(
                a != b
                for a, b in zip(slide.objects, updated.objects, strict=True)
                if a.object_id != object_id
            )
            or updated.speaker_notes != slide.speaker_notes
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Text fitting changed unrelated slide content.",
            )
        with zipfile.ZipFile(target) as archive:
            actual = TextInheritance(archive, slide.part_name)
            saved = editor._find_shape(actual.slide, obj.ooxml_id)
            if etree.tostring(saved, method="c14n") != expected_shape:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED", "The fitted text shape did not validate."
                )
        return True

    return {**editor._commit_revision(project, document, revision, source, write), **outcome}
