from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SvalinnAIConfig:
    """Main svalinn-AI configuration"""

    # Model paths and settings
    models_config_path: Path | None = None
    normalization_config_path: Path | None = None

    # Processing settings
    max_input_length: int = 8192
    max_output_length: int = 4096
    processing_timeout_seconds: int = 30

    # Performance settings
    max_concurrent_requests: int = 10
    enable_model_caching: bool = True

    # Logging and monitoring
    log_level: str = "INFO"
    log_file: Path | None = None
    enable_metrics: bool = True
    metrics_db_path: Path | None = None

    # Security settings
    fail_safe_mode: bool = True  # Block on errors
    enable_request_logging: bool = True
    anonymize_logs: bool = False


class ConfigManager:
    """Configuration management for svalinn-AI"""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path
        self._config: SvalinnAIConfig | None = None

    @property
    def config(self) -> SvalinnAIConfig:
        """Get current configuration (load if not cached)"""
        if self._config is None:
            self._config = self.load_config()
        return self._config

    def load_config(self, config_path: Path | None = None) -> SvalinnAIConfig:
        """Load configuration from file or create default"""
        path = config_path or self.config_path

        if path and path.exists():
            try:
                with open(path) as f:
                    config_data = yaml.safe_load(f)
                return SvalinnAIConfig(**config_data)
            except Exception as e:
                print(f"Warning: Could not load config from {path}: {e}")
                print("Using default configuration")

        return SvalinnAIConfig()  # Default config

    def save_config(self, config: SvalinnAIConfig | None = None, path: Path | None = None) -> None:
        """Save configuration to file"""
        config_to_save = config or self.config
        save_path = path or self.config_path

        if not save_path:
            error_msg = "No config path specified"
            raise ValueError(error_msg)

        save_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and handle Path objects
        config_dict = asdict(config_to_save)
        for key, value in config_dict.items():
            if isinstance(value, Path):
                config_dict[key] = str(value)

        with open(save_path, "w") as f:
            yaml.dump(config_dict, f, default_flow_style=False, indent=2)

    def update_config(self, **kwargs: dict[str, Any]) -> None:
        """Update configuration values"""
        if self._config is None:
            self._config = self.load_config()

        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
            else:
                error_msg = f"Invalid config key: {key}"
                raise ValueError(error_msg)

    @staticmethod
    def create_default_config_file(path: Path) -> None:
        """Create a default configuration file"""
        default_config = SvalinnAIConfig(
            models_config_path=path.parent / "models.yaml",
            normalization_config_path=path.parent / "normalization.yaml",
            log_file=path.parent / "logs" / "jbs.log",
            metrics_db_path=path.parent / "data" / "metrics.db",
        )

        manager = ConfigManager()
        manager.save_config(default_config, path)
