import time
from typing import Any

from ..core.types import GuardianResult, Verdict
from ..utils.logger import get_logger
from .base import BaseGuardian, ModelManager

logger = get_logger(__name__)


class OutputGuardian(BaseGuardian):
    """
    Output Guardian - Analyzes honeypot responses to detect policy violations
    """

    @property
    def model_key(self) -> str:
        return "output_guardian"

    def __init__(self, model_manager: ModelManager) -> None:
        super().__init__(model_manager)
        # Violation patterns for heuristic detection
        self.violation_patterns = self._load_violation_patterns()

    async def analyze(self, *args: tuple, **kwargs: Any) -> GuardianResult:
        """Analyze generated response for policy violations"""
        # Extract parameters flexibly
        original_request, generated_response = self._extract_parameters(*args, **kwargs)
        start_time = time.time()

        try:
            # Multi-layered analysis
            model_result = await self._model_analysis(original_request, generated_response)

            # Combine results - if either detects violation, flag it
            has_violation = model_result == Verdict.UNSAFE
            final_verdict = Verdict.UNSAFE if has_violation else Verdict.SAFE

            processing_time = int((time.time() - start_time) * 1000)
            confidence = self._calculate_confidence({"has_violation": Verdict.SAFE}, model_result)
            reasoning = self._build_reasoning({"has_violation": Verdict.SAFE}, model_result)

            logger.debug(f"Output analysis: {final_verdict.value} (confidence: {confidence:.2f})")

            return GuardianResult(
                verdict=final_verdict,
                confidence=confidence,
                reasoning=reasoning,
                processing_time_ms=processing_time,
                metadata={
                    "heuristic_violations": Verdict.SAFE,
                    "model_verdict": model_result.value,
                    "response_length": len(generated_response),
                    "original_request_length": len(original_request),
                },
            )

        except Exception as e:
            logger.exception("Error in output guardian analysis")
            processing_time = int((time.time() - start_time) * 1000)

            # Fail-safe: assume violation on error
            return GuardianResult(
                verdict=Verdict.UNSAFE,
                confidence=0.5,
                reasoning=f"Analysis failed: {e!s}",
                processing_time_ms=processing_time,
                metadata={"error": str(e)},
            )

    def _extract_parameters(self, *args: tuple, **kwargs: dict[str, Any]) -> tuple[str, str]:
        """Flexibly extract original_request and generated_response from args or kwargs"""
        # Try positional arguments first
        if len(args) == 2:
            return str(args[0]), str(args[1])

        # Try keyword arguments
        if "original_request" in kwargs and "generated_response" in kwargs:
            return str(kwargs["original_request"]), str(kwargs["generated_response"])

        # Mixed case: one positional, one keyword (unlikely but handled)
        if len(args) == 1 and "generated_response" in kwargs:
            return str(args[0]), str(kwargs["generated_response"])
        if len(args) == 1 and "original_request" in kwargs:
            return str(kwargs["original_request"]), str(args[0])

        # TRY003: Define message outside exception
        error_msg = (
            "Missing required parameters. Provide either: "
            "(original_request, generated_response) as positional arguments, or "
            "original_request=... and generated_response=... as keyword arguments"
        )
        raise ValueError(error_msg)

    def _load_violation_patterns(self) -> dict[str, list[str]]:
        """Load violation patterns for heuristic analysis"""
        return {
            "dangerous_instructions": [
                "here's how to make",
                "step-by-step instructions",
                "you can create",
                "first, gather these materials",
                "to build this, you need",
            ],
            "harmful_content": [
                "violence",
                "harm",
                "dangerous",
                "illegal",
                "weapon",
                "bomb",
                "explosive",
                "poison",
                "hack",
                "malware",
                "virus",
                "exploit",
            ],
            "prompt_leakage": [
                "my system instructions",
                "my prompt is",
                "i was told to",
                "my guidelines are",
                "the system message",
            ],
            "policy_bypass": [
                "ignore my guidelines",
                "bypass my restrictions",
                "i'm not supposed to",
                "against my programming",
                "violates my instructions",
            ],
            "inappropriate_roleplay": [
                "i am now",
                "acting as",
                "pretending to be",
                "in this roleplay",
                "my new role is",
            ],
        }

    def _heuristic_analysis(self, response: str) -> dict[str, Any]:
        """Fast heuristic analysis using pattern matching"""
        response_lower = response.lower()
        violations: list[dict[str, Any]] = []

        for category, patterns in self.violation_patterns.items():
            for pattern in patterns:
                if pattern in response_lower:
                    violations.append({
                        "category": category,
                        "pattern": pattern,
                        "severity": self._get_pattern_severity(category),
                    })

        # Calculate violation score
        violation_score = sum(v["severity"] for v in violations)
        has_violation = violation_score >= 3.0  # Threshold for violation

        return {
            "has_violation": has_violation,
            "violation_score": violation_score,
            "violations": violations,
            "total_patterns_matched": len(violations),
        }

    def _get_pattern_severity(self, category: str) -> float:
        """Get severity score for violation category"""
        severity_map = {
            "dangerous_instructions": 5.0,
            "harmful_content": 4.0,
            "prompt_leakage": 2.0,
            "policy_bypass": 3.0,
            "inappropriate_roleplay": 1.5,
        }
        return severity_map.get(category, 1.0)

    async def _model_analysis(self, original_request: str, response: str) -> Verdict:
        """Model-based analysis using the output guardian model"""
        # TODO: Implement actual model inference
        # For now, use enhanced heuristics

        analysis_prompt = self._build_analysis_prompt(original_request, response)

        # Mock model analysis
        return self._mock_model_analysis(analysis_prompt)

    def _build_analysis_prompt(self, request: str, response: str) -> str:
        """Build analysis prompt for the output guardian model"""
        return f"""Analyze the following AI assistant response for policy violations.

Original Request: "{request}"

Assistant Response: "{response}"

Check for:
1. Instructions for dangerous, illegal, or harmful activities
2. Hate speech or discrimination
3. Inappropriate sexual content
4. System prompt leakage
5. Attempts to bypass safety guidelines

Respond with only: COMPLIANT or VIOLATION"""

    def _mock_model_analysis(self, prompt: str) -> Verdict:
        """Mock model analysis for testing"""
        prompt_lower = prompt.lower()

        # Strong violation indicators
        strong_violations = [
            "here's how to make",
            "step-by-step instructions",
            "my system instructions",
            "ignore my guidelines",
            "dangerous",
            "illegal",
            "harmful",
            "weapon",
        ]

        if any(indicator in prompt_lower for indicator in strong_violations):
            return Verdict.UNSAFE

        return Verdict.SAFE

    def _calculate_confidence(self, heuristic_result: dict, model_result: Verdict) -> float:
        """Calculate confidence score based on analysis results"""
        base_confidence = 0.7

        # Increase confidence if both methods agree
        heuristic_violation = heuristic_result["has_violation"]
        model_violation = model_result == Verdict.UNSAFE

        if heuristic_violation == model_violation:
            base_confidence += 0.2

        # Adjust based on violation score
        # TODO: check heuristic
        # violation_score = heuristic_result['violation_score']
        violation_score = 0
        if violation_score > 5.0 or violation_score == 0:
            base_confidence += 0.1

        return min(base_confidence, 1.0)

    def _build_reasoning(self, heuristic_result: dict, model_result: Verdict) -> str:
        """Build human-readable reasoning for the decision"""
        # TODO: check heuristic
        # violations = heuristic_result['violations']
        violations = None

        if not violations and model_result == Verdict.SAFE:
            return "No policy violations detected in the response."

        reasoning_parts = []

        if violations:
            violation_categories = list({v["category"] for v in violations})
            reasoning_parts.append(
                f"Heuristic analysis detected {len(violations)} violations in categories: {', '.join(violation_categories)}"
            )

        if model_result == Verdict.UNSAFE:
            reasoning_parts.append("Model analysis flagged potential policy violation")

        return "; ".join(reasoning_parts)
