"use client";

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { fetchGlossaryDescription } from "@/lib/api";

/* ════════════════════════════════════════════════════════════════
   OpenDeploy Architecture v4 — Focus View · Component Selection
   Multi-select → isolated focus layer with AI-described relationships
   ════════════════════════════════════════════════════════════════ */

/* ── Types ───────────────────────────────────────────────────── */

interface Impact {
  category: string;
  label: string;
  delta: "better" | "worse" | "neutral";
  reason: string;
}

interface Alternative {
  name: string;
  icon: string;
  impacts: Impact[];
  summary: string;
  affectedWires: string[];
}

interface ArchComponent {
  id: string;
  label: string;
  layer: string;
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
  icon: string;
  tech: string[];
  files: string[];
  description: string;
  details: string;
  connections: string[];
  qa: { q: string; a: string }[];
  alternatives: Alternative[];
}

interface Wire {
  id: string;
  from: string;
  to: string;
  label: string;
  protocol: string;
  port?: string;
  dataFlow: string;
  critical?: boolean;
}

/* ── Wires ───────────────────────────────────────────────────── */

const WIRES: Wire[] = [
  { id: "w1", from: "browser", to: "dashboard", label: "Page Load", protocol: "HTTPS", port: "3000", dataFlow: "HTML/CSS/JS bundles, RSC payloads, static assets via Next.js App Router" },
  { id: "w2", from: "browser", to: "nginx", label: "API Proxy", protocol: "HTTPS", port: "3000", dataFlow: "/api/* requests proxied through nginx reverse proxy to backend" },
  { id: "w3", from: "browser", to: "webrtc_gw", label: "WebRTC Signaling", protocol: "HTTP→WebRTC", port: "7000", dataFlow: "SDP offer/answer exchange, then P2P DataChannel for raw video frames (binary)" },
  { id: "w4", from: "cli", to: "docker_compose", label: "Orchestration", protocol: "Docker API", port: "unix:///var/run/docker.sock", dataFlow: "docker compose up/down/build commands via Docker SDK, GPU device requests" },
  { id: "w5", from: "cli", to: "terraform", label: "IaC Provisioning", protocol: "Terraform CLI", dataFlow: "terraform init → plan → apply, state management, HCL variable injection" },
  { id: "w6", from: "cli", to: "fastapi", label: "Health Probe", protocol: "HTTP GET", port: "8000", dataFlow: "GET /health response {status: healthy} — used by deploy scripts to verify startup", critical: true },
  { id: "w7", from: "grpc_client", to: "fastapi", label: "gRPC Contract", protocol: "gRPC/HTTP2", port: "50051", dataFlow: "Infer(prompt, image, temperature) → InferenceResponse(text, compute_ms, tokens). Streaming via InferStream for token-by-token." },
  { id: "w8", from: "dashboard", to: "nginx", label: "Reverse Proxy", protocol: "HTTP", port: "3000→8000", dataFlow: "Next.js SSR/CSR → nginx → proxy_pass to FastAPI. Headers: X-API-Key, Content-Type" },
  { id: "w9", from: "nginx", to: "fastapi", label: "Upstream Proxy", protocol: "HTTP/1.1", port: "8000", dataFlow: "proxy_pass http://api:8000, proxy_set_header Host, X-Real-IP, X-Forwarded-For, WebSocket upgrade" },
  { id: "w10", from: "fastapi", to: "registry", label: "Model Lookup", protocol: "In-process", dataFlow: "registry.get_model(name) → BaseModel instance. registry.list_models() → [{name, input_type, version, ready}]" },
  { id: "w11", from: "registry", to: "models", label: "Plugin Load", protocol: "importlib", dataFlow: "spec_from_file_location → module_from_spec → exec_module → subclass introspection → register()" },
  { id: "w12", from: "fastapi", to: "database", label: "ORM Queries", protocol: "SQLAlchemy", port: "file:opendeploy.db", dataFlow: "Session.add(Prediction), Session.query(GlossaryCache).filter_by(term=...), init_db() creates tables", critical: true },
  { id: "w13", from: "fastapi", to: "metrics_store", label: "Metrics Record", protocol: "In-process", dataFlow: "record_request(duration_ms, status, model_name), record_compute(ms), inc_active/dec_active, record_tokens(in, out)" },
  { id: "w14", from: "fastapi", to: "shm_reader", label: "Frame Read", protocol: "mmap", dataFlow: "SharedMemoryFrameReader.read_latest() → ShmFrame(w, h, fmt, data). ODSH header: magic+ver+W+H+fmt+len+seq+ts (40B)" },
  { id: "w15", from: "fastapi", to: "openai_api", label: "Glossary AI", protocol: "HTTPS", port: "443", dataFlow: "POST chat/completions {model: gpt-4o-mini, messages: [{role: system, content: ...}]}. JSON response cached in GlossaryCache" },
  { id: "w16", from: "fastapi", to: "prometheus_exp", label: "Metric Emit", protocol: "In-process", dataFlow: "REQUESTS_TOTAL.labels(path,method,status).inc(), REQUEST_LATENCY_MS.observe(ms), ACTIVE_REQUESTS.inc/dec()" },
  { id: "w17", from: "metrics_store", to: "prometheus_exp", label: "Snapshot → Prom", protocol: "In-process", dataFlow: "MetricsStore.snapshot() feeds JSON endpoint; Prometheus counters/histograms feed /metrics/prometheus text format" },
  { id: "w18", from: "webrtc_gw", to: "shm_reader", label: "Frame Write", protocol: "mmap", port: "/dev/shm", dataFlow: "ShmWriter.WriteFrame(w, h, fmt, data) → 40B ODSH header + raw pixels. Atomic seq++ for consistency. Zero-copy, <2ms", critical: true },
  { id: "w19", from: "prometheus", to: "prometheus_exp", label: "Scrape", protocol: "HTTP GET", port: "8000", dataFlow: "GET /metrics/prometheus every 15s → text/plain Counter/Histogram/Gauge. Stored in TSDB with 15s resolution" },
  { id: "w20", from: "grafana", to: "prometheus", label: "PromQL Query", protocol: "HTTP", port: "9090", dataFlow: "rate(opendeploy_requests_total[5m]), histogram_quantile(0.99, ...), opendeploy_active_requests" },
  { id: "w21", from: "docker_compose", to: "fastapi", label: "Container: api", protocol: "Docker", port: "8000:8000", dataFlow: "Dockerfile build, NVIDIA GPU runtime, env vars (API_KEY, DB_URL), /dev/shm mount, IPC host" },
  { id: "w22", from: "docker_compose", to: "webrtc_gw", label: "Container: webrtc", protocol: "Docker", port: "7000:7000", dataFlow: "webrtc-gateway/Dockerfile, shared /dev/shm volume with api container, IPC host mode" },
  { id: "w23", from: "docker_compose", to: "dashboard", label: "Container: dashboard", protocol: "Docker", port: "3000:3000", dataFlow: "frontend/dashboard/Dockerfile, multi-stage build (deps → build → runner), next start" },
  { id: "w24", from: "docker_compose", to: "prometheus", label: "Container: prometheus", protocol: "Docker", port: "9090:9090", dataFlow: "prom/prometheus image, prometheus.yml mount, scrape_configs targeting api:8000" },
  { id: "w25", from: "docker_compose", to: "grafana", label: "Container: grafana", protocol: "Docker", port: "3002:3000", dataFlow: "grafana/grafana image, provisioned datasources + dashboards, anonymous auth" },
  { id: "w26", from: "kubernetes", to: "docker_compose", label: "K8s Deployments", protocol: "K8s API", dataFlow: "Operator → Deployment (pod spec, GPU limits) → Service (ClusterIP) → HPA (cpu target) → KEDA ScaledObject" },
  { id: "w27", from: "terraform", to: "kubernetes", label: "Node Provision", protocol: "AWS API", dataFlow: "EC2 g5.xlarge → EKS node join. Karpenter EC2NodeClass + NodePool for GPU spot provisioning" },
  { id: "w28", from: "edge", to: "models", label: "ONNX Export", protocol: "File I/O", dataFlow: "torch.onnx.export(model) → model.onnx. Edge agent polls registry dir, copies new versions to cache" },
  { id: "w29", from: "triton_vllm", to: "fastapi", label: "Inference Backend", protocol: "HTTP/gRPC", port: "8001/8002", dataFlow: "Triton: model_repo → config.pbtxt → ONNX/TRT inference. vLLM: OpenAI-compatible /v1/completions" },
];

/* ── Adjacency for connection validation ─────────────────────── */

function buildAdjacency(): Map<string, Set<string>> {
  const adj = new Map<string, Set<string>>();
  for (const w of WIRES) {
    if (!adj.has(w.from)) adj.set(w.from, new Set());
    if (!adj.has(w.to)) adj.set(w.to, new Set());
    adj.get(w.from)!.add(w.to);
    adj.get(w.to)!.add(w.from);
  }
  return adj;
}

const ADJACENCY = buildAdjacency();

/** Check if a candidate has a direct wire with any component in the set */
function isReachableFromSet(candidateId: string, selectedIds: Set<string>): boolean {
  if (selectedIds.size === 0) return true;
  const neighbors = ADJACENCY.get(candidateId);
  if (!neighbors) return false;
  for (const sel of selectedIds) {
    if (neighbors.has(sel)) return true;
  }
  return false;
}

/** Get wires connecting any two components within a set */
function getWiresBetween(ids: Set<string>): Wire[] {
  return WIRES.filter((w) => ids.has(w.from) && ids.has(w.to));
}

/* ── Default component data ──────────────────────────────────── */

