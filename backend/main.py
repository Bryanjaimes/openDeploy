from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Security, Depends, status, Form, Request, Response
from fastapi.security import APIKeyHeader
from fastapi.responses import HTMLResponse, FileResponse
from starlette.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Tuple
from contextlib import asynccontextmanager
import time
import os
import logging
import threading
import uuid
import shutil
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

from backend.registry import registry
from backend.loader import load_plugins
from backend.database import init_db, get_db, Prediction, GlossaryCache, ModelEvolution, Recording
from backend.metrics import metrics_store
from backend.metrics_prom import REQUESTS_TOTAL, REQUEST_LATENCY_MS, ACTIVE_REQUESTS, COMPUTE_MS, MODEL_LOAD_MS
from backend.shm_frames import SharedMemoryFrameReader
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy.orm import Session
from pydantic import BaseModel

# --- Security Setup ---
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

RATE_LIMIT_PER_MIN = int(os.getenv("OPENDEPLOY_RATE_LIMIT_PER_MIN", "60"))
MAX_BODY_BYTES = int(os.getenv("OPENDEPLOY_MAX_BODY_MB", "10")) * 1024 * 1024

_rate_lock = threading.Lock()
_rate_state: Dict[str, Tuple[float, int]] = {}


async def get_api_key(api_key_header: str = Security(api_key_header)):
    expected_key = os.getenv("OPENDEPLOY_API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server API key is not configured"
        )

    if api_key_header == expected_key:
        return api_key_header

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid or missing API Key"
    )
# ----------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database
    init_db()
    
    # Startup: Load all models dynamically
    # Resolve absolute path to models directory (sibling of backend)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    models_path = os.path.join(os.path.dirname(current_dir), "models")
    load_plugins(models_path)
    yield
    # Shutdown: Could unload models here if needed

app = FastAPI(
    title="OpenDeploy v2", 
    description="Minimal AI Deployment Platform",
    lifespan=lifespan
)

shm_reader = SharedMemoryFrameReader.from_env()

# ── Recordings directory ───────────────────────────────────────
RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Enable CORS for frontend communication
allowed_origins = [
    origin.strip() for origin in os.getenv(
        "OPENDEPLOY_ALLOWED_ORIGINS",
        "http://localhost:3001,http://127.0.0.1:3001,https://localhost:3443,https://127.0.0.1:3443"
    ).split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path
    enforce_limits = path.startswith("/models/") or path.startswith("/vision/stream/predict")

    if enforce_limits:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})

        api_key = request.headers.get(API_KEY_NAME, "")
        client_id = api_key if api_key else (request.client.host if request.client else "unknown")
        rate_key = f"{client_id}:{path}"
        now = time.time()

        with _rate_lock:
            window_start, count = _rate_state.get(rate_key, (now, 0))
            if now - window_start >= 60:
                window_start, count = now, 0
            count += 1
            _rate_state[rate_key] = (window_start, count)

            if RATE_LIMIT_PER_MIN > 0 and count > RATE_LIMIT_PER_MIN:
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    return await call_next(request)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    is_predict = request.url.path.startswith("/models/") and request.url.path.endswith("/predict")
    if is_predict:
        metrics_store.inc_active()
        ACTIVE_REQUESTS.inc()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        REQUEST_LATENCY_MS.labels(request.url.path, request.method).observe(duration_ms)
        status_code = getattr(response, "status_code", 500)
        REQUESTS_TOTAL.labels(request.url.path, request.method, str(status_code)).inc()
        if is_predict:
            # Extract model name from /models/{model_name}/predict
            parts = request.url.path.strip("/").split("/")
            model_name = parts[1] if len(parts) >= 3 else ""
            metrics_store.record_request(duration_ms, status_code, model_name=model_name)
            metrics_store.dec_active()
            ACTIVE_REQUESTS.dec()

@app.get("/")
def read_root():
    return {"message": "Welcome to OpenDeploy v2. Platform is running."}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/models", dependencies=[Depends(get_api_key)])
def list_models():
    """List all deployed models and their capabilities"""
    return registry.list_models()

