"""
Threshold sweep for YOLOv8-seg — finds optimal conf_threshold and iou_threshold.

Usage:
    python scripts/threshold_sweep.py [--images-dir path]

Without ground-truth annotations we use a quality heuristic:
    Q = avg_confidence × sqrt(unique_classes / total_classes) × log2(1 + detections_per_image)

This balances high-confidence detections (precision proxy), class coverage
(recall proxy), and useful detection density.  The sweep tests all combos
and reports the top configurations.
"""

import argparse
import asyncio
import io
import itertools
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.yolov8_seg import YOLOv8SegModel, COCO_NAMES

# ── Sweep grid ──────────────────────────────────────────────────────
CONF_THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60]
IOU_THRESHOLDS = [0.30, 0.40, 0.45, 0.50, 0.60, 0.70]


def collect_test_images(images_dir: str | None) -> list[tuple[str, bytes]]:
    images: list[tuple[str, bytes]] = []
    if images_dir and os.path.isdir(images_dir):
        for p in sorted(Path(images_dir).glob("*")):
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                images.append((p.name, p.read_bytes()))
        if images:
            return images

    try:
        import ultralytics
        assets = Path(ultralytics.__file__).parent / "assets"
        for p in sorted(assets.glob("*.jpg")):
            images.append((p.name, p.read_bytes()))
    except ImportError:
        pass

    if not images:
        print("No test images found — generating synthetic test set")
        for i in range(5):
            arr = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            buf = io.BytesIO()
            Image.fromarray(arr).save(buf, format="JPEG")
            images.append((f"synthetic_{i}.jpg", buf.getvalue()))
    return images


