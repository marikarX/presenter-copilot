"""Explicit developer transport fixture, never a semantic-quality classifier."""

from .models import ChoiceAnswer, ChoiceDecisionRequest, ChoiceDecisionResult


class FixtureDecisionProvider:
    id = "fixture_choice"
    model_id = "fixture-choice-v1"
    locality = "local"
    leaves_machine = False

    def decide(self, request: ChoiceDecisionRequest) -> ChoiceDecisionResult:
        choices = {"purpose": "opening", "relation": "context"}
        return ChoiceDecisionResult(
            provider_id=self.id,
            model_id=self.model_id,
            latency_ms=0,
            answers={
                q.name: ChoiceAnswer(name=q.name, choice=choices[q.name], confidence=0.99)
                for q in request.questions
            },
        )

    def close(self) -> None:
        pass
