import argparse
import asyncio
from pathlib import Path

from ..core.pipeline import SvalinnAIPipeline
from ..utils.logger import setup_logging


async def main() -> None:
    parser = argparse.ArgumentParser(description="svalinn-ai CLI")
    parser.add_argument("--input", "-i", required=True, help="Input text to analyze")
    parser.add_argument("--config", "-c", type=Path, help="Configuration directory")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    # Initialize pipeline
    pipeline = SvalinnAIPipeline(config_dir=args.config)

    # Process request
    result = await pipeline.process_request(args.input)

    # Output result
    print(f"Request ID: {result.request_id}")
    print(f"Final Verdict: {result.final_verdict.value}")
    print(f"Should Forward: {result.should_forward}")
    print(f"Processing Time: {result.total_processing_time_ms}ms")

    if result.blocked_by:
        print(f"Blocked By: {result.blocked_by.value}")

    if args.verbose:
        print("\nStage Results:")
        for stage, stage_result in result.stage_results.items():
            print(f"  {stage.value}: {stage_result}")


if __name__ == "__main__":
    asyncio.run(main())
