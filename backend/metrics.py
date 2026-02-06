import os
import platform
import subprocess
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional


class MetricsStore:
    """Thread-safe in-process metrics collector."""

    def __init__(self):
        self._lock = threading.Lock()
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

        # Per-model counters
        self.model_request_counts: Dict[str, int] = {}
        self.model_error_counts: Dict[str, int] = {}
        self.model_latencies: Dict[str, Deque[float]] = {}

        # Token tracking
        self.total_tokens_in = 0
        self.total_tokens_out = 0

        # Request size tracking
        self.request_sizes_bytes: Deque[int] = deque(maxlen=5000)
        self.response_sizes_bytes: Deque[int] = deque(maxlen=5000)

    def record_model_load(self, model_name: str, duration_ms: float):
        with self._lock:
            self.model_load_times[model_name] = duration_ms

    def record_request(self, duration_ms: float, status_code: int, model_name: str = ""):
        now = time.time()
        with self._lock:
            self.request_timestamps.append(now)
            self.request_latencies_ms.append(duration_ms)
            self.total_count += 1
            if status_code >= 500:
                self.error_count += 1
            if self.first_request_time is None:
                self.first_request_time = now

            # Per-model
            if model_name:
                self.model_request_counts[model_name] = self.model_request_counts.get(model_name, 0) + 1
                if status_code >= 500:
                    self.model_error_counts[model_name] = self.model_error_counts.get(model_name, 0) + 1
                if model_name not in self.model_latencies:
                    self.model_latencies[model_name] = deque(maxlen=2000)
                self.model_latencies[model_name].append(duration_ms)

    def record_compute(self, duration_ms: float):
        with self._lock:
            self.compute_latencies_ms.append(duration_ms)
            self.last_compute_ms = duration_ms

    def record_tokens(self, tokens_in: int, tokens_out: int):
        with self._lock:
            self.total_tokens_in += tokens_in
            self.total_tokens_out += tokens_out

    def record_payload_sizes(self, req_bytes: int = 0, res_bytes: int = 0):
        with self._lock:
            if req_bytes:
                self.request_sizes_bytes.append(req_bytes)
            if res_bytes:
                self.response_sizes_bytes.append(res_bytes)

    def inc_active(self):
        with self._lock:
            self.active_requests += 1

    def dec_active(self):
        with self._lock:
            self.active_requests = max(0, self.active_requests - 1)

    def _percentile(self, values, pct: float) -> Optional[float]:
        if not values:
            return None
        sorted_vals = sorted(values)
        k = int(round((pct / 100.0) * (len(sorted_vals) - 1)))
        return sorted_vals[k]

    def _avg(self, values) -> Optional[float]:
        if not values:
            return None
        return sum(values) / len(values)

    def snapshot(self) -> Dict:
        with self._lock:
            now = time.time()
            uptime_s = now - self.app_start_time
            window_seconds = 60
            recent = [t for t in self.request_timestamps if now - t <= window_seconds]
            rps = len(recent) / window_seconds if window_seconds else 0.0

            p50 = self._percentile(self.request_latencies_ms, 50)
            p90 = self._percentile(self.request_latencies_ms, 90)
            p95 = self._percentile(self.request_latencies_ms, 95)
            p99 = self._percentile(self.request_latencies_ms, 99)
            p999 = self._percentile(self.request_latencies_ms, 99.9)
            avg_latency = self._avg(self.request_latencies_ms)
            min_latency = min(self.request_latencies_ms) if self.request_latencies_ms else None
            max_latency = max(self.request_latencies_ms) if self.request_latencies_ms else None

            compute_p50 = self._percentile(self.compute_latencies_ms, 50)
            compute_p95 = self._percentile(self.compute_latencies_ms, 95)
            compute_p99 = self._percentile(self.compute_latencies_ms, 99)
            compute_avg = self._avg(self.compute_latencies_ms)

            cold_start_ms = None
            if self.first_request_time is not None:
                cold_start_ms = (self.first_request_time - self.app_start_time) * 1000.0

            error_rate = (self.error_count / self.total_count) * 100 if self.total_count else 0.0
            success_rate = 100.0 - error_rate

            # Queue depth approximation
            queue_depth = max(0, self.active_requests)

            # Throughput - requests per minute
            rpm = rps * 60

            # Avg payload sizes
            avg_req_size = self._avg(self.request_sizes_bytes)
            avg_res_size = self._avg(self.response_sizes_bytes)

            # Per-model breakdown
            per_model: Dict[str, Dict] = {}
            for name in set(list(self.model_request_counts.keys()) + list(self.model_latencies.keys())):
                lats = self.model_latencies.get(name, deque())
                per_model[name] = {
                    "requests": self.model_request_counts.get(name, 0),
                    "errors": self.model_error_counts.get(name, 0),
                    "p50_ms": self._percentile(lats, 50),
                    "p95_ms": self._percentile(lats, 95),
                    "p99_ms": self._percentile(lats, 99),
                    "avg_ms": self._avg(lats),
                }

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
        cpu_stats = _get_cpu_stats()
        mem_stats = _get_memory_stats()
        system_info = _get_system_info()

        return {
            # ── Application layer ──
            "uptime_s": uptime_s,
            "rps": rps,
            "rpm": rpm,
            "total_requests": self.total_count,
            "error_count": self.error_count,
            "error_rate_pct": error_rate,
            "success_rate_pct": success_rate,
            "active_requests": self.active_requests,
            "queue_depth": queue_depth,
            # ── Latency percentiles ──
            "p50_ms": p50,
            "p90_ms": p90,
            "p95_ms": p95,
            "p99_ms": p99,
            "p999_ms": p999,
            "avg_latency_ms": avg_latency,
            "min_latency_ms": min_latency,
            "max_latency_ms": max_latency,
            # ── Compute (model only) ──
            "compute_p50_ms": compute_p50,
            "compute_p95_ms": compute_p95,
            "compute_p99_ms": compute_p99,
            "compute_avg_ms": compute_avg,
            "last_compute_ms": self.last_compute_ms,
            # ── Cold start ──
            "cold_start_ms": cold_start_ms,
            # ── Tokens ──
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_tokens": self.total_tokens_in + self.total_tokens_out,
            # ── Payload sizes ──
            "avg_request_size_bytes": avg_req_size,
            "avg_response_size_bytes": avg_res_size,
            # ── Cost ──
            "price_per_hour": price_per_hour,
            "price_per_1k_tokens": price_per_1k_tokens,
            "cost_per_1k_tokens": price_per_1k_tokens,
            "cost_per_inference": cost_per_inference,
            "throughput_per_dollar": throughput_per_dollar,
            # ── Per-model breakdown ──
            "per_model": per_model,
            # ── Hardware: GPU ──
            "gpu": gpu_stats,
            # ── Hardware: CPU ──
            "cpu": cpu_stats,
            # ── Hardware: Memory ──
            "memory": mem_stats,
            # ── System info ──
            "system": system_info,
            # ── Model load times ──
            "model_load_times_ms": self.model_load_times,
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


def _get_gpu_stats() -> Dict:
    """Deep GPU telemetry via nvidia-smi — silicon-level metrics."""
    try:
        # Query everything nvidia-smi exposes
        fields = (
            "utilization.gpu,"
            "utilization.memory,"
            "memory.used,"
            "memory.total,"
            "memory.free,"
            "power.draw,"
            "power.limit,"
            "clocks.sm,"
            "clocks.mem,"
            "clocks.max.sm,"
            "clocks.max.mem,"
            "temperature.gpu,"
            "temperature.memory,"
            "fan.speed,"
            "pstate,"
            "pcie.link.gen.current,"
            "pcie.link.width.current,"
            "encoder.stats.sessionCount,"
            "ecc.errors.corrected.volatile.total,"
            "ecc.errors.uncorrected.volatile.total,"
            "gpu_name,"
            "driver_version,"
            "compute_cap"
        )
        output = subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        ).strip()
        if not output:
            return {"available": False}

        f = [item.strip() for item in output.split(",")]

        def safe_float(idx: int) -> Optional[float]:
            try:
                v = f[idx] if idx < len(f) else None
                return float(v) if v and v not in ("[N/A]", "N/A", "[Not Supported]") else None
            except (ValueError, TypeError):
                return None

        def safe_str(idx: int) -> Optional[str]:
            try:
                v = f[idx].strip() if idx < len(f) else None
                return v if v and v not in ("[N/A]", "N/A", "[Not Supported]") else None
            except (IndexError, AttributeError):
                return None

        mem_used = safe_float(2)
        mem_total = safe_float(3)
        mem_free = safe_float(4)
        vram_pct = (mem_used / mem_total * 100.0) if mem_used and mem_total else None
        power_draw = safe_float(5)
        power_limit = safe_float(6)
        power_pct = (power_draw / power_limit * 100.0) if power_draw and power_limit else None
        sm_clock = safe_float(7)
        sm_max = safe_float(9)
        sm_throttle_pct = ((1.0 - sm_clock / sm_max) * 100.0) if sm_clock and sm_max else None

        return {
            "available": True,
            # Utilization
            "utilization_gpu_pct": safe_float(0),
            "utilization_mem_pct": safe_float(1),
            # VRAM
            "vram_used_mb": mem_used,
            "vram_total_mb": mem_total,
            "vram_free_mb": mem_free,
            "vram_used_pct": vram_pct,
            # Power
            "power_watts": power_draw,
            "power_limit_watts": power_limit,
            "power_usage_pct": power_pct,
            # Clocks
            "sm_clock_mhz": sm_clock,
            "mem_clock_mhz": safe_float(8),
            "sm_max_clock_mhz": sm_max,
            "mem_max_clock_mhz": safe_float(10),
            "clock_throttle_pct": sm_throttle_pct,
            # Thermals
            "temp_gpu_c": safe_float(11),
            "temp_memory_c": safe_float(12),
            "fan_speed_pct": safe_float(13),
            # Performance state
            "pstate": safe_str(14),
            # PCIe bus
            "pcie_gen": safe_float(15),
            "pcie_width": safe_float(16),
            # Encoder
            "encoder_sessions": safe_float(17),
            # ECC errors (transistor-level)
            "ecc_corrected": safe_float(18),
            "ecc_uncorrected": safe_float(19),
            # Device info
            "gpu_name": safe_str(20),
            "driver_version": safe_str(21),
            "compute_capability": safe_str(22),
        }
    except Exception:
        return {"available": False}


