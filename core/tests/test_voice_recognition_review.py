"""Recognition observations are ephemeral, bounded and never accuracy judgments."""

from pathlib import Path

import pytest

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import DeterministicFakeAudioInput
from presenter_core.asr.recognition_review import recognition_review
from tests.test_presentation_voice import (
    VOICE_CANCEL,
    VOICE_START,
    VOICE_STOP,
    _call,
    _core,
    _feed_instruction,
    _start_params,
    _wait_until,
    _workspace_context,
)


@pytest.mark.parametrize("score", [None, False, float("nan"), float("inf"), -0.1, 1.1, 10**500])
def test_unavailable_or_invalid_score_does_not_become_confidence(score):
    review = recognition_review(["Do not change the cost."], [score])
    assert review["unavailable_count"] == 1
    assert review["chunks"] == [{"text": "Do not change the cost.", "adapter_score": None}]


def test_bounded_preview_counts_all_unknown_phrases_and_retains_original_scores():
    parts = [f"Original phrase {i}" for i in range(70)]
    scores = [0.2, 0.9, *([None] * 68)]
    review = recognition_review(parts, scores)
    assert review["chunk_count"] == 70 and review["truncated"] is True
    assert review["unavailable_count"] == 68
    assert len(review["chunks"]) == 64
    assert review["chunks"][0] == {"text": parts[0], "adapter_score": 0.2}
    assert review["chunks"][1]["adapter_score"] == 0.9


def test_empty_review_and_mismatched_scores():
    assert recognition_review([], []) == {
        "version": 1,
        "chunk_count": 0,
        "unavailable_count": 0,
        "truncated": False,
        "chunks": [],
    }
    with pytest.raises(ValueError):
        recognition_review(["phrase"], [])


@pytest.mark.parametrize("intent", ["rewrite", "edit_plan_slide", "edit_plan_deck", "outline"])
@pytest.mark.parametrize("score", [None, 0.2])
def test_actual_workspace_capture_returns_original_review_without_durable_rows(
    tmp_path: Path, intent: str, score: float | None
):
    audio = DeterministicFakeAudioInput()
    events = []
    core = _core(
        tmp_path / "data",
        audio=audio,
        adapter=DeterministicFakeASRAdapter(final_text="Do not change the cost.", confidence=score),
        events=events,
    )
    try:
        if intent == "outline":
            project = _call(core, "project.create", {"name": "Outline review"})["project"]["id"]
            params = {"project_id": project, "intent": "outline", "scope": "deck"}
        else:
            context = _workspace_context(core)
            project = context["project_id"]
            params = _start_params(context, intent)
        capture = _call(core, VOICE_START, params)["capture_id"]
        _feed_instruction(audio)
        result = _call(core, VOICE_STOP, {"project_id": project, "capture_id": capture})
        assert result["transcript"] == "Do not change the cost."
        assert result["recognition_review"] == recognition_review([result["transcript"]], [score])
        assert not audio.started and core._asr.active_owner_details() is None
        assert not any(event["event"] == "asr.final" for event in events)
        with core._storage.project_database(project) as connection:
            for table in ("utterances", "sessions", "provider_runs"):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        assert core.close() is True


def test_cancel_purges_original_phrase_scores_before_releasing_owner(tmp_path: Path):
    audio = DeterministicFakeAudioInput()
    core = _core(
        tmp_path / "data",
        audio=audio,
        adapter=DeterministicFakeASRAdapter(final_text="Keep the cost.", confidence=0.2),
        events=[],
    )
    try:
        project = _call(core, "project.create", {"name": "Canceled review"})["project"]["id"]
        capture = _call(
            core,
            VOICE_START,
            {
                "project_id": project,
                "intent": "outline",
                "scope": "deck",
            },
        )["capture_id"]
        active = core._asr._active
        assert active is not None
        _feed_instruction(audio)
        assert _wait_until(lambda: active.workspace_final_scores == [0.2])
        result = _call(core, VOICE_CANCEL, {"project_id": project, "capture_id": capture})
        assert result["cancelled"] is True
        assert "recognition_review" not in result
        assert active.workspace_final_parts == [] and active.workspace_final_scores == []
        assert not audio.started and core._asr.active_owner_details() is None
    finally:
        assert core.close() is True
