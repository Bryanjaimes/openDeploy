# OpenDeploy — The Sovereign AI Cloud Platform

OpenDeploy is an open-source, multi-cloud orchestration engine that treats AI models as first-class citizens. It lets engineers build, optimize, and serve models (LLMs, Vision, Diffusion) across any compute substrate—from AWS Spot to rural edge devices—with a single CLI command.

## 🚀 V0 (Local Runner)

Goal: prove that a model is a deployable service with a standardized local endpoint.

### 1) Build the CLI

```bash
cd cli
go build -o opendeploy ./cmd/opendeploy
```

### 2) Run a model locally

```bash
./opendeploy run tiny-llama-chat
```

The local runner starts the backend container and exposes:

- `POST http://localhost:8000/generate`

Example request:

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: secret-key-123" \
  -d '{"prompt":"Hello!","model":"tiny-llama-chat"}'
```

## ☁️ V1 (Single-Cloud Deploy)

Provision a GPU VM on AWS and deploy the runner:

```bash
# Build CLI
cd cli
go build -o opendeploy ./cmd/opendeploy

# Provision cloud (requires Terraform + AWS credentials)
./opendeploy deploy --cloud aws --public-key ~/.ssh/id_rsa.pub

# Deploy app to the new VM
./deploy.sh ec2-user@<public_ip>
```

## 💸 V2 (AWS Spot Scheduling)

Query AWS Spot pricing and choose the cheapest availability zone under a max price:

```bash
# Build CLI
cd cli
go build -o opendeploy ./cmd/opendeploy

# Get a scheduling recommendation
./opendeploy schedule \
  --region us-east-1 \
  --instance-type g5.xlarge \
  --max-price 1.00 \
  --on-demand-price 1.20
```

This prints the cheapest AZ and an estimated savings percentage vs on-demand pricing.

## ⚡ V3 (Elastic Cluster Orchestration)

Goal: stop managing VMs and move to cluster-native orchestration.

Implemented:
- **K8s Operator**: Custom controller that converts OpenDeploy configs into Deployments/Services and updates status.
- **Autoscaling**: HPA creation via `spec.autoscaling` (CPU-based).
- **KEDA/Karpenter Manifests**: Ready-to-apply templates for scale-to-zero and node provisioning.
- **Karpenter bootstrap**: IAM, discovery tags, and controller install are set up.

Remaining:
None.

Local kind quickstart:
```bash
kubectl apply -f k8s/crd/opendeploy.yaml
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/operator-deployment.yaml
kubectl apply -f k8s/sample/opendeploy-sample.yaml
```

If you use HPA locally, install metrics-server:
```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deployment metrics-server --type='json' -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
```

Resume bullet:
*Implemented a serverless GPU architecture using Kubernetes, Karpenter, and KEDA to achieve rapid cold-starts and scale-to-zero efficiency.*

## 👁️ V4 — The "Visionary" (High-Performance Pipeline)

Goal: solve the Physical AI latency problem.

Build:
- **WebRTC Gateway**: A sidecar container (Go/Pion) that accepts video streams.
- **Zero-Copy Buffer**: Use shared memory (/dev/shm) to pass raw frames from the WebRTC gateway to the Python inference container without serialization overhead.
- **Inference**: Run TensorRT-optimized models on the frames.

Local quickstart:
```bash
docker compose up -d --build webrtc-gateway api
```

Browser client example:
- Open [frontend/webrtc-client.html](frontend/webrtc-client.html) in a browser and click Start Stream.

Shared-memory frame format (DataChannel payload):
- First 12 bytes: little-endian uint32 width, uint32 height, uint32 format
- Remaining bytes: raw frame data
- Format values: 1=RGB, 2=RGBA, 3=GRAY

The gateway writes frames to /dev/shm/opendeploy_frames. The API reads the latest frame at:
- POST /vision/stream/predict

Resume bullet:
*Engineered a low-latency video ingestion pipeline using WebRTC and shared memory buffers, reducing end-to-end computer vision latency to <20ms.*

## 🧊 V5 — The "Edge Transpiler" (Model Compiler)

Goal: run the same model on edge devices (Raspberry Pi, offline laptops) by compiling and shipping optimized artifacts.

What this does:
- **Edge Build**: compiles a model into GGUF (llama.cpp) or ONNX using a quantization preset (e.g., 4-bit).
- **Artifact Registry**: stores versioned artifacts in a lightweight registry directory (or OCI via oras later).
- **Edge Agent (OTA)**: polls the registry and pulls the newest artifact to the device.
- **Runtime Selector**: picks the right runtime based on the artifact format.

Build (local):
```bash
opendeploy build --target edge --model TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --format gguf --quant q4_0 --output artifacts/edge --registry artifacts/registry
```

Edge agent (OTA):
```bash
python scripts/edge/agent.py --model TinyLlama/TinyLlama-1.1B-Chat-v1.0 --registry artifacts/registry
```

Runtime selection (edge):
```bash
python scripts/edge/runtime.py --artifact artifacts/edge/TinyLlama_TinyLlama-1.1B-Chat-v1.0/<version>
```

Notes:
- Set `LLAMA_CPP_PATH` or `AUTOGPTQ_BIN` to enable real conversions. Without them, the pipeline generates a placeholder artifact and a manifest for integration testing.
- The registry is currently a local directory; OCI push can be added via `oras`.

Resume bullet:
*Built an automated model quantization pipeline that compiles PyTorch checkpoints into hardware-optimized artifacts (GGUF/ONNX) for edge deployment.*

## 🔥 vLLM Runner (OpenAI-Compatible)

Run the vLLM server locally (GPU recommended):

```bash
docker compose -f docker-compose.vllm.yml up -d vllm
```

The server will listen on http://localhost:8001 and expose OpenAI-compatible endpoints, for example:

```bash
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"TinyLlama/TinyLlama-1.1B-Chat-v1.0","messages":[{"role":"user","content":"Hello!"}]}'
```

CLI shortcut:

```bash
opendeploy run TinyLlama/TinyLlama-1.1B-Chat-v1.0 --runner vllm
```

## ⚙️ Optional: Triton Serving (Vision)

If you want the eye scanner to run via NVIDIA Triton, export the ONNX model and start Triton:

```bash
# Export ResNet-18 ONNX into the Triton model repo
python scripts/export_resnet18_onnx.py

