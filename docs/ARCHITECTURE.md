# OpenDeploy — High-Level Architecture

> **Version:** 0.7.0 (V0–V5 implemented)
> **Last Updated:** 2026-02-05

---

## 1. System Context

```
┌──────────────────────────────────────────────────────────────────┐
│                          ENGINEER                                │
│                    (opendeploy CLI / Dashboard)                   │
└────────────┬────────────────────────┬────────────────────────────┘
             │  YAML spec / flags     │  HTTP / WebSocket
             ▼                        ▼
┌────────────────────┐     ┌───────────────────────┐
│   Go CLI Binary    │     │   Next.js Dashboard   │
│  (Cobra + Viper)   │     │   (future – V6)       │
└────────┬───────────┘     └───────────┬───────────┘
         │                             │
         │  Docker Compose / K8s API   │  REST
         ▼                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    CONTROL PLANE                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ K8s Operator │  │  Terraform   │  │  GPU Arbitrage         │  │
│  │ (Python)     │  │  Provisioner │  │  Scheduler (Go)        │  │
│  └──────────────┘  └──────────────┘  └────────────────────────┘  │
└────────────────────────────┬─────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌────────────────┐ ┌────────────────┐ ┌──────────────────┐
│  FastAPI Runner│ │  vLLM Runner   │ │  Triton Runner   │
│  (general)     │ │  (LLM)         │ │  (vision)        │
└───────┬────────┘ └────────────────┘ └──────────────────┘
        │
        │  /dev/shm (zero-copy)
        ▼
┌────────────────┐       ┌────────────────────┐
│ WebRTC Gateway │──────▶│ Prometheus/Grafana  │
│ (Go + Pion)    │       │ (Observability)     │
└────────────────┘       └────────────────────┘
```

---

## 2. Component Breakdown

### 2.1 Go CLI (`cli/`)

| Concern | Implementation |
|---------|---------------|
| Framework | Cobra (subcommands) + Viper (YAML config) |
| Subcommands | `run`, `build`, `schedule`, `deploy` |
| Distribution | Single static binary, cross-compiled via `GOOS`/`GOARCH` |

The CLI is the **only** entry point for engineers. It delegates to Docker Compose
for local runs, Terraform for cloud provisioning, and the Python edge build
pipeline for quantization.

### 2.2 Python Model Runner (`backend/`)

| Concern | Implementation |
|---------|---------------|
| Framework | FastAPI + Uvicorn |
| Plugin System | Dynamic class loader discovers `AIModel` subclasses at startup |
| Serving Modes | Direct PyTorch, HuggingFace Pipelines, Triton Client, vLLM |
| Security | API-key auth, rate limiting, body size limits |

Models are hot-pluggable: drop a Python file into `models/` that subclasses
`AIModel` and it's automatically registered and served.

### 2.3 GPU Arbitrage Scheduler (`cli/cmd/opendeploy/schedule.go`)

The scheduler queries **real-time** spot/preemptible pricing:

1. **AWS**: `aws ec2 describe-spot-price-history` → parse → sort by price
2. **GCP**: `gcloud compute machine-types` + billing catalog estimates
3. **Selection**: Cheapest AZ at or below the user's `--max-price` constraint

This is the core differentiator — the system makes **financial decisions**
so the engineer doesn't have to.

### 2.4 Kubernetes Operator (`operator/`)

Custom controller watching `OpenDeploy` CRDs:

```
Event Watch → Reconcile → {Deployment, Service, HPA, KEDA ScaledObject}
```

Supports:
- HPA-based autoscaling (CPU utilization target)
- KEDA scale-to-zero (Prometheus trigger on RPS)
- Karpenter just-in-time GPU node provisioning (spot preference)

### 2.5 WebRTC Vision Pipeline (`webrtc-gateway/`)

**Data Flow:**

```
Camera/Device → WebRTC DataChannel → Go Gateway
    → mmap write to ring buffer slot (ODSH v2)
    → Python FastAPI reads /dev/shm (latest or temporal window)
    → Model inference (single-frame or multi-frame action recognition)
    → JSON result
```

**IPC Protocol — ODSH v2 Ring Buffer:**

```
┌─────────────────────────── /dev/shm/opendeploy_frames ───────────────────────────┐
│ Global Header (64 B)  │ Slot 0 │ Slot 1 │ Slot 2 │ ... │ Slot N-1              │
└───────────────────────┴────────┴────────┴────────┴─────┴────────────────────────┘
```

Global Header (64 bytes):
- `magic(4)="ODSH"` · `version(4)=2` · `num_slots(4)` · `slot_size(4)` · `write_seq(8)` · `slot_capacity(4)` · `reserved(36)`

