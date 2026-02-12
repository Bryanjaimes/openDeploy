from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, Float, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import datetime
import os

DATABASE_URL = os.getenv("OPENDEPLOY_DATABASE_URL", "sqlite:///./opendeploy.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, server_default=func.now())
    model = Column(String, index=True)
    input = Column(String)
    result = Column(JSON)


class GlossaryCache(Base):
    """Cached AI-generated glossary descriptions.  One row per term."""
    __tablename__ = "glossary_cache"

    term = Column(String, primary_key=True, index=True)
    display_name = Column(String, nullable=False)
    short = Column(String, nullable=False)
    detail = Column(String, nullable=True)
    category = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class ModelEvolution(Base):
    """Tracks every iteration of any deployed model as it improves.

    Supports vision, LLM, audio, multimodal and other model types.
    Metrics that don't apply to a given model_type are simply left NULL.
    """
    __tablename__ = "model_evolution"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, server_default=func.now())

    # ── Identity ────────────────────────────────────────────────
    model_type = Column(String, nullable=False, default="vision", index=True)
    #   "vision" | "llm" | "audio" | "multimodal" | "other"
    version = Column(String, nullable=False, index=True)          # e.g. "V0", "V1", ...
    iteration = Column(Integer, nullable=False)                    # sequential counter within version
    tag = Column(String, nullable=False)                           # short human label

    # ── What changed ────────────────────────────────────────────
    description = Column(String, nullable=False)
    changes = Column(JSON, nullable=True)                          # structured list of changes

    # ── Model details ───────────────────────────────────────────
    model_arch = Column(String, nullable=True)                     # "yolov8n-seg", "mistral-7b", etc.
    model_weights = Column(String, nullable=True)                  # path or URI to weights
    model_size_mb = Column(Float, nullable=True)                   # model file size in MB
    model_params = Column(Integer, nullable=True)                  # total parameter count
    training_data = Column(String, nullable=True)
    training_epochs = Column(Integer, nullable=True)
    training_time_min = Column(Float, nullable=True)

    # ── Shared performance metrics ──────────────────────────────
    benchmark_dataset = Column(String, nullable=True)
    num_eval_samples = Column(Integer, nullable=True)              # images, prompts, etc.
    avg_inference_ms = Column(Float, nullable=True)
    status = Column(String, default="completed")
    notes = Column(String, nullable=True)
    metrics_raw = Column(JSON, nullable=True)                      # full raw benchmark dump

    # ── Vision-specific metrics ─────────────────────────────────
    num_eval_images = Column(Integer, nullable=True)               # alias kept for compat
    mAP50 = Column(Float, nullable=True)
    mAP50_95 = Column(Float, nullable=True)
    precision = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    avg_detections = Column(Float, nullable=True)
    total_classes = Column(Integer, nullable=True)
    target_classes = Column(JSON, nullable=True)
    per_class_ap = Column(JSON, nullable=True)                     # {class_name: AP} dict
    mask_iou = Column(Float, nullable=True)                        # segmentation mask IoU
    fps = Column(Float, nullable=True)                             # frames per second
    false_positive_rate = Column(Float, nullable=True)
    confidence_calibration = Column(Float, nullable=True)          # ECE or similar
    temporal_consistency = Column(Float, nullable=True)            # frame-to-frame consistency

    # Movement/action specific (V3+)
    action_accuracy = Column(Float, nullable=True)
    action_classes = Column(Integer, nullable=True)
    novel_detection_rate = Column(Float, nullable=True)

    # ── LLM-specific metrics ───────────────────────────────────
    # Knowledge & reasoning
    mmlu_score = Column(Float, nullable=True)                      # Massive Multitask Language Understanding
    mmlu_pro_score = Column(Float, nullable=True)                  # MMLU-Pro (harder)
    gpqa_score = Column(Float, nullable=True)                      # Graduate-level science QA
    arc_agi_score = Column(Float, nullable=True)                   # ARC-AGI reasoning
    hellaswag_score = Column(Float, nullable=True)                 # commonsense NLI
    bigbench_hard_score = Column(Float, nullable=True)             # BIG-Bench Hard
    truthfulqa_score = Column(Float, nullable=True)                # TruthfulQA
    livebench_score = Column(Float, nullable=True)                 # LiveBench (contamination-free)

    # Code generation
    humaneval_score = Column(Float, nullable=True)                 # HumanEval Pass@1
    humaneval_plus_score = Column(Float, nullable=True)            # HumanEval+ (stricter tests)
    mbpp_score = Column(Float, nullable=True)                      # Mostly Basic Python Problems
    swe_bench_score = Column(Float, nullable=True)                 # SWE-bench (real GH issues)
    pass_at_1 = Column(Float, nullable=True)                       # generic Pass@1

    # Math
    math_score = Column(Float, nullable=True)                      # MATH benchmark
    gsm8k_score = Column(Float, nullable=True)                     # GSM8K grade-school math

    # Conversational / human-pref
    chatbot_arena_elo = Column(Float, nullable=True)               # LMSYS Chatbot Arena ELO
    mt_bench_score = Column(Float, nullable=True)                  # MT-Bench multi-turn
    alpaca_eval_score = Column(Float, nullable=True)               # AlpacaEval 2.0 LC win-rate

    # Reliability
    hallucination_rate = Column(Float, nullable=True)              # % hallucinated answers
    cot_consistency = Column(Float, nullable=True)                 # chain-of-thought self-consistency

    # Safety
    toxicity_score = Column(Float, nullable=True)                  # lower = safer
    bias_score = Column(Float, nullable=True)                      # fairness/bias metric
    refusal_accuracy = Column(Float, nullable=True)                # correct refusal rate on harmful input

    # LLM throughput
    context_window = Column(Integer, nullable=True)                # max context length in tokens
    ttft_ms = Column(Float, nullable=True)                         # time to first token
    tokens_per_sec = Column(Float, nullable=True)                  # decode throughput
    total_tokens_eval = Column(Integer, nullable=True)             # tokens processed during eval

    # Cost
    cost_per_1k_tokens = Column(Float, nullable=True)              # $ per 1k tokens


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