const DEFAULT_COMPONENTS: ArchComponent[] = [
  {
    id: "browser", label: "Browser Client", layer: "Clients",
    x: 50, y: 40, w: 155, h: 56, color: "#3b82f6", icon: "🌐",
    tech: ["HTML/CSS/JS", "WebRTC API", "fetch()", "localStorage"],
    files: ["frontend/index.html", "frontend/webrtc-client.html"],
    description: "End-user browser. REST calls to backend, WebRTC video streaming, glassmorphic tooltip hovers.",
    details: "Two UIs: legacy index.html (vanilla JS) + Next.js dashboard.\nAuth via X-API-Key in headers.\nWebRTC client: SDP offer → Go gateway → P2P DataChannel → raw video frames.\nGlossary: hover → localStorage L1 → API L2 → OpenAI L3.",
    connections: ["dashboard", "nginx", "webrtc_gw"],
    qa: [{ q: "How does auth work from the browser?", a: "Every fetch() includes X-API-Key header. Stored in localStorage via useApiKey() hook. Backend validates against OPENDEPLOY_API_KEY env var." }],
    alternatives: [
      { name: "Mobile App (React Native)", icon: "📱", summary: "Replace browser with a native mobile app for on-device inference and push notifications.", affectedWires: ["w1", "w2", "w3"], impacts: [{ category: "UX", label: "Offline support", delta: "better", reason: "Native apps can cache models and run ONNX inference on-device without network" }, { category: "Latency", label: "Push notifications", delta: "better", reason: "FCM/APNS for inference completion instead of polling" }, { category: "Dev Velocity", label: "Code duplication", delta: "worse", reason: "Separate iOS/Android codebase or React Native bridge layer adds complexity" }, { category: "Distribution", label: "App Store review", delta: "worse", reason: "App store submission, review cycles, and update delays vs instant web deploys" }] },
      { name: "Desktop App (Electron)", icon: "🖥️", summary: "Electron wrapper for local GPU inference without server dependency.", affectedWires: ["w1", "w2"], impacts: [{ category: "Performance", label: "Local GPU access", delta: "better", reason: "Direct CUDA/Metal access for on-device inference without HTTP roundtrip" }, { category: "Resources", label: "Memory overhead", delta: "worse", reason: "Electron bundles Chromium (~300MB RAM baseline) plus Node.js runtime" }, { category: "Security", label: "API key storage", delta: "better", reason: "Keychain/Credential Manager instead of localStorage" }, { category: "Distribution", label: "Auto-updates", delta: "neutral", reason: "electron-updater works but adds packaging complexity" }] },
    ],
  },
  {
    id: "cli", label: "Go CLI", layer: "Clients",
    x: 235, y: 40, w: 155, h: 56, color: "#3b82f6", icon: "⌨️",
    tech: ["Go 1.21+", "Cobra", "Docker SDK", "Terraform"],
    files: ["cli/cmd/opendeploy/main.go", "cli/cmd/opendeploy/run.go", "cli/cmd/opendeploy/build.go", "cli/cmd/opendeploy/deploy.go", "cli/cmd/opendeploy/schedule.go"],
    description: "Operator CLI. Orchestrates Docker Compose, Terraform, edge builds, GPU scheduling.",
    details: "Cobra subcommands:\n• run → docker compose up (GPU flags)\n• build → docker build + OCI/ORAS push\n• deploy → terraform init+apply\n• schedule → GPU spot price arbitrage (AWS/GCP)\n\nCross-compiled: GOOS=linux GOARCH=amd64.",
    connections: ["docker_compose", "terraform", "fastapi"],
    qa: [{ q: "How does GPU scheduling work?", a: "Compares spot prices across AWS g4dn/g5/p3 and GCP a2-highgpu regions. Picks cheapest and runs terraform apply." }],
    alternatives: [
      { name: "Python CLI (Click/Typer)", icon: "🐍", summary: "Replace Go CLI with Python for unified language stack.", affectedWires: ["w4", "w5", "w6"], impacts: [{ category: "Dev Velocity", label: "Single language", delta: "better", reason: "Same Python as backend — shared models, no context switching, one toolchain" }, { category: "Performance", label: "Startup time", delta: "worse", reason: "Python CLI cold start ~500ms vs Go's ~5ms. Docker/Terraform calls dominate but feels sluggish" }, { category: "Distribution", label: "Binary distribution", delta: "worse", reason: "Go compiles to a single static binary. Python needs venv, pip, or PyInstaller (100MB+ bundles)" }, { category: "Concurrency", label: "Parallel operations", delta: "worse", reason: "Go goroutines handle concurrent spot price checks naturally. Python needs asyncio or threading" }] },
      { name: "Rust CLI (Clap)", icon: "🦀", summary: "Rust for maximum performance and type safety.", affectedWires: ["w4", "w5", "w6"], impacts: [{ category: "Performance", label: "Startup speed", delta: "better", reason: "~2ms startup, zero-cost abstractions, smaller binary than Go (~5MB vs ~15MB)" }, { category: "Safety", label: "Memory safety", delta: "better", reason: "Compile-time guarantees eliminate null pointers, data races, buffer overflows" }, { category: "Dev Velocity", label: "Development speed", delta: "worse", reason: "Steeper learning curve, longer compile times, smaller ecosystem for infra tooling" }, { category: "Ecosystem", label: "Docker/Terraform SDKs", delta: "worse", reason: "Go has first-party Docker and Terraform SDKs. Rust alternatives are less mature" }] },
    ],
  },
  {
    id: "grpc_client", label: "gRPC Contract", layer: "Clients",
    x: 420, y: 40, w: 155, h: 56, color: "#3b82f6", icon: "📡",
    tech: ["Protobuf v3", "gRPC", "Streaming", "Code Gen"],
    files: ["proto/v1/opendeploy.proto"],
    description: "gRPC service contract. Unary + streaming inference. Auto-generated clients in any language.",
    details: "Service: OpenDeployService\n• Health() → HealthResponse\n• ListModels() → [ModelInfo]\n• Infer(prompt,image,temp) → InferenceResponse\n• InferStream() → stream tokens\n\nNot yet server-implemented — design contract for v2.",
    connections: ["fastapi"],
    qa: [{ q: "Why gRPC alongside REST?", a: "gRPC gives streaming (token-by-token), binary payloads without base64, and auto-generated typed clients. REST stays for browser compatibility." }],
    alternatives: [
      { name: "GraphQL (Apollo)", icon: "◈", summary: "Replace gRPC with GraphQL for flexible queries and subscriptions.", affectedWires: ["w7"], impacts: [{ category: "Flexibility", label: "Query flexibility", delta: "better", reason: "Clients request exactly the fields they need. No over/under-fetching." }, { category: "Browser Support", label: "No codegen needed", delta: "better", reason: "GraphQL works from any HTTP client — no protoc, no generated stubs" }, { category: "Performance", label: "Streaming efficiency", delta: "worse", reason: "GraphQL subscriptions over WebSocket are slower than gRPC HTTP/2 streams for high-throughput token streaming" }, { category: "Typing", label: "Type safety", delta: "worse", reason: "Protobuf gives compile-time type safety with generated code. GraphQL typing is runtime-validated" }] },
      { name: "WebSocket API", icon: "🔌", summary: "Direct WebSocket for bidirectional real-time inference.", affectedWires: ["w7"], impacts: [{ category: "Simplicity", label: "No codegen", delta: "better", reason: "Plain JSON over WebSocket — works in any browser, any language, zero tooling" }, { category: "Browser", label: "Native support", delta: "better", reason: "WebSocket is built into every browser. gRPC needs grpc-web proxy" }, { category: "Ecosystem", label: "Tooling", delta: "worse", reason: "No auto-generated clients, no schema validation, no built-in retry/deadline semantics" }, { category: "Performance", label: "Multiplexing", delta: "worse", reason: "gRPC HTTP/2 multiplexes streams on one connection. WebSocket is single-stream per connection" }] },
    ],
  },
  {
    id: "dashboard", label: "Next.js Dashboard", layer: "Frontend",
    x: 50, y: 145, w: 240, h: 56, color: "#8b5cf6", icon: "📊",
    tech: ["Next.js 16", "TypeScript", "Tailwind v4", "shadcn/ui", "Recharts"],
    files: ["frontend/dashboard/app/layout.tsx", "frontend/dashboard/app/metrics/page.tsx", "frontend/dashboard/lib/api.ts", "frontend/dashboard/components/sidebar.tsx"],
    description: "7-page React dashboard. Glassmorphic AI tooltips.",
    details: "App Router: / (overview), /models/[name], /metrics (9-tier), /architecture, /history, /webrtc, /settings.\nGlossary: hover → localStorage(7d TTL) → POST /glossary/describe → OpenAI → SQLite cache.",
    connections: ["nginx", "fastapi"],
    qa: [{ q: "How does the API client work?", a: "lib/api.ts defines typed fetch wrappers. NEXT_PUBLIC_API_URL defaults to /api (nginx proxy). All calls include X-API-Key header." }],
    alternatives: [
      { name: "Remix", icon: "💿", summary: "Remix for nested routes and server-side data loading.", affectedWires: ["w1", "w8"], impacts: [{ category: "Data Loading", label: "Loader pattern", delta: "better", reason: "Remix loaders co-locate data fetching with routes — no useEffect/useState dance." }, { category: "Bundle Size", label: "Smaller JS", delta: "better", reason: "Remix sends less client JS by default — more work stays on the server" }, { category: "Ecosystem", label: "Component library", delta: "worse", reason: "shadcn/ui and most React component libraries are tested primarily with Next.js" }, { category: "Deployment", label: "Vercel optimization", delta: "worse", reason: "Next.js has first-party Vercel deployment with ISR, edge functions. Remix needs custom setup" }] },
      { name: "SvelteKit", icon: "🔶", summary: "SvelteKit for smaller bundles and reactive simplicity.", affectedWires: ["w1", "w8"], impacts: [{ category: "Performance", label: "Bundle size", delta: "better", reason: "Svelte compiles to vanilla JS — no virtual DOM. 60-80% smaller bundles than React" }, { category: "DX", label: "Less boilerplate", delta: "better", reason: "Reactive declarations ($:), built-in stores, no useState/useEffect/useMemo ceremony" }, { category: "Ecosystem", label: "Component availability", delta: "worse", reason: "React has 10x more components, libraries, and examples than Svelte" }, { category: "Hiring", label: "Developer pool", delta: "worse", reason: "Far fewer Svelte developers available compared to React/Next.js talent pool" }] },
      { name: "Vue + Nuxt", icon: "💚", summary: "Nuxt 3 with Vue's Composition API.", affectedWires: ["w1", "w8"], impacts: [{ category: "DX", label: "Template syntax", delta: "better", reason: "Vue's template syntax is more approachable than JSX for HTML-focused developers" }, { category: "Reactivity", label: "Fine-grained", delta: "better", reason: "Vue's reactivity system is compile-time optimized" }, { category: "TypeScript", label: "TS integration", delta: "neutral", reason: "Nuxt 3 has good TS support but not as deeply integrated as Next.js" }, { category: "Ecosystem", label: "Charting/UI", delta: "worse", reason: "Recharts, shadcn/ui, and most polished component sets are React-first" }] },
    ],
  },
  {
    id: "nginx", label: "Nginx", layer: "Frontend",
    x: 330, y: 145, w: 155, h: 56, color: "#8b5cf6", icon: "🔀",
    tech: ["Nginx", "Reverse Proxy", "SSL", "Static Files"],
    files: ["frontend/nginx.conf"],
    description: "Reverse proxy: serves frontend, routes /api/* → FastAPI:8000.",
    details: "Routes:\n• / → static files / Next.js\n• /api/* → proxy_pass http://api:8000\n• WebSocket upgrade\n\nPort 3000 in Docker Compose.",
    connections: ["fastapi", "dashboard"],
    qa: [],
    alternatives: [
      { name: "Caddy", icon: "🔒", summary: "Caddy with automatic HTTPS.", affectedWires: ["w8", "w9"], impacts: [{ category: "Security", label: "Auto HTTPS", delta: "better", reason: "Caddy auto-provisions Let's Encrypt certs." }, { category: "Config", label: "Caddyfile simplicity", delta: "better", reason: "3-line Caddyfile vs 30-line nginx.conf." }, { category: "Performance", label: "Raw throughput", delta: "worse", reason: "Nginx handles ~50% more req/s at high concurrency." }, { category: "Ecosystem", label: "Community knowledge", delta: "worse", reason: "99% of proxy tutorials use Nginx" }] },
      { name: "Traefik", icon: "🔷", summary: "Traefik for Docker/K8s auto-discovery.", affectedWires: ["w8", "w9"], impacts: [{ category: "Docker", label: "Auto-discovery", delta: "better", reason: "Traefik reads Docker labels to auto-configure routes." }, { category: "K8s", label: "Ingress controller", delta: "better", reason: "Native K8s Ingress support with CRD-based routing." }, { category: "Performance", label: "Overhead", delta: "worse", reason: "Traefik adds ~10ms P99 latency vs Nginx's ~2ms." }, { category: "Complexity", label: "Learning curve", delta: "worse", reason: "Traefik's middleware chain is more complex than nginx.conf" }] },
    ],
  },
  {
    id: "fastapi", label: "FastAPI Backend", layer: "Backend",
    x: 50, y: 260, w: 190, h: 64, color: "#22c55e", icon: "⚡",
    tech: ["Python 3.14", "FastAPI", "Uvicorn", "Pydantic", "async/await"],
    files: ["backend/main.py", "backend/requirements.txt"],
    description: "Core API: inference, model mgmt, metrics, glossary AI, prediction history.",
    details: "Endpoints: /health, /models, /models/{name}/predict, /vision/stream/predict, /metrics, /metrics/prometheus, /generate, /glossary/describe, /glossary/cache, /history\n\nMiddleware: CORS → Rate Limit → Body Size → Metrics",
    connections: ["registry", "database", "metrics_store", "prometheus_exp", "shm_reader", "openai_api"],
    qa: [{ q: "How does the middleware stack work?", a: "LIFO order: metrics (outermost) → security (rate limit + body size) → CORS (innermost). Every request gets timed and counted." }],
    alternatives: [
      { name: "Express.js (Node)", icon: "🟢", summary: "Node.js Express for unified JS stack.", affectedWires: ["w6", "w9", "w10", "w12", "w13", "w15", "w16", "w21"], impacts: [{ category: "Language", label: "Full-stack JS", delta: "better", reason: "Same language as Next.js frontend" }, { category: "Performance", label: "Event loop", delta: "better", reason: "Node excels at I/O-bound work" }, { category: "ML", label: "Python ML ecosystem", delta: "worse", reason: "PyTorch, transformers, numpy are Python-native" }, { category: "Typing", label: "Validation", delta: "worse", reason: "FastAPI+Pydantic gives auto-validated OpenAPI docs" }, { category: "GPU", label: "nvidia-smi / psutil", delta: "worse", reason: "System metrics trivial in Python, needs native addons in Node" }] },
      { name: "Go (Gin/Fiber)", icon: "🔵", summary: "Go HTTP for max throughput.", affectedWires: ["w6", "w9", "w10", "w12", "w13", "w21"], impacts: [{ category: "Performance", label: "Throughput", delta: "better", reason: "5-10x more req/s than Uvicorn" }, { category: "Deployment", label: "Single binary", delta: "better", reason: "Static binary, no venv/pip" }, { category: "ML", label: "Model loading", delta: "worse", reason: "No native PyTorch/transformers" }, { category: "Prototyping", label: "Iteration speed", delta: "worse", reason: "Python hot-reload is faster" }] },
      { name: "Django + DRF", icon: "🎸", summary: "Batteries-included Python.", affectedWires: ["w6", "w9", "w10", "w12", "w21"], impacts: [{ category: "Features", label: "Admin panel", delta: "better", reason: "Free CRUD UI — zero code" }, { category: "ORM", label: "Migrations", delta: "better", reason: "Built-in makemigrations/migrate" }, { category: "Performance", label: "Async support", delta: "worse", reason: "Django async is bolted on" }, { category: "API", label: "Auto-docs", delta: "worse", reason: "FastAPI auto-generates OpenAPI from type hints" }] },
    ],
  },
  {
    id: "registry", label: "Model Registry", layer: "Backend",
    x: 275, y: 255, w: 145, h: 48, color: "#22c55e", icon: "📦",
    tech: ["Python", "importlib", "Plugin Pattern"],
    files: ["backend/registry.py", "backend/loader.py"],
    description: "Dynamic plugin system. Auto-discovers BaseModel subclasses from models/.",
    details: "Convention-over-config:\n• Drop .py in models/ → auto-registered\n• Each model: name, input_type, version, predict()\n• Loader: importlib.util → subclass introspection",
    connections: ["models", "fastapi"],
    qa: [],
    alternatives: [
      { name: "MLflow Registry", icon: "📊", summary: "MLflow for versioned model tracking.", affectedWires: ["w10", "w11"], impacts: [{ category: "Versioning", label: "Model versions", delta: "better", reason: "Tracks versions, stages, lineage" }, { category: "Experiment", label: "Tracking", delta: "better", reason: "Logs hyperparams, metrics, artifacts" }, { category: "Simplicity", label: "Setup overhead", delta: "worse", reason: "Needs tracking server, S3, database" }, { category: "Latency", label: "Model load", delta: "worse", reason: "Loads from remote artifact store" }] },
    ],
  },
  {
    id: "models", label: "AI Models", layer: "Backend",
    x: 455, y: 255, w: 145, h: 48, color: "#f59e0b", icon: "🧠",
    tech: ["PyTorch", "Transformers", "ONNX", "Pillow"],
    files: ["models/echo_demo.py", "models/career_advisor.py", "models/symptom_checker.py", "models/tiny_llama.py"],
    description: "Pluggable AI models. Echo bots to quantized LLMs.",
    details: "echo_demo · career_advisor · symptom_checker · eye_scanner · hf_sentiment · tiny_llama · mistral_small",
    connections: ["registry"],
    qa: [],
    alternatives: [
      { name: "ONNX Runtime Only", icon: "⚙️", summary: "Standardize all models as ONNX.", affectedWires: ["w11"], impacts: [{ category: "Performance", label: "Inference speed", delta: "better", reason: "ONNX Runtime + TensorRT EP is 2-5x faster" }, { category: "Portability", label: "Cross-platform", delta: "better", reason: "Runs on CPU, CUDA, DirectML, CoreML" }, { category: "Flexibility", label: "Dynamic models", delta: "worse", reason: "Not all models export cleanly to ONNX" }, { category: "Development", label: "Debugging", delta: "worse", reason: "Can't debug ONNX graph like Python" }] },
    ],
  },
  {
    id: "database", label: "SQLite + SQLAlchemy", layer: "Backend",
    x: 275, y: 320, w: 145, h: 48, color: "#22c55e", icon: "🗃️",
    tech: ["SQLAlchemy 2.0", "SQLite", "ORM"],
    files: ["backend/database.py"],
    description: "Prediction history + glossary cache. Zero-config SQLite.",
    details: "Tables: Prediction (id, timestamp, model, input, result), GlossaryCache (term, display_name, short, detail, category)",
    connections: ["fastapi"],
    qa: [],
    alternatives: [
      { name: "PostgreSQL", icon: "🐘", summary: "Production-grade concurrent access.", affectedWires: ["w12"], impacts: [{ category: "Concurrency", label: "Write throughput", delta: "better", reason: "MVCC vs SQLite full-DB lock" }, { category: "Queries", label: "JSON operators", delta: "better", reason: "JSONB with GIN indexes" }, { category: "Simplicity", label: "Setup", delta: "worse", reason: "Requires running Postgres server" }, { category: "Cost", label: "Hosting", delta: "worse", reason: "RDS $15/mo vs SQLite $0" }] },
      { name: "MongoDB", icon: "🍃", summary: "Flexible document storage.", affectedWires: ["w12"], impacts: [{ category: "Schema", label: "Flexibility", delta: "better", reason: "Arbitrary JSON natively" }, { category: "Scaling", label: "Horizontal", delta: "better", reason: "MongoDB shards horizontally" }, { category: "Consistency", label: "ACID", delta: "worse", reason: "Weaker consistency guarantees" }, { category: "Ecosystem", label: "SQLAlchemy", delta: "worse", reason: "Must rewrite all ORM code" }] },
      { name: "Redis", icon: "🔴", summary: "In-memory caching.", affectedWires: ["w12"], impacts: [{ category: "Speed", label: "Read latency", delta: "better", reason: "<1ms in-memory reads" }, { category: "TTL", label: "Auto-expiry", delta: "better", reason: "Native TTL on keys" }, { category: "Durability", label: "Data loss risk", delta: "worse", reason: "AOF/RDB can lose recent writes" }, { category: "Querying", label: "SQL support", delta: "worse", reason: "No SQL, manual index design" }] },
    ],
  },
  {
    id: "metrics_store", label: "Metrics Store", layer: "Backend",
    x: 50, y: 380, w: 160, h: 48, color: "#22c55e", icon: "📈",
    tech: ["threading", "deque", "psutil", "nvidia-smi"],
    files: ["backend/metrics.py"],
    description: "Thread-safe 40+ metrics from GPU transistor-level to app KPIs.",
    details: "9 Tiers: App → Latency → Compute → Tokens → Payload → Cost → GPU (24 fields) → CPU → System",
    connections: ["fastapi", "prometheus_exp"],
    qa: [],
    alternatives: [
      { name: "OpenTelemetry SDK", icon: "🔭", summary: "Vendor-neutral observability.", affectedWires: ["w13", "w16", "w17"], impacts: [{ category: "Tracing", label: "Distributed traces", delta: "better", reason: "Follows requests across services" }, { category: "Vendor", label: "Portability", delta: "better", reason: "Export to Jaeger, Zipkin, Datadog" }, { category: "Overhead", label: "Memory/CPU", delta: "worse", reason: "~20MB + ~5% CPU overhead" }, { category: "Simplicity", label: "Setup complexity", delta: "worse", reason: "Needs collector sidecar, config" }] },
      { name: "StatsD + Datadog", icon: "🐶", summary: "Managed observability platform.", affectedWires: ["w13", "w17"], impacts: [{ category: "Operations", label: "Managed platform", delta: "better", reason: "Storage, alerting, anomaly detection" }, { category: "Alerting", label: "ML-based alerts", delta: "better", reason: "Auto-learns baselines" }, { category: "Cost", label: "Pricing", delta: "worse", reason: "$15-23/host/mo vs $0" }, { category: "Vendor Lock", label: "Lock-in", delta: "worse", reason: "Proprietary metrics format" }] },
    ],
  },
  {
    id: "prometheus_exp", label: "Prometheus Exporter", layer: "Backend",
    x: 245, y: 380, w: 155, h: 48, color: "#22c55e", icon: "🔥",
    tech: ["prometheus_client", "Counter", "Histogram", "Gauge"],
    files: ["backend/metrics_prom.py"],
    description: "Prometheus-compatible at /metrics/prometheus.",
    details: "opendeploy_requests_total, request_latency_ms, active_requests, compute_ms, model_load_ms",
    connections: ["prometheus", "metrics_store"],
    qa: [],
    alternatives: [],
  },
  {
    id: "shm_reader", label: "Shared Memory IPC", layer: "Backend",
    x: 455, y: 320, w: 145, h: 48, color: "#06b6d4", icon: "🧬",
    tech: ["mmap", "/dev/shm", "ODSH Protocol"],
    files: ["backend/shm_frames.py", "webrtc-gateway/shm_unix.go"],
    description: "Zero-copy frame sharing. <2ms latency via mmap.",
    details: "ODSH Protocol (40B header): magic+ver+W+H+fmt+len+seq+ts\nDouble-read consistency check.",
    connections: ["webrtc_gw", "fastapi"],
    qa: [],
    alternatives: [
      { name: "gRPC Streaming", icon: "📡", summary: "gRPC bidirectional frame transfer.", affectedWires: ["w14", "w18"], impacts: [{ category: "Portability", label: "Cross-machine", delta: "better", reason: "Works over network" }, { category: "Debugging", label: "Observability", delta: "better", reason: "Inspectable with grpcurl" }, { category: "Latency", label: "Frame transfer", delta: "worse", reason: "~10ms vs SHM's <2ms for 1080p" }, { category: "Throughput", label: "Frame rate", delta: "worse", reason: "gRPC limits to ~15-20fps for 1080p" }] },
      { name: "Redis Pub/Sub", icon: "🔴", summary: "Redis frame message passing.", affectedWires: ["w14", "w18"], impacts: [{ category: "Decoupling", label: "Pub/sub", delta: "better", reason: "Multiple subscribers independently" }, { category: "Portability", label: "Network", delta: "better", reason: "Works across machines" }, { category: "Latency", label: "Frame transfer", delta: "worse", reason: "~5-10ms per frame" }, { category: "Memory", label: "Double storage", delta: "worse", reason: "Frame in Redis AND process memory" }] },
    ],
  },
  {
    id: "openai_api", label: "OpenAI API", layer: "Backend",
    x: 435, y: 380, w: 145, h: 48, color: "#a855f7", icon: "✦",
    tech: ["OpenAI SDK", "gpt-4o-mini", "JSON Mode"],
    files: ["backend/main.py"],
    description: "AI glossary descriptions. Cached in SQLite.",
    details: "POST /glossary/describe → check cache → OpenAI gpt-4o-mini → cache result → localStorage 7d TTL",
    connections: ["fastapi"],
    qa: [],
    alternatives: [
      { name: "Anthropic Claude", icon: "🤖", summary: "Better technical explanations.", affectedWires: ["w15"], impacts: [{ category: "Quality", label: "Technical depth", delta: "better", reason: "Excels at technical nuance" }, { category: "Context", label: "200K tokens", delta: "better", reason: "Larger context window" }, { category: "Cost", label: "Price per token", delta: "worse", reason: "Claude Haiku ~$0.25/1M vs gpt-4o-mini ~$0.15/1M" }, { category: "Speed", label: "TTFT latency", delta: "neutral", reason: "Both ~200-400ms" }] },
      { name: "Local LLM (Ollama)", icon: "🏠", summary: "Zero-cost local generation.", affectedWires: ["w15"], impacts: [{ category: "Cost", label: "Zero API cost", delta: "better", reason: "Free after GPU electricity" }, { category: "Privacy", label: "No data leaves", delta: "better", reason: "Fully air-gapped" }, { category: "Quality", label: "Output quality", delta: "worse", reason: "8B model less nuanced" }, { category: "Resources", label: "GPU memory", delta: "worse", reason: "~6GB VRAM for Llama 3.1 8B" }] },
    ],
  },
  {
    id: "webrtc_gw", label: "WebRTC Gateway", layer: "Real-time",
    x: 50, y: 470, w: 190, h: 48, color: "#06b6d4", icon: "📹",
    tech: ["Go", "Pion WebRTC v3", "mmap", "DataChannel"],
    files: ["webrtc-gateway/main.go", "webrtc-gateway/shm_unix.go"],
    description: "Go signaling server. WebRTC → /dev/shm → Python.",
    details: "Browser → POST /offer (SDP) → PeerConnection → DataChannel → ShmWriter → /dev/shm → Python reads",
    connections: ["browser", "shm_reader"],
    qa: [],
    alternatives: [
      { name: "mediasoup (Node.js)", icon: "🟢", summary: "SFU for multi-party WebRTC.", affectedWires: ["w3", "w18", "w22"], impacts: [{ category: "Multi-party", label: "SFU routing", delta: "better", reason: "Supports multi-party, simulcast" }, { category: "Language", label: "JS ecosystem", delta: "neutral", reason: "Node.js matches frontend stack" }, { category: "Performance", label: "Concurrency", delta: "worse", reason: "Go handles 10K+ conns vs Node ~5K" }, { category: "SHM", label: "mmap access", delta: "worse", reason: "Node.js can't easily do mmap" }] },
    ],
  },
  {
    id: "prometheus", label: "Prometheus", layer: "Observability",
    x: 275, y: 470, w: 145, h: 48, color: "#ef4444", icon: "🔴",
    tech: ["Prometheus", "PromQL", "TSDB", "15s scrape"],
    files: ["prometheus/prometheus.yml"],
    description: "Time-series DB. Scrapes every 15s.",
    details: "Scrape: api:8000/metrics/prometheus @ 15s, local TSDB, 15d retention",
    connections: ["prometheus_exp", "grafana"],
    qa: [],
    alternatives: [
      { name: "Victoria Metrics", icon: "📈", summary: "Better compression and long-term storage.", affectedWires: ["w19", "w20"], impacts: [{ category: "Storage", label: "10x compression", delta: "better", reason: "~10x less disk" }, { category: "Scaling", label: "Cluster mode", delta: "better", reason: "Built-in clustering" }, { category: "Compatibility", label: "PromQL", delta: "neutral", reason: "Supports PromQL + MetricsQL" }, { category: "Ecosystem", label: "Community", delta: "worse", reason: "Smaller community" }] },
    ],
  },
  {
    id: "grafana", label: "Grafana", layer: "Observability",
    x: 455, y: 470, w: 145, h: 48, color: "#ef4444", icon: "📉",
    tech: ["Grafana", "Provisioning", "PromQL"],
    files: ["grafana/dashboards/opendeploy.json", "grafana/provisioning/datasources/datasource.yml"],
    description: "Pre-provisioned dashboards. Port 3002.",
    details: "Datasource: Prometheus, Dashboard: RPS/latency/error/GPU, anonymous auth",
    connections: ["prometheus"],
    qa: [],
    alternatives: [],
  },
  {
    id: "docker_compose", label: "Docker Compose", layer: "Infrastructure",
    x: 50, y: 565, w: 170, h: 48, color: "#f97316", icon: "🐳",
    tech: ["Docker", "Compose", "NVIDIA Toolkit", "GPU"],
    files: ["docker-compose.yml", "docker-compose.vllm.yml", "docker-compose.triton.yml", "Dockerfile"],
    description: "5-service local stack with GPU passthrough.",
    details: "api(8000) · webrtc(7000) · dashboard(3000) · prometheus(9090) · grafana(3002)",
    connections: ["fastapi", "webrtc_gw", "dashboard", "prometheus", "grafana"],
    qa: [],
    alternatives: [
      { name: "Kubernetes (direct)", icon: "☸️", summary: "K8s even for dev.", affectedWires: ["w21", "w22", "w23", "w24", "w25"], impacts: [{ category: "Prod Parity", label: "Dev=Prod", delta: "better", reason: "Same manifests everywhere" }, { category: "Scaling", label: "Auto-scaling", delta: "better", reason: "HPA/KEDA available" }, { category: "Simplicity", label: "Setup overhead", delta: "worse", reason: "10x more setup" }, { category: "Resources", label: "Local resources", delta: "worse", reason: "K8s control plane ~2GB RAM" }] },
      { name: "Podman Compose", icon: "🦭", summary: "Rootless, daemonless containers.", affectedWires: ["w21", "w22", "w23", "w24", "w25"], impacts: [{ category: "Security", label: "Rootless", delta: "better", reason: "No docker.sock attack surface" }, { category: "Compatibility", label: "Drop-in", delta: "neutral", reason: "Largely compatible" }, { category: "GPU", label: "NVIDIA support", delta: "worse", reason: "Less tested GPU support" }, { category: "Ecosystem", label: "Tooling", delta: "worse", reason: "Docker-native tools less polished" }] },
    ],
  },
  {
    id: "terraform", label: "Terraform + AWS", layer: "Infrastructure",
    x: 255, y: 565, w: 170, h: 48, color: "#f97316", icon: "☁️",
    tech: ["Terraform 1.14", "AWS EC2", "g5.xlarge", "A10G"],
    files: ["infra/aws/main.tf", "infra/aws/variables.tf"],
    description: "IaC for AWS g5.xlarge (A10G GPU).",
    details: "Instance: i-003279fa29750d3f2 @ 52.54.209.253, 200GB gp3, SG for 22/8000/3000",
    connections: ["cli", "kubernetes"],
    qa: [],
    alternatives: [
      { name: "Pulumi (TypeScript)", icon: "🟣", summary: "IaC in TypeScript.", affectedWires: ["w5", "w27"], impacts: [{ category: "Language", label: "Real programming", delta: "better", reason: "TypeScript with loops, conditionals" }, { category: "Testing", label: "Unit tests", delta: "better", reason: "Jest/Vitest for infra" }, { category: "State", label: "State management", delta: "neutral", reason: "Both use state files" }, { category: "Ecosystem", label: "Provider coverage", delta: "worse", reason: "Terraform has 3000+ providers" }] },
      { name: "GCP", icon: "🔵", summary: "TPU access + Vertex AI.", affectedWires: ["w5", "w27"], impacts: [{ category: "ML", label: "TPU access", delta: "better", reason: "TPU v4/v5 10x faster for transformers" }, { category: "MLOps", label: "Vertex AI", delta: "better", reason: "Integrated model serving" }, { category: "GPU Pricing", label: "Spot cost", delta: "neutral", reason: "Similar pricing" }, { category: "Ecosystem", label: "Enterprise tooling", delta: "worse", reason: "AWS is #1 cloud" }] },
    ],
  },
  {
    id: "kubernetes", label: "K8s Operator", layer: "Infrastructure",
    x: 460, y: 565, w: 145, h: 48, color: "#f97316", icon: "☸️",
    tech: ["CRD", "Python Operator", "KEDA", "Karpenter"],
    files: ["operator/main.py", "k8s/crd/opendeploy.yaml"],
    description: "Custom K8s operator. CRDs → Deployments, HPAs, KEDA.",
    details: "CRD: opendeploys.opendeploy.dev/v1alpha1\nReconciles: Deployment, Service, HPA, KEDA ScaledObject",
    connections: ["docker_compose", "terraform"],
    qa: [],
    alternatives: [
      { name: "Knative Serving", icon: "🚢", summary: "Serverless scale-to-zero.", affectedWires: ["w26"], impacts: [{ category: "Scale-to-zero", label: "Built-in", delta: "better", reason: "Core feature of Knative" }, { category: "Traffic", label: "Revisions", delta: "better", reason: "Canary + traffic splitting" }, { category: "Complexity", label: "Knative install", delta: "worse", reason: "Needs Istio/Kourier" }, { category: "GPU", label: "GPU scheduling", delta: "worse", reason: "Doesn't understand GPU memory" }] },
    ],
  },
  {
    id: "edge", label: "Edge Pipeline", layer: "Edge",
    x: 50, y: 660, w: 170, h: 48, color: "#ec4899", icon: "📱",
    tech: ["Python", "ONNX", "OTA Sync", "Docker"],
    files: ["scripts/edge/agent.py", "scripts/edge/build.py"],
    description: "Edge deployment: OTA agent, ONNX builds.",
    details: "agent.py (OTA) · build.py (Docker+ONNX) · registry.py · runtime.py · export_resnet18_onnx.py",
    connections: ["models"],
    qa: [],
    alternatives: [],
  },
  {
    id: "triton_vllm", label: "Triton / vLLM", layer: "Edge",
    x: 275, y: 660, w: 170, h: 48, color: "#ec4899", icon: "🚀",
    tech: ["Triton", "vLLM", "ONNX", "TensorRT", "PagedAttention"],
    files: ["docker-compose.triton.yml", "docker-compose.vllm.yml"],
    description: "Production inference: Triton multi-framework, vLLM for LLMs.",
    details: "Triton: dynamic batching, model repo. vLLM: PagedAttention, continuous batching, /v1/completions",
    connections: ["fastapi"],
    qa: [],
    alternatives: [],
  },
];

