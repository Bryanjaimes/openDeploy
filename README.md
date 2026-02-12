# OpenDeploy — The Sovereign AI Cloud Platform

OpenDeploy is an open-source, multi-cloud orchestration engine that treats AI models as first-class citizens. It lets engineers build, optimize, and serve models (LLMs, Vision, Diffusion) across any compute substrate — from AWS Spot to rural edge devices — with a single CLI command.

## 🎯 Quick Start

```bash
# 1. Build the CLI
cd cli && go build -o ../bin/opendeploy ./cmd/opendeploy && cd ..

# 2. Start the full local stack (API + WebRTC + Dashboard + Prometheus + Grafana)
docker compose up -d --build

# 3. Test inference
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${OPENDEPLOY_API_KEY}" \
  -d '{"prompt":"Hello!","model":"tiny-llama-chat"}'
```

Once running:

| Service | URL |
|---------|-----|
| **Dashboard** | http://localhost:3000 |
| **API** | http://localhost:8000 |
| **Prometheus** | http://localhost:9090 |
| **Grafana** | http://localhost:3002 (admin / admin) |

---

## 🏗️ Project Structure

```
openDeploy/
├── backend/             # FastAPI server — model inference, history, metrics
├── models/              # Hot-pluggable AIModel plugins (drop-in Python files)
├── cli/                 # Go CLI (Cobra) — run, build, deploy, schedule
├── frontend/dashboard/  # Next.js dashboard (architecture view, metrics, models)
├── webrtc-gateway/      # Go + Pion WebRTC gateway for real-time vision
├── operator/            # Python Kubernetes operator (CRD → Deployment/Service)
├── k8s/                 # CRDs, RBAC, KEDA, Karpenter manifests
├── infra/aws/           # Terraform module for AWS GPU VMs
├── scripts/edge/        # Edge build, registry, agent, runtime selector
├── proto/v1/            # gRPC service contract (protobuf)
├── prometheus/          # Prometheus scrape config
├── grafana/             # Provisioned dashboards + datasources
├── triton_model_repo/   # NVIDIA Triton model repo (ResNet-18 ONNX)
├── tests/               # Load tests
├── docker-compose.yml   # Full local stack
├── docker-compose.vllm.yml    # vLLM runner
├── docker-compose.triton.yml  # Triton Inference Server
├── Makefile             # Common dev commands
└── docs/ARCHITECTURE.md # Detailed architecture deep-dive
```

---

## ✨ What's Implemented (V0 – V6)

### 🚀 V0 — Local Runner

Proves a model is a deployable service with a standardized endpoint.

```bash
./bin/opendeploy run tiny-llama-chat
```

The FastAPI backend auto-discovers `AIModel` subclasses from `models/` and serves them. Included model plugins:

| Model | Type | File |
|-------|------|------|
| TinyLlama Chat | LLM | `tiny_llama.py` |
| Mistral Small (4-bit) | Quantized LLM | `mistral_small_quantized.py` |
| Career Advisor | Gemini-powered agent | `career_advisor.py` |
| Symptom Checker | Gemini-powered agent | `symptom_checker.py` |
| Eye Scanner | Vision (retinopathy) | `eye_scanner.py` |
| HF Sentiment | NLP classifier | `hf_sentiment.py` |
| Echo Demo | Test/debug | `echo_demo.py` |

### ☁️ V1 — Single-Cloud Deploy

Provision a GPU VM on AWS and deploy via SSH:

```bash
./bin/opendeploy deploy --cloud aws --public-key ~/.ssh/id_rsa.pub
./deploy.sh ec2-user@<public_ip>
```

Infrastructure is managed by Terraform (`infra/aws/`).

### 💸 V2 — GPU Arbitrage Scheduler

Query real-time AWS Spot and GCP preemptible pricing to find the cheapest availability zone:

```bash
./bin/opendeploy schedule \
  --region us-east-1 \
  --instance-type g5.xlarge \
  --max-price 1.00 \
  --on-demand-price 1.20
```

Supports `--cloud aws` and `--cloud gcp` with automatic zone selection.

### ⚡ V3 — Elastic Cluster Orchestration

Kubernetes-native deployment via a custom operator:

```bash
kubectl apply -f k8s/crd/opendeploy.yaml
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/operator-deployment.yaml
kubectl apply -f k8s/sample/opendeploy-sample.yaml
```

