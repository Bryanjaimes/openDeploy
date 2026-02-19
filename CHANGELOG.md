# Changelog

All notable changes to OpenDeploy are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.7.0] — 2026-02-17

### V7-P1: Person Detection + Instance Segmentation

**Added**
- `models/yolov8_seg.py` — YOLOv8-seg instance segmentation model with two serving modes (ONNX Runtime local, NVIDIA Triton remote)
- Pure-NumPy NMS implementation (no torchvision dependency required)
- Full COCO 80-class detection with per-instance pixel masks and contour polygons
- `scripts/export_yolov8_seg_onnx.py` — one-command ONNX export (supports n/s/m/l/x model sizes) with Triton repo layout
- `scripts/benchmark_vision.py` — automated benchmarking with database-backed evolution tracking
- `scripts/threshold_sweep.py` — exhaustive 54-combination (9 conf × 6 IoU) hyperparameter sweep with quality heuristic
- `ModelEvolution` database table — full schema for tracking every model iteration, including vision-specific and LLM-specific metrics
- `Recording` database table — persisted video recording metadata linked to model evolution entries
- `benchmark_results.json` — machine-readable benchmark evolution log
- `sweep_results.json` — full threshold sweep results (1,340 lines, 54 configurations)
- Database migration logic (`_migrate_add_columns`) for safe schema evolution

**Benchmarked**
- **Iteration 0 (Baseline):** YOLOv8n-seg, conf=0.25, IoU=0.45 → 24.73ms avg inference, 0.713 avg confidence, 4 classes detected
- **Iteration 1 (Threshold Optimized):** conf=0.30, IoU=0.40 → 33.95ms, 0.767 avg confidence (+7.6%), quality score 0.398
- **Iteration 2 (Model Scale-Up):** YOLOv8s-seg → 68.14ms, 0.843 avg confidence (+18.3%), but FPS dropped from 29.5 → 14.7

---

## [0.6.0] — 2026-02-05

### V6: Next.js Dashboard

**Added**
- `frontend/dashboard/` — full Next.js 15 dashboard application
- Architecture view with interactive system diagram, wire display modes, and layer focus
- Models page — browse registered models and view details
- Metrics page — live request rate, latency percentiles, GPU utilization
- History page — prediction history from SQLite store
- WebRTC page — browser-based video stream testing
- Settings page — API key configuration
- `components.json` — shadcn/ui component configuration
- Dockerfile for dashboard container

---

## [0.5.0] — 2026-01-28

### V5: Edge Model Compiler

**Added**
- `scripts/edge/build.py` — compile models to edge-optimized formats (GGUF, ONNX, AutoGPTQ)
- `scripts/edge/registry.py` — local filesystem and OCI/ORAS artifact registry
- `scripts/edge/agent.py` — OTA polling agent for edge devices
- `scripts/edge/runtime.py` — automatic inference runtime selection based on hardware capabilities
- CLI `build` subcommand with `--target edge`, `--format`, `--quant` flags

**Supported Formats**
- GGUF via llama.cpp (q4_0, q4_1, q5_0, q5_1, q8_0 quantization)
- ONNX with dynamic axes
- AutoGPTQ 4-bit quantization

---

## [0.4.0] — 2026-01-20

### V4: Real-Time Vision Pipeline

**Added**
- `webrtc-gateway/` — Go + Pion WebRTC data channel gateway
- `backend/shm_frames.py` — ODSH v2 ring buffer protocol for zero-copy frame sharing via `/dev/shm`
- Ring buffer: 64 slots (configurable), per-slot 40-byte header, double-read consistency check
- `read_latest()` for single-frame inference, `read_window(n)` for temporal analysis
- `frontend/webrtc-client.html` — browser-based WebRTC test client
- Frame validation: max width/height/bytes enforced on all ingest paths
- 12-byte frame header protocol on WebRTC DataChannel (width, height, format)

**Performance**
- End-to-end latency budget: < 15ms (WebRTC decode 2ms + SHM read 3ms + inference 8ms + response 2ms)
- Zero-copy IPC via mmap — eliminates gRPC serialization overhead (~5ms saved)

