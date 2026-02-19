# Webcam YOLO Vision Pipeline — Complete Technical Deep-Dive

> **Scope:** Everything about the real-time webcam → YOLO inference pipeline in OpenDeploy — architecture, data flow, every iteration, every optimization, and exactly why each decision was made.  
> **Last Updated:** 2026-02-17

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Data Flow — Frame-by-Frame](#3-data-flow--frame-by-frame)
4. [Shared Memory Protocol (ODSH v2)](#4-shared-memory-protocol-odsh-v2)
5. [YOLOv8-Seg Model Pipeline](#5-yolov8-seg-model-pipeline)
6. [ONNX Export Pipeline](#6-onnx-export-pipeline)
7. [Iteration History](#7-iteration-history--the-full-story)
8. [Threshold Sweep Methodology](#8-threshold-sweep-methodology)
9. [Quality Heuristic](#9-quality-heuristic)
10. [Serving Modes](#10-serving-modes)
11. [Configuration Reference](#11-configuration-reference)
12. [What's Next (V7 Roadmap)](#12-whats-next--v7-roadmap)

---

## 1. Overview

The Webcam YOLO pipeline lets a browser-connected camera feed run through real-time instance segmentation. A user opens a browser, grants webcam access, and immediately sees bounding boxes, class labels, confidence scores, and pixel-level segmentation masks overlaid on their video — all running through the OpenDeploy backend.

**Key numbers (current best):**

| Metric | Value |
|--------|-------|
| End-to-end latency | < 15ms target |
| Model | YOLOv8n-seg (nano) on ONNX Runtime |
| Classes | 80 (full COCO) |
| Input resolution | 640×640 (letterboxed) |
| Avg inference (CPU) | ~25ms (nano), ~68ms (small) |
| IPC mechanism | Zero-copy shared memory via mmap |

---

## 2. Architecture

```
┌──────────────┐
│   Browser    │
│  (getUserMe- │
│   dia API)   │
└──────┬───────┘
       │ WebRTC DataChannel (binary frames)
       ▼
┌──────────────────────────────────┐
│   Go WebRTC Gateway              │
│   (Pion library, :7000)          │
│                                  │
│   POST /offer → SDP negotiation  │
│   DataChannel → frame receiver   │
│   12-byte header: w, h, format   │
└──────┬───────────────────────────┘
       │ mmap write to ring buffer slot
       ▼
┌──────────────────────────────────┐
│   /dev/shm/opendeploy_frames    │
│   ODSH v2 Ring Buffer            │
│   64 slots × (40B header + data) │
└──────┬───────────────────────────┘
       │ mmap read (zero-copy)
       ▼
┌──────────────────────────────────┐
│   Python FastAPI Backend         │
│   SharedMemoryFrameReader        │
│   → read_latest() or             │
│     read_window(n) for temporal  │
└──────┬───────────────────────────┘
       │ numpy array
       ▼
┌──────────────────────────────────┐
│   YOLOv8-Seg Model               │
│   (ONNX Runtime or Triton)       │
│                                  │
│   preprocess → infer → postproc  │
│   → bboxes, masks, classes, conf │
└──────┬───────────────────────────┘
       │ JSON response
       ▼
┌──────────────────────────────────┐
│   Browser / Dashboard            │
│   Canvas overlay rendering       │
└──────────────────────────────────┘
```

---

## 3. Data Flow — Frame-by-Frame

Here is exactly what happens to a single video frame, step by step:

### Step 1: Browser Captures Frame
The browser calls `getUserMedia()` to access the webcam. Each frame is encoded and sent as binary data over a WebRTC DataChannel with a 12-byte header:

| Bytes | Field | Type |
|-------|-------|------|
| 0–3 | width | uint32 LE |
| 4–7 | height | uint32 LE |
| 8–11 | format | uint32 LE (1=RGB, 2=RGBA, 3=GRAY) |
| 12+ | pixel data | raw bytes |

### Step 2: Go Gateway Receives Frame
The Go gateway (`webrtc-gateway/main.go`) receives the DataChannel message, validates dimensions against `OPENDEPLOY_MAX_FRAME_WIDTH` / `OPENDEPLOY_MAX_FRAME_HEIGHT`, and writes the frame into the next ring buffer slot.

### Step 3: Shared Memory Write
The gateway performs an atomic ring buffer write:
1. Compute slot index: `(write_seq) % num_slots`
2. Mark slot flags = `WRITING` (2)
3. Copy 40-byte slot header (magic, width, height, format, data_len, flags, seq, timestamp_ns)
4. Copy pixel payload into slot body
5. Mark slot flags = `READY` (1)
6. Increment global `write_seq`

### Step 4: Python Backend Reads Frame
`SharedMemoryFrameReader.read_latest()`:
1. Read `write_seq` from global header
2. Compute slot index: `(write_seq - 1) % num_slots`
3. Read slot header — check magic (`ODSF`), flags (`READY`), dimensions
4. Read pixel payload
5. **Double-read consistency check**: re-read header; if seq or flags changed during read, the slot was overwritten → retry (up to 3 attempts)
6. Return `SharedFrame` dataclass

### Step 5: YOLOv8-Seg Preprocessing
`YOLOv8SegModel._preprocess(image)`:
1. Decode raw bytes to numpy array via PIL
2. **Letterbox resize** to 640×640 maintaining aspect ratio, pad with gray (114, 114, 114)
3. Normalize pixel values to [0, 1] float32
4. Transpose from HWC → CHW (channels first)
5. Add batch dimension → shape `[1, 3, 640, 640]`
6. Record scale ratio and padding offsets for later coordinate mapping

### Step 6: Model Inference
Either ONNX Runtime or Triton executes the forward pass:
- **Output 0** — shape `[1, 116, 8400]`: 8400 candidate detections × (4 box coords + 80 class scores + 32 mask coefficients)
- **Output 1** — shape `[1, 32, 160, 160]`: 32 prototype masks at ¼ resolution

### Step 7: Postprocessing
`YOLOv8SegModel._postprocess(output0, output1, ...)`:

1. **Split channels**: boxes (4), class scores (80), mask coefficients (32) from the 116 channels
2. **Confidence filter**: keep only detections where `max(class_scores) > CONF_THRESHOLD`
3. **Box conversion**: center-xywh → corner-xyxy
4. **NMS** (pure NumPy): IoU-based suppression at `IOU_THRESHOLD` — no torchvision dependency
5. **Mask generation**: matrix multiply selected mask coefficients with prototype masks → per-instance mask at 160×160
6. **Sigmoid activation** on masks → probability map
7. **Crop masks** to each detection's bounding box
8. **Resize masks** back to original image dimensions using the letterbox scale/padding
9. **Extract contours** via OpenCV `findContours` → polygon representation
10. **Compute mask area** in pixels

### Step 8: JSON Response
```json
{
  "model": "yolov8-seg",
  "version": "8.0.0",
  "serving": "onnxruntime",
  "image_width": 1920,
  "image_height": 1080,
  "inference_ms": 24.73,
  "detections_count": 9,
  "detections": [
    {
      "class_id": 0,
      "class_name": "person",
      "confidence": 0.861,
      "bbox": [120, 45, 380, 510],
      "mask_polygon": [[125, 50], [130, 48], ...],
      "mask_area_px": 45230
    }
  ]
}
```

---

## 4. Shared Memory Protocol (ODSH v2)

### Why Shared Memory?

| IPC Method | Frame Transfer Latency | Why Not |
|------------|----------------------|---------|
| gRPC streaming | ~7ms | Protobuf serialization overhead |
| Unix sockets | ~4ms | Kernel copies on send/recv |
| **Shared memory (mmap)** | **< 2ms** | Zero-copy — both processes read/write the same physical memory |

For 60fps video at 1080p, every millisecond matters. gRPC adds ~5ms of serialization overhead per frame. Shared memory eliminates this entirely.

### Memory Layout

```
┌─────────────────────────── /dev/shm/opendeploy_frames ───────────────────────────┐
│ Global Header (64 bytes)                                                         │
│ ┌─────────┬─────────┬───────────┬───────────┬───────────┬──────────┬───────────┐ │
│ │magic(4) │vers.(4) │num_slots(4)│slot_sz(4) │write_seq(8)│slot_cap(4)│reserved(36)│
│ │"ODSH"   │2        │64         │...        │monotonic  │...       │          │ │
│ └─────────┴─────────┴───────────┴───────────┴───────────┴──────────┴───────────┘ │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Slot 0                                                                          │
│ ┌───────────────────── 40-byte header ──────────────────────┬── payload ──────┐ │
│ │magic(4) │w(4) │h(4) │fmt(4) │len(4) │flags(4) │seq(8) │ts(8)│ pixel data  │ │
│ │"ODSF"   │1920 │1080 │1(RGB) │...    │1(READY) │...    │ns   │ raw bytes   │ │
│ └───────────────────────────────────────────────────────────┴────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Slot 1  ...  Slot 63                                                            │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Ring Buffer Semantics

- **Slot count**: 64 (configurable via `OPENDEPLOY_RING_SLOTS`)
- **Slot capacity**: `4 × 1920 × 1080` bytes default (configurable via `OPENDEPLOY_MAX_FRAME_BYTES`)
- **Write index**: `slot_index = write_seq % num_slots` (wraps around)
- **Overwrite policy**: oldest slot is silently overwritten (no blocking)
- **Consistency**: double-read check after payload copy detects torn writes

### Flags State Machine

```
EMPTY (0) → WRITING (2) → READY (1) → [overwritten] → WRITING (2) → ...
```

---

## 5. YOLOv8-Seg Model Pipeline

### Model Architecture

YOLOv8-seg is an anchor-free, single-stage instance segmentation model from Ultralytics. It outputs:

1. **Detection head**: 8400 candidate boxes with 80-class scores + 32 mask coefficients per box
2. **Segmentation head**: 32 prototype masks at 160×160 resolution

Final instance masks are computed by: `mask = sigmoid(coefficients × prototypes)` and cropped to each bounding box.

### Available Model Sizes

| Size | File | Parameters | Inference (CPU) | Accuracy |
|------|------|-----------|-----------------|----------|
| **Nano (n)** | `yolov8n-seg.pt` | 3.4M | ~25ms | Good |
| **Small (s)** | `yolov8s-seg.pt` | 11.8M | ~68ms | Better |
| Medium (m) | `yolov8m-seg.pt` | 27.3M | ~150ms | High |
| Large (l) | `yolov8l-seg.pt` | 46.0M | ~280ms | Higher |
| XLarge (x) | `yolov8x-seg.pt` | 71.8M | ~400ms | Highest |

OpenDeploy currently ships with **nano** (default) and **small** weights. The project includes both `.pt` files at the repo root.

### Pure-NumPy NMS

A deliberate design decision: the NMS implementation uses only NumPy — no torchvision, no OpenCV NMS. This means:
- No PyTorch GPU dependency for inference
- Runs on any machine with numpy + onnxruntime
- Identical behavior on CPU and GPU serving paths

---

## 6. ONNX Export Pipeline

**Script:** `scripts/export_yolov8_seg_onnx.py`

```bash
python scripts/export_yolov8_seg_onnx.py --size n   # nano (default)
python scripts/export_yolov8_seg_onnx.py --size s   # small
```

**What it does:**
1. Downloads the Ultralytics `.pt` checkpoint
2. Exports to ONNX with `opset=18`, `simplify=True`, `dynamic=True` (dynamic batch axis)
3. Moves output to `triton_model_repo/yolov8_seg/1/model.onnx`

**Model I/O:**

| Direction | Name | Shape | Type |
|-----------|------|-------|------|
| Input | `images` | `[batch, 3, 640, 640]` | FP32 |
| Output | `output0` | `[batch, 116, 8400]` | FP32 |
| Output | `output1` | `[batch, 32, 160, 160]` | FP32 |

The dynamic batch axis means the same ONNX file supports batch=1 (real-time) and batch>1 (offline benchmarking).

---

## 7. Iteration History — The Full Story

Every iteration of the YOLO pipeline is tracked in the database (`ModelEvolution` table) and in `benchmark_results.json`. Here is the complete history:

### Iteration 0 — Baseline (2026-02-12)

**What:** First working end-to-end pipeline. YOLOv8n-seg with default Ultralytics thresholds.

| Parameter | Value |
|-----------|-------|
| Model | YOLOv8n-seg (nano, 3.4M params) |
| Conf threshold | 0.25 (Ultralytics default) |
| IoU threshold | 0.45 (Ultralytics default) |
| Input size | 640×640 |
| Serving | ONNX Runtime (CPU) |

**Results:**

| Metric | Value |
|--------|-------|
| Test images | 2 (Ultralytics sample assets) |
| Total detections | 9 |
| Avg detections/image | 4.5 |
| Avg inference | 24.73ms |
| Avg confidence | 0.713 |
| Unique classes detected | 4 / 80 |
| Classes found | person (6), bus (1), skateboard (1), tie (1) |

**Assessment:** Working pipeline — reasonable speed, but we had no data on whether the default thresholds were optimal for our use case.

---

### Iteration 1 — Threshold Optimized (2026-02-12)

**What changed:** Ran a 54-configuration threshold sweep to find optimal conf/IoU thresholds.

**How the sweep worked:**
- 9 confidence thresholds: `[0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60]`
- 6 IoU thresholds: `[0.30, 0.40, 0.45, 0.50, 0.60, 0.70]`
- Each combination tested against the same image set
- Ranked by quality heuristic (see [Section 9](#9-quality-heuristic))

**Winning configuration:**

| Parameter | Before | After | Change |
|-----------|--------|-------|--------|
| Conf threshold | 0.25 | **0.30** | +0.05 |
| IoU threshold | 0.45 | **0.40** | -0.05 |

**Results:**

| Metric | Baseline | Optimized | Delta |
|--------|----------|-----------|-------|
| Total detections | 9 | 8 | -1 |
| Avg detections/image | 4.5 | 4.0 | -0.5 |
| Avg inference | 24.73ms | 33.95ms | +9.22ms |
| Avg confidence | 0.713 | **0.767** | **+7.6%** |
| Unique classes | 4 | 4 | — |
| Quality score | — | **0.398** | — |
| FPS | — | 29.5 | — |

**Confidence distribution (Iteration 1):**

| Percentile | Value |
|------------|-------|
| P10 | 0.581 |
| P25 | 0.774 |
| **P50 (median)** | **0.840** |
| P75 | 0.858 |
| P90 | 0.860 |
| Std dev | 0.151 |
| Min | 0.405 |
| Max | 0.861 |

**Per-class average confidence:**

| Class | Confidence |
|-------|-----------|
| bus | 0.861 |
| person | 0.842 |
| tie | 0.656 |
| skateboard | 0.405 |

**Why this was better:** Raising the confidence threshold from 0.25 → 0.30 filtered out 1 low-confidence detection, increasing average confidence by 7.6%. Lowering IoU from 0.45 → 0.40 produced slightly more aggressive NMS, removing borderline duplicates. The net effect: fewer but higher-quality detections.

---

### Iteration 2 — Model Scale-Up (2026-02-12)

**What changed:** Switched from YOLOv8**n**-seg (nano, 3.4M params) to YOLOv8**s**-seg (small, 11.8M params) to test whether a larger model backbone improves detection quality.

| Parameter | Before | After |
|-----------|--------|-------|
| Model | YOLOv8n-seg | **YOLOv8s-seg** |
| Parameters | 3.4M | **11.8M** (3.5× more) |
| Conf threshold | 0.30 | 0.30 |
| IoU threshold | 0.40 | 0.40 |

**Results:**

| Metric | Nano (Iter 1) | Small (Iter 2) | Delta |
|--------|---------------|----------------|-------|
| Total detections | 8 | 8 | — |
| Avg detections/image | 4.0 | 4.0 | — |
| Avg inference | 33.95ms | **68.14ms** | **+100.7%** |
| Avg confidence | 0.767 | **0.843** | **+9.9%** |
| Unique classes | 4 | **3** | **-1** |
| Quality score | 0.398 | **0.379** | **-4.8%** |
| FPS | 29.5 | **14.7** | **-50.2%** |

**Confidence distribution (Iteration 2):**

| Percentile | Value |
|------------|-------|
| P10 | 0.706 |
| P25 | 0.839 |
| **P50 (median)** | **0.886** |
| P75 | 0.900 |
| P90 | 0.915 |
| Std dev | 0.097 |
| Min | 0.631 |
| Max | 0.925 |

**Per-class average confidence:**

| Class | Confidence |
|-------|-----------|
| bus | **0.925** |
| person | 0.847 |
| tie | 0.738 |
| skateboard | *(not detected)* |

**Key insight:** The small model is significantly more confident (median 0.886 vs 0.840), with tighter spread (std 0.097 vs 0.151). However:
- **FPS halved** (29.5 → 14.7) — this may break the 60fps real-time target
- **Lost skateboard class** — the higher-capacity model appears more conservative, failing to detect the low-confidence skateboard
- **Quality score actually decreased** (-4.8%) because the heuristic penalizes reduced class coverage

**Decision:** Keep YOLOv8n-seg as the default for real-time use. The small model is available via `--model-arch yolov8s-seg` for accuracy-critical offline analysis where latency doesn't matter.

---

## 8. Threshold Sweep Methodology

### Why Sweep?

Default model thresholds (conf=0.25, IoU=0.45) are tuned for general COCO benchmarks. Our deployment context — webcam video of real-world scenes — may have different characteristics. The sweep finds the best thresholds for *our* data.

### Sweep Grid

```
Confidence: [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60]   (9 values)
IoU:        [0.30, 0.40, 0.45, 0.50, 0.60, 0.70]                        (6 values)
Total:      54 configurations
```

### Process

For each of the 54 (conf, IoU) pairs:
1. Instantiate a fresh `YOLOv8SegModel(conf_threshold=c, iou_threshold=i)`
2. Load model weights
3. Run inference on all test images
4. Collect: detection count, confidences, class distribution, inference time, mask areas
5. Compute quality score

### Output

Results saved to `sweep_results.json` (1,340 lines). The script prints a ranked table:

```
Rank  Conf   IoU   Dets  AvgConf  Classes  FPS   Quality
  1   0.30   0.40   8    0.767      4     29.5   0.398
  2   0.30   0.45   8    0.767      4     34.1   0.398
  3   0.25   0.40   9    0.713      4     35.6   0.398
  ...
```

And compares the winner against the Ultralytics baseline.

---

## 9. Quality Heuristic

Without ground-truth annotations, we can't compute real mAP. Instead, the project uses a proxy quality score:

$$Q = \text{avg\_confidence} \times \sqrt{\frac{\text{unique\_classes}}{80}} \times \log_2(1 + \text{avg\_detections\_per\_image})$$

### Why these three factors?

| Factor | What It Measures | Why It Matters |
|--------|-----------------|----------------|
| `avg_confidence` | Precision proxy | High-confidence detections are more likely correct |
| `√(unique_classes / 80)` | Recall proxy | Detecting more of the 80 COCO classes suggests the model isn't missing objects |
| `log₂(1 + avg_dets)` | Detection density | More detections per image is useful, but with diminishing returns (log prevents rewarding noise) |

### F1 Proxy (for database tracking)

The benchmark script also computes an F1 proxy for the `ModelEvolution` record:

$$F_1 = \frac{2 \times \text{precision} \times \text{recall}}{\text{precision} + \text{recall}}$$

Where precision = `avg_confidence` and recall = `class_coverage` (unique_classes / 80).

---

## 10. Serving Modes

### Mode 1: ONNX Runtime (Default)

```
Model file: triton_model_repo/yolov8_seg/1/model.onnx
Runtime:    onnxruntime (pip install onnxruntime or onnxruntime-gpu)
GPU:        Tries CUDAExecutionProvider first, falls back to CPUExecutionProvider
```

No external services required. The model file is loaded directly into the Python process.

### Mode 2: NVIDIA Triton Inference Server

```bash
# Start Triton
docker compose -f docker-compose.triton.yml up -d

# Set env var on API container
TRITON_URL=localhost:8001
```

When `TRITON_URL` is set, the model connects via `tritonclient.http` and delegates inference to Triton. Benefits:
- Dynamic batching (Triton groups concurrent requests)
- TensorRT optimization (if model is exported to TRT)
- Model versioning and A/B testing via Triton model repository
- GPU memory management across multiple models

---

## 11. Configuration Reference

All configuration is via environment variables — no config files needed.

### Frame / SHM Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENDEPLOY_MAX_FRAME_WIDTH` | 1920 | Max accepted frame width (pixels) |
| `OPENDEPLOY_MAX_FRAME_HEIGHT` | 1080 | Max accepted frame height (pixels) |
| `OPENDEPLOY_MAX_FRAME_BYTES` | 8294400 (4×1920×1080) | Max bytes per frame slot |
| `OPENDEPLOY_RING_SLOTS` | 64 | Number of ring buffer slots |

### Model Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `TRITON_URL` | *(unset)* | If set, use Triton. Otherwise ONNX Runtime. |

### Threshold Overrides (via benchmark scripts)

| CLI Flag | Default | Description |
|----------|---------|-------------|
| `--conf-threshold` | 0.25 | Confidence filter threshold |
| `--iou-threshold` | 0.45 | NMS IoU threshold |
| `--model-arch` | yolov8n-seg | Model architecture tag |
| `--onnx-path` | *(auto)* | Override ONNX model file path |

---

## 12. What's Next — V7 Roadmap

The current pipeline handles single-frame detection. V7 extends it to temporal, multi-model sports movement recognition:

| Phase | Status | What Ships |
|-------|--------|------------|
| **P0** | Planned | Multi-frame ring buffer (64 frames with timestamps) |
| **P1** | **Done** | YOLOv8-seg person detection + instance segmentation |
| **P2** | Planned | YOLOv8-pose skeleton keypoints (17 joints per person) |
| **P3** | Planned | Temporal action recognition (SlowFast / X3D on Kinetics-700) |
| **P4** | Planned | Sports-specific fine-tuning (10K+ action classes) |
| **P5** | Planned | Novel movement detection + VLM description generation |
| **P6** | Planned | Frontend canvas overlay (bboxes, masks, skeletons, labels) |
| **P7** | Planned | End-to-end training pipeline (CVAT → PyTorch Lightning → Triton) |

See the main [README.md](../README.md) for the full V7 architecture diagram and movement taxonomy.
