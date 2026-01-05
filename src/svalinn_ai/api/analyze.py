import logging
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from ..core.pipeline import SvalinnAIPipeline
from .schemas import AnalysisRequest, AnalysisResponse, StageMetrics, VerdictType

logger = logging.getLogger("svalinn.api")
router = APIRouter()


async def get_pipeline(request: Request) -> SvalinnAIPipeline:
    pipeline = cast(SvalinnAIPipeline, request.app.state.pipeline)
    if not pipeline:
        raise HTTPException(status_code=503, detail="System initializing")
    return pipeline


@router.post("/v1/analyze", response_model=AnalysisResponse, tags=["Internal Tools"])
async def analyze_text(
    payload: AnalysisRequest, pipeline: Annotated[SvalinnAIPipeline, Depends(get_pipeline)]
) -> AnalysisResponse:
    """
    Direct Classification Endpoint.
    Analyzes text and returns full security metadata.
    Does NOT forward to upstream LLMs.
    """
    logger.info(f"🔍 Analyzing direct request ({len(payload.text)} chars)")

    # Run the pipeline logic
    result = await pipeline.process_request(payload.text)

    # Map internal result to Public Schema
    stages_data = {}

    for stage, stage_result in result.stage_results.items():
        # Handle different internal types safely
        # GuardianResult has .verdict, .reasoning
        # HoneypotResponse has .generated_text (no verdict)

        verdict = VerdictType.SAFE
        reasoning = None

        if hasattr(stage_result, "verdict"):
            verdict = VerdictType(stage_result.verdict.value)
            reasoning = stage_result.reasoning

        stages_data[stage.value] = StageMetrics(
            verdict=verdict,
            latency_ms=getattr(stage_result, "processing_time_ms", 0),
            reasoning=reasoning,
            metadata=getattr(stage_result, "metadata", {}) or {},
        )

    return AnalysisResponse(
        request_id=result.request_id,
        final_verdict=VerdictType(result.final_verdict.value),
        blocked_by=result.blocked_by.value if result.blocked_by else None,
        total_latency_ms=result.total_processing_time_ms,
        stages=stages_data,
    )