@app.get("/history", dependencies=[Depends(get_api_key)])
def get_history(db: Session = Depends(get_db)):
    """Get the history of predictions"""
    return db.query(Prediction).order_by(Prediction.timestamp.desc()).all()

@app.post("/models/{model_name}/predict", dependencies=[Depends(get_api_key)])
async def predict(model_name: str, file: UploadFile = File(None), text_input: str = Form(None), db: Session = Depends(get_db)):
    """
    Generic prediction endpoint. 
    Accepts either a file (for image/audio models) or text_input (for LLMs).
    """
    model = registry.get_model(model_name)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if hasattr(model, "ready") and not getattr(model, "ready", False):
        start = time.perf_counter()
        model.load()
        duration_ms = (time.perf_counter() - start) * 1000.0
        metrics_store.record_model_load(model.name, duration_ms)
        MODEL_LOAD_MS.labels(model.name).observe(duration_ms)

    result = None
    input_summary = ""
    compute_start = time.perf_counter()

    # Simple routing based on input type
    if model.input_type == "text":
        if not text_input:
             raise HTTPException(status_code=400, detail="Model requires 'text_input'")
        result = await model.predict(text_input)
        input_summary = text_input[:50] + "..." if len(text_input) > 50 else text_input
    
    elif model.input_type == "image":
        if not file:
            raise HTTPException(status_code=400, detail="Model requires a file upload")
        # In a real app, we'd process the image bytes here
        content = await file.read()
        result = await model.predict(content)
        input_summary = f"Image: {file.filename}"

    else:
        raise HTTPException(status_code=500, detail="Unsupported model input type")

    compute_ms = (time.perf_counter() - compute_start) * 1000.0
    metrics_store.record_compute(compute_ms)
    COMPUTE_MS.observe(compute_ms)

    if isinstance(result, dict):
        result.setdefault("metrics", {})
        result["metrics"].update({
            "compute_ms": compute_ms
        })

    # Save to history
    db_prediction = Prediction(
        model=model_name,
        input=input_summary,
        result=result
    )
    db.add(db_prediction)
    db.commit()
    db.refresh(db_prediction)

    return result


class StreamPredictRequest(BaseModel):
    model: str = "yolov8-seg"


class StreamWindowRequest(BaseModel):
    model: str = "yolov8-seg"
    frames: int = 16


class DirectDetectRequest(BaseModel):
    model: str = "yolov8-seg"
    image: str  # base64-encoded image (JPEG/PNG)


@app.post("/vision/detect")
async def vision_detect_direct(request: DirectDetectRequest):
    """Direct frame detection — accepts a base64 image, returns detections.

    No SHM or WebRTC gateway required. Ideal for local / Windows dev.
    """
    import base64

    model = registry.get_model(request.model)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if hasattr(model, "ready") and not getattr(model, "ready", False):
        start = time.perf_counter()
        model.load()
        duration_ms = (time.perf_counter() - start) * 1000.0
        metrics_store.record_model_load(model.name, duration_ms)
        MODEL_LOAD_MS.labels(model.name).observe(duration_ms)

    try:
        image_bytes = base64.b64decode(request.image)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    compute_start = time.perf_counter()
    result = await model.predict(image_bytes)
    compute_ms = (time.perf_counter() - compute_start) * 1000.0
    metrics_store.record_compute(compute_ms)
    COMPUTE_MS.observe(compute_ms)

    if isinstance(result, dict):
        result.setdefault("metrics", {})
        result["metrics"]["compute_ms"] = compute_ms

    return result


@app.post("/vision/stream/predict", dependencies=[Depends(get_api_key)])
async def predict_stream(request: StreamPredictRequest, db: Session = Depends(get_db)):
    model = registry.get_model(request.model)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if hasattr(model, "ready") and not getattr(model, "ready", False):
        start = time.perf_counter()
        model.load()
        duration_ms = (time.perf_counter() - start) * 1000.0
        metrics_store.record_model_load(model.name, duration_ms)
        MODEL_LOAD_MS.labels(model.name).observe(duration_ms)

    frame = shm_reader.read_latest()
    if not frame:
        raise HTTPException(status_code=404, detail="No shared-memory frame available")

    compute_start = time.perf_counter()
    try:
        image_bytes = frame.to_image_bytes()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = await model.predict(image_bytes)
    compute_ms = (time.perf_counter() - compute_start) * 1000.0
    metrics_store.record_compute(compute_ms)
    COMPUTE_MS.observe(compute_ms)

    if isinstance(result, dict):
        result.setdefault("metrics", {})
        result["metrics"].update({
            "compute_ms": compute_ms,
            "frame_seq": frame.seq,
            "frame_timestamp_ns": frame.timestamp_ns,
            "frame_size": f"{frame.width}x{frame.height}",
        })

    db_prediction = Prediction(
        model=request.model,
        input=f"SHM frame seq {frame.seq}",
        result=result,
    )
    db.add(db_prediction)
    db.commit()
    db.refresh(db_prediction)

    return result


