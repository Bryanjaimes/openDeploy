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
    per_class_conf_sum: dict[int, float] = {}
    confidence_sum = 0.0
    confidence_count = 0
    all_confidences: list[float] = []
    all_mask_areas: list[int] = []
    infer_times: list[float] = []

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
                per_class_conf_sum[cid] = per_class_conf_sum.get(cid, 0.0) + d["confidence"]
                confidence_sum += d["confidence"]
                confidence_count += 1
                all_confidences.append(d["confidence"])
                all_mask_areas.append(d.get("mask_area_px", 0))

        if "inference_ms" in result:
            total_infer_ms += result["inference_ms"]
            infer_times.append(result["inference_ms"])

    num_images = len(images)
    avg_infer = total_infer_ms / num_images if num_images else 0
    avg_dets = total_detections / num_images if num_images else 0
    avg_conf = confidence_sum / confidence_count if confidence_count else 0
    fps = 1000.0 / avg_infer if avg_infer > 0 else 0.0

    # Confidence distribution
    if all_confidences:
        conf_arr = np.array(all_confidences)
        conf_percentiles = {
            "p10": float(np.percentile(conf_arr, 10)),
            "p25": float(np.percentile(conf_arr, 25)),
            "p50": float(np.percentile(conf_arr, 50)),
            "p75": float(np.percentile(conf_arr, 75)),
            "p90": float(np.percentile(conf_arr, 90)),
            "std": float(np.std(conf_arr)),
            "min": float(conf_arr.min()),
            "max": float(conf_arr.max()),
        }
    else:
        conf_percentiles = {}

    # Inference time distribution
    if infer_times:
        infer_arr = np.array(infer_times)
        infer_percentiles = {
            "p50": float(np.percentile(infer_arr, 50)),
            "p95": float(np.percentile(infer_arr, 95)),
            "p99": float(np.percentile(infer_arr, 99)),
            "std": float(np.std(infer_arr)),
        }
    else:
        infer_percentiles = {}

    # Per-class average confidence (used as per_class_ap proxy)
    per_class_ap: dict[str, float] = {}
    for cid in sorted(all_classes_seen):
        cls_name = COCO_NAMES[cid] if cid < len(COCO_NAMES) else f"class_{cid}"
        per_class_ap[cls_name] = round(
            per_class_conf_sum[cid] / per_class_counts[cid], 4
        )

    # Average mask area
    avg_mask_area = float(np.mean(all_mask_areas)) if all_mask_areas else 0.0

    # Class coverage ratio
    class_coverage = len(all_classes_seen) / len(COCO_NAMES)

    # Quality heuristic (same as sweep)
    import math
    quality_score = avg_conf * math.sqrt(class_coverage) * math.log2(1 + avg_dets)

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
        "class_coverage": round(class_coverage, 4),
        "fps": round(fps, 1),
        "quality_score": round(quality_score, 4),
        "conf_percentiles": conf_percentiles,
        "infer_percentiles": infer_percentiles,
        "per_class_ap": per_class_ap,
        "avg_mask_area_px": round(avg_mask_area, 1),
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
    model_weights: str = "triton_model_repo/yolov8_seg/1/model.onnx",
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45,
) -> int:
    """Write a ModelEvolution row to the database. Returns the row ID."""
    init_db()
    db = SessionLocal()
    try:
        # Compute F1 proxy: harmonic mean of confidence (precision proxy) and class_coverage (recall proxy)
        prec = benchmark["avg_confidence"]
        rec = benchmark.get("class_coverage", 0.0)
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        entry = ModelEvolution(
            version=version,
            iteration=iteration,
            tag=tag,
            description=description,
            changes=changes or [],
            model_arch=model_arch,
            model_weights=model_weights,
            benchmark_dataset="ultralytics sample assets",
            num_eval_images=benchmark["num_images"],
            avg_inference_ms=benchmark["avg_inference_ms"],
            avg_detections=benchmark["avg_detections_per_image"],
            total_classes=benchmark["total_classes_available"],
            target_classes=[c["class_name"] for c in benchmark["class_distribution"][:10]],
            precision=benchmark["avg_confidence"],
            recall=round(rec, 4),
            f1_score=round(f1, 4),
            fps=benchmark.get("fps"),
            per_class_ap=benchmark.get("per_class_ap"),
            status="completed",
            notes=notes or f"conf={conf_threshold}, iou={iou_threshold}",
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
    parser.add_argument("--conf-threshold", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--iou-threshold", type=float, default=0.45, help="IoU NMS threshold")
    parser.add_argument("--model-arch", type=str, default="yolov8n-seg", help="Model architecture label")
    parser.add_argument("--onnx-path", type=str, default=None, help="Path to ONNX model file")
    parser.add_argument("--changes", type=str, nargs="*", default=None, help="List of changes made")
    args = parser.parse_args()

    if not args.description:
        args.description = f"{args.version} {args.tag} — initial benchmark"

    print(f"🔍 Benchmarking YOLOv8-seg ({args.version} / {args.tag})")
    print(f"   conf_threshold={args.conf_threshold}  iou_threshold={args.iou_threshold}")
    print("=" * 60)

    # Load model with configured thresholds
    model = YOLOv8SegModel(
        conf_threshold=args.conf_threshold,
        iou_threshold=args.iou_threshold,
        onnx_path=args.onnx_path,
    )
    model.load()
    print(f"Model loaded: {model.name} v{model.version}")

    # Collect images
    images = collect_test_images(args.images_dir)
    print(f"Test images: {len(images)}")

    # Run benchmark
    print("Running inference...")
    benchmark = run_benchmark(model, images)

    # Print summary
    print(f"\n{'─' * 50}")
    print(f"  Images evaluated:     {benchmark['num_images']}")
    print(f"  Total detections:     {benchmark['total_detections']}")
    print(f"  Avg detections/image: {benchmark['avg_detections_per_image']}")
    print(f"  Avg inference (ms):   {benchmark['avg_inference_ms']}")
    print(f"  FPS:                  {benchmark['fps']}")
    print(f"  Avg confidence:       {benchmark['avg_confidence']:.1%}")
    print(f"  Unique classes seen:  {benchmark['unique_classes_detected']}")
    print(f"  Class coverage:       {benchmark['class_coverage']:.1%}")
    print(f"  Quality score:        {benchmark['quality_score']}")
    if benchmark.get("conf_percentiles"):
        cp = benchmark["conf_percentiles"]
        print(f"  Conf distribution:    P10={cp['p10']:.3f}  P50={cp['p50']:.3f}  P90={cp['p90']:.3f}")
    print(f"  Top classes:")
    for c in benchmark["class_distribution"][:10]:
        ap = benchmark.get("per_class_ap", {}).get(c["class_name"], 0)
        print(f"    {c['class_name']:20s} × {c['count']:3d}  (avg_conf={ap:.3f})")
    print(f"{'─' * 50}")

    # Determine model weights path
    model_weights = args.onnx_path or "triton_model_repo/yolov8_seg/1/model.onnx"

    # Log to DB
    entry_id = log_evolution(
        version=args.version,
        iteration=args.iteration,
        tag=args.tag,
        description=args.description,
        model_arch=args.model_arch,
        benchmark=benchmark,
        notes=args.notes,
        changes=args.changes,
        model_weights=model_weights,
        conf_threshold=args.conf_threshold,
        iou_threshold=args.iou_threshold,
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
