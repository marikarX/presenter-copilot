from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from test_appendix_workflow import slides
from test_object_groups import mixed_fixture
from test_object_paste import inventory
from test_presentation_native_layouts import path
from test_presentation_transactions import call
from test_selection_actions import save

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def operations(slide, count, color):
    return [
        {
            "type": "create_text_box",
            "params": {
                "slide_id": slide,
                "text": f"[{index + 1}] Architecture notes.md · unit {index + 1} · context",
                "geometry": {
                    "x_emu": 228600,
                    "y_emu": 4500000 + index * 274320,
                    "width_emu": 8000000,
                    "height_emu": 274320,
                },
                "text_style": {"font_size_pt": 10, "font_color": "#" + color, "alignment": "left"},
            },
        }
        for index in range(count)
    ]


@pytest.mark.parametrize("count", [1, 4])
@pytest.mark.parametrize("color", ["333333", "FFFFFF"])
def test_footnotes_native_style_parts_and_atomic_history(tmp_path: Path, count, color):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, _ = mixed_fixture(core, tmp_path)
        before = path(core, params).read_bytes()
        original = inventory(core, params, 1)
        ops = operations(original["slide_id"], count, color)
        plan = core._presentation_edit_plans.prepare(
            {
                **params,
                "summary": "Reviewed evidence footnotes",
                "operations": ops,
            },
        )
        assert path(core, params).read_bytes() == before
        applied = save(core, params, plan)
        after = path(core, params).read_bytes()
        current = inventory(core, params, 1)
        assert len(current["objects"]) == len(original["objects"]) + count
        assert current["objects"][:-count] == original["objects"]
        for index, obj in enumerate(current["objects"][-count:]):
            native = slides(core, params)[0].objects[-count + index]
            assert native.text == ops[index]["params"]["text"]
            assert obj["geometry"] == ops[index]["params"]["geometry"]
            assert native.text_style.font_size_pt == 10
            assert native.text_style.font_color == "#" + color
            assert native.text_style.alignment == "left"
            assert obj["geometry_editable"] and obj["delete_editable"]
        with (
            zipfile.ZipFile(io.BytesIO(before)) as left,
            zipfile.ZipFile(io.BytesIO(after)) as right,
        ):
            assert left.namelist() == right.namelist()
            changed = [name for name in left.namelist() if left.read(name) != right.read(name)]
            assert changed == ["ppt/slides/slide1.xml"]
        assert applied["sha256"] == plan["sha256"]
        call(
            core,
            "presentation.workspace.step_revision",
            {**params, "direction": "undo"},
        )
        assert path(core, params).read_bytes() == before
        params["expected_revision_id"] = core._presentation_edits._current_revision_source(
            params["project_id"], params["document_id"]
        )["revision_id"]
        call(
            core,
            "presentation.workspace.step_revision",
            {**params, "direction": "redo"},
        )
        assert path(core, params).read_bytes() == after
    finally:
        core.close()


@pytest.mark.parametrize("bad", ["bounds", "size", "color", "style", "late", "empty"])
def test_footnote_creation_rejects_invalid_inputs_without_partial_revision(tmp_path: Path, bad):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, _ = mixed_fixture(core, tmp_path)
        before = path(core, params).read_bytes()
        ops = operations(inventory(core, params, 1)["slide_id"], 2, "333333")
        target = ops[-1]["params"]
        if bad == "bounds":
            target["geometry"]["x_emu"] = 9000000
        if bad == "size":
            target["text_style"]["font_size_pt"] = 5
        if bad == "color":
            target["text_style"]["font_color"] = "invalid"
        if bad == "style":
            target["text_style"]["bullet_mode"] = "bullet"
        if bad == "late":
            target["slide_id"] = {"created_by": 1}
        if bad == "empty":
            target["text"] = " "
        with pytest.raises(CoreDomainError):
            core._presentation_edit_plans.prepare(
                {
                    **params,
                    "summary": "Invalid footnote",
                    "operations": ops,
                },
            )
        assert path(core, params).read_bytes() == before
        assert (
            core._presentation_edits._current_revision_source(
                params["project_id"], params["document_id"]
            )["revision_id"]
            == params["expected_revision_id"]
        )
    finally:
        core.close()
