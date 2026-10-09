"""Explicit marked objection recurrence preserves independent original review authority."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import DeterministicFakeAudioInput
from presenter_core.errors import CoreDomainError
from presenter_core.presentation.recurring_objections import group_objections
from presenter_core.storage import database
from tests.test_m6_run import make_core
from tests.test_presentation_planning import call

METHOD = "presentation.workspace.recurring_objections"


@pytest.fixture
def rehearsals(tmp_path: Path):
    core = make_core(tmp_path, DeterministicFakeAudioInput(), DeterministicFakeASRAdapter(), [])
    try:
        project = call(core, "project.create", {"name": "Objections"})["project"]["id"]
        document = call(
            core,
            "presentation.workspace.create_from_outline",
            {
                "project_id": project,
                "title": "Decision",
                "slides": [
                    {"title": name, "bullets": ["Review"], "notes": "Initial notes"}
                    for name in ("Opening", "Decision")
                ],
            },
        )["document"]["id"]
        revision = call(
            core,
            "presentation.workspace.list_revisions",
            {"project_id": project, "document_id": document},
        )["current_revision_id"]
        scope = {"project_id": project, "document_id": document, "expected_revision_id": revision}

        def run(notes: list[str], ordinal: int = 1):
            call(core, "presentation.workspace.select_for_rehearsal", scope)
            identity = call(
                core,
                "session.start",
                {
                    "project_id": project,
                    "mode": "run",
                    "current_slide_start": ordinal,
                    "expected_presentation_revision_id": scope["expected_revision_id"],
                },
            )["session"]["id"]
            for note in notes:
                call(
                    core,
                    "run.mark_event",
                    {
                        "project_id": project,
                        "session_id": identity,
                        "marker_type": "objection",
                        "note": note,
                    },
                )
            result = call(core, "session.stop", {"project_id": project, "session_id": identity})
            return identity, result

        yield core, scope, run
    finally:
        core.close()


def test_recurrence_requires_distinct_sessions_and_preserves_wording(rehearsals):
    core, scope, run = rehearsals
    run(["Why this cost?", "Why this cost?", "why this cost?", "Why this cost!"])
    assert call(core, METHOD, scope)["groups"] == []
    _, ended = run(["  Why  this cost?  "])
    assert any(
        "marked objection" in question
        for question in ended["debrief"]["recommended_challenge_questions"]
    )
    result = call(core, METHOD, scope)
    assert result["total_groups"] == 1
    group = result["groups"][0]
    assert (group["session_count"], group["occurrence_count"]) == (2, 3)
    assert group["note"] == "Why this cost?"
    assert result["ungrouped_objections"] == 2
    assert group["dispositions"] == {"unreviewed": 3, "applied": 0, "rejected": 0}
    assert {finding["quote"] for finding in group["occurrences"]} == {
        "Why this cost?",
        "  Why  this cost?  ",
    }


def test_matching_words_on_another_slide_do_not_merge(rehearsals):
    core, scope, run = rehearsals
    run(["Why this cost?"], 1)
    run(["Why this cost?"], 2)
    assert call(core, METHOD, scope)["groups"] == []


def test_group_follows_reorder_and_each_review_remains_independent(rehearsals):
    core, scope, run = rehearsals
    run(["Why this cost?"])
    first = call(
        core,
        "presentation.workspace.review_deck_semantics",
        {
            "project_id": scope["project_id"],
            "document_id": scope["document_id"],
            "revision_id": scope["expected_revision_id"],
        },
    )["items"]
    reordered = call(
        core,
        "presentation.workspace.reorder_slides",
        {**scope, "ordered_slide_ids": [item["slide_id"] for item in first][::-1]},
    )
    scope["expected_revision_id"] = reordered["revision_id"]
    call(core, "source.reindex", {key: scope[key] for key in ("project_id", "document_id")})
    run(["Why this cost?"], 2)
    group = call(core, METHOD, scope)["groups"][0]
    assert group["current_slide_number"] == 2
    assert {item["source_slide_number"] for item in group["occurrences"]} == {1, 2}
    identity = group["group_id"]
    finding = group["selected_finding"]
    call(
        core,
        "presentation.workspace.reject_rehearsal_finding",
        {**scope, "finding_id": finding["finding_id"]},
    )
    current = call(core, METHOD, scope)["groups"][0]
    assert current["group_id"] == identity
    assert current["dispositions"] == {"unreviewed": 1, "applied": 0, "rejected": 1}
    assert current["selected_finding"]["finding_id"] != finding["finding_id"]
    call(
        core,
        "presentation.workspace.reject_rehearsal_finding",
        {**scope, "finding_id": finding["finding_id"], "reopen": True},
    )
    assert call(core, METHOD, scope)["groups"][0]["dispositions"]["unreviewed"] == 2


def test_original_objection_beyond_default_list_can_be_resolved(rehearsals):
    core, scope, run = rehearsals
    run([f"Unique note {index}" for index in range(110)] + ["Need original evidence"])
    run(["Need original evidence"])
    group = call(core, METHOD, scope)["groups"][0]
    assert group["session_count"] == 2
    assert group["occurrence_count"] == 2
    # Old occurrence after the first 100 category rows is still independently resolvable.
    older = group["occurrences"][-1]
    listed = call(core, "presentation.workspace.list_rehearsal_findings", scope)
    assert older["finding_id"] not in {item["finding_id"] for item in listed["findings"]}
    call(
        core,
        "presentation.workspace.reject_rehearsal_finding",
        {**scope, "finding_id": older["finding_id"]},
    )
    assert call(core, METHOD, scope)["groups"][0]["dispositions"]["rejected"] == 1


@pytest.mark.parametrize(
    "extra", [{"limit": 0}, {"limit": 21}, {"offset": True}, {"offset": -1}, {"unexpected": 1}]
)
def test_bad_pages_are_rejected(rehearsals, extra):
    core, scope, _ = rehearsals
    assert call(core, METHOD, {**scope, **extra}, ok=False)["code"] == "INVALID_REQUEST"


def test_removed_slide_keeps_original_group_without_current_navigation(rehearsals):
    core, scope, run = rehearsals
    run(["Need evidence"])
    run(["Need evidence"])
    original = call(core, METHOD, scope)["groups"][0]
    removed = call(
        core, "presentation.workspace.delete_slide", {**scope, "slide_id": original["slide_id"]}
    )
    stale = call(core, METHOD, scope, ok=False)
    assert stale["code"] == "PRESENTATION_REVISION_CONFLICT"
    scope["expected_revision_id"] = removed["revision_id"]
    group = call(core, METHOD, scope)["groups"][0]
    assert group["current_slide_number"] is None and group["group_id"] == original["group_id"]


def _observation(index: int, note: str = "Risk", slide: str | None = "slide"):
    return {
        "finding_id": str(index),
        "kind": "marked",
        "label": "objection",
        "slide_id": slide,
        "session_id": f"session-{index}",
        "quote": note,
        "current_slide_number": 1,
        "disposition": "unreviewed",
        "source_revision_number": 1,
    }


def test_group_pages_and_preview_are_bounded_without_hiding_next_unreviewed():
    findings = [_observation(index) for index in range(20)]
    for finding in findings[:19]:
        finding["disposition"] = "applied"
    groups, excluded = group_objections(
        "doc", findings + [_observation(22, " "), _observation(23, slide=None)]
    )
    assert excluded == 2 and len(groups) == 1
    assert groups[0]["occurrence_count"] == 20 and len(groups[0]["occurrences"]) == 5
    assert groups[0]["occurrences_truncated"] is True
    assert groups[0]["selected_finding"]["finding_id"] == "19"
    assert groups[0]["selected_finding"] in groups[0]["occurrences"]
    many = []
    for index in range(25):
        many.extend(
            [
                _observation(index * 2, f"Concern {index}"),
                _observation(index * 2 + 1, f"Concern {index}"),
            ]
        )
    assert len(group_objections("doc", many)[0]) == 25
    assert groups[0]["group_id"] != group_objections("other", findings)[0][0]["group_id"]


def _legacy19(path: Path):
    with sqlite3.connect(path) as connection:
        for version in range(1, 20):
            getattr(database, f"_migrate_project_v{version}")(connection)
        connection.execute("PRAGMA user_version=19")
        project = str(uuid.uuid4())
        session = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO project (id,name,created_at,updated_at,privacy_mode, "
            "default_style_policy,schema_version) "
            "VALUES (?,'Legacy','start','now','local_only','preserve_voice',19)",
            (project,),
        )
        connection.execute(
            "INSERT INTO sessions (id,project_id,mode,started_at,ended_at,style_policy, "
            "privacy_mode,provider_id,status,teach_state) "
            "VALUES (?,?,'run','start','end','preserve_voice','local_only', "
            "'fixture','completed','completed')",
            (session, project),
        )
        for index, kind in enumerate(("question", "weak_point", "note")):
            connection.execute(
                "INSERT INTO run_markers VALUES (?,?,?, ?,1,?,'now')",
                (str(uuid.uuid4()), session, kind, index, None if index == 2 else "Original note"),
            )
        connection.commit()
    return session


def test_schema19_upgrade_preserves_all_markers_and_foreign_keys(tmp_path: Path):
    path = tmp_path / "legacy19.db"
    session = _legacy19(path)
    with sqlite3.connect(path) as connection:
        before = connection.execute("SELECT * FROM run_markers ORDER BY rowid").fetchall()
    migrated = database.connect_project_database(path)
    try:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 22
        assert migrated.execute("SELECT schema_version FROM project").fetchone()[0] == 22
        assert [
            tuple(row) for row in migrated.execute("SELECT * FROM run_markers ORDER BY rowid")
        ] == before
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []
        migrated.execute(
            "INSERT INTO run_markers VALUES (?,?, 'objection',1,1,'Why?','now')",
            (str(uuid.uuid4()), session),
        )
        migrated.commit()
        assert migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='run_markers_session_idx'"
        ).fetchone()
        migrated.execute("DELETE FROM sessions WHERE id=?", (session,))
        migrated.commit()
        assert migrated.execute("SELECT COUNT(*) FROM run_markers").fetchone()[0] == 0
    finally:
        migrated.close()
    reopened = database.connect_project_database(path)
    reopened.close()


def test_failed_upgrade_rolls_back_original_schema_rows_and_index(tmp_path: Path, monkeypatch):
    path = tmp_path / "rollback19.db"
    _legacy19(path)
    original = database._migrate_project_v20

    def failing(connection):
        original(connection)
        connection.execute(
            "INSERT INTO run_markers VALUES ('bad','bad','unsupported',-1,NULL,NULL,'now')"
        )

    monkeypatch.setattr(database, "_migrate_project_v20", failing)
    with pytest.raises(CoreDomainError) as error:
        database.connect_project_database(path)
    assert error.value.code == "DATABASE_MIGRATION_FAILED"
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 19
        assert connection.execute("SELECT COUNT(*) FROM run_markers").fetchone()[0] == 3
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='run_markers_v20'"
            ).fetchone()
            is None
        )
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='run_markers_session_idx'"
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE run_markers SET marker_type='objection'")


def test_applying_selected_objection_records_only_its_original_provenance(rehearsals):
    core, scope, run = rehearsals
    run(["Why this cost?"])
    run(["Why this cost?"])
    group = call(core, METHOD, scope)["groups"][0]
    finding = group["selected_finding"]
    saved = call(
        core,
        "presentation.workspace.apply_rehearsal_edit",
        {
            **scope,
            "finding_id": finding["finding_id"],
            "edit_kind": "notes",
            "slide_id": group["slide_id"],
            "expected_text": "Initial notes",
            "replacement_text": (
                "Initial notes\n\nReviewed: explain the cost before asking for a decision."
            ),
        },
    )
    scope["expected_revision_id"] = saved["revision_id"]
    result = call(core, METHOD, scope)["groups"][0]
    assert result["dispositions"] == {"unreviewed": 1, "applied": 1, "rejected": 0}
    applied = next(
        item for item in result["occurrences"] if item["finding_id"] == finding["finding_id"]
    )
    assert applied["applied_revision_id"] == saved["revision_id"]
    assert applied["source_revision_id"] == finding["source_revision_id"]
    assert (
        call(
            core,
            "presentation.workspace.apply_rehearsal_edit",
            {
                **scope,
                "finding_id": finding["finding_id"],
                "edit_kind": "notes",
                "slide_id": group["slide_id"],
                "expected_text": "anything",
                "replacement_text": "anything else",
            },
            ok=False,
        )["code"]
        == "REHEARSAL_FINDING_REVIEWED"
    )
