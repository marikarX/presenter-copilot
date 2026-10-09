"""Legend-only edits preserve chart data, shared parts and exact reviewed revisions."""

from __future__ import annotations

import copy
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from test_copilot_data import DataProvider
from test_copilot_diagrams import operations
from test_presentation_chart_editing import imported
from test_presentation_edit_planning import call
from test_presentation_native_layouts import path, scope
from test_selection_actions import save

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.chart_legend import apply_legend, inspect_legend
from presenter_core.presentation.charts import CNS, NS
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def core_at(tmp, provider=None):
    return CoreService(
        data_root=tmp / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )


def prepare(core, params, catalog, position="bottom", overlay=False, fingerprint=None):
    item = catalog["items"][0]
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": "Review chart legend",
            "operations": [
                {
                    "type": "set_chart_legend",
                    "params": {
                        "slide_id": catalog["slide_id"],
                        "object_id": item["object_id"],
                        "expected_fingerprint": fingerprint or item["fingerprint"],
                        "legend_position": position,
                        "legend_overlay": overlay,
                    },
                }
            ],
        },
    )


@pytest.mark.parametrize("kind", ["column", "bar", "line", "pie"])
@pytest.mark.parametrize("position,overlay", [("bottom", False), ("right", True)])
def test_native_legend_save_preserves_shared_parts_and_undo(
    tmp_path: Path, kind, position, overlay
):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path, kind, shared=True)
        before = path(core, params).read_bytes()
        with zipfile.ZipFile(path(core, params)) as archive:
            originals = {v.filename: archive.read(v) for v in archive.infolist()}
        assert catalog["items"][0]["legend"]["editable"]
        proposal = prepare(core, params, catalog, position, overlay)
        assert path(core, params).read_bytes() == before
        save(core, params, proposal)
        after = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1}
        )
        unchanged = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 2}
        )
        assert after["items"][0]["legend"] == {
            "editable": True,
            "reason": None,
            "position": position,
            "overlay": overlay,
        }
        assert unchanged["items"][0]["legend"] == catalog["items"][0]["legend"]
        assert after["items"][0]["object_id"] == catalog["items"][0]["object_id"]
        assert after["items"][0]["data"] == catalog["items"][0]["data"]
        with zipfile.ZipFile(path(core, params)) as archive:
            changes = {name for name, payload in originals.items() if archive.read(name) != payload}
            assert changes == {
                "[Content_Types].xml",
                "ppt/slides/slide1.xml",
                "ppt/slides/_rels/slide1.xml.rels",
            }
            assert len(set(archive.namelist()) - originals.keys()) == 2
        # Repeat semantic settings are a no-op; hiding is explicitly reviewed.
        noop = prepare(core, params, after, position, overlay)
        assert not noop["changed"]
        call(
            core,
            "presentation.workspace.reject_edit_plan",
            {
                "project_id": params["project_id"],
                "document_id": params["document_id"],
                "plan_id": noop["plan_id"],
            },
        )
        visible = path(core, params).read_bytes()
        save(core, params, prepare(core, params, after, "hidden", False))
        assert (
            call(core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1})[
                "items"
            ][0]["legend"]["position"]
            == "hidden"
        )
        for expected in [visible, before]:
            result = call(
                core, "presentation.workspace.step_revision", {**params, "direction": "undo"}
            )
            params["expected_revision_id"] = result["revision_id"]
            assert path(core, params).read_bytes() == expected
    finally:
        core.close()


def legend_xml():
    root = etree.fromstring(
        f'<c:chartSpace xmlns:c="{CNS}"><c:chart><c:plotArea/></c:chart></c:chartSpace>'
    )
    apply_legend(root, "right", False)
    return root


