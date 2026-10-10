from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_claim_provider_context import proposal
from test_claim_provider_context import save as save_claim
from test_m5_challenge import configure, create_profile, start_challenge
from test_presentation_claims import setup
from test_presentation_edit_planning import PlanProvider, call

from presenter_core.ipc.core import CoreService
from presenter_core.presentation.narrative import FIELD_LIMITS
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def scope_only(scope):
    return {key: scope[key] for key in ("project_id", "document_id", "revision_id")}


def save(core, scope, text="Approve a limited pilot", expected=None):
    fields = dict.fromkeys(FIELD_LIMITS, "")
    fields.update(
        objective=text, target_audience="Steering committee", desired_action="Fund the pilot"
    )
    return call(
        core,
        "presentation.workspace.save_narrative",
        {
            **scope_only(scope),
            "fields": fields,
            "reviewed": True,
            "expected_record_token": expected,
        },
    )


def change(core, scope, target):
    return call(
        core,
        "presentation.workspace.replace_text_shape",
        {
            **{key: scope[key] for key in ("project_id", "document_id", "slide_id")},
            "expected_revision_id": scope["revision_id"],
            "object_id": target["object_id"],
            "expected_text": target["current_text"],
            "replacement_text": "Revised pilot decision",
            "operation_type": "replace_text_shape",
        },
    )


def test_narrative_persistence_inheritance_clear_conflicts_and_undo(tmp_path: Path):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, target, _ = setup(core, tmp_path)
        baseline = scope["revision_id"]
        assert (
            call(core, "presentation.workspace.get_narrative", scope_only(scope))["status"]
            == "missing"
        )
        saved = save(core, scope)
        assert saved["status"] == "reviewed" and saved["source_revision_id"] == baseline
        with core._storage.project_database(scope["project_id"]) as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM presentation_revisions").fetchone()[0] == 1
            )
        core.close()
        core = CoreService(
            data_root=tmp_path / "data",
            embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        )
        assert call(core, "presentation.workspace.get_narrative", scope_only(scope)) == saved
        error = call(
            core,
            "presentation.workspace.save_narrative",
            {
                **scope_only(scope),
                "fields": saved["fields"],
                "reviewed": True,
                "expected_record_token": None,
            },
            ok=False,
        )
        assert error["code"] == "PRESENTATION_NARRATIVE_CONFLICT"
        changed = change(core, scope, target)
        call(core, "presentation.workspace.get_narrative", scope_only(scope), ok=False)
        call(
            core,
            "presentation.workspace.save_narrative",
            {
                **scope_only(scope),
                "fields": saved["fields"],
                "reviewed": True,
                "expected_record_token": saved["record_token"],
            },
            ok=False,
        )
        scope["revision_id"] = changed["revision_id"]
        inherited = call(core, "presentation.workspace.get_narrative", scope_only(scope))
        assert inherited["status"] == "needs_review" and inherited["fields"] == saved["fields"]
        assert inherited["source_revision_id"] == baseline
        clear = call(
            core,
            "presentation.workspace.save_narrative",
            {
                **scope_only(scope),
                "fields": dict.fromkeys(FIELD_LIMITS, ""),
                "reviewed": True,
                "expected_record_token": inherited["record_token"],
            },
        )
        assert clear["status"] == "reviewed" and not any(clear["fields"].values())
        current_target = {**target, "current_text": "Revised pilot decision"}
        next_revision = call(
            core,
            "presentation.workspace.replace_text_shape",
            {
                **{key: scope[key] for key in ("project_id", "document_id", "slide_id")},
                "expected_revision_id": scope["revision_id"],
                "object_id": target["object_id"],
                "expected_text": current_target["current_text"],
                "replacement_text": "Another decision",
                "operation_type": "replace_text_shape",
            },
        )
        scope["revision_id"] = next_revision["revision_id"]
        assert not any(
            call(core, "presentation.workspace.get_narrative", scope_only(scope))["fields"].values()
        )
        restored = call(
            core,
            "presentation.workspace.step_revision",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "expected_revision_id": scope["revision_id"],
                "direction": "undo",
            },
        )
        restored = call(
            core,
            "presentation.workspace.step_revision",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "expected_revision_id": restored["revision_id"],
                "direction": "undo",
            },
        )
        scope["revision_id"] = restored["revision_id"]
        assert call(core, "presentation.workspace.get_narrative", scope_only(scope)) == saved
        branch = change(core, scope, target)
        scope["revision_id"] = branch["revision_id"]
        branched = call(core, "presentation.workspace.get_narrative", scope_only(scope))
        assert branched["status"] == "needs_review" and branched["fields"] == saved["fields"]
        assert branched["source_revision_id"] == baseline
    finally:
        core.close()