- **K8s Operator** — Python controller: CRD → Deployment + Service + HPA
- **KEDA** — scale-to-zero on Prometheus RPS trigger
- **Karpenter** — just-in-time GPU node provisioning with spot preference

### 👁️ V4 — Real-Time Vision Pipeline

Sub-20ms video inference using WebRTC + shared memory IPC:

```bash
docker compose up -d --build webrtc-gateway api
```

**Data flow:** Camera → WebRTC DataChannel → Go gateway → `/dev/shm` (zero-copy mmap) → Python FastAPI → model inference → JSON response.

Open [frontend/webrtc-client.html](frontend/webrtc-client.html) in a browser to test.

### 🧊 V5 — Edge Model Compiler

Compile, ship, and serve models on edge devices:

```bash
# Build a quantized artifact
./bin/opendeploy build --target edge \
  --model TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --format gguf --quant q4_0 \
  --output artifacts/edge --registry artifacts/registry

# OTA agent on the edge device
python scripts/edge/agent.py \
  --model TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --registry artifacts/registry

# Runtime auto-selection
python scripts/edge/runtime.py \
  --artifact artifacts/edge/TinyLlama_TinyLlama-1.1B-Chat-v1.0/<version>
```

Supports GGUF (llama.cpp), ONNX, and AutoGPTQ formats. Set `LLAMA_CPP_PATH` for real conversions.

### 🖥️ V6 — Next.js Dashboard

Full-featured dashboard at http://localhost:3000 with:

- **Architecture view** — interactive system diagram with wire display modes and layer focus
- **Models** — browse registered models, view details
- **Metrics** — live request stats, latency percentiles, GPU utilization
- **History** — prediction history from the SQLite store
- **WebRTC** — browser-based video stream testing
- **Settings** — API key configuration

### 🏀 V7 — Sports Movement Vision Pipeline (Planned)

A universal sports movement detection and classification system built on top of the existing WebRTC + shared-memory pipeline. The model watches live video, draws segmentation boxes around athletes, and identifies the **exact movement** being performed — across every sport that has ever existed.

**Goal:** Given a live camera feed of any sporting event, the system:
1. Detects all human subjects in the frame via instance segmentation (bounding boxes + pixel masks)
2. Estimates skeletal pose (17+ keypoints per person) for biomechanical analysis
3. Buffers a temporal window of frames to capture motion over time
4. Classifies the movement being performed (e.g., hook shot, bicycle kick, Eurostep, crossover, rainbow flick, slap shot, spike, etc.)
5. If the movement doesn't match any known action, flags it as **novel**, generates a descriptive name, and writes a natural-language description of what is happening in the frame

**Architecture:**

```
Camera → WebRTC DataChannel → Go Gateway → /dev/shm Ring Buffer (N frames)
                                                    │
                                         ┌──────────┴──────────┐
                                         ▼                      ▼
                                  YOLOv8-Seg               YOLOv8-Pose
                                  (Triton ONNX)            (Triton ONNX)
                                  bboxes + masks           skeleton keypoints
                                         │                      │
                                         └──────────┬───────────┘
                                                    ▼
                                        Temporal Action Classifier
                                        (SlowFast / X3D / VideoMAE)
                                        (Triton TensorRT / ONNX)
                                                    │
                                          ┌─────────┴─────────┐
                                          ▼                   ▼
                                   Known Action          Unknown Action
                                   label + conf          ▼
                                          │         VLM Description
                                          │         (Gemini / GPT-4V)
                                          │         novel name + desc
                                          └─────────┬─────────┘
                                                    ▼
                                        JSON Response + Canvas Overlay
                                        bboxes, masks, skeleton, label,
                                        confidence, description
```

**Tech Stack:**

