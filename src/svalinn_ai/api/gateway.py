import logging
import os
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from ..core.pipeline import SvalinnAIPipeline
from ..core.types import Verdict
from .openai_schemas import OpenAIChatRequest

logger = logging.getLogger("svalinn.gateway")
router = APIRouter()

# Configuration
# Default to OpenAI, but can be overridden (e.g., http://localhost:11434/v1 for Ollama)
UPSTREAM_BASE_URL = os.getenv("UPSTREAM_BASE_URL", "https://api.openai.com/v1")


async def get_pipeline(request: Request) -> SvalinnAIPipeline:
    """Dependency to retrieve the pipeline from app state"""
    pipeline = request.app.state.pipeline
    if not pipeline:
        raise HTTPException(status_code=503, detail="Security layer initializing")
    return pipeline


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """Dependency to get shared HTTP client"""
    return request.app.state.http_client


@router.post("/v1/chat/completions")
async def openai_proxy(
    chat_request: OpenAIChatRequest,
    request: Request,
    pipeline: Annotated[SvalinnAIPipeline, Depends(get_pipeline)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    authorization: str | None = Header(None),
):
    """
    OpenAI-Compatible Endpoint (Reverse Proxy).
    """

    # --- 1. INPUT ANALYSIS ---
    last_user_msg = next((m.content for m in reversed(chat_request.messages) if m.role == "user"), None)

    if last_user_msg:
        logger.info(f"🛡️ Intercepting request for model '{chat_request.model}'")
        shield_result = await pipeline.process_request(last_user_msg)

        if shield_result.final_verdict == Verdict.UNSAFE:
            logger.warning(f"🚫 BLOCKED Input: {shield_result.blocked_by} | ID: {shield_result.request_id}")
            # Return an OpenAI-compatible error so clients handle it gracefully
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": f"Request blocked by Svalinn Guardrails ({shield_result.blocked_by.name}).",
                        "type": "invalid_request_error",
                        "param": "prompt",
                        "code": "security_policy_violation",
                    }
                },
            )

    # --- 2. FORWARD TO UPSTREAM ---
    logger.info("✅ Input Safe. Forwarding to Upstream...")

    # Disable streaming if Output Guardian is enabled
    # If disabled, we still disable streaming in this version because our proxy logic
    # (JSON parsing) assumes a complete response.
    # TODO: Implement StreamingResponse for pass-through mode
    if chat_request.stream:
        if pipeline.output_guardian:
            logger.warning("⚠️ Streaming disabled to enforce Output Policy.")
        chat_request.stream = False

    try:
        # Use shared client
        upstream_response = await _forward_request(client, chat_request, authorization)
    except httpx.RequestError as e:
        logger.exception("Upstream connection failed")
        raise HTTPException(status_code=502, detail="Failed to connect to upstream LLM provider") from e

    if upstream_response.status_code != 200:
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            media_type=upstream_response.headers.get("content-type"),
        )

    # --- 3. OUTPUT ANALYSIS ---
    try:
        response_json = upstream_response.json()
        generated_text = response_json["choices"][0]["message"]["content"]
    except (KeyError, ValueError):
        logger.warning("Could not parse upstream response. Skipping output check.")
        return JSONResponse(content=upstream_response.json(), status_code=upstream_response.status_code)

    # Only run analysis if enabled in config
    if pipeline.output_guardian:
        out_result = await pipeline.output_guardian.analyze(
            original_request=last_user_msg or "", generated_response=generated_text
        )

        if out_result.verdict == Verdict.UNSAFE:
            logger.warning("🚫 BLOCKED Output: Policy Violation detected in response.")
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": "Response blocked by Output Security Policy.",
                        "type": "invalid_request_error",
                        "code": "output_policy_violation",
                    }
                },
            )
        logger.info("✅ Output Verified Safe.")
    else:
        logger.info("⏩ Output Guardian disabled. Returning upstream response.")

    # --- 4. RETURN RESULT ---
    return JSONResponse(content=response_json)


async def _forward_request(
    client: httpx.AsyncClient, payload: OpenAIChatRequest, auth_header: str | None
) -> httpx.Response:
    """Helper to send request using shared client"""
    url = f"{UPSTREAM_BASE_URL}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    return await client.post(url, json=payload.model_dump(), headers=headers)
