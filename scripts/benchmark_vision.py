"""
Benchmark the YOLOv8-seg model and log results to the evolution tracker.

Usage:
    python scripts/benchmark_vision.py [--images-dir path] [--version V0] [--tag "Baseline"] [--description "..."]

Runs the model against a set of test images, computes detection metrics,
and records the result as a ModelEvolution entry in the database.
"""

import argparse
import asyncio
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image
import numpy as np

from backend.database import SessionLocal, ModelEvolution, init_db
from models.yolov8_seg import YOLOv8SegModel, COCO_NAMES

logger = logging.getLogger(__name__)


def collect_test_images(images_dir: str | None) -> list[tuple[str, bytes]]:
    """Gather test images. Falls back to built-in ultralytics assets."""
    images: list[tuple[str, bytes]] = []

    if images_dir and os.path.isdir(images_dir):
        for p in sorted(Path(images_dir).glob("*")):
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                images.append((p.name, p.read_bytes()))
        if images:
            return images

    # Fallback: ultralytics sample images
    try:
        import ultralytics
        assets = Path(ultralytics.__file__).parent / "assets"
        for p in sorted(assets.glob("*.jpg")):
            images.append((p.name, p.read_bytes()))
    except ImportError:
        pass

    # Fallback: generate synthetic test images
    if not images:
        print("No test images found — generating synthetic test set")
        for i in range(5):
            arr = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            buf = io.BytesIO()
            Image.fromarray(arr).save(buf, format="JPEG")
            images.append((f"synthetic_{i}.jpg", buf.getvalue()))

    return images


def run_benchmark(
    model: YOLOv8SegModel,
    images: list[tuple[str, bytes]],
) -> dict:
    """Run model on all images and compute aggregate metrics."""
    results = []
    total_infer_ms = 0.0
    total_detections = 0
    all_classes_seen: set[int] = set()
    per_class_counts: dict[int, int] = {}
    confidence_sum = 0.0
    confidence_count = 0

    for name, img_bytes in images:
        result = asyncio.run(model.predict(img_bytes))
        results.append({"image": name, **result})

        if "detections" in result:
            dets = result["detections"]
            total_detections += len(dets)
            for d in dets:
                cid = d["class_id"]
                all_classes_seen.add(cid)
                per_class_counts[cid] = per_class_counts.get(cid, 0) + 1
                confidence_sum += d["confidence"]
                confidence_count += 1

        if "inference_ms" in result:
            total_infer_ms += result["inference_ms"]

    num_images = len(images)
    avg_infer = total_infer_ms / num_images if num_images else 0
    avg_dets = total_detections / num_images if num_images else 0
    avg_conf = confidence_sum / confidence_count if confidence_count else 0

    # Class distribution (top classes by frequency)
    class_dist = sorted(per_class_counts.items(), key=lambda x: x[1], reverse=True)
    class_summary = [
        {"class_id": cid, "class_name": COCO_NAMES[cid] if cid < len(COCO_NAMES) else f"class_{cid}", "count": cnt}
        for cid, cnt in class_dist[:20]
    ]

    return {
        "num_images": num_images,
        "total_detections": total_detections,
        "avg_detections_per_image": round(avg_dets, 2),
        "avg_inference_ms": round(avg_infer, 2),
        "avg_confidence": round(avg_conf, 4),
        "unique_classes_detected": len(all_classes_seen),
        "total_classes_available": len(COCO_NAMES),
        "class_distribution": class_summary,
        "per_image_results": results,
    }


def log_evolution(
    version: str,
    iteration: int,
    tag: str,
    description: str,
    model_arch: str,
    benchmark: dict,
    changes: list[str] | None = None,
    notes: str | None = None,
) -> int:
    """Write a ModelEvolution row to the database. Returns the row ID."""
    init_db()
    db = SessionLocal()
    try:
        entry = ModelEvolution(
            version=version,
            iteration=iteration,
            tag=tag,
            description=description,
            changes=changes or [],
            model_arch=model_arch,
            model_weights=f"triton_model_repo/yolov8_seg/1/model.onnx",
            benchmark_dataset="ultralytics sample assets" if not changes else None,
            num_eval_images=benchmark["num_images"],
            avg_inference_ms=benchmark["avg_inference_ms"],
            avg_detections=benchmark["avg_detections_per_image"],
            total_classes=benchmark["total_classes_available"],
            target_classes=[c["class_name"] for c in benchmark["class_distribution"][:10]],
            precision=benchmark["avg_confidence"],  # approximate until proper mAP eval
            status="completed",
            notes=notes,
            metrics_raw=benchmark,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        print(f"\n✅ Logged evolution entry ID={entry.id}: {version} / {tag}")
        return entry.id
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Benchmark vision model")
    parser.add_argument("--images-dir", type=str, default=None, help="Directory of test images")
    parser.add_argument("--version", type=str, default="V0", help="Version label (V0-V7)")
    parser.add_argument("--iteration", type=int, default=0, help="Iteration number within version")
    parser.add_argument("--tag", type=str, default="Baseline", help="Short tag for this entry")
    parser.add_argument("--description", type=str, default=None, help="What was done/changed")
    parser.add_argument("--notes", type=str, default=None, help="Extra notes")
    args = parser.parse_args()

    if not args.description:
        args.description = f"{args.version} {args.tag} — initial benchmark"

    print(f"🔍 Benchmarking YOLOv8-seg ({args.version} / {args.tag})")
    print("=" * 60)

    # Load model
    model = YOLOv8SegModel()
    model.load()
    print(f"Model loaded: {model.name} v{model.version}")

    # Collect images
    images = collect_test_images(args.images_dir)
    print(f"Test images: {len(images)}")

    # Run benchmark
    print("Running inference...")
    benchmark = run_benchmark(model, images)

    # Print summary
    print(f"\n{'─' * 40}")
    print(f"  Images evaluated:     {benchmark['num_images']}")
    print(f"  Total detections:     {benchmark['total_detections']}")
    print(f"  Avg detections/image: {benchmark['avg_detections_per_image']}")
    print(f"  Avg inference (ms):   {benchmark['avg_inference_ms']}")
    print(f"  Avg confidence:       {benchmark['avg_confidence']:.1%}")
    print(f"  Unique classes seen:  {benchmark['unique_classes_detected']}")
    print(f"  Top classes:")
    for c in benchmark["class_distribution"][:10]:
        print(f"    {c['class_name']:20s} × {c['count']}")
    print(f"{'─' * 40}")

    # Log to DB
    entry_id = log_evolution(
        version=args.version,
        iteration=args.iteration,
        tag=args.tag,
        description=args.description,
        model_arch="yolov8n-seg",
        benchmark=benchmark,
        notes=args.notes,
    )

    # Also save raw JSON
    out_path = os.path.join(os.path.dirname(__file__), "..", "benchmark_results.json")
    existing = []
    if os.path.exists(out_path):
        with open(out_path) as f:
            existing = json.load(f)
    existing.append({
        "id": entry_id,
        "version": args.version,
        "iteration": args.iteration,
        "tag": args.tag,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        **{k: v for k, v in benchmark.items() if k != "per_image_results"},
    })
    with open(out_path, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"📄 Raw results saved to {out_path}")


if __name__ == "__main__":
    main()
