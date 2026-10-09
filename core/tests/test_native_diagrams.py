from __future__ import annotations

import copy
import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from test_appendix_workflow import slides
from test_presentation_native_layouts import path, scope
from test_presentation_transactions import call, context
from test_selection_actions import save

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.diagrams import inspect_diagram, keys, validate_data
from presenter_core.presentation.fidelity import _NS
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def data(kind="process", count=3):
    return {
        "name": "Pilot workflow",
        "kind": kind,
        "palette": "classic",
        "nodes": [
            {
                "id": f"node{i}",
                "label": f"Step {i + 1}",
                "parent": "node0" if kind == "hierarchy" and i else None,
            }
            for i in range(count)
        ],
    }


def prepare(core, params, slide, value, *, existing=None, geometry=None, late=False):
    operations = [
        {
            "type": "replace_diagram" if existing else "create_diagram",
            "params": {
                "slide_id": slide,
                "data": value,
                "geometry": geometry
                or {"x_emu": 914400, "y_emu": 1800000, "width_emu": 9500000, "height_emu": 4200000},
                **(
                    {
                        "object_id": existing["object_id"],
                        "expected_fingerprint": existing["fingerprint"],
                    }
                    if existing
                    else {}
                ),
            },
        }
    ]
    if late:
        operations.append(
            {
                "type": "delete_object",
                "params": {
                    "slide_id": slide,
                    "object_id": "00000000-0000-0000-0000-000000000000",
                    "expected_geometry": operations[0]["params"]["geometry"],
                },
            }
        )
    return core._presentation_edit_plans.prepare(
        {**params, "summary": "Review structured diagram", "operations": operations}
    )


def catalog(core, params):
    return call(core, "presentation.workspace.list_diagrams", {**scope(params), "slide_number": 1})


@pytest.mark.parametrize(
    "kind,count", [("process", 3), ("process", 8), ("hierarchy", 5), ("cycle", 2), ("cycle", 8)]
)
def test_native_diagram_review_structure_identity_history_and_regeneration(
    tmp_path: Path, kind, count
):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, targets = context(core)
        slide = targets[0]["params"]["slide_id"]
        original = path(core, params).read_bytes()
        before = slides(core, params)
        value = data(kind, count)
        proposed = prepare(core, params, slide, value)
        assert path(core, params).read_bytes() == original
        save(core, params, proposed)
        after = slides(core, params)
        assert after[1:] == before[1:]
        assert after[0].speaker_notes == before[0].speaker_notes
        assert after[0].objects[: len(before[0].objects)] == before[0].objects
        item = catalog(core, params)["items"][0]
        assert item["editable"] and item["data"] == value
        with zipfile.ZipFile(io.BytesIO(path(core, params).read_bytes())) as archive:
            root = etree.fromstring(archive.read("ppt/slides/slide1.xml"))
            group = root.find("p:cSld/p:spTree/p:grpSp", _NS)
            info = inspect_diagram(group)
            assert len(info["_native"]) == len(keys(value))
            connectors = group.findall("p:cxnSp", _NS)
            assert len(connectors) == (count if kind == "cycle" else count - 1)
            assert all(
                c.find("p:nvCxnSpPr/p:cNvCxnSpPr/a:stCxn", _NS) is not None
                and c.find("p:nvCxnSpPr/p:cNvCxnSpPr/a:endCxn", _NS) is not None
                for c in connectors
            )
            native = info["_native"]
        unchanged = prepare(core, params, slide, value, existing=item)
        assert not unchanged["changed"]
        call(
            core,
            "presentation.workspace.reject_edit_plan",
            {
                "project_id": params["project_id"],
                "document_id": params["document_id"],
                "plan_id": unchanged["plan_id"],
            },
        )
        revised = copy.deepcopy(value)
        revised["nodes"][0]["label"] = "Reviewed first step"
        revised["palette"] = "paper"
        edited = prepare(core, params, slide, revised, existing=item)
        save(core, params, edited)
        new_item = catalog(core, params)["items"][0]
        assert new_item["object_id"] == item["object_id"]
        assert new_item["data"] == revised
        with zipfile.ZipFile(path(core, params)) as archive:
            group = etree.fromstring(archive.read("ppt/slides/slide1.xml")).find(
                "p:cSld/p:spTree/p:grpSp", _NS
            )
            assert inspect_diagram(group)["_native"] == native
        final = path(core, params).read_bytes()
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        params["expected_revision_id"] = core._presentation_edits._current_revision_source(
            params["project_id"], params["document_id"]
        )["revision_id"]
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        assert path(core, params).read_bytes() == original
        params["expected_revision_id"] = core._presentation_edits._current_revision_source(
            params["project_id"], params["document_id"]
        )["revision_id"]
        call(core, "presentation.workspace.step_revision", {**params, "direction": "redo"})
        params["expected_revision_id"] = core._presentation_edits._current_revision_source(
            params["project_id"], params["document_id"]
        )["revision_id"]
        call(core, "presentation.workspace.step_revision", {**params, "direction": "redo"})
        assert path(core, params).read_bytes() == final
    finally:
        core.close()


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate",
        "later_parent",
        "cycle_parent",
        "empty",
        "too_many",
        "control",
        "palette",
        "bad_geometry",
        "late",
    ],
)
def test_invalid_diagrams_leave_authority_unchanged(tmp_path: Path, failure):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, targets = context(core)
        original = path(core, params).read_bytes()
        value = data()
        if failure == "duplicate":
            value["nodes"][1]["id"] = "node0"
        if failure == "later_parent":
            value = data("hierarchy")
            value["nodes"][1]["parent"] = "node2"
        if failure == "cycle_parent":
            value["nodes"][1]["parent"] = "node0"
        if failure == "empty":
            value["nodes"][0]["label"] = " "
        if failure == "too_many":
            value = data(count=9)
        if failure == "control":
            value["nodes"][0]["label"] = "bad\x00"
        if failure == "palette":
            value["palette"] = []
        geometry = (
            {"x_emu": 999999999, "y_emu": 0, "width_emu": 999999, "height_emu": 999999}
            if failure == "bad_geometry"
            else None
        )
        with pytest.raises(CoreDomainError):
            prepare(
                core,
                params,
                targets[0]["params"]["slide_id"],
                value,
                geometry=geometry,
                late=failure == "late",
            )
        assert path(core, params).read_bytes() == original
        assert not catalog(core, params)["items"]
    finally:
        core.close()


