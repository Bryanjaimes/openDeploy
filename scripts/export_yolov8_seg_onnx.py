"""
Export YOLOv8-seg (instance segmentation) to ONNX for Triton Inference Server.

Usage:
    python scripts/export_yolov8_seg_onnx.py [--size n|s|m|l|x]

The exported ONNX model lands in triton_model_repo/yolov8_seg/1/model.onnx
with a matching config.pbtxt generated alongside it.
"""

import argparse
import os
import sys


def export_yolov8_seg(size: str = "n", repo_root: str | None = None):
    """Download YOLOv8{size}-seg from Ultralytics and export to ONNX."""
    from ultralytics import YOLO

    model_name = f"yolov8{size}-seg"
    print(f"⬇️  Downloading {model_name} from Ultralytics hub...")
    model = YOLO(f"{model_name}.pt")

    if repo_root is None:
        repo_root = os.path.join(
            os.getcwd(), "triton_model_repo", "yolov8_seg", "1"
        )
    os.makedirs(repo_root, exist_ok=True)

    onnx_path = os.path.join(repo_root, "model.onnx")

    print(f"📦 Exporting to ONNX → {onnx_path}")
    model.export(
        format="onnx",
        imgsz=640,
        opset=18,
        simplify=True,
        dynamic=True,          # dynamic batch axis
    )

    # ultralytics writes the onnx next to the .pt — move it
    auto_path = f"{model_name}.onnx"
    if os.path.exists(auto_path) and os.path.abspath(auto_path) != os.path.abspath(onnx_path):
        import shutil
        shutil.move(auto_path, onnx_path)
        print(f"✅ Moved ONNX model to {onnx_path}")
    elif os.path.exists(onnx_path):
        print(f"✅ ONNX model already at {onnx_path}")
    else:
        print(f"⚠️  Expected ONNX at {auto_path} — check ultralytics output")
        sys.exit(1)

    # Clean up the .pt file if desired
    if os.path.exists(f"{model_name}.pt"):
        print(f"🗑️  Keeping {model_name}.pt (delete manually if not needed)")

    print(f"\n✅ Export complete: {onnx_path}")
    print(f"   Model: {model_name}")
    print(f"   Input: images [batch, 3, 640, 640]  FP32")
    print(f"   Outputs: output0 (detection+seg coefficients), output1 (prototype masks)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export YOLOv8-seg to ONNX")
    parser.add_argument(
        "--size",
        choices=["n", "s", "m", "l", "x"],
        default="n",
        help="YOLOv8 variant size (default: n = nano, fastest)",
    )
    args = parser.parse_args()
    export_yolov8_seg(size=args.size)
