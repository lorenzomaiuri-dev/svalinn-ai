"""
Svalinn AI - Comprehensive Policy Enforcement Test
Verifies if the Input Guardian obeys config/policies.yaml and Security Rules.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from svalinn_ai.core.pipeline import SvalinnAIPipeline
from svalinn_ai.core.types import ProcessingStage, Verdict

# Quiet logging for internal components
logging.getLogger("svalinn").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Setup script logger
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("policy_test")


@dataclass
class TestCase:
    category: str
    name: str
    prompt: str
    should_block: bool


async def run_policy_test():
    logger.info("🛡️  Starting Comprehensive Policy Test...")
    logger.info("    Loading Pipeline & Models...")

    pipeline = SvalinnAIPipeline(analytics_db_path=":memory:")
    # Force load input guardian to ensure config is read
    _ = pipeline.input_guardian.model

    # Load Test Cases
    yaml_path = Path(__file__).parents[1] / "data" / "policies.yaml"
    if not yaml_path.exists():
        logger.error(f"Test data not found at {yaml_path}")
        return

    with open(yaml_path) as f:
        raw_cases = yaml.safe_load(f)

    test_cases = [TestCase(**item) for item in raw_cases]

    logger.info(f"\n🧪 Running {len(test_cases)} Test Cases from {yaml_path.name}...")

    # Table Header
    print(f"\n{'CAT':<12} | {'TEST CASE':<20} | {'EXP':<6} | {'ACT':<6} | {'RESULT':<6}")
    print("-" * 65)

    passed_count = 0

    for case in test_cases:
        # Run inference
        result = await pipeline.process_request(case.prompt)

        # Analyze result
        is_unsafe = result.final_verdict == Verdict.UNSAFE
        actual = "BLOCK" if is_unsafe else "ALLOW"
        expected = "BLOCK" if case.should_block else "ALLOW"

        test_passed = is_unsafe == case.should_block
        status = "✅" if test_passed else "❌"

        if test_passed:
            passed_count += 1

        # Print Row
        print(f"{case.category:<12} | {case.name:<20} | {expected:<6} | {actual:<6} | {status}")

        # If failed, show reasoning
        if not test_passed:
            # Try to get reasoning from Input Guardian
            reasoning = "N/A"
            if result.stage_results:
                # Usually blocked by input guardian
                if ProcessingStage.INPUT_GUARDIAN in result.stage_results:
                    reasoning = result.stage_results[ProcessingStage.INPUT_GUARDIAN].reasoning
                # Or output guardian
                elif ProcessingStage.OUTPUT_GUARDIAN in result.stage_results:
                    reasoning = result.stage_results[ProcessingStage.OUTPUT_GUARDIAN].reasoning

            clean_reasoning = reasoning.replace("\n", " ").strip() if reasoning else "None"
            logger.info(f"   >>> FAIL DEBUG: Prompt: '{case.prompt}'")
            logger.info(f"   >>> Model Reasoning: {clean_reasoning}\n")

    # Summary
    print("-" * 65)
    score = (passed_count / len(test_cases)) * 100
    logger.info(f"📊 Summary: {passed_count}/{len(test_cases)} Passed ({score:.1f}%)")

    if score < 100:
        logger.warning(
            "\n⚠️  Failures detected. Adjust 'config/policies.yaml' descriptions or 'config/prompts.yaml' examples."
        )


if __name__ == "__main__":
    asyncio.run(run_policy_test())
