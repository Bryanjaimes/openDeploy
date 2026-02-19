# Benchmark Evolution Report

> Human-readable summary of every benchmark run against the YOLOv8-seg vision pipeline.  
> Raw data: [`benchmark_results.json`](../benchmark_results.json) · [`sweep_results.json`](../sweep_results.json)  
> Last Updated: 2026-02-17

---

## Summary

| # | Version | Iteration | Tag | Model | Conf | IoU | Avg Inference | Avg Conf | Classes | FPS | Quality |
|---|---------|-----------|-----|-------|------|-----|---------------|----------|---------|-----|---------|
| 1 | V0 | 0 | Baseline | YOLOv8n-seg | 0.25 | 0.45 | 24.73ms | 0.713 | 4 | — | — |
| 2 | V0 | 0 | Baseline (re-run) | YOLOv8n-seg | 0.25 | 0.45 | 24.82ms | 0.713 | 4 | — | — |
| 3 | V0 | 1 | Threshold Optimized | YOLOv8n-seg | 0.30 | 0.40 | 33.95ms | 0.767 | 4 | 29.5 | 0.398 |
| 4 | V0 | 2 | Model Scale-Up | YOLOv8s-seg | 0.30 | 0.40 | 68.14ms | 0.843 | 3 | 14.7 | 0.379 |

---

## Run #1 — Baseline (2026-02-12 13:30)

**Purpose:** Establish a baseline with the default YOLOv8n-seg model and Ultralytics default thresholds.

| Setting | Value |
|---------|-------|
| Model | YOLOv8n-seg (nano) |
| Confidence threshold | 0.25 |
| IoU threshold | 0.45 |
| Test images | 2 (Ultralytics sample assets) |

### Results

| Metric | Value |
|--------|-------|
| Total detections | 9 |
| Avg detections / image | 4.5 |
| Avg inference time | **24.73ms** |
| Avg confidence | **0.713** |
| Unique classes detected | 4 / 80 |

### Class Distribution

| Class | Count |
|-------|-------|
| person | 6 |
| bus | 1 |
| skateboard | 1 |
| tie | 1 |

---

## Run #2 — Baseline Re-Run (2026-02-12 13:36)

**Purpose:** Verify reproducibility. Same config as Run #1.

| Metric | Run #1 | Run #2 | Delta |
|--------|--------|--------|-------|
| Avg inference | 24.73ms | 24.82ms | +0.09ms |
| Avg confidence | 0.713 | 0.713 | 0.000 |
| Detections | 9 | 9 | 0 |

**Conclusion:** Results are reproducible. Inference time variance < 0.4%.

---

## Threshold Sweep (2026-02-12)

**Purpose:** Find optimal confidence and IoU thresholds for our deployment context.

**Grid:** 9 confidence × 6 IoU = **54 configurations** tested.

### Top 10 Configurations (by quality score)

| Rank | Conf | IoU | Dets/Img | Avg Conf | Classes | FPS | Quality Score |
|------|------|-----|----------|----------|---------|-----|--------------|
| 1 | 0.30 | 0.40 | 4.0 | 0.767 | 4 | 35.6 | **0.398** |
| 2 | 0.30 | 0.45 | 4.0 | 0.767 | 4 | 34.1 | 0.398 |
| 3 | 0.30 | 0.50 | 4.0 | 0.767 | 4 | 37.3 | 0.398 |
| 4 | 0.30 | 0.60 | 4.0 | 0.767 | 4 | 34.7 | 0.398 |
| 5 | 0.30 | 0.70 | 4.0 | 0.767 | 4 | 34.2 | 0.398 |
| 6 | 0.25 | 0.30 | 4.5 | 0.713 | 4 | ~36 | 0.394 |
| 7 | 0.25 | 0.40 | 4.5 | 0.713 | 4 | ~35 | 0.394 |
| 8 | 0.25 | 0.45 | 4.5 | 0.713 | 4 | ~35 | 0.394 |
| 9 | 0.20 | 0.40 | 4.5 | 0.699 | 4 | ~35 | 0.387 |
| 10 | 0.35 | 0.40 | 3.5 | 0.802 | 3 | ~36 | 0.371 |

### Key Findings

1. **Conf = 0.30 dominates.** All top-5 configs use conf = 0.30, regardless of IoU.
2. **IoU has minimal impact** at this detection density — all IoU values from 0.40 to 0.70 produce identical quality scores.
3. **Higher conf (0.35+) hurts quality** because it drops the skateboard class (low confidence), reducing class coverage.
4. **Lower conf (0.10–0.20) adds noise** — more false positives without meaningful class gain.

### Winner vs Baseline

| Metric | Baseline (0.25/0.45) | Winner (0.30/0.40) | Delta |
|--------|---------------------|-------------------|-------|
| Detections/image | 4.5 | 4.0 | -0.5 |
| Avg confidence | 0.713 | **0.767** | **+7.6%** |
| Unique classes | 4 | 4 | — |
| Quality score | ~0.394 | **0.398** | +1.0% |

**Selected:** conf=0.30, IoU=0.40 as the new default for threshold-optimized runs.

---

## Run #3 — Threshold Optimized (2026-02-12 20:45)

**Purpose:** Benchmark with the sweep-selected optimal thresholds.

