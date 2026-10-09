"""Individual objection dispositions and reviewed native edits retain exact recording provenance."""

import json
import uuid
from zipfile import ZipFile

import pytest
import test_rehearsal_coverage as coverage_tests
from test_presentation_planning import call
from test_rehearsal_objection_context import append
from test_rehearsal_objection_store import ObjectionProvider, analysis, params, read, saved
from test_rehearsal_semantic_adoption import native_files, rewrite_service

from presenter_core.providers.fake import DeterministicFakeReasoningProvider

rehearsal = coverage_tests.rehearsal
PREFIX = "presentation.workspace."


def selection(scope, result, index=0):
    return {k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")} | {
        "finding_id": result["finding_ids"][index]
    }


def target(core, scope):
    return next(
        item
        for item in call(
            core,
            PREFIX + "list_text_targets",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "revision_id": scope["expected_revision_id"],
                "slide_number": 1,
            },
        )["targets"]
        if item["current_text"] == "First point"
    )


def edit(core, scope, result, kind="notes"):
    finding = core._presentation_rehearsal.resolve_finding(selection(scope, result))
    values = selection(scope, result) | {
        "slide_id": result["slide_id"],
        "edit_kind": kind,
        "expected_text": "private notes excluded",
        "replacement_text": "private notes excluded\n\n" + finding["quote"],
    }
    if kind == "text":
        selected = target(core, scope)
        values.update(
            object_id=selected["object_id"],
            expected_text=selected["current_text"],
            replacement_text=finding["quote"],
        )
    return values


def rewrite_params(core, scope, result):
    return {
        **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
        "slide_number": 1,
        "object_id": target(core, scope)["object_id"],
        "instruction": "Review this exact recorded concern and improve the selected text.",
        "rehearsal_finding_id": result["finding_ids"][0],
    }


def test_exact_candidate_resolution_and_public_detail_keep_quotes_and_interpretation_separate(
    rehearsal,
):
    core, scope = rehearsal
    result = saved(core, scope)
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute(
            "UPDATE run_debriefs SET debrief_json='broken JSON' WHERE session_id=?",
            (scope["session_id"],),
        )
        db.commit()
    finding = core._presentation_rehearsal.resolve_finding(selection(scope, result))
    concern = result["hint"]["observations"][0]
    assert finding["kind"] == "semantic_objection"
    assert finding["quote"] == concern["concern_quotes"][0]["quote"]
    assert finding["quote"] != concern["concern"]
    assert "object_id" not in finding
    assert finding["semantic_review"]["recorded_speech_included"]
    assert not finding["semantic_review"]["speaker_identity_verified"]
    detail = call(
        core,
        PREFIX + "get_rehearsal_objections_analysis",
        {
            **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "analysis_id": result["analysis_id"],
        },
    )
    public = detail["findings"][0]["finding"]
    assert public["quote"] == finding["quote"] and "_objection_guard" not in public


def test_each_candidate_dismisses_and_reopens_without_changing_sibling_or_native_files(rehearsal):
    core, scope = rehearsal
    append(core, scope, "Who will fund this pilot?")
    result = saved(core, scope, multi=True)
    before = native_files(core, scope)
    call(core, PREFIX + "reject_rehearsal_finding", selection(scope, result))
    assert [value["disposition"] for value in read(core, scope, result)["findings"]] == [
        "rejected",
        "unreviewed",
    ]
    call(core, PREFIX + "reject_rehearsal_finding", selection(scope, result) | {"reopen": True})
    assert all(
        value["disposition"] == "unreviewed" for value in read(core, scope, result)["findings"]
    )
    assert native_files(core, scope) == before


