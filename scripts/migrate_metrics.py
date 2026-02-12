"""One-shot DB migration: add new metric columns to model_evolution."""
import sqlite3, os

db_path = os.path.join(os.path.dirname(__file__), "..", "opendeploy.db")
db = sqlite3.connect(db_path)
cur = db.cursor()

cur.execute("PRAGMA table_info(model_evolution)")
existing = {row[1] for row in cur.fetchall()}
print(f"Existing columns: {len(existing)}")

NEW_COLS = [
    ("model_type", "TEXT", "'vision'"),
    ("model_size_mb", "REAL", None),
    ("model_params", "INTEGER", None),
    ("num_eval_samples", "INTEGER", None),
    ("per_class_ap", "TEXT", None),
    ("mask_iou", "REAL", None),
    ("fps", "REAL", None),
    ("false_positive_rate", "REAL", None),
    ("confidence_calibration", "REAL", None),
    ("temporal_consistency", "REAL", None),
    ("mmlu_score", "REAL", None),
    ("mmlu_pro_score", "REAL", None),
    ("gpqa_score", "REAL", None),
    ("arc_agi_score", "REAL", None),
    ("hellaswag_score", "REAL", None),
    ("bigbench_hard_score", "REAL", None),
    ("truthfulqa_score", "REAL", None),
    ("livebench_score", "REAL", None),
    ("humaneval_score", "REAL", None),
    ("humaneval_plus_score", "REAL", None),
    ("mbpp_score", "REAL", None),
    ("swe_bench_score", "REAL", None),
    ("pass_at_1", "REAL", None),
    ("math_score", "REAL", None),
    ("gsm8k_score", "REAL", None),
    ("chatbot_arena_elo", "REAL", None),
    ("mt_bench_score", "REAL", None),
    ("alpaca_eval_score", "REAL", None),
    ("hallucination_rate", "REAL", None),
    ("cot_consistency", "REAL", None),
    ("toxicity_score", "REAL", None),
    ("bias_score", "REAL", None),
    ("refusal_accuracy", "REAL", None),
    ("context_window", "INTEGER", None),
    ("ttft_ms", "REAL", None),
    ("tokens_per_sec", "REAL", None),
    ("total_tokens_eval", "INTEGER", None),
    ("cost_per_1k_tokens", "REAL", None),
]

added = 0
for name, typ, default in NEW_COLS:
    if name not in existing:
        default_clause = f" DEFAULT {default}" if default else ""
        sql = f"ALTER TABLE model_evolution ADD COLUMN {name} {typ}{default_clause}"
        cur.execute(sql)
        added += 1
        print(f"  + {name} ({typ})")

cur.execute("UPDATE model_evolution SET model_type = 'vision' WHERE model_type IS NULL")
db.commit()
db.close()
print(f"\nAdded {added} new columns. Migration complete.")