@pytest.mark.parametrize(
    "failure", ["fields", "unknown", "oversize", "nul", "unreviewed", "token", "foreign"]
)
def test_invalid_narrative_never_writes(tmp_path: Path, failure):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, _, _ = setup(core, tmp_path)
        fields = dict.fromkeys(FIELD_LIMITS, "")
        payload = {
            **scope_only(scope),
            "fields": fields,
            "reviewed": True,
            "expected_record_token": None,
        }
        if failure == "fields":
            del fields["objective"]
        if failure == "unknown":
            fields["command"] = "ignored?"
        if failure == "oversize":
            fields["objective"] = "x" * 1001
        if failure == "nul":
            fields["objective"] = "bad\x00text"
        if failure == "unreviewed":
            payload["reviewed"] = False
        if failure == "token":
            del payload["expected_record_token"]
        if failure == "foreign":
            payload["project_id"] = call(core, "project.create", {"name": "Other"})["project"]["id"]
        call(core, "presentation.workspace.save_narrative", payload, ok=False)
        assert (
            call(core, "presentation.workspace.get_narrative", scope_only(scope))["status"]
            == "missing"
        )
    finally:
        core.close()


def test_narrative_context_is_bounded_frozen_and_coexists_with_claims(tmp_path: Path):
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        save_claim(core, scope, target, evidence)
        saved = save(core, scope, text="x" * 1000)
        prepared = proposal(core, scope)
        packet = json.loads(provider.request_objects[-1].current_slide_summary)
        assert packet["reviewed_claim_context"] == prepared["reviewed_claim_context"]
        narrative = packet["presentation_narrative"]
        assert narrative == prepared["presentation_narrative"]
        assert narrative["fields"]["objective"] == "x" * 240
        assert narrative["shortened_fields"] == ["objective"] and narrative["status"] == "reviewed"
        with core._storage.project_database(scope["project_id"]) as connection:
            manifest = connection.execute(
                "SELECT context_manifest_json FROM provider_runs WHERE id=?",
                (prepared["provider_run_id"],),
            ).fetchone()[0]
        assert "Steering committee" not in manifest and scope["revision_id"] in manifest
        audience = create_profile(core, scope["project_id"], "Reviewer", "CTO")
        session = start_challenge(core, scope["project_id"])
        configure(core, scope["project_id"], session, [audience])
        changed = change(core, scope, target)
        new_scope = {**scope, "revision_id": changed["revision_id"]}
        save(core, new_scope, text="New intent", expected=saved["record_token"])
        call(
            core,
            "challenge.next_question",
            {"project_id": scope["project_id"], "session_id": session},
        )
        frozen = json.loads(provider.request_objects[-1].current_slide_summary)[
            "presentation_narrative"
        ]
        assert (
            frozen["revision_id"] == scope["revision_id"]
            and frozen["fields"]["objective"] == "x" * 240
        )
        assert (
            proposal(core, new_scope)["presentation_narrative"]["fields"]["objective"]
            == "New intent"
        )
    finally:
        core.close()


def test_local_only_narrative_never_reaches_remote_provider(tmp_path: Path):
    provider = PlanProvider(locality="remote")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, _, _ = setup(core, tmp_path)
        save(core, scope)
        error = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "expected_revision_id": scope["revision_id"],
                "slide_numbers": [1],
                "instruction": "Clarify",
            },
            ok=False,
        )
        assert error["code"] == "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED"
        assert not provider.request_objects
    finally:
        core.close()


