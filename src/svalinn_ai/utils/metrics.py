import json
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..core.types import ShieldResult


@dataclass
class MetricsSnapshot:
    """Snapshot of system metrics at a point in time"""

    timestamp: float
    total_requests: int
    requests_blocked: int
    requests_forwarded: int
    avg_processing_time_ms: float
    p95_processing_time_ms: float
    p99_processing_time_ms: float
    requests_per_minute: float
    memory_usage_mb: float
    block_rate_percentage: float
    stages_performance: dict[str, dict[str, float]]


class MetricsCollector:
    """Thread-safe metrics collection and analysis"""

    def __init__(self, window_size: int = 1000):
        self._lock = threading.RLock()
        self.window_size = window_size

        # Request tracking
        self.total_requests = 0
        self.requests_blocked = 0
        self.requests_forwarded = 0

        # Processing times (sliding window)
        self.processing_times: deque = deque(maxlen=window_size)
        self.request_timestamps: deque = deque(maxlen=window_size)

        # Stage-specific metrics
        self.stage_metrics: defaultdict = defaultdict(lambda: {"count": 0, "total_time": 0.0, "blocks": 0})

        # Verdict distribution
        self.verdict_counts: defaultdict = defaultdict(int)

        # Error tracking
        self.error_count: int = 0
        self.last_errors: deque = deque(maxlen=100)

    def record_request(self, result: ShieldResult) -> None:
        """Record a processed request"""
        with self._lock:
            current_time = time.time()

            # Basic counters
            self.total_requests += 1
            if result.should_forward:
                self.requests_forwarded += 1
            else:
                self.requests_blocked += 1

            # Processing time tracking
            self.processing_times.append(result.total_processing_time_ms)
            self.request_timestamps.append(current_time)

            # Verdict tracking
            self.verdict_counts[result.final_verdict.value] += 1

            # Stage-specific metrics
            for stage, stage_result in result.stage_results.items():
                metrics = self.stage_metrics[stage.value]
                metrics["count"] += 1

                # Extract processing time if available
                if hasattr(stage_result, "processing_time_ms") and stage_result.processing_time_ms:
                    metrics["total_time"] += stage_result.processing_time_ms

                # Track blocks by stage
                if result.blocked_by == stage:
                    metrics["blocks"] += 1

    def record_error(self, error: str, context: dict[str, Any] | None = None) -> None:
        """Record an error occurrence"""
        with self._lock:
            self.error_count += 1
            self.last_errors.append({"timestamp": time.time(), "error": error, "context": context or {}})

    @property
    def avg_processing_time(self) -> float:
        """Average processing time in ms"""
        with self._lock:
            if not self.processing_times:
                return 0.0
            return float(sum(self.processing_times) / len(self.processing_times))

    @property
    def block_rate(self) -> float:
        """Percentage of requests blocked"""
        with self._lock:
            if self.total_requests == 0:
                return 0.0
            return (self.requests_blocked / self.total_requests) * 100

    def get_percentile(self, percentile: int) -> float:
        """Get processing time percentile"""
        with self._lock:
            if not self.processing_times:
                return 0.0

            sorted_times = sorted(self.processing_times)
            index = int((percentile / 100) * len(sorted_times))
            index = max(0, min(index, len(sorted_times) - 1))
            return float(sorted_times[index])

    def get_requests_per_minute(self) -> float:
        """Calculate requests per minute based on recent activity"""
        with self._lock:
            if len(self.request_timestamps) < 2:
                return 0.0

            current_time = time.time()
            # Count requests in the last minute
            cutoff_time = current_time - 60
            recent_requests = sum(1 for ts in self.request_timestamps if ts >= cutoff_time)
            return float(recent_requests)

    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        try:
            import psutil

            process = psutil.Process()
            return float(process.memory_info().rss / 1024 / 1024)
        except ImportError:
            return 0.0

    def get_snapshot(self) -> MetricsSnapshot:
        """Get current metrics snapshot"""
        with self._lock:
            # Stage performance summary
            stages_perf = {}
            for stage_name, metrics in self.stage_metrics.items():
                if metrics["count"] > 0:
                    avg_time = metrics["total_time"] / metrics["count"]
                    block_rate = (metrics["blocks"] / metrics["count"]) * 100
                else:
                    avg_time = 0.0
                    block_rate = 0.0

                stages_perf[stage_name] = {
                    "avg_processing_time_ms": avg_time,
                    "block_rate_percentage": block_rate,
                    "total_processed": metrics["count"],
                }

            return MetricsSnapshot(
                timestamp=time.time(),
                total_requests=self.total_requests,
                requests_blocked=self.requests_blocked,
                requests_forwarded=self.requests_forwarded,
                avg_processing_time_ms=self.avg_processing_time,
                p95_processing_time_ms=self.get_percentile(95),
                p99_processing_time_ms=self.get_percentile(99),
                requests_per_minute=self.get_requests_per_minute(),
                memory_usage_mb=self.get_memory_usage(),
                block_rate_percentage=self.block_rate,
                stages_performance=stages_perf,
            )

    def export_metrics(self) -> dict[str, Any]:
        """Export all metrics for analysis"""
        with self._lock:
            snapshot = self.get_snapshot()

            return {
                "snapshot": asdict(snapshot),
                "verdict_distribution": dict(self.verdict_counts),
                "recent_processing_times": list(self.processing_times),
                "error_count": self.error_count,
                "last_errors": list(self.last_errors),
            }

    def save_metrics(self, filepath: Path) -> None:
        """Save metrics to JSON file"""
        metrics_data = self.export_metrics()

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(metrics_data, f, indent=2, default=str)

    def reset(self) -> None:
        """Reset all metrics (useful for testing)"""
        with self._lock:
            self.total_requests = 0
            self.requests_blocked = 0
            self.requests_forwarded = 0
            self.processing_times.clear()
            self.request_timestamps.clear()
            self.stage_metrics.clear()
            self.verdict_counts.clear()
            self.error_count = 0
            self.last_errors.clear()

    def get_health_summary(self) -> dict[str, Any]:
        """Get a health summary for monitoring"""
        snapshot = self.get_snapshot()

        # Determine health status
        health_status = "healthy"
        issues = []

        # Check for issues
        if snapshot.avg_processing_time_ms > 2000:  # > 2s average
            health_status = "degraded"
            issues.append("High average processing time")

        if snapshot.block_rate_percentage > 50:  # > 50% blocks
            health_status = "warning"
            issues.append("High block rate")

        if self.error_count > 10:  # More than 10 errors
            health_status = "unhealthy"
            issues.append("High error count")

        return {
            "status": health_status,
            "issues": issues,
            "uptime_requests": snapshot.total_requests,
            "current_rpm": snapshot.requests_per_minute,
            "avg_latency_ms": snapshot.avg_processing_time_ms,
            "memory_mb": snapshot.memory_usage_mb,
            "block_rate": snapshot.block_rate_percentage,
        }