@app.post("/vision/stream/window", dependencies=[Depends(get_api_key)])
async def predict_stream_window(request: StreamWindowRequest):
    """Read a temporal window of frames from the ring buffer.

    Returns frame metadata for each frame in the window. This endpoint is
    the foundation for temporal action recognition — downstream models
    receive a sequence of frames rather than a single snapshot.
    """
    frames = shm_reader.read_window(n=min(request.frames, 64))
    if not frames:
        raise HTTPException(status_code=404, detail="No frames available in ring buffer")

    frame_list = []
    for f in frames:
        frame_list.append({
            "seq": f.seq,
            "timestamp_ns": f.timestamp_ns,
            "width": f.width,
            "height": f.height,
            "format": f.fmt,
            "data_len": len(f.data),
        })

    return {
        "frame_count": len(frames),
        "oldest_seq": frames[0].seq,
        "newest_seq": frames[-1].seq,
        "span_ms": (frames[-1].timestamp_ns - frames[0].timestamp_ns) / 1_000_000
        if len(frames) > 1
        else 0.0,
        "frames": frame_list,
    }


@app.get("/metrics", dependencies=[Depends(get_api_key)])
def get_metrics():
    snapshot = metrics_store.snapshot()
    return {
        **snapshot,
        "model_load_times_ms": metrics_store.model_load_times
    }


def get_metrics_token_header() -> Optional[str]:
    token = os.getenv("OPENDEPLOY_METRICS_TOKEN")
    return token.strip() if token else None


@app.get("/metrics/prometheus")
def get_prometheus_metrics(request: Request):
    token = get_metrics_token_header()
    if token:
        if request.headers.get("X-Metrics-Token") != token:
            raise HTTPException(status_code=403, detail="Missing or invalid metrics token")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)



class GenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = None

@app.post("/generate", dependencies=[Depends(get_api_key)])
async def generate(request: GenerateRequest, db: Session = Depends(get_db)):
    """
    Simple text-generation endpoint for V0 local runner.
    """
    # Pick requested model or first text-capable model
    model_name = request.model
    if not model_name:
        for m in registry.list_models():
            if m.get("input_type") == "text":
                model_name = m.get("name")
                break

    if not model_name:
        raise HTTPException(status_code=404, detail="No text-capable model available")

    model = registry.get_model(model_name)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    result = await model.predict(request.prompt)

    # Save to history
    db_prediction = Prediction(
        model=model_name,
        input=request.prompt[:50] + "..." if len(request.prompt) > 50 else request.prompt,
        result=result
    )
    db.add(db_prediction)
    db.commit()
    db.refresh(db_prediction)

    if isinstance(result, dict):
        return {"model": model_name, **result}
    return {"model": model_name, "response": result}


# ── Glossary AI description endpoint ────────────────────────────────

class GlossaryDescribeRequest(BaseModel):
    term: str
    context: Optional[str] = None  # e.g. "shown on the Metrics page"


