"""
Export YOLOv8-pose (keypoint estimation) to ONNX for Triton Inference Server.

Usage:
    python scripts/export_yolov8_pose_onnx.py [--size n|s|m|l|x]

The exported ONNX model lands in triton_model_repo/yolov8_pose/1/model.onnx
with a matching config.pbtxt generated alongside it.

Model I/O:
    Input:  images   [batch, 3, 640, 640]  FP32
    Output: output0  [batch, 56, 8400]     FP32
            56 = 4 (box xywh) + 1 (obj conf) + 51 (17 keypoints × 3: x, y, visibility)
"""

import argparse
import os
import sys


def export_yolov8_pose(size: str = "n", repo_root: str | None = None):
    """Download YOLOv8{size}-pose from Ultralytics and export to ONNX."""
    from ultralytics import YOLO

    model_name = f"yolov8{size}-pose"
    print(f"⬇️  Downloading {model_name} from Ultralytics hub...")
    model = YOLO(f"{model_name}.pt")

    if repo_root is None:
        repo_root = os.path.join(
            os.getcwd(), "triton_model_repo", "yolov8_pose", "1"
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
    print(f"   Output: output0 [batch, 56, 8400]  FP32")
    print(f"           56 = 4 (box) + 1 (conf) + 51 (17 keypoints × 3)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export YOLOv8-pose to ONNX")
    parser.add_argument(
        "--size",
        choices=["n", "s", "m", "l", "x"],
        default="n",
        help="Model size: n(ano), s(mall), m(edium), l(arge), x(large) — default: n",
    )
    args = parser.parse_args()
    export_yolov8_pose(size=args.size)
