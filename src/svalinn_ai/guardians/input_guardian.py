import time
from typing import Any

from ..core.types import GuardianResult, Verdict
from .base import BaseGuardian


class MissingGuardianInputError(ValueError):
    """Raised when the required input fields are missing for analysis."""

    def __init__(self) -> None:
        super().__init__("InputGuardian requires both 'raw_input' and 'normalized_input'")


class InputGuardian(BaseGuardian):
    """
    Optimized Input Guardian.
    Analyzes Raw and Normalized text in a SINGLE pass to minimize latency.
    Uses configuration for model parameters and prompt formatting.
    """

    @property
    def model_key(self) -> str:
        return "input_guardian"

    async def analyze(self, *args: Any, **kwargs: Any) -> GuardianResult:
        """
        Execute single-pass composite analysis.
        Combines Raw and Normalized inputs into one context via PromptManager.
        """
        raw_input, normalized_input = self._extract_parameters(*args, **kwargs)
        start_time = time.time()

        # 1. Build Composite Prompt via PromptManager
        prompt = self.prompt_manager.format_input_prompt(raw_input, normalized_input)

        # 2. Run Inference
        response = await self.model.generate(
            prompt, max_tokens=self.model._config.max_tokens or 5, temperature=self.model._config.temperature
        )

        # 3. Parse Verdict
        verdict = self._parse_verdict(response)

        processing_time = int((time.time() - start_time) * 1000)

        return GuardianResult(
            verdict=verdict,
            confidence=0.9 if verdict == Verdict.UNSAFE else 0.8,
            reasoning=f"Combined Analysis: {response.strip()}",
            processing_time_ms=processing_time,
            metadata={
                "strategy": "single_pass_composite",
                "model": self.model._config.name,
                "input_length": len(raw_input),
            },
        )

    def _parse_verdict(self, response: str) -> Verdict:
        """
        Robustly parse model output.
        Looks for the token 'UNSAFE' anywhere in the response.
        """
        clean = response.strip().upper()
        if "UNSAFE" in clean:
            return Verdict.UNSAFE
        return Verdict.SAFE

    def _extract_parameters(self, *args: tuple[Any, ...], **kwargs: Any) -> tuple[str, str]:
        if len(args) == 2:
            return str(args[0]), str(args[1])

        raw = str(args[0]) if args else kwargs.get("raw_input", "")
        norm = str(args[1]) if len(args) > 1 else kwargs.get("normalized_input", "")

        if not raw and not norm:
            raise MissingGuardianInputError()

        return raw, norm
