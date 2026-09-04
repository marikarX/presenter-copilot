"""Deterministic test-only provider with bounded payload capture."""

from __future__ import annotations

from time import monotonic
from typing import Any

from .models import (
    CHALLENGE_INTENSITIES,
    ProviderCapabilities,
    ProviderError,
    ProviderHealth,
    ProviderInvocation,
    ReasoningProvider,
    ReasoningRequest,
    ReasoningResult,
    validate_provider_output,
)


class DeterministicFakeReasoningProvider(ReasoningProvider):
    """Offline provider used by CI and explicit developer acceptance flows."""

    id = "fake-test"

    def __init__(
        self,
        *,
        locality: str = "remote",
        failure_code: str | None = None,
        model_id: str = "fake-teach-v1",
    ) -> None:
        self.locality = locality
        self.model_id = model_id
        self.failure_code = failure_code
        self.requests: list[dict[str, Any]] = []
        self.request_objects: list[ReasoningRequest] = []
        self.call_count = 0

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            structured_outputs=True,
            streaming=False,
            cancellation=False,
            task_types=(
                "teach_question",
                "teach_candidate",
                "challenge_question",
                "challenge_follow_up",
                "challenge_evaluation",
                "live_cue",
            ),
        )

    def health(self) -> ProviderHealth:
        if self.failure_code == "PROVIDER_UNCONFIGURED":
            return ProviderHealth(
                provider_id=self.id,
                locality=self.locality,
                model_id=self.model_id,
                status="unconfigured",
                configured=False,
                error_code=self.failure_code,
            )
        return ProviderHealth(
            provider_id=self.id,
            locality=self.locality,
            model_id=self.model_id,
            status="ready",
            configured=True,
        )

    def generate(self, invocation: ProviderInvocation) -> ReasoningResult:
        request = invocation.request
        self.call_count += 1
        self.requests.append(invocation.to_payload())
        self.request_objects.append(request)
        if self.failure_code is not None:
            raise ProviderError(
                self.failure_code,
                "The deterministic reasoning provider was configured to fail.",
                retryable=self.failure_code
                in {"PROVIDER_TIMEOUT", "PROVIDER_RATE_LIMITED", "PROVIDER_UNAVAILABLE"},
            )
        started = monotonic()
        if request.task_type == "teach_question":
            evidence = request.evidence[0] if request.evidence else None
            if isinstance(evidence, dict) and isinstance(evidence.get("label"), str):
                question = (
                    f"What made the option described in {evidence['label']} a poor fit "
                    "for this project?"
                )
            else:
                question = "What decision or tradeoff behind this project should I remember?"
            output = validate_provider_output(
                request.task_type,
                {"question": question, "focus": "decision_rationale"},
            )
        elif request.task_type == "live_cue":
            grounding = (
                request.grounding_evidence
                or request.evidence
                or request.preferred_user_explanations
            )
            evidence = grounding[0] if grounding else None
            if isinstance(evidence, dict):
                label = str(evidence.get("label") or "Project source")
                excerpt = " ".join(str(evidence.get("text") or "").split())
                line = f"{label}: {excerpt}"[:180].rstrip()
                evidence_ids = [
                    str(item["evidence_id"])
                    for item in grounding[:2]
                    if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
                ]
            else:
                line = "Use the prepared project context to answer directly."
                evidence_ids = []
            output = validate_provider_output(
                request.task_type,
                {"cue_type": "fact", "lines": [line], "evidence_ids": evidence_ids},
            )
        elif request.task_type == "teach_candidate":
            answer = (request.user_input or "").strip()
            if not answer:
                raise ProviderError(
                    "PROVIDER_MALFORMED_OUTPUT",
                    "The deterministic provider needs a user explanation.",
                )
            lowered = answer.casefold()
            if "reject" in lowered or "rollback" in lowered or "cutover" in lowered:
                candidate_text = (
                    "We rejected it because it doubled the cutover surface and made rollback "
                    "harder."
                    if "doubled the cutover surface" in lowered
                    else answer
                )
            else:
                candidate_text = answer
            output = validate_provider_output(
                request.task_type,
                {
                    "kind": "rationale",
                    "text": candidate_text,
                    "follow_up_question": None,
                },
            )
        elif request.task_type in {"challenge_question", "challenge_follow_up"}:
            output = self._challenge_question(request)
        elif request.task_type == "challenge_evaluation":
            output = self._challenge_evaluation(request)
        else:
            raise ProviderError("PROVIDER_REQUEST_FAILED", "Unsupported fake provider task.")
        return ReasoningResult(
            output=output,
            input_token_count=None,
            output_token_count=None,
            latency_ms=max(0, int((monotonic() - started) * 1000)),
        )

    @staticmethod
    def _challenge_question(request: ReasoningRequest) -> dict[str, Any]:
        profile = request.audience_context[0] if request.audience_context else {}
        role = str(profile.get("role") or "audience member")
        role_lower = role.casefold()
        observation_text = " ".join(
            str(item.get("text", ""))
            for item in profile.get("observations", [])
            if isinstance(item, dict)
        ).casefold()
        is_finance = any(
            marker in f"{role_lower} {observation_text}"
            for marker in ("cfo", "finance", "cost", "budget", "status quo")
        )
        is_technical = any(
            marker in f"{role_lower} {observation_text}"
            for marker in ("cto", "technical", "rto", "availability", "rollback", "migration")
        )
        intensity = request.challenge_intensity
        if intensity not in CHALLENGE_INTENSITIES:
            intensity = "normal"
        if is_finance:
            stems = {
                "normal": "What is the cost and downside case for this proposal "
                "compared with keeping the current platform?",
                "skeptical": "What evidence supports the cost and downside case "
                "instead of extending the current platform?",
                "adversarial": "Why should we accept this cost and downside exposure "
                "instead of keeping the current platform?",
            }
        elif is_technical:
            stems = {
                "normal": "What is the migration rollback and recovery plan if "
                "availability is threatened?",
                "skeptical": "What evidence shows the migration can meet the recovery "
                "target and still roll back safely?",
                "adversarial": "What fails first in this migration, and how will you "
                "restore service within the recovery target?",
            }
        else:
            stems = {
                "normal": "What decision or trade-off should this audience understand "
                "about the proposal?",
                "skeptical": "Which assumption or trade-off in the proposal has the "
                "weakest supporting evidence?",
                "adversarial": "What is the strongest professional counterargument to "
                "this proposal?",
            }
        question = stems[intensity]
        prior_count = len(request.prior_question_context)
        if request.task_type == "challenge_follow_up":
            question = (
                "What specific evidence or next step would resolve the concern raised "
                "by your prior answer?"
            )
        elif prior_count:
            question = question.rstrip("?") + " Which part of that case remains least tested?"
        grounding = (
            request.grounding_evidence or request.evidence or request.preferred_user_explanations
        )
        evidence_ids = [
            str(item["evidence_id"])
            for item in grounding[:2]
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
        ]
        observation_ids = [
            str(item["id"])
            for item in profile.get("observations", [])[:2]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        rationale = (
            f"This {intensity} question reflects the selected {role} audience context and "
            f"the supplied project evidence."
        )
        return validate_provider_output(
            request.task_type,
            {
                "question": question,
                "rationale": rationale,
                "evidence_ids": evidence_ids,
                "audience_observation_ids": observation_ids,
            },
            conflict_metadata=request.conflict_metadata,
        )

    @staticmethod
    def _challenge_evaluation(request: ReasoningRequest) -> dict[str, Any]:
        answer = (request.user_input or "").strip()
        answer_lower = answer.casefold()
        words = answer_lower.split()
        grounding = (
            request.grounding_evidence or request.evidence or request.preferred_user_explanations
        )
        grounding_text = " ".join(
            str(item.get("text", "")) for item in grounding if isinstance(item, dict)
        ).casefold()
        overlap = sum(1 for token in set(words) if len(token) >= 4 and token in grounding_text)
        correctness = min(1.0, 0.35 + (0.1 * min(overlap, 4)) + (0.1 if len(words) >= 12 else 0.0))
        directness = min(1.0, 0.55 + (0.1 if len(words) <= 55 else -0.15))
        completeness = min(1.0, 0.35 + (0.1 * min(overlap, 5)))
        concision = max(0.2, min(1.0, 0.9 - max(0, len(words) - 35) * 0.01))
        if request.speaker_evidence:
            style = {
                "score": 0.8,
                "feedback": "The answer is consistent with approved style evidence.",
            }
        else:
            style = {"score": None, "feedback": "Not enough style evidence to assess style match."}
        if request.conflict_metadata:
            support_status = "conflicted"
            support_feedback = (
                "Relevant project evidence contains a conflict; state the ambiguity explicitly."
            )
        elif overlap >= 2:
            support_status = "supported"
            support_feedback = "The answer uses terms supported by the supplied project evidence."
        elif overlap >= 1:
            support_status = "partially_supported"
            support_feedback = "Only part of the answer is connected to the supplied evidence."
        else:
            support_status = "unsupported"
            support_feedback = "The answer did not provide source-supported content."
        supported_ids = [
            str(item["evidence_id"])
            for item in grounding[:2]
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str) and overlap >= 1
        ]
        result = {
            "correctness": {
                "score": round(correctness, 3),
                "feedback": "The answer addresses the question using the available evidence."
                if overlap
                else "Add a project-supported claim or example.",
            },
            "directness": {
                "score": round(directness, 3),
                "feedback": "The answer is focused on the question."
                if len(words) <= 55
                else "Lead with the answer before adding detail.",
            },
            "completeness": {
                "score": round(completeness, 3),
                "feedback": "The answer covers the main supported point."
                if overlap >= 2
                else "Cover the main cost, risk, or decision point explicitly.",
            },
            "concision": {
                "score": round(concision, 3),
                "feedback": "The answer is a usable length."
                if len(words) <= 55
                else "Trim repeated context and keep the decision point.",
            },
            "style_match": style,
            "source_support": {"status": support_status, "feedback": support_feedback},
            "missing_points": []
            if overlap >= 2
            else ["Connect the answer to a specific project source or decision."],
            "supported_evidence_ids": supported_ids,
        }
        return validate_provider_output(
            request.task_type,
            result,
            conflict_metadata=request.conflict_metadata,
        )
