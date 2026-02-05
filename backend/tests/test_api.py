"""Unit tests for the OpenDeploy API endpoints."""

import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("OPENDEPLOY_API_KEY", "test-key-123")


@pytest.fixture(autouse=True)
def _patch_model_loading():
    """Prevent real model loading during tests."""
    with patch("backend.loader.load_plugins"):
        yield


@pytest.fixture()
def client():
    from backend.main import app

    return TestClient(app)


API_HEADERS = {"X-API-Key": "test-key-123"}


class TestHealthAndRoot:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "OpenDeploy" in resp.json()["message"]

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestAuthentication:
    def test_list_models_no_key(self, client):
        resp = client.get("/models")
        assert resp.status_code == 403

    def test_list_models_wrong_key(self, client):
        resp = client.get("/models", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 403

    def test_list_models_valid_key(self, client):
        resp = client.get("/models", headers=API_HEADERS)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestPredictEndpoint:
    def test_predict_unknown_model(self, client):
        resp = client.post(
            "/models/nonexistent/predict",
            headers=API_HEADERS,
            data={"text_input": "hello"},
        )
        assert resp.status_code == 404

    def test_predict_text_model(self, client):
        from backend.registry import registry

        mock_model = MagicMock()
        mock_model.name = "test-model"
        mock_model.input_type = "text"
        mock_model.ready = True
        mock_model.predict = AsyncMock(return_value={"response": "ok"})
        registry._models["test-model"] = mock_model

        resp = client.post(
            "/models/test-model/predict",
            headers=API_HEADERS,
            data={"text_input": "hello"},
        )
        assert resp.status_code == 200
        assert resp.json()["response"] == "ok"

        # Cleanup
        del registry._models["test-model"]

    def test_predict_text_model_missing_input(self, client):
        from backend.registry import registry

        mock_model = MagicMock()
        mock_model.name = "test-text"
        mock_model.input_type = "text"
        mock_model.ready = True
        registry._models["test-text"] = mock_model

        resp = client.post(
            "/models/test-text/predict",
            headers=API_HEADERS,
        )
        assert resp.status_code == 400

        del registry._models["test-text"]


class TestMetrics:
    def test_metrics_json(self, client):
        resp = client.get("/metrics", headers=API_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "rps" in data

    def test_prometheus_endpoint(self, client):
        resp = client.get("/metrics/prometheus")
        assert resp.status_code == 200
        assert b"opendeploy" in resp.content or resp.status_code == 200
