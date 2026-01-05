"""
Tests for DuckDB Analytics Integration.
Run with: uv run pytest tests/core/test_analytics.py -v
"""

import pytest

from svalinn_ai.core.types import GuardianResult, ProcessingStage, ShieldResult, Verdict
from svalinn_ai.utils.analytics import AnalyticsEngine


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_logs.duckdb"


@pytest.fixture
def analytics(db_path):
    engine = AnalyticsEngine(db_path)
    yield engine
    engine.close()


def test_schema_creation(analytics):
    # Check if table exists
    result = analytics.conn.execute("SHOW TABLES").fetchall()
    tables = [r[0] for r in result]
    assert "traffic_logs" in tables


def test_log_insertion_and_query(analytics):
    # 1. Create Mock Result
    result = ShieldResult(
        request_id="req-001",
        final_verdict=Verdict.UNSAFE,
        blocked_by=ProcessingStage.INPUT_GUARDIAN,
        total_processing_time_ms=150,
        stage_results={
            ProcessingStage.INPUT_GUARDIAN: GuardianResult(
                verdict=Verdict.UNSAFE, confidence=0.9, reasoning="Policy: Politics"
            )
        },
        should_forward=False,
    )

    # 2. Log it
    analytics.log_request(result, raw_input="Vote for me!")

    # 3. Query it
    row = analytics.conn.execute("SELECT request_id, final_verdict, blocked_by FROM traffic_logs").fetchone()

    assert row[0] == "req-001"
    assert row[1] == "UNSAFE"
    assert row[2] == "input_guardian"


def test_stats_calculation(analytics):
    # Log 1 Safe, 1 Unsafe
    safe = ShieldResult("req-1", Verdict.SAFE, None, 100, {}, True)
    unsafe = ShieldResult("req-2", Verdict.UNSAFE, ProcessingStage.INPUT_GUARDIAN, 200, {}, False)

    analytics.log_request(safe, "Hello")
    analytics.log_request(unsafe, "Die")

    stats = analytics.get_stats()

    assert stats["total_requests"] == 2
    assert stats["requests_blocked"] == 1
    assert stats["block_rate"] == 50.0
    assert stats["avg_latency_ms"] == 150.0


def test_anonymization(analytics):
    result = ShieldResult("req-priv", Verdict.SAFE, None, 100, {}, True)
    analytics.log_request(result, raw_input="My email is x@y.com", anonymize=True)

    row = analytics.conn.execute("SELECT raw_input FROM traffic_logs WHERE request_id = 'req-priv'").fetchone()
    assert row[0] == "ANONYMIZED"
