"""Discover and edit bounded native chart caches with isolated literal workbooks."""

from __future__ import annotations

import copy
import hashlib
import posixpath
import shutil
import uuid
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.charts import (
    CNS,
    NS,
    literal_workbook,
    read_chart,
    summary,
    validate_data,
)
from presenter_core.presentation.fidelity import (
    REL_NS,
    _notes_body_is_plain_editable,
    _parse_xml_part,
    _relationships,
    _resolve_internal_part,
    inspect_pptx_snapshot,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService
    from presenter_core.presentation.workspace_source import PresentationWorkspaceSourceService

PACKAGE_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def inspect_chart(
    archive: zipfile.ZipFile, slide_part: str, frame: Any
) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
    graphics = frame.findall("a:graphic/a:graphicData", NS)
    if len(graphics) != 1 or graphics[0].get("uri") != CNS:
        return None
    info: dict[str, Any] = {
        "editable": False,
        "reason": "This chart type, cache or workbook is unsupported.",
    }
    refs = graphics[0].findall("c:chart", NS)
    if len(refs) != 1 or len(graphics[0]) != 1 or frame.findall(".//p:ph", NS):
        return info, None
    slide_rels_part = posixpath.join(
        posixpath.dirname(slide_part), "_rels", posixpath.basename(slide_part) + ".rels"
    )
    members = {v.filename: v for v in archive.infolist()}
    if slide_rels_part not in members:
        return info, None
    slide_rels = _parse_xml_part(archive, members[slide_rels_part])
    relation = _relationships(slide_rels).get(refs[0].get(f"{{{REL_NS}}}id", ""))
    if not relation or relation[0] != f"{REL_NS}/chart" or relation[2].casefold() != "internal":
        return info, None
    chart_part = _resolve_internal_part(posixpath.dirname(slide_part), relation[1])
    rels_part = posixpath.join(
        posixpath.dirname(chart_part), "_rels", posixpath.basename(chart_part) + ".rels"
    )
    if chart_part not in members or rels_part not in members:
        return info, None
    chart = _parse_xml_part(archive, members[chart_part])
    relations = _parse_xml_part(archive, members[rels_part])
    info["fingerprint"] = hashlib.sha256(
        etree.tostring(frame, method="c14n")
        + chart_part.encode()
        + etree.tostring(chart, method="c14n")
        + etree.tostring(relations, method="c14n")
    ).hexdigest()
    data = read_chart(chart)
    if data is None:
        return info, None
    info["data"] = data
    if chart.findall(".//c:extLst", NS) or frame.findall(".//p:extLst", NS):
        info["reason"] = "Charts with extension data remain read-only."
        return info, None
    external = chart.findall("c:externalData", NS)
    parsed_relations = _relationships(relations)
    if len(external) != 1:
        return info, None
    workbook_rid = external[0].get(f"{{{REL_NS}}}id", "")
    workbook_rel = parsed_relations.get(workbook_rid)
    if (
        not workbook_rel
        or workbook_rel[0] != f"{REL_NS}/package"
        or workbook_rel[2].casefold() != "internal"
    ):
        info["reason"] = "Charts with linked external workbooks remain read-only."
        return info, None
    workbook_part = _resolve_internal_part(posixpath.dirname(chart_part), workbook_rel[1])
    if workbook_part not in members or not workbook_part.casefold().endswith(".xlsx"):
        return info, None
    for _, target, mode in parsed_relations.values():
        if (
            mode.casefold() != "internal"
            or _resolve_internal_part(posixpath.dirname(chart_part), target) not in members
        ):
            return info, None
    nodes = chart.findall("c:chart/c:plotArea/*/c:ser", NS)
    for series in nodes:
        for field, ref, cache in [
            ("tx", "strRef", "strCache"),
            ("cat", "strRef", "strCache"),
            ("val", "numRef", "numCache"),
        ]:
            containers = series.findall(f"c:{field}/c:{ref}", NS)
            if len(containers) != 1 or [v.tag for v in containers[0]] != [
                f"{{{CNS}}}f",
                f"{{{CNS}}}{cache}",
            ]:
                return info, None
    if len(chart.findall(".//c:f", NS)) != 3 * len(nodes):
        info["reason"] = "Additional linked title or data-label workbook formulas remain read-only."
        return info, None
    title_body = chart.find("c:chart/c:title/c:tx/c:rich", NS)
    title_editable = title_body is not None and _notes_body_is_plain_editable(
        title_body.findall("a:p", NS)
    )
    info.update(editable=True, reason=None, title_editable=title_editable)
    from presenter_core.presentation.chart_structure import structure_reason

    reason = structure_reason(chart, data)
    info.update(structure_editable=reason is None, structure_reason=reason)
    from presenter_core.presentation.chart_legend import inspect_legend

    info["legend"] = inspect_legend(chart)
    from presenter_core.presentation.chart_colors import inspect_colors

    info["colors"] = inspect_colors(chart, data)
    from presenter_core.presentation.chart_fills import inspect_fills

    info["fills"] = inspect_fills(chart, data)
    from presenter_core.presentation.chart_markers import inspect_markers

    info["markers"] = inspect_markers(chart, data)
    from presenter_core.presentation.chart_labels import inspect_labels

    info["labels"] = inspect_labels(chart, data)
    from presenter_core.presentation.chart_axes import inspect_axes

    info["axes"] = inspect_axes(chart)
    return info, {
        "chart": chart,
        "chart_part": chart_part,
        "relations": relations,
        "workbook_rid": workbook_rid,
        "slide_rels": slide_rels,
        "slide_rels_part": slide_rels_part,
    }


class PresentationChartService:
    def __init__(self, sources: PresentationWorkspaceSourceService) -> None:
        self._sources = sources

    def list_charts(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.editing import _verified_source_archive
        from presenter_core.presentation.semantics import PresentationSemanticService

        reject_unknown_fields(params, {"project_id", "document_id", "revision_id", "slide_number"})
        project, document, revision, native = self._sources.read_revision_inventory(
            {k: v for k, v in params.items() if k != "slide_number"}
        )
        ordinal = params.get("slide_number")
        if type(ordinal) is not int or not 1 <= ordinal <= len(native.slides):
            raise invalid_request("Choose a slide number.")
        slide = native.slides[ordinal - 1]
        with self._sources._storage.project_database(project) as conn:
            row = conn.execute(
                "SELECT local_snapshot_path, sha256, byte_size "
                "FROM presentation_revisions WHERE id=?",
                (revision,),
            ).fetchone()
        path = self._sources._storage.paths.snapshot_path(
            project, row["local_snapshot_path"], require_exists=True
        )
        items = []
        with _verified_source_archive(
            path, expected_sha256=row["sha256"], expected_byte_size=row["byte_size"]
        ) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            for frame in root.findall("p:cSld/p:spTree/p:graphicFrame", NS):
                inspected = inspect_chart(archive, slide.part_name, frame)
                if inspected is None:
                    continue
                identity = frame.find("p:nvGraphicFramePr/p:cNvPr", NS)
                obj = next(v for v in slide.objects if v.ooxml_id == identity.get("id"))
                items.append({"object_id": obj.object_id, "name": obj.name, **inspected[0]})
                if len(items) >= 20:
                    break
        with self._sources._storage.project_database(project) as conn:
            PresentationSemanticService._require_current_presentation(
                conn, project, document, revision
            )
        return {
            "revision_id": revision,
            "slide_id": slide.slide_id,
            "slide_width_emu": native.slide_width_emu,
            "slide_height_emu": native.slide_height_emu,
            "items": items,
        }


def replace_chart_data(
    editor: PresentationEditService, params: dict[str, Any], *, structural: bool = False
) -> dict[str, Any]:
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
            "title",
            "chart_type",
            "categories",
            "series",
            *({"category_sources", "series_sources"} if structural else set()),
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    object_id = editor._uuid_field(params.get("object_id"), "object_id")
    fingerprint = params.get("expected_fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise invalid_request("Provide the verified chart fingerprint.")
    data = validate_data(params)
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
        if slide is None or obj is None:
            raise CoreDomainError("PRESENTATION_EDIT_TARGET_NOT_FOUND", "The chart is unavailable.")
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            frames = [
                v
                for v in root.findall("p:cSld/p:spTree/p:graphicFrame", NS)
                if v.find("p:nvGraphicFramePr/p:cNvPr", NS).get("id") == obj.ooxml_id
            ]
            inspected = (
                inspect_chart(archive, slide.part_name, frames[0]) if len(frames) == 1 else None
            )
            if not inspected or not inspected[0]["editable"] or inspected[1] is None:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED", "The chart cannot be safely edited."
                )
            info, context = inspected
            assert context is not None
            if fingerprint != info["fingerprint"]:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET", "The chart changed. Reload its data."
                )
            old = info["data"]
            if (
                data["chart_type"] != old["chart_type"]
                or (not structural and len(data["categories"]) != len(old["categories"]))
                or (not structural and len(data["series"]) != len(old["series"]))
            ):
                raise invalid_request(
                    "Data editing preserves chart type, category count and series count."
                )
            if not info["title_editable"] and data["title"] != old["title"]:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED", "The imported chart title must be preserved."
                )
            from presenter_core.presentation.chart_structure import replace_cache, reshape_chart

            chart = context["chart"]
            if structural:
                reshape_chart(chart, old, data, params)
            if data == old and (
                not structural
                or (
                    params["category_sources"] == list(range(len(old["categories"])))
                    and params["series_sources"] == list(range(len(old["series"])))
                )
            ):
                return False
            nodes = chart.findall("c:chart/c:plotArea/*/c:ser", NS)
            for column, (series, values) in enumerate(zip(nodes, data["series"], strict=True), 1):
                letter = chr(65 + column)
                for selector, texts, formula in [
                    ("c:tx/c:strRef", [values["name"]], f"Sheet1!${letter}$1"),
                    (
                        "c:cat/c:strRef",
                        data["categories"],
                        f"Sheet1!$A$2:$A${len(data['categories']) + 1}",
                    ),
                    (
                        "c:val/c:numRef",
                        values["values"],
                        f"Sheet1!${letter}$2:${letter}${len(data['categories']) + 1}",
                    ),
                ]:
                    ref = series.find(selector, NS)
                    ref.find("c:f", NS).text = formula
                    replace_cache(
                        ref,
                        texts,
                        structural=structural,
                        mapping=(
                            [0]
                            if selector == "c:tx/c:strRef"
                            else [None] * len(texts)
                            if selector == "c:val/c:numRef"
                            and params.get("series_sources", [])[column - 1] is None
                            else params["category_sources"]
                        )
                        if structural
                        else None,
                    )
            if data["title"] != old["title"]:
                body = chart.find("c:chart/c:title/c:tx/c:rich", NS)
                editor._replace_notes_paragraphs(body, body.findall("a:p", NS), data["title"])
            external = chart.find("c:externalData", NS)
            auto = external.find("c:autoUpdate", NS)
            if auto is None:
                auto = etree.SubElement(external, f"{{{CNS}}}autoUpdate")
            auto.set("val", "0")
            prefix = uuid.uuid4().hex
            directory = posixpath.dirname(context["chart_part"])
            chart_part = f"{directory}/copilot-{prefix}.xml"
            rels_part = f"{directory}/_rels/copilot-{prefix}.xml.rels"
            workbook_part = f"ppt/embeddings/copilot-{prefix}.xlsx"
            relations = context["relations"]
            for relation in relations:
                if relation.get("Id") == context["workbook_rid"]:
                    relation.set("Target", posixpath.relpath(workbook_part, directory))
            slide_rels = context["slide_rels"]
            rid = editor._new_relationship_id(set(_relationships(slide_rels)), "Chart")
            etree.SubElement(
                slide_rels,
                f"{{{PACKAGE_NS}}}Relationship",
                Id=rid,
                Type=f"{REL_NS}/chart",
                Target=posixpath.relpath(chart_part, posixpath.dirname(slide.part_name)),
            )
            frames[0].find("a:graphic/a:graphicData/c:chart", NS).set(f"{{{REL_NS}}}id", rid)
            workbook = literal_workbook(data)

            def serialize(node: Any) -> bytes:
                payload: bytes = etree.tostring(
                    node, encoding="UTF-8", xml_declaration=True, standalone=True
                )
                return payload

            additions = {
                chart_part: serialize(chart),
                rels_part: serialize(relations),
                workbook_part: workbook,
            }
            if {v.casefold() for v in additions} & {
                v.filename.casefold() for v in archive.infolist()
            }:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED", "Chart part paths already exist."
                )
            types = _parse_xml_part(archive, archive.getinfo("[Content_Types].xml"))
            for part, content_type in [
                (chart_part, "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"),
                (
                    workbook_part,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            ]:
                etree.SubElement(
                    types,
                    f"{{{CONTENT_NS}}}Override",
                    PartName="/" + part,
                    ContentType=content_type,
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
        expected = replace(
            slide,
            objects=tuple(
                replace(v, text=summary(data)) if v.object_id == object_id else v
                for v in slide.objects
            ),
        )
        if after.slides != tuple(expected if v.slide_id == slide_id else v for v in before.slides):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Chart data editing changed unrelated content.",
            )
        with zipfile.ZipFile(target) as archive:
            if (
                read_chart(_parse_xml_part(archive, archive.getinfo(chart_part))) != data
                or archive.read(workbook_part) != workbook
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED", "Chart data validation failed."
                )
        return None

    return editor._commit_revision(project, document, revision, source, write)
