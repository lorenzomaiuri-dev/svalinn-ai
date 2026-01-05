from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field  # Added ConfigDict


class VerdictType(str, Enum):
    SAFE = "SAFE"
    UNSAFE = "UNSAFE"


class AnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=32000, description="The raw text to analyze")
    request_id: str | None = Field(None, description="Optional client-side tracking ID")


class StageMetrics(BaseModel):
    verdict: VerdictType
    latency_ms: int
    reasoning: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisResponse(BaseModel):
    request_id: str
    final_verdict: VerdictType
    blocked_by: str | None = Field(None, description="Which guardian blocked the request (if any)")
    total_latency_ms: int

    # Detailed breakdown per stage (Input, Honey, Output)
    stages: dict[str, StageMetrics]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "final_verdict": "UNSAFE",
                "blocked_by": "input_guardian",
                "total_latency_ms": 450,
                "stages": {
                    "input_guardian": {
                        "verdict": "UNSAFE",
                        "latency_ms": 448,
                        "reasoning": "Policy Violation: Politics",
                        "metadata": {"model": "Qwen2.5-1.5B"},
                    }
                },
            }
        }
    )
