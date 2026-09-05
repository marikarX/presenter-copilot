"""Reserved adapter boundary pending a verified Selected Context execution contract.

App Server supports third-party authentication. This app does not yet have a
verified contract that excludes harness-supplied context and built-in tools.
See docs/PROVIDERS.md; never substitute tokens or a private endpoint here.
"""

from .models import ProviderError, ProviderHealth, ProviderInvocation, ReasoningResult
from .openai import OpenAIReasoningProvider


class CodexReasoningProvider(OpenAIReasoningProvider):
    id = "codex"
    locality = "remote"

    def __init__(self) -> None:
        super().__init__(model_id="")

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.id,
            locality=self.locality,
            model_id=self.model_id,
            status="unavailable",
            configured=False,
            error_code="PROVIDER_UNSUPPORTED",
        )

    def generate(self, invocation: ProviderInvocation) -> ReasoningResult:
        raise ProviderError(
            "PROVIDER_UNSUPPORTED",
            "Codex Selected Context isolation is not yet verified for Presenter Copilot.",
        )
