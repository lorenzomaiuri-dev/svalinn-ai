import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..core.pipeline import SvalinnAIPipeline
from .analyze import router as analyze_router
from .gateway import router as gateway_router
from .system import router as system_router

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("svalinn.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application Lifespan Manager.
    Loads models and persistent connections on startup.
    """
    logger.info("🚀 Svalinn AI is starting up...")

    # 1. Initialize Pipeline
    config_dir = Path("config")

    try:
        # Initialize Core Pipeline (Loads models into RAM)
        pipeline = SvalinnAIPipeline(config_dir=config_dir)
        logger.info("🔥 Warming up models...")
        if pipeline.input_guardian:
            _ = pipeline.input_guardian.model
        app.state.pipeline = pipeline
    except Exception:
        logger.critical("❌ Startup Failed")
        raise

    # 2. Initialize Shared HTTP Client (Connection Pooling)
    # Timeout set high for LLM generation
    app.state.http_client = httpx.AsyncClient(timeout=120.0)

    logger.info("✅ System Ready. Listening for requests.")

    yield

    # Cleanup
    logger.info("🛑 Shutting down...")
    if hasattr(app.state, "pipeline") and app.state.pipeline:
        app.state.pipeline.model_manager.unload_all()
    if hasattr(app.state, "http_client"):
        await app.state.http_client.aclose()


app = FastAPI(
    title="Svalinn AI Gateway",
    description="Drop-in Guardrails Proxy for OpenAI-compatible APIs",
    # TODO: version management
    version="1.0.0",
    lifespan=lifespan,
)

# 1. Gateway (OpenAI Proxy)
app.include_router(gateway_router)
# 2. Internal Tools (Direct Analysis)
app.include_router(analyze_router)
# 3. System Tools (Config inspection)
app.include_router(system_router)


@app.get("/health")
async def health_check() -> Any:
    if not getattr(app.state, "pipeline", None):
        return JSONResponse({"status": "starting"}, status_code=503)
    stats = await app.state.pipeline.health_check()
    return {"status": "healthy", "metrics": stats}
