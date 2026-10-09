"""Bounded provider claim discovery; existing explicit review owns persistence."""

import json
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.claims import PresentationClaimService, digest
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.providers.context import (
    APPLICATION_POLICY,
    MAX_TOTAL_CONTEXT_CHARS,
    MAX_TRUSTED_CONTENT_OVERHEAD_CHARS,
)
from presenter_core.providers.execution import ProviderExecutionService
from presenter_core.providers.models import (
    ProviderError,
    ReasoningRequest,
    output_schema_for,
    task_instruction_for,
)
from presenter_core.providers.router import ReasoningRoute, ReasoningRouter
from presenter_core.providers.service import ProviderService

TASK_TYPE = "presentation_claim_extraction"


def claim_request(
    texts: dict[str, str],
    privacy: str,
    document: str,
    revision: str,
    source_kinds: dict[str, str] | None = None,
) -> ReasoningRequest:
    return ReasoningRequest(
        task_type=TASK_TYPE,
        question=(
            "Find substantive claim candidates in these selected native representations. "
            "native_text is slide wording; native_table_cells is row-major cell text; "
            "native_chart_cache is raw cached chart data, not displayed/formatted values "
            "or independently verified workbook data. Do not infer units or visual meaning."
        ),
        user_input=None,
        current_slide_summary=json.dumps(
            {
                "objects": [
                    {
                        "object_id": key,
                        "text": value,
                        "source_kind": (source_kinds or {}).get(key, "native_text"),
                    }
                    for key, value in texts.items()
                ]
            },
            ensure_ascii=False,
        ),
        evidence=(),
        preferred_user_explanations=(),
        speaker_evidence=(),
        style_context={},
        conflict_metadata=(),
        style_policy="preserve_voice",
        privacy_mode=privacy,
        output_schema=output_schema_for(TASK_TYPE),
        latency_budget_ms=30000,
        application_policy=APPLICATION_POLICY,
        task_instruction=task_instruction_for(TASK_TYPE),
        source_ids=(document,),
        presentation_revision_ids=(revision,),
    )


def claim_context_size(request: ReasoningRequest) -> int:
    return (
        len(request.serialized_input())
        + len(APPLICATION_POLICY)
        + len(request.task_instruction or "")
        + MAX_TRUSTED_CONTENT_OVERHEAD_CHARS
    )


