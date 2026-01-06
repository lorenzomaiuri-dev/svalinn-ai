import logging
import os
from typing import Annotated, cast

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

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
    pipeline = cast(SvalinnAIPipeline, request.app.state.pipeline)
    if not pipeline:
        raise HTTPException(status_code=503, detail="Security layer initializing")
    return pipeline


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """Dependency to get shared HTTP client"""
    return cast(httpx.AsyncClient, request.app.state.http_client)


@router.post("/v1/chat/completions")
async def openai_proxy(
    chat_request: OpenAIChatRequest,
    pipeline: Annotated[SvalinnAIPipeline, Depends(get_pipeline)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    authorization: str | None = Header(None),
) -> Response:
    """OpenAI-Compatible Endpoint (Reverse Proxy)."""

    # 1. Input Guarding
    last_user_msg = next((m.content for m in reversed(chat_request.messages) if m.role == "user"), None)
    if last_user_msg:
        input_error = await _run_input_guard(pipeline, chat_request.model, last_user_msg)
        if input_error:
            return input_error

    # 2. Handle Streaming logic
    should_stream = chat_request.stream and not pipeline.output_guardian
    if chat_request.stream and not should_stream:
        logger.warning("⚠️ Streaming disabled to enforce Output Policy.")
        chat_request.stream = False

    if should_stream:
        return await _handle_streaming_response(client, chat_request, authorization)

    # 3. Forward Non-Streaming Request
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

    # 4. Output Guarding & Final Response
    return await _process_output_and_respond(pipeline, last_user_msg, upstream_response)


async def _run_input_guard(pipeline: SvalinnAIPipeline, model: str, message: str) -> JSONResponse | None:
    """Analyzes input and returns a JSONResponse error if unsafe."""
    logger.info(f"🛡️ Intercepting request for model '{model}'")
    shield_result = await pipeline.process_request(message)

    if shield_result.final_verdict == Verdict.UNSAFE:
        logger.warning(f"🚫 BLOCKED Input: {shield_result.blocked_by} | ID: {shield_result.request_id}")
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": f"Request blocked by Svalinn Guardrails ({shield_result.blocked_by}).",
                    "type": "invalid_request_error",
                    "param": "prompt",
                    "code": "security_policy_violation",
                }
            },
        )
    return None


async def _handle_streaming_response(
    client: httpx.AsyncClient, chat_request: OpenAIChatRequest, authorization: str | None
) -> StreamingResponse:
    """Proxies the streaming response from upstream."""
    url = f"{UPSTREAM_BASE_URL}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    try:
        req = client.build_request("POST", url, json=chat_request.model_dump(), headers=headers)
        r = await client.send(req, stream=True)
        return StreamingResponse(
            r.aiter_bytes(),
            status_code=r.status_code,
            media_type=r.headers.get("content-type"),
            background=BackgroundTask(r.aclose),
        )
    except httpx.RequestError as e:
        logger.exception("Upstream connection failed during stream init")
        raise HTTPException(status_code=502, detail="Failed to connect to upstream LLM provider") from e


async def _process_output_and_respond(
    pipeline: SvalinnAIPipeline, last_user_msg: str | None, upstream_response: httpx.Response
) -> Response:
    """Parses upstream response, runs output guardian, and returns final JSON."""
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
