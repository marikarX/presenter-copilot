from __future__ import annotations

import io
import zipfile

import pytest
from lxml import etree
from test_presentation_edit_planning import call
from test_presentation_native_layouts import path, scope
from test_presentation_tables import table_request
from test_presentation_transactions import context

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.fidelity import _NS
from presenter_core.presentation.table_structure import axis_sources, structure_supported
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def fixture(core):
    params, ops = context(core)
    saved = call(core, "presentation.workspace.create_table", table_request(params, ops))
    params["expected_revision_id"] = saved["revision_id"]
    inventory = call(
        core, "presentation.workspace.list_tables", {**scope(params), "slide_number": 1}
    )
    table = inventory["items"][0]
    return (
        params,
        {
            "slide_id": inventory["slide_id"],
            "object_id": table["object_id"],
            "expected_fingerprint": table["fingerprint"],
            "row_sources": [0, None, 2],
            "column_sources": [0, 1, None, 2],
            "cells": [
                ["Metric", "Current", "Owner", "Target"],
                ["New", "1", "Pat", "2"],
                ["Risk", "Measured", "Dana", "Bounded"],
            ],
        },
        table,
    )


def test_structure_review_retains_styles_geometry_parts_retrieval_and_undo(tmp_path):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, operation, table = fixture(core)
        assert table["structure_editable"]
        original = path(core, params).read_bytes()
        plan = call(
            core,
            "presentation.workspace.prepare_edit_plan",
            {
                **params,
                "summary": "Insert and remove table rows/columns",
                "operations": [{"type": "reshape_table", "params": operation}],
            },
        )
        assert path(core, params).read_bytes() == original
        identity = {
            "project_id": params["project_id"],
            "document_id": params["document_id"],
            "plan_id": plan["plan_id"],
        }
        call(core, "presentation.workspace.open_edit_plan_preview", identity)
        saved = call(
            core,
            "presentation.workspace.apply_edit_plan",
            {**identity, "reviewed_sha256": plan["sha256"], "confirm": True},
        )
        params["expected_revision_id"] = saved["revision_id"]
        fresh = call(
            core, "presentation.workspace.list_tables", {**scope(params), "slide_number": 1}
        )["items"][0]
        assert fresh["object_id"] == table["object_id"] and fresh["cells"] == operation["cells"]
        with (
            zipfile.ZipFile(io.BytesIO(original)) as before,
            zipfile.ZipFile(path(core, params)) as after,
        ):
            assert before.namelist() == after.namelist()
            assert [
                name for name in before.namelist() if before.read(name) != after.read(name)
            ] == ["ppt/slides/slide1.xml"]
            old = etree.fromstring(before.read("ppt/slides/slide1.xml"))
            new = etree.fromstring(after.read("ppt/slides/slide1.xml"))
            frame_path = "p:cSld/p:spTree/p:graphicFrame"
            a, b = old.find(frame_path, _NS), new.find(frame_path, _NS)
            assert etree.tostring(a.find("p:xfrm", _NS)) == etree.tostring(b.find("p:xfrm", _NS))
            old_rows = a.findall(".//a:tr", _NS)
            new_rows = b.findall(".//a:tr", _NS)
            assert sum(int(n.get("h")) for n in old_rows) == sum(int(n.get("h")) for n in new_rows)
            assert sum(int(n.get("w")) for n in a.findall(".//a:gridCol", _NS)) == sum(
                int(n.get("w")) for n in b.findall(".//a:gridCol", _NS)
            )
            for r, source_r in enumerate([0, 2, 2]):
                for c, source_c in enumerate([0, 1, 2, 2]):
                    old_cell = old_rows[source_r].findall("a:tc", _NS)[source_c]
                    new_cell = new_rows[r].findall("a:tc", _NS)[c]
                    assert etree.tostring(old_cell.find("a:tcPr", _NS)) == etree.tostring(
                        new_cell.find("a:tcPr", _NS)
                    )
                    assert etree.tostring(
                        old_cell.find("a:txBody/a:p/a:r/a:rPr", _NS)
                    ) == etree.tostring(new_cell.find("a:txBody/a:p/a:r/a:rPr", _NS))
        call(
            core,
            "source.reindex",
            {"project_id": params["project_id"], "document_id": params["document_id"]},
        )
        with core._storage.project_database(params["project_id"]) as conn:
            assert any("Pat" in row[0] for row in conn.execute("SELECT text FROM source_units"))
        # Fingerprints and dimensions continue protecting the legacy cell-only operation.
        call(core, "presentation.workspace.replace_table_cells", {**params, **operation}, ok=False)
        no_op = call(
            core,
            "presentation.workspace.prepare_edit_plan",
            {
                **params,
                "summary": "Verify unchanged table",
                "operations": [
                    {
                        "type": "reshape_table",
                        "params": {
                            **operation,
                            "expected_fingerprint": fresh["fingerprint"],
                            "row_sources": [0, 1, 2],
                            "column_sources": [0, 1, 2, 3],
                        },
                    }
                ],
            },
        )
        assert not no_op["changed"]
        call(
            core,
            "presentation.workspace.reject_edit_plan",
            {
                "project_id": params["project_id"],
                "document_id": params["document_id"],
                "plan_id": no_op["plan_id"],
            },
        )
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


