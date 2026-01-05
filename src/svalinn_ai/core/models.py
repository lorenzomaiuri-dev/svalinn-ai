import asyncio
import logging
import multiprocessing
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ModelConfigurationError(ValueError):
    """Raised when a requested model key is missing from the configuration."""

    def __init__(self, model_key: str):
        super().__init__(f"Model key '{model_key}' not found in configuration")


class ModelLoadError(RuntimeError):
    """Raised when an LLM instance fails to initialize."""

    def __init__(self, model_key: str):
        super().__init__(f"Could not load model {model_key}")


# Try importing llama_cpp, handle missing dependency gracefully
try:
    from llama_cpp import Llama

    HAS_LLAMA_CPP = True
except ImportError:
    HAS_LLAMA_CPP = False
    print("Warning: llama-cpp-python not installed. Using Mock models.")

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    name: str
    path: str
    context_length: int = 4096
    temperature: float = 0.1
    max_tokens: int = 64
    n_gpu_layers: int = 0
    n_threads: int | None = None
    enabled: bool = True  # Default to True for backward compatibility


class ThreadSafeModel:
    """
    Thread-safe wrapper around llama.cpp Llama instance.
    Ensures that only one inference request runs on the specific model instance at a time.
    """

    def __init__(self, model_instance: Any, config: ModelConfig):
        self._model = model_instance
        self._config = config
        self._lock = threading.Lock()
        self.model_path = str(Path(config.path).resolve())

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """
        Run inference in a separate thread to avoid blocking the asyncio event loop.
        Acquires a lock to ensure thread safety for the underlying C++ memory.
        """
        # Merge call-time kwargs with config defaults
        params = {
            "temperature": kwargs.get("temperature", self._config.temperature),
            "max_tokens": kwargs.get("max_tokens", self._config.max_tokens),
            "stop": kwargs.get("stop", []),
            "echo": False,
        }

        # Run CPU-bound task in thread pool
        return await asyncio.to_thread(self._generate_blocking, prompt, params)

    def _generate_blocking(self, prompt: str, params: dict[str, Any]) -> str:
        """Blocking generation call protected by lock."""
        with self._lock:
            try:
                # Raw completion
                output = self._model.create_completion(
                    prompt=prompt,
                    temperature=params["temperature"],
                    max_tokens=params["max_tokens"],
                    stop=params["stop"],
                    echo=params["echo"],
                )
                return str(output["choices"][0]["text"])
            except Exception:
                logger.exception(f"Inference error on {self._config.name}")
                raise


class MockModel(ThreadSafeModel):
    """Fallback mock model for testing or when llama-cpp is missing."""

    def __init__(self, config: ModelConfig):
        # No actual model instance, just config
        self._config = config
        self._lock = threading.Lock()
        self.model_path = str(Path(config.path).resolve()) if config.path else "mock_path"

    def _generate_blocking(self, prompt: str, params: dict[str, Any]) -> str:
        """Simulate latency and return dummy response."""
        import time

        time.sleep(0.1)  # Simulate inference time
        if "jailbreak" in prompt.lower():
            return "UNSAFE"
        return "SAFE"


class ModelManager:
    """
    Manages loading and lifecycle of LLM models.
    Implements the Registry Pattern to share model instances (RAM) across guardians.
    """

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path
        self._loaded_models: dict[str, ThreadSafeModel] = {}
        self._config_cache: dict[str, ModelConfig] = {}

        # Load configuration immediately
        self._load_config()

    def _load_config(self) -> None:
        """Load model configuration from YAML."""
        default_config = {
            "input_guardian": {
                "name": "microsoft/Phi-3.5-mini-instruct",
                "path": "models/phi-3.5-mini-instruct-q4_k_m.gguf",
                "temperature": 0.0,
                "context_length": 4096,
                "enabled": True,
            },
            "honeypot": {
                "name": "qwen/Qwen2.5-1.5B-Instruct",
                "path": "models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
                "temperature": 0.8,
                "context_length": 8192,
                "enabled": True,
            },
            "output_guardian": {
                "name": "microsoft/Phi-3.5-mini-instruct",
                "path": "models/phi-3.5-mini-instruct-q4_k_m.gguf",
                "temperature": 0.0,
                "context_length": 4096,
                "enabled": True,
            },
        }

        loaded_data: dict[str, Any] = {}
        if self.config_path and self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    loaded_data = yaml.safe_load(f) or {}
            except Exception:
                logger.exception("Failed to load model config")

        # Merge loaded with default, prioritizing loaded
        # Note: We don't overwrite the whole dict, we look up specific keys
        for key in default_config:
            # Get data from file or default
            data = loaded_data.get(key, default_config[key])
            self._config_cache[key] = ModelConfig(**data)

    def get_config(self, model_key: str) -> ModelConfig:
        """Get the configuration object for a specific model key."""
        config = self._config_cache.get(model_key)
        if not config:
            raise ModelConfigurationError(model_key)
        return config

    def load_model(self, model_key: str) -> ThreadSafeModel:
        """
        Load a model by its configuration key (e.g., 'input_guardian').
        If the underlying model file is already loaded, returns the existing instance.
        """
        config = self.get_config(model_key)

        if not config.enabled:
            logger.warning(f"Attempting to load disabled model: {model_key}")

        # Resolve absolute path to use as the cache key
        try:
            model_path_abs = str(Path(config.path).resolve())
        except OSError:
            # Fallback for mock paths that don't exist
            model_path_abs = config.path

        # 1. Check Cache (Shared Memory Strategy)
        if model_path_abs in self._loaded_models:
            logger.debug(f"Using cached model instance for {model_key} ({model_path_abs})")
            return self._loaded_models[model_path_abs]

        # 2. Load Model
        logger.info(f"Loading new model instance: {model_key} from {model_path_abs}")

        if HAS_LLAMA_CPP and Path(model_path_abs).exists():
            # Calculate threads: leave 1 core free if possible
            n_threads = config.n_threads or max(1, multiprocessing.cpu_count() - 1)

            try:
                llama_instance = Llama(
                    model_path=model_path_abs,
                    n_ctx=config.context_length,
                    n_gpu_layers=config.n_gpu_layers,  # 0 for CPU
                    n_threads=n_threads,
                    verbose=False,
                )
                wrapper = ThreadSafeModel(llama_instance, config)
            except Exception as e:
                logger.exception(f"Failed to load Llama model {model_path_abs}")
                raise ModelLoadError(model_key) from e
        else:
            if not Path(model_path_abs).exists() and HAS_LLAMA_CPP:
                logger.warning(f"Model file not found: {model_path_abs}. Falling back to MOCK.")
            wrapper = MockModel(config)

        # 3. Update Cache
        self._loaded_models[model_path_abs] = wrapper
        return wrapper

    def unload_all(self) -> None:
        """Force unload all models and clear cache."""
        self._loaded_models.clear()
        import gc

        gc.collect()

    def models(self) -> dict[str, ThreadSafeModel]:
        return self._loaded_models