---

## [0.3.0] — 2026-01-12

### V3: Elastic Cluster Orchestration

**Added**
- `operator/` — Python Kubernetes operator watching `OpenDeploy` CRDs
- `k8s/crd/opendeploy.yaml` — Custom Resource Definition for OpenDeploy workloads
- `k8s/rbac.yaml` — ServiceAccount, ClusterRole, ClusterRoleBinding
- `k8s/operator-deployment.yaml` — Operator Deployment manifest
- `k8s/sample/opendeploy-sample.yaml` — Example OpenDeploy CR
- `k8s/keda/` — KEDA ScaledObject for scale-to-zero on Prometheus RPS trigger
- `k8s/karpenter/` — EC2NodeClass + NodePool for just-in-time GPU node provisioning (spot preference)
- HPA-based autoscaling (CPU utilization target) via operator reconciler

---

## [0.2.0] — 2026-01-05

### V2: GPU Arbitrage Scheduler

**Added**
- `cli/cmd/opendeploy/schedule.go` — real-time GPU pricing query and cheapest-AZ selection
- AWS Spot pricing via `aws ec2 describe-spot-price-history`
- GCP preemptible pricing via `gcloud compute machine-types` + billing catalog estimates
- `--max-price` constraint with automatic zone selection
- `--cloud aws` and `--cloud gcp` flags
- Static GCP pricing fallback when Billing API is unavailable

---

## [0.1.0] — 2025-12-28

### V1: Single-Cloud Deploy

**Added**
- `cli/cmd/opendeploy/deploy.go` — deploy via SSH to cloud VM
- `infra/aws/main.tf` — Terraform module for AWS GPU VMs (g4dn.xlarge)
- `infra/aws/variables.tf` — configurable region, instance type, key pair
- `deploy.sh` — rsync project + docker compose up on remote host
- `create_aws_instance.sh` — standalone EC2 provisioning helper

---

## [0.0.1] — 2025-12-20

### V0: Local Runner

**Added**
- `backend/main.py` — FastAPI server with Uvicorn
- `backend/loader.py` — dynamic class loader discovering `AIModel` subclasses from `models/`
- `backend/interface.py` — `AIModel` abstract base class (`name`, `input_type`, `load`, `predict`)
- `backend/registry.py` — model registry with auto-discovery
- `backend/database.py` — SQLite-backed prediction history
- `backend/gen_ui.py` — auto-generated UI for each model
- `backend/metrics.py` — in-process metrics store (RPS, p50/p95/p99, cold-start, GPU stats)
- `backend/metrics_prom.py` — Prometheus metrics exporter
- `backend/metrics_catalog.py` — AI-powered metrics glossary
- `cli/` — Go CLI (Cobra + Viper) with `run` subcommand
- `models/tiny_llama.py` — TinyLlama 1.1B Chat
- `models/mistral_small_quantized.py` — Mistral Small 4-bit quantized
- `models/career_advisor.py` — Gemini-powered career advisor agent
- `models/symptom_checker.py` — Gemini-powered symptom checker agent
- `models/eye_scanner.py` — retinopathy vision classifier
- `models/hf_sentiment.py` — HuggingFace sentiment classifier
- `models/echo_demo.py` — test/debug echo model
- `prometheus/prometheus.yml` — Prometheus scrape configuration
- `grafana/` — auto-provisioned dashboards and datasource configs
- `docker-compose.yml` — full local stack (API + WebRTC + Prometheus + Grafana)
- `docker-compose.vllm.yml` — vLLM runner (OpenAI-compatible)
- `docker-compose.triton.yml` — NVIDIA Triton Inference Server
- `proto/v1/opendeploy.proto` — gRPC service contract
- API-key auth, rate limiting, body size limits, CORS
- `Makefile` with test, lint, fmt, build, run, stop, clean targets
- `pytest.ini` + `backend/tests/` — unit test suite (API, metrics, registry, SHM ring buffer)