@pytest.mark.parametrize("kind", ["notes", "text"])
def test_explicit_native_save_records_only_selected_candidate_and_exact_source_quote(
    rehearsal, kind
):
    core, scope = rehearsal
    append(core, scope, "Who will fund this pilot?")
    result = saved(core, scope, multi=True)
    values = edit(core, scope, result, kind)
    applied = call(core, PREFIX + "apply_rehearsal_edit", values)
    assert applied["changed"] and applied["parent_revision_id"] == scope["expected_revision_id"]
    current = scope | {"expected_revision_id": applied["revision_id"]}
    item = read(core, current, result)
    assert [candidate["disposition"] for candidate in item["findings"]] == ["applied", "unreviewed"]
    assert item["findings"][0]["applied_revision_id"] == applied["revision_id"]
    assert item["snapshot"]["source_revision_id"] == scope["expected_revision_id"]
    with core._storage.project_database(scope["project_id"]) as db:
        row = db.execute(
            "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
            (applied["revision_id"],),
        ).fetchone()
    path = core._storage.paths.snapshot_path(scope["project_id"], row[0], require_exists=True)
    with ZipFile(path) as package:
        texts = "\n".join(
            package.read(name).decode("utf-8")
            for name in package.namelist()
            if name.startswith(
                "ppt/notesSlides/notesSlide" if kind == "notes" else "ppt/slides/slide"
            )
            and name.endswith(".xml")
        )
    assert result["hint"]["observations"][0]["concern_quotes"][0]["quote"] in texts
    assert result["hint"]["observations"][0]["concern"] not in texts
    if kind == "notes":
        assert "private notes excluded" in texts
    assert (
        call(
            core,
            PREFIX + "reject_rehearsal_finding",
            selection(current, result)
            | {
                "reopen": True,
            },
            ok=False,
        )["code"]
        == "REHEARSAL_FINDING_REVIEWED"
    )


def test_no_op_save_keeps_candidate_unreviewed(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    values = edit(core, scope, result)
    before = native_files(core, scope)
    unchanged = call(
        core,
        PREFIX + "apply_rehearsal_edit",
        values | {"replacement_text": values["expected_text"]},
    )
    assert not unchanged["changed"]
    assert read(core, scope, result)["findings"][0]["disposition"] == "unreviewed"
    assert native_files(core, scope) == before


def test_sibling_candidates_can_save_independently_across_successive_native_revisions(rehearsal):
    core, scope = rehearsal
    append(core, scope, "Who will fund this pilot?")
    result = saved(core, scope, multi=True)
    first_values = edit(core, scope, result)
    first = call(core, PREFIX + "apply_rehearsal_edit", first_values)
    current = scope | {"expected_revision_id": first["revision_id"]}
    second_finding = core._presentation_rehearsal.resolve_finding(selection(current, result, 1))
    second = call(
        core,
        PREFIX + "apply_rehearsal_edit",
        selection(current, result, 1)
        | {
            "slide_id": result["slide_id"],
            "edit_kind": "notes",
            "expected_text": first_values["replacement_text"],
            "replacement_text": first_values["replacement_text"] + "\n\n" + second_finding["quote"],
        },
    )
    assert second["changed"] and second["parent_revision_id"] == first["revision_id"]
    latest = scope | {"expected_revision_id": second["revision_id"]}
    findings = read(core, latest, result)["findings"]
    assert [item["disposition"] for item in findings] == ["applied", "applied"]
    assert [item["applied_revision_id"] for item in findings] == [
        first["revision_id"],
        second["revision_id"],
    ]


def test_changed_recording_blocks_save_and_rewrite_but_remains_dismissible(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    values, rewrite = edit(core, scope, result), rewrite_params(core, scope, result)
    provider = DeterministicFakeReasoningProvider(locality="local")
    rewrite_service(core, provider)
    append(core, scope, "Unmapped late utterance", ordinal=None)
    before = native_files(core, scope)
    for method, payload in (("apply_rehearsal_edit", values), ("propose_text_rewrite", rewrite)):
        assert call(core, PREFIX + method, payload, ok=False)["code"] == "REHEARSAL_CONTEXT_CHANGED"
    assert provider.call_count == 0 and native_files(core, scope) == before
    call(core, PREFIX + "reject_rehearsal_finding", selection(scope, result))
    call(core, PREFIX + "reject_rehearsal_finding", selection(scope, result) | {"reopen": True})
    detail = read(core, scope, result)
    assert not detail["context_current"] and not detail["findings"][0]["can_adopt"]


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("speech", "REHEARSAL_CONTEXT_CHANGED"),
        ("review", "REHEARSAL_FINDING_REVIEWED"),
        ("analysis", "REHEARSAL_OBJECTION_CORRUPT"),
        ("candidate", "REHEARSAL_OBJECTION_CORRUPT"),
        ("audit", "REHEARSAL_OBJECTION_CORRUPT"),
    ],
)
def test_atomic_guard_rolls_back_native_revision_and_review_on_late_mutation(
    rehearsal, monkeypatch, mutation, code
):
    core, scope = rehearsal
    result = saved(core, scope)
    values, before = edit(core, scope, result), native_files(core, scope)
    method = core._presentation_rehearsal._edits.replace_speaker_notes

    def changed(params, *, on_commit):
        def callback(db, revision):
            if mutation == "speech":
                db.execute(
                    "UPDATE utterances SET text='late recording change' WHERE session_id=?",
                    (scope["session_id"],),
                )
            elif mutation == "review":
                db.execute(
                    "INSERT INTO presentation_rehearsal_reviews VALUES (?,?,?,?,?,?,?,?)",
                    (
                        result["finding_ids"][0],
                        scope["session_id"],
                        scope["document_id"],
                        scope["expected_revision_id"],
                        scope["expected_revision_id"],
                        None,
                        "rejected",
                        "now",
                    ),
                )
            elif mutation == "analysis":
                db.execute(
                    "UPDATE presentation_rehearsal_objection_analyses SET snapshot_sha256=?",
                    ("0" * 64,),
                )
            elif mutation == "candidate":
                db.execute("DELETE FROM presentation_rehearsal_objection_findings")
            else:
                db.execute(
                    "UPDATE provider_runs SET status='error' WHERE id=?", (result["analysis_id"],)
                )
            on_commit(db, revision)

        return method(params, on_commit=callback)

    monkeypatch.setattr(core._presentation_rehearsal._edits, "replace_speaker_notes", changed)
    failure = call(core, PREFIX + "apply_rehearsal_edit", values, ok=False)
    assert failure["code"] == code
    assert native_files(core, scope) == before
    with core._storage.project_database(scope["project_id"]) as db:
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_reviews").fetchone()[0] == 0
        assert (
            db.execute("SELECT revision_id FROM presentation_revision_heads").fetchone()[0]
            == scope["expected_revision_id"]
        )
    assert read(core, scope, result)["findings"][0]["disposition"] == "unreviewed"


