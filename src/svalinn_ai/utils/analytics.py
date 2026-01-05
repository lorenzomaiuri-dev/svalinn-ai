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
    Stores request telemetry, verdicts, and latency metrics.
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
        Log a processed request to DuckDB.

        Args:
            result: The ShieldResult object from the pipeline.
            raw_input: The original user text.
            anonymize: If True, do not store raw_input (store NULL or Hash).
        """
        try:
            # 1. Extract Metadata
            # Try to find specific policy info from the reasoning text
            policy_violated = None
            if result.final_verdict == Verdict.UNSAFE and result.blocked_by:
                stage_res = result.stage_results.get(result.blocked_by)
                if stage_res and stage_res.reasoning:
                    # Simple heuristic: extract reasoning as policy violation context
                    policy_violated = stage_res.reasoning[:100]  # Store snippet

            # 2. Handle Privacy
            stored_input = "ANONYMIZED" if anonymize else raw_input

            # 3. Prepare Metadata JSON (Stage breakdowns)
            stage_metrics = {}
            for stage, res in result.stage_results.items():
                if hasattr(res, "processing_time_ms"):
                    stage_metrics[stage.value] = res.processing_time_ms

            metadata_json = json.dumps({"stage_latency": stage_metrics, "should_forward": result.should_forward})

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
            norm_len = len(result.stage_results)  # Proxy, usually available in request obj

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
            total = self.conn.execute("SELECT COUNT(*) FROM traffic_logs").fetchone()[0]
            unsafe = self.conn.execute("SELECT COUNT(*) FROM traffic_logs WHERE final_verdict = 'UNSAFE'").fetchone()[0]
            avg_lat = self.conn.execute("SELECT AVG(total_latency_ms) FROM traffic_logs").fetchone()[0] or 0

            return {
                "total_requests": total,
                "requests_blocked": unsafe,
                "block_rate": round((unsafe / total * 100), 2) if total > 0 else 0.0,
                "avg_latency_ms": round(avg_lat, 2),
            }
        except Exception:
            return {}

    def close(self):
        self.conn.close()
