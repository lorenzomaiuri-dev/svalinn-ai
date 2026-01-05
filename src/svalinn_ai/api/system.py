from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..core.pipeline import SvalinnAIPipeline

router = APIRouter()


class PolicyInfo(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool


class SystemStatus(BaseModel):
    status: str
    models_loaded: int
    active_policies: list[PolicyInfo]
    memory_usage_mb: float


async def get_pipeline(request: Request) -> SvalinnAIPipeline:
    return cast(SvalinnAIPipeline, request.app.state.pipeline)


@router.get("/v1/system/status", response_model=SystemStatus, tags=["System"])
async def get_system_status(pipeline: Annotated[SvalinnAIPipeline, Depends(get_pipeline)]) -> SystemStatus:
    """
    Get current system health and active configuration.
    """
    # Get basic health stats
    health = await pipeline.health_check()

    # TODO: GET POLICIES AND MODELS
    policies: list[PolicyInfo] = []

    return SystemStatus(
        status=health["status"],
        models_loaded=health["models_loaded"],
        active_policies=policies,
        memory_usage_mb=health["memory_usage_mb"],
    )
