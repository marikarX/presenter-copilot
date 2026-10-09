"""Chart appearance edits isolate the selected chart and preserve workbook bytes."""

from __future__ import annotations

import copy
import posixpath
import re
import shutil
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request
from presenter_core.presentation.chart_editing import CONTENT_NS, PACKAGE_NS, inspect_chart
from presenter_core.presentation.charts import NS
from presenter_core.presentation.fidelity import (
    REL_NS,
    _parse_xml_part,
    _relationships,
    inspect_pptx_snapshot,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService


def edit_chart_appearance(
    editor: PresentationEditService,
    params: dict[str, Any],
    mutate: Callable[[Any], bool],
) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    object_id = editor._uuid_field(params.get("object_id"), "object_id")
    fingerprint = params.get("expected_fingerprint")
    if not isinstance(fingerprint, str) or not re.fullmatch("[0-9a-f]{64}", fingerprint):
        raise invalid_request("Provide the verified chart fingerprint.")
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
        if slide is None:
            raise CoreDomainError("PRESENTATION_EDIT_TARGET_NOT_FOUND", "The slide is unavailable.")
        obj = next((v for v in slide.objects if v.object_id == object_id), None)
        if obj is None:
            raise CoreDomainError("PRESENTATION_EDIT_TARGET_NOT_FOUND", "The chart is unavailable.")
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            frames = root.xpath(
                "p:cSld/p:spTree/p:graphicFrame[p:nvGraphicFramePr/p:cNvPr/@id=$identity]",
                namespaces=NS,
                identity=obj.ooxml_id,
            )
            inspected = (
                inspect_chart(archive, slide.part_name, frames[0]) if len(frames) == 1 else None
            )
            if not inspected or not inspected[0]["editable"] or inspected[1] is None:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED", "The chart cannot be safely edited."
                )
            info, context = inspected
            assert context is not None
            if info["fingerprint"] != fingerprint:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET", "The chart changed. Reload its appearance."
                )
            chart = context["chart"]
            if not mutate(chart):
                return False
            expected_chart = bytes(etree.tostring(chart, method="c14n"))
            prefix = uuid.uuid4().hex
            directory = posixpath.dirname(context["chart_part"])
            chart_part = f"{directory}/copilot-appearance-{prefix}.xml"
            rels_part = f"{directory}/_rels/copilot-appearance-{prefix}.xml.rels"
            slide_rels = context["slide_rels"]
            rid = editor._new_relationship_id(set(_relationships(slide_rels)), "Chart")
            etree.SubElement(
                slide_rels,
                f"{{{PACKAGE_NS}}}Relationship",
                Id=rid,
                Type=REL_NS + "/chart",
                Target=posixpath.relpath(chart_part, posixpath.dirname(slide.part_name)),
            )
            frames[0].find("a:graphic/a:graphicData/c:chart", NS).set(f"{{{REL_NS}}}id", rid)
            types = _parse_xml_part(archive, archive.getinfo("[Content_Types].xml"))
            etree.SubElement(
                types,
                f"{{{CONTENT_NS}}}Override",
                PartName="/" + chart_part,
                ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml",
            )

            def serialize(node: Any) -> bytes:
                return bytes(
                    etree.tostring(node, encoding="UTF-8", xml_declaration=True, standalone=True)
                )

            additions = {chart_part: serialize(chart), rels_part: serialize(context["relations"])}
            if {v.casefold() for v in additions} & {
                v.filename.casefold() for v in archive.infolist()
            }:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED", "Chart part paths already exist."
                )
            replacements = {
                slide.part_name: serialize(root),
                context["slide_rels_part"]: serialize(slide_rels),
                "[Content_Types].xml": serialize(types),
            }
            with zipfile.ZipFile(target, "w") as output:
                output.comment = archive.comment
                for member in archive.infolist():
                    if member.filename in replacements:
                        output.writestr(copy.copy(member), replacements.pop(member.filename))
                    else:
                        with (
                            archive.open(member) as reader,
                            output.open(copy.copy(member), "w") as writer,
                        ):
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
                for name, payload in {**replacements, **additions}.items():
                    output.writestr(name, payload)
        with target.open("rb") as handle:
            after = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=editor._sha256_path(target),
                byte_size=target.stat().st_size,
            )
        if after.slides != before.slides:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Chart appearance changed slide content or identities.",
            )
        with zipfile.ZipFile(target) as archive:
            edited = _parse_xml_part(archive, archive.getinfo(chart_part))
            if etree.tostring(edited, method="c14n") != expected_chart:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED", "Chart appearance failed verification."
                )
        return None

    return editor._commit_revision(project, document, revision, source, write)
