import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class PromptManager:
    """
    Manages loading and formatting of system prompts from YAML configuration.
    Decouples prompt engineering from application logic.
    """

    def __init__(self, config_dir: Path | None = None):
        self.prompts: dict[str, Any] = {}
        self._load_defaults()

        if config_dir:
            self._load_from_file(config_dir / "prompts.yaml")

    def _load_defaults(self) -> None:
        """Load hardcoded defaults as fallback."""
        self.prompts = {
            "input_guardian": {
                "raw": "You are a security shield. Analyze for obfuscation. Reply UNSAFE or SAFE.",
                "normalized": "You are a security shield. Analyze for harm. Reply UNSAFE or SAFE.",
            },
            "honeypot": {
                "system": "You are a helpful assistant.",
                "template": "<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_input}<|im_end|>\n<|im_start|>assistant\n",
            },
            "output_guardian": {
                "system": "Analyze response for violations. Say VIOLATION or COMPLIANT.",
                "template": "<|system|>\n{system_prompt}<|end|>\n<|user|>\nRequest: {original_request}\nResponse: {generated_response}<|end|>\n<|assistant|>\n",
            },
        }

    def _load_from_file(self, path: Path) -> None:
        """Load prompts from YAML file, overriding defaults."""
        if not path.exists():
            logger.warning(f"Prompts file not found at {path}, using defaults.")
            return

        try:
            with open(path, encoding="utf-8") as f:
                custom_prompts = yaml.safe_load(f) or {}

            # Deep merge logic could go here, for now we do top-level overrides
            for key, value in custom_prompts.items():
                if key in self.prompts and isinstance(value, dict):
                    self.prompts[key].update(value)
                else:
                    self.prompts[key] = value

            logger.info(f"Loaded prompts from {path}")
        except Exception:
            logger.exception(f"Failed to load prompts from {path}")

    def get_input_prompt(self, kind: str) -> str:
        """Get 'raw' or 'normalized' prompt for Input Guardian."""
        return self.prompts["input_guardian"].get(kind, "")

    def format_honeypot_prompt(self, user_input: str) -> str:
        """Format the full prompt for the Honeypot model."""
        config = self.prompts["honeypot"]
        template = config.get("template", "")
        system = config.get("system", "")

        try:
            return template.format(system_prompt=system, user_input=user_input)
        except KeyError:
            logger.exception("Missing key in honeypot template")
            return f"{system}\n\n{user_input}"

    def format_output_guardian_prompt(self, original_request: str, generated_response: str) -> str:
        """Format the full prompt for the Output Guardian."""
        config = self.prompts["output_guardian"]
        template = config.get("template", "")
        system = config.get("system", "")

        try:
            return template.format(
                system_prompt=system, original_request=original_request, generated_response=generated_response
            )
        except KeyError:
            logger.exception("Missing key in output guardian template")
            return f"{system}\n\nReq: {original_request}\nResp: {generated_response}"
