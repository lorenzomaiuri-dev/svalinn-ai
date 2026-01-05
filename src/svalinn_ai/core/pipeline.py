import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ..guardians.honeypot import HoneypotExecutor
from ..guardians.input_guardian import InputGuardian
from ..guardians.output_guardian import OutputGuardian
from ..utils.analytics import AnalyticsEngine
from ..utils.logger import get_logger
from ..utils.metrics import MetricsCollector
from .models import ModelManager
from .normalizer import AdvancedTextNormalizer
from .prompts import PromptManager
from .types import (
    ProcessingStage,
    ShieldRequest,
    ShieldResult,
    Verdict,
)

logger = get_logger(__name__)


class SvalinnAIPipeline:
    prompt_manager: PromptManager
    normalizer: AdvancedTextNormalizer
    model_manager: ModelManager
    metrics: MetricsCollector
    analytics: AnalyticsEngine
    input_guardian: InputGuardian | None
    honeypot: HoneypotExecutor | None
    output_guardian: OutputGuardian | None

    def __init__(self, config_dir: Path | None = None):
        """
        Initialize the Svalinn AI Pipeline.

        Args:
            config_dir: Directory containing configuration files (models.yaml, normalization.yaml)
                        If None, tries to auto-discover 'config' directory in CWD.
        """
        # 1. Auto-discover config directory
        if config_dir is None:
            cwd_config = Path("config")
            if cwd_config.exists() and cwd_config.is_dir():
                config_dir = cwd_config
                logger.debug(f"Auto-detected config directory: {config_dir.absolute()}")

        # 2. Initialize Prompt Manager
        self.prompt_manager = PromptManager(config_dir)

        # 3. Load Normalization Configuration
        norm_config: dict[str, Any] = {}
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

        # 4. Initialize Model Manager
        model_config_path = (config_dir / "models.yaml") if config_dir else None
        self.model_manager = ModelManager(model_config_path)

        # 5. Initialize Metrics and Analytics
        self.metrics = MetricsCollector()
        data_dir = Path("data")
        self.analytics = AnalyticsEngine(data_dir / "svalinn_logs.duckdb")

        # 6. Initialize Guardians

        # Input Guardian is core, usually enabled, but we check config anyway
        if self._is_model_enabled("input_guardian"):
            self.input_guardian = InputGuardian(self.model_manager, self.prompt_manager)
        else:
            self.input_guardian = None
            logger.warning("Input Guardian is DISABLED in config.")

        # Honeypot
        if self._is_model_enabled("honeypot"):
            self.honeypot = HoneypotExecutor(self.model_manager, self.prompt_manager)
        else:
            self.honeypot = None
            logger.info("Honeypot disabled (Speed Mode).")

        # Output Guardian
        if self._is_model_enabled("output_guardian"):
            self.output_guardian = OutputGuardian(self.model_manager, self.prompt_manager)
        else:
            self.output_guardian = None
            logger.info("Output Guardian disabled (Speed Mode).")

        logger.info("svalinn-ai pipeline initialized")

    def _is_model_enabled(self, key: str) -> bool:
        """Helper to check model config status"""
        try:
            return self.model_manager.get_config(key).enabled
        except Exception:
            return True  # Default to True if config missing

    async def process_request(self, user_input: str) -> ShieldResult:
        """Main processing pipeline"""
        start_time = time.time()
        request = ShieldRequest(id=str(uuid.uuid4()), user_input=user_input, timestamp=datetime.now())
        stage_results: dict[ProcessingStage, Any] = {}

        try:
            # Stage 1: Text Normalization
            normalized_input = self.normalizer.normalize(user_input)
            request.normalized_input = normalized_input

            # Stage 2: Input Guardian (If Enabled)
            if self.input_guardian:
                input_result = await self.input_guardian.analyze(user_input, normalized_input)
                stage_results[ProcessingStage.INPUT_GUARDIAN] = input_result

                if input_result.verdict == Verdict.UNSAFE:
                    return self._finalize_result(
                        request, Verdict.UNSAFE, ProcessingStage.INPUT_GUARDIAN, stage_results, start_time, False
                    )

            # Stage 3: Honeypot Execution (If Enabled)
            honeypot_response = None
            if self.honeypot:
                honeypot_response = await self.honeypot.execute(user_input)
                stage_results[ProcessingStage.HONEYPOT] = honeypot_response
            else:
                # If honeypot is disabled, we cannot run internal Output Guardian check
                # We consider this "Speed Mode" success
                return self._finalize_result(request, Verdict.SAFE, None, stage_results, start_time, True)

            # Stage 4: Output Guardian (If Enabled and Honeypot ran)
            output_result = None
            if self.output_guardian and honeypot_response:
                output_result = await self.output_guardian.analyze(
                    original_request=user_input, generated_response=honeypot_response.generated_text
                )
                stage_results[ProcessingStage.OUTPUT_GUARDIAN] = output_result

                if output_result.verdict == Verdict.UNSAFE:
                    return self._finalize_result(
                        request, Verdict.UNSAFE, ProcessingStage.OUTPUT_GUARDIAN, stage_results, start_time, False
                    )

            # Final Decision: SAFE
            return self._finalize_result(request, Verdict.SAFE, None, stage_results, start_time, True)

        except Exception:
            logger.exception(f"Error processing request {request.id}")
            # Fail-safe: Block on internal error
            return self._finalize_result(request, Verdict.UNSAFE, None, stage_results, start_time, False)

    def _finalize_result(
        self,
        request: ShieldRequest,
        verdict: Verdict,
        blocked_by: ProcessingStage | None,
        stages: dict,
        start_time: float,
        forward: bool,
    ) -> ShieldResult:
        """Helper to construct result and log it"""
        total_time = int((time.time() - start_time) * 1000)

        if verdict == Verdict.UNSAFE and blocked_by:
            logger.info(f"Request {request.id} blocked by {blocked_by.value}")
        elif verdict == Verdict.SAFE:
            logger.info(f"Request {request.id} approved")

        result = ShieldResult(
            request_id=request.id,
            final_verdict=verdict,
            blocked_by=blocked_by,
            total_processing_time_ms=total_time,
            stage_results=stages,
            should_forward=forward,
        )

        # 1. Update Metrics
        self.metrics.record_request(result)

        # 2. Log to Analytics (Async safe via DuckDB)
        if hasattr(self, "analytics") and self.analytics:
            self.analytics.log_request(result, request.user_input)

        return result

    async def health_check(self) -> dict[str, Any]:
        """System health check"""
        models_count = len(self.model_manager.models())

        return {
            "status": "healthy",
            "models_loaded": models_count,
            "total_requests": self.metrics.total_requests,
            "avg_processing_time_ms": self.metrics.avg_processing_time,
            "memory_usage_mb": self._get_memory_usage(),
        }

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        try:
            import psutil

            process = psutil.Process()
            return float(process.memory_info().rss / 1024 / 1024)
        except ImportError:
            return 0.0