def test_v15_narrative_migration_preserves_claim_rows(tmp_path: Path):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        saved = save_claim(core, scope, target, evidence)
        with core._storage.project_database(scope["project_id"]) as connection:
            connection.execute("DROP TABLE presentation_components")
            connection.execute("DROP TABLE presentation_rehearsal_objection_comparison_candidates")
            connection.execute("DROP TABLE presentation_rehearsal_objection_comparisons")
            connection.execute("DROP TABLE presentation_rehearsal_objection_findings")
            connection.execute("DROP TABLE presentation_rehearsal_objection_analyses")
            connection.execute("DROP TABLE presentation_rehearsal_analyses")
            connection.execute("DROP TABLE presentation_revision_checkpoints")
            connection.execute("DROP TABLE presentation_outline_sessions")
            connection.execute("DROP TABLE presentation_outline_proposals")
            connection.execute("DROP TABLE presentation_slide_takeaways")
            connection.execute("DROP TABLE presentation_narratives")
            connection.execute("PRAGMA user_version = 15")
            connection.execute("UPDATE project SET schema_version = 15")
            connection.commit()
        with core._storage.project_database(scope["project_id"]) as migrated:
            assert migrated.execute("PRAGMA user_version").fetchone()[0] == 24
            assert migrated.execute("SELECT COUNT(*) FROM presentation_claims").fetchone()[0] == 1
            assert (
                migrated.execute("SELECT COUNT(*) FROM presentation_narratives").fetchone()[0] == 0
            )
        claim = call(core, "presentation.workspace.list_claims", scope)["items"][0]
        assert claim["claim_id"] == saved["claim_id"] and claim["coverage"] == "supported"
        assert (
            call(core, "presentation.workspace.get_narrative", scope_only(scope))["status"]
            == "missing"
        )
    finally:
        core.close()


def test_narrative_serialized_provider_budget_includes_escaping(tmp_path: Path):
    from presenter_core.presentation.narrative import PresentationNarrativeService

    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, _, _ = setup(core, tmp_path)
        call(
            core,
            "presentation.workspace.save_narrative",
            {
                **scope_only(scope),
                "fields": {key: "\\" * limit for key, limit in FIELD_LIMITS.items()},
                "reviewed": True,
                "expected_record_token": None,
            },
        )
        value = PresentationNarrativeService(core._presentation_semantics).provider_context(
            scope["project_id"], scope["revision_id"]
        )
        assert len(json.dumps(value, ensure_ascii=False)) <= 3200
        assert set(value["shortened_fields"]) == set(FIELD_LIMITS)
    finally:
        core.close()


def test_bounded_narrative_lineage_exposes_missing_history(tmp_path: Path):
    import uuid

    from presenter_core.presentation.narrative import PresentationNarrativeService

    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, _, _ = setup(core, tmp_path)
        saved = save(core, scope)
        call(
            core,
            "presentation.workspace.save_slide_takeaway",
            {
                **scope,
                "takeaway": "Earlier author intent",
                "reviewed": True,
                "expected_record_token": None,
            },
        )
        parent = scope["revision_id"]
        with core._storage.project_database(scope["project_id"]) as connection:
            row = dict(
                connection.execute(
                    "SELECT * FROM presentation_revisions WHERE id=?", (parent,)
                ).fetchone()
            )
            for number in range(2, 104):
                revision = str(uuid.uuid4())
                columns = list(row)
                clone = {
                    **row,
                    "id": revision,
                    "parent_revision_id": parent,
                    "revision_number": number,
                }
                connection.execute(
                    "INSERT INTO presentation_revisions ("
                    + ",".join(columns)
                    + ") VALUES ("
                    + ",".join("?" for _ in columns)
                    + ")",
                    tuple(clone[key] for key in columns),
                )
                parent = revision
            connection.execute(
                "UPDATE presentation_revision_heads SET revision_id=? WHERE presentation_id=?",
                (parent, scope["document_id"]),
            )
            connection.commit()
        scope["revision_id"] = parent
        missing = call(core, "presentation.workspace.get_narrative", scope_only(scope))
        assert missing["status"] == "missing" and missing["lineage_truncated"]
        assert missing["record_token"] is None and not any(missing["fields"].values())
        missing_takeaway = call(core, "presentation.workspace.get_slide_takeaway", scope)
        assert missing_takeaway["status"] == "missing" and missing_takeaway["lineage_truncated"]
        assert missing_takeaway["takeaway"] == "" and missing_takeaway["record_token"] is None
        current_takeaway = call(
            core,
            "presentation.workspace.save_slide_takeaway",
            {
                **scope,
                "takeaway": "Current author intent",
                "reviewed": True,
                "expected_record_token": None,
            },
        )
        assert (
            current_takeaway["status"] == "reviewed" and not current_takeaway["lineage_truncated"]
        )

        service = PresentationNarrativeService(core._presentation_semantics)
        assert service.provider_context(scope["project_id"], parent)["lineage_truncated"]
        # Explicitly reviewing the current revision resolves bounded ancestry uncertainty.
        saved = save(core, scope, text="Current intent")
        assert saved["status"] == "reviewed" and not saved["lineage_truncated"]
    finally:
        core.close()
