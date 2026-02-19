"""
YOLOv8-seg instance segmentation model for the OpenDeploy vision pipeline.

P1 of V7 — Sports Movement Vision Pipeline:
  Camera → WebRTC → SHM ring buffer → YOLOv8-seg → bboxes + pixel masks

Supports two serving modes:
  1. ONNX Runtime (local) — default, no GPU required
  2. Triton Inference Server — set TRITON_URL env var

COCO 80-class detection with instance segmentation masks.
"""

import io
import logging
import os
import time
from typing import Any, Dict, List

import cv2
import numpy as np
from PIL import Image

from backend.interface import AIModel

logger = logging.getLogger(__name__)

# COCO 80-class names
COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]


class YOLOv8SegModel(AIModel):
    """YOLOv8-seg instance segmentation via ONNX Runtime or Triton."""

    # Defaults (overridable via constructor)
    DEFAULT_CONF_THRESHOLD = 0.25
    DEFAULT_IOU_THRESHOLD = 0.45
    DEFAULT_INPUT_SIZE = 640

    def __init__(
        self,
        conf_threshold: float | None = None,
        iou_threshold: float | None = None,
        input_size: int | None = None,
        onnx_path: str | None = None,
    ):
        self.CONF_THRESHOLD = conf_threshold or self.DEFAULT_CONF_THRESHOLD
        self.IOU_THRESHOLD = iou_threshold or self.DEFAULT_IOU_THRESHOLD
        self.INPUT_SIZE = input_size or self.DEFAULT_INPUT_SIZE
        self._onnx_path_override = onnx_path
        self.ready = False

    # ── AIModel interface ────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "yolov8-seg"

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
        self.triton_model_name = os.getenv("TRITON_SEG_MODEL_NAME", "yolov8_seg")
        self.use_triton = True
        self.ready = True
        logger.info(
            "✅ YOLOv8-seg using Triton at %s (model: %s)",
            triton_url,
            self.triton_model_name,
        )

    def _load_onnx(self) -> None:
        import onnxruntime as ort

        if self._onnx_path_override:
            model_path = os.path.abspath(self._onnx_path_override)
        else:
            model_path = os.getenv(
                "YOLO_SEG_ONNX_PATH",
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "triton_model_repo",
                    "yolov8_seg",
                    "1",
                    "model.onnx",
                ),
            )
            model_path = os.path.abspath(model_path)
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"ONNX model not found at {model_path}")

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.use_triton = False
        self.ready = True
        active = self.session.get_providers()
        logger.info("✅ YOLOv8-seg loaded via ONNX Runtime (providers: %s)", active)

    # ── Predict ──────────────────────────────────────────────────────

    async def predict(self, input_data: bytes) -> Dict[str, Any]:
        try:
            image = Image.open(io.BytesIO(input_data)).convert("RGB")
            img_np = np.array(image)  # H, W, C  uint8

            # Pre-process
            blob, ratio, (pad_w, pad_h) = self._preprocess(img_np)

            # Inference
            t0 = time.perf_counter()
            output0, output1 = self._infer(blob)
            infer_ms = (time.perf_counter() - t0) * 1000.0

            # Post-process → detections + masks
            detections = self._postprocess(
                output0, output1, img_np.shape, ratio, pad_w, pad_h
            )

            return {
                "model": self.name,
                "version": self.version,
                "serving": "triton" if getattr(self, "use_triton", False) else "onnxruntime",
                "image_size": f"{image.width}x{image.height}",
                "inference_ms": round(infer_ms, 2),
                "detection_count": len(detections),
                "detections": detections,
            }

        except Exception as exc:
            logger.exception("YOLOv8-seg inference failed")
            return {"error": f"Inference failed: {exc}"}

    # ── Pre-process ──────────────────────────────────────────────────

    def _preprocess(self, img: np.ndarray):
        """Letter-box resize to 640×640, normalize, NCHW float32."""
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

    def _infer(self, blob: np.ndarray):
        """Run forward pass, return raw output0 and output1."""
        if getattr(self, "use_triton", False):
            return self._infer_triton(blob)
        return self._infer_onnx(blob)

    def _infer_onnx(self, blob: np.ndarray):
        outputs = self.session.run(None, {"images": blob})
        return outputs[0], outputs[1]  # output0, output1

    def _infer_triton(self, blob: np.ndarray):
        import tritonclient.http as triton_http

        inp = triton_http.InferInput("images", blob.shape, "FP32")
        inp.set_data_from_numpy(blob)
        out0 = triton_http.InferRequestedOutput("output0")
        out1 = triton_http.InferRequestedOutput("output1")

        resp = self.triton_client.infer(
            model_name=self.triton_model_name,
            inputs=[inp],
            outputs=[out0, out1],
        )
        return resp.as_numpy("output0"), resp.as_numpy("output1")

    # ── Post-process ─────────────────────────────────────────────────

    def _postprocess(
        self,
        output0: np.ndarray,
        output1: np.ndarray,
        orig_shape: tuple,
        ratio: float,
        pad_w: float,
        pad_h: float,
    ) -> List[Dict[str, Any]]:
        """
        Decode YOLOv8-seg outputs into a list of detections.

        output0: (1, 116, 8400) — 4 box coords + 80 class scores + 32 mask coefficients
        output1: (1, 32, 160, 160) — prototype masks
        """
        predictions = output0[0].T  # (8400, 116)
        protos = output1[0]  # (32, 160, 160)

        orig_h, orig_w = orig_shape[:2]

        # Split columns: box (4) | class scores (80) | mask coefficients (32)
        boxes_xywh = predictions[:, :4]
        class_scores = predictions[:, 4:84]
        mask_coeffs = predictions[:, 84:]  # (8400, 32)

        # Best class per anchor
        class_ids = np.argmax(class_scores, axis=1)
        confidences = class_scores[np.arange(len(class_ids)), class_ids]

        # Confidence filter
        mask = confidences >= self.CONF_THRESHOLD
        boxes_xywh = boxes_xywh[mask]
        confidences = confidences[mask]
        class_ids = class_ids[mask]
        mask_coeffs = mask_coeffs[mask]

        if len(boxes_xywh) == 0:
            return []

        # xywh → xyxy (in 640×640 space)
        boxes_xyxy = self._xywh_to_xyxy(boxes_xywh)

        # NMS
        keep = self._nms(boxes_xyxy, confidences, self.IOU_THRESHOLD)
        boxes_xyxy = boxes_xyxy[keep]
        confidences = confidences[keep]
        class_ids = class_ids[keep]
        mask_coeffs = mask_coeffs[keep]

        # Generate instance masks from prototype
        masks = self._process_masks(
            protos, mask_coeffs, boxes_xyxy, (self.INPUT_SIZE, self.INPUT_SIZE)
        )

        # Scale boxes back to original image coords
        boxes_xyxy[:, [0, 2]] = (boxes_xyxy[:, [0, 2]] - pad_w) / ratio
        boxes_xyxy[:, [1, 3]] = (boxes_xyxy[:, [1, 3]] - pad_h) / ratio
        boxes_xyxy[:, [0, 2]] = np.clip(boxes_xyxy[:, [0, 2]], 0, orig_w)
        boxes_xyxy[:, [1, 3]] = np.clip(boxes_xyxy[:, [1, 3]], 0, orig_h)

        # Build JSON-serialisable detections
        detections: List[Dict[str, Any]] = []
        for i in range(len(boxes_xyxy)):
            x1, y1, x2, y2 = boxes_xyxy[i].tolist()
            cls_id = int(class_ids[i])
            conf = float(confidences[i])

            # Resize binary mask back to original image size
            seg_mask = cv2.resize(
                masks[i].astype(np.float32), (orig_w, orig_h),
                interpolation=cv2.INTER_LINEAR,
            )
            binary_mask = (seg_mask > 0.5).astype(np.uint8)

            # Extract mask contour as polygon (lighter than sending full bitmap)
            contours, _ = cv2.findContours(
                binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            # Take the largest contour
            polygon: List[List[int]] = []
            if contours:
                largest = max(contours, key=cv2.contourArea)
                polygon = largest.squeeze(1).tolist() if largest.size > 0 else []

            # Compute mask area (pixels)
            mask_area = int(binary_mask.sum())

            detections.append({
                "class_id": cls_id,
                "class_name": COCO_NAMES[cls_id] if cls_id < len(COCO_NAMES) else f"class_{cls_id}",
                "confidence": round(conf, 4),
                "bbox": {
                    "x1": round(x1, 1),
                    "y1": round(y1, 1),
                    "x2": round(x2, 1),
                    "y2": round(y2, 1),
                },
                "mask_polygon": polygon,
                "mask_area_px": mask_area,
            })

        # Sort by confidence descending
        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _xywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
        xyxy = np.empty_like(boxes)
        xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2  # x1
        xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2  # y1
        xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2  # x2
        xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2  # y2
        return xyxy

    @staticmethod
    def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float) -> np.ndarray:
        """Pure-numpy NMS (no torchvision dependency)."""
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

    @staticmethod
    def _process_masks(
        protos: np.ndarray,
        mask_coeffs: np.ndarray,
        boxes_xyxy: np.ndarray,
        input_shape: tuple,
    ) -> np.ndarray:
        """
        Generate instance masks from prototype masks and per-detection coefficients.

        protos: (32, 160, 160)
        mask_coeffs: (N, 32)
        Returns: (N, 160, 160) binary-ish masks cropped to each bbox.
        """
        n = mask_coeffs.shape[0]
        mh, mw = protos.shape[1], protos.shape[2]  # 160, 160
        ih, iw = input_shape  # 640, 640

        # Matrix mult: (N, 32) @ (32, 160*160) → (N, 160*160) → (N, 160, 160)
        masks = (mask_coeffs @ protos.reshape(32, -1)).reshape(n, mh, mw)

        # Sigmoid
        masks = 1.0 / (1.0 + np.exp(-masks))

        # Crop each mask to its bounding box (in mask-resolution coords)
        scale_x = mw / iw
        scale_y = mh / ih
        for i in range(n):
            bx1 = max(0, int(boxes_xyxy[i, 0] * scale_x))
            by1 = max(0, int(boxes_xyxy[i, 1] * scale_y))
            bx2 = min(mw, int(boxes_xyxy[i, 2] * scale_x))
            by2 = min(mh, int(boxes_xyxy[i, 3] * scale_y))
            crop_mask = np.zeros((mh, mw), dtype=np.float32)
            crop_mask[by1:by2, bx1:bx2] = masks[i, by1:by2, bx1:bx2]
            masks[i] = crop_mask

        return masks
