# Contributing to OpenDeploy

Thank you for your interest in contributing. This guide covers everything you need to get started.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Development Setup](#development-setup)
3. [Running Tests](#running-tests)
4. [Adding a New Model](#adding-a-new-model)
5. [Code Style](#code-style)
6. [Commit Messages](#commit-messages)
7. [Pull Request Process](#pull-request-process)
8. [Architecture Notes](#architecture-notes)

---

## Project Overview

OpenDeploy has four main languages/runtimes:

| Component | Language | Directory |
|-----------|----------|-----------|
| Model runner + API | Python (FastAPI) | `backend/`, `models/` |
| CLI | Go (Cobra) | `cli/` |
| WebRTC gateway | Go (Pion) | `webrtc-gateway/` |
| Dashboard | TypeScript (Next.js) | `frontend/dashboard/` |
| K8s operator | Python | `operator/` |

---

## Development Setup

### Prerequisites

- Docker with NVIDIA Container Toolkit (GPU recommended, not required)
- Go 1.21+
- Python 3.10+
- Node.js 18+ (for dashboard)

### Quick Start

```bash
# 1. Clone
git clone https://github.com/Bryanjaimes/openDeploy.git
cd openDeploy

# 2. Build CLI
cd cli && go build -o ../bin/opendeploy ./cmd/opendeploy && cd ..

# 3. Start the full stack
docker compose up -d --build

# 4. Verify
curl http://localhost:8000/health
```

### Environment Variables

Create a `.env` file in the project root:

```env
OPENDEPLOY_API_KEY=dev-test-key
GEMINI_API_KEY=your-gemini-key          # Only needed for career_advisor / symptom_checker models
```

---

## Running Tests

### Python

```bash
# All tests
python -m pytest backend/tests/ -v --tb=short

# Specific test file
python -m pytest backend/tests/test_api.py -v

# With coverage
python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

### Go

```bash
cd cli && go test ./...
```

### Makefile shortcuts

```bash
make test       # Python tests
make go-test    # Go tests
make lint       # Lint Python (ruff check)
make fmt        # Format Python (ruff format)
```

---

## Adding a New Model

This is the most common contribution. OpenDeploy uses a **plugin system** — drop a Python file into `models/` and it's automatically discovered, registered, and served.

### Step 1: Create the Model File

Create `models/my_model.py`:

```python
from backend.interface import AIModel

class MyModel(AIModel):
    @property
    def name(self) -> str:
        return "my-cool-model"    # URL-safe, unique

    @property
    def input_type(self) -> str:
        return "text"              # "text", "image", or "audio"

    @property
    def version(self) -> str:
        return "1.0.0"            # Optional, defaults to "0.0.0"

    def load(self):
        """Called once at startup. Load weights, initialize resources."""
        self.ready = True

    async def predict(self, input_data) -> dict:
        """Called on each inference request. Return a JSON-serializable dict."""
        return {"result": f"Processed: {input_data}"}
```

### Step 2: Test It

```bash
# Start the server
python -m uvicorn backend.main:app --reload

# Hit the endpoint
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-test-key" \
  -d '{"prompt": "Hello!", "model": "my-cool-model"}'
```

### Step 3: Add a Test

Create or update `backend/tests/test_my_model.py`:

```python
import pytest
from models.my_model import MyModel

def test_model_loads():
    m = MyModel()
    m.load()
    assert m.ready

@pytest.mark.asyncio
async def test_model_predicts():
    m = MyModel()
    m.load()
    result = await m.predict("test input")
    assert "result" in result
```

### AIModel Interface Reference

| Member | Required | Description |
|--------|----------|-------------|
| `name` | Yes | Unique model identifier (property) |
| `input_type` | Yes | `"text"`, `"image"`, or `"audio"` (property) |
| `version` | No | Semantic version string (defaults to `"0.0.0"`) |
| `load()` | Yes | Load model weights; set `self.ready = True` when done |
| `predict(input_data)` | Yes | Async. Return a dict. |
| `hardware_requirements` | No | Dict with `min_ram` (GB) and `min_vram` (GB) |

---

## Code Style

### Python

- Formatter: **ruff format** (Black-compatible)
- Linter: **ruff check**
- Type hints encouraged on public functions
- Docstrings on modules and classes (Google style)

```bash
make fmt    # Auto-format
make lint   # Check
```

### Go

- Standard `gofmt`
- No external linter enforced; `go vet` on CI

### TypeScript

- ESLint config in `frontend/dashboard/eslint.config.mjs`
- Prettier via ESLint integration

---

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add pose estimation model (V7-P2)
fix: ring buffer double-read race condition
docs: add threshold sweep methodology to BENCHMARK_REPORT
perf: reduce ONNX preprocess latency by 2ms
test: add SHM ring buffer edge case tests
refactor: extract NMS into standalone function
```

Prefix with scope when useful: `feat(vision): ...`, `fix(gateway): ...`, `docs(k8s): ...`

---

## Pull Request Process

1. **Fork** the repository and create a branch from `main`
2. **Make your changes** — keep PRs focused on a single concern
3. **Add tests** for new functionality
4. **Run the test suite** (`make test && make go-test`)
5. **Update documentation** if you changed behavior:
   - Public API changes → update `README.md`
   - Architecture changes → update `docs/ARCHITECTURE.md`
   - Vision pipeline changes → update `docs/VISION_PIPELINE.md`
   - New benchmarks → run `scripts/benchmark_vision.py` and update `docs/BENCHMARK_REPORT.md`
   - Any shipped change → add entry to `CHANGELOG.md`
6. **Open a PR** with a clear description of what and why
7. PRs require passing CI checks before merge

---

## Architecture Notes

For contributors working on deeper changes, these resources explain the system design:

| Document | Contents |
|----------|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System context diagram, component breakdown, design trade-offs |
| [docs/VISION_PIPELINE.md](docs/VISION_PIPELINE.md) | Complete YOLO webcam pipeline: data flow, SHM protocol, iteration history |
| [docs/BENCHMARK_REPORT.md](docs/BENCHMARK_REPORT.md) | All benchmark runs with tables, percentiles, and cross-iteration comparison |
| [CHANGELOG.md](CHANGELOG.md) | Version-by-version history of every shipped change |
| [k8s/README.md](k8s/README.md) | Kubernetes operator setup and KEDA/Karpenter config |
| [models/README.md](models/README.md) | Model plugin quick reference |

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Go CLI + Python runner | Go: single-binary distribution, fast scheduling. Python: ML ecosystem. Clean boundary. |
| Shared memory IPC (not gRPC) | Zero-copy is critical for 60fps video. Saves ~5ms per frame vs gRPC. |
| Pure-NumPy NMS | No torchvision dependency. Runs on any machine with numpy. |
| SQLite (not Postgres) | Sufficient for single-node. Swappable via `OPENDEPLOY_DATABASE_URL`. |
| Plugin-based model loading | Drop a file in `models/`, restart, done. No registration code needed. |

---

## Questions?

Open an issue at [GitHub Issues](https://github.com/Bryanjaimes/openDeploy/issues) or start a discussion.
