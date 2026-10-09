"""Coverage adapters use one contract; quoted speech never gains semantic authority."""

import copy
import json
import uuid
from types import SimpleNamespace

import pytest
import test_local_provider as local_tests

from presenter_core.presentation.rehearsal_semantic_context import coverage_request
from presenter_core.providers.codex import CodexReasoningProvider
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.providers.local import LocalReasoningProvider
from presenter_core.providers.models import (
    TASK_CONTEXT_CLASS_ALLOWLIST,
    ProviderError,
    ProviderInvocation,
    derive_context_manifest,
    output_schema_for,
    task_instruction_for,
    validate_provider_output,
)
from presenter_core.providers.openai import OpenAIReasoningProvider
from presenter_core.providers.rehearsal_coverage_schema import (
    TASK_INSTRUCTION,
    TASK_TYPE,
    output_schema,
    validate_window_output,
)

server = local_tests.server
UTTERANCE = str(uuid.uuid4())
SPEECH = [{"utterance_id": UTTERANCE, "text": "We reduced costs by twenty percent. Next quarter."}]


def request():
    return coverage_request(
        {
            "document_id": str(uuid.uuid4()),
            "source_revision_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
        },
        {"quote": "Costs decreased 20%."},
        SPEECH,
        "local_only",
    )


def hint(status="addressed"):
    return {
        "status": status,
        "reason": "Review this paraphrase; it remains unverified.",
        "quotes": [{"utterance_id": UTTERANCE, "quote": "reduced costs by twenty percent"}],
    }


@pytest.mark.parametrize("status", ["addressed", "partially_addressed", "not_observed", "unclear"])
def test_exact_paraphrase_support_is_a_hint_only(status):
    value = hint(status)
    result = validate_window_output(value, SPEECH)
    assert result == value and result is not value and result["quotes"] is not value["quotes"]
    assert set(result) == {"status", "reason", "quotes"}


@pytest.mark.parametrize(
    "change",
    [
        {"status": "omitted"},
        {"status": None},
        {"status": []},
        {"reason": " "},
        {"reason": "x" * 601},
        {"reason": "a\x00b"},
        {"reason": 5},
        {"confidence": 1},
        {"quotes": None},
        {"quotes": []},
        {"quotes": [{"utterance_id": UTTERANCE, "quote": "invented speech"}]},
        {"quotes": [{"utterance_id": str(uuid.uuid4()), "quote": "Next quarter"}]},
        {"quotes": [{"utterance_id": UTTERANCE, "quote": " "}]},
        {"quotes": [{"utterance_id": UTTERANCE, "quote": "x" * 4001}]},
        {"quotes": [{"utterance_id": UTTERANCE, "quote": "Next quarter", "confidence": 1}]},
        {"quotes": [{"utterance_id": UTTERANCE, "quote": "Next quarter"}] * 5},
        {"quotes": [{"utterance_id": UTTERANCE, "quote": "Next quarter"}] * 2},
        {
            "quotes": [
                {"utterance_id": UTTERANCE, "quote": "reduced costs"},
                {"utterance_id": UTTERANCE, "quote": "costs by twenty"},
            ]
        },
    ],
)
def test_malformed_or_unbound_hints_fail(change):
    value = hint() | change
    with pytest.raises(ProviderError) as error:
        validate_window_output(value, SPEECH)
    assert error.value.code == "PROVIDER_MALFORMED_OUTPUT"


@pytest.mark.parametrize("text,quote", [("cost costs", "cost"), ("aaa", "aa")])
def test_repeated_and_overlapping_spans_are_ambiguous(text, quote):
    value = hint()
    value["quotes"][0]["quote"] = quote
    with pytest.raises(ProviderError):
        validate_window_output(value, [{"utterance_id": UTTERANCE, "text": text}])


def test_two_nonoverlapping_excerpts_and_absence_scope():
    value = hint()
    value["quotes"].append({"utterance_id": UTTERANCE, "quote": "Next quarter"})
    assert validate_window_output(value, SPEECH) == value
    for status in ("not_observed", "unclear"):
        value = {"status": status, "reason": "No support observed in this window.", "quotes": []}
        assert validate_window_output(value, SPEECH) == value
    with pytest.raises(ProviderError):
        validate_window_output(hint(), [])


def test_shared_schema_dispatch_manifest_and_no_alias():
    req = request()
    assert task_instruction_for(TASK_TYPE) == TASK_INSTRUCTION
    assert output_schema_for(TASK_TYPE) == req.output_schema == output_schema()
    changed = output_schema()
    changed["properties"]["status"]["enum"].clear()
    assert len(output_schema()["properties"]["status"]["enum"]) == 4
    assert validate_provider_output(TASK_TYPE, hint()) == hint()
    manifest = derive_context_manifest(req, provider_id="fixture")
    assert set(manifest["classes_sent"]) <= TASK_CONTEXT_CLASS_ALLOWLIST[TASK_TYPE]
    assert manifest["presentation_revision_ids"] == list(req.presentation_revision_ids)
    assert manifest["rehearsal_session_ids"] == list(req.rehearsal_session_ids)
    assert SPEECH[0]["text"] not in json.dumps(manifest)


def test_all_adapter_capabilities_and_fake_abstention():
    providers = [
        OpenAIReasoningProvider(),
        LocalReasoningProvider(),
        CodexReasoningProvider(),
        DeterministicFakeReasoningProvider(),
    ]
    for provider in providers:
        assert TASK_TYPE in provider.capabilities().task_types
    req = request()
    fake = providers[-1]
    output = fake.generate(ProviderInvocation(req, req.serialized_input())).output
    assert output["status"] == "unclear" and not output["quotes"]
    assert validate_window_output(output, SPEECH) == output


def test_openai_adapter_sends_shared_contract_and_validates_shape():
    calls = []
    value = hint()

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(value), usage=None)

    provider = OpenAIReasoningProvider(
        api_key="fixture-only",
        client_factory=lambda **_: SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    req = request()
    invocation = ProviderInvocation(req, req.serialized_input())
    assert provider.generate(invocation).output == hint()
    assert calls[0]["text"]["format"]["schema"] == output_schema()
    assert calls[0]["text"]["format"]["name"] == TASK_TYPE
    assert calls[0]["tools"] == [] and calls[0]["store"] is False
    value = copy.deepcopy(hint()) | {"status": "omitted"}
    with pytest.raises(ProviderError):
        provider.generate(invocation)


def test_local_transport_contract_and_reply(server):
    server["body"] = json.dumps(
        {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(hint())}}]}
    ).encode()
    provider = LocalReasoningProvider(endpoint=server["endpoint"], model_id="fixture")
    req = request()
    try:
        output = provider.generate(ProviderInvocation(req, req.serialized_input())).output
        assert validate_window_output(output, SPEECH) == hint()
        body = server["calls"][0][2]
        assert body["max_tokens"] == 4096
        assert body["response_format"]["json_schema"]["schema"] == output_schema()
        assert body["messages"][1]["content"] == req.serialized_input()
    finally:
        provider.close()