def evaluate_config(
    images: list[tuple[str, bytes]],
    conf_threshold: float,
    iou_threshold: float,
) -> dict:
    """Run model with specific thresholds and compute quality metrics."""
    model = YOLOv8SegModel(
        conf_threshold=conf_threshold,
        iou_threshold=iou_threshold,
    )
    model.load()

    total_dets = 0
    total_infer_ms = 0.0
    classes_seen: set[int] = set()
    confidences: list[float] = []
    mask_areas: list[int] = []
    per_class_counts: dict[int, int] = {}

    for _name, img_bytes in images:
        result = asyncio.run(model.predict(img_bytes))
        if "detections" in result:
            dets = result["detections"]
            total_dets += len(dets)
            for d in dets:
                cid = d["class_id"]
                classes_seen.add(cid)
                per_class_counts[cid] = per_class_counts.get(cid, 0) + 1
                confidences.append(d["confidence"])
                mask_areas.append(d.get("mask_area_px", 0))
        if "inference_ms" in result:
            total_infer_ms += result["inference_ms"]

    n = len(images)
    avg_conf = float(np.mean(confidences)) if confidences else 0.0
    avg_infer = total_infer_ms / n if n else 0.0
    dets_per_image = total_dets / n if n else 0.0
    class_coverage = len(classes_seen) / len(COCO_NAMES)
    fps = 1000.0 / avg_infer if avg_infer > 0 else 0.0

    # Confidence distribution
    if confidences:
        conf_arr = np.array(confidences)
        conf_p10 = float(np.percentile(conf_arr, 10))
        conf_p25 = float(np.percentile(conf_arr, 25))
        conf_p50 = float(np.percentile(conf_arr, 50))
        conf_p75 = float(np.percentile(conf_arr, 75))
        conf_p90 = float(np.percentile(conf_arr, 90))
        conf_std = float(np.std(conf_arr))
    else:
        conf_p10 = conf_p25 = conf_p50 = conf_p75 = conf_p90 = conf_std = 0.0

    # Average mask area
    avg_mask_area = float(np.mean(mask_areas)) if mask_areas else 0.0

    # Quality heuristic: balances confidence, class coverage, detection density
    import math
    quality = avg_conf * math.sqrt(class_coverage) * math.log2(1 + dets_per_image)

    return {
        "conf_threshold": conf_threshold,
        "iou_threshold": iou_threshold,
        "total_detections": total_dets,
        "dets_per_image": round(dets_per_image, 2),
        "avg_confidence": round(avg_conf, 4),
        "conf_std": round(conf_std, 4),
        "conf_p10": round(conf_p10, 4),
        "conf_p25": round(conf_p25, 4),
        "conf_p50": round(conf_p50, 4),
        "conf_p75": round(conf_p75, 4),
        "conf_p90": round(conf_p90, 4),
        "unique_classes": len(classes_seen),
        "class_coverage": round(class_coverage, 4),
        "avg_inference_ms": round(avg_infer, 2),
        "fps": round(fps, 1),
        "avg_mask_area_px": round(avg_mask_area, 1),
        "quality_score": round(quality, 4),
        "per_class_counts": {
            COCO_NAMES[k] if k < len(COCO_NAMES) else f"class_{k}": v
            for k, v in sorted(per_class_counts.items(), key=lambda x: -x[1])
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Threshold sweep for YOLOv8-seg")
    parser.add_argument("--images-dir", type=str, default=None)
    parser.add_argument("--top", type=int, default=10, help="Show top N configs")
    args = parser.parse_args()

    images = collect_test_images(args.images_dir)
    print(f"Test images: {len(images)}")

    combos = list(itertools.product(CONF_THRESHOLDS, IOU_THRESHOLDS))
    print(f"Testing {len(combos)} threshold combinations...\n")

    results = []
    for i, (conf, iou) in enumerate(combos, 1):
        print(f"  [{i:2d}/{len(combos)}] conf={conf:.2f}  iou={iou:.2f}", end="  →  ", flush=True)
        r = evaluate_config(images, conf, iou)
        print(
            f"dets={r['total_detections']:3d}  avg_conf={r['avg_confidence']:.3f}  "
            f"classes={r['unique_classes']:2d}  Q={r['quality_score']:.4f}"
        )
        results.append(r)

    # Sort by quality score descending
    results.sort(key=lambda r: r["quality_score"], reverse=True)

    print(f"\n{'═' * 80}")
    print(f"  TOP {args.top} CONFIGURATIONS (by quality score)")
    print(f"{'═' * 80}")
    print(f"  {'Rank':<5} {'Conf':>5} {'IoU':>5} {'Dets':>5} {'AvgConf':>8} {'Classes':>8} {'FPS':>6} {'Quality':>8}")
    print(f"  {'─' * 5} {'─' * 5} {'─' * 5} {'─' * 5} {'─' * 8} {'─' * 8} {'─' * 6} {'─' * 8}")
    for rank, r in enumerate(results[:args.top], 1):
        print(
            f"  {rank:<5} {r['conf_threshold']:>5.2f} {r['iou_threshold']:>5.2f} "
            f"{r['total_detections']:>5} {r['avg_confidence']:>8.4f} "
            f"{r['unique_classes']:>8} {r['fps']:>6.1f} {r['quality_score']:>8.4f}"
        )

    best = results[0]
    print(f"\n🏆 OPTIMAL: conf={best['conf_threshold']:.2f}  iou={best['iou_threshold']:.2f}")
    print(f"   Quality Score: {best['quality_score']:.4f}")
    print(f"   Avg Confidence: {best['avg_confidence']:.1%}")
    print(f"   Detections/Image: {best['dets_per_image']}")
    print(f"   Unique Classes: {best['unique_classes']}")
    print(f"   FPS: {best['fps']:.1f}")

    # Compare to baseline (conf=0.25, iou=0.45)
    baseline = next(
        (r for r in results if r["conf_threshold"] == 0.25 and r["iou_threshold"] == 0.45),
        None,
    )
    if baseline and baseline != best:
        print(f"\n📊 vs Baseline (conf=0.25, iou=0.45):")
        q_delta = ((best["quality_score"] - baseline["quality_score"]) / baseline["quality_score"]) * 100
        print(f"   Quality:     {baseline['quality_score']:.4f} → {best['quality_score']:.4f}  ({q_delta:+.1f}%)")
        c_delta = best["avg_confidence"] - baseline["avg_confidence"]
        print(f"   Confidence:  {baseline['avg_confidence']:.4f} → {best['avg_confidence']:.4f}  ({c_delta:+.4f})")
        d_delta = best["dets_per_image"] - baseline["dets_per_image"]
        print(f"   Dets/Image:  {baseline['dets_per_image']} → {best['dets_per_image']}  ({d_delta:+.1f})")

    # Save full results
    out_path = os.path.join(os.path.dirname(__file__), "..", "sweep_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n📄 Full results saved to {out_path}")


if __name__ == "__main__":
    main()