@pytest.mark.parametrize("mapping", [[0, 0], [1, 0], [-1, 0], [True, 1], [0, 4], "bad", [], [None]])
def test_bad_structure_mapping(mapping):
    with pytest.raises(CoreDomainError):
        axis_sources(mapping, 2, 3, "row_sources")


@pytest.mark.parametrize(
    "case", ["row_missing", "column_duplicate", "stale", "oversize", "foreign", "unknown"]
)
def test_invalid_structure_plan_does_not_publish(tmp_path, case):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, op, _ = fixture(core)
        before = path(core, params).read_bytes()
        if case == "row_missing":
            op.pop("row_sources")
        elif case == "column_duplicate":
            op["column_sources"] = [0, 1, 1, 2]
        elif case == "stale":
            op["expected_fingerprint"] = "0" * 64
        elif case == "oversize":
            op["cells"] *= 5
        elif case == "foreign":
            op["object_id"] = "00000000-0000-4000-8000-000000000001"
        else:
            op["file_path"] = "arbitrary"
        error = call(
            core,
            "presentation.workspace.prepare_edit_plan",
            {
                **params,
                "summary": "Invalid structural draft",
                "operations": [{"type": "reshape_table", "params": op}],
            },
            ok=False,
        )
        assert error["code"] == (
            "PRESENTATION_EDIT_STALE_TARGET"
            if case == "stale"
            else "PRESENTATION_EDIT_TARGET_NOT_FOUND"
            if case == "foreign"
            else "INVALID_REQUEST"
        )
        assert path(core, params).read_bytes() == before
    finally:
        core.close()


@pytest.mark.parametrize(
    "case", ["row_attribute", "grid_extension", "zero_width", "negative_height"]
)
def test_complex_native_structure_locked(case):
    root = etree.fromstring(
        f'''<p:graphicFrame xmlns:p="{_NS["p"]}" xmlns:a="{_NS["a"]}">
        <a:graphic><a:graphicData><a:tbl><a:tblPr/>
        <a:tblGrid><a:gridCol w="100"/></a:tblGrid>
        <a:tr h="100"><a:tc/></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>'''
    )
    assert structure_supported(root)
    row = root.find(".//a:tr", _NS)
    grid = root.find(".//a:tblGrid", _NS)
    if case == "row_attribute":
        row.set("unsupported", "yes")
    elif case == "grid_extension":
        etree.SubElement(grid, f"{{{_NS['a']}}}extLst")
    elif case == "zero_width":
        grid[0].set("w", "0")
    else:
        row.set("h", "-1")
    assert not structure_supported(root)