def test_existing_legend_style_and_entries_survive_move_and_overlay():
    root = legend_xml()
    legend = root.find("c:chart/c:legend", NS)
    entry = etree.SubElement(legend, f"{{{CNS}}}legendEntry")
    etree.SubElement(entry, f"{{{CNS}}}idx", val="1")
    etree.SubElement(entry, f"{{{CNS}}}delete", val="1")
    style = etree.SubElement(legend, f"{{{CNS}}}spPr")
    etree.SubElement(style, "color", val="purple")
    original = [etree.tostring(entry), etree.tostring(style)]
    assert apply_legend(root, "top_right", True)
    assert [etree.tostring(entry), etree.tostring(style)] == original
    assert inspect_legend(root)["position"] == "top_right"
    assert inspect_legend(root)["overlay"]


@pytest.mark.parametrize(
    "mutation",
    ["manual", "extension", "duplicate", "bad_position", "bad_overlay", "nested", "attribute"],
)
def test_unsupported_legend_settings_are_read_only(mutation):
    root = legend_xml()
    legend = root.find("c:chart/c:legend", NS)
    if mutation == "manual":
        etree.SubElement(etree.SubElement(legend, f"{{{CNS}}}layout"), f"{{{CNS}}}manualLayout")
    if mutation == "extension":
        etree.SubElement(legend, f"{{{CNS}}}extLst")
    if mutation == "duplicate":
        legend.append(copy.deepcopy(legend.find("c:legendPos", NS)))
    if mutation == "bad_position":
        legend.find("c:legendPos", NS).set("val", "unsupported")
    if mutation == "bad_overlay":
        legend.find("c:overlay", NS).set("val", "maybe")
    if mutation == "nested":
        etree.SubElement(legend.find("c:legendPos", NS), "unexpected")
    if mutation == "attribute":
        legend.set("unexpected", "1")
    original = etree.tostring(root)
    assert not inspect_legend(root)["editable"]
    with pytest.raises(CoreDomainError):
        apply_legend(root, "bottom", False)
    assert etree.tostring(root) == original


def test_stale_or_invalid_legend_draft_keeps_current_package(tmp_path: Path):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path)
        before = path(core, params).read_bytes()
        for position, overlay, fingerprint in [
            ("unknown", False, None),
            ("bottom", 1, None),
            ("hidden", True, None),
            ("bottom", False, "0" * 64),
        ]:
            with pytest.raises(CoreDomainError):
                prepare(core, params, catalog, position, overlay, fingerprint)
            assert path(core, params).read_bytes() == before
    finally:
        core.close()


def test_copilot_binds_staged_fingerprints_and_reviews_previous_legend(tmp_path: Path):
    provider = DataProvider(locality="local")
    core = core_at(tmp_path, provider)
    try:
        params, catalog = imported(core, tmp_path, shared=True)
        observed = []

        def build(snapshot):
            slide = snapshot["slides"][0]
            item = slide["charts"][0]
            observed.append(item)
            return {
                "summary": "Review legend placement",
                "operations": operations(
                    [
                        (
                            "set_chart_legend",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": item["object_id"],
                                "legend_position": position,
                                "legend_overlay": overlay,
                            },
                        )
                        for position, overlay in [("bottom", False), ("right", True)]
                    ]
                ),
            }

        provider.builder = build
        proposal = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {**params, "instruction": "Show then move the legend.", "slide_numbers": [1]},
        )
        assert observed[0]["legend"]["position"] == "hidden"
        assert "fingerprint" not in observed[0]
        assert [v["previous_data"] for v in proposal["review_operations"]] == [
            {"legend_position": "hidden", "legend_overlay": False},
            {"legend_position": "bottom", "legend_overlay": False},
        ]
        assert (
            proposal["review_operations"][0]["params"]["expected_fingerprint"]
            != proposal["review_operations"][1]["params"]["expected_fingerprint"]
        )
        save(core, params, proposal)
        assert (
            call(core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1})[
                "items"
            ][0]["legend"]["position"]
            == "right"
        )
    finally:
        core.close()
