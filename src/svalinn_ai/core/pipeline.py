import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ..guardians.honeypot import HoneypotExecutor
from ..guardians.input_guardian import InputGuardian
from ..guardians.output_guardian import OutputGuardian
from ..utils.logger import get_logger
from ..utils.metrics import MetricsCollector
from .models import ModelManager
from .normalizer import AdvancedTextNormalizer
from .types import (
    GuardianResult,
    HoneypotResponse,
    ProcessingStage,
    ShieldRequest,
    ShieldResult,
    Verdict,
)

logger = get_logger(__name__)


class SvalinnAIPipeline:
    def __init__(self, config_dir: Path | None = None):
        """
        Initialize the Svalinn AI Pipeline.

        Args:
            config_dir: Directory containing configuration files (models.yaml, normalization.yaml)
        """
        # 1. Load Normalization Configuration
        norm_config = {}
        if config_dir:
            norm_path = config_dir / "normalization.yaml"
            if norm_path.exists():
                try:
                    with open(norm_path, encoding="utf-8") as f:
                        norm_config = yaml.safe_load(f) or {}
                    logger.info(f"Loaded normalization config from {norm_path}")
                except Exception as e:
                    logger.warning(f"Failed to load normalization config from {norm_path}: {e}")
                    logger.info("Using default normalization rules")
            else:
                logger.debug(f"No normalization.yaml found in {config_dir}, using defaults")

        # Initialize Normalizer with loaded config
        self.normalizer = AdvancedTextNormalizer(config=norm_config)

        # 2. Initialize Model Manager
        # It handles its own loading of models.yaml
        self.model_manager = ModelManager(config_dir / "models.yaml" if config_dir else None)

        # 3. Initialize Metrics
        self.metrics = MetricsCollector()

        # 4. Initialize Guardians
        self.input_guardian = InputGuardian(self.model_manager)
        self.honeypot = HoneypotExecutor(self.model_manager)
        self.output_guardian = OutputGuardian(self.model_manager)

        logger.info("svalinn-ai pipeline initialized")

    async def process_request(self, user_input: str) -> ShieldResult:
        """Main processing pipeline"""
        start_time = time.time()

        # Create request object
        request = ShieldRequest(id=str(uuid.uuid4()), user_input=user_input, timestamp=datetime.now())

        stage_results: dict[ProcessingStage, GuardianResult | HoneypotResponse | ShieldRequest] = {}

        try:
            # Stage 1: Text Normalization
            normalized_input = self.normalizer.normalize(user_input)
            request.normalized_input = normalized_input

            obfuscation_analysis = self.normalizer.detect_obfuscation(user_input, normalized_input)
            logger.debug(f"Request {request.id}: Obfuscation analysis: {obfuscation_analysis}")

            # Stage 2: Input Guardian (Dual-Channel Analysis)
            input_result = await self.input_guardian.analyze(user_input, normalized_input)
            stage_results[ProcessingStage.INPUT_GUARDIAN] = input_result

            if input_result.verdict == Verdict.UNSAFE:
                total_time = int((time.time() - start_time) * 1000)
                result = ShieldResult(
                    request_id=request.id,
                    final_verdict=Verdict.UNSAFE,
                    blocked_by=ProcessingStage.INPUT_GUARDIAN,
                    total_processing_time_ms=total_time,
                    stage_results=stage_results,
                    should_forward=False,
                )
                self.metrics.record_request(result)
                logger.info(f"Request {request.id} blocked by Input Guardian")
                return result

            # Stage 3: Honeypot Execution
            honeypot_response = await self.honeypot.execute(user_input)
            stage_results[ProcessingStage.HONEYPOT] = honeypot_response

            # Stage 4: Output Guardian
            output_result = await self.output_guardian.analyze(
                original_request=user_input, generated_response=honeypot_response.generated_text
            )
            stage_results[ProcessingStage.OUTPUT_GUARDIAN] = output_result

            # Final Decision
            if output_result.verdict == Verdict.UNSAFE:
                final_verdict = Verdict.UNSAFE
                blocked_by = ProcessingStage.OUTPUT_GUARDIAN
                should_forward = False
                logger.info(f"Request {request.id} blocked by Output Guardian")
            else:
                final_verdict = Verdict.SAFE
                blocked_by = None
                should_forward = True
                logger.info(f"Request {request.id} approved - forwarding to production LLM")

            total_time = int((time.time() - start_time) * 1000)
            result = ShieldResult(
                request_id=request.id,
                final_verdict=final_verdict,
                blocked_by=blocked_by,
                total_processing_time_ms=total_time,
                stage_results=stage_results,
                should_forward=should_forward,
            )

            self.metrics.record_request(result)

        except Exception:
            logger.exception(f"Error processing request {request.id}")
            total_time = int((time.time() - start_time) * 1000)

            # Fail-safe: block on error
            result = ShieldResult(
                request_id=request.id,
                final_verdict=Verdict.UNSAFE,
                blocked_by=None,
                total_processing_time_ms=total_time,
                stage_results=stage_results,
                should_forward=False,
            )
            self.metrics.record_request(result)
            return result
        else:
            return result

    async def health_check(self) -> dict[str, Any]:
        """System health check"""
        return {
            "status": "healthy",
            "models_loaded": len(self.model_manager.models),
            "total_requests": self.metrics.total_requests,
            "avg_processing_time_ms": self.metrics.avg_processing_time,
            "memory_usage_mb": self._get_memory_usage(),
        }

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        import psutil

        process = psutil.Process()
        return float(process.memory_info().rss / 1024 / 1024)
