"""Comparison cannot widen candidate identities or merge their review authority."""

import copy
import json
import uuid
from itertools import product
from types import SimpleNamespace

import pytest
import test_local_provider as local_tests

from presenter_core.providers.codex import CodexReasoningProvider
from presenter_core.providers.context import APPLICATION_POLICY
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.providers.local import LocalReasoningProvider
from presenter_core.providers.models import (
    TASK_CONTEXT_CLASS_ALLOWLIST,
    ProviderError,
    ProviderInvocation,
    ReasoningRequest,
    derive_context_manifest,
    output_schema_for,
    task_instruction_for,
    validate_provider_output,
)
from presenter_core.providers.openai import OpenAIReasoningProvider
from presenter_core.providers.rehearsal_objection_equivalence_schema import (
    TASK_INSTRUCTION,
    TASK_TYPE,
    output_schema,
    validate_output,
    validate_pair_output,
)

server = local_tests.server
LEFT = [f"{number:064x}" for number in range(1, 5)]
RIGHT = [f"{number:064x}" for number in range(5, 9)]


def matrix(left=LEFT, right=RIGHT, relationship="unclear"):
    return {
        "comparisons": [
            {
                "left_finding_id": first,
                "right_finding_id": second,
                "relationship": relationship,
                "reason": "Review the exact original concerns; interpretation is unverified.",
            }
            for first, second in product(left, right)
        ]
    }


@pytest.mark.parametrize("relationship", ["equivalent", "related", "distinct", "unclear"])
def test_complete_matrix_preserves_original_sides_and_has_no_merged_authority(relationship):
    value = matrix(relationship=relationship)
    result = validate_pair_output(value, LEFT, RIGHT)
    assert result == value and result is not value
    assert len(result["comparisons"]) == 16
    assert all(
        set(item) == {"left_finding_id", "right_finding_id", "relationship", "reason"}
        for item in result["comparisons"]
    )
    result["comparisons"][0]["reason"] = "Changed independently"
    assert value["comparisons"][0]["reason"] != "Changed independently"


def test_provider_order_is_canonicalized_without_mutating_input_or_fabricating_pairs():
    value = matrix()
    value["comparisons"].reverse()
    before = copy.deepcopy(value)
    assert validate_pair_output(value, LEFT, RIGHT) == matrix()
    assert value == before


@pytest.mark.parametrize("kind", ["omitted", "duplicated", "foreign", "reversed", "same_side"])
def test_unbound_incomplete_or_duplicated_comparisons_are_rejected(kind):
    value = matrix()
    if kind == "omitted":
        value["comparisons"].pop()
    elif kind == "duplicated":
        value["comparisons"][-1] = copy.deepcopy(value["comparisons"][0])
    elif kind == "foreign":
        value["comparisons"][0]["right_finding_id"] = "f" * 64
    elif kind == "reversed":
        item = value["comparisons"][0]
        item["left_finding_id"], item["right_finding_id"] = (
            item["right_finding_id"],
            item["left_finding_id"],
        )
    else:
        value["comparisons"][0]["right_finding_id"] = LEFT[1]
    with pytest.raises(ProviderError) as caught:
        validate_pair_output(value, LEFT, RIGHT)
    assert caught.value.code == "PROVIDER_MALFORMED_OUTPUT"


@pytest.mark.parametrize(
    "change",
    [
        {"reason": " "},
        {"reason": "x" * 601},
        {"reason": "bad\x00reason"},
        {"relationship": "resolved"},
        {"relationship": []},
        {"left_finding_id": str(uuid.uuid4())},
        {"right_finding_id": "G" * 64},
        {"left_finding_id": []},
        {"review_state": "approved"},
        {"merged_finding_id": "e" * 64},
        {"speaker_verified": True},
        {"confidence": 1},
        {"concern_quotes": []},
    ],
)
def test_unverified_interpretation_cannot_add_review_quote_or_speaker_authority(change):
    value = matrix(LEFT[:1], RIGHT[:1])
    value["comparisons"][0].update(change)
    with pytest.raises(ProviderError):
        validate_output(value)


@pytest.mark.parametrize(
    "left,right",
    [
        ([], RIGHT),
        (LEFT, []),
        (LEFT + ["a" * 64], RIGHT),
        ([LEFT[0], LEFT[0]], RIGHT),
        (LEFT, LEFT),
        (tuple(LEFT), RIGHT),
    ],
)
def test_selection_must_be_bounded_unique_and_disjoint(left, right):
    with pytest.raises(ProviderError):
        validate_pair_output(matrix(), left, right)


