import logging
import os
import time
from typing import Dict, Type
from backend.interface import AIModel
from backend.metrics import metrics_store

logger = logging.getLogger(__name__)

class ModelRegistry:
    def __init__(self):
        self._models: Dict[str, AIModel] = {}

    def register(self, model_instance: AIModel):
        """Register a new model instance"""
        logger.info("Registering model: %s", model_instance.name)
        self._models[model_instance.name] = model_instance

        lazy_load = os.getenv("OPENDEPLOY_LAZY_LOAD", "false").lower() in {"1", "true", "yes"}
        if not lazy_load:
            start = time.perf_counter()
            model_instance.load()
            duration_ms = (time.perf_counter() - start) * 1000.0
            metrics_store.record_model_load(model_instance.name, duration_ms)

    def get_model(self, name: str) -> AIModel:
        return self._models.get(name)

    def list_models(self) -> list:
        return [
            {
                "name": m.name,
                "input_type": m.input_type,
                "version": getattr(m, "version", "0.0.0"),
                "ready": getattr(m, "ready", False),
            }
            for m in self._models.values()
        ]

# Global registry instance
registry = ModelRegistry()
