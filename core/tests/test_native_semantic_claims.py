"""Actual graphic sources retain exact quotes and trusted representation provenance."""

import json
from pathlib import Path

import pytest
from test_native_semantic_inventory import fixture
from test_presentation_edit_planning import PlanProvider, call

from presenter_core.ipc.core import CoreService
from presenter_core.presentation.claim_extraction import claim_context_size, claim_request
from presenter_core.presentation.claims import PresentationClaimService
from presenter_core.providers.context import MAX_TOTAL_CONTEXT_CHARS
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def setup(tmp_path: Path, decision_provider=None):
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        decision_provider=decision_provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    project = call(core, "project.create", {"name": "Native representations"})["project"]["id"]
    document = call(
        core,
        "source.import",
        {
            "project_id": project,
            "kind": "presentation",
            "path": str(fixture(tmp_path / "native.pptx")),
        },
    )["document"]["id"]
    opened = call(
        core, "presentation.workspace.open_source", {"project_id": project, "document_id": document}
    )
    call(
        core,
        "presentation.workspace.close_source",
        {"project_id": project, "document_id": document, "session_id": opened["session_id"]},
    )
    scope = {
        "project_id": project,
        "document_id": document,
        "revision_id": opened["revision_id"],
        "slide_number": 1,
    }
    inventory = call(core, "presentation.workspace.list_text_targets", scope)
    scope["slide_id"] = inventory["slide_id"]
    return core, provider, scope, inventory


@pytest.mark.parametrize("kind", ["native_chart_cache", "native_table_cells"])
def test_graphic_extraction_review_save_and_provider_context(tmp_path: Path, kind: str):
    core, provider, scope, inventory = setup(tmp_path)
    try:
        target = next(t for t in inventory["semantic_targets"] if t["source_kind"] == kind)
        quote = target["decision_text"].splitlines()[-1]

        def choose_data(output, _invocation):
            output["candidates"][0]["quote"] = quote

        provider.modifier = choose_data
        result = call(
            core,
            "presentation.workspace.extract_claims",
            {**scope, "object_ids": [target["object_id"]]},
        )
        candidate = result["candidates"][0]
        assert candidate["source_kind"] == kind
        assert candidate["quote"] == quote
        packet = json.loads(provider.request_objects[-1].current_slide_summary)
        assert packet["objects"] == [
            {"object_id": target["object_id"], "text": target["decision_text"], "source_kind": kind}
        ]
        assert "not displayed/formatted values" in provider.request_objects[-1].task_instruction
        assert not call(core, "presentation.workspace.list_claims", scope)["items"]
        payload = {
            **scope,
            "object_id": target["object_id"],
            "quote": candidate["quote"],
            "confirm": True,
            "evidence": [],
        }
        assert (
            call(
                core,
                "presentation.workspace.save_claim",
                {**payload, "source_kind": "native_text"},
                ok=False,
            )["code"]
            == "INVALID_REQUEST"
        )
        call(core, "presentation.workspace.save_claim", {**payload, "confirm": False}, ok=False)
        call(core, "presentation.workspace.save_claim", payload)
        claim = call(core, "presentation.workspace.list_claims", scope)["items"][0]
        assert claim["source_kind"] == kind and claim["coverage"] == "unlinked"
        context, evidence = PresentationClaimService(core._presentation_semantics).provider_context(
            scope["project_id"], scope["revision_id"], [1]
        )
        assert context["claims"][0]["source_kind"] == kind
        assert context["claims"][0]["reviewed_for_revision"] and not evidence
        assert len(inventory["targets"]) == 1
        if kind == "native_chart_cache":
            assert "Q1: 0.2" in candidate["quote"] and "20%" not in candidate["quote"]
    finally:
        core.close()


def test_graphic_scan_budget_and_source_kind_binding(tmp_path: Path):
    core, provider, scope, inventory = setup(tmp_path)
    try:
        base = {k: scope[k] for k in ("project_id", "document_id", "revision_id")}
        plan = call(core, "presentation.workspace.prepare_claim_scan", base)
        slide = plan["items"][0]
        assert slide["eligible_objects"] == 3 and slide["excluded_objects"] == 0
        assert plan["coverage_scope"] == "available_native_representations_only"
        targets = {t["object_id"]: t for t in inventory["semantic_targets"]}
        for batch in slide["batches"]:
            assert batch["source_kinds"] == {
                key: targets[key]["source_kind"] for key in batch["object_ids"]
            }
            texts = {
                s["object_id"]: targets[s["object_id"]]["decision_text"][s["start"] : s["end"]]
                for s in batch["spans"]
            }
            request = claim_request(
                texts,
                "selected_context_cloud",
                scope["document_id"],
                scope["revision_id"],
                batch["source_kinds"],
            )
            assert claim_context_size(request) <= MAX_TOTAL_CONTEXT_CHARS - 100
        assert not provider.requests
    finally:
        core.close()