def _generate_glossary_via_openai(term: str, context: Optional[str] = None) -> dict:
    """Call OpenAI (or compatible endpoint) to generate a glossary entry."""
    import json as _json

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        raise HTTPException(
            status_code=501,
            detail="OPENAI_API_KEY not configured on server",
        )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)

        system_prompt = (
            "You are a concise technical glossary writer for OpenDeploy, "
            "an open-source GPU-optimized AI deployment platform.\n"
            "Respond ONLY with valid JSON — no markdown fences.\n"
            '{"term": "<Display Name>", '
            '"short": "<1-sentence plain-English explanation>", '
            '"detail": "<2-3 sentence deeper explanation>", '
            '"category": "<Metric|Infra|ML|Cost|Platform>"}'
        )

        user_msg = f'Define "{term}"'
        if context:
            user_msg += f" (context: {context})"

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=300,
        )

        raw = completion.choices[0].message.content or "{}"
        # Strip markdown fences if the model wraps them anyway
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        return _json.loads(raw)

    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="openai package not installed. Run: pip install openai",
        )
    except Exception as exc:
        logger.error(f"OpenAI glossary generation failed for '{term}': {exc}")
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/glossary/describe")
def describe_glossary_term(
    req: GlossaryDescribeRequest,
    db: Session = Depends(get_db),
):
    """
    Return an AI-generated description for a technical term.
    Results are cached in SQLite — OpenAI is only called once per term.
    """
    normalized = req.term.strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="term is required")

    # 1. Check cache
    cached = db.query(GlossaryCache).filter(GlossaryCache.term == normalized).first()
    if cached:
        return {
            "term": cached.display_name,
            "short": cached.short,
            "detail": cached.detail,
            "category": cached.category,
            "source": "cache",
        }

    # 2. Generate via OpenAI
    entry = _generate_glossary_via_openai(req.term, req.context)

    # 3. Persist to cache
    row = GlossaryCache(
        term=normalized,
        display_name=entry.get("term", req.term),
        short=entry.get("short", ""),
        detail=entry.get("detail"),
        category=entry.get("category"),
    )
    db.merge(row)
    db.commit()

    return {
        "term": row.display_name,
        "short": row.short,
        "detail": row.detail,
        "category": row.category,
        "source": "generated",
    }


@app.get("/glossary/cache")
def list_glossary_cache(db: Session = Depends(get_db)):
    """Return all cached glossary entries."""
    rows = db.query(GlossaryCache).order_by(GlossaryCache.term).all()
    return [
        {
            "term": r.display_name,
            "short": r.short,
            "detail": r.detail,
            "category": r.category,
        }
        for r in rows
    ]


