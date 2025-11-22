# OpenDeploy v2# OpenDeploy



A platform for developers to deploy AI models with auto-generated UIs.**One-click platform to deploy and scale ML models to the cheapest/fastest cloud automatically.**



## Structure[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

- `backend/`: FastAPI server to handle model deployment and inference requests.

- `frontend/`: Web interface (will eventually auto-generate UIs based on model input/output schema).## 🚀 Vision

- `models/`: Directory to store or reference AI models.

OpenDeploy democratizes AI deployment. Anyone can deploy powerful ML models (LLMs, vision, speech, diffusion) in 60 seconds—no Kubernetes or cloud APIs required. We automatically find the cheapest/fastest GPU, scale to zero, and provide production-grade observability.

## Vision

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

Access Grafana at `http://localhost:3000` (default credentials in `docker-compose.yml`)

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
