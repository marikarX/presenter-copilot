"""Bounded native table creation and cell-only editing without package flattening."""

from __future__ import annotations

import copy
import hashlib
import shutil
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    _NS,
    DRAWING_NS,
    OBJECT_LIMIT,
    PRESENTATION_NS,
    _notes_body_is_plain_editable,
    _parse_xml_part,
    inspect_pptx_snapshot,
)
from presenter_core.presentation.workspace_source import PresentationWorkspaceSourceService

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

TABLE_URI = "http://schemas.openxmlformats.org/drawingml/2006/table"


def validate_cells(value: Any) -> list[list[str]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 12:
        raise invalid_request("A table needs 1–12 rows.", field="cells")
    columns = len(value[0]) if isinstance(value[0], list) else 0
    if not 1 <= columns <= 8 or any(
        not isinstance(row, list) or len(row) != columns for row in value
    ):
        raise invalid_request("A table needs 1–8 columns and rectangular rows.", field="cells")
    total = 0
    for row in value:
        for text in row:
            if not isinstance(text, str) or len(text) > 500 or len(text.split("\n")) > 10:
                raise invalid_request("Each table cell accepts 500 characters and 10 paragraphs.")
            if any(
                not (
                    ord(c) in (9, 10)
                    or 0x20 <= ord(c) <= 0xD7FF
                    or 0xE000 <= ord(c) <= 0xFFFD
                    or 0x10000 <= ord(c) <= 0x10FFFF
                )
                for c in text
            ):
                raise invalid_request("A table cell contains unsupported characters.")
            total += len(text)
    if total > 10000:
        raise invalid_request("A table accepts at most 10000 characters.")
    return value


def inspect_table(frame: Any) -> dict[str, Any] | None:
    from presenter_core.presentation.table_structure import (
        row_identity,
        table_extensions_supported,
    )

    data = frame.findall("a:graphic/a:graphicData", _NS)
    if len(data) != 1 or data[0].get("uri") != TABLE_URI:
        return None
    result: dict[str, Any] = {
        "editable": False,
        "reason": "This table has merged, linked or complex cells.",
        "fingerprint": hashlib.sha256(etree.tostring(frame, method="c14n")).hexdigest(),
    }
    tables = data[0].findall("a:tbl", _NS)
    if (
        len(tables) != 1
        or len(data[0]) != 1
        # A table inserted into a content placeholder keeps its p:ph link; cell and
        # row edits never touch it.
        or frame.xpath(".//@r:* | .//p:ph[not(parent::p:nvPr)]", namespaces=_NS)
        or not table_extensions_supported(frame)
    ):
        return result
    table = tables[0]
    rows = table.findall("a:tr", _NS)
    columns = table.findall("a:tblGrid/a:gridCol", _NS)
    if not 1 <= len(rows) <= 12 or not 1 <= len(columns) <= 8:
        result["reason"] = "The cell editor supports up to 12 rows and 8 columns."
        return result
    values = []
    for row in rows:
        cells = row.findall("a:tc", _NS)
        if len(cells) != len(columns) or len(row) != len(cells) + (row_identity(row) is not None):
            return result
        texts = []
        for cell in cells:
            if [n.tag for n in cell] != [
                f"{{{DRAWING_NS}}}txBody",
                f"{{{DRAWING_NS}}}tcPr",
            ]:
                return result
            body = cell.find("a:txBody", _NS)
            paragraphs = body.findall("a:p", _NS)
            if not paragraphs or not all(_notes_body_is_plain_editable([p]) for p in paragraphs):
                return result
            texts.append(
                "\n".join(
                    "".join(n.text or "" for n in p.findall("a:r/a:t", _NS)) for p in paragraphs
                )
            )
        values.append(texts)
    from presenter_core.presentation.table_merge import layout

    try:
        spans = layout(frame)
    except CoreDomainError as error:
        result["reason"] = error.message
        return result
    if any(
        values[r][c] and spans["owners"][r][c][:2] != [r, c]
        for r, row in enumerate(values)
        for c in range(len(row))
    ):
        result["reason"] = "Hidden content in covered cells stays read-only."
        return result
    try:
        validate_cells(values)
    except CoreDomainError:
        result["reason"] = "The table text exceeds the bounded cell editor."
        return result
    from presenter_core.presentation.table_structure import structure_supported

    result.update(
        editable=True,
        reason=None,
        cells=values,
        spans=spans,
        structure_editable=not spans["regions"] and structure_supported(frame),
    )
    from presenter_core.presentation.table_format import inspect_formatting

    result["formatting"] = inspect_formatting(frame)
    from presenter_core.presentation.table_borders import inspect_borders

    result["borders"] = inspect_borders(frame)
    from presenter_core.presentation.table_fit import inspect_fit

    result["fit"] = inspect_fit(frame)
    return result


def make_table(
    editor: PresentationEditService, tree: Any, geometry: Any, cells: list[list[str]], header: bool
) -> Any:
    from presenter_core.presentation.editing import _next_ooxml_shape_id

    frame = etree.Element(f"{{{PRESENTATION_NS}}}graphicFrame")
    nv = etree.SubElement(frame, f"{{{PRESENTATION_NS}}}nvGraphicFramePr")
    identity = _next_ooxml_shape_id(tree)
    etree.SubElement(nv, f"{{{PRESENTATION_NS}}}cNvPr", id=identity, name=f"Table {identity}")
    etree.SubElement(nv, f"{{{PRESENTATION_NS}}}cNvGraphicFramePr")
    etree.SubElement(nv, f"{{{PRESENTATION_NS}}}nvPr")
    transform = etree.SubElement(frame, f"{{{PRESENTATION_NS}}}xfrm")
    etree.SubElement(
        transform, f"{{{DRAWING_NS}}}off", x=str(geometry.x_emu), y=str(geometry.y_emu)
    )
    etree.SubElement(
        transform, f"{{{DRAWING_NS}}}ext", cx=str(geometry.width_emu), cy=str(geometry.height_emu)
    )
    graphic = etree.SubElement(frame, f"{{{DRAWING_NS}}}graphic")
    data = etree.SubElement(graphic, f"{{{DRAWING_NS}}}graphicData", uri=TABLE_URI)
    table = etree.SubElement(data, f"{{{DRAWING_NS}}}tbl")
    etree.SubElement(table, f"{{{DRAWING_NS}}}tblPr")
    grid = etree.SubElement(table, f"{{{DRAWING_NS}}}tblGrid")
    cols = len(cells[0])
    for index in range(cols):
        etree.SubElement(
            grid,
            f"{{{DRAWING_NS}}}gridCol",
            w=str(
                geometry.width_emu // cols + (geometry.width_emu % cols if index == cols - 1 else 0)
            ),
        )
    for row_index, values in enumerate(cells):
        row = etree.SubElement(
            table,
            f"{{{DRAWING_NS}}}tr",
            h=str(
                geometry.height_emu // len(cells)
                + (geometry.height_emu % len(cells) if row_index == len(cells) - 1 else 0)
            ),
        )
        for text in values:
            cell = etree.SubElement(row, f"{{{DRAWING_NS}}}tc")
            body = etree.SubElement(cell, f"{{{DRAWING_NS}}}txBody")
            etree.SubElement(body, f"{{{DRAWING_NS}}}bodyPr")
            etree.SubElement(body, f"{{{DRAWING_NS}}}lstStyle")
            p = etree.SubElement(body, f"{{{DRAWING_NS}}}p")
            run = etree.SubElement(p, f"{{{DRAWING_NS}}}r")
            props = etree.SubElement(
                run, f"{{{DRAWING_NS}}}rPr", sz="1800", b="1" if header and row_index == 0 else "0"
            )
            fill = etree.SubElement(props, f"{{{DRAWING_NS}}}solidFill")
            etree.SubElement(
                fill,
                f"{{{DRAWING_NS}}}srgbClr",
                val="FFFFFF" if header and row_index == 0 else "182132",
            )
            etree.SubElement(props, f"{{{DRAWING_NS}}}latin", typeface="Arial")
            etree.SubElement(run, f"{{{DRAWING_NS}}}t").text = ""
            editor._replace_notes_paragraphs(body, [p], text)
            properties = etree.SubElement(
                cell,
                f"{{{DRAWING_NS}}}tcPr",
                marL="91440",
                marR="91440",
                marT="45720",
                marB="45720",
                anchor="ctr",
            )
            for edge in ("lnL", "lnR", "lnT", "lnB"):
                line = etree.SubElement(properties, f"{{{DRAWING_NS}}}{edge}", w="12700")
                fill = etree.SubElement(line, f"{{{DRAWING_NS}}}solidFill")
                etree.SubElement(fill, f"{{{DRAWING_NS}}}srgbClr", val="CBD5E1")
            fill = etree.SubElement(properties, f"{{{DRAWING_NS}}}solidFill")
            etree.SubElement(
                fill,
                f"{{{DRAWING_NS}}}srgbClr",
                val="26364D"
                if header and row_index == 0
                else "FFFFFF"
                if row_index % 2
                else "F1F5F9",
            )
    return frame


class PresentationTableService:
    def __init__(self, sources: PresentationWorkspaceSourceService) -> None:
        self._sources = sources

    def list_tables(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.editing import _verified_source_archive

        project, document, revision, native = self._sources.read_revision_inventory(
            {k: v for k, v in params.items() if k != "slide_number"}
        )
        reject_unknown_fields(params, {"project_id", "document_id", "revision_id", "slide_number"})
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
            for frame in root.findall("p:cSld/p:spTree/p:graphicFrame", _NS):
                info = inspect_table(frame)
                if info is None:
                    continue
                identity = frame.find("p:nvGraphicFramePr/p:cNvPr", _NS)
                obj = next(v for v in slide.objects if v.ooxml_id == identity.get("id"))
                items.append({"object_id": obj.object_id, "name": obj.name, **info})
                if len(items) >= 20:
                    break
        from presenter_core.presentation.semantics import PresentationSemanticService

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


def edit_table(
    editor: PresentationEditService,
    params: dict[str, Any],
    *,
    create: bool,
    structural: bool = False,
    formatting: bool = False,
    borders: bool = False,
    merging: bool = False,
    splitting: bool = False,
    fitting: bool = False,
) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            *(
                {"row_start", "row_end", "column_start", "column_end", "style"}
                if formatting
                else {"row_start", "row_end", "column_start", "column_end"}
                if merging or splitting
                else {"strategy"}
                if fitting
                else {
                    "row_start",
                    "row_end",
                    "column_start",
                    "column_end",
                    "border_scope",
                    "line_style",
                    "width_pt",
                    "color",
                }
                if borders
                else {"cells"}
            ),
            *({"row_sources", "column_sources"} if structural else set()),
            *({"geometry", "header_row"} if create else {"object_id", "expected_fingerprint"}),
        },
    )
    project, document = (
        editor._project_id(params.get("project_id")),
        editor._document_id(params.get("document_id")),
    )
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    cells = (
        []
        if formatting or borders or merging or splitting or fitting
        else validate_cells(params.get("cells"))
    )
    geometry = editor._geometry_field(params.get("geometry"), "geometry") if create else None
    header = params.get("header_row", True)
    if create and type(header) is not bool:
        raise invalid_request("header_row must be a boolean.")
    object_id = editor._uuid_field(params.get("object_id"), "object_id") if not create else None
    fingerprint = params.get("expected_fingerprint")
    if not create and (not isinstance(fingerprint, str) or len(fingerprint) != 64):
        raise invalid_request("Provide the verified table fingerprint.")
    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()
    created: list[str] = []
    fitted_geometry = None

    def write(original: Path, target: Path) -> bool:
        nonlocal cells, fitted_geometry
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
        if create:
            assert geometry is not None
            if before.object_count >= OBJECT_LIMIT:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_RESOURCE_LIMIT", "The object limit has been reached."
                )
            editor._validate_geometry_bounds(
                geometry,
                slide_width_emu=before.slide_width_emu,
                slide_height_emu=before.slide_height_emu,
                field="geometry",
            )
            if geometry.width_emu < len(cells[0]) or geometry.height_emu < len(cells):
                raise invalid_request("The table dimensions are too small.")
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            tree = root.find("p:cSld/p:spTree", _NS)
            if create:
                frame = make_table(editor, tree, geometry, cells, header)
                extensions = tree.findall("p:extLst", _NS)
                if len(extensions) > 1 or (extensions and tree[-1] is not extensions[0]):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED", "The shape tree is unsupported."
                    )
                tree.insert(tree.index(extensions[0]) if extensions else len(tree), frame)
            else:
                obj = next((v for v in slide.objects if v.object_id == object_id), None)
                frames = [
                    v
                    for v in tree.findall("p:graphicFrame", _NS)
                    if v.find("p:nvGraphicFramePr/p:cNvPr", _NS).get("id")
                    == (obj.ooxml_id if obj else None)
                ]
                if len(frames) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The table is unavailable."
                    )
                frame = frames[0]
                info = inspect_table(frame)
                if not info or not info["editable"]:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED", "The table cannot be safely edited."
                    )
                if info["fingerprint"] != fingerprint:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET", "The table changed. Reload its cells."
                    )
                if fitting:
                    from presenter_core.presentation.table_fit import fit_rows

                    cells = info["cells"]
                    if not fit_rows(frame, params.get("strategy"), before.slide_height_emu):
                        return False
                    if obj is None or obj.geometry is None:
                        raise invalid_request("The table geometry is unavailable.")
                    fitted_geometry = replace(
                        obj.geometry, height_emu=int(frame.find("p:xfrm/a:ext", _NS).get("cy"))
                    )
                    editor._validate_geometry_bounds(
                        fitted_geometry,
                        slide_width_emu=before.slide_width_emu,
                        slide_height_emu=before.slide_height_emu,
                        field="fitted_geometry",
                    )
                elif merging or splitting:
                    from presenter_core.presentation.table_merge import merge_cells

                    if not merge_cells(editor, frame, params, split=splitting):
                        return False
                    merged_info = inspect_table(frame)
                    assert merged_info is not None
                    cells = merged_info["cells"]
                elif borders:
                    from presenter_core.presentation.table_borders import set_borders

                    cells = info["cells"]
                    if not set_borders(frame, params):
                        return False
                elif formatting:
                    from presenter_core.presentation.table_format import format_cells

                    cells = info["cells"]
                    if not format_cells(frame, params):
                        return False
                elif structural:
                    from presenter_core.presentation.table_structure import reshape_table

                    if not reshape_table(
                        editor,
                        frame,
                        cells,
                        params.get("row_sources"),
                        params.get("column_sources"),
                    ):
                        return False
                elif len(cells) != len(info["cells"]) or len(cells[0]) != len(info["cells"][0]):
                    raise invalid_request("Cell editing preserves the table dimensions.")
                elif cells == info["cells"]:
                    return False
                if (
                    not structural
                    and not formatting
                    and not borders
                    and not merging
                    and not splitting
                    and not fitting
                ):
                    from presenter_core.presentation.table_merge import replace_text

                    for r, (row, values) in enumerate(
                        zip(
                            frame.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS),
                            cells,
                            strict=True,
                        )
                    ):
                        for c, (cell, text) in enumerate(
                            zip(row.findall("a:tc", _NS), values, strict=True)
                        ):
                            if text == info["cells"][r][c]:
                                continue
                            owner = info["spans"]["owners"][r][c]
                            if owner[:2] != [r, c]:
                                raise invalid_request("Edit merged text at its top-left cell.")
                            replace_text(editor, cell, text)
            expected_frame = etree.tostring(frame, method="c14n")
            shape_id = frame.find("p:nvGraphicFramePr/p:cNvPr", _NS).get("id")
            payload = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
            if len(payload) > 2 * 1024 * 1024:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_RESOURCE_LIMIT", "The slide XML exceeds the safe limit."
                )
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
        updated = next(v for v in after.slides if v.slide_id == slide_id)
        if (
            len(after.slides) != len(before.slides)
            or any(
                old != new
                for old, new in zip(before.slides, after.slides, strict=True)
                if old.slide_id != slide_id
            )
            or updated.objects[: len(slide.objects)]
            != tuple(
                replace(
                    obj,
                    text="\n".join("\t".join(row) for row in cells),
                    geometry=fitted_geometry or obj.geometry,
                )
                if not create and obj.object_id == object_id
                else obj
                for obj in slide.objects
            )
            or len(updated.objects) != len(slide.objects) + int(create)
            or updated.speaker_notes != slide.speaker_notes
            or updated.speaker_notes_editable != slide.speaker_notes_editable
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED", "Table editing changed unrelated content."
            )
        with zipfile.ZipFile(target) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            actual = next(
                v
                for v in root.findall("p:cSld/p:spTree/p:graphicFrame", _NS)
                if v.find("p:nvGraphicFramePr/p:cNvPr", _NS).get("id") == shape_id
            )
            if etree.tostring(actual, method="c14n") != expected_frame:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED", "The native table did not validate."
                )
        if create:
            created.append(updated.objects[-1].object_id)
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {
        **result,
        **({"created_object_id": created[0]} if create and created else {}),
        "slide_id": slide_id,
    }
