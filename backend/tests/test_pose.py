"""Unit tests for the YOLOv8-pose model plugin and /vision/pose endpoint.

Tests cover:
  - Model interface compliance (name, input_type, version, hardware_requirements)
  - Preprocessing (letterbox, normalization, shape)
  - NMS (pure-numpy)
  - Postprocessing (box decoding, keypoint scaling, skeleton generation)
  - API endpoint integration (/vision/pose, /vision/detect with pose, /vision/analyze)
"""

import os
import sys
import base64

import numpy as np
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("OPENDEPLOY_API_KEY", "test-key-123")


# ── Model unit tests ────────────────────────────────────────────────

class TestYOLOv8PoseInterface:
    """Verify the model satisfies the AIModel interface contract."""

    def test_model_instantiates(self):
        from models.yolov8_pose import YOLOv8PoseModel

        m = YOLOv8PoseModel()
        assert m.name == "yolov8-pose"
        assert m.input_type == "image"
        assert m.version == "8.0.0"
        assert m.ready is False

    def test_hardware_requirements(self):
        from models.yolov8_pose import YOLOv8PoseModel

        m = YOLOv8PoseModel()
        hw = m.hardware_requirements
        assert "min_ram" in hw
        assert "min_vram" in hw
        assert hw["min_ram"] >= 1

    def test_custom_thresholds(self):
        from models.yolov8_pose import YOLOv8PoseModel

        m = YOLOv8PoseModel(conf_threshold=0.5, iou_threshold=0.3, kpt_threshold=0.7)
        assert m.CONF_THRESHOLD == 0.5
        assert m.IOU_THRESHOLD == 0.3
        assert m.KPT_THRESHOLD == 0.7

    def test_default_thresholds(self):
        from models.yolov8_pose import YOLOv8PoseModel

        m = YOLOv8PoseModel()
        assert m.CONF_THRESHOLD == 0.25
        assert m.IOU_THRESHOLD == 0.45
        assert m.KPT_THRESHOLD == 0.5


class TestYOLOv8PoseConstants:
    """Verify keypoint and skeleton constants are correct."""

    def test_keypoint_names(self):
        from models.yolov8_pose import KEYPOINT_NAMES

        assert len(KEYPOINT_NAMES) == 17
        assert KEYPOINT_NAMES[0] == "nose"
        assert KEYPOINT_NAMES[5] == "left_shoulder"
        assert KEYPOINT_NAMES[16] == "right_ankle"

    def test_skeleton_edges(self):
        from models.yolov8_pose import SKELETON_EDGES

        assert len(SKELETON_EDGES) == 16
        # All edge indices must be valid keypoint indices
        for start, end in SKELETON_EDGES:
            assert 0 <= start < 17
            assert 0 <= end < 17

    def test_skeleton_bone_groups(self):
        from models.yolov8_pose import SKELETON_BONE_GROUPS, SKELETON_EDGES

        all_grouped = []
        for group_edges in SKELETON_BONE_GROUPS.values():
            all_grouped.extend(group_edges)
        # Every edge should be in a bone group
        assert set(all_grouped) == set(SKELETON_EDGES)


class TestYOLOv8PosePreprocess:
    """Test letterbox preprocessing."""

    def test_preprocess_shape(self):
        from models.yolov8_pose import YOLOv8PoseModel

        m = YOLOv8PoseModel()
        # Create a dummy 480×640 RGB image
        img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        blob, ratio, (pad_w, pad_h) = m._preprocess(img)

        assert blob.shape == (1, 3, 640, 640)
        assert blob.dtype == np.float32
        assert 0.0 <= blob.min()
        assert blob.max() <= 1.0

    def test_preprocess_square_image(self):
        from models.yolov8_pose import YOLOv8PoseModel

        m = YOLOv8PoseModel()
        img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
        blob, ratio, (pad_w, pad_h) = m._preprocess(img)

        assert blob.shape == (1, 3, 640, 640)
        assert ratio == 1.0
        assert pad_w == 0.0
        assert pad_h == 0.0

    def test_preprocess_letterbox_padding(self):
        from models.yolov8_pose import YOLOv8PoseModel

        m = YOLOv8PoseModel()
        # Wide image: 200×800
        img = np.random.randint(0, 255, (200, 800, 3), dtype=np.uint8)
        blob, ratio, (pad_w, pad_h) = m._preprocess(img)

        assert blob.shape == (1, 3, 640, 640)
        # Should have vertical padding (pad_h > 0)
        assert pad_h > 0


