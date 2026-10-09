from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from test_native_diagrams import catalog, data, prepare
from test_presentation_edit_planning import PlanProvider, call, context
from test_presentation_native_layouts import path
from test_selection_actions import save

from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def edit_scope(params):
    return {k: params[k] for k in ("project_id", "document_id", "expected_revision_id")}


def operations(entries):
    return [
        {
            "type": kind,
            "params": params,
            "rationale": "Review native diagram structure and placement",
            "evidence_ids": [],
        }
        for kind, params in entries
    ]


@pytest.mark.parametrize(
    "mode", ["replace", "delete", "forward", "unselected", "evidence", "private_fp", "bad_parent"]
)
def test_provider_diagrams_bind_staged_targets_and_preconditions(tmp_path: Path, mode):
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        params = context(core)
        baseline = path(core, edit_scope(params)).read_bytes()
        value = data()
        revised = data("cycle")
        revised["nodes"][0]["label"] = "Reviewed pilot"
        geometry = {"x_emu": 914400, "y_emu": 1800000, "width_emu": 9500000, "height_emu": 4200000}

        def modify(output, invocation):
            snapshot = json.loads(invocation.request.current_slide_summary)[
                "presentation_edit_snapshot"
            ]
            slide = snapshot["slides"][0]["slide_id"]
            entries = [
                ("create_slide", {"slide_id": slide, "layout_source_slide_id": slide}),
                (
                    "create_diagram",
                    {"slide_id": {"created_by": 1}, "data": value, "geometry": geometry},
                ),
                (
                    "replace_diagram",
                    {
                        "slide_id": {"created_by": 1},
                        "object_id": {"created_by": 2},
                        "data": revised,
                        "geometry": geometry,
                    },
                ),
            ]
            if mode == "delete":
                entries.append(
                    (
                        "delete_diagram",
                        {"slide_id": {"created_by": 1}, "object_id": {"created_by": 2}},
                    )
                )
            if mode == "forward":
                entries[2][1]["object_id"] = {"created_by": 9}
            if mode == "unselected":
                entries[1][1]["slide_id"] = snapshot["ordered_slide_ids"][1]
            if mode == "private_fp":
                entries[2][1]["expected_fingerprint"] = "0" * 64
            if mode == "bad_parent":
                entries[1][1]["data"]["nodes"][1]["parent"] = "node0"
            output["operations"] = operations(entries)
            if mode == "evidence":
                output["operations"][1]["evidence_ids"] = ["invented-evidence"]

        provider.modifier = modify
        valid = mode in {"replace", "delete"}
        proposal = call(core, "presentation.workspace.propose_edit_plan", params, ok=valid)
        assert path(core, edit_scope(params)).read_bytes() == baseline
        if not valid:
            assert not core._presentation_edit_plans._plans
            assert not list(
                core._storage.paths.safe_sources_directory(params["project_id"]).glob(
                    ".edit-*.pptx"
                )
            )
            return
        assert len(proposal["operations"][2]["params"]["expected_fingerprint"]) == 64
        assert isinstance(proposal["operations"][2]["params"]["object_id"], str)
        if mode == "delete":
            assert (
                proposal["operations"][3]["params"]["expected_fingerprint"]
                != proposal["operations"][2]["params"]["expected_fingerprint"]
            )
        scope = edit_scope(params)
        saved = save(core, scope, proposal)
        assert saved["revision_number"] == 2
        diagrams = call(
            core,
            "presentation.workspace.list_diagrams",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "revision_id": scope["expected_revision_id"],
                "slide_number": 2,
            },
        )["items"]
        if mode == "delete":
            assert not diagrams
        else:
            assert (
                diagrams[0]["data"] == revised
                and diagrams[0]["object_id"] == proposal["operations"][2]["params"]["object_id"]
            )
        call(core, "presentation.workspace.step_revision", {**scope, "direction": "undo"})
        assert path(core, edit_scope(params)).read_bytes() == baseline
    finally:
        core.close()


def test_existing_diagram_context_is_selected_bounded_and_fingerprint_is_core_owned(tmp_path: Path):
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        params = context(core)
        scope = edit_scope(params)
        native = core._presentation_edit_planning._read(
            core._presentation_edits,
            scope["project_id"],
            scope["document_id"],
            scope["expected_revision_id"],
        )
        save(core, scope, prepare(core, scope, native.slides[0].slide_id, data("hierarchy")))
        params["expected_revision_id"] = scope["expected_revision_id"]
        item = catalog(core, scope)["items"][0]
        baseline = path(core, scope).read_bytes()

        def modify(output, invocation):
            snapshot = json.loads(invocation.request.current_slide_summary)[
                "presentation_edit_snapshot"
            ]
            supplied = snapshot["slides"][0]["diagrams"][0]
            assert supplied["editable"] and supplied["data"] == item["data"]
            assert "fingerprint" not in supplied and "_native" not in supplied
            revised = copy.deepcopy(supplied["data"])
            revised["nodes"][1]["label"] = "Delivery team"
            output["operations"] = operations(
                [
                    (
                        "replace_diagram",
                        {
                            "slide_id": snapshot["slides"][0]["slide_id"],
                            "object_id": supplied["object_id"],
                            "data": revised,
                            "geometry": supplied["geometry"],
                        },
                    )
                ]
            )

        provider.modifier = modify
        proposal = call(core, "presentation.workspace.propose_edit_plan", params)
        assert proposal["operations"][0]["params"]["expected_fingerprint"] == item["fingerprint"]
        assert path(core, scope).read_bytes() == baseline
        save(core, scope, proposal)
        updated = catalog(core, scope)["items"][0]
        assert (
            updated["object_id"] == item["object_id"]
            and updated["data"]["nodes"][1]["label"] == "Delivery team"
        )
    finally:
        core.close()
