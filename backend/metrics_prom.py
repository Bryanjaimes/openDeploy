from prometheus_client import Counter, Gauge, Histogram

REQUESTS_TOTAL = Counter(
    "opendeploy_requests_total",
    "Total HTTP requests",
    ["path", "method", "status"],
)

REQUEST_LATENCY_MS = Histogram(
    "opendeploy_request_latency_ms",
    "Request latency in milliseconds",
    ["path", "method"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000),
)

ACTIVE_REQUESTS = Gauge(
    "opendeploy_active_requests",
    "Active in-flight requests",
)

COMPUTE_MS = Histogram(
    "opendeploy_compute_ms",
    "Model compute time in milliseconds",
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000),
)

MODEL_LOAD_MS = Histogram(
    "opendeploy_model_load_ms",
    "Model load time in milliseconds",
    ["model"],
    buckets=(50, 100, 250, 500, 1000, 2000, 5000, 10000),
)
