import os
import subprocess
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
        self.last_compute_ms: Optional[float] = None

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
        self.last_compute_ms = duration_ms

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

        price_per_hour = _get_env_float("OPENDEPLOY_PRICE_PER_HOUR")
        price_per_1k_tokens = _get_env_float("OPENDEPLOY_PRICE_PER_1K_TOKENS")
        cost_per_inference = None
        throughput_per_dollar = None

        if price_per_hour is not None:
            if self.last_compute_ms is not None:
                cost_per_inference = (price_per_hour / 3600.0) * (self.last_compute_ms / 1000.0)
            if rps > 0:
                throughput_per_dollar = rps / price_per_hour

        gpu_stats = _get_gpu_stats()

        return {
            "rps": rps,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "compute_p50_ms": compute_p50,
            "cold_start_ms": cold_start_ms,
            "error_rate_pct": error_rate,
            "active_requests": self.active_requests,
            "last_compute_ms": self.last_compute_ms,
            "price_per_hour": price_per_hour,
            "price_per_1k_tokens": price_per_1k_tokens,
            "cost_per_1k_tokens": price_per_1k_tokens,
            "cost_per_inference": cost_per_inference,
            "throughput_per_dollar": throughput_per_dollar,
            "gpu": gpu_stats,
        }


metrics_store = MetricsStore()


def _get_env_float(key: str) -> Optional[float]:
    value = os.getenv(key)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _get_gpu_stats() -> Dict[str, Optional[float]]:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.sm",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        ).strip()
        if not output:
            return {"available": False}

        fields = [item.strip() for item in output.split(",")]
        util_gpu = float(fields[0])
        util_mem = float(fields[1])
        mem_used = float(fields[2])
        mem_total = float(fields[3])
        power_draw = float(fields[4]) if len(fields) > 4 else None
        clocks_sm = float(fields[5]) if len(fields) > 5 else None
        vram_pct = (mem_used / mem_total * 100.0) if mem_total else None

        return {
            "available": True,
            "utilization_gpu_pct": util_gpu,
            "utilization_mem_pct": util_mem,
            "vram_used_mb": mem_used,
            "vram_total_mb": mem_total,
            "vram_used_pct": vram_pct,
            "power_watts": power_draw,
            "sm_clock_mhz": clocks_sm,
        }
    except Exception:
        return {"available": False}