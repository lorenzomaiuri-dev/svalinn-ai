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


@router.post("/v1/chat/completions")
async def openai_proxy(
    chat_request: OpenAIChatRequest,
    request: Request,
    pipeline: Annotated[SvalinnAIPipeline, Depends(get_pipeline)],
    authorization: str | None = Header(None),
):
    """
    OpenAI-Compatible Endpoint (Reverse Proxy).
    1. Intercepts request -> Input Guardian
    2. Forwards to Upstream (OpenAI/Anthropic)
    3. Intercepts response -> Output Guardian
    4. Returns result to client
    """

    # --- 1. INPUT ANALYSIS ---
    # Extract the last user message to analyze
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

    # Force stream=False to enable Output Guardrails
    # (We cannot filter output if we stream it bit-by-bit)
    if chat_request.stream:
        logger.warning("⚠️ Client requested streaming. Disabling it to enforce Output Policy.")
        chat_request.stream = False

    try:
        upstream_response = await _forward_request(chat_request, authorization)
    except httpx.RequestError as e:
        logger.exception("Upstream connection failed")
        raise HTTPException(status_code=502, detail="Failed to connect to upstream LLM provider") from e

    if upstream_response.status_code != 200:
        # Pass upstream errors (like 401 Invalid Key, 429 Rate Limit) through directly
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            media_type=upstream_response.headers.get("content-type"),
        )

    # --- 3. OUTPUT ANALYSIS ---
    try:
        response_json = upstream_response.json()
        # Extract generated text from OpenAI format
        generated_text = response_json["choices"][0]["message"]["content"]
    except (KeyError, ValueError):
        # Could not parse response (maybe it's not chat completion?), pass it through blindly
        # or block it depending on strictness. For now, pass.
        logger.warning("Could not parse upstream response for verification. Passing through.")
        return JSONResponse(content=upstream_response.json(), status_code=upstream_response.status_code)

    if pipeline.output_guardian:
        # Use the pipeline's guardian directly
        # Note: We reuse the last_user_msg as context
        out_result = await pipeline.output_guardian.analyze(
            original_request=last_user_msg or "", generated_response=generated_text
        )

        if out_result.verdict == Verdict.UNSAFE:
            logger.warning("🚫 BLOCKED Output: Policy Violation detected in response.")
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": "Response blocked by Output Security Policy (Harmful Content Detected).",
                        "type": "invalid_request_error",
                        "code": "output_policy_violation",
                    }
                },
            )

    # --- 4. RETURN RESULT ---
    logger.info("✅ Output Safe. Returning to client.")
    return JSONResponse(content=response_json)


async def _forward_request(payload: OpenAIChatRequest, auth_header: str | None) -> httpx.Response:
    """Helper to send request to real OpenAI"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Construct full URL
        url = f"{UPSTREAM_BASE_URL}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header

        # dump the pydantic model to dict
        return await client.post(url, json=payload.model_dump(), headers=headers)