| Setting | Value |
|---------|-------|
| Model | YOLOv8n-seg (nano) |
| Confidence threshold | **0.30** (was 0.25) |
| IoU threshold | **0.40** (was 0.45) |

### Results

| Metric | Value |
|--------|-------|
| Total detections | 8 |
| Avg detections / image | 4.0 |
| Avg inference | 33.95ms |
| Avg confidence | **0.767** |
| FPS | 29.5 |
| Quality score | 0.398 |

### Confidence Percentiles

```
Min ──── P10 ──── P25 ──── P50 ──── P75 ──── P90 ──── Max
0.405    0.581    0.774    0.840    0.858    0.860    0.861
                           (std: 0.151)
```

### Inference Percentiles

```
P50 ──── P95 ──── P99
33.95ms  37.10ms  37.38ms   (std: 3.50ms)
```

### Per-Class Confidence

| Class | Avg Confidence | Count |
|-------|---------------|-------|
| bus | 0.861 | 1 |
| person | 0.842 | 5 |
| tie | 0.656 | 1 |
| skateboard | 0.405 | 1 |

### Mask Statistics

| Metric | Value |
|--------|-------|
| Avg mask area | 61,067.2 px |

---

## Run #4 — Model Scale-Up (2026-02-12 20:52)

**Purpose:** Test whether upgrading from YOLOv8n (nano) to YOLOv8s (small) improves quality enough to justify the latency increase.

| Setting | Value |
|---------|-------|
| Model | **YOLOv8s-seg** (small, 11.8M params) |
| Confidence threshold | 0.30 |
| IoU threshold | 0.40 |

### Results

| Metric | Value |
|--------|-------|
| Total detections | 8 |
| Avg detections / image | 4.0 |
| Avg inference | **68.14ms** |
| Avg confidence | **0.843** |
| FPS | **14.7** |
| Quality score | 0.379 |

### Confidence Percentiles

```
Min ──── P10 ──── P25 ──── P50 ──── P75 ──── P90 ──── Max
0.631    0.706    0.839    0.886    0.900    0.915    0.925
                           (std: 0.097)
```

### Inference Percentiles

```
P50 ──── P95 ──── P99
68.14ms  78.15ms  79.04ms   (std: 11.12ms)
```

### Per-Class Confidence

| Class | Avg Confidence | Count |
|-------|---------------|-------|
| bus | **0.925** | 1 |
| person | 0.847 | 6 |
| tie | 0.738 | 1 |
| skateboard | *(not detected)* | 0 |

### Mask Statistics

| Metric | Value |
|--------|-------|
| Avg mask area | 64,171.0 px |

---

## Cross-Iteration Comparison

### Confidence Progression

| Iteration | Model | Min | Median | Max | Std |
|-----------|-------|-----|--------|-----|-----|
| 0 (Baseline) | nano | — | — | — | — |
| 1 (Optimized) | nano | 0.405 | 0.840 | 0.861 | 0.151 |
| 2 (Scale-Up) | small | 0.631 | 0.886 | 0.925 | 0.097 |

Trend: Each iteration improves median confidence and tightens the distribution.

### Inference Speed vs Confidence Trade-off

```
                Avg Confidence
  0.85 ─┤                                    ● Iter 2 (small)
        │
  0.80 ─┤
        │
  0.77 ─┤              ● Iter 1 (nano-opt)
        │
  0.71 ─┤  ● Iter 0 (nano-baseline)
        │
        └──┬──────────┬──────────┬──────────┬──
          20ms       35ms       50ms       70ms
                    Avg Inference Time
```

### Class Detection Across Iterations

| Class | Iter 0 | Iter 1 | Iter 2 |
|-------|--------|--------|--------|
| person | 6 | 5 | 6 |
| bus | 1 | 1 | 1 |
| tie | 1 | 1 | 1 |
| skateboard | 1 | 1 | **0** |

The small model misses the skateboard — a low-confidence edge case that the nano model's lower decision boundary catches.

---

## How to Run Your Own Benchmarks

### Standard Benchmark

```bash
python scripts/benchmark_vision.py \
  --version V0 \
  --iteration 3 \
  --tag "My Test" \
  --description "Testing with custom images" \
  --images-dir path/to/my/images \
  --conf-threshold 0.30 \
  --iou-threshold 0.40
```

Results are appended to `benchmark_results.json` and logged to the `model_evolution` database table.

### Threshold Sweep

```bash
python scripts/threshold_sweep.py --images-dir path/to/my/images
```

Results are saved to `sweep_results.json` and a ranked comparison is printed to stdout.

### Quality Score Formula

$$Q = \text{avg\_confidence} \times \sqrt{\frac{\text{unique\_classes}}{80}} \times \log_2(1 + \text{avg\_detections\_per\_image})$$

This balances precision (confidence), recall (class coverage), and detection density (with diminishing returns).

---

## Data Files Reference

| File | Format | Contents |
|------|--------|----------|
| `benchmark_results.json` | JSON array | All benchmark runs — one object per run with full metrics |
| `sweep_results.json` | JSON array | All 54 sweep configs with per-config metrics |
| SQLite `model_evolution` table | Database | Complete history with 50+ metrics columns (vision + LLM) |
| SQLite `recordings` table | Database | Video recording sessions linked to model evolution entries |