# ── Serve the vision client at /vision ──────────────────────────
@app.get("/vision", response_class=HTMLResponse)
def serve_vision_client():
    """Serve the live detection client HTML page."""
    client_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "webrtc-client.html"
    )
    with open(client_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ── Model Evolution Tracking API ────────────────────────────────


# V7 roadmap definition — used by the dashboard
V7_ROADMAP = [
    {"version": "V0", "name": "Baseline COCO", "goal": "Pretrained YOLOv8n-seg on COCO 80 classes, no fine-tuning"},
    {"version": "V1", "name": "Sports Objects", "goal": "Fine-tune on sports equipment and courts"},
    {"version": "V2", "name": "Athlete Pose", "goal": "Add pose estimation for athlete body keypoints"},
    {"version": "V3", "name": "Basic Actions", "goal": "Temporal action classification (punch, kick, run, jump)"},
    {"version": "V4", "name": "Sport-Specific", "goal": "Multi-sport action sets (MMA, basketball, soccer, tennis)"},
    {"version": "V5", "name": "Sequence Understanding", "goal": "Multi-frame combos and movement sequences"},
    {"version": "V6", "name": "Real-time + Edge", "goal": "Optimised for real-time edge inference (<10ms)"},
    {"version": "V7", "name": "Universal Sports AI", "goal": "Any sport, any move, any combat style — production-ready"},
]


class EvolutionEntry(BaseModel):
    model_type: str = "vision"  # "vision" | "llm" | "audio" | "multimodal" | "other"
    version: str
    iteration: int = 0
    tag: str
    description: str
    changes: list[str] | None = None
    # Model details
    model_arch: str | None = None
    model_weights: str | None = None
    model_size_mb: float | None = None
    model_params: int | None = None
    training_data: str | None = None
    training_epochs: int | None = None
    training_time_min: float | None = None
    # Shared
    benchmark_dataset: str | None = None
    num_eval_samples: int | None = None
    num_eval_images: int | None = None
    avg_inference_ms: float | None = None
    status: str = "completed"
    notes: str | None = None
    metrics_raw: dict | None = None
    # Vision metrics
    mAP50: float | None = None
    mAP50_95: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1_score: float | None = None
    avg_detections: float | None = None
    total_classes: int | None = None
    target_classes: list[str] | None = None
    per_class_ap: dict | None = None
    mask_iou: float | None = None
    fps: float | None = None
    false_positive_rate: float | None = None
    confidence_calibration: float | None = None
    temporal_consistency: float | None = None
    action_accuracy: float | None = None
    action_classes: int | None = None
    novel_detection_rate: float | None = None
    # LLM metrics — knowledge & reasoning
    mmlu_score: float | None = None
    mmlu_pro_score: float | None = None
    gpqa_score: float | None = None
    arc_agi_score: float | None = None
    hellaswag_score: float | None = None
    bigbench_hard_score: float | None = None
    truthfulqa_score: float | None = None
    livebench_score: float | None = None
    # LLM metrics — code
    humaneval_score: float | None = None
    humaneval_plus_score: float | None = None
    mbpp_score: float | None = None
    swe_bench_score: float | None = None
    pass_at_1: float | None = None
    # LLM metrics — math
    math_score: float | None = None
    gsm8k_score: float | None = None
    # LLM metrics — conversational
    chatbot_arena_elo: float | None = None
    mt_bench_score: float | None = None
    alpaca_eval_score: float | None = None
    # LLM metrics — reliability
    hallucination_rate: float | None = None
    cot_consistency: float | None = None
    # LLM metrics — safety
    toxicity_score: float | None = None
    bias_score: float | None = None
    refusal_accuracy: float | None = None
    # LLM metrics — throughput
    context_window: int | None = None
    ttft_ms: float | None = None
    tokens_per_sec: float | None = None
    total_tokens_eval: int | None = None
    cost_per_1k_tokens: float | None = None


@app.get("/vision/evolution")
def list_evolution(db: Session = Depends(get_db)):
    """List all model evolution entries, ordered by timestamp, with linked recordings."""
    rows = db.query(ModelEvolution).order_by(ModelEvolution.timestamp.asc()).all()
    all_recs = db.query(Recording).order_by(Recording.created_at.desc()).all()

    # Build a map of evolution_id → recordings, plus unlinked ones matched by model_arch
    recs_by_evo: dict[int, list] = {}
    for rec in all_recs:
        evo_id = getattr(rec, 'evolution_id', None)
        if evo_id:
            recs_by_evo.setdefault(evo_id, []).append(rec)

    # Also try to match unlinked recordings by model_arch
    for rec in all_recs:
        if getattr(rec, 'evolution_id', None):
            continue
        rec_arch = getattr(rec, 'model_arch', None) or getattr(rec, 'model', None) or ''
        if not rec_arch:
            continue
        for row in rows:
            if row.model_arch and rec_arch.lower() in row.model_arch.lower():
                recs_by_evo.setdefault(row.id, []).append(rec)
                break

    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "model_type": getattr(r, "model_type", "vision"),
            "version": r.version,
            "iteration": r.iteration,
            "tag": r.tag,
            "description": r.description,
            "changes": r.changes,
            "model_arch": r.model_arch,
            "model_weights": r.model_weights,
            "model_size_mb": r.model_size_mb,
            "model_params": r.model_params,
            "training_data": r.training_data,
            "training_epochs": r.training_epochs,
            "training_time_min": r.training_time_min,
            "benchmark_dataset": r.benchmark_dataset,
            "num_eval_samples": r.num_eval_samples,
            "num_eval_images": r.num_eval_images,
            "avg_inference_ms": r.avg_inference_ms,
            "status": r.status,
            "notes": r.notes,
            "metrics_raw": r.metrics_raw,
            # Vision
            "mAP50": r.mAP50,
            "mAP50_95": r.mAP50_95,
            "precision": r.precision,
            "recall": r.recall,
            "f1_score": r.f1_score,
            "avg_detections": r.avg_detections,
            "total_classes": r.total_classes,
            "target_classes": r.target_classes,
            "per_class_ap": r.per_class_ap,
            "mask_iou": r.mask_iou,
            "fps": r.fps,
            "false_positive_rate": r.false_positive_rate,
            "confidence_calibration": r.confidence_calibration,
            "temporal_consistency": r.temporal_consistency,
            "action_accuracy": r.action_accuracy,
            "action_classes": r.action_classes,
            "novel_detection_rate": r.novel_detection_rate,
            # LLM
            "mmlu_score": r.mmlu_score,
            "mmlu_pro_score": r.mmlu_pro_score,
            "gpqa_score": r.gpqa_score,
            "arc_agi_score": r.arc_agi_score,
            "hellaswag_score": r.hellaswag_score,
            "bigbench_hard_score": r.bigbench_hard_score,
            "truthfulqa_score": r.truthfulqa_score,
            "livebench_score": r.livebench_score,
            "humaneval_score": r.humaneval_score,
            "humaneval_plus_score": r.humaneval_plus_score,
            "mbpp_score": r.mbpp_score,
            "swe_bench_score": r.swe_bench_score,
            "pass_at_1": r.pass_at_1,
            "math_score": r.math_score,
            "gsm8k_score": r.gsm8k_score,
            "chatbot_arena_elo": r.chatbot_arena_elo,
            "mt_bench_score": r.mt_bench_score,
            "alpaca_eval_score": r.alpaca_eval_score,
            "hallucination_rate": r.hallucination_rate,
            "cot_consistency": r.cot_consistency,
            "toxicity_score": r.toxicity_score,
            "bias_score": r.bias_score,
            "refusal_accuracy": r.refusal_accuracy,
            "context_window": r.context_window,
            "ttft_ms": r.ttft_ms,
            "tokens_per_sec": r.tokens_per_sec,
            "total_tokens_eval": r.total_tokens_eval,
            "cost_per_1k_tokens": r.cost_per_1k_tokens,
            # Linked recordings
            "recordings": [
                _serialize_recording(rec)
                for rec in recs_by_evo.get(r.id, [])
            ],
        }
        for r in rows
    ]