class TestYOLOv8PoseNMS:
    """Test pure-numpy NMS implementation."""

    def test_nms_no_overlap(self):
        from models.yolov8_pose import YOLOv8PoseModel

        boxes = np.array([
            [0, 0, 10, 10],
            [100, 100, 110, 110],
        ], dtype=np.float32)
        scores = np.array([0.9, 0.8], dtype=np.float32)

        keep = YOLOv8PoseModel._nms(boxes, scores, 0.5)
        assert len(keep) == 2

    def test_nms_high_overlap(self):
        from models.yolov8_pose import YOLOv8PoseModel

        boxes = np.array([
            [0, 0, 100, 100],
            [5, 5, 105, 105],   # nearly identical
        ], dtype=np.float32)
        scores = np.array([0.9, 0.8], dtype=np.float32)

        keep = YOLOv8PoseModel._nms(boxes, scores, 0.5)
        assert len(keep) == 1
        assert keep[0] == 0  # higher-confidence box kept

    def test_nms_empty(self):
        from models.yolov8_pose import YOLOv8PoseModel

        boxes = np.empty((0, 4), dtype=np.float32)
        scores = np.empty((0,), dtype=np.float32)

        keep = YOLOv8PoseModel._nms(boxes, scores, 0.5)
        assert len(keep) == 0


class TestYOLOv8PoseBoxConversion:
    """Test xywh → xyxy conversion."""

    def test_xywh_to_xyxy(self):
        from models.yolov8_pose import YOLOv8PoseModel

        boxes = np.array([[50, 50, 20, 30]], dtype=np.float32)  # cx=50,cy=50,w=20,h=30
        xyxy = YOLOv8PoseModel._xywh_to_xyxy(boxes)

        np.testing.assert_allclose(xyxy[0], [40, 35, 60, 65])


class TestYOLOv8PosePostprocess:
    """Test full postprocessing with synthetic model output."""

    def test_postprocess_no_detections(self):
        from models.yolov8_pose import YOLOv8PoseModel

        m = YOLOv8PoseModel(conf_threshold=0.9)

        # output0: (1, 56, 8400) with all-zero confidence → no detections
        output0 = np.zeros((1, 56, 8400), dtype=np.float32)
        detections = m._postprocess(output0, (480, 640), 1.0, 0.0, 0.0)
        assert detections == []

    def test_postprocess_single_detection(self):
        from models.yolov8_pose import YOLOv8PoseModel

        m = YOLOv8PoseModel(conf_threshold=0.3, kpt_threshold=0.3)

        # Craft a synthetic output0 with one strong detection at anchor 0
        output0 = np.zeros((1, 56, 8400), dtype=np.float32)
        # Box: center at (320, 320), w=100, h=200
        output0[0, 0, 0] = 320.0  # cx
        output0[0, 1, 0] = 320.0  # cy
        output0[0, 2, 0] = 100.0  # w
        output0[0, 3, 0] = 200.0  # h
        # Confidence
        output0[0, 4, 0] = 0.85
        # 17 keypoints × 3 (x, y, vis) starting at index 5
        for k in range(17):
            output0[0, 5 + k * 3, 0] = 300.0 + k * 2  # x
            output0[0, 6 + k * 3, 0] = 200.0 + k * 3  # y
            output0[0, 7 + k * 3, 0] = 0.9             # visibility

        # orig_shape=(640,640), ratio=1.0, no padding
        detections = m._postprocess(output0, (640, 640), 1.0, 0.0, 0.0)

        assert len(detections) == 1
        d = detections[0]
        assert d["class_name"] == "person"
        assert d["confidence"] == 0.85
        assert "bbox" in d
        assert d["bbox"]["x1"] < d["bbox"]["x2"]
        assert d["bbox"]["y1"] < d["bbox"]["y2"]
        assert len(d["keypoints"]) == 17
        assert d["total_keypoints"] == 17
        assert d["visible_keypoints"] == 17  # all have vis=0.9 > kpt_threshold=0.3
        assert len(d["skeleton"]) == 16

        # Check keypoint structure
        kp = d["keypoints"][0]
        assert kp["name"] == "nose"
        assert "x" in kp
        assert "y" in kp
        assert "visibility" in kp
        assert "visible" in kp

        # Check skeleton edge structure
        edge = d["skeleton"][0]
        assert "from" in edge
        assert "to" in edge
        assert "from_xy" in edge
        assert "to_xy" in edge
        assert "visible" in edge


# ── API endpoint tests ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _patch_model_loading():
    """Prevent real model loading during tests."""
    with patch("backend.loader.load_plugins"):
        yield