def test_chart_format_revision_requires_review_then_data_revision_changes_span(tmp_path: Path):
    from test_chart_colors import prepare_color
    from test_presentation_chart_editing import draft
    from test_selection_actions import save

    core, _, scope, inventory = setup(tmp_path)
    try:
        target = next(
            t for t in inventory["semantic_targets"] if t["source_kind"] == "native_chart_cache"
        )
        payload = {**scope, "object_id": target["object_id"], "quote": "Q1: 0.2", "confirm": True}
        saved = call(core, "presentation.workspace.save_claim", payload)
        params = {
            "project_id": scope["project_id"],
            "document_id": scope["document_id"],
            "expected_revision_id": scope["revision_id"],
        }
        catalog = call(
            core,
            "presentation.workspace.list_charts",
            {k: v for k, v in scope.items() if k != "slide_id"},
        )
        save(core, params, prepare_color(core, params, catalog))
        scope["revision_id"] = params["expected_revision_id"]
        item = call(core, "presentation.workspace.list_claims", scope)["items"][0]
        assert item["span_status"] == "unchanged" and item["coverage"] == "needs_review"
        service = PresentationClaimService(core._presentation_semantics)
        context, _ = service.provider_context(scope["project_id"], scope["revision_id"], [1])
        assert context["claims"][0]["reviewed_for_revision"] is False
        call(
            core,
            "presentation.workspace.save_claim",
            {**payload, **scope, "claim_id": saved["claim_id"]},
        )
        assert (
            call(core, "presentation.workspace.list_claims", scope)["items"][0]["coverage"]
            == "unlinked"
        )
        catalog = call(
            core,
            "presentation.workspace.list_charts",
            {k: v for k, v in scope.items() if k != "slide_id"},
        )
        changed = draft(params, catalog)
        changed["series"][0]["values"][0] = 0.3
        plan = call(
            core,
            "presentation.workspace.prepare_edit_plan",
            {
                **params,
                "summary": "Review chart data",
                "operations": [
                    {
                        "type": "replace_chart_data",
                        "params": {k: v for k, v in changed.items() if k not in params},
                    }
                ],
            },
        )
        save(core, params, plan)
        scope["revision_id"] = params["expected_revision_id"]
        item = call(core, "presentation.workspace.list_claims", scope)["items"][0]
        assert item["span_status"] == "changed" and item["coverage"] == "needs_review"
        assert item["source_kind"] == "native_chart_cache"
        call(
            core,
            "presentation.workspace.save_claim",
            {**payload, **scope, "claim_id": saved["claim_id"]},
            ok=False,
        )
        call(
            core,
            "presentation.workspace.save_claim",
            {**payload, **scope, "quote": "Q1: 0.3", "claim_id": saved["claim_id"]},
        )
        assert (
            call(core, "presentation.workspace.list_claims", scope)["items"][0]["span_status"]
            == "unchanged"
        )
        historical = service.revision_claims({**scope, "revision_id": payload["revision_id"]})
        assert historical["items"][0]["quote"] == "Q1: 0.2"
        assert historical["items"][0]["source_kind"] == "native_chart_cache"
    finally:
        core.close()


@pytest.mark.parametrize("kind", ["native_chart_cache", "native_table_cells"])
def test_graphic_fast_decision_triage_receives_native_basis_without_saving(
    tmp_path: Path, kind: str
):
    from test_claim_triage import Provider

    provider = Provider("unclear", 0.99)
    core, _, scope, inventory = setup(tmp_path, provider)
    try:
        source = tmp_path / "Evidence.txt"
        source.write_text("Pilot rate was twenty percent in Q1.")
        call(
            core,
            "source.import",
            {"project_id": scope["project_id"], "kind": "supporting", "path": str(source)},
        )
        evidence = call(
            core,
            "presentation.workspace.search_claim_evidence",
            {"project_id": scope["project_id"], "query": "pilot"},
        )["items"][0]
        target = next(t for t in inventory["semantic_targets"] if t["source_kind"] == kind)
        result = call(
            core,
            "presentation.workspace.triage_claim_evidence",
            {
                **scope,
                "object_id": target["object_id"],
                "quote": target["decision_text"].splitlines()[-1],
                "chunk_id": evidence["chunk_id"],
                "expected_sha256": evidence["sha256"],
            },
        )
        assert result["source_kind"] == kind and result["abstained"]
        state = json.loads(provider.requests[0].serialized_state())
        assert state["claim_source_kind"] == kind
        assert "percentage scaling" in provider.requests[0].questions[0].instructions
        assert not call(core, "presentation.workspace.list_claims", scope)["items"]
        with core._storage.project_database(scope["project_id"]) as connection:
            manifest = json.loads(
                connection.execute(
                    "SELECT context_manifest_json FROM provider_runs WHERE id=?",
                    (result["provider_run_id"],),
                ).fetchone()[0]
            )
        assert manifest["claim_source_kind"] == kind
        assert target["decision_text"] not in json.dumps(manifest)
    finally:
        core.close()


def test_historical_text_records_default_kind_and_wrong_graphic_kind_needs_review(tmp_path: Path):
    core, _, scope, inventory = setup(tmp_path)
    try:
        for kind in ("native_text", "native_chart_cache"):
            target = next(t for t in inventory["semantic_targets"] if t["source_kind"] == kind)
            saved = call(
                core,
                "presentation.workspace.save_claim",
                {
                    **scope,
                    "object_id": target["object_id"],
                    "quote": target["decision_text"],
                    "confirm": True,
                },
            )
            with core._storage.project_database(scope["project_id"]) as connection:
                row = connection.execute(
                    "SELECT record_json FROM presentation_claims WHERE claim_id=?",
                    (saved["claim_id"],),
                ).fetchone()
                record = json.loads(row[0])
                record.pop("source_kind")
                connection.execute(
                    "UPDATE presentation_claims SET record_json=? WHERE claim_id=?",
                    (json.dumps(record), saved["claim_id"]),
                )
                connection.commit()
            item = next(
                c
                for c in call(core, "presentation.workspace.list_claims", scope)["items"]
                if c["claim_id"] == saved["claim_id"]
            )
            assert item["source_kind"] == "native_text"
            assert item["span_status"] == ("unchanged" if kind == "native_text" else "changed")
            assert item["coverage"] == ("unlinked" if kind == "native_text" else "needs_review")
    finally:
        core.close()
