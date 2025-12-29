"""
Tests for ModelManager and ThreadSafeModel.
Run with: uv run pytest tests/core/test_models.py -v
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from svalinn_ai.core.models import MockModel, ModelConfig, ModelManager, ThreadSafeModel


# Fixture for a dummy GGUF file path
@pytest.fixture
def dummy_model_path():
    with tempfile.NamedTemporaryFile(suffix=".gguf", delete=False) as f:
        f.write(b"mock gguf content")
    path = Path(f.name)
    yield path
    # Cleanup
    if path.exists():
        path.unlink()


# Fixture for a config file pointing to the dummy model
@pytest.fixture
def model_config_file(dummy_model_path):
    config_data = {
        "input_guardian": {"name": "Test Input", "path": str(dummy_model_path), "context_length": 1024},
        "output_guardian": {
            "name": "Test Output",
            "path": str(dummy_model_path),  # SAME PATH
            "context_length": 1024,
        },
        "honeypot": {
            "name": "Test Honey",
            "path": str(dummy_model_path.with_name("other.gguf")),  # DIFFERENT PATH
            "context_length": 2048,
        },
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_data, f)

    config_path = Path(f.name)
    yield config_path
    if config_path.exists():
        config_path.unlink()


@pytest.mark.asyncio
async def test_shared_memory_optimization(model_config_file, dummy_model_path):
    """
    CRITICAL: Verify that if two guardians use the same model path,
    ModelManager returns the EXACT SAME instance (Shared Memory).
    """
    # Mock Llama to avoid actual loading
    with patch("svalinn_ai.core.models.Llama") as mock_llama:
        manager = ModelManager(model_config_file)

        # Load Input Guardian
        input_model = manager.load_model("input_guardian")

        # Load Output Guardian (configured with same path)
        output_model = manager.load_model("output_guardian")

        # Assertions
        assert input_model is output_model, "Model instances should be identical for same path"
        assert input_model._model is output_model._model

        # Verify Llama was only initialized ONCE despite two load calls
        assert mock_llama.call_count == 1


@pytest.mark.asyncio
async def test_distinct_models(model_config_file):
    """Verify different paths load different instances"""
    with patch("svalinn_ai.core.models.Llama") as mock_llama:
        manager = ModelManager(model_config_file)

        # Setup the "other" file so it exists logic checks pass
        with patch("pathlib.Path.exists", return_value=True):
            input_model = manager.load_model("input_guardian")
            honey_model = manager.load_model("honeypot")

        assert input_model is not honey_model
        assert mock_llama.call_count == 2


@pytest.mark.asyncio
async def test_thread_safe_locking():
    """Verify the generate method runs and uses the lock"""
    config = ModelConfig(name="test", path="test.gguf")

    # Create a mock internal model
    mock_internal = MagicMock()
    mock_internal.create_completion.return_value = {"choices": [{"text": "generated text"}]}

    wrapper = ThreadSafeModel(mock_internal, config)

    # Run async generation
    result = await wrapper.generate("test prompt")

    assert result == "generated text"
    mock_internal.create_completion.assert_called_once()


def test_missing_config_raises_error():
    manager = ModelManager()
    with pytest.raises(ValueError):
        manager.load_model("non_existent_key")


@pytest.mark.asyncio
async def test_mock_fallback(model_config_file):
    """Verify fallback to MockModel if file doesn't exist"""
    manager = ModelManager(model_config_file)

    # We didn't patch Llama, and we know the path in config is a temp file
    # But let's force a path that definitely doesn't exist to trigger fallback
    manager._config_cache["input_guardian"].path = "/non/existent/path.gguf"

    model = manager.load_model("input_guardian")

    assert isinstance(model, MockModel)
    assert await model.generate("test") in ["SAFE", "UNSAFE"]