@pytest.fixture()
def client():
    from backend.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


API_HEADERS = {"X-API-Key": "test-key-123"}


class TestVisionPoseEndpoint:
    """Test the /vision/pose endpoint."""

    def test_pose_model_not_loaded(self, client):
        resp = client.post(
            "/vision/pose",
            json={"image": base64.b64encode(b"fake").decode()},
        )
        assert resp.status_code == 404
        assert "yolov8-pose" in resp.json()["detail"]

    def test_pose_invalid_base64(self, client):
        from backend.registry import registry

        mock_model = MagicMock()
        mock_model.name = "yolov8-pose"
        mock_model.input_type = "image"
        mock_model.ready = True
        registry._models["yolov8-pose"] = mock_model

        resp = client.post("/vision/pose", json={"image": "not!!valid!!base64"})
        assert resp.status_code == 400

        del registry._models["yolov8-pose"]

    def test_pose_success(self, client):
        from backend.registry import registry

        mock_result = {
            "model": "yolov8-pose",
            "version": "8.0.0",
            "serving": "onnxruntime",
            "detection_count": 1,
            "detections": [{"class_name": "person", "confidence": 0.9}],
        }

        mock_model = MagicMock()
        mock_model.name = "yolov8-pose"
        mock_model.input_type = "image"
        mock_model.ready = True
        mock_model.predict = AsyncMock(return_value=mock_result)
        registry._models["yolov8-pose"] = mock_model

        # Create a minimal valid PNG image as base64
        from PIL import Image
        import io

        img = Image.new("RGB", (64, 64), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64_image = base64.b64encode(buf.getvalue()).decode()

        resp = client.post("/vision/pose", json={"image": b64_image})
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "yolov8-pose"
        assert data["detection_count"] == 1

        del registry._models["yolov8-pose"]


class TestVisionDetectWithPose:
    """Test that /vision/detect can route to the pose model."""

    def test_detect_with_pose_model(self, client):
        from backend.registry import registry

        mock_result = {
            "model": "yolov8-pose",
            "detection_count": 2,
            "detections": [],
        }

        mock_model = MagicMock()
        mock_model.name = "yolov8-pose"
        mock_model.input_type = "image"
        mock_model.ready = True
        mock_model.predict = AsyncMock(return_value=mock_result)
        registry._models["yolov8-pose"] = mock_model

        from PIL import Image
        import io

        img = Image.new("RGB", (64, 64), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64_image = base64.b64encode(buf.getvalue()).decode()

        resp = client.post(
            "/vision/detect",
            json={"model": "yolov8-pose", "image": b64_image},
        )
        assert resp.status_code == 200
        assert resp.json()["model"] == "yolov8-pose"

        del registry._models["yolov8-pose"]


class TestVisionAnalyzeEndpoint:
    """Test the /vision/analyze combined endpoint."""

    def test_analyze_both_missing(self, client):
        from PIL import Image
        import io

        img = Image.new("RGB", (64, 64), color="green")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64_image = base64.b64encode(buf.getvalue()).decode()

        resp = client.post("/vision/analyze", json={"image": b64_image})
        assert resp.status_code == 404
        assert "yolov8-seg" in resp.json()["detail"]
        assert "yolov8-pose" in resp.json()["detail"]

    def test_analyze_success(self, client):
        from backend.registry import registry

        seg_result = {"model": "yolov8-seg", "detection_count": 3}
        pose_result = {"model": "yolov8-pose", "detection_count": 2}

        mock_seg = MagicMock()
        mock_seg.name = "yolov8-seg"
        mock_seg.ready = True
        mock_seg.predict = AsyncMock(return_value=seg_result)

        mock_pose = MagicMock()
        mock_pose.name = "yolov8-pose"
        mock_pose.ready = True
        mock_pose.predict = AsyncMock(return_value=pose_result)

        registry._models["yolov8-seg"] = mock_seg
        registry._models["yolov8-pose"] = mock_pose

        from PIL import Image
        import io

        img = Image.new("RGB", (64, 64), color="yellow")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64_image = base64.b64encode(buf.getvalue()).decode()

        resp = client.post("/vision/analyze", json={"image": b64_image})
        assert resp.status_code == 200
        data = resp.json()
        assert data["combined"] is True
        assert "total_compute_ms" in data
        assert data["segmentation"]["model"] == "yolov8-seg"
        assert data["pose"]["model"] == "yolov8-pose"

        del registry._models["yolov8-seg"]
        del registry._models["yolov8-pose"]
