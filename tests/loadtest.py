"""
Locust load test for OpenDeploy API.

Usage:
  pip install locust
  locust -f tests/loadtest.py --host http://localhost:8000

Then open http://localhost:8089 to configure and run.
"""

from locust import HttpUser, task, between, events
import os

API_KEY = os.getenv("OPENDEPLOY_API_KEY", "secret-key-123")
HEADERS = {"X-API-Key": API_KEY}


class OpenDeployUser(HttpUser):
    """Simulates a client hitting the OpenDeploy API."""

    wait_time = between(0.5, 2.0)

    @task(5)
    def health_check(self):
        self.client.get("/health")

    @task(3)
    def list_models(self):
        self.client.get("/models", headers=HEADERS)

    @task(1)
    def get_metrics(self):
        self.client.get("/metrics", headers=HEADERS)

    @task(2)
    def predict_text(self):
        self.client.post(
            "/generate",
            json={"prompt": "What is machine learning?"},
            headers=HEADERS,
        )

    @task(1)
    def prometheus_metrics(self):
        self.client.get("/metrics/prometheus")


class HighThroughputUser(HttpUser):
    """Simulates burst traffic for stress testing."""

    wait_time = between(0.1, 0.3)

    @task
    def burst_predict(self):
        self.client.post(
            "/generate",
            json={"prompt": "Explain GPU arbitrage in one sentence."},
            headers=HEADERS,
        )