/* ── Layer bands ─────────────────────────────────────────────── */

interface LayerBand { label: string; yMin: number; yMax: number; color: string; }

const LAYERS: LayerBand[] = [
  { label: "Clients", yMin: 20, yMax: 110, color: "rgba(59,130,246,0.07)" },
  { label: "Frontend", yMin: 120, yMax: 215, color: "rgba(139,92,246,0.07)" },
  { label: "Backend + Data + AI", yMin: 230, yMax: 445, color: "rgba(34,197,94,0.07)" },
  { label: "Real-time + Observability", yMin: 450, yMax: 535, color: "rgba(6,182,212,0.07)" },
  { label: "Infrastructure + Orchestration", yMin: 545, yMax: 630, color: "rgba(249,115,22,0.07)" },
  { label: "Edge + Production Inference", yMin: 640, yMax: 725, color: "rgba(236,72,153,0.07)" },
];

const SVG_W = 660;
const SVG_H = 745;
const PAD = 14;

function findLayerByName(layer: string): LayerBand {
  const words = layer.split(/[^a-zA-Z]+/).filter(Boolean);
  return LAYERS.find((l) => words.some((w) => l.label.includes(w))) || LAYERS[2];
}

function clampPos(x: number, y: number, w: number, h: number, layer: LayerBand) {
  return {
    x: Math.max(PAD, Math.min(SVG_W - w - PAD, x)),
    y: Math.max(layer.yMin + 4, Math.min(layer.yMax - h - 4, y)),
  };
}