def test_rewrite_discloses_unverified_window_metadata_and_exact_concern_separately(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    provider = DeterministicFakeReasoningProvider(locality="local")
    rewrite_service(core, provider)
    before = native_files(core, scope)
    rewritten = call(core, PREFIX + "propose_text_rewrite", rewrite_params(core, scope, result))
    request = provider.request_objects[-1]
    context = json.loads(request.current_slide_summary)["rehearsal_finding"]
    observation = result["hint"]["observations"][0]
    assert context["kind"] == "semantic_objection"
    assert context["quote"] == observation["concern_quotes"][0]["quote"]
    assert context["semantic_review"]["concern"] == observation["concern"]
    assert context["semantic_review"]["answer_status"] == "not_observed"
    assert "private notes excluded" not in request.serialized_input()
    assert (
        not request.evidence
        and not request.preferred_user_explanations
        and not request.speaker_evidence
    )
    assert native_files(core, scope) == before
    assert read(core, scope, result)["findings"][0]["disposition"] == "unreviewed"
    with core._storage.project_database(scope["project_id"]) as db:
        manifest = json.loads(
            db.execute(
                "SELECT context_manifest_json FROM provider_runs WHERE id=?",
                (rewritten["provider_run_id"],),
            ).fetchone()[0]
        )
    assert manifest["rehearsal_session_ids"] == [scope["session_id"]]
    assert manifest["rehearsal_finding_ids"] == [result["finding_ids"][0]]


def test_recording_change_during_rewrite_rejects_output_before_success(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)

    class ChangedProvider(DeterministicFakeReasoningProvider):
        def generate(self, invocation):
            output = super().generate(invocation)
            append(core, scope, "Late recorded utterance")
            return output

    provider = ChangedProvider(locality="local")
    rewrite_service(core, provider)
    before = native_files(core, scope)
    failure = call(
        core, PREFIX + "propose_text_rewrite", rewrite_params(core, scope, result), ok=False
    )
    assert failure["code"] == "REHEARSAL_CONTEXT_CHANGED" and provider.call_count == 1
    assert native_files(core, scope) == before
    with core._storage.project_database(scope["project_id"]) as db:
        row = db.execute(
            "SELECT status,error_code FROM provider_runs "
            "WHERE task_type='presentation_text_rewrite'"
        ).fetchone()
    assert row["status"] == "error" and row["error_code"] == "REHEARSAL_CONTEXT_CHANGED"


def test_reordered_original_slide_can_save_notes_with_original_provenance(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    values = edit(core, scope, result)
    slides = call(core, PREFIX + "rehearsal_coverage", scope)["slides"]
    updated = call(
        core,
        PREFIX + "reorder_slides",
        {
            **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "ordered_slide_ids": [item["slide_id"] for item in slides][::-1],
        },
    )
    current = scope | {"expected_revision_id": updated["revision_id"]}
    finding = core._presentation_rehearsal.resolve_finding(selection(current, result))
    assert finding["source_slide_number"] == 1 and finding["current_slide_number"] == 3
    applied = call(
        core,
        PREFIX + "apply_rehearsal_edit",
        values | {"expected_revision_id": updated["revision_id"]},
    )
    assert applied["changed"]


def test_removed_original_slide_blocks_adoption_and_remains_dismissible(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    values = edit(core, scope, result)
    deleted = call(
        core,
        PREFIX + "delete_slide",
        {
            **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "slide_id": result["slide_id"],
        },
    )
    current = scope | {"expected_revision_id": deleted["revision_id"]}
    before = native_files(core, scope)
    failure = call(
        core,
        PREFIX + "apply_rehearsal_edit",
        values | {"expected_revision_id": deleted["revision_id"]},
        ok=False,
    )
    assert failure["code"] == "REHEARSAL_SLIDE_REMOVED"
    call(core, PREFIX + "reject_rehearsal_finding", selection(current, result))
    assert read(core, current, result)["findings"][0]["disposition"] == "rejected"
    assert native_files(core, scope) == before


def test_possible_answer_quotes_are_separate_and_not_appended_as_concern_notes(rehearsal):
    core, scope = rehearsal
    answer = "A recorded possible answer says the pilot has a budget."
    answer_id = append(core, scope, answer, actor="user")

    class AnswerProvider(ObjectionProvider):
        def generate(self, invocation):
            result = super().generate(invocation)
            result.output["observations"][0].update(
                {
                    "answer_status": "addressed",
                    "answer_quotes": [{"utterance_id": answer_id, "quote": answer}],
                }
            )
            return result

    result = analysis(core, AnswerProvider()).analyze(params(core, scope))
    finding = core._presentation_rehearsal.resolve_finding(selection(scope, result))
    assert answer not in finding["quote"]
    assert finding["semantic_review"]["answer_status"] == "addressed"
    assert finding["semantic_review"]["answer_references"][0]["utterance_id"] == answer_id
    assert not finding["semantic_review"]["speaker_identity_verified"]
    values = edit(core, scope, result)
    assert answer not in values["replacement_text"]
    applied = call(core, PREFIX + "apply_rehearsal_edit", values)
    assert applied["changed"]


@pytest.mark.parametrize("native_revision", ["original", "baseline"])
def test_native_snapshot_mutation_inside_save_rolls_back_revision_and_candidate(
    rehearsal, monkeypatch, native_revision
):
    core, scope = rehearsal
    result = saved(core, scope)
    values = edit(core, scope, result)
    slides = call(core, PREFIX + "rehearsal_coverage", scope)["slides"]
    reordered = call(
        core,
        PREFIX + "reorder_slides",
        {
            **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "ordered_slide_ids": [item["slide_id"] for item in slides][::-1],
        },
    )
    current = scope | {"expected_revision_id": reordered["revision_id"]}
    with core._storage.project_database(scope["project_id"]) as db:
        row = db.execute(
            "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
            (
                scope["expected_revision_id"]
                if native_revision == "original"
                else reordered["revision_id"],
            ),
        ).fetchone()
    path = core._storage.paths.snapshot_path(scope["project_id"], row[0], require_exists=True)
    original_bytes = path.read_bytes()
    before = native_files(core, scope)
    method = core._presentation_rehearsal._edits.replace_speaker_notes

    def changed(parameters, *, on_commit):
        def callback(db, revision):
            path.write_bytes(original_bytes + b"late snapshot mutation")
            try:
                on_commit(db, revision)
            finally:
                path.write_bytes(original_bytes)

        return method(parameters, on_commit=callback)

    monkeypatch.setattr(core._presentation_rehearsal._edits, "replace_speaker_notes", changed)
    failure = call(
        core,
        PREFIX + "apply_rehearsal_edit",
        values | {"expected_revision_id": reordered["revision_id"]},
        ok=False,
    )
    assert failure["code"] == "SOURCE_SNAPSHOT_CHANGED"
    assert native_files(core, scope) == before
    assert read(core, current, result)["findings"][0]["disposition"] == "unreviewed"


@pytest.mark.parametrize("field", ["project_id", "document_id", "expected_revision_id"])
def test_foreign_candidate_scope_is_rejected_before_native_save(rehearsal, field):
    core, scope = rehearsal
    result = saved(core, scope)
    before = native_files(core, scope)
    call(
        core,
        PREFIX + "apply_rehearsal_edit",
        edit(core, scope, result) | {field: str(uuid.uuid4())},
        ok=False,
    )
    assert native_files(core, scope) == before
