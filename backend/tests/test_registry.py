"""Unit tests for the AIModel interface and ModelRegistry."""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.interface import AIModel
from backend.registry import ModelRegistry


class StubModel(AIModel):
    @property
    def name(self):
        return "stub"

    @property
    def input_type(self):
        return "text"

    def load(self):
        self.ready = True

    async def predict(self, input_data):
        return {"echo": input_data}


class TestAIModel:
    def test_defaults(self):
        m = StubModel()
        assert m.ready is False
        assert m.version == "0.0.0"
        assert m.hardware_requirements == {"min_ram": 1, "min_vram": 0}

    def test_ready_setter(self):
        m = StubModel()
        m.load()
        assert m.ready is True


class TestModelRegistry:
    def test_register_and_get(self):
        reg = ModelRegistry()
        os.environ["OPENDEPLOY_LAZY_LOAD"] = "true"
        m = StubModel()
        reg.register(m)
        assert reg.get_model("stub") is m
        del os.environ["OPENDEPLOY_LAZY_LOAD"]

    def test_list_models(self):
        reg = ModelRegistry()
        os.environ["OPENDEPLOY_LAZY_LOAD"] = "true"
        reg.register(StubModel())
        models = reg.list_models()
        assert len(models) == 1
        assert models[0]["name"] == "stub"
        assert models[0]["input_type"] == "text"
        assert "version" in models[0]
        assert "ready" in models[0]
        del os.environ["OPENDEPLOY_LAZY_LOAD"]

    def test_get_missing_model(self):
        reg = ModelRegistry()
        assert reg.get_model("does-not-exist") is None
