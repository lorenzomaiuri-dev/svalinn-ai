from abc import ABC, abstractmethod
from typing import Any

from ..core.models import ModelManager, ThreadSafeModel
from ..core.prompts import PromptManager


class GuardianParameterError(ValueError):
    """Exception raised when required text parameters are missing."""

    def __init__(self, message: str = "Missing required text parameters"):
        super().__init__(message)


class BaseGuardian(ABC):
    """
    Abstract base class for all security guardians.
    Handles lazy model loading and common interface definitions.
    """

    def __init__(self, model_manager: ModelManager, prompt_manager: PromptManager):
        self.model_manager: ModelManager = model_manager
        self.prompt_manager: PromptManager = prompt_manager
        self._model: ThreadSafeModel | None = None

    @property
    def model(self) -> ThreadSafeModel:
        """
        Lazy load the model instance on first access.
        This ensures we don't load gigabytes of weights until the pipeline actually starts.
        """
        if self._model is None:
            self._model = self.model_manager.load_model(self.model_key)
        return self._model

    @property
    @abstractmethod
    def model_key(self) -> str:
        """Config key for this guardian (e.g., 'input_guardian', 'honeypot')"""
        pass

    @abstractmethod
    async def analyze(self, *args: Any, **kwargs: Any) -> Any:
        """Main analysis logic"""
        pass

    def _extract_text_parameters(self, *args: Any, **kwargs: Any) -> tuple[str, str]:
        """Standardized parameter extraction for all guardians."""
        if len(args) == 2:
            return str(args[0]), str(args[1])

        # Fallback to looking for string values in kwargs if specific keys aren't found
        values = [str(v) for v in kwargs.values() if isinstance(v, str | int | float)]
        if len(values) >= 2:
            return values[0], values[1]

        raise GuardianParameterError()