class PresentationClaimExtractionService:
    def __init__(
        self,
        semantics: PresentationSemanticService,
        providers: ProviderService,
        execution: ProviderExecutionService,
    ) -> None:
        self._semantics, self._providers, self._execution = semantics, providers, execution
        self._claims = PresentationClaimService(semantics)

    def extract_claims(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "revision_id",
                "slide_id",
                "slide_number",
                "object_ids",
                "spans",
            },
        )
        ids = params.get("object_ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 8:
            raise invalid_request("Choose one to eight text objects for claim extraction.")
        ids = [self._semantics._uuid_field(item, "object_ids") for item in ids]
        if len(set(ids)) != len(ids):
            raise invalid_request("Choose distinct claim text objects.")
        spans = params.get("spans")
        windows: dict[str, dict[str, Any]] = {}
        if spans is not None:
            if not isinstance(spans, list) or len(spans) != len(ids):
                raise invalid_request("Provide one prepared text window per selected object.")
            for span in spans:
                if not isinstance(span, dict):
                    raise invalid_request("The prepared text window is invalid.")
                reject_unknown_fields(span, {"object_id", "start", "end", "sha256"})
                object_id = self._semantics._uuid_field(span.get("object_id"), "object_id")
                if object_id not in ids or object_id in windows:
                    raise invalid_request("Prepared windows must match distinct selected objects.")
                windows[object_id] = span
        scope = {key: params[key] for key in params if key not in {"object_ids", "spans"}}

        def selection() -> tuple[str, str, str, dict[str, Any], dict[str, str], dict[str, str]]:
            project, document, revision, inventory = self._claims._selection(scope)
            targets = {t["object_id"]: t for t in inventory["semantic_targets"]}
            texts: dict[str, str] = {}
            kinds: dict[str, str] = {}
            for object_id in ids:
                target = targets.get(object_id)
                text = target.get("decision_text") if target else None
                if not isinstance(text, str) or not text.strip():
                    raise invalid_request(
                        "Choose current text objects with one to 6000 characters."
                    )
                if windows:
                    span = windows[object_id]
                    start, end = span.get("start"), span.get("end")
                    if (
                        isinstance(start, bool)
                        or not isinstance(start, int)
                        or isinstance(end, bool)
                        or not isinstance(end, int)
                        or not 0 <= start < end <= len(text)
                        or end - start > 6000
                        or span.get("sha256") != digest(text)
                        or not text[start:end].strip()
                    ):
                        raise invalid_request(
                            "The prepared text window no longer matches this object."
                        )
                elif len(text) > 6000:
                    raise invalid_request("Choose text objects with at most 6000 characters.")
                texts[object_id] = text
                kinds[object_id] = target["source_kind"] if target else "native_text"
            selected = supplied_text(texts)
            if sum(map(len, selected.values())) > 6000:
                raise invalid_request(
                    "Choose fewer objects: extraction accepts 6000 text characters."
                )
            return project, document, revision, inventory, texts, kinds

        def supplied_text(texts: dict[str, str]) -> dict[str, str]:
            return {
                key: text[windows[key]["start"] : windows[key]["end"]] if windows else text
                for key, text in texts.items()
            }

        project, document, revision, inventory, texts, kinds = selection()
        storage = self._semantics._storage

        def policy() -> tuple[str, bool]:
            with storage.project_database(project) as connection:
                row = connection.execute(
                    "SELECT privacy_mode,remote_reasoning_acknowledged_at FROM project WHERE id=?",
                    (project,),
                ).fetchone()
            return str(row["privacy_mode"]), row["remote_reasoning_acknowledged_at"] is not None

        initial_policy = policy()
        provider, health = self._providers.current_provider_and_health()
        route = ReasoningRouter().decide(
            task_type=TASK_TYPE,
            privacy_mode=initial_policy[0],
            remote_acknowledged=initial_policy[1],
            provider=provider,
            provider_health=health,
        )
        if route.route == ReasoningRoute.RETRIEVAL_ONLY or provider is None:
            codes = {
                "local_only": "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED",
                "remote_reasoning_acknowledgement_required": "PRIVACY_REMOTE_ACK_REQUIRED",
                "provider_task_unsupported": "PROVIDER_TASK_UNSUPPORTED",
            }
            raise CoreDomainError(
                codes.get(route.reason, "PROVIDER_UNCONFIGURED"),
                "Configure an allowed, ready reasoning provider in Settings "
                "to find claim candidates.",
            )
        selected_texts = supplied_text(texts)
        request = claim_request(selected_texts, initial_policy[0], document, revision, kinds)
        if claim_context_size(request) > MAX_TOTAL_CONTEXT_CHARS:
            raise invalid_request("Choose fewer objects: escaped text exceeds the context budget.")

        def current() -> None:
            if policy() != initial_policy:
                raise CoreDomainError(
                    "PRIVACY_POLICY_CHANGED",
                    "Project privacy changed during claim extraction. Retry after review.",
                    retryable=True,
                )
            latest = selection()
            if latest[-2] != texts or latest[-1] != kinds:
                raise CoreDomainError(
                    "PRESENTATION_REVISION_CONFLICT",
                    "Claim text changed during extraction. Refresh and retry.",
                    retryable=True,
                )

        def validate(output: dict[str, Any]) -> dict[str, Any]:
            current()
            seen: set[tuple[str, str]] = set()
            for item in output["candidates"]:
                object_id, quote = item["object_id"], item["quote"]
                text = texts.get(object_id)
                pair = object_id, quote
                if (
                    text is None
                    or pair in seen
                    or quote not in selected_texts.get(object_id, "")
                    or text.find(quote) < 0
                    or text.find(quote, text.find(quote) + 1) >= 0
                ):
                    raise ProviderError(
                        "PROVIDER_MALFORMED_OUTPUT",
                        "A claim must quote a unique exact span in a supplied object.",
                    )
                seen.add(pair)
            return output

        result = self._execution.execute(
            project_id=project,
            session_id=None,
            provider=provider,
            request=request,
            before_provider=lambda _id, _manifest: current(),
            output_validator=validate,
        )
        current()
        return {
            **result.result.output,
            "document_id": document,
            "revision_id": revision,
            "slide_id": inventory["slide_id"],
            "object_ids": ids,
            "inventory_truncated": inventory["semantic_has_more"],
            "provider_run_id": result.provider_run_id,
            "provider_id": provider.id,
            "model_id": provider.model_id,
            "requires_user_review": True,
            "candidates": [
                {
                    **item,
                    "source_kind": kinds[item["object_id"]],
                    "object_sha256": digest(texts[item["object_id"]]),
                    "start": texts[item["object_id"]].index(item["quote"]),
                    "end": texts[item["object_id"]].index(item["quote"]) + len(item["quote"]),
                }
                for item in result.result.output["candidates"]
            ],
        }
