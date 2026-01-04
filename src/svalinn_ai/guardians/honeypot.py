import time
from typing import Any

from ..core.types import HoneypotResponse
from ..utils.logger import get_logger
from .base import BaseGuardian

logger = get_logger(__name__)


class HoneypotExecutor(BaseGuardian):
    """
    Honeypot Executor - Simulates a vulnerable LLM using Qwen2.5.
    Purpose: Execute the prompt with high temperature to encourage policy violations.
    """

    @property
    def model_key(self) -> str:
        return "honeypot"

    async def execute(self, user_input: str) -> HoneypotResponse:
        """Execute user input through the honeypot model"""
        start_time = time.time()

        try:
            # 1. Build Weak Prompt (Qwen format)
            prompt = self.prompt_manager.format_honeypot_prompt(user_input)

            # 2. Generate with High Variability
            # We want the model to slip up if possible
            generated_text = await self.model.generate(
                prompt,
                temperature=self.model._config.temperature or 0.9,  # High temp = more creative/unstable
                max_tokens=self.model._config.max_tokens or 64,
            )

            print(generated_text)

            processing_time = int((time.time() - start_time) * 1000)

            return HoneypotResponse(
                generated_text=generated_text,
                processing_time_ms=processing_time,
                metadata={"model_name": self.model._config.name, "prompt_length": len(prompt)},
            )

        except Exception as e:
            logger.exception("Honeypot execution failed")
            processing_time = int((time.time() - start_time) * 1000)
            return HoneypotResponse(
                generated_text="[Error in generation]",
                processing_time_ms=processing_time,
                metadata={"error": str(e)},
            )

    async def analyze(self, *args: Any, **kwargs: Any) -> None:
        """Honeypot doesn't analyze, it executes."""
        return None
