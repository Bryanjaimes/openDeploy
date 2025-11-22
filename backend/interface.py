from abc import ABC, abstractmethod
from typing import Any, Dict, List

class AIModel(ABC):
    """
    Base class that all OpenDeploy models must inherit from.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the model"""
        pass

    @property
    @abstractmethod
    def input_type(self) -> str:
        """Type of input: 'text', 'image', 'audio'"""
        pass

    @abstractmethod
    def load(self):
        """Load model weights or resources"""
        pass

    @abstractmethod
    async def predict(self, input_data: Any) -> Any:
        """Run inference"""
        pass