| Layer | Technology | Purpose |
|-------|------------|--------|
| Detection + Segmentation | YOLOv8x-seg / YOLOv11-seg (Ultralytics) | Person instance segmentation — bounding boxes + pixel masks |
| Pose Estimation | YOLOv8x-pose / RTMPose | 17-keypoint skeleton per person for biomechanical movement encoding |
| Temporal Backbone | SlowFast (Meta) / X3D / VideoMAE / TimeSformer | Multi-frame action recognition — captures motion across a sliding window of 16–64 frames |
| Action Classification Head | Fine-tuned FC layers on temporal features | Maps motion embeddings → sport-specific action labels (10,000+ classes across all sports) |
| Novel Movement Detection | Mahalanobis distance / reconstruction error on action embeddings | Out-of-distribution detector — flags movements that don't match any trained class |
| Novel Movement Description | Gemini 2.0 Flash / GPT-4V via VLM API | Given the segmented frame + pose skeleton, generates a name and natural-language description |
| Frame Buffer | Circular `/dev/shm` ring buffer (N=64 frames) | Replaces current single-frame SHM with temporal window for action models |
| Model Serving | NVIDIA Triton (ONNX / TensorRT) | All CV models served via Triton with dynamic batching; TensorRT for GPU, ONNX for CPU fallback |
| Training Data | Kinetics-700, FineGym, Sports-1M, UCF-Sports, custom scrape | Pre-train on public datasets, fine-tune on curated per-sport move taxonomies |
| Annotation | CVAT / Label Studio | Bounding box, segmentation mask, pose, and temporal action annotation |
| Frontend Overlay | HTML5 Canvas (2D context) | Real-time rendering of bboxes, masks, skeletons, and action labels on top of video feed |

**Movement Taxonomy (initial scope):**

| Sport | Example Moves |
|-------|---------------|
| Basketball | Hook shot, crossover, Eurostep, fadeaway, pump fake, alley-oop, slam dunk, layup, stepback, behind-the-back pass |
| Soccer/Football | Bicycle kick, rainbow flick, Cruyff turn, rabona, trivela, header, sliding tackle, Marseille turn |
| American Football | Touchdown signal, Heisman pose, juke, spin move, stiff arm, QB scramble, hurdle |
| Baseball | Home run swing, bunt, diving catch, pitch windup, slide, steal |
| Tennis | Serve, forehand topspin, backhand slice, drop shot, volley, overhead smash |
| Boxing/MMA | Jab, cross, hook, uppercut, roundhouse kick, takedown, sprawl, armbar |
| Gymnastics | Backflip, front tuck, cartwheel, roundoff, Yurchenko vault, iron cross |
| Swimming | Butterfly stroke, freestyle, backstroke, flip turn, dive entry |
| Track & Field | Sprint start, hurdle clearance, high jump Fosbury flop, javelin throw, shot put, pole vault |
| Wrestling | Single-leg takedown, suplex, fireman's carry, sprawl, pin |
| Cricket | Cover drive, sweep, reverse sweep, yorker delivery, caught-and-bowled |
| Volleyball | Spike, block, dig, set, jump serve, pancake |
| Hockey | Slap shot, wrist shot, deke, hip check, glove save |
| ... | Extensible to every sport — fencing, surfing, skateboarding, climbing, martial arts, etc. |

**Phased Rollout:**

| Phase | Milestone | What Ships |
|-------|-----------|------------|
| P0 | Multi-frame ring buffer | Upgrade SHM from 1-frame to 64-frame circular buffer with per-frame timestamps |
| P1 | Person detection + segmentation | YOLOv8-seg exported to ONNX, served via Triton, bboxes + masks returned in API response |
| P2 | Pose estimation | YOLOv8-pose added as second Triton model, skeleton keypoints overlaid on frontend |
| P3 | Temporal action recognition | SlowFast/X3D trained on Kinetics-700, classifies buffered frame sequences into action labels |
| P4 | Sports-specific fine-tuning | Curated datasets per sport, 10K+ action classes, fine-tuned classification head |
| P5 | Novel movement detection | OOD detector on action embeddings + VLM-powered description generation |
| P6 | Frontend canvas overlay | Real-time bboxes, masks, skeletons, labels, and confidence rendered on the video feed |
| P7 | Training pipeline | End-to-end: data ingestion → annotation (CVAT) → training (PyTorch Lightning) → ONNX export → Triton deploy |

---

## 🔥 vLLM Runner (OpenAI-Compatible)

```bash
docker compose -f docker-compose.vllm.yml up -d vllm
```

Exposes OpenAI-compatible endpoints on http://localhost:8001:

```bash
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"TinyLlama/TinyLlama-1.1B-Chat-v1.0","messages":[{"role":"user","content":"Hello!"}]}'
```

CLI shortcut: `./bin/opendeploy run TinyLlama/TinyLlama-1.1B-Chat-v1.0 --runner vllm`

## ⚙️ Triton Serving (Vision)