def test_native_manual_changes_are_not_regenerated():
    from presenter_core.presentation.diagrams import generated
    from presenter_core.presentation.fidelity import FidelityGeometry

    value = validate_data(data())
    native = {key: str(i + 2) for i, key in enumerate(keys(value))}
    group = generated(value, FidelityGeometry(0, 0, 6000000, 3000000), native)
    assert inspect_diagram(group)["editable"]
    group.find("p:sp/p:txBody/a:p/a:r/a:t", _NS).text = "Manual PowerPoint change"
    assert not inspect_diagram(group)["editable"]


def test_structure_changes_keep_retained_identities_and_reject_stale_fingerprint(tmp_path: Path):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, targets = context(core)
        slide = targets[0]["params"]["slide_id"]
        value = data("hierarchy", 4)
        save(core, params, prepare(core, params, slide, value))
        item = catalog(core, params)["items"][0]
        with zipfile.ZipFile(path(core, params)) as archive:
            group = etree.fromstring(archive.read("ppt/slides/slide1.xml")).find(
                "p:cSld/p:spTree/p:grpSp", _NS
            )
            old_ids = inspect_diagram(group)["_native"]
        value["nodes"] = [
            value["nodes"][0],
            value["nodes"][2],
            {"id": "new", "label": "A new team", "parent": "node2"},
        ]
        save(core, params, prepare(core, params, slide, value, existing=item))
        with zipfile.ZipFile(path(core, params)) as archive:
            group = etree.fromstring(archive.read("ppt/slides/slide1.xml")).find(
                "p:cSld/p:spTree/p:grpSp", _NS
            )
            new_ids = inspect_diagram(group)["_native"]
        for key in set(old_ids) & set(new_ids):
            assert old_ids[key] == new_ids[key]
        assert len(set(new_ids.values())) == len(new_ids)
        before = path(core, params).read_bytes()
        with pytest.raises(CoreDomainError) as error:
            prepare(core, params, slide, data(), existing=item)
        assert error.value.code == "PRESENTATION_EDIT_STALE_TARGET"
        assert path(core, params).read_bytes() == before
    finally:
        core.close()


def test_external_dependencies_block_regeneration():
    from presenter_core.presentation.diagrams import external_dependencies, generated
    from presenter_core.presentation.fidelity import PRESENTATION_NS, FidelityGeometry

    group = generated(
        data(),
        FidelityGeometry(0, 0, 6000000, 3000000),
        {key: str(i + 2) for i, key in enumerate(keys(data()))},
    )
    root = etree.Element(f"{{{PRESENTATION_NS}}}sld", nsmap={"p": PRESENTATION_NS})
    common = etree.SubElement(root, f"{{{PRESENTATION_NS}}}cSld")
    tree = etree.SubElement(common, f"{{{PRESENTATION_NS}}}spTree")
    tree.append(group)
    assert not external_dependencies(root, group)
    timing = etree.SubElement(root, f"{{{PRESENTATION_NS}}}timing")
    etree.SubElement(timing, f"{{{PRESENTATION_NS}}}spTgt", spid="3")
    assert external_dependencies(root, group)


@pytest.mark.parametrize("late", [False, True])
def test_reviewed_diagram_deletion_is_atomic_and_undoable(tmp_path: Path, late):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, targets = context(core)
        slide = targets[0]["params"]["slide_id"]
        original = path(core, params).read_bytes()
        save(core, params, prepare(core, params, slide, data()))
        inserted = path(core, params).read_bytes()
        item = catalog(core, params)["items"][0]
        operations = [
            {
                "type": "delete_diagram",
                "params": {
                    "slide_id": slide,
                    "object_id": item["object_id"],
                    "expected_fingerprint": item["fingerprint"],
                },
            }
        ]
        if late:
            operations.append(
                {
                    "type": "delete_slide",
                    "params": {"slide_id": "00000000-0000-0000-0000-000000000000"},
                }
            )
        request = {**params, "summary": "Review whole diagram removal", "operations": operations}
        if late:
            with pytest.raises(CoreDomainError):
                core._presentation_edit_plans.prepare(request)
            assert path(core, params).read_bytes() == inserted
        else:
            proposed = core._presentation_edit_plans.prepare(request)
            assert path(core, params).read_bytes() == inserted
            save(core, params, proposed)
            assert not catalog(core, params)["items"]
            with (
                zipfile.ZipFile(io.BytesIO(original)) as before,
                zipfile.ZipFile(path(core, params)) as after,
            ):
                assert before.namelist() == after.namelist()
                assert all(
                    before.read(name) == after.read(name)
                    for name in before.namelist()
                    if name != "ppt/slides/slide1.xml"
                )
                assert etree.tostring(
                    etree.fromstring(before.read("ppt/slides/slide1.xml")), method="c14n"
                ) == etree.tostring(
                    etree.fromstring(after.read("ppt/slides/slide1.xml")), method="c14n"
                )
            call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
            assert path(core, params).read_bytes() == inserted
    finally:
        core.close()
