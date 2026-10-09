"""User-reviewed presentation decisions behind the Core privacy boundary."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from presenter_core.credentials import (
    CredentialStore,
    CredentialStoreUnavailable,
    openrouter_credential_source,
    resolve_openrouter_credential,
)
from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.workspace_source import PresentationWorkspaceSourceService
from presenter_core.project.service import utc_now
from presenter_core.providers.service import ProviderService
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

from .jev import DEFAULT_JEV_MODEL
from .models import (
    ChoiceAnswer,
    ChoiceDecisionRequest,
    ChoiceDecisionResult,
    ChoiceQuestion,
    DecisionError,
    DecisionProvider,
)
from .ollama import (
    DEFAULT_OLLAMA_MODEL,
    OLLAMA_MODEL_IDS,
    OLLAMA_MODEL_OPTIONS,
)
from .openai_decisions import DEFAULT_OPENAI_DECISIONS_MODEL
from .openai_fast import DEFAULT_OPENAI_ULTRAFAST_DECISION_MODEL
from .purpose import SLIDE_PURPOSE_CHOICES, SLIDE_PURPOSE_QUESTION_INSTRUCTIONS

TASK_TYPE = "presentation_slide_purpose"
_SETTING_KEY = "presenter_copilot.decision_provider.v1"
_OLLAMA_MODEL_SETTING_KEY = "presenter_copilot.ollama_decision_model.v1"
_CHATGPT_PLAN_MODEL_SETTING_KEY = "presenter_copilot.chatgpt_plan_decision_model.v1"
_PROVIDER_IDS = frozenset(
    {
        "local_choice",
        "openai_fast",
        "openai_ultrafast",
        "openai_decisions",
        "openrouter_jev",
        "ollama_systemone",
        "openai_chatgpt_plan",
    }
)
_SAFE_ERROR_CODE = re.compile(r"^[A-Z0-9_]{1,80}$")
_OLLAMA_RESOLVED_MODEL_ID = re.compile(
    rf"^(?:{'|'.join(re.escape(model_id) for model_id in sorted(OLLAMA_MODEL_IDS))})"
    r"@sha256:[0-9a-f]{64}$"
)
_MAX_SLIDE_TEXT_CHARS = 12_000


class DecisionWorkflowService:
    """Expose one typed suggestion workflow; results never mutate presentation data."""

    def __init__(
        self,
        storage: StorageManager,
        workspace_sources: PresentationWorkspaceSourceService,
        providers: ProviderService,
        openrouter_credential_store: CredentialStore,
        *,
        injected_provider: DecisionProvider | None = None,
    ) -> None:
        self._storage = storage
        self._workspace_sources = workspace_sources
        self._providers = providers
        self._openrouter_credential_store = openrouter_credential_store
        self._injected_provider = injected_provider

    def status(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        selected = self._selected_provider_id()
        reasoners = {
            item["provider_id"]: item
            for item in self._providers.list({}).get("providers", [])
            if isinstance(item, dict) and isinstance(item.get("provider_id"), str)
        }
        local = reasoners.get("local_openai", {})
        openai = reasoners.get("openai", {})
        try:
            openrouter_configured = bool(
                resolve_openrouter_credential(self._openrouter_credential_store)
            )
            openrouter_source = openrouter_credential_source(self._openrouter_credential_store)
        except Exception:
            openrouter_configured = False
            openrouter_source = "unavailable"
        try:
            openai_configured = bool(
                self._providers.credentials_status({"provider_id": "openai"})["configured"]
            )
        except Exception:
            openai_configured = False
        try:
            chatgpt_plan_signed_in = (
                self._providers.chatgpt_plan_status().get("state") == "signed_in"
            )
        except Exception:
            chatgpt_plan_signed_in = False

        providers = [
            {
                "provider_id": "local_choice",
                "label": "Local structured output",
                "model_id": local.get("model_id", ""),
                "configured": bool(local.get("health", {}).get("configured")),
                "leaves_machine": bool(local.get("safe_config", {}).get("leaves_machine", True)),
            },
            {
                "provider_id": "openai_fast",
                "label": "OpenAI Responses · Fast",
                "model_id": openai.get("model_id", ""),
                "configured": openai_configured,
                "leaves_machine": True,
            },
            {
                "provider_id": "openai_ultrafast",
                "label": "OpenAI Responses · Ultrafast",
                "model_id": DEFAULT_OPENAI_ULTRAFAST_DECISION_MODEL,
                "configured": openai_configured,
                "leaves_machine": True,
            },
            {
                "provider_id": "openai_decisions",
                "label": "OpenAI Decisions · Beta",
                "model_id": DEFAULT_OPENAI_DECISIONS_MODEL,
                "configured": openai_configured,
                "leaves_machine": True,
            },
            {
                "provider_id": "openrouter_jev",
                "label": "Jev · OpenRouter System One",
                "model_id": DEFAULT_JEV_MODEL,
                "configured": openrouter_configured,
                "credential_source": openrouter_source,
                "leaves_machine": True,
            },
            {
                "provider_id": "ollama_systemone",
                "label": "Ollama · Jev-compatible System One",
                "model_id": self._selected_ollama_model_id(),
                "model_options": [
                    {"model_id": model_id, "label": label}
                    for model_id, label in OLLAMA_MODEL_OPTIONS
                ],
                "configured": True,
                "leaves_machine": False,
            },
            {
                "provider_id": "openai_chatgpt_plan",
                "label": "ChatGPT plan usage · Preview",
                "model_id": self._selected_chatgpt_plan_model_id(),
                "configured": chatgpt_plan_signed_in,
                "leaves_machine": True,
            },
        ]
        if self._injected_provider is not None:
            providers = [
                {
                    "provider_id": self._injected_provider.id,
                    "label": "Test decision provider",
                    "model_id": self._injected_provider.model_id,
                    "configured": True,
                    "leaves_machine": self._injected_provider.leaves_machine,
                }
            ]
            selected = self._injected_provider.id
        return {
            "selected_provider_id": selected,
            "ollama_model_id": self._selected_ollama_model_id(),
            "chatgpt_plan_model_id": self._selected_chatgpt_plan_model_id(),
            "providers": providers,
        }

    def configure(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"provider_id", "model_id"})
        provider_id = params.get("provider_id")
        if not isinstance(provider_id, str) or (
            provider_id != "disabled" and provider_id not in _PROVIDER_IDS
        ):
            raise invalid_request("The decision provider is not supported.", field="provider_id")
        requested_model_id = params.get("model_id")
        if provider_id == "ollama_systemone":
            model_id = (
                requested_model_id
                if requested_model_id is not None
                else self._selected_ollama_model_id()
            )
            if not isinstance(model_id, str) or model_id not in OLLAMA_MODEL_IDS:
                raise invalid_request(
                    "The Ollama decision model is not supported.", field="model_id"
                )
        elif provider_id == "openai_chatgpt_plan":
            model_id = (
                requested_model_id
                if requested_model_id is not None
                else self._selected_chatgpt_plan_model_id()
            )
            if not isinstance(model_id, str) or not model_id:
                raise invalid_request(
                    "Select a model from the signed-in ChatGPT account.", field="model_id"
                )
            model_options = self._providers.chatgpt_plan_models()
            if not any(item.get("model_id") == model_id for item in model_options):
                raise invalid_request(
                    "The selected model is not available for the active ChatGPT account.",
                    field="model_id",
                )
        else:
            if requested_model_id is not None:
                raise invalid_request(
                    "model_id is only supported for Ollama and ChatGPT plan decisions.",
                    field="model_id",
                )
            model_id = None
        with self._storage.app_database() as connection:
            connection.execute(
                """
                INSERT INTO app_metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (_SETTING_KEY, str(provider_id)),
            )
            if model_id is not None:
                setting_key = (
                    _OLLAMA_MODEL_SETTING_KEY
                    if provider_id == "ollama_systemone"
                    else _CHATGPT_PLAN_MODEL_SETTING_KEY
                )
                connection.execute(
                    """
                    INSERT INTO app_metadata (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (setting_key, model_id),
                )
            connection.commit()
        return self.status({})

    def credentials_status(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        try:
            return {
                "provider_id": "openrouter_jev",
                "configured": bool(
                    resolve_openrouter_credential(self._openrouter_credential_store)
                ),
                "credential_source": openrouter_credential_source(
                    self._openrouter_credential_store
                ),
                "secure_store_available": self._openrouter_credential_store.is_available(),
                "environment_detected": bool(os.environ.get("OPENROUTER_API_KEY")),
            }
        except CredentialStoreUnavailable as error:
            raise CoreDomainError(
                "DECISION_CREDENTIAL_STORE_UNAVAILABLE",
                "The secure OpenRouter credential store could not be read.",
                retryable=True,
            ) from error

    def save_detected_credential(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        detected = os.environ.get("OPENROUTER_API_KEY")
        if not detected:
            return {"provider_id": "openrouter_jev", "saved": False, "detected": False}
        if not self._openrouter_credential_store.is_available():
            return {
                "provider_id": "openrouter_jev",
                "saved": False,
                "detected": True,
                "secure_store_available": False,
            }
        try:
            self._openrouter_credential_store.write(detected)
            stored = self._openrouter_credential_store.read()
        except Exception as error:
            raise CoreDomainError(
                "DECISION_CREDENTIAL_STORE_UNAVAILABLE",
                "The OpenRouter credential could not be saved securely.",
                retryable=True,
            ) from error
        if stored != detected:
            raise CoreDomainError(
                "DECISION_CREDENTIAL_STORE_UNAVAILABLE",
                "The OpenRouter credential could not be verified after saving.",
                retryable=True,
            )
        return {
            "provider_id": "openrouter_jev",
            "saved": True,
            "detected": True,
            "credential_source": openrouter_credential_source(self._openrouter_credential_store),
        }

    def remove_stored_credential(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        try:
            removed = self._openrouter_credential_store.delete()
            if self._openrouter_credential_store.read():
                raise CoreDomainError(
                    "DECISION_CREDENTIAL_STORE_UNAVAILABLE",
                    "The stored OpenRouter credential could not be removed and verified.",
                    retryable=True,
                )
        except CoreDomainError:
            raise
        except Exception as error:
            raise CoreDomainError(
                "DECISION_CREDENTIAL_STORE_UNAVAILABLE",
                "The stored OpenRouter credential could not be removed and verified.",
                retryable=True,
            ) from error
        return {
            "provider_id": "openrouter_jev",
            "credentials_removed": removed,
            "credential_source": openrouter_credential_source(self._openrouter_credential_store),
        }

    def classify_slide(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "document_id", "revision_id", "slide_number"},
        )
        project_id_value = params.get("project_id")
        if not isinstance(project_id_value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        project_id = normalize_project_id(project_id_value)
        document_id = self._normalize_uuid(params.get("document_id"), "document_id")
        revision_id = self._normalize_uuid(params.get("revision_id"), "revision_id")
        slide_number = params.get("slide_number")
        if (
            isinstance(slide_number, bool)
            or not isinstance(slide_number, int)
            or not 1 <= slide_number <= 5_000
        ):
            raise invalid_request("slide_number must be between 1 and 5000.", field="slide_number")

        selection = self._workspace_sources.list_text_targets(
            {
                "project_id": project_id,
                "document_id": document_id,
                "revision_id": revision_id,
                "slide_number": slide_number,
            }
        )
        if selection["revision_id"] != revision_id or selection["ordinal"] != slide_number:
            raise CoreDomainError(
                "PRESENTATION_REVISION_CONFLICT",
                "The current presentation revision changed. Refresh and try again.",
                retryable=True,
            )
        if selection["has_more"]:
            raise CoreDomainError(
                "DECISION_CONTEXT_TOO_LARGE",
                "This slide has too many text objects for one bounded decision.",
            )
        targets = selection["targets"]
        slide_text: list[str] = []
        for target in targets:
            text = target.get("decision_text")
            if text is None:
                if target.get("current_text") is not None:
                    raise CoreDomainError(
                        "DECISION_CONTEXT_TOO_LARGE",
                        "This slide contains text outside the decision size limit.",
                    )
                continue
            if not isinstance(text, str):
                raise CoreDomainError(
                    "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                    "The selected slide text could not be verified.",
                )
            if text.strip():
                slide_text.append(text)
        if not slide_text:
            raise CoreDomainError(
                "DECISION_CONTEXT_UNAVAILABLE",
                "This slide does not contain supported text to classify.",
            )
        if sum(len(text) for text in slide_text) > _MAX_SLIDE_TEXT_CHARS:
            raise CoreDomainError(
                "DECISION_CONTEXT_TOO_LARGE",
                "This slide contains too much text for one bounded decision.",
            )

        request = ChoiceDecisionRequest(
            state={"slide_text": slide_text},
            questions=(
                ChoiceQuestion(
                    name="purpose",
                    instructions=SLIDE_PURPOSE_QUESTION_INSTRUCTIONS,
                    criteria=SLIDE_PURPOSE_CHOICES,
                ),
            ),
        )
        result, answer, run_id = self._run_choice(
            project_id,
            revision_id,
            request,
            question="purpose",
            choices=SLIDE_PURPOSE_CHOICES,
            task_type=TASK_TYPE,
            boundary="selected_slide_text",
            classes=["presentation_text"],
            source_ids=[document_id],
            extra_manifest={},
            precondition=lambda: self._ensure_current_revision(
                project_id, document_id, revision_id
            ),
        )
        return {
            "provider_run_id": run_id,
            "revision_id": revision_id,
            "slide_id": selection["slide_id"],
            "slide_number": slide_number,
            "purpose": answer.choice,
            "confidence": answer.confidence,
            "probabilities": dict(answer.probabilities) if answer.probabilities else None,
            "provider_id": result.provider_id,
            "model_id": result.model_id,
            "latency_ms": result.latency_ms,
            "requires_user_review": True,
        }

    def triage_claim_evidence(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "revision_id",
                "slide_number",
                "slide_id",
                "object_id",
                "quote",
                "chunk_id",
                "expected_sha256",
            },
        )
        from presenter_core.presentation.claims import PresentationClaimService, digest
        from presenter_core.presentation.semantics import PresentationSemanticService

        from .triage import CLAIM_RELATIONS, reviewed_suggestion, triage_request

        claims = PresentationClaimService(
            PresentationSemanticService(self._storage, self._workspace_sources)
        )
        quote = params.get("quote")
        if not isinstance(quote, str) or not 1 <= len(quote) <= 2000 or not quote.strip():
            raise invalid_request("Choose an exact claim quote of 1-2000 characters.")

        def pair() -> tuple[str, str, str, dict[str, Any], Any, str, str]:
            project, document, revision, selection = claims._selection(params)
            target = next(
                (
                    t
                    for t in selection["semantic_targets"]
                    if t["object_id"] == params.get("object_id")
                ),
                None,
            )
            text = target.get("decision_text") if target else None
            if (
                not isinstance(text, str)
                or text.find(quote) < 0
                or text.find(quote, text.find(quote) + 1) >= 0
            ):
                raise invalid_request(
                    "Choose a unique exact quote from a current slide text object."
                )
            chunk = params.get("chunk_id")
            if not isinstance(chunk, str):
                raise invalid_request("Choose a current source excerpt.")
            with self._storage.project_database(project) as connection:
                source = claims._evidence(connection, project, chunk)
            if (
                source is None
                or len(source["text"]) > 8000
                or digest(source["text"]) != params.get("expected_sha256")
            ):
                raise CoreDomainError(
                    "CLAIM_EVIDENCE_CHANGED",
                    "The selected source excerpt changed or is unavailable. Search again.",
                    retryable=True,
                )
            return (
                project,
                document,
                revision,
                selection,
                source,
                digest(text),
                target["source_kind"] if target else "native_text",
            )

        project, document, revision, selection, source, object_sha, source_kind = pair()
        request = triage_request(quote, source["text"], source_kind)

        def precondition() -> None:
            current = pair()
            if current[-2] != object_sha or current[-1] != source_kind:
                raise CoreDomainError(
                    "PRESENTATION_REVISION_CONFLICT",
                    "The claim object changed. Refresh and retry.",
                    retryable=True,
                )

        result, answer, run_id = self._run_choice(
            project,
            revision,
            request,
            question="relation",
            choices=CLAIM_RELATIONS,
            task_type="presentation_claim_evidence_triage",
            boundary="selected_claim_and_excerpt",
            classes=["claim_quote", "document_excerpt"],
            source_ids=[document, source["document_id"]],
            extra_manifest={
                "claim_object_id": params["object_id"],
                "claim_source_kind": source_kind,
                "claim_quote_sha256": digest(quote),
                "selected_excerpt_id": source["id"],
                "selected_excerpt_sha256": digest(source["text"]),
            },
            precondition=precondition,
        )
        return {
            **reviewed_suggestion(answer),
            "provider_run_id": run_id,
            "revision_id": revision,
            "slide_id": selection["slide_id"],
            "object_id": params["object_id"],
            "source_kind": source_kind,
            "chunk_id": source["id"],
            "excerpt_sha256": digest(source["text"]),
            "provider_id": result.provider_id,
            "model_id": result.model_id,
            "latency_ms": result.latency_ms,
        }

    def _run_choice(
        self,
        project_id: str,
        revision_id: str,
        request: ChoiceDecisionRequest,
        *,
        question: str,
        choices: Mapping[str, str],
        task_type: str,
        boundary: str,
        classes: list[str],
        source_ids: list[str],
        extra_manifest: dict[str, Any],
        precondition: Callable[[], None],
    ) -> tuple[ChoiceDecisionResult, ChoiceAnswer, str]:
        provider = self._selected_provider()
        initial_mode, initial_ack = self._project_authority(project_id)
        self._validate_authority(provider, initial_mode, initial_ack)
        serialized_input = request.serialized_request()
        manifest = {
            "provider_content_boundary": boundary,
            "provider_id": provider.id,
            "task_type": task_type,
            "privacy_mode": initial_mode,
            "classes_sent": classes,
            "source_ids": source_ids,
            "presentation_revision_ids": [revision_id],
            "knowledge_item_ids": [],
            "speaker_evidence_ids": [],
            "audience_profile_ids": [],
            "audience_observation_ids": [],
            "raw_audio_sent": False,
            "full_document_sent": False,
            "full_corpus_sent": False,
            "private_items_sent": False,
            "prior_question_count": 0,
            "bounded_context_chars": len(serialized_input),
        }
        manifest.update(extra_manifest)
        run_id = self._start_run(project_id, provider.id, initial_mode, manifest)
        try:
            current_mode, current_ack = self._project_authority(project_id)
            if current_mode != initial_mode or current_ack != initial_ack:
                raise CoreDomainError(
                    "PRIVACY_POLICY_CHANGED",
                    "Project privacy changed while preparing the decision; retry.",
                    retryable=True,
                )
            self._validate_authority(provider, current_mode, current_ack)
            precondition()
            result = provider.decide(request)
            precondition()
            final_mode, final_ack = self._project_authority(project_id)
            if final_mode != initial_mode or final_ack != initial_ack:
                raise CoreDomainError(
                    "PRIVACY_POLICY_CHANGED",
                    "Project privacy changed during the decision; review the current deck "
                    "and retry.",
                    retryable=True,
                )
            answer = self._validate_answer(
                result, expected_provider_id=provider.id, question_name=question, choices=choices
            )
            if provider.id == "ollama_systemone":
                if not _OLLAMA_RESOLVED_MODEL_ID.fullmatch(result.model_id):
                    raise DecisionError(
                        "DECISION_PROVIDER_MALFORMED_OUTPUT",
                        "Ollama did not return a verifiable model identity.",
                    )
                manifest["resolved_model_id"] = result.model_id
        except CoreDomainError as error:
            self._finish_run(
                project_id,
                run_id,
                task_type=task_type,
                status="error",
                error_code=error.code,
            )
            raise
        except Exception as error:
            self._finish_run(
                project_id,
                run_id,
                task_type=task_type,
                status="error",
                error_code="DECISION_PROVIDER_REQUEST_FAILED",
            )
            raise CoreDomainError(
                "DECISION_PROVIDER_REQUEST_FAILED",
                "The decision provider could not complete this request.",
                retryable=True,
            ) from error

        self._finish_run(
            project_id,
            run_id,
            task_type=task_type,
            status="success",
            latency_ms=result.latency_ms,
            manifest=manifest,
        )
        return result, answer, run_id

    def close(self) -> None:
        if self._injected_provider is not None:
            self._injected_provider.close()

    def _selected_provider_id(self) -> str:
        if self._injected_provider is not None:
            return self._injected_provider.id
        with self._storage.app_database() as connection:
            row = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?",
                (_SETTING_KEY,),
            ).fetchone()
        if row is None or row["value"] == "disabled":
            return "disabled"
        value = str(row["value"])
        return value if value in _PROVIDER_IDS else "disabled"

    def _selected_provider(self) -> DecisionProvider:
        if self._injected_provider is not None:
            return self._injected_provider
        provider_id = self._selected_provider_id()
        if provider_id == "disabled":
            raise CoreDomainError(
                "DECISION_PROVIDER_NOT_SELECTED",
                "Select a typed decision provider before classifying a slide.",
            )
        if provider_id == "ollama_systemone":
            provider = self._providers.decision_provider(
                provider_id,
                model_id=self._selected_ollama_model_id(),
            )
        elif provider_id == "openai_chatgpt_plan":
            model_id = self._selected_chatgpt_plan_model_id()
            model_options = self._providers.chatgpt_plan_models()
            if not model_id or not any(item.get("model_id") == model_id for item in model_options):
                raise DecisionError(
                    "DECISION_PROVIDER_UNCONFIGURED",
                    "Select a model currently available to the active ChatGPT account.",
                )
            provider = self._providers.decision_provider(provider_id, model_id=model_id)
        else:
            provider = self._providers.decision_provider(provider_id)
        if provider_id == "local_choice" and not provider.model_id:
            raise DecisionError(
                "DECISION_PROVIDER_UNCONFIGURED",
                "Configure a local reasoning model before requesting a slide decision.",
            )
        return provider

    def _selected_ollama_model_id(self) -> str:
        with self._storage.app_database() as connection:
            row = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?",
                (_OLLAMA_MODEL_SETTING_KEY,),
            ).fetchone()
        if row is None or not isinstance(row["value"], str):
            return DEFAULT_OLLAMA_MODEL
        value = str(row["value"])
        return value if value in OLLAMA_MODEL_IDS else DEFAULT_OLLAMA_MODEL

    def _selected_chatgpt_plan_model_id(self) -> str:
        with self._storage.app_database() as connection:
            row = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?",
                (_CHATGPT_PLAN_MODEL_SETTING_KEY,),
            ).fetchone()
        return str(row["value"]) if row is not None and isinstance(row["value"], str) else ""

    def _project_authority(self, project_id: str) -> tuple[str, bool]:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                "SELECT privacy_mode, remote_reasoning_acknowledged_at FROM project WHERE id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
        return str(row["privacy_mode"]), row["remote_reasoning_acknowledged_at"] is not None

    @staticmethod
    def _validate_authority(
        provider: DecisionProvider, privacy_mode: str, acknowledged: bool
    ) -> None:
        if provider.locality not in {"local", "remote"}:
            raise CoreDomainError(
                "DECISION_PROVIDER_UNAVAILABLE",
                "The selected decision provider has an unsupported location.",
                retryable=True,
            )
        if provider.leaves_machine and privacy_mode == "local_only":
            raise CoreDomainError(
                "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED",
                "Local Only blocks remote decision requests for this project.",
                details={"privacy_mode": privacy_mode, "provider_id": provider.id},
            )
        if provider.leaves_machine and not acknowledged:
            raise CoreDomainError(
                "PRIVACY_REMOTE_ACK_REQUIRED",
                "Explicit project acknowledgement is required before remote decisions.",
                details={"privacy_mode": privacy_mode},
            )

    def _ensure_current_revision(self, project_id: str, document_id: str, revision_id: str) -> None:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                """
                SELECT h.revision_id
                FROM documents d
                JOIN presentation_revision_heads h ON h.presentation_id = d.id
                WHERE d.id = ? AND d.project_id = ? AND d.kind = 'presentation'
                """,
                (document_id, project_id),
            ).fetchone()
        if row is None or str(row["revision_id"]) != revision_id:
            raise CoreDomainError(
                "PRESENTATION_REVISION_CONFLICT",
                "The selected presentation changed while the decision was running. "
                "Refresh and retry.",
                retryable=True,
            )

    def _start_run(
        self,
        project_id: str,
        provider_id: str,
        privacy_mode: str,
        manifest: dict[str, Any],
    ) -> str:
        run_id = str(uuid.uuid4())
        with self._storage.project_database(project_id) as connection:
            connection.execute(
                """
                INSERT INTO provider_runs (
                    id, session_id, task_type, provider_id, privacy_mode, started_at,
                    ended_at, status, input_token_count, output_token_count, latency_ms,
                    context_manifest_json, error_code
                ) VALUES (?, NULL, ?, ?, ?, ?, NULL, 'started', NULL, NULL, NULL, ?, NULL)
                """,
                (
                    run_id,
                    manifest["task_type"],
                    provider_id,
                    privacy_mode,
                    utc_now(),
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            connection.commit()
        return run_id

    def _finish_run(
        self,
        project_id: str,
        run_id: str,
        *,
        status: str,
        task_type: str,
        latency_ms: int | None = None,
        error_code: str | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        safe_error = (
            error_code
            if isinstance(error_code, str) and _SAFE_ERROR_CODE.fullmatch(error_code)
            else "DECISION_PROVIDER_REQUEST_FAILED"
            if error_code is not None
            else None
        )
        with self._storage.project_database(project_id) as connection:
            connection.execute(
                """
                UPDATE provider_runs
                SET ended_at = ?, status = ?, latency_ms = ?, error_code = ?,
                    context_manifest_json = COALESCE(?, context_manifest_json)
                WHERE id = ? AND task_type = ?
                """,
                (
                    utc_now(),
                    status,
                    latency_ms,
                    safe_error,
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
                    if manifest is not None
                    else None,
                    run_id,
                    task_type,
                ),
            )
            connection.commit()

    @staticmethod
    def _validate_answer(
        result: ChoiceDecisionResult,
        *,
        expected_provider_id: str,
        question_name: str = "purpose",
        choices: Mapping[str, str] = SLIDE_PURPOSE_CHOICES,
    ) -> ChoiceAnswer:
        if (
            not isinstance(result, ChoiceDecisionResult)
            or result.provider_id != expected_provider_id
            or set(result.answers) != {question_name}
        ):
            raise DecisionError(
                "DECISION_PROVIDER_MALFORMED_OUTPUT",
                "The decision provider returned an incomplete answer.",
            )
        answer = result.answers[question_name]
        if answer.choice not in choices or (
            answer.probabilities is not None and set(answer.probabilities).difference(choices)
        ):
            raise DecisionError(
                "DECISION_PROVIDER_MALFORMED_OUTPUT",
                "The decision provider returned an unsupported choice.",
            )
        return answer

    @staticmethod
    def _normalize_uuid(value: object, field: str) -> str:
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a UUID.", field=field) from error
