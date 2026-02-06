from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Security, Depends, status, Form, Request, Response
from fastapi.security import APIKeyHeader
from starlette.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Tuple
from contextlib import asynccontextmanager
import time
import os
import logging
import threading
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

from backend.registry import registry
from backend.loader import load_plugins
from backend.database import init_db, get_db, Prediction, GlossaryCache
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
    model: str = "diabetic-retinopathy-glaucoma-detector"


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

