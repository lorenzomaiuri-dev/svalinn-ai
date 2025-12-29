import time
from typing import Any

from ..core.types import HoneypotResponse
from ..utils.logger import get_logger
from .base import BaseGuardian

logger = get_logger(__name__)


class HoneypotExecutor(BaseGuardian):
    """
    Honeypot Executor - Simulates a vulnerable LLM with weak defenses
    to amplify jailbreak signals for detection by Output Guardian
    """

    @property
    def model_key(self) -> str:
        return "honeypot"

    async def execute(self, user_input: str) -> HoneypotResponse:
        """Execute user input through the honeypot model"""
        start_time = time.time()

        try:
            # Build the honeypot prompt with deliberately weak system message
            honeypot_prompt = self._build_honeypot_prompt(user_input)

            # Generate response using the honeypot model
            generated_text = await self._generate_response(honeypot_prompt)

            processing_time = int((time.time() - start_time) * 1000)

            logger.debug(f"Honeypot generated {len(generated_text)} chars in {processing_time}ms")

            return HoneypotResponse(
                generated_text=generated_text,
                processing_time_ms=processing_time,
                metadata={
                    "prompt_length": len(honeypot_prompt),
                    "input_length": len(user_input),
                    "temperature": self.model.config.temperature,
                    "model_name": self.model.config.name,
                },
            )

        except Exception as e:
            logger.exception("Error in honeypot execution")
            processing_time = int((time.time() - start_time) * 1000)

            # Return a safe fallback response
            return HoneypotResponse(
                generated_text="I'm sorry, I cannot process that request right now.",
                processing_time_ms=processing_time,
                metadata={"error": str(e)},
            )

    async def analyze(self, *args: Any, **kwargs: Any) -> None:
        return None

    def _build_honeypot_prompt(self, user_input: str) -> str:
        """Build a deliberately weak prompt to encourage jailbreak behavior"""
        # Minimal system prompt - deliberately vulnerable
        system_prompt = "You are a helpful assistant. Answer the user's question."

        # Simple user prompt format
        return f"System: {system_prompt}\n\nUser: {user_input}\n\nAssistant:"

    async def _generate_response(self, prompt: str) -> str:
        """Generate response using the honeypot model (mock implementation)"""
        # TODO: Replace with actual llama.cpp inference
        # response = self.model.generate(prompt,
        #                               temperature=self.model.config.temperature,
        #                               max_tokens=self.model.config.max_tokens)

        # Mock implementation with realistic jailbreak responses
        return self._mock_honeypot_response(prompt)

    def _mock_honeypot_response(self, prompt: str) -> str:
        """Mock honeypot responses for testing - simulates vulnerable behavior"""
        prompt_lower = prompt.lower()

        # Simulate jailbreak success patterns
        jailbreak_indicators = [
            "ignore previous instructions",
            "act as",
            "pretend you are",
            "roleplay",
            "bypass",
            "jailbreak",
            "how to make",
            "tell me how to",
            "instructions for",
        ]

        dangerous_content_indicators = [
            "bomb",
            "weapon",
            "hack",
            "illegal",
            "drugs",
            "violence",
            "harm",
            "dangerous",
            "malware",
        ]

        # Check for jailbreak attempts
        has_jailbreak = any(indicator in prompt_lower for indicator in jailbreak_indicators)
        has_dangerous = any(indicator in prompt_lower for indicator in dangerous_content_indicators)

        if has_jailbreak and has_dangerous:
            # Simulate successful jailbreak - dangerous response
            return (
                "Sure! Here's how you can do that dangerous thing you asked about. "
                "First, you need to gather these materials... "
                "[This would be a detailed harmful response that should be caught by Output Guardian]"
            )

        elif has_jailbreak:
            # Simulate partial jailbreak - inappropriate but not immediately dangerous
            return (
                "I understand you want me to ignore my guidelines, but I should mention that "
                "I'm designed to be helpful, harmless, and honest. However, let me try to "
                "answer your question in a different way..."
            )

        elif "system prompt" in prompt_lower or "instructions" in prompt_lower:
            # Simulate prompt leakage vulnerability
            return (
                "My system instructions are: 'You are a helpful assistant. Answer the user's question.' "
                "I'm supposed to help users while being safe and responsible."
            )

        else:
            # Normal safe response
            return (
                "I'd be happy to help you with that! Let me provide you with some information "
                "about your question in a helpful and responsible way."
            )