@app.get("/vision/evolution/roadmap")
def get_roadmap(db: Session = Depends(get_db)):
    """Return the V7 roadmap with current progress overlaid."""
    # Get the latest entry per version
    latest_by_version: dict[str, dict] = {}
    rows = db.query(ModelEvolution).order_by(ModelEvolution.timestamp.asc()).all()
    for r in rows:
        latest_by_version[r.version] = {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "model_type": getattr(r, "model_type", "vision"),
            "tag": r.tag,
            "iteration": r.iteration,
            "mAP50": r.mAP50,
            "precision": r.precision,
            "avg_inference_ms": r.avg_inference_ms,
            "status": r.status,
            # LLM headline metrics
            "mmlu_score": r.mmlu_score,
            "humaneval_score": r.humaneval_score,
            "chatbot_arena_elo": r.chatbot_arena_elo,
            "tokens_per_sec": r.tokens_per_sec,
        }

    roadmap = []
    for stage in V7_ROADMAP:
        entry = {**stage, "status": "not-started", "latest": None}
        if stage["version"] in latest_by_version:
            entry["status"] = latest_by_version[stage["version"]].get("status", "completed")
            entry["latest"] = latest_by_version[stage["version"]]
        roadmap.append(entry)

    return {
        "roadmap": roadmap,
        "total_entries": len(rows),
        "current_version": rows[-1].version if rows else None,
    }


@app.get("/vision/evolution/latest")
def latest_evolution(db: Session = Depends(get_db)):
    """Get the most recent evolution entry."""
    row = db.query(ModelEvolution).order_by(ModelEvolution.timestamp.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail="No evolution entries yet")
    return {
        "id": row.id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "model_type": getattr(row, "model_type", "vision"),
        "version": row.version,
        "iteration": row.iteration,
        "tag": row.tag,
        "description": row.description,
        "mAP50": row.mAP50,
        "precision": row.precision,
        "avg_inference_ms": row.avg_inference_ms,
        "total_classes": row.total_classes,
        "status": row.status,
        # LLM headline
        "mmlu_score": row.mmlu_score,
        "humaneval_score": row.humaneval_score,
        "tokens_per_sec": row.tokens_per_sec,
    }


