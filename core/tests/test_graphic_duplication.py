from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from test_graphic_geometry import fixture
from test_presentation_chart_editing import imported
from test_presentation_edit_planning import call
from test_presentation_native_layouts import path, scope

from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


@pytest.mark.parametrize("kind", ["chart", "table"])
def test_duplicate_native_graphic_is_independent_and_undoable(tmp_path: Path, kind: str):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, inventory, obj = fixture(core, tmp_path, kind)
        original = path(core, params).read_bytes()
        saved = call(
            core,
            "presentation.workspace.duplicate_object",
            {
                **params,
                "slide_id": inventory["slide_id"],
                "object_id": obj["object_id"],
                "expected_geometry": obj["geometry"],
            },
        )
        params["expected_revision_id"] = saved["revision_id"]
        assert saved["changed"] and saved["created_object_id"] != obj["object_id"]
        fresh = call(
            core, "presentation.workspace.list_text_targets", {**scope(params), "slide_number": 1}
        )
        created = next(o for o in fresh["objects"] if o["object_id"] == saved["created_object_id"])
        assert created["kind"] == obj["kind"] and created["name"] != obj["name"]
        assert created["geometry"]["width_emu"] == obj["geometry"]["width_emu"]
        assert next(o for o in fresh["objects"] if o["object_id"] == obj["object_id"]) == obj
        with (
            zipfile.ZipFile(io.BytesIO(original)) as before,
            zipfile.ZipFile(path(core, params)) as after,
        ):
            changed = [n for n in before.namelist() if before.read(n) != after.read(n)]
            if kind == "table":
                assert changed == ["ppt/slides/slide1.xml"]
            else:
                assert set(changed) == {
                    "ppt/slides/slide1.xml",
                    "ppt/slides/_rels/slide1.xml.rels",
                    "[Content_Types].xml",
                }
                added = set(after.namelist()) - set(before.namelist())
                assert len(added) == 3
                workbook = next(n for n in added if n.endswith(".xlsx"))
                old_workbook = next(n for n in before.namelist() if n.endswith(".xlsx"))
                assert after.read(workbook) == before.read(old_workbook)
                cloned_chart = next(n for n in added if n.endswith(".xml") and "/_rels/" not in n)
                assert cloned_chart.startswith("ppt/charts/copilot-copy-")
                assert after.read(cloned_chart) == before.read("ppt/charts/chart1.xml")
                charts = call(
                    core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1}
                )["items"]
                assert len(charts) == 2 and charts[0]["data"] == charts[1]["data"]
                target = charts[1]
                edit = call(
                    core,
                    "presentation.workspace.replace_chart_data",
                    {
                        **params,
                        "slide_id": inventory["slide_id"],
                        "object_id": target["object_id"],
                        "expected_fingerprint": target["fingerprint"],
                        **target["data"],
                        "title": "Independent copy",
                    },
                )
                params["expected_revision_id"] = edit["revision_id"]
                titles = [
                    c["data"]["title"]
                    for c in call(
                        core,
                        "presentation.workspace.list_charts",
                        {**scope(params), "slide_number": 1},
                    )["items"]
                ]
                assert titles == ["Imported pilot", "Independent copy"]
                undone = call(
                    core, "presentation.workspace.step_revision", {**params, "direction": "undo"}
                )
                params["expected_revision_id"] = undone["revision_id"]
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


@pytest.mark.parametrize("mutation", ["linked", "extension"])
def test_chart_duplication_rejects_unknown_or_external_dependencies(tmp_path, mutation):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, _ = imported(core, tmp_path, mutation=mutation)
        inventory = call(
            core, "presentation.workspace.list_text_targets", {**scope(params), "slide_number": 1}
        )
        obj = inventory["objects"][0]
        original = path(core, params).read_bytes()
        rejected = call(
            core,
            "presentation.workspace.duplicate_object",
            {
                **params,
                "slide_id": inventory["slide_id"],
                "object_id": obj["object_id"],
                "expected_geometry": obj["geometry"],
            },
            ok=False,
        )
        assert rejected["code"] == "PRESENTATION_EDIT_UNSUPPORTED"
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


def test_chart_dependency_graph_copies_styles_images_and_relationship_targets(tmp_path):
    from lxml import etree

    from presenter_core.presentation.fidelity import _NS, PACKAGE_REL_NS
    from presenter_core.presentation.graphic_duplication import clone_chart_graph

    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, _ = imported(core, tmp_path)
        with zipfile.ZipFile(path(core, params)) as source:
            parts = {n: source.read(n) for n in source.namelist()}
        rels = etree.fromstring(parts["ppt/charts/_rels/chart1.xml.rels"])
        etree.SubElement(
            rels,
            f"{{{PACKAGE_REL_NS}}}Relationship",
            Id="rIdStyle",
            Type="http://schemas.microsoft.com/office/2011/relationships/chartStyle",
            Target="style1.xml",
        )
        parts["ppt/charts/_rels/chart1.xml.rels"] = etree.tostring(rels)
        parts["ppt/charts/style1.xml"] = b"<style/>"
        parts["ppt/media/graph.png"] = b"isolated-image-bytes"
        parts["ppt/charts/_rels/style1.xml.rels"] = (
            f'<Relationships xmlns="{PACKAGE_REL_NS}"><Relationship Id="rIdImage" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            'Target="../media/graph.png"/></Relationships>'
        ).encode()
        ct = etree.fromstring(parts["[Content_Types].xml"])
        ns = "http://schemas.openxmlformats.org/package/2006/content-types"
        etree.SubElement(
            ct,
            f"{{{ns}}}Override",
            PartName="/ppt/charts/style1.xml",
            ContentType="application/vnd.ms-office.chartstyle+xml",
        )
        etree.SubElement(ct, f"{{{ns}}}Default", Extension="png", ContentType="image/png")
        parts["[Content_Types].xml"] = etree.tostring(ct)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as generated:
            for n, payload in parts.items():
                generated.writestr(n, payload)
        with zipfile.ZipFile(buffer) as generated:
            frame = etree.fromstring(parts["ppt/slides/slide1.xml"]).find(".//p:graphicFrame", _NS)
            additions = clone_chart_graph(generated, "ppt/slides/slide1.xml", frame)
        assert (
            next(v for n, v in additions.items() if n.endswith(".png")) == b"isolated-image-bytes"
        )
        styles = [n for n, v in additions.items() if v == b"<style/>"]
        assert len(styles) == 1
        style_rels = etree.fromstring(
            additions["ppt/charts/_rels/" + Path(styles[0]).name + ".rels"]
        )
        assert style_rels[0].get("Target") != "../media/graph.png"
        assert set(additions).intersection(parts) == {
            "[Content_Types].xml",
            "ppt/slides/_rels/slide1.xml.rels",
        }
    finally:
        core.close()
