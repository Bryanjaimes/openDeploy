from abc import ABC, abstractmethod
from typing import Any, Dict


class AIModel(ABC):
    """
    Base class that all OpenDeploy models must inherit from.

    Subclasses must define ``name``, ``input_type``, ``load``, and ``predict``.
    Optionally override ``version`` and ``hardware_requirements``.
    """

    _ready: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the model."""
        ...

    @property
    @abstractmethod
    def input_type(self) -> str:
        """Type of input: 'text', 'image', 'audio'."""
        ...

    @property
    def version(self) -> str:
        """Semantic version of the model artifact."""
        return "0.0.0"

    @property
    def ready(self) -> bool:
        """Whether the model has been loaded and is ready for inference."""
        return self._ready

    @ready.setter
    def ready(self, value: bool) -> None:
        self._ready = value

    @abstractmethod
    def load(self) -> None:
        """Load model weights or resources."""
        ...

    @abstractmethod
    async def predict(self, input_data: Any) -> Any:
        """Run inference on ``input_data`` and return a result dict."""
        ...

    @property
    def hardware_requirements(self) -> Dict[str, Any]:
        """Hardware requirements. Override in subclasses for GPU models."""
        return {"min_ram": 1, "min_vram": 0}
