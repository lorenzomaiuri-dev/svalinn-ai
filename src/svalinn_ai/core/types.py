import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class Verdict(Enum):
    SAFE = "SAFE"
    UNSAFE = "UNSAFE"


class ProcessingStage(Enum):
    INPUT_GUARDIAN = "input_guardian"
    HONEYPOT = "honeypot"
    OUTPUT_GUARDIAN = "output_guardian"


@dataclass
class GuardianResult:
    verdict: Verdict
    confidence: float
    reasoning: str | None = None
    processing_time_ms: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class HoneypotResponse:
    generated_text: str
    processing_time_ms: int
    metadata: dict[str, Any] | None = None


@dataclass
class ShieldRequest:
    id: str
    user_input: str
    timestamp: datetime
    normalized_input: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())


@dataclass
class ShieldResult:
    request_id: str
    final_verdict: Verdict
    blocked_by: ProcessingStage | None
    total_processing_time_ms: int
    stage_results: dict[ProcessingStage, Any]
    should_forward: bool

    @property
    def is_safe(self) -> bool:
        return self.final_verdict in [Verdict.SAFE]