def test_empty_or_extra_result_fields_cannot_imply_whole_run_absence():
    for value in (
        {"comparisons": []},
        {"comparisons": matrix()["comparisons"], "no_objections": True},
    ):
        with pytest.raises(ProviderError):
            validate_output(value)


def request():
    runs = (str(uuid.uuid4()), str(uuid.uuid4()))
    revisions = (str(uuid.uuid4()), str(uuid.uuid4()))
    summary = {
        side: {
            "session_id": runs[index],
            "source_revision_id": revisions[index],
            "candidates": [
                {
                    "finding_id": ids[0],
                    "concern_quotes": [{"utterance_id": str(uuid.uuid4()), "quote": quote}],
                    "answer_quotes": [],
                }
            ],
        }
        for index, (side, ids, quote) in enumerate(
            (
                ("left", LEFT, "Who owns pilot approval?"),
                ("right", RIGHT, "Which team decides whether the pilot proceeds?"),
            )
        )
    }
    return ReasoningRequest(
        task_type=TASK_TYPE,
        question="Compare only these selected concerns from distinct recorded Runs.",
        user_input=None,
        current_slide_summary=json.dumps(summary),
        evidence=(),
        preferred_user_explanations=(),
        speaker_evidence=(),
        style_context={},
        conflict_metadata=(),
        style_policy="preserve_voice",
        privacy_mode="local_only",
        output_schema=output_schema(),
        latency_budget_ms=30000,
        application_policy=APPLICATION_POLICY,
        task_instruction=TASK_INSTRUCTION,
        source_ids=(str(uuid.uuid4()),),
        presentation_revision_ids=revisions,
        rehearsal_session_ids=runs,
        rehearsal_finding_ids=tuple(LEFT[:1] + RIGHT[:1]),
    )


def test_registry_capabilities_and_manifest_retain_both_runs_without_recorded_text():
    req = request()
    assert task_instruction_for(TASK_TYPE) == TASK_INSTRUCTION
    assert output_schema_for(TASK_TYPE) == req.output_schema
    assert validate_provider_output(TASK_TYPE, matrix()) == matrix()
    for adapter in (
        OpenAIReasoningProvider(),
        LocalReasoningProvider(),
        CodexReasoningProvider(),
        DeterministicFakeReasoningProvider(),
    ):
        assert TASK_TYPE in adapter.capabilities().task_types
    manifest = derive_context_manifest(req, provider_id="fixture")
    assert manifest["rehearsal_session_ids"] == sorted(req.rehearsal_session_ids)
    assert manifest["presentation_revision_ids"] == sorted(req.presentation_revision_ids)
    assert manifest["rehearsal_finding_ids"] == sorted(req.rehearsal_finding_ids)
    assert set(manifest["classes_sent"]) <= TASK_CONTEXT_CLASS_ALLOWLIST[TASK_TYPE]
    assert "Who owns" not in json.dumps(manifest)
    assert "Which team" not in json.dumps(manifest)
    result = (
        DeterministicFakeReasoningProvider()
        .generate(ProviderInvocation(req, req.serialized_input()))
        .output
    )
    assert result["comparisons"][0]["relationship"] == "unclear"
    validate_pair_output(result, LEFT[:1], RIGHT[:1])


def test_openai_transport_uses_strict_schema_no_tools_or_storage():
    calls = []
    value = matrix(LEFT[:1], RIGHT[:1])

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(value), usage=None)

    provider = OpenAIReasoningProvider(
        api_key="fixture-only",
        client_factory=lambda **_: SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    req = request()
    invocation = ProviderInvocation(req, req.serialized_input())
    validate_pair_output(provider.generate(invocation).output, LEFT[:1], RIGHT[:1])
    assert calls[0]["tools"] == [] and calls[0]["store"] is False
    assert calls[0]["text"]["format"]["schema"] == output_schema()
    assert calls[0]["text"]["format"]["name"] == TASK_TYPE
    value["comparisons"][0]["merged_finding_id"] = "a" * 64
    with pytest.raises(ProviderError):
        provider.generate(invocation)


def test_local_transport_preserves_both_original_inputs_and_matrix_budget(server):
    server["body"] = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(matrix(LEFT[:1], RIGHT[:1]))},
                }
            ]
        }
    ).encode()
    provider = LocalReasoningProvider(endpoint=server["endpoint"], model_id="fixture")
    req = request()
    try:
        result = provider.generate(ProviderInvocation(req, req.serialized_input())).output
        validate_pair_output(result, LEFT[:1], RIGHT[:1])
        body = server["calls"][0][2]
        assert body["max_tokens"] == 8192
        assert body["messages"][1]["content"] == req.serialized_input()
        assert body["response_format"]["json_schema"]["schema"] == output_schema()
    finally:
        provider.close()
