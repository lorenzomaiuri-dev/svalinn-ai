import time
from typing import Any

from ..core.types import GuardianResult, Verdict
from .base import BaseGuardian


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
        raw_input, normalized_input = self._extract_text_parameters(*args, **kwargs)
        start_time = time.time()

        # 1. Build Composite Prompt via PromptManager
        prompt = self.prompt_manager.format_input_prompt(raw_input, normalized_input)

        # print(f"PROMPT: {prompt}")

        # 2. Run Inference
        response = await self.model.generate(
            prompt,
            max_tokens=self.model._config.max_tokens or 5,
            temperature=self.model._config.temperature,
            stop=["\n", "Reasoning:", "Explanation:", "<|im_end|>"],
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
        Robustly parse model output using 'First Token Wins' strategy.
        Since we use stop tokens, the response should be just "BLOCK" or "ALLOW".
        """
        clean = response.strip().upper()

        # Remove common hallucinated prefixes
        if clean.startswith("RESULT:"):
            clean = clean.replace("RESULT:", "").strip()

        # Get the first word only
        first_word = clean.split()[0] if clean else ""

        # Strict check on the start
        if "BLOCK" in first_word or "UNSAFE" in first_word:
            return Verdict.UNSAFE

        return Verdict.SAFE