/* ── Wire display mode ────────────────────────────────────────── */
type WireDisplayMode = "all" | "hover" | "critical";

/* ── Curved path for cleaner wires ───────────────────────────── */

function curvedPath(x1: number, y1: number, x2: number, y2: number, idx: number, total: number): string {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  // Spread parallel wires further apart
  const spread = total > 1 ? (idx - (total - 1) / 2) * 18 : 0;
  const nx = (-dy / dist) * spread;
  const ny = (dx / dist) * spread;
  // Directional bend: mostly-vertical wires bow horizontally, mostly-horizontal bow vertically
  const angle = Math.atan2(Math.abs(dy), Math.abs(dx));
  const verticalness = angle / (Math.PI / 2); // 0=horizontal, 1=vertical
  const baseBend = Math.min(dist * 0.25, 60);
  // Horizontal offset for vertical wires, vertical offset for horizontal wires
  const hBend = baseBend * verticalness * (idx % 2 === 0 ? 1 : -1) * 0.6;
  const vBend = baseBend * (1 - verticalness) * Math.sign(dy || 1) * 0.4;
  const cx1 = x1 + dx * 0.25 + nx + hBend;
  const cy1 = y1 + dy * 0.25 + ny + vBend;
  const cx2 = x1 + dx * 0.75 + nx + hBend * 0.5;
  const cy2 = y1 + dy * 0.75 + ny + vBend * 0.5;
  return `M${x1 + nx},${y1 + ny} C${cx1},${cy1} ${cx2},${cy2} ${x2 + nx},${y2 + ny}`;
}

function getWireGroupInfo(wire: Wire): { index: number; total: number } {
  const key = [wire.from, wire.to].sort().join("|");
  const group = WIRES.filter((w) => [w.from, w.to].sort().join("|") === key);
  return { index: group.indexOf(wire), total: group.length };
}

/* ── AI description cache ─────────────────────────────────────── */
interface AIDescription { text: string; loading: boolean; }

/* ── Focus layout — auto-arrange selected components ──────── */
function computeFocusLayout(ids: string[], all: ArchComponent[]): Record<string, { x: number; y: number }> {
  const comps = ids.map((id) => all.find((c) => c.id === id)!).filter(Boolean);
  const n = comps.length;
  if (n === 0) return {};
  const CX = 310, CY = 190;
  const out: Record<string, { x: number; y: number }> = {};
  if (n === 1) {
    out[comps[0].id] = { x: CX - comps[0].w / 2, y: CY - comps[0].h / 2 };
  } else if (n === 2) {
    out[comps[0].id] = { x: CX - 200 - comps[0].w / 2, y: CY - comps[0].h / 2 };
    out[comps[1].id] = { x: CX + 200 - comps[1].w / 2, y: CY - comps[1].h / 2 };
  } else if (n === 3) {
    // Inverted triangle for 3: one top, two bottom
    out[comps[0].id] = { x: CX - comps[0].w / 2, y: CY - 120 };
    out[comps[1].id] = { x: CX - 180 - comps[1].w / 2, y: CY + 60 };
    out[comps[2].id] = { x: CX + 180 - comps[2].w / 2, y: CY + 60 };
  } else if (n === 4) {
    // Diamond layout for 4
    out[comps[0].id] = { x: CX - comps[0].w / 2, y: CY - 130 };
    out[comps[1].id] = { x: CX - 210 - comps[1].w / 2, y: CY };
    out[comps[2].id] = { x: CX + 210 - comps[2].w / 2, y: CY };
    out[comps[3].id] = { x: CX - comps[3].w / 2, y: CY + 120 };
  } else {
    // Circle layout with generous radius for 5+
    const r = Math.max(150, n * 28);
    comps.forEach((c, i) => {
      const a = (i / n) * Math.PI * 2 - Math.PI / 2;
      out[c.id] = { x: CX + Math.cos(a) * r - c.w / 2, y: CY + Math.sin(a) * r - c.h / 2 };
    });
  }
  return out;
}

