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
        self.active_policy_string: str = ""

        # Load defaults
        self._load_defaults()

        if config_dir:
            self._load_policies(config_dir / "policies.yaml")
            self._load_prompts(config_dir / "prompts.yaml")

    def _load_defaults(self) -> None:
        """Load hardcoded defaults as fallback."""
        self.prompts = {
            "input_guardian": {
                # The system instruction
                "raw": "You are a security shield. Analyze for obfuscation. {active_policies} Reply UNSAFE or SAFE.",
                "normalized": "You are a security shield. Analyze for harm. Reply UNSAFE or SAFE.",
                # The ChatML Template (Composite Input)
                "template": (
                    "<|im_start|>system\n{system_prompt}<|im_end|>\n"
                    "<|im_start|>user\nRAW INPUT: {raw_input}\nNORMALIZED: {normalized_input}<|im_end|>\n"
                    "<|im_start|>assistant\n"
                ),
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
        self.active_policy_string = "   - No specific business policies defined."

    def _load_policies(self, path: Path) -> None:
        """Load and format policies from yaml."""
        if not path.exists():
            logger.debug(f"No policies file at {path}, using defaults.")
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            policies = data.get("policies", [])
            enabled_policies = [p for p in policies if p.get("enabled", False)]

            if not enabled_policies:
                self.active_policy_string = "   - No active business policies."
                return

            # Format into a bulleted list for the LLM
            formatted_lines = []
            for p in enabled_policies:
                line = f"   - {p['name']}: {p['description']}"
                formatted_lines.append(line)

            self.active_policy_string = "\n".join(formatted_lines)
            logger.info(f"Loaded {len(enabled_policies)} active guardrail policies.")

        except Exception:
            logger.exception(f"Failed to load policies from {path}")

    def _load_prompts(self, path: Path) -> None:
        """Load prompt templates from yaml."""
        if not path.exists():
            logger.warning(f"Prompts file not found at {path}, using defaults.")
            return

        try:
            with open(path, encoding="utf-8") as f:
                custom_prompts = yaml.safe_load(f) or {}

            # recursive update for top-level keys
            for key, value in custom_prompts.items():
                if key in self.prompts and isinstance(value, dict):
                    self.prompts[key].update(value)
                else:
                    self.prompts[key] = value

            logger.info(f"Loaded prompts from {path}")
        except Exception:
            logger.exception(f"Failed to load prompts from {path}")

    def format_input_prompt(self, raw_input: str, normalized_input: str) -> str:
        """
        Format the composite prompt for the Input Guardian.
        Injects policies into the system prompt BEFORE formatting the ChatML template.
        """
        config = self.prompts["input_guardian"]
        template = config.get("template", "")
        # For single-pass composite strategy, we use the 'raw' key as the main system instruction
        system = config.get("raw", "")

        # Inject policies before formatting the template
        if "{active_policies}" in system:
            system = system.replace("{active_policies}", self.active_policy_string)

        # Optional: If the system prompt itself expects {raw_input} (Few-Shot style),
        # we can inject it here to prevent key errors, though standard ChatML usually
        # puts input in the user block.
        if "{raw_input}" in system:
            # If using few-shot where examples include input in system prompt
            system = system.replace("{raw_input}", raw_input)
            system = system.replace("{normalized_input}", normalized_input)
            # If we put input in system, we might want to clear it from the user block
            # or let it appear twice. For now, let's assume standard behavior is preferred.

        try:
            return str(template.format(system_prompt=system, raw_input=raw_input, normalized_input=normalized_input))
        except KeyError:
            logger.exception("Missing key in input guardian template")
            return f"{system}\n\nRAW: {raw_input}\nNORM: {normalized_input}"

    def get_input_prompt(self, kind: str) -> str:
        """Get raw text of a specific prompt key (legacy/debug use)."""
        template: str = self.prompts["input_guardian"].get(kind, "")
        if "{active_policies}" in template:
            return template.replace("{active_policies}", self.active_policy_string)
        return template

    def format_honeypot_prompt(self, user_input: str) -> str:
        """Format the full prompt for the Honeypot model."""
        config = self.prompts["honeypot"]
        template = config.get("template", "")
        system = config.get("system", "")

        try:
            return str(template.format(system_prompt=system, user_input=user_input))
        except KeyError:
            logger.exception("Missing key in honeypot template")
            return f"{system}\n\n{user_input}"

    def format_output_guardian_prompt(self, original_request: str, generated_response: str) -> str:
        """Format the full prompt for the Output Guardian."""
        config = self.prompts["output_guardian"]
        template = config.get("template", "")
        system = config.get("system", "")

        try:
            return str(
                template.format(
                    system_prompt=system, original_request=original_request, generated_response=generated_response
                )
            )
        except KeyError:
            logger.exception("Missing key in output guardian template")
            return f"{system}\n\nReq: {original_request}\nResp: {generated_response}"
