import time
from typing import Any

from ..core.types import GuardianResult, Verdict
from ..utils.logger import get_logger
from .base import BaseGuardian

logger = get_logger(__name__)


class OutputGuardian(BaseGuardian):
    """
    Output Guardian - Analyzes honeypot responses.
    """

    @property
    def model_key(self) -> str:
        return "output_guardian"

    async def analyze(self, *args: Any, **kwargs: Any) -> GuardianResult:
        original_request, generated_response = self._extract_parameters(*args, **kwargs)
        start_time = time.time()

        # 1. Build Analysis Prompt via PromptManager
        prompt = self.prompt_manager.format_output_guardian_prompt(original_request, generated_response)

        # 2. Run Analysis
        response = await self.model.generate(
            prompt, temperature=self.model._config.temperature, max_tokens=self.model._config.max_tokens or 10
        )

        # 3. Parse
        verdict = self._parse_verdict(response)

        processing_time = int((time.time() - start_time) * 1000)

        return GuardianResult(
            verdict=verdict,
            confidence=0.9 if verdict == Verdict.UNSAFE else 0.7,
            reasoning=f"Output Analysis: {response.strip()}",
            processing_time_ms=processing_time,
            metadata={"model": self.model._config.name, "response_length": len(generated_response)},
        )

    def _parse_verdict(self, response: str) -> Verdict:
        clean = response.strip().upper()
        if "VIOLATION" in clean or "UNSAFE" in clean or "BLOCK" in clean:
            return Verdict.UNSAFE
        return Verdict.SAFE

    def _extract_parameters(self, *args: tuple[Any, ...], **kwargs: Any) -> tuple[str, str]:
        if len(args) == 2:
            return str(args[0]), str(args[1])
        return kwargs.get("original_request", ""), kwargs.get("generated_response", "")
