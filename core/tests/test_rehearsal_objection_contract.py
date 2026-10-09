"""Objection hints cannot fabricate, duplicate or silently widen recorded quotes."""

import copy
import uuid

import pytest

from presenter_core.providers.models import ProviderError
from presenter_core.providers.rehearsal_objection_schema import (
    output_schema,
    validate_output,
    validate_window_output,
)

QUESTION = str(uuid.uuid4())
ANSWER = str(uuid.uuid4())
SPEECH = [
    {
        "utterance_id": QUESTION,
        "text": "What about migration cost? Who owns the pilot?",
        "actor": "other",
    },
    {
        "utterance_id": ANSWER,
        "text": "Finance owns the pilot. Costs remain uncertain.",
        "actor": "user",
    },
]


def observation():
    return {
        "concern": "Pilot ownership",
        "reason": "Review whether this recorded answer addresses the question.",
        "concern_quotes": [{"utterance_id": QUESTION, "quote": "Who owns the pilot?"}],
        "answer_status": "addressed",
        "answer_quotes": [{"utterance_id": ANSWER, "quote": "Finance owns the pilot."}],
    }


def test_no_concern_is_an_explicit_empty_result_not_an_invented_candidate():
    assert validate_window_output({"observations": []}, SPEECH) == {"observations": []}


def test_original_actor_labels_do_not_change_quote_identity_or_answer_authority():
    source = {"observations": [observation()]}
    result = validate_window_output(source, SPEECH)
    assert result == source and result is not source
    result["observations"][0]["concern_quotes"][0]["quote"] = "changed"
    assert source["observations"][0]["concern_quotes"][0]["quote"] == "Who owns the pilot?"
    assert "speaker_verified" not in source["observations"][0]


@pytest.mark.parametrize("status", ["partially_addressed", "unclear", "not_observed"])
def test_window_status_does_not_become_whole_run_resolution(status):
    item = observation()
    item["answer_status"] = status
    if status == "not_observed":
        item["answer_quotes"] = []
    result = validate_window_output({"observations": [item]}, SPEECH)
    assert result["observations"][0]["answer_status"] == status


@pytest.mark.parametrize(
    "change",
    [
        {"concern": " "},
        {"concern": "x" * 201},
        {"reason": "x" * 601},
        {"reason": "a\x00b"},
        {"confidence": 1},
        {"answer_status": "resolved"},
        {"answer_status": []},
        {"concern_quotes": []},
        {"answer_quotes": []},
        {"answer_status": "not_observed"},
        {"concern_quotes": [{"utterance_id": QUESTION, "quote": "invented concern"}]},
        {"answer_quotes": [{"utterance_id": ANSWER, "quote": "costs are approved"}]},
        {"concern_quotes": [{"utterance_id": ANSWER, "quote": "Who owns the pilot?"}]},
        {
            "answer_quotes": [
                {"utterance_id": str(uuid.uuid4()), "quote": "Finance owns the pilot."}
            ]
        },
        {"concern_quotes": [{"utterance_id": "x" * 36, "quote": "Who owns the pilot?"}]},
        {
            "concern_quotes": [
                {"utterance_id": QUESTION, "quote": "Who owns the pilot?", "verified": True}
            ]
        },
    ],
)
def test_unquoted_or_unbounded_authority_is_rejected(change):
    item = {**observation(), **change}
    with pytest.raises(ProviderError, match="invalid"):
        validate_window_output({"observations": [item]}, SPEECH)


def test_repeated_text_requires_a_unique_span_before_any_observation_can_survive():
    speech = copy.deepcopy(SPEECH)
    speech[0]["text"] += " Who owns the pilot?"
    with pytest.raises(ProviderError):
        validate_window_output({"observations": [observation()]}, speech)


def test_overlapping_concern_excerpts_cannot_inflate_recurrence_counts():
    first, second = observation(), observation()
    second["concern"] = "Who is responsible?"
    second["concern_quotes"][0]["quote"] = "owns the pilot"
    with pytest.raises(ProviderError):
        validate_window_output({"observations": [first, second]}, SPEECH)


def test_distinct_concerns_can_share_a_possible_answer_without_merging_observations():
    first, second = observation(), observation()
    second["concern"] = "Migration cost"
    second["concern_quotes"][0]["quote"] = "What about migration cost?"
    result = validate_window_output({"observations": [first, second]}, SPEECH)
    assert len(result["observations"]) == 2
    assert result["observations"][0]["answer_quotes"] == result["observations"][1]["answer_quotes"]


def test_duplicate_supplied_identity_does_not_silently_replace_original_speech():
    with pytest.raises(ProviderError):
        validate_window_output({"observations": [observation()]}, [*SPEECH, SPEECH[0]])


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"observations": None},
        {"observations": [observation()] * 5},
        {"observations": [], "applied": True},
    ],
)
def test_task_envelope_and_candidate_cap_are_strict(value):
    with pytest.raises(ProviderError):
        validate_output(value)


def test_schema_copy_cannot_widen_the_next_provider_contract():
    schema = output_schema()
    schema["properties"]["observations"]["maxItems"] = 100
    assert output_schema()["properties"]["observations"]["maxItems"] == 4