/* ════════════════════════════════════════════════════════════════
   Component
   ════════════════════════════════════════════════════════════════ */

export default function ArchitecturePage() {
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [selected, setSelected] = useState<ArchComponent | null>(null);
  const [selectedWire, setSelectedWire] = useState<Wire | null>(null);
  const [hoveredComp, setHoveredComp] = useState<string | null>(null);
  const [hoveredWire, setHoveredWire] = useState<string | null>(null);
  const [qaOpen, setQaOpen] = useState<number | null>(null);
  const [activeSwap, setActiveSwap] = useState<Alternative | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const [dragStart, setDragStart] = useState<{ mx: number; my: number; cx: number; cy: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  /* ── Selection / Focus state ────────────────────────────────── */
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedComponents, setSelectedComponents] = useState<Set<string>>(new Set());
  const [focusView, setFocusView] = useState(false);
  const [aiDescriptions, setAiDescriptions] = useState<Record<string, AIDescription>>({});
  const [wireMode, setWireMode] = useState<WireDisplayMode>("all");

  const components = useMemo(() =>
    DEFAULT_COMPONENTS.map((c) => { const p = positions[c.id]; return p ? { ...c, x: p.x, y: p.y } : c; }),
  [positions]);

  const getComp = useCallback((id: string) => components.find((c) => c.id === id), [components]);

  function getCenter(id: string, overrides?: Record<string, { x: number; y: number }>) {
    const c = DEFAULT_COMPONENTS.find((cc) => cc.id === id);
    if (!c) return { x: 0, y: 0 };
    const p = overrides?.[id] ?? positions[id];
    const x = p ? p.x : c.x;
    const y = p ? p.y : c.y;
    return { x: x + c.w / 2, y: y + c.h / 2 };
  }

  const connectedWireIds = useMemo(() => {
    if (!hoveredComp) return new Set<string>();
    return new Set(WIRES.filter((w) => w.from === hoveredComp || w.to === hoveredComp).map((w) => w.id));
  }, [hoveredComp]);

  const connectedCompIds = useMemo(() => {
    if (!hoveredComp) return new Set<string>();
    const s = new Set<string>();
    WIRES.forEach((w) => { if (w.from === hoveredComp) s.add(w.to); if (w.to === hoveredComp) s.add(w.from); });
    s.add(hoveredComp);
    return s;
  }, [hoveredComp]);

  const swapAffectedWires = useMemo(() =>
    activeSwap ? new Set(activeSwap.affectedWires) : new Set<string>(),
  [activeSwap]);

  const reachableComponents = useMemo(() => {
    if (!selectionMode) return new Set<string>();
    const r = new Set<string>();
    for (const c of DEFAULT_COMPONENTS) {
      if (!selectedComponents.has(c.id) && isReachableFromSet(c.id, selectedComponents)) r.add(c.id);
    }
    return r;
  }, [selectionMode, selectedComponents]);

  const focusWires = useMemo(() => getWiresBetween(selectedComponents), [selectedComponents]);
  const focusPositions = useMemo(() => computeFocusLayout(Array.from(selectedComponents), DEFAULT_COMPONENTS), [selectedComponents]);

  useEffect(() => { if ((selected || selectedWire) && panelRef.current) panelRef.current.scrollTop = 0; }, [selected, selectedWire]);

  const selectComponent = useCallback((c: ArchComponent) => { setSelected(c); setSelectedWire(null); setQaOpen(null); setActiveSwap(null); }, []);
  const selectWire = useCallback((w: Wire) => { setSelectedWire(w); setSelected(null); setQaOpen(null); setActiveSwap(null); }, []);

  /* ── Selection toggles ─────────────────────────────────────── */
  const toggleSelectionMode = useCallback(() => {
    setSelectionMode((p) => { if (p) { setSelectedComponents(new Set()); setFocusView(false); setAiDescriptions({}); } return !p; });
    setSelected(null); setSelectedWire(null);
  }, []);

  const toggleComponentSelection = useCallback((id: string) => {
    setSelectedComponents((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (prev.size === 0 || isReachableFromSet(id, prev)) next.add(id);
      return next;
    });
    setAiDescriptions({});
    setFocusView(false);
  }, []);

  const enterFocusView = useCallback(() => {
    if (selectedComponents.size < 2) return;
    const wires = getWiresBetween(selectedComponents);
    if (wires.length === 0) return;
    setFocusView(true); setSelected(null); setSelectedWire(null);

    wires.forEach((wire) => {
      const from = DEFAULT_COMPONENTS.find((c) => c.id === wire.from);
      const to = DEFAULT_COMPONENTS.find((c) => c.id === wire.to);
      if (!from || !to) return;
      setAiDescriptions((p) => ({ ...p, [wire.id]: { text: "", loading: true } }));
      const term = `${from.label} → ${to.label} connection`;
      const context = `In the OpenDeploy system architecture, explain how "${from.label}" (${from.description}) interacts with "${to.label}" (${to.description}) via ${wire.protocol}. Wire: ${wire.label}. Data flow: ${wire.dataFlow}. Explain in 2-3 sentences what this connection does, why it exists, and what would break if it was severed.`;
      fetchGlossaryDescription(term, context)
        .then((r) => setAiDescriptions((p) => ({ ...p, [wire.id]: { text: r.detail || r.short || "Connection established.", loading: false } })))
        .catch(() => setAiDescriptions((p) => ({ ...p, [wire.id]: { text: `${from.label} communicates with ${to.label} via ${wire.protocol}. ${wire.dataFlow}`, loading: false } })));
    });
  }, [selectedComponents]);

  const exitFocusView = useCallback(() => { setFocusView(false); setAiDescriptions({}); }, []);

  /* ── SVG helpers ────────────────────────────────────────────── */
  function svgPoint(cx: number, cy: number) {
    const svg = svgRef.current; if (!svg) return { x: 0, y: 0 };
    const pt = svg.createSVGPoint(); pt.x = cx; pt.y = cy;
    const ctm = svg.getScreenCTM(); if (!ctm) return { x: 0, y: 0 };
    const s = pt.matrixTransform(ctm.inverse());
    return { x: s.x, y: s.y };
  }

  const handlePointerDown = useCallback((e: React.PointerEvent, comp: ArchComponent) => {
    if (selectionMode) return;
    e.stopPropagation(); e.preventDefault();
    (e.target as SVGElement).setPointerCapture(e.pointerId);
    const sp = svgPoint(e.clientX, e.clientY);
    setDragging(comp.id); setDragStart({ mx: sp.x, my: sp.y, cx: comp.x, cy: comp.y });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectionMode]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging || !dragStart) return;
    const sp = svgPoint(e.clientX, e.clientY);
    const def = DEFAULT_COMPONENTS.find((c) => c.id === dragging)!;
    const layer = findLayerByName(def.layer);
    const clamped = clampPos(dragStart.cx + sp.x - dragStart.mx, dragStart.cy + sp.y - dragStart.my, def.w, def.h, layer);
    setPositions((p) => ({ ...p, [dragging]: clamped }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dragging, dragStart]);

  const handlePointerUp = useCallback(() => { setDragging(null); setDragStart(null); }, []);

  const handleDoubleClick = useCallback((comp: ArchComponent) => {
    if (selectionMode) return;
    setPositions((p) => { const n = { ...p }; delete n[comp.id]; return n; });
  }, [selectionMode]);

  /* ── Glass CSS ─────────────────────────────────────────────── */
  const glassCard = "bg-white/[0.04] backdrop-blur-2xl border border-white/[0.08] shadow-[0_8px_32px_rgba(0,0,0,0.25)]";
  const glassCardHover = "hover:bg-white/[0.07] hover:border-white/[0.14]";
  const glassPanel = "bg-white/[0.03] backdrop-blur-3xl border border-white/[0.06] shadow-[0_12px_48px_rgba(0,0,0,0.35)]";

  /* ═══════════════════════════════════════════════════════════════
     FOCUS VIEW
     ═══════════════════════════════════════════════════════════════ */

  if (focusView && selectedComponents.size >= 2) {
    const focusComps = Array.from(selectedComponents).map((id) => DEFAULT_COMPONENTS.find((c) => c.id === id)!).filter(Boolean);

    return (
      <div className="flex flex-col xl:flex-row gap-6 pb-12">
        <div className="flex-1 min-w-0">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400 bg-clip-text text-transparent">
                🔎 Focus View
              </h1>
              <p className="text-sm text-muted-foreground/70">
                {focusComps.length} components isolated · {focusWires.length} connections · AI-described relationships
              </p>
            </div>
            <button onClick={exitFocusView}
              className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all ${glassCard} ${glassCardHover} text-blue-300`}>
              ← Back to Full View
            </button>
          </div>

          <div className={`rounded-2xl overflow-hidden ${glassCard}`}>
            <svg viewBox="0 0 620 400" className="w-full select-none" style={{ minHeight: 360 }}>
              <defs>
                <filter id="fg-blue" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur stdDeviation="4" result="b" /><feFlood floodColor="#3b82f6" floodOpacity="0.5" /><feComposite in2="b" operator="in" /><feMerge><feMergeNode /><feMergeNode in="SourceGraphic" /></feMerge>
                </filter>
                <filter id="fg-red" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur stdDeviation="4" result="b" /><feFlood floodColor="#ef4444" floodOpacity="0.6" /><feComposite in2="b" operator="in" /><feMerge><feMergeNode /><feMergeNode in="SourceGraphic" /></feMerge>
                </filter>
                <filter id="fg-shadow" x="-10%" y="-10%" width="120%" height="130%">
                  <feDropShadow dx="0" dy="3" stdDeviation="6" floodColor="#000" floodOpacity="0.4" />
                </filter>
                <marker id="fa" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#60a5fa" /></marker>
                <marker id="fac" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#f87171" /></marker>
                <linearGradient id="fgf" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="rgba(255,255,255,0.1)" /><stop offset="100%" stopColor="rgba(255,255,255,0.03)" /></linearGradient>
                <style>{`@keyframes fd{to{stroke-dashoffset:-20}}.fw-anim{animation:fd 1.5s linear infinite}`}</style>
              </defs>
              <rect x="0" y="0" width="620" height="400" rx="16" fill="rgba(15,23,42,0.3)" />

              {focusWires.map((wire) => {
                const fc = focusComps.find((c) => c.id === wire.from), tc = focusComps.find((c) => c.id === wire.to);
                const fp = focusPositions[wire.from], tp = focusPositions[wire.to];
                if (!fc || !tc || !fp || !tp) return null;
                const x1 = fp.x + fc.w / 2, y1 = fp.y + fc.h / 2, x2 = tp.x + tc.w / 2, y2 = tp.y + tc.h / 2;
                const { index, total } = getWireGroupInfo(wire);
                const d = curvedPath(x1, y1, x2, y2, index, total);
                const col = wire.critical ? "#f87171" : "#60a5fa";
                const mx = (x1 + x2) / 2, my = (y1 + y2) / 2 - 14;
                return (
                  <g key={wire.id} className="cursor-pointer" onClick={() => selectWire(wire)}>
                    <path d={d} fill="none" stroke={col} strokeWidth={8} opacity={0.08} strokeLinecap="round" />
                    <path d={d} fill="none" stroke={col} strokeWidth={2.5} strokeLinecap="round"
                      markerEnd={wire.critical ? "url(#fac)" : "url(#fa)"}
                      filter={wire.critical ? "url(#fg-red)" : "url(#fg-blue)"}
                      strokeDasharray="6 4" className="fw-anim" />
                    <g><rect x={mx - 52} y={my - 10} width={104} height={20} rx={10} fill="rgba(0,0,0,0.75)" stroke={col} strokeWidth={0.8} />
                    <text x={mx} y={my + 3.5} textAnchor="middle" fontSize={8} fontWeight={600} fill="#e2e8f0">{wire.label}</text></g>
                    <g><rect x={mx - 30} y={my + 14} width={60} height={14} rx={7} fill="rgba(0,0,0,0.5)" stroke="rgba(255,255,255,0.1)" strokeWidth={0.5} />
                    <text x={mx} y={my + 23} textAnchor="middle" fontSize={6.5} fontWeight={500} fill="rgba(148,163,184,0.8)">{wire.protocol}</text></g>
                  </g>
                );
              })}

              {focusComps.map((comp) => {
                const pos = focusPositions[comp.id]; if (!pos) return null;
                return (
                  <g key={comp.id} filter="url(#fg-shadow)" className="cursor-pointer" onClick={() => selectComponent(comp)}>
                    <rect x={pos.x - 3} y={pos.y - 3} width={comp.w + 6} height={comp.h + 6} rx={15} fill="none" stroke={comp.color} strokeWidth={1} opacity={0.25} />
                    <rect x={pos.x} y={pos.y} width={comp.w} height={comp.h} rx={12} fill="url(#fgf)" stroke={comp.color + "66"} strokeWidth={1.5} />
                    <rect x={pos.x} y={pos.y} width={4} height={comp.h} rx={2} fill={comp.color} opacity={0.8} />
                    <text x={pos.x + 16} y={pos.y + comp.h / 2 + 1} fontSize={16} dominantBaseline="middle" style={{ filter: `drop-shadow(0 0 6px ${comp.color}55)` }}>{comp.icon}</text>
                    <text x={pos.x + 38} y={pos.y + comp.h / 2 - 5} fontSize={11} fontWeight={700} fill={comp.color} dominantBaseline="middle">{comp.label}</text>
                    <text x={pos.x + 38} y={pos.y + comp.h / 2 + 10} fontSize={7.5} fill="rgba(148,163,184,0.7)" dominantBaseline="middle">{comp.tech.slice(0, 3).join(" · ")}</text>
                  </g>
                );
              })}
            </svg>
          </div>

          {/* AI Relationship Descriptions */}
          <div className="mt-4 space-y-3">
            <h3 className="text-sm font-semibold text-muted-foreground/70 flex items-center gap-2">
              <span className="text-base">✦</span> AI-Described Relationships
            </h3>
            {focusWires.map((wire) => {
              const fc = getComp(wire.from), tc = getComp(wire.to), ai = aiDescriptions[wire.id];
              return (
                <div key={wire.id} className={`rounded-xl p-4 ${glassCard} transition-all duration-300`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm">{fc?.icon}</span>
                    <span className="text-xs font-bold" style={{ color: fc?.color }}>{fc?.label}</span>
                    <span className="text-muted-foreground/40 text-xs">→</span>
                    <span className="text-sm">{tc?.icon}</span>
                    <span className="text-xs font-bold" style={{ color: tc?.color }}>{tc?.label}</span>
                    {wire.critical && <Badge variant="destructive" className="text-[8px] ml-auto">CRITICAL</Badge>}
                    {wire.port && <span className="text-[9px] font-mono text-purple-400/60 ml-auto">{wire.port}</span>}
                  </div>
                  <div className="flex items-center gap-2 mb-2">
                    <Badge className="text-[9px] border-0 bg-blue-500/10 text-blue-300">{wire.protocol}</Badge>
                    <span className="text-[10px] text-muted-foreground/50 font-medium">{wire.label}</span>
                  </div>
                  <div className="mt-2 text-[11px] leading-relaxed">
                    {ai?.loading ? (
                      <div className="flex items-center gap-2 text-muted-foreground/40">
                        <span className="inline-block w-3 h-3 border-2 border-blue-400/40 border-t-blue-400 rounded-full animate-spin" />
                        Generating AI description…
                      </div>
                    ) : ai?.text ? (
                      <p className="text-muted-foreground/70">{ai.text}</p>
                    ) : (
                      <p className="text-muted-foreground/40 italic">{wire.dataFlow}</p>
                    )}
                  </div>
                </div>
              );
            })}
            {focusWires.length === 0 && (
              <p className="text-sm text-muted-foreground/40 text-center py-4">No direct connections between these components.</p>
            )}
          </div>
        </div>

        {/* RIGHT panel in focus view */}
        <div ref={panelRef} className={`xl:w-[430px] xl:max-h-[calc(100vh-6rem)] xl:overflow-y-auto rounded-2xl ${glassPanel}`}>
          {selectedWire && (
            <div className="p-5 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold flex items-center gap-2 text-blue-300">🔗 {selectedWire.label}
                    {selectedWire.critical && <Badge variant="destructive" className="text-[9px]">CRITICAL</Badge>}
                  </h2>
                  <p className="text-xs text-muted-foreground/60 mt-1">{getComp(selectedWire.from)?.label} → {getComp(selectedWire.to)?.label}</p>
                </div>
                <button onClick={() => setSelectedWire(null)} className="text-muted-foreground/40 hover:text-white/80 text-lg transition-colors">✕</button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className={`rounded-xl p-3 ${glassCard}`}><span className="text-muted-foreground/50 block text-[10px] font-medium uppercase tracking-wider">Protocol</span><span className="font-bold text-blue-300">{selectedWire.protocol}</span></div>
                {selectedWire.port && <div className={`rounded-xl p-3 ${glassCard}`}><span className="text-muted-foreground/50 block text-[10px] font-medium uppercase tracking-wider">Port</span><span className="font-mono font-bold text-purple-300">{selectedWire.port}</span></div>}
              </div>
              <div><h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">Data Flow</h3><p className={`text-[11px] leading-relaxed font-mono p-3 rounded-xl ${glassCard}`}>{selectedWire.dataFlow}</p></div>
            </div>
          )}
          {selected && (
            <div className="p-5 space-y-5">
              <div className="flex items-start justify-between gap-3">
                <div><div className="flex items-center gap-2.5 mb-1.5"><span className="text-2xl" style={{ filter: `drop-shadow(0 0 8px ${selected.color}55)` }}>{selected.icon}</span><h2 className="text-lg font-bold" style={{ color: selected.color }}>{selected.label}</h2></div>
                <Badge className="text-[10px] font-semibold uppercase tracking-wider border-0" style={{ background: selected.color + "18", color: selected.color }}>{selected.layer}</Badge></div>
                <button onClick={() => setSelected(null)} className="text-muted-foreground/40 hover:text-white/80 text-lg transition-colors">✕</button>
              </div>
              <p className="text-sm text-muted-foreground/70 leading-relaxed">{selected.description}</p>
              <div><h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">Technologies</h3><div className="flex flex-wrap gap-1.5">{selected.tech.map((t) => <span key={t} className="text-[11px] px-2.5 py-0.5 rounded-full bg-white/[0.06] border border-white/[0.08] font-medium">{t}</span>)}</div></div>
              <div><h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">Key Files</h3><div className="space-y-0.5">{selected.files.map((f) => <div key={f} className="text-[11px] font-mono text-muted-foreground/50">📄 {f}</div>)}</div></div>
              <div><h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">Details</h3><div className={`text-[11px] leading-relaxed whitespace-pre-line font-mono p-3 rounded-xl ${glassCard}`}>{selected.details}</div></div>
            </div>
          )}
          {!selected && !selectedWire && (
            <div className="p-8 text-center space-y-4">
              <div className="text-5xl" style={{ filter: "drop-shadow(0 0 16px rgba(96,165,250,0.3))" }}>🔎</div>
              <h2 className="text-lg font-bold bg-gradient-to-r from-cyan-300 to-blue-300 bg-clip-text text-transparent">Focus View Active</h2>
              <p className="text-sm text-muted-foreground/50 leading-relaxed max-w-xs mx-auto">Click any component or wire in the diagram to see details here.</p>
              <div className="text-xs text-muted-foreground/40 space-y-1.5 pt-4 text-left max-w-xs mx-auto">
                <p>🧩 <strong className="text-muted-foreground/60">{focusComps.length} components</strong> isolated</p>
                <p>🔗 <strong className="text-muted-foreground/60">{focusWires.length} connections</strong> between them</p>
                <p>✦ <strong className="text-muted-foreground/60">AI descriptions</strong> generated below the diagram</p>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  /* ═══════════════════════════════════════════════════════════════
     MAIN VIEW
     ═══════════════════════════════════════════════════════════════ */
  return (
    <div className="flex flex-col xl:flex-row gap-6 pb-12">
      <div className="flex-1 min-w-0">
        <div className="mb-4 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-blue-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">System Architecture</h1>
              <p className="text-sm text-muted-foreground/70">
                {selectionMode
                  ? `Select components to isolate · ${selectedComponents.size} selected · Only connected components can be added`
                  : "Drag components · Click wires · Hover to trace · Double-click to reset · ⇄ Swap frameworks"}
              </p>
            </div>
            <div className="flex gap-2 shrink-0">
              {selectionMode && selectedComponents.size >= 2 && (
                <button onClick={enterFocusView} disabled={focusWires.length === 0}
                  className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all duration-300 ${focusWires.length > 0
                    ? "bg-gradient-to-r from-cyan-500/20 to-blue-500/20 border border-cyan-500/30 text-cyan-300 hover:from-cyan-500/30 hover:to-blue-500/30 shadow-[0_0_20px_rgba(6,182,212,0.15)]"
                    : "bg-white/[0.03] border border-white/[0.06] text-muted-foreground/30 cursor-not-allowed"}`}>
                  🔎 Focus View ({focusWires.length})
                </button>
              )}
              <button onClick={toggleSelectionMode}
                className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all duration-300 ${selectionMode
                  ? "bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 shadow-[0_0_16px_rgba(6,182,212,0.2)]"
                  : `${glassCard} ${glassCardHover} text-muted-foreground/70`}`}>
                {selectionMode ? "✕ Cancel" : "🧩 Select & Focus"}
              </button>
            </div>
          </div>
          {/* Wire visibility controls */}
          {!selectionMode && (
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-muted-foreground/40 uppercase tracking-wider font-semibold mr-1">Wires:</span>
              {(["all", "hover", "critical"] as WireDisplayMode[]).map((mode) => (
                <button key={mode} onClick={() => setWireMode(mode)}
                  className={`px-3 py-1 rounded-lg text-[11px] font-medium transition-all duration-200 ${
                    wireMode === mode
                      ? "bg-blue-500/15 border border-blue-500/30 text-blue-300 shadow-[0_0_10px_rgba(59,130,246,0.1)]"
                      : `${glassCard} text-muted-foreground/50 hover:text-muted-foreground/70 hover:bg-white/[0.06]`
                  }`}>
                  {mode === "all" ? "📊 All" : mode === "hover" ? "👆 On Hover" : "⚠️ Critical Only"}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Selected chips bar */}
        {selectionMode && selectedComponents.size > 0 && (
          <div className={`rounded-xl p-3 mb-3 ${glassCard} flex flex-wrap items-center gap-2`}>
            <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider font-semibold shrink-0">Selected:</span>
            {Array.from(selectedComponents).map((id) => {
              const comp = getComp(id); if (!comp) return null;
              return (
                <button key={id} onClick={() => toggleComponentSelection(id)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all duration-200"
                  style={{ background: comp.color + "18", color: comp.color, border: `1px solid ${comp.color}33` }}>
                  {comp.icon} {comp.label} <span className="text-[9px] opacity-60 ml-0.5">✕</span>
                </button>
              );
            })}
          </div>
        )}

        {/* SVG Diagram */}
        <div className={`rounded-2xl overflow-auto ${glassCard}`}>
          <svg ref={svgRef} viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="w-full select-none"
            style={{ minHeight: 480, cursor: dragging ? "grabbing" : selectionMode ? "crosshair" : "default" }}
            onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerLeave={handlePointerUp}>
            <defs>
              <filter id="glow-blue" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="b" /><feFlood floodColor="#3b82f6" floodOpacity="0.6" /><feComposite in2="b" operator="in" /><feMerge><feMergeNode /><feMergeNode in="SourceGraphic" /></feMerge></filter>
              <filter id="glow-red" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3.5" result="b" /><feFlood floodColor="#ef4444" floodOpacity="0.7" /><feComposite in2="b" operator="in" /><feMerge><feMergeNode /><feMergeNode in="SourceGraphic" /></feMerge></filter>
              <filter id="glow-amber" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3.5" result="b" /><feFlood floodColor="#f59e0b" floodOpacity="0.7" /><feComposite in2="b" operator="in" /><feMerge><feMergeNode /><feMergeNode in="SourceGraphic" /></feMerge></filter>
              <filter id="glow-cyan" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="b" /><feFlood floodColor="#06b6d4" floodOpacity="0.6" /><feComposite in2="b" operator="in" /><feMerge><feMergeNode /><feMergeNode in="SourceGraphic" /></feMerge></filter>
              <filter id="card-shadow" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="2" stdDeviation="4" floodColor="#000" floodOpacity="0.3" /></filter>
              <filter id="card-shadow-hover" x="-10%" y="-10%" width="120%" height="140%"><feDropShadow dx="0" dy="4" stdDeviation="8" floodColor="#000" floodOpacity="0.45" /></filter>
              <marker id="arr" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="rgba(148,163,184,0.3)" /></marker>
              <marker id="arr-hi" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#60a5fa" /></marker>
              <marker id="arr-crit" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#f87171" /></marker>
              <marker id="arr-swap" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#fbbf24" /></marker>
              <marker id="arr-sel" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#22d3ee" /></marker>
              <linearGradient id="glass-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="rgba(255,255,255,0.08)" /><stop offset="100%" stopColor="rgba(255,255,255,0.02)" /></linearGradient>
            </defs>

            {/* Layer bands */}
            {LAYERS.map((l) => (
              <g key={l.label}>
                <rect x={PAD} y={l.yMin} width={SVG_W - PAD * 2} height={l.yMax - l.yMin} rx={12} fill={l.color} stroke="rgba(255,255,255,0.04)" strokeWidth={1} />
                <text x={PAD + 10} y={l.yMin + 14} fontSize={8} fontWeight={700} letterSpacing={1.2} fill="currentColor" className="fill-muted-foreground" opacity={0.3}>{l.label.toUpperCase()}</text>
              </g>
            ))}

            {/* Wires — curved with visibility modes */}
            {WIRES.map((wire) => {
              const from = getCenter(wire.from), to = getCenter(wire.to);
              const isHovered = hoveredWire === wire.id || connectedWireIds.has(wire.id);
              const isSwapAffected = swapAffectedWires.has(wire.id);
              const isWireSelected = selectedWire?.id === wire.id;
              const active = isHovered || isWireSelected || isSwapAffected;
              const isSelWire = selectionMode && selectedComponents.has(wire.from) && selectedComponents.has(wire.to);

              // Wire display mode filtering
              const modeVisible = selectionMode ? true
                : wireMode === "all" ? true
                : wireMode === "critical" ? (wire.critical || active)
                : wireMode === "hover" ? active : true;

              const dimmed = selectionMode
                ? !isSelWire && !active
                : !modeVisible
                  ? true
                  : (hoveredComp && !connectedWireIds.has(wire.id)) || (!!(activeSwap) && !swapAffectedWires.has(wire.id));

              const color = isSelWire ? "#22d3ee"
                : isSwapAffected ? "#fbbf24"
                : (isWireSelected || isHovered) ? (wire.critical ? "#f87171" : "#60a5fa")
                : wire.critical ? "rgba(239,68,68,0.18)"
                : "rgba(148,163,184,0.08)";
              // Default wires are ultra-thin; only emphasize on interaction
              const sw = isSelWire ? 2.5 : active ? 2.5 : wire.critical ? 1 : 0.5;
              const opacity = dimmed ? (wireMode === "hover" && !active ? 0.02 : 0.04) : 1;
              const filter = isSelWire ? "url(#glow-cyan)" : active ? (isSwapAffected ? "url(#glow-amber)" : wire.critical ? "url(#glow-red)" : "url(#glow-blue)") : undefined;
              const marker = isSelWire ? "url(#arr-sel)" : isSwapAffected ? "url(#arr-swap)" : active ? (wire.critical ? "url(#arr-crit)" : "url(#arr-hi)") : "url(#arr)";

              const { index, total } = getWireGroupInfo(wire);
              const d = curvedPath(from.x, from.y, to.x, to.y, index, total);
              const mx = (from.x + to.x) / 2, my = (from.y + to.y) / 2;

              return (
                <g key={wire.id} opacity={opacity} style={{ transition: "opacity 0.3s ease" }}
                  onMouseEnter={() => !selectionMode && setHoveredWire(wire.id)} onMouseLeave={() => !selectionMode && setHoveredWire(null)}
                  onClick={(e) => { if (!selectionMode) { e.stopPropagation(); selectWire(wire); } }}
                  className={selectionMode ? "" : "cursor-pointer"}>
                  {/* Wide invisible hit target */}
                  <path d={d} fill="none" stroke="transparent" strokeWidth={18} />
                  {/* Soft glow behind active wires */}
                  {(active || isSelWire) && <path d={d} fill="none" stroke={color} strokeWidth={8} opacity={0.08} strokeLinecap="round" />}
                  {/* Main wire stroke */}
                  <path d={d} fill="none" stroke={color} strokeWidth={sw} strokeLinecap="round"
                    strokeDasharray={active || isSelWire || wire.critical ? undefined : "3 8"} markerEnd={marker} filter={filter}
                    style={{ transition: "all 0.35s ease" }} />
                  {/* Label pill — only on interaction */}
                  {(active || isSelWire) && (
                    <g style={{ transition: "opacity 0.2s ease" }}>
                      <rect x={mx - 48} y={my - 11} width={96} height={22} rx={11} fill="rgba(0,0,0,0.8)" stroke={color} strokeWidth={0.6} />
                      <text x={mx} y={my + 3} textAnchor="middle" fontSize={7.5} fontWeight={600} fill={isSelWire ? "#22d3ee" : isSwapAffected ? "#fbbf24" : "#e2e8f0"}>{wire.label}</text>
                    </g>
                  )}
                </g>
              );
            })}

            {/* Component cards */}
            {components.map((comp) => {
              const isDetailSel = selected?.id === comp.id;
              const isHov = hoveredComp === comp.id;
              const isLinked = connectedCompIds.has(comp.id);
              const isDrag = dragging === comp.id;
              const isChecked = selectedComponents.has(comp.id);
              const canSel = selectionMode && (isChecked || reachableComponents.has(comp.id) || selectedComponents.size === 0);
              const dimmed = selectionMode ? !isChecked && !canSel : hoveredComp && !isHov && !isLinked;
              const borderColor = selectionMode && isChecked ? "#22d3ee" : isDetailSel ? comp.color : isHov ? comp.color + "88" : "rgba(255,255,255,0.08)";
              const bw = selectionMode && isChecked ? 2.5 : isDetailSel ? 2 : isHov ? 1.5 : 0.8;

              return (
                <g key={comp.id}
                  style={{ cursor: selectionMode ? (canSel ? "pointer" : "not-allowed") : isDrag ? "grabbing" : "grab", opacity: dimmed ? 0.15 : 1, transition: isDrag ? "none" : "opacity 0.25s ease" }}
                  onPointerDown={(e) => handlePointerDown(e, comp)} onDoubleClick={() => handleDoubleClick(comp)}
                  onMouseEnter={() => { if (!dragging && !selectionMode) setHoveredComp(comp.id); }}
                  onMouseLeave={() => { if (!dragging && !selectionMode) setHoveredComp(null); }}
                  onClick={() => { if (selectionMode) { if (canSel) toggleComponentSelection(comp.id); } else if (!dragging) selectComponent(comp); }}
                  filter={isDrag ? "url(#card-shadow-hover)" : "url(#card-shadow)"}>
                  {selectionMode && isChecked && (
                    <rect x={comp.x - 3} y={comp.y - 3} width={comp.w + 6} height={comp.h + 6} rx={15} fill="none" stroke="#22d3ee" strokeWidth={1.5} opacity={0.4} style={{ filter: "url(#glow-cyan)" }} />
                  )}
                  <rect x={comp.x} y={comp.y} width={comp.w} height={comp.h} rx={12} fill="url(#glass-fill)" stroke={borderColor} strokeWidth={bw} style={{ transition: isDrag ? "none" : "all 0.25s ease" }} />
                  <rect x={comp.x} y={comp.y} width={3.5} height={comp.h} rx={2} fill={isChecked ? "#22d3ee" : comp.color} opacity={isDetailSel || isHov || isChecked ? 0.9 : 0.4} />
                  <text x={comp.x + 14} y={comp.y + comp.h / 2 + 1} fontSize={14} dominantBaseline="middle" style={{ filter: isHov || isChecked ? "drop-shadow(0 0 4px rgba(255,255,255,0.3))" : undefined }}>{comp.icon}</text>
                  <text x={comp.x + 32} y={comp.y + comp.h / 2 - 5} fontSize={10.5} fontWeight={700} fill={isChecked ? "#22d3ee" : isDetailSel ? comp.color : "#e2e8f0"} dominantBaseline="middle">{comp.label}</text>
                  <text x={comp.x + 32} y={comp.y + comp.h / 2 + 9} fontSize={7.5} fill="rgba(148,163,184,0.7)" dominantBaseline="middle">{comp.tech.slice(0, 3).join(" · ")}</text>
                  {selectionMode ? (canSel ? (
                    <g>
                      <rect x={comp.x + comp.w - 20} y={comp.y + 6} width={14} height={14} rx={4} fill={isChecked ? "#22d3ee" : "rgba(255,255,255,0.06)"} stroke={isChecked ? "#22d3ee" : "rgba(255,255,255,0.2)"} strokeWidth={1} />
                      {isChecked && <text x={comp.x + comp.w - 13} y={comp.y + 17} textAnchor="middle" fontSize={10} fill="#0f172a" fontWeight={700}>✓</text>}
                    </g>
                  ) : null) : comp.alternatives.length > 0 ? (
                    <g><circle cx={comp.x + comp.w - 12} cy={comp.y + 12} r={7} fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.15)" strokeWidth={0.6} />
                    <text x={comp.x + comp.w - 12} y={comp.y + 14.5} textAnchor="middle" fontSize={8} fill="rgba(255,255,255,0.5)">⇄</text></g>
                  ) : null}
                </g>
              );
            })}
          </svg>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 mt-3 text-[10px] text-muted-foreground/60 flex-wrap">
          <span>{WIRES.length} connections</span>
          <span>{components.length} components</span>
          <span className="flex items-center gap-1"><span className="inline-block w-5 h-[2px] rounded bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.6)]" />Critical</span>
          <span className="flex items-center gap-1"><span className="inline-block w-5 h-[2px] rounded bg-blue-400 shadow-[0_0_6px_rgba(96,165,250,0.6)]" />Active</span>
          {selectionMode && <span className="flex items-center gap-1"><span className="inline-block w-5 h-[2px] rounded bg-cyan-400 shadow-[0_0_6px_rgba(34,211,238,0.6)]" />Selected</span>}
          {!selectionMode && <span className="text-muted-foreground/40">·</span>}
          {!selectionMode && <span className="text-muted-foreground/40">Mode: {wireMode === "all" ? "All wires" : wireMode === "hover" ? "Hover only" : "Critical only"}</span>}
        </div>
      </div>

      {/* ══════════ RIGHT PANEL ══════════ */}
      <div ref={panelRef} className={`xl:w-[430px] xl:max-h-[calc(100vh-6rem)] xl:overflow-y-auto rounded-2xl ${glassPanel}`}>

        {/* Wire detail */}
        {selectedWire && !selectionMode && (
          <div className="p-5 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold flex items-center gap-2 text-blue-300">🔗 {selectedWire.label}
                  {selectedWire.critical && <Badge variant="destructive" className="text-[9px]">CRITICAL</Badge>}
                </h2>
                <p className="text-xs text-muted-foreground/60 mt-1">{getComp(selectedWire.from)?.label} → {getComp(selectedWire.to)?.label}</p>
              </div>
              <button onClick={() => setSelectedWire(null)} className="text-muted-foreground/40 hover:text-white/80 text-lg transition-colors">✕</button>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className={`rounded-xl p-3 ${glassCard}`}><span className="text-muted-foreground/50 block text-[10px] font-medium uppercase tracking-wider">Protocol</span><span className="font-bold text-blue-300">{selectedWire.protocol}</span></div>
              {selectedWire.port && <div className={`rounded-xl p-3 ${glassCard}`}><span className="text-muted-foreground/50 block text-[10px] font-medium uppercase tracking-wider">Port</span><span className="font-mono font-bold text-purple-300">{selectedWire.port}</span></div>}
            </div>
            <div><h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">Data Flow</h3><p className={`text-[11px] leading-relaxed font-mono p-3 rounded-xl ${glassCard}`}>{selectedWire.dataFlow}</p></div>
            <div className="flex gap-2">
              {[selectedWire.from, selectedWire.to].map((cid) => { const c = getComp(cid); return c ? (
                <button key={cid} onClick={() => selectComponent(c)} className={`text-xs px-3 py-1.5 rounded-xl flex items-center gap-1.5 transition-all duration-200 ${glassCard} ${glassCardHover}`}>{c.icon} {c.label}</button>
              ) : null; })}
            </div>
          </div>
        )}

        {/* Component detail */}
        {selected && !selectionMode && (
          <div className="p-5 space-y-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2.5 mb-1.5"><span className="text-2xl" style={{ filter: `drop-shadow(0 0 8px ${selected.color}55)` }}>{selected.icon}</span><h2 className="text-lg font-bold" style={{ color: selected.color }}>{selected.label}</h2></div>
                <Badge className="text-[10px] font-semibold uppercase tracking-wider border-0" style={{ background: selected.color + "18", color: selected.color }}>{selected.layer}</Badge>
              </div>
              <button onClick={() => setSelected(null)} className="text-muted-foreground/40 hover:text-white/80 text-lg transition-colors">✕</button>
            </div>
            <p className="text-sm text-muted-foreground/70 leading-relaxed">{selected.description}</p>
            <div><h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">Technologies</h3><div className="flex flex-wrap gap-1.5">{selected.tech.map((t) => <span key={t} className="text-[11px] px-2.5 py-0.5 rounded-full bg-white/[0.06] border border-white/[0.08] font-medium">{t}</span>)}</div></div>
            <div><h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">Key Files</h3><div className="space-y-0.5">{selected.files.map((f) => <div key={f} className="text-[11px] font-mono text-muted-foreground/50">📄 {f}</div>)}</div></div>
            <div><h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">Details</h3><div className={`text-[11px] leading-relaxed whitespace-pre-line font-mono p-3 rounded-xl ${glassCard}`}>{selected.details}</div></div>
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">Connections ({WIRES.filter(w => w.from === selected.id || w.to === selected.id).length})</h3>
              <div className="space-y-1">
                {WIRES.filter(w => w.from === selected.id || w.to === selected.id).map((w) => (
                  <button key={w.id} onClick={() => selectWire(w)} className={`w-full text-left text-[11px] px-3 py-2 rounded-xl flex items-center gap-2 transition-all duration-200 ${glassCard} ${glassCardHover}`}>
                    <span className="text-muted-foreground/40">{w.from === selected.id ? "→" : "←"}</span>
                    <span className="font-medium">{w.label}</span>
                    <span className="text-muted-foreground/40 ml-auto text-[10px]">{w.protocol}</span>
                    {w.port && <span className="font-mono text-[9px] text-purple-400/60">{w.port}</span>}
                    {w.critical && <span className="text-red-400 text-[10px] animate-pulse">●</span>}
                  </button>
                ))}
              </div>
            </div>
            {selected.qa.length > 0 && (
              <div><h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-1.5">💬 Q&A</h3>
                <div className="space-y-1.5">{selected.qa.map((item, i) => (
                  <div key={i} className={`rounded-xl overflow-hidden ${glassCard}`}>
                    <button onClick={() => setQaOpen(qaOpen === i ? null : i)} className="w-full text-left px-3 py-2.5 text-[12px] font-medium hover:bg-white/[0.04] transition-colors flex items-center justify-between gap-2"><span>{item.q}</span><span className="text-muted-foreground/40 text-xs shrink-0">{qaOpen === i ? "▲" : "▼"}</span></button>
                    {qaOpen === i && <div className="px-3 py-2 text-[12px] text-muted-foreground/60 border-t border-white/[0.06] leading-relaxed">{item.a}</div>}
                  </div>
                ))}</div></div>
            )}
            {selected.alternatives.length > 0 && (
              <div>
                <Separator className="mb-4 opacity-10" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-2">⇄ Swap — What If You Replaced This?</h3>
                <div className="space-y-2">
                  {selected.alternatives.map((alt) => {
                    const isActive = activeSwap?.name === alt.name;
                    return (
                      <div key={alt.name} className={`rounded-xl overflow-hidden transition-all duration-300 ${isActive ? "bg-amber-500/[0.06] border border-amber-500/20 shadow-[0_0_20px_rgba(245,158,11,0.1)]" : glassCard}`}>
                        <button onClick={() => setActiveSwap(isActive ? null : alt)} className="w-full text-left px-3 py-3 transition-colors flex items-center gap-2.5 hover:bg-white/[0.03]">
                          <span className="text-lg">{alt.icon}</span>
                          <div className="flex-1 min-w-0"><span className="text-sm font-semibold block">{alt.name}</span><span className="text-[11px] text-muted-foreground/50 block truncate">{alt.summary}</span></div>
                          <span className="text-muted-foreground/30 text-xs shrink-0">{isActive ? "▲" : "▼"}</span>
                        </button>
                        {isActive && (
                          <div className="border-t border-white/[0.06] p-3 space-y-3">
                            <p className="text-xs text-muted-foreground/60">{alt.summary}</p>
                            <div className="space-y-2">{alt.impacts.map((imp, j) => (
                              <div key={j} className="flex items-start gap-2.5 text-[11px]">
                                <span className={`shrink-0 font-bold mt-0.5 text-sm ${imp.delta === "better" ? "text-emerald-400" : imp.delta === "worse" ? "text-red-400" : "text-muted-foreground/40"}`}>{imp.delta === "better" ? "▲" : imp.delta === "worse" ? "▼" : "━"}</span>
                                <div className="flex-1"><span className="font-semibold">{imp.category}: {imp.label}</span><p className="text-muted-foreground/50 leading-snug mt-0.5">{imp.reason}</p></div>
                              </div>
                            ))}</div>
                            <div className="pt-2 border-t border-white/[0.05]">
                              <p className="text-[10px] text-muted-foreground/40 font-medium uppercase tracking-wider mb-1.5">Affected Connections ({alt.affectedWires.length})</p>
                              <div className="flex flex-wrap gap-1">{alt.affectedWires.map((wid) => { const w = WIRES.find(x => x.id === wid); return w ? <button key={wid} onClick={() => selectWire(w)} className="text-[10px] px-2.5 py-0.5 rounded-full bg-amber-500/[0.08] text-amber-400/80 border border-amber-500/20 hover:bg-amber-500/[0.15] transition-all">{w.label}</button> : null; })}</div>
                            </div>
                            <div className="flex gap-4 pt-2 border-t border-white/[0.05] text-[11px]">
                              <span className="text-emerald-400 font-bold">{alt.impacts.filter(i => i.delta === "better").length} better</span>
                              <span className="text-red-400 font-bold">{alt.impacts.filter(i => i.delta === "worse").length} worse</span>
                              <span className="text-muted-foreground/40 font-bold">{alt.impacts.filter(i => i.delta === "neutral").length} neutral</span>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Selection mode panel */}
        {selectionMode && (
          <div className="p-5 space-y-5">
            <div>
              <h2 className="text-lg font-bold bg-gradient-to-r from-cyan-300 to-blue-300 bg-clip-text text-transparent flex items-center gap-2">🧩 Component Selection</h2>
              <p className="text-sm text-muted-foreground/50 mt-1.5 leading-relaxed">Click components in the diagram to select them. Only components with a direct connection to your selection can be added.</p>
            </div>
            <div className={`rounded-xl p-4 ${glassCard}`}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50">{selectedComponents.size} of {DEFAULT_COMPONENTS.length} selected</span>
                {selectedComponents.size > 0 && <button onClick={() => { setSelectedComponents(new Set()); setAiDescriptions({}); }} className="text-[10px] text-red-400/60 hover:text-red-400 transition-colors">Clear all</button>}
              </div>
              <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden"><div className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all duration-500" style={{ width: `${(selectedComponents.size / DEFAULT_COMPONENTS.length) * 100}%` }} /></div>
            </div>
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-2">Components</h3>
              <div className="space-y-1">
                {DEFAULT_COMPONENTS.map((comp) => {
                  const isChk = selectedComponents.has(comp.id);
                  const canS = isChk || reachableComponents.has(comp.id) || selectedComponents.size === 0;
                  return (
                    <button key={comp.id} onClick={() => canS && toggleComponentSelection(comp.id)} disabled={!canS}
                      className={`w-full text-left text-[11px] px-3 py-2 rounded-xl flex items-center gap-2 transition-all duration-200 ${isChk ? "bg-cyan-500/[0.08] border border-cyan-500/20" : canS ? `${glassCard} ${glassCardHover}` : "bg-white/[0.01] border border-white/[0.03] opacity-30 cursor-not-allowed"}`}>
                      <span className={`w-4 h-4 rounded flex items-center justify-center text-[9px] shrink-0 ${isChk ? "bg-cyan-500 text-black font-bold" : "border border-white/[0.15] bg-white/[0.03]"}`}>{isChk ? "✓" : ""}</span>
                      <span className="text-sm">{comp.icon}</span>
                      <span className={`font-medium ${isChk ? "text-cyan-300" : ""}`}>{comp.label}</span>
                      <span className="text-muted-foreground/30 ml-auto text-[9px]">{comp.layer}</span>
                      {!canS && selectedComponents.size > 0 && <span className="text-[8px] text-red-400/40">no connection</span>}
                    </button>
                  );
                })}
              </div>
            </div>
            {selectedComponents.size >= 2 && (
              <div className={`rounded-xl p-4 ${glassCard}`}>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/50 mb-2">Connections Found</h3>
                {focusWires.length > 0 ? (
                  <div className="space-y-1.5">{focusWires.map((wire) => (
                    <div key={wire.id} className="flex items-center gap-2 text-[11px]">
                      <span className={`w-1.5 h-1.5 rounded-full ${wire.critical ? "bg-red-400" : "bg-cyan-400"}`} />
                      <span className="text-muted-foreground/60">{getComp(wire.from)?.icon}</span>
                      <span className="text-muted-foreground/40">→</span>
                      <span className="text-muted-foreground/60">{getComp(wire.to)?.icon}</span>
                      <span className="font-medium">{wire.label}</span>
                      <span className="text-muted-foreground/30 ml-auto text-[9px]">{wire.protocol}</span>
                    </div>
                  ))}</div>
                ) : <p className="text-[11px] text-muted-foreground/40">No direct connections between selected components.</p>}
              </div>
            )}
            {selectedComponents.size >= 2 && focusWires.length > 0 && (
              <button onClick={enterFocusView}
                className="w-full py-3 rounded-xl text-sm font-bold transition-all duration-300 bg-gradient-to-r from-cyan-500/20 to-blue-500/20 border border-cyan-500/30 text-cyan-300 hover:from-cyan-500/30 hover:to-blue-500/30 shadow-[0_0_24px_rgba(6,182,212,0.2)] flex items-center justify-center gap-2">
                🔎 Enter Focus View <span className="text-[10px] text-cyan-400/60">({focusWires.length} connections · AI descriptions)</span>
              </button>
            )}
          </div>
        )}

        {/* Empty state */}
        {!selected && !selectedWire && !selectionMode && (
          <div className="p-8 text-center space-y-4">
            <div className="text-5xl" style={{ filter: "drop-shadow(0 0 16px rgba(139,92,246,0.3))" }}>🏗️</div>
            <h2 className="text-lg font-bold bg-gradient-to-r from-blue-300 to-purple-300 bg-clip-text text-transparent">OpenDeploy Architecture</h2>
            <p className="text-sm text-muted-foreground/50 leading-relaxed max-w-xs mx-auto">Drag components to rearrange. Click any component or connection to explore. Use ⇄ to swap frameworks.</p>
            <div className="text-xs text-muted-foreground/40 space-y-1.5 pt-4">
              <p>🖱️ <strong className="text-muted-foreground/60">Drag</strong> → rearrange within layer</p>
              <p>🔗 <strong className="text-muted-foreground/60">Click wire</strong> → protocol, port, data flow</p>
              <p>👆 <strong className="text-muted-foreground/60">Hover</strong> → highlight data paths</p>
              <p>📊 <strong className="text-muted-foreground/60">Wire modes</strong> → All / On Hover / Critical Only</p>
              <p>⇄ <strong className="text-muted-foreground/60">Swap</strong> → impact analysis</p>
              <p>🔄 <strong className="text-muted-foreground/60">Double-click</strong> → reset position</p>
            </div>
            <div className={`rounded-xl p-4 mt-4 ${glassCard} text-left`}>
              <div className="flex items-center gap-2 mb-2"><span className="text-base">🧩</span><span className="text-xs font-bold text-cyan-300">New: Select & Focus</span></div>
              <p className="text-[11px] text-muted-foreground/50 leading-relaxed">Click the <strong className="text-cyan-300/80">Select & Focus</strong> button to pick specific components, then isolate them in a clean focus view with AI-generated relationship descriptions.</p>
            </div>
            <div className="pt-4 text-left text-xs space-y-2 border-t border-white/[0.05] max-w-xs mx-auto">
              <p className="font-semibold text-muted-foreground/40 mb-2">Layers:</p>
              {[
                { color: "#3b82f6", label: "Clients — Browser, CLI, gRPC" },
                { color: "#8b5cf6", label: "Frontend — Next.js, Nginx" },
                { color: "#22c55e", label: "Backend — FastAPI, Registry, DB, Metrics" },
                { color: "#06b6d4", label: "Real-time — WebRTC, SHM IPC" },
                { color: "#ef4444", label: "Observability — Prometheus, Grafana" },
                { color: "#f97316", label: "Infrastructure — Docker, AWS, K8s" },
                { color: "#ec4899", label: "Edge — ONNX, Triton, vLLM" },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-2.5">
                  <div className="w-3 h-3 rounded-full shrink-0" style={{ background: item.color, boxShadow: `0 0 8px ${item.color}55` }} />
                  <span className="text-muted-foreground/50">{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