@app.post("/vision/evolution")
def add_evolution(entry: EvolutionEntry, db: Session = Depends(get_db)):
    """Add a new model evolution entry."""
    row = ModelEvolution(**entry.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "version": row.version, "tag": row.tag}


@app.get("/vision/evolution/{evo_id}/recordings")
def evolution_recordings(evo_id: int, db: Session = Depends(get_db)):
    """Get all recordings linked to a specific evolution entry."""
    evo = db.query(ModelEvolution).filter(ModelEvolution.id == evo_id).first()
    if not evo:
        raise HTTPException(status_code=404, detail="Evolution entry not found")

    # Direct link via FK
    recs = db.query(Recording).filter(
        Recording.evolution_id == evo_id
    ).order_by(Recording.created_at.desc()).all()

    # Also match by model_arch if no FK link
    if not recs and evo.model_arch:
        recs = db.query(Recording).filter(
            Recording.model_arch.ilike(f"%{evo.model_arch}%")
        ).order_by(Recording.created_at.desc()).all()
        # Fallback: match by model name
        if not recs:
            recs = db.query(Recording).filter(
                Recording.model.ilike(f"%{evo.model_arch.split('-')[0]}%")
            ).order_by(Recording.created_at.desc()).all()

    return {
        "evolution_id": evo_id,
        "version": evo.version,
        "tag": evo.tag,
        "model_arch": evo.model_arch,
        "recordings": [_serialize_recording(r) for r in recs],
        "total": len(recs),
    }


# ── Metrics Catalog ────────────────────────────────────────────────
from backend.metrics_catalog import (
    catalog_json,
    metrics_for_type,
    METRICS_BY_KEY,
    CATEGORIES,
    MODEL_TYPES as CATALOG_MODEL_TYPES,
)


# ═══════════════════════════════════════════════════════════════
#  Recordings — upload, list, download, delete
# ═══════════════════════════════════════════════════════════════

@app.post("/recordings/upload")
async def upload_recording(
    video: UploadFile = File(...),
    log: UploadFile = File(None),
    name: str = Form(""),
    duration_ms: int = Form(0),
    total_frames: int = Form(0),
    total_detections: int = Form(0),
    unique_classes: int = Form(0),
    avg_confidence: float = Form(0.0),
    avg_inference_ms: float = Form(0.0),
    model: str = Form(""),
    classes_seen: str = Form("[]"),
    model_arch: str = Form(""),
    model_version: str = Form(""),
    conf_threshold: float = Form(0.0),
    iou_threshold: float = Form(0.0),
    db: Session = Depends(get_db),
):
    """Upload a composite recording (video + optional log) from the live detection client."""
    import json as _json

    rec_id = uuid.uuid4().hex[:12]
    if not name:
        name = f"rec_{rec_id}"

    # Save video
    video_filename = f"{rec_id}.webm"
    video_path = os.path.join(RECORDINGS_DIR, video_filename)
    with open(video_path, "wb") as f:
        shutil.copyfileobj(video.file, f)
    video_size = os.path.getsize(video_path)

    # Save log (if provided)
    log_filename = None
    log_size = None
    if log and log.filename:
        log_filename = f"{rec_id}.txt"
        log_path_full = os.path.join(RECORDINGS_DIR, log_filename)
        with open(log_path_full, "wb") as f:
            shutil.copyfileobj(log.file, f)
        log_size = os.path.getsize(log_path_full)

    # Parse classes_seen
    try:
        classes_list = _json.loads(classes_seen)
    except Exception:
        classes_list = []

    # Match to latest evolution entry (by model_arch or model name)
    evolution_id_val = None
    if model_arch or model:
        match_arch = model_arch or model
        evo_row = db.query(ModelEvolution).filter(
            ModelEvolution.model_arch.ilike(f"%{match_arch}%")
        ).order_by(ModelEvolution.timestamp.desc()).first()
        if evo_row:
            evolution_id_val = evo_row.id

    # DB record
    rec = Recording(
        name=name,
        video_path=video_filename,
        log_path=log_filename,
        duration_ms=duration_ms,
        total_frames=total_frames,
        total_detections=total_detections,
        unique_classes=unique_classes,
        avg_confidence=avg_confidence,
        avg_inference_ms=avg_inference_ms,
        model=model,
        classes_seen=classes_list,
        model_arch=model_arch or None,
        model_version=model_version or None,
        conf_threshold=conf_threshold or None,
        iou_threshold=iou_threshold or None,
        evolution_id=evolution_id_val,
        video_size_bytes=video_size,
        log_size_bytes=log_size,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    return {
        "id": rec.id,
        "name": rec.name,
        "video_size": video_size,
        "log_size": log_size,
        "message": "Recording saved to server",
    }


@app.get("/recordings")
def list_recordings(db: Session = Depends(get_db)):
    """List all saved recordings, newest first."""
    recs = db.query(Recording).order_by(Recording.created_at.desc()).all()
    return {
        "recordings": [_serialize_recording(r) for r in recs],
        "total": len(recs),
    }


def _serialize_recording(r: Recording) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "duration_ms": r.duration_ms,
        "total_frames": r.total_frames,
        "total_detections": r.total_detections,
        "unique_classes": r.unique_classes,
        "avg_confidence": r.avg_confidence,
        "avg_inference_ms": r.avg_inference_ms,
        "model": r.model,
        "classes_seen": r.classes_seen,
        "model_arch": getattr(r, 'model_arch', None),
        "model_version": getattr(r, 'model_version', None),
        "conf_threshold": getattr(r, 'conf_threshold', None),
        "iou_threshold": getattr(r, 'iou_threshold', None),
        "evolution_id": getattr(r, 'evolution_id', None),
        "video_size_bytes": r.video_size_bytes,
        "log_size_bytes": r.log_size_bytes,
    }


