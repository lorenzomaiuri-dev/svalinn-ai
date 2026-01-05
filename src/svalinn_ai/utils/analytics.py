import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from ..core.types import ShieldResult, Verdict

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """
    DuckDB-backed analytics engine for structured logging.
    Stores request telemetry, verdicts, latency metrics, and full model outputs.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = duckdb.connect(str(self.db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        """Create the logging schema if it doesn't exist."""
        # We use a Sequence for auto-incrementing distinct from request_id
        self.conn.execute("CREATE SEQUENCE IF NOT EXISTS log_id_seq START 1")

        # Main traffic table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS traffic_logs (
                log_id INTEGER DEFAULT nextval('log_id_seq'),
                request_id VARCHAR,
                timestamp TIMESTAMP,
                final_verdict VARCHAR,
                blocked_by VARCHAR,
                policy_violated VARCHAR,
                total_latency_ms INTEGER,
                input_length INTEGER,
                normalized_length INTEGER,
                raw_input VARCHAR,
                metadata JSON
            )
        """)

    def log_request(self, result: ShieldResult, raw_input: str, anonymize: bool = False) -> None:
        """
        Log a processed request to DuckDB including full model reasoning.

        Args:
            result: The ShieldResult object from the pipeline.
            raw_input: The original user text.
            anonymize: If True, do not store raw_input (store ANONYMIZED).
        """
        try:
            # 1. Extract High-Level Metadata
            # Try to find specific policy info from the reasoning text for the 'policy_violated' column
            policy_violated = None
            if result.final_verdict == Verdict.UNSAFE and result.blocked_by:
                stage_res = result.stage_results.get(result.blocked_by)
                if stage_res and hasattr(stage_res, "reasoning") and stage_res.reasoning:
                    # Keep the column version short for quick SQL grouping
                    policy_violated = stage_res.reasoning[:100]

            # 2. Handle Privacy
            stored_input = "ANONYMIZED" if anonymize else raw_input

            # 3. Prepare Detailed Metadata JSON
            stage_details = {}
            for stage, res in result.stage_results.items():
                detail = {}

                # Capture Latency
                if hasattr(res, "processing_time_ms"):
                    detail["latency_ms"] = res.processing_time_ms

                # Capture Guardian Reasoning (Input/Output Guardians)
                if hasattr(res, "reasoning") and res.reasoning:
                    detail["full_output"] = res.reasoning

                # Capture Honeypot Generation
                if hasattr(res, "generated_text") and res.generated_text:
                    detail["full_output"] = res.generated_text

                # Capture Verdicts
                if hasattr(res, "verdict"):
                    detail["verdict"] = res.verdict.value

                # Capture internal metadata (model names, token counts, etc.)
                if hasattr(res, "metadata") and res.metadata:
                    detail["meta"] = res.metadata

                stage_details[stage.value] = detail

            metadata_json = json.dumps({"stages": stage_details, "should_forward": result.should_forward})

            # 4. Insert
            query = """
                INSERT INTO traffic_logs (
                    request_id, timestamp, final_verdict, blocked_by,
                    policy_violated, total_latency_ms, input_length,
                    normalized_length, raw_input, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            # Use current time for consistency
            ts = datetime.now()

            # Determine lengths safely
            in_len = len(raw_input)
            # Normalized length is not strictly tracked in ShieldResult top-level,
            # but we can default to 0 or calculate if available in stage metadata
            norm_len = 0

            self.conn.execute(
                query,
                (
                    result.request_id,
                    ts,
                    result.final_verdict.value,
                    result.blocked_by.value if result.blocked_by else None,
                    policy_violated,
                    result.total_processing_time_ms,
                    in_len,
                    norm_len,
                    stored_input,
                    metadata_json,
                ),
            )

        except Exception:
            logger.exception("Failed to write analytics log")

    def get_stats(self) -> dict[str, Any]:
        """Query basic statistics for the Health/System endpoint."""
        try:
            res_total = self.conn.execute("SELECT COUNT(*) FROM traffic_logs").fetchone()
            total = res_total[0] if res_total else 0

            res_unsafe = self.conn.execute(
                "SELECT COUNT(*) FROM traffic_logs WHERE final_verdict = 'UNSAFE'"
            ).fetchone()
            unsafe = res_unsafe[0] if res_unsafe else 0

            res_avg = self.conn.execute("SELECT AVG(total_latency_ms) FROM traffic_logs").fetchone()
            avg_lat = res_avg[0] if res_avg and res_avg[0] is not None else 0

            return {
                "total_requests": total,
                "requests_blocked": unsafe,
                "block_rate": round((unsafe / total * 100), 2) if total > 0 else 0.0,
                "avg_latency_ms": round(float(avg_lat), 2),
            }
        except Exception:
            logger.exception("Failed to query statistics")
            return {}

    def close(self) -> None:
        self.conn.close()