def _get_cpu_stats() -> Dict:
    """CPU metrics — utilization, frequency, core count, load average."""
    try:
        import psutil
        freq = psutil.cpu_freq()
        load_1, load_5, load_15 = (None, None, None)
        try:
            load_1, load_5, load_15 = os.getloadavg()
        except (OSError, AttributeError):
            pass
        per_core = psutil.cpu_percent(interval=0, percpu=True)
        return {
            "available": True,
            "utilization_pct": psutil.cpu_percent(interval=0),
            "per_core_pct": per_core,
            "core_count_physical": psutil.cpu_count(logical=False),
            "core_count_logical": psutil.cpu_count(logical=True),
            "freq_current_mhz": freq.current if freq else None,
            "freq_max_mhz": freq.max if freq else None,
            "freq_min_mhz": freq.min if freq else None,
            "freq_throttle_pct": ((1.0 - freq.current / freq.max) * 100.0) if freq and freq.max and freq.current else None,
            "load_1m": load_1,
            "load_5m": load_5,
            "load_15m": load_15,
            "ctx_switches": psutil.cpu_stats().ctx_switches,
            "interrupts": psutil.cpu_stats().interrupts,
        }
    except ImportError:
        # psutil not installed — return basic info
        return {
            "available": False,
            "core_count_logical": os.cpu_count(),
            "note": "install psutil for full CPU metrics",
        }
    except Exception:
        return {"available": False}


def _get_memory_stats() -> Dict:
    """System memory and swap — RAM utilization."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "available": True,
            "ram_total_mb": vm.total / (1024 * 1024),
            "ram_used_mb": vm.used / (1024 * 1024),
            "ram_free_mb": vm.available / (1024 * 1024),
            "ram_used_pct": vm.percent,
            "ram_cached_mb": getattr(vm, "cached", 0) / (1024 * 1024),
            "ram_buffers_mb": getattr(vm, "buffers", 0) / (1024 * 1024),
            "swap_total_mb": swap.total / (1024 * 1024),
            "swap_used_mb": swap.used / (1024 * 1024),
            "swap_used_pct": swap.percent,
        }
    except ImportError:
        return {"available": False, "note": "install psutil for memory metrics"}
    except Exception:
        return {"available": False}


def _get_system_info() -> Dict:
    """Static system identification."""
    return {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "python_version": platform.python_version(),
        "pid": os.getpid(),
    }