@app.get("/recordings/{rec_id}/video")
def download_recording_video(rec_id: int, db: Session = Depends(get_db)):
    """Stream the recording video file."""
    rec = db.query(Recording).filter(Recording.id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    path = os.path.join(RECORDINGS_DIR, rec.video_path)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video file missing")
    return FileResponse(path, media_type="video/webm", filename=f"{rec.name}.webm")


@app.get("/recordings/{rec_id}/log")
def download_recording_log(rec_id: int, db: Session = Depends(get_db)):
    """Download the recording's detection log."""
    rec = db.query(Recording).filter(Recording.id == rec_id).first()
    if not rec or not rec.log_path:
        raise HTTPException(status_code=404, detail="Log not found")
    path = os.path.join(RECORDINGS_DIR, rec.log_path)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Log file missing")
    return FileResponse(path, media_type="text/plain", filename=f"{rec.name}_log.txt")


@app.delete("/recordings/{rec_id}")
def delete_recording(rec_id: int, db: Session = Depends(get_db)):
    """Delete a recording and its files."""
    rec = db.query(Recording).filter(Recording.id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    # Remove files
    for fname in [rec.video_path, rec.log_path]:
        if fname:
            fpath = os.path.join(RECORDINGS_DIR, fname)
            if os.path.exists(fpath):
                os.remove(fpath)

    db.delete(rec)
    db.commit()
    return {"message": "Recording deleted", "id": rec_id}


@app.get("/metrics/catalog")
def get_metrics_catalog(model_type: str | None = None):
    """Return the full metrics catalog, optionally filtered by model type.

    Query params:
        model_type — "llm", "vision", "audio", "video", "multimodal",
                     "embeddings", "agentic".  Omit for the full list.
    """
    return {
        "metrics": catalog_json(model_type),
        "categories": CATEGORIES if not model_type else list(
            dict.fromkeys(m.category for m in metrics_for_type(model_type))
        ),
        "model_types": CATALOG_MODEL_TYPES,
        "total": len(catalog_json(model_type)),
    }


@app.get("/metrics/catalog/{key}")
def get_metric_detail(key: str):
    """Return a single metric definition by its key."""
    m = METRICS_BY_KEY.get(key)
    if not m:
        raise HTTPException(status_code=404, detail=f"Metric '{key}' not found")
    return {
        "key": m.key,
        "name": m.name,
        "category": m.category,
        "description": m.description,
        "model_types": list(m.model_types),
        "unit": m.unit,
        "higher_is_better": m.higher_is_better,
        "format": m.format,
        "has_db_column": m.db_column is not None,
    }