```bash
python scripts/export_resnet18_onnx.py
docker compose -f docker-compose.triton.yml up -d
```

Set `TRITON_URL=localhost:8001` on the API container to route the eye scanner model through NVIDIA Triton.

---

## 🛠️ Development

### Prerequisites

- Docker with NVIDIA Container Toolkit (GPU recommended)
- Go 1.21+ (for CLI)
- Python 3.10+ (for running tests locally)
- Node.js 18+ (for dashboard development)
- Terraform (optional, for AWS provisioning)

### Makefile Targets

```bash
make help           # Show all targets
make test           # Python unit tests
make lint           # Lint Python code (ruff)
make fmt            # Format Python code
make build          # Build Go CLI → bin/opendeploy
make go-test        # Go unit tests
make run            # docker compose up -d --build
make stop           # docker compose down
make clean          # Remove build artifacts
```

### Environment Variables

Create a `.env` file in the project root (optional):

```env
OPENDEPLOY_API_KEY=your-secret-key
GEMINI_API_KEY=your-gemini-key          # Required for career_advisor / symptom_checker
```

### Running Tests

```bash
# Python
python -m pytest backend/tests/ -v --tb=short

# Go
cd cli && go test ./...
```

## 📊 Observability

Prometheus metrics are exposed at `GET /metrics/prometheus`:

| Metric | Type |
|--------|------|
| `opendeploy_requests_total` | Counter (path, method, status) |
| `opendeploy_request_latency_ms` | Histogram |
| `opendeploy_compute_ms` | Histogram |
| `opendeploy_active_requests` | Gauge |
| `opendeploy_model_load_ms` | Histogram (model) |

JSON metrics snapshot: `GET /metrics`

Grafana dashboard is auto-provisioned at http://localhost:3002 with request rate, latency percentiles, and GPU stats panels.

## 🔒 Security

| Layer | Mechanism |
|-------|-----------|
| API Authentication | `X-API-Key` header vs `OPENDEPLOY_API_KEY` env var |
| Rate Limiting | Sliding window, configurable (`OPENDEPLOY_RATE_LIMIT_PER_MIN`, default 60) |
| Body Size Limit | `OPENDEPLOY_MAX_BODY_MB` (default 10 MB) |
| CORS | Configurable allowed origins (`OPENDEPLOY_ALLOWED_ORIGINS`) |
| Frame Validation | Max width/height/bytes enforced on WebRTC and upload paths |
| Infrastructure | Terraform security groups (SSH + API ports only) |

## 🌟 Roadmap

- [x] Local model runner with plugin system (V0)
- [x] Single-cloud AWS deployment via Terraform (V1)
- [x] GPU arbitrage scheduler — AWS Spot + GCP preemptible (V2)
- [x] Kubernetes operator + KEDA + Karpenter (V3)
- [x] WebRTC + shared-memory vision pipeline (V4)
- [x] Edge model compiler — GGUF / ONNX quantization (V5)
- [x] Next.js dashboard with architecture visualization (V6)
- [x] Prometheus + Grafana observability stack
- [x] gRPC service contract (`proto/v1/`)
- [x] vLLM and Triton runner integrations
- [ ] **V7-P0:** Multi-frame SHM ring buffer (64 frames, temporal window)
- [ ] **V7-P1:** Person detection + instance segmentation (YOLOv8-seg on Triton)
- [ ] **V7-P2:** Pose estimation pipeline (YOLOv8-pose, 17-keypoint skeletons)
- [ ] **V7-P3:** Temporal action recognition (SlowFast / X3D on Kinetics-700)
- [ ] **V7-P4:** Sports-specific fine-tuning (10K+ action classes across all sports)
- [ ] **V7-P5:** Novel movement detection + VLM description generation
- [ ] **V7-P6:** Frontend canvas overlay (bboxes, masks, skeletons, labels)
- [ ] **V7-P7:** End-to-end training pipeline (CVAT → PyTorch Lightning → Triton)
- [ ] Multi-region failover
- [ ] A/B testing and canary deployments
- [ ] OCI artifact push via ORAS
- [ ] GPU sharing and request batching

## 📄 License

MIT

## 📞 Links

- **Architecture Deep-Dive**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Issues**: [GitHub Issues](https://github.com/Bryanjaimes/openDeploy/issues)

---

Built with ❤️ by Bryan Jaimes