Per-Slot (40-byte header + payload):
- `magic(4)="ODSF"` · `width(4)` · `height(4)` · `format(4)` · `data_len(4)` · `flags(4)` · `seq(8)` · `timestamp_ns(8)`
- Flags: `0=empty`, `1=ready`, `2=writing`
- Payload follows immediately after the 40-byte slot header

**Ring Buffer Semantics:**
- Default: 64 slots (configurable via `OPENDEPLOY_RING_SLOTS`)
- Slot capacity from `OPENDEPLOY_MAX_FRAME_BYTES` (default 4×1920×1080)
- `write_seq` increments monotonically; slot index = `(write_seq - 1) % num_slots`
- Writer marks slot `WRITING → copies payload → marks READY → updates global write_seq`
- Reader uses double-read consistency check (re-reads seq + flags after payload copy)
- `read_latest()` returns the most recent frame (backward compatible)
- `read_window(n)` returns the last *n* frames oldest→newest for temporal analysis

**Latency Budget:**
| Stage | Target |
|-------|--------|
| WebRTC decode + write | < 2ms |
| SHM read + preprocess | < 3ms |
| Model inference (ResNet18 GPU) | < 8ms |
| HTTP response | < 2ms |
| **Total** | **< 15ms** |

### 2.6 Edge Pipeline (`scripts/edge/`)

```
CLI build cmd → build.py → {llama.cpp | AutoGPTQ | ONNX export}
    → artifact dir (model + manifest.json)
    → registry.py push (local FS or OCI/ORAS)
    → agent.py polls for new versions on edge device
    → runtime.py selects correct inference runtime
```

---

## 3. Design Trade-offs

| Decision | Alternative | Why This |
|----------|-------------|----------|
| **Go CLI + Python Runner** | All-Python or all-Go | Go gives single-binary distribution and concurrency for scheduling; Python has the ML ecosystem (transformers, torch). The boundary is clean: Go orchestrates, Python computes. |
| **Python K8s Operator** | Go + controller-runtime (Kubebuilder) | Faster iteration for a small team. Production migration path is Kubebuilder when operator complexity grows. |
| **Shared Memory IPC** | gRPC streaming, Unix sockets | Zero-copy is critical for 60fps video. gRPC adds serialization overhead (~5ms). SHM + mmap keeps us under 2ms for frame transfer. |
| **SQLite for predictions** | PostgreSQL | Sufficient for single-node; easy to swap via `OPENDEPLOY_DATABASE_URL` env var. |
| **Static GCP pricing fallback** | Real-time Billing API | GCP's billing export API requires project-level setup. The fallback uses known reference prices and real zone availability from `gcloud`. |

---

## 4. Observability

- **Prometheus metrics** exposed at `/metrics/prometheus`
  - `opendeploy_requests_total` (counter, by path/method/status)
  - `opendeploy_request_latency_ms` (histogram)
  - `opendeploy_compute_ms` (histogram)
  - `opendeploy_active_requests` (gauge)
  - `opendeploy_model_load_ms` (histogram, by model)
- **Grafana dashboard** auto-provisioned via `grafana/provisioning/`
- **In-process MetricsStore** provides JSON snapshot at `/metrics`
  - RPS, p50/p95/p99, cold-start time, GPU stats (via nvidia-smi)

---

## 5. Security Model

| Layer | Mechanism |
|-------|-----------|
| API Authentication | `X-API-Key` header, validated against `OPENDEPLOY_API_KEY` env var |
| Rate Limiting | Per-client, per-path sliding window (60 req/min default) |
| Body Size | Configurable max (`OPENDEPLOY_MAX_BODY_MB`, default 10MB) |
| Metrics Endpoint | Optional bearer token (`OPENDEPLOY_METRICS_TOKEN`) |
| CORS | Configurable allowed origins |
| Infrastructure | Terraform security groups (SSH + API ports only) |

---

## 6. Deployment Topology

### Local Development
```
docker compose up → {api, webrtc-gateway, frontend, prometheus, grafana}
```

### Single Cloud VM (V1)
```
opendeploy deploy --cloud aws → Terraform → EC2 g4dn.xlarge
./deploy.sh user@ip → rsync + docker compose up
```

### Kubernetes Cluster (V3)
```
kubectl apply -f k8s/crd/ → CRD registered
kubectl apply -f k8s/rbac.yaml → ServiceAccount + RBAC
kubectl apply -f k8s/operator-deployment.yaml → Operator running
kubectl apply -f k8s/sample/opendeploy-sample.yaml → Model deployed
```
