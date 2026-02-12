"""
OpenDeploy Metrics Catalog
==========================
Every evaluation metric in one place.  Each entry carries enough metadata
so the dashboard can:

1. Show the *relevant* metrics for a given model_type automatically.
2. Let users add *any* metric from the full catalog via a dropdown.
3. Display human-readable names, descriptions, and formatting hints.

Storage strategy
----------------
- A handful of "headline" metrics live as named DB columns for fast
  queries and indexing (mAP50, precision, mmlu_score, etc.).
- Everything else goes into the ``metrics_raw`` JSON column.
- The catalog is the single source of truth for what exists and how
  to display it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ModelType = Literal["llm", "vision", "audio", "video", "multimodal", "embeddings", "agentic", "other"]


@dataclass(frozen=True, slots=True)
class MetricDef:
    """One metric definition."""

    key: str                            # machine key stored in metrics_raw
    name: str                           # human-readable short name
    category: str                       # grouping label
    description: str                    # one-liner shown in tooltips
    model_types: tuple[ModelType, ...]  # which model types get this by default
    unit: str = ""                      # "%", "ms", "tokens/s", "$", etc.
    higher_is_better: bool = True       # for colour-coding (green ↑ / red ↓)
    format: str = ".1f"                 # Python format spec for display
    db_column: str | None = None        # if stored as a named column too


# ── helper to build many defs quickly ──────────────────────────────────
def _m(key, name, cat, desc, types, **kw) -> MetricDef:  # noqa: D401
    return MetricDef(key=key, name=name, category=cat, description=desc,
                     model_types=tuple(types), **kw)


# ═══════════════════════════════════════════════════════════════════════
#  Part 1 · LLM Metrics
# ═══════════════════════════════════════════════════════════════════════

_LLM: tuple[ModelType, ...] = ("llm",)
_LLM_MM: tuple[ModelType, ...] = ("llm", "multimodal")

LLM_KNOWLEDGE = [
    _m("mmlu_score",           "MMLU",            "Knowledge & Reasoning", "Massive Multitask Language Understanding — 57 academic subjects",                      _LLM_MM, unit="%", db_column="mmlu_score"),
    _m("mmlu_pro_score",       "MMLU-Pro",        "Knowledge & Reasoning", "Harder MMLU successor with 10-choice answers, less guessable",                         _LLM_MM, unit="%", db_column="mmlu_pro_score"),
    _m("gpqa_score",           "GPQA Diamond",    "Knowledge & Reasoning", "PhD-level science QA — physics, chemistry, biology",                                   _LLM_MM, unit="%", db_column="gpqa_score"),
    _m("arc_agi_score",        "ARC-AGI",         "Knowledge & Reasoning", "Abstract visual-pattern reasoning — pure novel problem-solving",                       _LLM_MM, unit="%", db_column="arc_agi_score"),
    _m("bigbench_hard_score",  "BigBench-Hard",   "Knowledge & Reasoning", "23 tasks where prior LMs < average human — multi-step reasoning",                     _LLM_MM, unit="%", db_column="bigbench_hard_score"),
    _m("hellaswag_score",      "HellaSwag",       "Knowledge & Reasoning", "Commonsense NLI — predict the most plausible continuation",                           _LLM_MM, unit="%", db_column="hellaswag_score"),
    _m("truthfulqa_score",     "TruthfulQA",      "Knowledge & Reasoning", "Designed to elicit common misconceptions — tests factual alignment",                   _LLM_MM, unit="%", db_column="truthfulqa_score"),
    _m("livebench_score",      "LiveBench",       "Knowledge & Reasoning", "Contamination-free benchmark updated with new questions",                              _LLM_MM, unit="%", db_column="livebench_score"),
    _m("winogrande_score",     "WinoGrande",      "Knowledge & Reasoning", "Pronoun resolution requiring commonsense reasoning",                                  _LLM_MM, unit="%"),
    _m("drop_score",           "DROP",            "Knowledge & Reasoning", "Discrete Reasoning Over Paragraphs — counting, sorting, arithmetic",                  _LLM_MM, unit="%"),
    _m("musr_score",           "MuSR",            "Knowledge & Reasoning", "Multistep Soft Reasoning — free-text murder mysteries and logic",                     _LLM_MM, unit="%"),
]

LLM_CODE = [
    _m("humaneval_score",      "HumanEval",       "Code Generation",       "164 Python function-completion problems, Pass@1",                                      _LLM_MM, unit="%", db_column="humaneval_score"),
    _m("humaneval_plus_score", "HumanEval+",      "Code Generation",       "HumanEval with significantly more test cases per problem",                             _LLM_MM, unit="%", db_column="humaneval_plus_score"),
    _m("mbpp_score",           "MBPP",            "Code Generation",       "Mostly Basic Python Programming — 974 introductory problems",                          _LLM_MM, unit="%", db_column="mbpp_score"),
    _m("swe_bench_score",      "SWE-bench",       "Code Generation",       "Real GitHub issues — understand, locate, and patch code",                              _LLM_MM, unit="%", db_column="swe_bench_score"),
    _m("pass_at_1",            "Pass@1",          "Code Generation",       "First-attempt correctness on code generation tasks",                                   _LLM_MM, unit="%", db_column="pass_at_1"),
    _m("aider_polyglot_score", "Aider Polyglot",  "Code Generation",       "Code editing across 12+ languages — targeted edits, not greenfield",                   _LLM_MM, unit="%"),
    _m("livecodebench_score",  "LiveCodeBench",   "Code Generation",       "Post-cutoff competitive programming — detects benchmark contamination",                _LLM_MM, unit="%"),
    _m("terminal_of_truth",    "Terminal of Truth","Code Generation",       "End-to-end agentic coding: terminal, filesystem, multi-step dev tasks",               _LLM_MM, unit="%"),
]

LLM_MATH = [
    _m("math_score",           "MATH",            "Mathematical Reasoning","Competition-level math — 5 difficulty levels, algebra through precalc",                _LLM_MM, unit="%", db_column="math_score"),
    _m("gsm8k_score",          "GSM8K",           "Mathematical Reasoning","Grade-school math word problems — floor test for arithmetic reasoning",               _LLM_MM, unit="%", db_column="gsm8k_score"),
    _m("mathvista_score",      "MathVista",       "Mathematical Reasoning","Math problems requiring visual understanding — charts, diagrams, geometry",           ("llm", "vision", "multimodal"), unit="%"),
    _m("minerva_score",        "Minerva/STEM",    "Mathematical Reasoning","University-level STEM problems — physics, chemistry, engineering",                    _LLM_MM, unit="%"),
]

LLM_INSTRUCTION = [
    _m("ifeval_prompt_score",  "IFEval (prompt)", "Instruction Following", "Prompt-level accuracy on verifiable formatting instructions",                          _LLM_MM, unit="%"),
    _m("ifeval_instr_score",   "IFEval (instr)",  "Instruction Following", "Instruction-level accuracy — % of individual constraints followed",                   _LLM_MM, unit="%"),
    _m("mt_bench_score",       "MT-Bench",        "Instruction Following", "Multi-turn conversation quality scored by GPT-4 judge",                               _LLM_MM, unit="/10", format=".2f", db_column="mt_bench_score"),
    _m("alpaca_eval_score",    "AlpacaEval 2.0",  "Instruction Following", "Length-Controlled win rate against GPT-4 Turbo",                                      _LLM_MM, unit="%", db_column="alpaca_eval_score"),
    _m("arena_hard_score",     "Arena-Hard",      "Instruction Following", "500 hard user queries — high-correlation proxy for Chatbot Arena ELO",                _LLM_MM, unit="%"),
    _m("chatbot_arena_elo",    "Chatbot Arena ELO","Instruction Following","LMSYS crowd-sourced human preference ELO rating",                                     _LLM_MM, unit="ELO", format=".0f", db_column="chatbot_arena_elo"),
]

LLM_LONG_CTX = [
    _m("niah_score",           "NIAH",            "Long Context",          "Needle-in-a-Haystack retrieval at various depths and lengths",                         _LLM_MM, unit="%"),
    _m("ruler_score",          "RULER",           "Long Context",          "Multi-hop QA, variable tracking, aggregation over long context",                       _LLM_MM, unit="%"),
    _m("infinitebench_score",  "InfiniteBench",   "Long Context",          "100K+ token tasks — novel reading, long-range code deps, dialogue",                   _LLM_MM, unit="%"),
    _m("effective_ctx_window", "Effective Context","Long Context",          "Actual context length where quality is maintained vs stated max",                     _LLM_MM, unit="tokens", format=".0f", higher_is_better=True),
]

LLM_FACTUALITY = [
    _m("hallucination_rate",   "Hallucination Rate","Factuality & Calibration","% fabricated claims — broken down by domain",                                     _LLM_MM, unit="%", higher_is_better=False, db_column="hallucination_rate"),
    _m("cot_consistency",      "CoT Consistency",   "Factuality & Calibration","Chain-of-thought self-consistency across multiple runs",                          _LLM_MM, unit="%", db_column="cot_consistency"),
    _m("calibration_ece",      "Calibration (ECE)", "Factuality & Calibration","Expected Calibration Error — confidence vs actual accuracy",                      _LLM_MM, unit="", format=".3f", higher_is_better=False),
    _m("sycophancy_rate",      "Sycophancy Rate",   "Factuality & Calibration","% of times model abandons correct answer when user challenges",                   _LLM_MM, unit="%", higher_is_better=False),
    _m("self_consistency",     "Self-Consistency",   "Factuality & Calibration","Answer variance on factual questions across multiple runs",                       _LLM_MM, unit="%"),
    _m("attribution_accuracy", "Attribution Accuracy","Factuality & Calibration","% of cited sources that exist and support the claim",                            _LLM_MM, unit="%"),
]

LLM_SAFETY = [
    _m("toxicity_score",       "Toxicity",         "Safety & Alignment",    "Probability/severity of toxic outputs (lower = safer)",                               _LLM_MM, unit="%", higher_is_better=False, db_column="toxicity_score"),
    _m("bias_score",           "Bias",             "Safety & Alignment",    "Fairness/bias metric across demographics (lower = fairer)",                           _LLM_MM, unit="%", higher_is_better=False, db_column="bias_score"),
    _m("refusal_accuracy",     "Refusal Accuracy", "Safety & Alignment",    "Correct refusal rate on harmful input (precision × recall)",                          _LLM_MM, unit="%", db_column="refusal_accuracy"),
    _m("jailbreak_resistance", "Jailbreak Resist.", "Safety & Alignment",    "Resistance across 20+ jailbreak categories",                                        _LLM_MM, unit="%"),
    _m("demographic_parity",   "Demographic Parity","Safety & Alignment",   "Quality equality regardless of implied user demographics",                           _LLM_MM, unit="%"),
]

LLM_THROUGHPUT = [
    _m("context_window",       "Context Window",   "LLM Throughput",        "Maximum context length in tokens",                                                   _LLM_MM, unit="tokens", format=".0f", db_column="context_window"),
    _m("ttft_ms",              "TTFT",             "LLM Throughput",        "Time to first token — critical for interactive UX",                                   _LLM_MM, unit="ms", higher_is_better=False, db_column="ttft_ms"),
    _m("tokens_per_sec",       "Tokens/sec",       "LLM Throughput",        "Sustained decode throughput",                                                        _LLM_MM, unit="tok/s", db_column="tokens_per_sec"),
    _m("total_tokens_eval",    "Tokens Evaluated", "LLM Throughput",        "Total tokens processed during evaluation",                                           _LLM_MM, unit="tokens", format=".0f", db_column="total_tokens_eval"),
    _m("cost_per_1k_tokens",   "Cost/1K Tokens",   "LLM Throughput",        "Dollar cost per 1,000 tokens",                                                      _LLM_MM, unit="$", format=".4f", higher_is_better=False, db_column="cost_per_1k_tokens"),
    _m("batch_throughput",     "Batch Throughput", "LLM Throughput",        "Tokens/sec when processing many requests in parallel",                                _LLM_MM, unit="tok/s"),
]

# ═══════════════════════════════════════════════════════════════════════
#  Part 2 · Vision Metrics
# ═══════════════════════════════════════════════════════════════════════

_VIS: tuple[ModelType, ...] = ("vision",)
_VIS_MM: tuple[ModelType, ...] = ("vision", "multimodal")

VISION_UNDERSTANDING = [
    _m("mmmu_score",           "MMMU",            "Visual Understanding",   "Multi-discipline multimodal understanding — college-level diagrams and charts",       _VIS_MM, unit="%"),
    _m("vqav2_score",          "VQAv2",           "Visual Understanding",   "Open-ended visual QA — object ID, counting, spatial relationships",                  _VIS_MM, unit="%"),
    _m("realworldqa_score",    "RealWorldQA",     "Visual Understanding",   "Practical real-world images — signs, maps, documents, interfaces",                   _VIS_MM, unit="%"),
    _m("ai2d_score",           "AI2D",            "Visual Understanding",   "Science diagram understanding — biology, physics, chemistry",                        _VIS_MM, unit="%"),
    _m("chartqa_score",        "ChartQA",         "Visual Understanding",   "Chart/graph data extraction, comparison, and trend analysis",                        _VIS_MM, unit="%"),
    _m("docvqa_score",         "DocVQA",          "Visual Understanding",   "Document understanding — text, tables, figures, layout reasoning",                   _VIS_MM, unit="%"),
    _m("textvqa_score",        "TextVQA",         "Visual Understanding",   "Reading text within images — OCR + comprehension",                                   _VIS_MM, unit="%"),
    _m("ocrbench_score",       "OCRBench",        "Visual Understanding",   "Character-level OCR accuracy across fonts, sizes, scripts",                          _VIS_MM, unit="%"),
    _m("blink_score",          "BLINK",           "Visual Understanding",   "Perception tasks humans find trivial — depth, spatial, forensics",                   _VIS_MM, unit="%"),
]

VISION_DETECTION = [
    _m("mAP50",               "mAP@0.5",         "Object Detection",       "Mean Average Precision at IoU=0.50",                                                  _VIS_MM, unit="%", db_column="mAP50"),
    _m("mAP50_95",            "mAP@.5:.95",      "Object Detection",       "Mean Average Precision averaged over IoU 0.50 to 0.95",                               _VIS_MM, unit="%", db_column="mAP50_95"),
    _m("mAP75",               "mAP@0.75",        "Object Detection",       "Mean Average Precision at IoU=0.75 — demands precise localization",                   _VIS_MM, unit="%"),
    _m("precision",           "Precision",        "Object Detection",       "True positives / (true positives + false positives)",                                 _VIS_MM, unit="%", db_column="precision"),
    _m("recall",              "Recall",           "Object Detection",       "True positives / (true positives + false negatives)",                                 _VIS_MM, unit="%", db_column="recall"),
    _m("f1_score",            "F1 Score",         "Object Detection",       "Harmonic mean of precision and recall",                                               _VIS_MM, unit="%", db_column="f1_score"),
    _m("per_class_ap",        "Per-Class AP",     "Object Detection",       "Average Precision broken down by object class",                                       _VIS_MM, unit="%", db_column="per_class_ap"),
    _m("false_positive_rate", "FP Rate",          "Object Detection",       "False positive detections per image",                                                 _VIS_MM, unit="%", higher_is_better=False, db_column="false_positive_rate"),
    _m("avg_detections",      "Avg Detections",   "Object Detection",       "Average detections per image",                                                        _VIS_MM, unit="", format=".1f", db_column="avg_detections"),
    _m("total_classes",       "Total Classes",    "Object Detection",       "Number of classes the model can detect",                                              _VIS_MM, unit="", format=".0f", db_column="total_classes"),
    _m("lvis_freq_ap",        "LVIS Frequent AP", "Object Detection",       "LVIS detection AP on frequent categories",                                            _VIS_MM, unit="%"),
    _m("lvis_common_ap",      "LVIS Common AP",   "Object Detection",       "LVIS detection AP on common categories",                                              _VIS_MM, unit="%"),
    _m("lvis_rare_ap",        "LVIS Rare AP",     "Object Detection",       "LVIS detection AP on rare/uncommon categories",                                       _VIS_MM, unit="%"),
    _m("open_vocab_det",      "Open-Vocab Det.",  "Object Detection",       "Detection of objects described in natural language outside training vocab",            _VIS_MM, unit="%"),
    _m("zero_shot_det",       "Zero-Shot Det.",   "Object Detection",       "Detection accuracy on never-trained object categories",                               _VIS_MM, unit="%"),
]

VISION_SEGMENTATION = [
    _m("mask_iou",            "Mask IoU",         "Segmentation",          "Segmentation mask intersection-over-union",                                            _VIS_MM, unit="%", db_column="mask_iou"),
    _m("miou_ade20k",         "mIoU (ADE20K)",    "Segmentation",          "Semantic segmentation mIoU on ADE20K — 150 categories",                                _VIS_MM, unit="%"),
    _m("miou_cityscapes",     "mIoU (Cityscapes)","Segmentation",          "mIoU on Cityscapes urban street scenes",                                               _VIS_MM, unit="%"),
    _m("instance_seg_ap",     "Instance Seg AP",  "Segmentation",          "Instance segmentation mask AP on COCO",                                                _VIS_MM, unit="%"),
    _m("panoptic_quality",    "Panoptic Quality", "Segmentation",          "PQ — combines Segmentation Quality and Recognition Quality",                           _VIS_MM, unit="%"),
    _m("sam_iou",             "SAM-style IoU",    "Segmentation",          "Interactive segmentation accuracy from point/box/text prompts",                        _VIS_MM, unit="%"),
]

VISION_HALLUCINATION = [
    _m("pope_accuracy",       "POPE Accuracy",    "Visual Hallucination",  "Object probing — correctly identifies absent vs present objects",                       _VIS_MM, unit="%"),
    _m("pope_f1",             "POPE F1",          "Visual Hallucination",  "Hallucination-specific F1 across random/popular/adversarial splits",                    _VIS_MM, unit="%"),
    _m("obj_hallucination_rate","Object Halluc.",  "Visual Hallucination",  "% of described objects that don't exist in the image",                                 _VIS_MM, unit="%", higher_is_better=False),
    _m("ocr_hallucination_rate","OCR Halluc.",     "Visual Hallucination",  "% of characters fabricated, misread, or altered",                                      _VIS_MM, unit="%", higher_is_better=False),
    _m("spatial_accuracy",    "Spatial Accuracy",  "Visual Hallucination",  "Accuracy on left/right/above/behind spatial relationship queries",                     _VIS_MM, unit="%"),
]

VISION_GENERATION = [
    _m("fid_score",           "FID",              "Image Generation",      "Fréchet Inception Distance — statistical distance to real images (lower = better)",    ("vision",), unit="", format=".1f", higher_is_better=False),
    _m("clip_score_img",      "CLIP Score",       "Image Generation",      "Text-image alignment — how well generated image matches prompt",                       ("vision",), unit="", format=".2f"),
    _m("inception_score",     "Inception Score",  "Image Generation",      "Quality × diversity of generated images",                                              ("vision",), unit="", format=".1f"),
    _m("artifact_rate_img",   "Artifact Rate",    "Image Generation",      "Extra fingers, melted text, impossible geometry per image",                             ("vision",), unit="%", higher_is_better=False),
    _m("text_render_accuracy","Text Render Acc.", "Image Generation",      "Character/word accuracy when generating text in images",                               ("vision",), unit="%"),
    _m("gen_consistency",     "Gen. Consistency",  "Image Generation",      "Style/quality consistency across different seeds for same prompt",                     ("vision",), unit="%"),
    _m("controllability",     "Controllability",   "Image Generation",      "Delta between controlled and uncontrolled generation quality",                         ("vision",), unit="%"),
]

VISION_PERFORMANCE = [
    _m("fps",                 "FPS",              "Vision Performance",    "Frames per second throughput",                                                          _VIS_MM, unit="fps", db_column="fps"),
    _m("confidence_calibration","Confidence Cal.", "Vision Performance",    "ECE — expected calibration error of confidence scores",                                _VIS_MM, unit="", format=".3f", higher_is_better=False, db_column="confidence_calibration"),
    _m("temporal_consistency", "Temporal Consist.","Vision Performance",    "Frame-to-frame detection consistency in video",                                        _VIS_MM, unit="%", db_column="temporal_consistency"),
    _m("model_size_mb",       "Model Size",       "Vision Performance",    "Model file size in megabytes",                                                         _VIS_MM, unit="MB", format=".1f", higher_is_better=False, db_column="model_size_mb"),
    _m("model_params",        "Parameters",       "Vision Performance",    "Total model parameter count",                                                          _VIS_MM, unit="", format=",d", higher_is_better=False, db_column="model_params"),
]

VISION_ACTION = [
    _m("action_accuracy",     "Action Accuracy",  "Action Recognition",    "Temporal action classification accuracy",                                              _VIS_MM, unit="%", db_column="action_accuracy"),
    _m("action_classes",      "Action Classes",   "Action Recognition",    "Number of action labels the model recognises",                                         _VIS_MM, unit="", format=".0f", db_column="action_classes"),
    _m("novel_detection_rate","Novel Detection",  "Action Recognition",    "Out-of-distribution / novel action detection rate",                                    _VIS_MM, unit="%", db_column="novel_detection_rate"),
    _m("kinetics700_score",   "Kinetics-700",     "Action Recognition",    "Human action classification — appearance-based actions",                               _VIS_MM, unit="%"),
    _m("sthsthv2_score",      "SthSth v2",        "Action Recognition",    "Temporal-dynamics action recognition — requires motion understanding",                 _VIS_MM, unit="%"),
]

# ═══════════════════════════════════════════════════════════════════════
#  Part 3 · Audio Metrics
# ═══════════════════════════════════════════════════════════════════════

_AUD: tuple[ModelType, ...] = ("audio",)
_AUD_MM: tuple[ModelType, ...] = ("audio", "multimodal")

AUDIO_ASR = [
    _m("wer",                 "WER",              "Speech Recognition",    "Word Error Rate — (sub+del+ins)/total reference words",                                _AUD_MM, unit="%", higher_is_better=False),
    _m("cer",                 "CER",              "Speech Recognition",    "Character Error Rate — better for CJK and proper nouns",                               _AUD_MM, unit="%", higher_is_better=False),
    _m("wer_noisy",           "WER (noisy)",      "Speech Recognition",    "WER at SNR 15dB — moderate noise conditions",                                         _AUD_MM, unit="%", higher_is_better=False),
    _m("accent_robustness",   "Accent Robustness","Speech Recognition",    "WER variance across 10+ accent groups (lower = fairer)",                               _AUD_MM, unit="%", higher_is_better=False),
    _m("code_switch_accuracy","Code-Switch Acc.", "Speech Recognition",    "Accuracy when speakers switch languages mid-sentence",                                _AUD_MM, unit="%"),
    _m("rtf",                 "Real-Time Factor", "Speech Recognition",    "Processing time / audio duration — <1 means faster than real-time",                    _AUD_MM, unit="×", format=".2f", higher_is_better=False),
    _m("diarization_der",     "Diarization DER",  "Speech Recognition",    "Diarization Error Rate — missed, false alarm, speaker confusion",                     _AUD_MM, unit="%", higher_is_better=False),
    _m("punctuation_acc",     "Punctuation Acc.", "Speech Recognition",    "Correct punctuation, capitalisation, and number formatting",                            _AUD_MM, unit="%"),
]

AUDIO_TTS = [
    _m("tts_mos",             "MOS",              "Speech Synthesis",      "Mean Opinion Score — human-rated naturalness (1-5)",                                   _AUD_MM, unit="/5", format=".2f"),
    _m("tts_mushra",          "MUSHRA",           "Speech Synthesis",      "Multi-Stimulus comparison against hidden natural reference",                            _AUD_MM, unit="/100", format=".0f"),
    _m("tts_intelligibility", "Intelligibility",  "Speech Synthesis",      "% of words correctly transcribed by listeners",                                        _AUD_MM, unit="%"),
    _m("tts_speaker_sim",     "Speaker Similarity","Speech Synthesis",     "Cosine similarity to target speaker embedding (voice cloning)",                        _AUD_MM, unit="", format=".3f"),
    _m("tts_latency",         "TTS Latency",      "Speech Synthesis",      "Time from text input to first audio output",                                           _AUD_MM, unit="ms", higher_is_better=False),
]

AUDIO_UNDERSTANDING = [
    _m("audio_event_acc",     "Audio Event Det.", "Audio Understanding",   "Non-speech event ID accuracy on AudioSet / ESC-50",                                    _AUD_MM, unit="%"),
    _m("music_genre_acc",     "Genre Accuracy",   "Audio Understanding",   "Music genre classification accuracy",                                                  _AUD_MM, unit="%"),
    _m("audio_qa_score",      "Audio QA",         "Audio Understanding",   "Answer accuracy given audio clip + question",                                          _AUD_MM, unit="%"),
    _m("emotion_recognition", "Emotion Recog.",   "Audio Understanding",   "Speaker emotion detection accuracy (neutral/happy/sad/angry/…)",                       _AUD_MM, unit="%"),
]

AUDIO_MUSIC_GEN = [
    _m("fad_score",           "FAD",              "Music Generation",      "Fréchet Audio Distance — statistical distance to real music (lower = better)",         ("audio",), unit="", format=".1f", higher_is_better=False),
    _m("clap_score",          "CLAP Score",       "Music Generation",      "Text-audio alignment of generated music to description",                               ("audio",), unit="", format=".2f"),
    _m("music_structure",     "Structural Coher.","Music Generation",      "Maintains harmonic, rhythmic, thematic coherence over duration",                       ("audio",), unit="/10", format=".1f"),
    _m("audio_artifact_rate", "Artifact Rate",    "Music Generation",      "Clicks, pops, timbre glitches per minute of generated audio",                          ("audio",), unit="/min", higher_is_better=False),
]

# ═══════════════════════════════════════════════════════════════════════
#  Part 4 · Video Metrics
# ═══════════════════════════════════════════════════════════════════════

_VID: tuple[ModelType, ...] = ("video",)
_VID_MM: tuple[ModelType, ...] = ("video", "multimodal")

VIDEO_UNDERSTANDING = [
    _m("videomme_score",      "VideoMME",         "Video Understanding",   "Multi-discipline video QA — short, medium, and long videos",                           _VID_MM, unit="%"),
    _m("activitynet_qa",      "ActivityNet-QA",   "Video Understanding",   "Open-ended video QA on actions and temporal sequences",                                _VID_MM, unit="%"),
    _m("temporal_reasoning",  "Temporal Reason.", "Video Understanding",   "Before/after, duration, sequence-of-events accuracy",                                  _VID_MM, unit="%"),
    _m("long_video_comp",     "Long-Video Comp.", "Video Understanding",   "QA accuracy on 30min+ videos — narrative and retrieval",                               _VID_MM, unit="%"),
    _m("video_caption_cider", "Video CIDEr",      "Video Understanding",   "Video captioning quality — CIDEr score",                                              _VID_MM, unit="", format=".1f"),
]

VIDEO_GENERATION = [
    _m("fvd_score",           "FVD",              "Video Generation",      "Fréchet Video Distance — per-frame + temporal consistency (lower = better)",           ("video",), unit="", format=".1f", higher_is_better=False),
    _m("temporal_smoothness", "Temporal Smooth.", "Video Generation",      "Frame-to-frame optical flow consistency and flicker detection",                        ("video",), unit="%"),
    _m("subject_consistency", "Subject Consist.", "Video Generation",      "Identity/appearance preservation across frames and cuts",                               ("video",), unit="%"),
    _m("physics_plausibility","Physics Plausib.", "Video Generation",      "Do objects obey gravity, momentum, collision, cloth physics?",                         ("video",), unit="%"),
    _m("motion_quality",      "Motion Quality",   "Video Generation",      "Motion smoothness, realism, speed consistency",                                        ("video",), unit="/5", format=".1f"),
    _m("vid_prompt_adherence","Prompt Adherence", "Video Generation",      "Generated video matches text description — objects, actions, style",                   ("video",), unit="%"),
    _m("gen_length_quality",  "Length vs Quality","Video Generation",      "Quality maintained at 1s, 5s, 15s, 30s, 1min+ duration",                               ("video",), unit="%"),
]

# ═══════════════════════════════════════════════════════════════════════
#  Part 5 · Multimodal / Cross-Modal
# ═══════════════════════════════════════════════════════════════════════

_MM: tuple[ModelType, ...] = ("multimodal",)

MULTIMODAL = [
    _m("muirbench_score",     "MuirBench",        "Cross-Modal Reasoning","Multi-image reasoning — compare, contrast, sequence, synthesise",                      _MM, unit="%"),
    _m("cross_modal_consist", "Cross-Modal Cons.","Cross-Modal Reasoning","Same info in different modalities → consistent answers?",                              _MM, unit="%"),
    _m("modality_pref_bias",  "Modality Bias",    "Cross-Modal Reasoning","When text and image conflict, which does the model trust?",                            _MM, unit="", format=".2f"),
    _m("cross_modal_recall1", "Cross-Ret R@1",    "Cross-Modal Reasoning","Text→image and image→text retrieval Recall@1",                                         _MM, unit="%"),
    _m("modality_degradation","Modality Degrad.", "Cross-Modal Reasoning","Performance drop when processing multiple modalities vs single",                       _MM, unit="%", higher_is_better=False),
]

# ═══════════════════════════════════════════════════════════════════════
#  Part 6 · Embeddings & Retrieval
# ═══════════════════════════════════════════════════════════════════════

_EMB: tuple[ModelType, ...] = ("embeddings",)

EMBEDDINGS = [
    _m("mteb_avg",            "MTEB Average",     "Embeddings",            "Massive Text Embedding Benchmark — 56 datasets, 8 tasks",                              _EMB, unit="%"),
    _m("beir_ndcg10",         "BEIR nDCG@10",     "Embeddings",            "Zero-shot retrieval quality across 18 diverse datasets",                               _EMB, unit="", format=".3f"),
    _m("sts_spearman",        "STS Spearman",     "Embeddings",            "Spearman correlation with human similarity judgments",                                 _EMB, unit="", format=".3f"),
    _m("cross_lingual_align", "Cross-Lingual",    "Embeddings",            "How well equivalent sentences in different languages cluster",                         _EMB, unit="%"),
    _m("linear_probe_acc",    "Linear Probe",     "Embeddings",            "Classification accuracy with a linear layer on frozen embeddings",                     _EMB, unit="%"),
    _m("zero_shot_imgnet",    "ZS ImageNet",      "Embeddings",            "Zero-shot image classification using text descriptions only",                          _EMB, unit="%"),
]

# ═══════════════════════════════════════════════════════════════════════
#  Part 7 · Agentic & Tool Use
# ═══════════════════════════════════════════════════════════════════════

_AGT: tuple[ModelType, ...] = ("agentic", "llm")

AGENTIC = [
    _m("tool_selection_acc",  "Tool Selection",   "Agentic & Tool Use",    "Correct tool(s) chosen given task and available tools",                                _AGT, unit="%"),
    _m("tool_call_correct",   "Tool Call Correct","Agentic & Tool Use",    "Correct parameters when the right tool is selected",                                   _AGT, unit="%"),
    _m("multi_tool_orch",     "Multi-Tool Orch.", "Agentic & Tool Use",    "Correct ordering, data passing, and error handling across tools",                      _AGT, unit="%"),
    _m("bfcl_score",          "BFCL",             "Agentic & Tool Use",    "Berkeley Function Calling Leaderboard — simple to nested calls",                       _AGT, unit="%"),
    _m("webarena_score",      "WebArena",         "Agentic & Tool Use",    "End-to-end web browsing task completion",                                              _AGT, unit="%"),
    _m("osworld_score",       "OSWorld",          "Agentic & Tool Use",    "Desktop computer-use task completion",                                                 _AGT, unit="%"),
    _m("recovery_from_errors","Error Recovery",   "Agentic & Tool Use",    "Detect failure → diagnose → recover → try alternative",                                _AGT, unit="%"),
    _m("human_intervention",  "Human Interv. Rate","Agentic & Tool Use",   "How often does a human need to step in? (lower = better)",                             _AGT, unit="%", higher_is_better=False),
]

# ═══════════════════════════════════════════════════════════════════════
#  Part 8 · Efficiency, Cost & Deployment
# ═══════════════════════════════════════════════════════════════════════

_ALL: tuple[ModelType, ...] = ("llm", "vision", "audio", "video", "multimodal", "embeddings", "agentic")

EFFICIENCY = [
    _m("avg_inference_ms",    "Avg Inference",    "Efficiency & Cost",     "Average end-to-end inference latency",                                                 _ALL, unit="ms", higher_is_better=False, db_column="avg_inference_ms"),
    _m("p95_latency_ms",      "P95 Latency",      "Efficiency & Cost",     "95th percentile latency — tail performance",                                          _ALL, unit="ms", higher_is_better=False),
    _m("p99_latency_ms",      "P99 Latency",      "Efficiency & Cost",     "99th percentile latency — worst-case user experience",                                _ALL, unit="ms", higher_is_better=False),
    _m("quality_per_dollar",  "Quality/$",        "Efficiency & Cost",     "Primary benchmark score divided by cost per 1M tokens/images",                         _ALL, unit="", format=".1f"),
    _m("effective_cost",      "Effective Cost",   "Efficiency & Cost",     "Actual cost including retries due to first-attempt failures",                           _ALL, unit="$", format=".4f", higher_is_better=False),
    _m("throughput_under_load","Throughput @ Load","Efficiency & Cost",    "Performance at 100/1000 concurrent requests",                                          _ALL, unit="req/s"),
]

# ═══════════════════════════════════════════════════════════════════════
#  Part 9 · Real-World ("Vibes") Metrics
# ═══════════════════════════════════════════════════════════════════════

REAL_WORLD = [
    _m("output_edit_distance","Output Edit Dist.","Real-World",            "How much you modify the model's output before using it",                                _ALL, unit="%", higher_is_better=False),
    _m("ctx_reexplain_freq",  "Re-Explain Freq.", "Real-World",            "How often you re-explain something already in context",                                _ALL, unit="%", higher_is_better=False),
    _m("time_to_usable",      "Time to Usable",   "Real-World",            "Generation + review + edit + retry = production-ready time",                           _ALL, unit="s", higher_is_better=False),
    _m("task_completion_rate", "Task Completion", "Real-World",            "% of your actual tasks completed without major intervention",                           _ALL, unit="%"),
    _m("trust_calibration",   "Trust Calibration","Real-World",            "After 100+ interactions, is your trust increasing or decreasing?",                     _ALL, unit="/5", format=".1f"),
    _m("failure_predictability","Failure Predict.","Real-World",           "Can you predict when the model will fail? (higher = more predictable)",                 _ALL, unit="%"),
]

# ═══════════════════════════════════════════════════════════════════════
#  Aggregated catalog
# ═══════════════════════════════════════════════════════════════════════

ALL_METRICS: list[MetricDef] = (
    LLM_KNOWLEDGE + LLM_CODE + LLM_MATH + LLM_INSTRUCTION
    + LLM_LONG_CTX + LLM_FACTUALITY + LLM_SAFETY + LLM_THROUGHPUT
    + VISION_UNDERSTANDING + VISION_DETECTION + VISION_SEGMENTATION
    + VISION_HALLUCINATION + VISION_GENERATION + VISION_PERFORMANCE
    + VISION_ACTION
    + AUDIO_ASR + AUDIO_TTS + AUDIO_UNDERSTANDING + AUDIO_MUSIC_GEN
    + VIDEO_UNDERSTANDING + VIDEO_GENERATION
    + MULTIMODAL
    + EMBEDDINGS
    + AGENTIC
    + EFFICIENCY
    + REAL_WORLD
)

# Quick look-ups
METRICS_BY_KEY: dict[str, MetricDef] = {m.key: m for m in ALL_METRICS}

CATEGORIES: list[str] = list(dict.fromkeys(m.category for m in ALL_METRICS))

# All unique model types present in the catalog
MODEL_TYPES: list[str] = sorted({t for m in ALL_METRICS for t in m.model_types})


def metrics_for_type(model_type: str) -> list[MetricDef]:
    """Return only the metrics relevant to *model_type* by default."""
    return [m for m in ALL_METRICS if model_type in m.model_types]


def catalog_json(model_type: str | None = None) -> list[dict]:
    """Serialise the catalog (or a subset) to JSON-safe dicts."""
    pool = metrics_for_type(model_type) if model_type else ALL_METRICS
    return [
        {
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
        for m in pool
    ]
