from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ModelConfig:
    name: str
    path: str
    context_length: int = 4096
    temperature: float = 0.1
    max_tokens: int = 512
    n_gpu_layers: int = 0


# TODO: REPLACE WITH ACTUAL MODEL
class MockModel:
    """Mock model for testing - replace with actual llama.cpp integration"""

    def __init__(self, config: ModelConfig):
        self.config = config

    def generate(self, prompt: str, **kwargs: dict[str, Any]) -> str:
        """Mock generation - returns predetermined responses for testing"""
        if "jailbreak" in prompt.lower() or "unsafe" in prompt.lower():
            return "UNSAFE" if "guardian" in self.config.name.lower() else "I cannot help with that request."
        return "SAFE" if "guardian" in self.config.name.lower() else "This is a safe response."


class ModelManager:
    def __init__(self, config_path: Path | None = None):
        self.config = self._load_config(config_path)
        self.models: dict[str, MockModel] = {}

    def _load_config(self, config_path: Path | None) -> dict[str, Any]:
        """Load model configuration from YAML"""
        default_config = {
            "input_guardian": ModelConfig(
                name="microsoft/Phi-3.5-mini-instruct", path="models/phi-3.5-mini-instruct-q4_k_m.gguf", temperature=0.1
            ),
            "honeypot": ModelConfig(
                name="qwen/Qwen2.5-1.5B-Instruct", path="models/qwen2.5-1.5b-instruct-q4_k_m.gguf", temperature=0.8
            ),
            "output_guardian": ModelConfig(
                name="microsoft/Phi-3.5-mini-instruct", path="models/phi-3.5-mini-instruct-q4_k_m.gguf", temperature=0.1
            ),
        }

        if config_path and config_path.exists():
            try:
                with open(config_path) as f:
                    loaded_config = yaml.safe_load(f)
            except Exception as e:
                print(f"Warning: Could not load config from {config_path}: {e}")
            else:
                if loaded_config:
                    for key, value in loaded_config.items():
                        if key in default_config:
                            default_config[key] = ModelConfig(**value)

        return default_config

    def load_model(self, model_key: str) -> MockModel:
        """Load a model for inference (stub for now)"""
        if model_key in self.models:
            return self.models[model_key]

        config = self.config.get(model_key)
        if not config:
            error_msg = f"Model {model_key} not found in config"
            raise ValueError(error_msg)

        # TODO: Implement actual llama-cpp-python loading
        # from llama_cpp import Llama
        # model = Llama(
        #     model_path=config.path,
        #     n_ctx=config.context_length,
        #     n_gpu_layers=config.n_gpu_layers,
        #     verbose=False
        # )

        # For now, return a mock model
        self.models[model_key] = MockModel(config)
        return self.models[model_key]
