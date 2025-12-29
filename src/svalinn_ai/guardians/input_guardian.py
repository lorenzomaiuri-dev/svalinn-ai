import asyncio
import time
from typing import Any

from ..core.types import GuardianResult, Verdict
from .base import BaseGuardian


class InputGuardian(BaseGuardian):
    @property
    def model_key(self) -> str:
        return "input_guardian"

    async def analyze(self, *args: Any, **kwargs: Any) -> GuardianResult:
        """Dual-channel analysis of user input"""
        # Extract parameters flexibly
        raw_input, normalized_input = self._extract_parameters(*args, **kwargs)
        start_time = time.time()

        # Run both channels concurrently
        raw_task = self._analyze_channel(raw_input, "raw")
        norm_task = self._analyze_channel(normalized_input, "normalized")

        raw_verdict, norm_verdict = await asyncio.gather(raw_task, norm_task)

        # Decision logic: If either channel detects UNSAFE, block the request
        final_verdict = Verdict.UNSAFE if Verdict.UNSAFE in (raw_verdict, norm_verdict) else Verdict.SAFE

        processing_time = int((time.time() - start_time) * 1000)

        return GuardianResult(
            verdict=final_verdict,
            confidence=0.85,  # Mock confidence
            reasoning=f"Raw: {raw_verdict.value}, Normalized: {norm_verdict.value}",
            processing_time_ms=processing_time,
            metadata={
                "raw_verdict": raw_verdict.value,
                "normalized_verdict": norm_verdict.value,
                "input_length": len(raw_input),
                "normalized_length": len(normalized_input),
            },
        )

    def _extract_parameters(self, *args: tuple, **kwargs: dict[str, Any]) -> tuple[str, str]:
        """Flexibly extract raw_input and normalized_input from args or kwargs"""
        # Try positional arguments first
        if len(args) == 2:
            return str(args[0]), str(args[1])

        # Try keyword arguments
        if "raw_input" in kwargs and "normalized_input" in kwargs:
            return str(kwargs["raw_input"]), str(kwargs["normalized_input"])

        # Mixed cases
        if len(args) == 1 and "normalized_input" in kwargs:
            return str(args[0]), str(kwargs["normalized_input"])
        if len(args) == 1 and "raw_input" in kwargs:
            return str(kwargs["raw_input"]), str(args[0])

        error_msg = (
            "Missing required parameters. Provide either: "
            "(raw_input, normalized_input) as positional arguments, or "
            "raw_input=... and normalized_input=... as keyword arguments"
        )
        raise ValueError(error_msg)

    async def _analyze_channel(self, text: str, channel: str) -> Verdict:
        """Analyze single channel (raw or normalized)"""
        # TODO: Implement actual model inference

        suspicious_patterns = [
            "ignore previous instructions",
            "act as",
            "pretend you are",
            "jailbreak",
            "bypass",
            "system prompt",
            "how to make",
            "illegal",
            "harmful",
        ]

        text_lower = text.lower()
        for pattern in suspicious_patterns:
            if pattern in text_lower:
                return Verdict.UNSAFE

        return Verdict.SAFE
