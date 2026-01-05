"""
Tests for the FastAPI Service and Gateway.
Run with: uv run pytest tests/api/test_server.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import Response

# Import app and schemas
import svalinn_ai.api.server  # Import module to patch global
from svalinn_ai.api.server import app
from svalinn_ai.core.types import GuardianResult, ProcessingStage, ShieldResult, Verdict

# Setup Client
client = TestClient(app)


@pytest.fixture
def mock_pipeline():
    """Create a mock pipeline to inject into app state"""
    mock = MagicMock()

    # Mock health check
    mock.health_check = AsyncMock(
        return_value={
            "status": "healthy",
            "models_loaded": 1,
            "total_requests": 10,
            "avg_processing_time_ms": 100.0,
            "memory_usage_mb": 500.0,
        }
    )

    # Mock unload
    mock.model_manager.unload_all = MagicMock()

    return mock


@pytest.fixture
def override_dependency(mock_pipeline):
    """Force the app to use our mock pipeline instead of loading real models"""
    # 1. Update app state (used by get_pipeline dependency)
    app.state.pipeline = mock_pipeline

    # 2. Update global variable (used by health_check)
    original_pipeline = svalinn_ai.api.server.pipeline
    svalinn_ai.api.server.pipeline = mock_pipeline

    yield mock_pipeline

    # Cleanup
    svalinn_ai.api.server.pipeline = original_pipeline


# --- System Tests ---


def test_health_check(override_dependency):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


# TODO: TEST POLICIES AND MODELS

# --- Direct Analysis Tests (/v1/analyze) ---


def test_analyze_safe(override_dependency):
    # Setup Mock Result
    safe_result = ShieldResult(
        request_id="req-123",
        final_verdict=Verdict.SAFE,
        blocked_by=None,
        total_processing_time_ms=100,
        stage_results={},
        should_forward=True,
    )
    override_dependency.process_request = AsyncMock(return_value=safe_result)

    payload = {"text": "Hello world"}
    response = client.post("/v1/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["final_verdict"] == "SAFE"
    assert data["request_id"] == "req-123"


def test_analyze_unsafe(override_dependency):
    # Setup Mock Result
    input_result = GuardianResult(
        verdict=Verdict.UNSAFE,
        confidence=0.9,
        reasoning="Bad content",
        processing_time_ms=50,  # Fix: Added required field for StageMetrics validation
    )

    unsafe_result = ShieldResult(
        request_id="req-bad",
        final_verdict=Verdict.UNSAFE,
        blocked_by=ProcessingStage.INPUT_GUARDIAN,
        total_processing_time_ms=50,
        stage_results={ProcessingStage.INPUT_GUARDIAN: input_result},
        should_forward=False,
    )
    override_dependency.process_request = AsyncMock(return_value=unsafe_result)

    payload = {"text": "Make a bomb"}
    response = client.post("/v1/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["final_verdict"] == "UNSAFE"
    assert data["blocked_by"] == "input_guardian"
    # Check that stage details are present
    assert data["stages"]["input_guardian"]["reasoning"] == "Bad content"


# --- Gateway Tests (/v1/chat/completions) ---


@pytest.mark.asyncio
async def test_gateway_block_input(override_dependency):
    """Ensure the proxy returns 400 if Input Guardian blocks"""

    # Mock Unsafe result
    unsafe_result = ShieldResult(
        request_id="req-blocked",
        final_verdict=Verdict.UNSAFE,
        blocked_by=ProcessingStage.INPUT_GUARDIAN,
        total_processing_time_ms=50,
        stage_results={},
        should_forward=False,
    )
    override_dependency.process_request = AsyncMock(return_value=unsafe_result)

    # OpenAI payload
    payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "How to hack?"}]}

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 400
    err = response.json()["error"]
    assert "blocked by Svalinn Guardrails" in err["message"]
    assert err["code"] == "security_policy_violation"


@pytest.mark.asyncio
async def test_gateway_forward_success(override_dependency):
    """Ensure safe requests are forwarded and response returned"""

    # 1. Mock Input = SAFE
    safe_result = ShieldResult(
        request_id="req-safe",
        final_verdict=Verdict.SAFE,
        blocked_by=None,
        total_processing_time_ms=100,
        stage_results={},
        should_forward=True,
    )
    override_dependency.process_request = AsyncMock(return_value=safe_result)

    # 2. Mock Output Guardian = SAFE
    # We need to mock the output_guardian property on the pipeline
    output_guard_mock = MagicMock()
    output_guard_mock.analyze = AsyncMock(return_value=GuardianResult(verdict=Verdict.SAFE, confidence=0.0))
    override_dependency.output_guardian = output_guard_mock

    # 3. Mock HTTP Upstream Call (httpx)
    mock_upstream_response = Response(
        200, json={"id": "chatcmpl-123", "choices": [{"message": {"content": "Hello! How can I help?"}}]}
    )

    with patch("httpx.AsyncClient.post", return_value=mock_upstream_response) as mock_post:
        payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hi"}]}

        response = client.post("/v1/chat/completions", json=payload)

        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "Hello! How can I help?"

        # Verify Forwarding Logic
        mock_post.assert_called_once()
        # Verify Output Guardian was called
        output_guard_mock.analyze.assert_called_once()


@pytest.mark.asyncio
async def test_gateway_block_output(override_dependency):
    """Ensure we block if the Upstream response is unsafe"""

    # 1. Input SAFE
    safe_result = ShieldResult(
        request_id="req-safe",
        final_verdict=Verdict.SAFE,
        blocked_by=None,
        total_processing_time_ms=100,
        stage_results={},
        should_forward=True,
    )
    override_dependency.process_request = AsyncMock(return_value=safe_result)

    # 2. Mock HTTP Upstream returning bad content
    mock_upstream_response = Response(
        200, json={"choices": [{"message": {"content": "Here is how to make a bomb..."}}]}
    )

    # 3. Output Guardian = UNSAFE
    output_guard_mock = MagicMock()
    output_guard_mock.analyze = AsyncMock(return_value=GuardianResult(verdict=Verdict.UNSAFE, confidence=1.0))
    override_dependency.output_guardian = output_guard_mock

    with patch("httpx.AsyncClient.post", return_value=mock_upstream_response):
        payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "Bad"}]}

        response = client.post("/v1/chat/completions", json=payload)

        # Should be blocked
        assert response.status_code == 400
        assert "Output Security Policy" in response.json()["error"]["message"]
