import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..core.pipeline import SvalinnAIPipeline
from .analyze import router as analyze_router
from .gateway import router as gateway_router
from .system import router as system_router

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("svalinn.api")

# Global State
pipeline: SvalinnAIPipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application Lifespan Manager.
    Loads models on startup and unloads them on shutdown.
    """
    global pipeline
    logger.info("🚀 Svalinn AI is starting up...")

    # Auto-detect config path relative to where command is run
    config_dir = Path("config")

    try:
        # Initialize Core Pipeline (Loads models into RAM)
        pipeline = SvalinnAIPipeline(config_dir=config_dir)

        # Force a warm-up inference to allocate buffers
        logger.info("🔥 Warming up models...")
        _ = pipeline.input_guardian.model

        # Attach to app state for routers to access
        app.state.pipeline = pipeline

        logger.info("✅ System Ready. Listening for requests.")
    except Exception as e:
        logger.critical(f"❌ Startup Failed: {e}")
        raise

    yield

    # Cleanup
    logger.info("🛑 Shutting down...")
    if pipeline:
        pipeline.model_manager.unload_all()


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
async def health_check():
    """Health check endpoint for Docker/K8s"""
    if not pipeline:
        return JSONResponse({"status": "starting"}, status_code=503)

    stats = await pipeline.health_check()
    return {"status": "healthy", "metrics": stats}