# Start Triton
docker compose -f docker-compose.triton.yml up -d
```

Then set these env vars for the API container (or your host):

- `TRITON_URL=localhost:8001`
- `TRITON_MODEL_NAME=resnet18`
- `TRITON_INPUT_NAME=input`
- `TRITON_OUTPUT_NAME=logits`

The `diabetic-retinopathy-glaucoma-detector` model will route inference through Triton when `TRITON_URL` is set.

## Structure

- `backend/`: FastAPI server for model inference and history
- `frontend/`: Web UI for the demo platform
- `models/`: Local model plugins
- `cli/`: Go CLI (V0 runner)

## ✨ Features

To help people create and deploy technology that improves lives, such as medical diagnosis models.

- **One-Click Deployment**: Deploy LLMs, diffusion models, speech, and vision models with a single command
- **Auto-Optimization**: Automatically selects the cheapest GPU/region based on real-time pricing
- **Multi-Cloud**: Support for AWS, Azure, GCP, and local Kubernetes
- **Unified API**: OpenAI-compatible API endpoints for all model types
- **Autoscaling**: Scale to zero when idle, scale up automatically under load
- **Production-Ready**: Built-in observability, SLOs, rollbacks, and A/B testing
- **Cost Transparency**: Real-time cost tracking and $/inference metrics

## 🎯 Quick Start

```bash
# Install CLI
pip install opendeploy

# Deploy your first model
opendeploy deploy --model llama3 --provider auto

# Test it
curl -X POST https://your-endpoint/v1/chat/completions \
  -H "Authorization: Bearer $OPENDEPLOY_API_KEY" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}]}'
```

## 📦 Supported Models

### Language Models (LLMs)
- Llama 3, Mistral, Gemma, Phi-3
- OpenAI-compatible API

### Image Generation
- Stable Diffusion, SDXL, DALL-E

### Speech
- **STT**: Whisper (all sizes)
- **TTS**: Bark, StyleTTS2

### Vision
- CLIP, YOLOv8, SAM

## 🏗️ Architecture

```
openDeploy/
├── api/              # FastAPI gateway + routing
├── scheduler/        # Job queue, autoscaler, placement engine
├── models/           # Model runners (LLM, diffusion, speech, vision)
├── ui/               # Dashboard (React/Svelte + Tailwind)
├── infra/            # Terraform modules for AWS/Azure/GCP/K8s
├── shared/           # Shared schemas, utilities, provider contracts
├── demos/            # Example notebooks and deployments
└── .github/          # CI/CD workflows
```

## 🛠️ Development Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Docker
- Terraform (optional, for infra deployment)

### Local Development

```bash
# Clone the repository
git clone https://github.com/Bryanjaimes/openDeploy.git
cd openDeploy

# Set up Python virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start local services
docker-compose up -d

# Run API server
cd api
uvicorn main:app --reload

# Run UI (in another terminal)
cd ui
npm install
npm run dev
```

## 📊 Observability

OpenDeploy includes built-in observability:

- **Metrics**: Prometheus + Grafana dashboards (p50/p95 latency, tokens/s, $/1k tokens)
- **Logs**: Centralized logging with Loki
- **Tracing**: OpenTelemetry distributed tracing
- **Alerts**: SLO-based alerting

Access Grafana at `http://localhost:3002` (default credentials in `docker-compose.yml`)

Local Prometheus + Grafana (V5 baseline):
```bash
docker compose up -d prometheus grafana
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3002 (admin/admin)

## 🤝 Contributing

We love contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🌟 Roadmap

- [x] Multi-cloud provider support (AWS, Azure, GCP)
- [x] LLM deployment (Llama, Mistral, Gemma)
- [x] Image generation (Stable Diffusion)
- [ ] Speech-to-Text (Whisper)
- [ ] Text-to-Speech (Bark, StyleTTS2)
- [ ] Vision models (CLIP, YOLO, SAM)
- [ ] A/B testing and canary deployments
- [ ] Multi-region failover
- [ ] GPU sharing and batching optimization
- [ ] Model quantization (ONNX, TensorRT)

## 💡 Why OpenDeploy?

**For Developers**: Ship AI features without becoming a cloud/K8s expert

**For Startups**: Minimize inference costs with automatic optimization

**For Enterprises**: Production-grade reliability with SLOs and security built-in

## 📞 Support

- **Documentation**: [docs.opendeploy.dev](https://docs.opendeploy.dev)
- **Discord**: [Join our community](https://discord.gg/opendeploy)
- **Issues**: [GitHub Issues](https://github.com/Bryanjaimes/openDeploy/issues)

---

Built with ❤️ by the OpenDeploy community
