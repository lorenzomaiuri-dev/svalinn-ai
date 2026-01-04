from abc import ABC, abstractmethod
from typing import Any

from ..core.models import ModelManager, ThreadSafeModel
from ..core.prompts import PromptManager


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
