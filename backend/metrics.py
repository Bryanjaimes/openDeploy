import time
from collections import deque
from typing import Deque, Dict, Optional


class MetricsStore:
    def __init__(self):
        self.app_start_time = time.time()
        self.first_request_time: Optional[float] = None
        self.model_load_times: Dict[str, float] = {}

        self.request_timestamps: Deque[float] = deque(maxlen=10000)
        self.request_latencies_ms: Deque[float] = deque(maxlen=10000)
        self.compute_latencies_ms: Deque[float] = deque(maxlen=10000)
        self.error_count = 0
        self.total_count = 0
        self.active_requests = 0

    def record_model_load(self, model_name: str, duration_ms: float):
        self.model_load_times[model_name] = duration_ms

    def record_request(self, duration_ms: float, status_code: int):
        now = time.time()
        self.request_timestamps.append(now)
        self.request_latencies_ms.append(duration_ms)
        self.total_count += 1
        if status_code >= 500:
            self.error_count += 1
        if self.first_request_time is None:
            self.first_request_time = now

    def record_compute(self, duration_ms: float):
        self.compute_latencies_ms.append(duration_ms)

    def inc_active(self):
        self.active_requests += 1

    def dec_active(self):
        self.active_requests = max(0, self.active_requests - 1)

    def _percentile(self, values: Deque[float], pct: float) -> Optional[float]:
        if not values:
            return None
        sorted_vals = sorted(values)
        k = int(round((pct / 100.0) * (len(sorted_vals) - 1)))
        return sorted_vals[k]

    def snapshot(self) -> Dict[str, Optional[float]]:
        now = time.time()
        window_seconds = 60
        recent = [t for t in self.request_timestamps if now - t <= window_seconds]
        rps = len(recent) / window_seconds if window_seconds else 0.0

        p50 = self._percentile(self.request_latencies_ms, 50)
        p95 = self._percentile(self.request_latencies_ms, 95)
        p99 = self._percentile(self.request_latencies_ms, 99)

        compute_p50 = self._percentile(self.compute_latencies_ms, 50)

        cold_start_ms = None
        if self.first_request_time is not None:
            cold_start_ms = (self.first_request_time - self.app_start_time) * 1000.0

        error_rate = (self.error_count / self.total_count) * 100 if self.total_count else 0.0

        return {
            "rps": rps,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "compute_p50_ms": compute_p50,
            "cold_start_ms": cold_start_ms,
            "error_rate_pct": error_rate,
            "active_requests": self.active_requests,
        }


metrics_store = MetricsStore()