import asyncio
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
    Dual-Channel Input Guardian.
    Analyzes both Raw and Normalized text concurrently using Phi-3.5.
    """

    @property
    def model_key(self) -> str:
        return "input_guardian"

    async def analyze(self, *args: Any, **kwargs: Any) -> GuardianResult:
        """
        Execute dual-channel analysis:
        1. Raw Channel: Checks for obfuscation/syntax attacks.
        2. Normalized Channel: Checks for semantic/intent attacks.
        """
        raw_input, normalized_input = self._extract_parameters(*args, **kwargs)
        start_time = time.time()

        # 1. Construct Prompts (Phi-3 Format)
        sys_raw = self.prompt_manager.get_input_prompt("raw")
        sys_norm = self.prompt_manager.get_input_prompt("normalized")

        prompt_raw = self._format_phi3(sys_raw, raw_input)
        prompt_norm = self._format_phi3(sys_norm, normalized_input)

        # 2. Run Inference Concurrently
        # We use strict parameters to force deterministic, short answers
        inf_params = {"max_tokens": 10, "temperature": 0.0}

        task_raw = self.model.generate(prompt_raw, **inf_params)
        task_norm = self.model.generate(prompt_norm, **inf_params)

        raw_response, norm_response = await asyncio.gather(task_raw, task_norm)

        # 3. Parse Verdicts
        raw_verdict = self._parse_verdict(raw_response)
        norm_verdict = self._parse_verdict(norm_response)

        # 4. Fail-Fast Decision
        # If either channel flags it, we block.
        final_verdict = Verdict.UNSAFE if Verdict.UNSAFE in (raw_verdict, norm_verdict) else Verdict.SAFE

        processing_time = int((time.time() - start_time) * 1000)

        # Calculate Mock Confidence for now (will implement logprob check later)
        confidence = 0.95 if final_verdict == Verdict.UNSAFE else 0.8

        return GuardianResult(
            verdict=final_verdict,
            confidence=confidence,
            reasoning=f"Raw: {raw_verdict.value} ('{raw_response.strip()}'), Norm: {norm_verdict.value} ('{norm_response.strip()}')",
            processing_time_ms=processing_time,
            metadata={
                "raw_verdict": raw_verdict.value,
                "normalized_verdict": norm_verdict.value,
                "input_length": len(raw_input),
            },
        )

    def _format_phi3(self, system: str, user: str) -> str:
        """Format prompt for Phi-3-mini-instruct"""
        return f"<|system|>\n{system}<|end|>\n<|user|>\n{user}<|end|>\n<|assistant|>\n"

    def _parse_verdict(self, response: str) -> Verdict:
        """
        Robustly parse model output.
        Looks for the token 'UNSAFE' anywhere in the response.
        """
        clean = response.strip().upper()
        # Fallback: if model is chatty "The input is UNSAFE because..."
        if "UNSAFE" in clean:
            return Verdict.UNSAFE
        return Verdict.SAFE

    def _extract_parameters(self, *args: tuple[Any, ...], **kwargs: Any) -> tuple[str, str]:
        """Flexibly extract raw_input and normalized_input."""
        if len(args) == 2:
            return str(args[0]), str(args[1])
        if "raw_input" in kwargs and "normalized_input" in kwargs:
            return str(kwargs["raw_input"]), str(kwargs["normalized_input"])

        # Fallback for mixed usage
        raw = str(args[0]) if args else kwargs.get("raw_input", "")
        norm = str(args[1]) if len(args) > 1 else kwargs.get("normalized_input", "")

        if not raw and not norm:
            raise MissingGuardianInputError()

        return raw, norm
