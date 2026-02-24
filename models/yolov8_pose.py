"""
YOLOv8-pose keypoint estimation model for the OpenDeploy vision pipeline.

P2 of V7 — Sports Movement Vision Pipeline:
  Camera → WebRTC → SHM ring buffer → YOLOv8-pose → bboxes + 17-keypoint skeletons

Supports two serving modes:
  1. ONNX Runtime (local) — default, no GPU required
  2. Triton Inference Server — set TRITON_URL env var

Detects persons and estimates 17 COCO keypoints per person:
  nose, left_eye, right_eye, left_ear, right_ear,
  left_shoulder, right_shoulder, left_elbow, right_elbow,
  left_wrist, right_wrist, left_hip, right_hip,
  left_knee, right_knee, left_ankle, right_ankle

Output per detection:
  - bounding box (x1, y1, x2, y2) in original image coordinates
  - confidence score
  - 17 keypoints, each with (x, y, visibility)
  - skeleton edges connecting keypoints for rendering

Model I/O (ONNX):
  Input:   images   [batch, 3, 640, 640]  FP32
  Output:  output0  [batch, 56, 8400]     FP32
           56 = 4 (box xywh) + 1 (obj conf) + 51 (17 keypoints × 3: x, y, vis)
"""

import io
import logging
import os
import time
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image

from backend.interface import AIModel

logger = logging.getLogger(__name__)

# ── COCO Keypoint definitions ─────────────────────────────────────

KEYPOINT_NAMES = [
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
]

# Skeleton edges — pairs of keypoint indices to draw bones between
SKELETON_EDGES = [
    # Face
    (0, 1),   # nose → left_eye
    (0, 2),   # nose → right_eye
    (1, 3),   # left_eye → left_ear
    (2, 4),   # right_eye → right_ear
    # Upper body
    (5, 6),   # left_shoulder → right_shoulder
    (5, 7),   # left_shoulder → left_elbow
    (7, 9),   # left_elbow → left_wrist
    (6, 8),   # right_shoulder → right_elbow
    (8, 10),  # right_elbow → right_wrist
    # Torso
    (5, 11),  # left_shoulder → left_hip
    (6, 12),  # right_shoulder → right_hip
    (11, 12), # left_hip → right_hip
    # Lower body
    (11, 13), # left_hip → left_knee
    (13, 15), # left_knee → left_ankle
    (12, 14), # right_hip → right_knee
    (14, 16), # right_knee → right_ankle
]

# Skeleton bone groups for coloured rendering on the frontend
SKELETON_BONE_GROUPS = {
    "face": [(0, 1), (0, 2), (1, 3), (2, 4)],
    "upper_body": [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10)],
    "torso": [(5, 11), (6, 12), (11, 12)],
    "lower_body": [(11, 13), (13, 15), (12, 14), (14, 16)],
}


