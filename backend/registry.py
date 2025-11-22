from typing import Dict, Type
from .interface import AIModel

class ModelRegistry:
    def __init__(self):
        self._models: Dict[str, AIModel] = {}

    def register(self, model_instance: AIModel):
        """Register a new model instance"""
        print(f"Registering model: {model_instance.name}")
        self._models[model_instance.name] = model_instance
        # In a real app, we might load lazily, but for now we load on register
        model_instance.load()

    def get_model(self, name: str) -> AIModel:
        return self._models.get(name)

    def list_models(self) -> list:
        return [
            {
                "name": m.name, 
                "input_type": m.input_type
            } 
            for m in self._models.values()
        ]

# Global registry instance
registry = ModelRegistry()
