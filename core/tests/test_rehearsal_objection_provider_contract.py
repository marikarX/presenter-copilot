"""Every adapter sends the same objection contract with bounded disclosure classes."""

import json
import uuid
from types import SimpleNamespace

import pytest
import test_local_provider as local_tests
from test_rehearsal_objection_contract import SPEECH, observation

from presenter_core.presentation.rehearsal_objection_context import objection_request
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
from presenter_core.providers.rehearsal_objection_schema import (
    TASK_INSTRUCTION,
    TASK_TYPE,
    output_schema,
    validate_window_output,
)

server = local_tests.server


def request():
    return objection_request(
        {
            "document_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "source_revision_id": str(uuid.uuid4()),
        },
        SPEECH,
        "local_only",
    )


def hint():
    return {"observations": [observation()]}


def test_shared_dispatch_and_content_free_manifest_retain_original_run_and_source():
    req = request()
    assert task_instruction_for(TASK_TYPE) == TASK_INSTRUCTION
    assert output_schema_for(TASK_TYPE) == req.output_schema == output_schema()
    assert validate_provider_output(TASK_TYPE, hint()) == hint()
    manifest = derive_context_manifest(req, provider_id="fixture")
    assert set(manifest["classes_sent"]) <= TASK_CONTEXT_CLASS_ALLOWLIST[TASK_TYPE]
    assert manifest["source_ids"] == list(req.source_ids)
    assert manifest["presentation_revision_ids"] == list(req.presentation_revision_ids)
    assert manifest["rehearsal_session_ids"] == list(req.rehearsal_session_ids)
    assert all(u["text"] not in json.dumps(manifest) for u in SPEECH)
    assert req.evidence == req.speaker_evidence == ()


def test_adapter_capabilities_and_fixture_empty_result_do_not_manufacture_an_objection():
    for provider in (
        OpenAIReasoningProvider(),
        LocalReasoningProvider(),
        CodexReasoningProvider(),
        DeterministicFakeReasoningProvider(),
    ):
        assert TASK_TYPE in provider.capabilities().task_types
    req = request()
    fake = DeterministicFakeReasoningProvider()
    result = fake.generate(ProviderInvocation(req, req.serialized_input())).output
    assert validate_window_output(result, SPEECH) == {"observations": []}


def test_openai_transport_uses_contract_without_tools_or_storage_and_rejects_invalid_shape():
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
    value = {"observations": [observation() | {"confidence": 1}]}
    with pytest.raises(ProviderError):
        provider.generate(invocation)


def test_local_transport_sends_complete_recorded_text_and_shared_schema(server):
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
