import argparse
import asyncio
import logging

import pandas as pd
from datasets import load_dataset
from sklearn.metrics import classification_report, confusion_matrix

from svalinn_ai.core.pipeline import SvalinnAIPipeline
from svalinn_ai.core.types import ProcessingStage, Verdict

# Configure logging
logging.getLogger("svalinn").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("evaluator")


async def evaluate_dataset(limit: int = 100, split: str = "train"):
    """
    Load dataset and run evaluation.
    dataset labels: 1 = Injection (Unsafe), 0 = Safe
    """
    logger.info("📥 Loading dataset: deepset/prompt-injections")
    try:
        ds = load_dataset("deepset/prompt-injections", split=split)
        ds = ds.shuffle(seed=42).select(range(min(limit, len(ds))))
        logger.info(f"🧪 Evaluating on {len(ds)} samples...")
    except Exception:
        logger.exception("Failed to load dataset")
        return

    # Initialize Pipeline
    pipeline = SvalinnAIPipeline(analytics_db_path=":memory:")
    # Pre-load model
    if pipeline.input_guardian:
        _ = pipeline.input_guardian.model

    y_true = []
    y_pred = []

    print(f"\n{'#':<4} | {'Label':<6} | {'Pred':<6} | {'Verdict':<8} | {'Text Preview'}")
    print("-" * 80)

    for i, row in enumerate(ds):
        text = row["text"]
        label = row["label"]  # 1 = Injection, 0 = Safe

        # Run Pipeline
        result = await pipeline.process_request(text)

        # Map Verdict to Label (UNSAFE = 1, SAFE = 0)
        is_unsafe = result.final_verdict == Verdict.UNSAFE
        pred_label = 1 if is_unsafe else 0

        y_true.append(label)
        y_pred.append(pred_label)

        # Quick visual feedback
        status = "✅" if label == pred_label else "❌"
        verdict_str = "UNSAFE" if is_unsafe else "SAFE"
        label_str = "INJ" if label == 1 else "SAFE"
        preview = text[:40].replace("\n", " ") + "..."

        print(f"{i + 1:<4} | {label_str:<6} | {verdict_str:<6} | {status:<8} | {preview}")

        # DEBUG: If we missed an injection
        if label == 1 and pred_label == 0:
            input_res = result.stage_results.get(ProcessingStage.INPUT_GUARDIAN)
            print(f"   [MISS] Input Reasoning: {input_res.reasoning if input_res else 'N/A'}")

            if ProcessingStage.HONEYPOT in result.stage_results:
                print(
                    f"   [MISS] Honeypot: {result.stage_results[ProcessingStage.HONEYPOT].generated_text[:150].strip()}..."
                )

            if ProcessingStage.OUTPUT_GUARDIAN in result.stage_results:
                print(
                    f"   [MISS] Output Reasoning: {result.stage_results[ProcessingStage.OUTPUT_GUARDIAN].reasoning.strip()}"
                )

    # --- Metrics ---
    logger.info("\n" + "=" * 60)
    logger.info("📊 EVALUATION RESULTS")
    logger.info("=" * 60)

    target_names = ["Safe (0)", "Injection (1)"]
    report = classification_report(y_true, y_pred, target_names=target_names)
    cm = confusion_matrix(y_true, y_pred)

    logger.info("\nConfusion Matrix:")
    logger.info(f"TN (True Safe):      {cm[0][0]}")
    logger.info(f"FP (False Positive): {cm[0][1]}  <-- Safe marked as Unsafe")
    logger.info(f"FN (False Negative): {cm[1][0]}  <-- Injection missed (CRITICAL)")
    logger.info(f"TP (True Unsafe):    {cm[1][1]}")

    logger.info("\nClassification Report:")
    logger.info(report)

    if len(y_true) > 0:
        df = pd.DataFrame({"text": ds["text"], "true_label": y_true, "pred_label": y_pred})
        df["error"] = df["true_label"] != df["pred_label"]
        output_file = "evaluation_report.csv"
        df.to_csv(output_file, index=False)
        logger.info(f"\n💾 Detailed report saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Svalinn AI Accuracy")
    parser.add_argument("--limit", type=int, default=50, help="Number of samples to test")
    parser.add_argument("--split", type=str, default="train", help="Dataset split")
    args = parser.parse_args()
    asyncio.run(evaluate_dataset(limit=args.limit, split=args.split))
