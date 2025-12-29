from abc import ABC, abstractmethod
from typing import Any

from ..core.models import MockModel, ModelManager


class BaseGuardian(ABC):
    def __init__(self, model_manager: ModelManager):
        self.model_manager: ModelManager = model_manager
        self._model: MockModel | None = None

    @property
    def model(self) -> MockModel:
        if self._model is None:
            self._model = self.model_manager.load_model(self.model_key)
        return self._model

    @property
    @abstractmethod
    def model_key(self) -> str:
        """Model key for this guardian"""
        pass

    @abstractmethod
    async def analyze(self, *args: tuple, **kwargs: dict[str, Any]) -> Any:
        """Analyze input and return result"""
        pass
