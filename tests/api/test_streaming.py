from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from svalinn_ai.api.server import app
from svalinn_ai.core.types import ShieldResult, Verdict


@pytest.fixture
def mock_pipeline_streaming():
    mock = MagicMock()
    # Mock Input Guardian passing
    safe_result = ShieldResult(
        request_id="req-stream",
        final_verdict=Verdict.SAFE,
        blocked_by=None,
        total_processing_time_ms=10,
        stage_results={},
        should_forward=True,
    )
    mock.process_request = AsyncMock(return_value=safe_result)

    # OUTPUT GUARDIAN MUST BE NONE for streaming to work
    mock.output_guardian = None

    return mock


def test_streaming_proxy(mock_pipeline_streaming):
    client = TestClient(app)

    # 1. Patch Pipeline
    with patch("svalinn_ai.api.server.SvalinnAIPipeline", return_value=mock_pipeline_streaming):
        app.state.pipeline = mock_pipeline_streaming

        # 2. Mock HTTP Client
        mock_http_client = AsyncMock()
        app.state.http_client = mock_http_client

        # Mock Response
        async def byte_generator():
            yield b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
            yield b'data: {"choices": [{"delta": {"content": " World"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/event-stream"}
        mock_response.aiter_bytes = byte_generator
        mock_response.aclose = AsyncMock()

        mock_http_client.send.return_value = mock_response
        mock_http_client.build_request.return_value = "mock_request"

        # 3. Request
        payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hi"}], "stream": True}
        response = client.post("/v1/chat/completions", json=payload)

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        content = response.content.decode()
        assert "Hello" in content
        assert "World" in content

        # Verify build_request was called (part of proxy logic)
        mock_http_client.build_request.assert_called()
        mock_http_client.send.assert_called_once()