class YOLOv8PoseModel(AIModel):
    """YOLOv8-pose keypoint estimation via ONNX Runtime or Triton.

    Detects persons and outputs 17 COCO keypoints per person with
    bounding boxes and confidence scores. Designed for real-time
    sports movement analysis as part of the V7 pipeline.
    """

    # Defaults (overridable via constructor or env vars)
    DEFAULT_CONF_THRESHOLD = 0.25
    DEFAULT_IOU_THRESHOLD = 0.45
    DEFAULT_KPT_THRESHOLD = 0.5   # keypoint visibility threshold
    DEFAULT_INPUT_SIZE = 640
    NUM_KEYPOINTS = 17

    def __init__(
        self,
        conf_threshold: float | None = None,
        iou_threshold: float | None = None,
        kpt_threshold: float | None = None,
        input_size: int | None = None,
        onnx_path: str | None = None,
    ):
        self.CONF_THRESHOLD = conf_threshold or self.DEFAULT_CONF_THRESHOLD
        self.IOU_THRESHOLD = iou_threshold or self.DEFAULT_IOU_THRESHOLD
        self.KPT_THRESHOLD = kpt_threshold or self.DEFAULT_KPT_THRESHOLD
        self.INPUT_SIZE = input_size or self.DEFAULT_INPUT_SIZE
        self._onnx_path_override = onnx_path
        self.ready = False

    # ── AIModel interface ────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "yolov8-pose"

    @property
    def input_type(self) -> str:
        return "image"

    @property
    def version(self) -> str:
        return "8.0.0"

    @property
    def hardware_requirements(self) -> Dict[str, Any]:
        return {"min_ram": 2, "min_vram": 0}

    # ── Load ─────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load model weights — Triton if TRITON_URL is set, else ONNX Runtime."""
        triton_url = os.getenv("TRITON_URL")
        if triton_url:
            self._load_triton(triton_url)
        else:
            self._load_onnx()

    def _load_triton(self, triton_url: str) -> None:
        try:
            import tritonclient.http as triton_http
        except ImportError as exc:
            raise RuntimeError(
                "TRITON_URL is set but tritonclient is not installed. "
                "pip install tritonclient[http]"
            ) from exc

        self.triton_client = triton_http.InferenceServerClient(url=triton_url)
        self.triton_model_name = os.getenv("TRITON_POSE_MODEL_NAME", "yolov8_pose")
        self.use_triton = True
        self.ready = True
        logger.info(
            "✅ YOLOv8-pose using Triton at %s (model: %s)",
            triton_url,
            self.triton_model_name,
        )

    def _load_onnx(self) -> None:
        import onnxruntime as ort

        if self._onnx_path_override:
            model_path = os.path.abspath(self._onnx_path_override)
        else:
            model_path = os.getenv(
                "YOLO_POSE_ONNX_PATH",
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "triton_model_repo",
                    "yolov8_pose",
                    "1",
                    "model.onnx",
                ),
            )
            model_path = os.path.abspath(model_path)
        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"ONNX model not found at {model_path}. "
                f"Run: python scripts/export_yolov8_pose_onnx.py"
            )

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.use_triton = False
        self.ready = True
        active = self.session.get_providers()
        logger.info("✅ YOLOv8-pose loaded via ONNX Runtime (providers: %s)", active)

    # ── Predict ──────────────────────────────────────────────────────

    async def predict(self, input_data: bytes) -> Dict[str, Any]:
        """Run pose estimation on an image.

        Args:
            input_data: Raw image bytes (JPEG/PNG).

        Returns:
            Dict with model info, inference stats, and per-person detections
            containing bounding boxes, confidence, and 17-keypoint skeletons.
        """
        try:
            image = Image.open(io.BytesIO(input_data)).convert("RGB")
            img_np = np.array(image)  # H, W, C  uint8

            # Pre-process: letterbox to 640×640
            blob, ratio, (pad_w, pad_h) = self._preprocess(img_np)

            # Inference
            t0 = time.perf_counter()
            output0 = self._infer(blob)
            infer_ms = (time.perf_counter() - t0) * 1000.0

            # Post-process → detections with keypoints
            detections = self._postprocess(
                output0, img_np.shape, ratio, pad_w, pad_h
            )

            return {
                "model": self.name,
                "version": self.version,
                "serving": "triton" if getattr(self, "use_triton", False) else "onnxruntime",
                "image_size": f"{image.width}x{image.height}",
                "inference_ms": round(infer_ms, 2),
                "detection_count": len(detections),
                "num_keypoints": self.NUM_KEYPOINTS,
                "keypoint_names": KEYPOINT_NAMES,
                "skeleton_edges": SKELETON_EDGES,
                "detections": detections,
            }

        except Exception as exc:
            logger.exception("YOLOv8-pose inference failed")
            return {"error": f"Inference failed: {exc}"}

    # ── Pre-process ──────────────────────────────────────────────────

    def _preprocess(self, img: np.ndarray) -> Tuple[np.ndarray, float, Tuple[float, float]]:
        """Letter-box resize to 640×640, normalize, NCHW float32.

        Identical to the seg model preprocessing — maintains aspect ratio
        and pads with gray (114, 114, 114).
        """
        h, w = img.shape[:2]
        ratio = min(self.INPUT_SIZE / h, self.INPUT_SIZE / w)
        new_w, new_h = int(round(w * ratio)), int(round(h * ratio))
        pad_w = (self.INPUT_SIZE - new_w) / 2
        pad_h = (self.INPUT_SIZE - new_h) / 2

        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        top, bottom = int(round(pad_h - 0.1)), int(round(pad_h + 0.1))
        left, right = int(round(pad_w - 0.1)), int(round(pad_w + 0.1))
        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114),
        )

        blob = padded.astype(np.float32) / 255.0
        blob = blob.transpose(2, 0, 1)[np.newaxis, ...]  # 1, 3, 640, 640
        return blob.astype(np.float32), ratio, (pad_w, pad_h)

    # ── Inference ────────────────────────────────────────────────────

    def _infer(self, blob: np.ndarray) -> np.ndarray:
        """Run forward pass, return raw output0."""
        if getattr(self, "use_triton", False):
            return self._infer_triton(blob)
        return self._infer_onnx(blob)

    def _infer_onnx(self, blob: np.ndarray) -> np.ndarray:
        outputs = self.session.run(None, {"images": blob})
        return outputs[0]  # output0: (1, 56, 8400)

    def _infer_triton(self, blob: np.ndarray) -> np.ndarray:
        import tritonclient.http as triton_http

        inp = triton_http.InferInput("images", blob.shape, "FP32")
        inp.set_data_from_numpy(blob)
        out0 = triton_http.InferRequestedOutput("output0")

        resp = self.triton_client.infer(
            model_name=self.triton_model_name,
            inputs=[inp],
            outputs=[out0],
        )
        return resp.as_numpy("output0")

    # ── Post-process ─────────────────────────────────────────────────

    def _postprocess(
        self,
        output0: np.ndarray,
        orig_shape: tuple,
        ratio: float,
        pad_w: float,
        pad_h: float,
    ) -> List[Dict[str, Any]]:
        """
        Decode YOLOv8-pose output into per-person detections with keypoints.

        output0: (1, 56, 8400)
            56 channels = 4 (box xywh) + 1 (obj confidence) + 51 (17 kpts × 3)
            8400 = number of anchor candidates
        """
        predictions = output0[0].T  # (8400, 56)
        orig_h, orig_w = orig_shape[:2]

        # Split columns
        boxes_xywh = predictions[:, :4]           # (8400, 4)
        obj_conf = predictions[:, 4]               # (8400,)
        kpts_raw = predictions[:, 5:]              # (8400, 51) → 17 × (x, y, vis)

        # Confidence filter
        mask = obj_conf >= self.CONF_THRESHOLD
        boxes_xywh = boxes_xywh[mask]
        obj_conf = obj_conf[mask]
        kpts_raw = kpts_raw[mask]

        if len(boxes_xywh) == 0:
            return []

        # xywh → xyxy (in 640×640 letterboxed space)
        boxes_xyxy = self._xywh_to_xyxy(boxes_xywh)

        # NMS (pure numpy, no torchvision)
        keep = self._nms(boxes_xyxy, obj_conf, self.IOU_THRESHOLD)
        boxes_xyxy = boxes_xyxy[keep]
        obj_conf = obj_conf[keep]
        kpts_raw = kpts_raw[keep]

        # Scale boxes back to original image coords
        boxes_xyxy[:, [0, 2]] = (boxes_xyxy[:, [0, 2]] - pad_w) / ratio
        boxes_xyxy[:, [1, 3]] = (boxes_xyxy[:, [1, 3]] - pad_h) / ratio
        boxes_xyxy[:, [0, 2]] = np.clip(boxes_xyxy[:, [0, 2]], 0, orig_w)
        boxes_xyxy[:, [1, 3]] = np.clip(boxes_xyxy[:, [1, 3]], 0, orig_h)

        # Reshape keypoints: (N, 51) → (N, 17, 3)
        kpts = kpts_raw.reshape(-1, self.NUM_KEYPOINTS, 3)

        # Scale keypoint coordinates back to original image
        kpts[:, :, 0] = (kpts[:, :, 0] - pad_w) / ratio   # x
        kpts[:, :, 1] = (kpts[:, :, 1] - pad_h) / ratio   # y
        kpts[:, :, 0] = np.clip(kpts[:, :, 0], 0, orig_w)
        kpts[:, :, 1] = np.clip(kpts[:, :, 1], 0, orig_h)
        # Visibility (channel 2) is a confidence score ∈ [0, 1] — no rescaling needed

        # Build JSON-serialisable detections
        detections: List[Dict[str, Any]] = []
        for i in range(len(boxes_xyxy)):
            x1, y1, x2, y2 = boxes_xyxy[i].tolist()
            conf = float(obj_conf[i])
            person_kpts = kpts[i]  # (17, 3)

            # Keypoints as list of dicts
            keypoints_list = []
            visible_count = 0
            for j in range(self.NUM_KEYPOINTS):
                kx, ky, kv = person_kpts[j].tolist()  # native Python floats
                is_visible = bool(kv >= self.KPT_THRESHOLD)
                if is_visible:
                    visible_count += 1
                keypoints_list.append({
                    "name": KEYPOINT_NAMES[j],
                    "x": round(float(kx), 1),
                    "y": round(float(ky), 1),
                    "visibility": round(float(kv), 4),
                    "visible": is_visible,
                })

            # Skeleton edges with coordinates (for direct frontend rendering)
            skeleton = []
            for edge_idx, (start_kpt, end_kpt) in enumerate(SKELETON_EDGES):
                sk = person_kpts[start_kpt].tolist()  # convert to native list
                ek = person_kpts[end_kpt].tolist()
                s_vis = sk[2] >= self.KPT_THRESHOLD
                e_vis = ek[2] >= self.KPT_THRESHOLD
                skeleton.append({
                    "from": KEYPOINT_NAMES[start_kpt],
                    "to": KEYPOINT_NAMES[end_kpt],
                    "from_xy": [round(float(sk[0]), 1), round(float(sk[1]), 1)],
                    "to_xy": [round(float(ek[0]), 1), round(float(ek[1]), 1)],
                    "visible": bool(s_vis and e_vis),
                })

            detections.append({
                "class_name": "person",
                "confidence": round(float(conf), 4),
                "bbox": {
                    "x1": round(float(x1), 1),
                    "y1": round(float(y1), 1),
                    "x2": round(float(x2), 1),
                    "y2": round(float(y2), 1),
                },
                "keypoints": keypoints_list,
                "visible_keypoints": visible_count,
                "total_keypoints": self.NUM_KEYPOINTS,
                "skeleton": skeleton,
            })

        # Sort by confidence descending
        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _xywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
        """Convert center-xywh boxes to corner-xyxy."""
        xyxy = np.empty_like(boxes)
        xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2  # x1
        xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2  # y1
        xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2  # x2
        xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2  # y2
        return xyxy

    @staticmethod
    def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float) -> np.ndarray:
        """Pure-numpy NMS — no torchvision dependency.

        Identical algorithm to the seg model NMS so both models produce
        consistent suppression behavior at the same IoU threshold.
        """
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]

        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
            inds = np.where(iou <= iou_thresh)[0]
            order = order[inds + 1]

        return np.array(keep, dtype=int)
