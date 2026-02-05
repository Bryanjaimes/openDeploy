"""Unit tests for the MetricsStore."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.metrics import MetricsStore


class TestMetricsStore:
    def test_initial_state(self):
        store = MetricsStore()
        snap = store.snapshot()
        assert snap["rps"] == 0.0
        assert snap["active_requests"] == 0
        assert snap["error_rate_pct"] == 0.0
        assert snap["p50_ms"] is None

    def test_record_request(self):
        store = MetricsStore()
        store.record_request(50.0, 200)
        store.record_request(100.0, 200)
        snap = store.snapshot()
        assert store.total_count == 2
        assert store.error_count == 0
        assert snap["p50_ms"] is not None

    def test_record_errors(self):
        store = MetricsStore()
        store.record_request(10.0, 200)
        store.record_request(10.0, 500)
        store.record_request(10.0, 503)
        assert store.error_count == 2
        snap = store.snapshot()
        assert abs(snap["error_rate_pct"] - 66.67) < 1.0

    def test_active_requests(self):
        store = MetricsStore()
        store.inc_active()
        store.inc_active()
        assert store.active_requests == 2
        store.dec_active()
        assert store.active_requests == 1
        store.dec_active()
        store.dec_active()  # should not go negative
        assert store.active_requests == 0

    def test_model_load_tracking(self):
        store = MetricsStore()
        store.record_model_load("resnet-18", 1234.5)
        assert store.model_load_times["resnet-18"] == 1234.5

    def test_compute_latency(self):
        store = MetricsStore()
        store.record_compute(42.0)
        assert store.last_compute_ms == 42.0
        snap = store.snapshot()
        assert snap["last_compute_ms"] == 42.0
