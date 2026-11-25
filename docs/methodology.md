# Measurement methodology

## Timing boundaries
All times are `time.perf_counter` wall clock inside a single worker process.

| Column | Meaning |
|---|---|
| `load_ms` | reading one frame from disk |
| `preprocess_ms` | invalid-point removal + range filter + voxel downsample |
| `register_ms` | ICP + validity gate + pose update (`p2plane` includes normal estimation; compiled variants include the gate's nearest-neighbour pass) |
| `total_ms` | `preprocess_ms + register_ms`: pipeline latency for a frame already in memory (**primary**) |
| `e2e_ms` | `load_ms + total_ms`: includes file I/O that a live sensor driver would not pay |

## Procedure
- Each repeat is a complete run in a **fresh process** (default 3 repeats). Thread limits (`OMP/OPENBLAS/MKL_NUM_THREADS`) and CPU affinity are applied before NumPy loads. The worker records its own effective environment into `run.json`.
- The initial reference frame (no registration) and `--warmup` frames (default 3) are excluded from latency statistics but still contribute to the trajectory.
- Percentiles: `numpy.percentile`, linear interpolation, pooled over repeats; per-repeat values and their spread are in `summary.json`.
- **Deadline**: the sensor period (100 ms at 10 Hz). A frame violates it if `total_ms` is strictly greater. The headline statistic is the **violation rate**. A P95 below the deadline is never reported as "meets the deadline" without it, because it still allows 5 % of frames to miss.
- Throughput: frames divided by loop wall time (file loading included). Peak memory: process peak working set. Machine RAM is a specification, not a measurement.
- Garbage collection is not disabled. v1 (Windows) did not control clocks; v2 (Ubuntu) runs with the `performance` governor and records governor, energy-performance preference and AC state in every `run.json`. Sustained clock under load is not measured.
- Sensor emulation happens before the timer starts: the sensor would deliver the reduced scan, so its cost is not the computer's.

## Accuracy
Poses are associated with ground truth by timestamp (nearest within 20 ms, one-to-one). **ATE**: position RMSE after a rigid SE(3) Umeyama alignment (no scale). **RPE**: position error of the displacement over fixed time windows (1 s, 5 s) and ground-truth path-length windows (5 m, 10 m), in the aligned world frame. Rotation RPE is UNAVAILABLE because the ground-truth body frame differs from the sensor frame (DEC-012). A short, nearly straight window can be aligned even when reversed, so the pose convention is verified separately by unit tests against hand-derived poses.

## Variants
| Variant | Implementation | Algorithm |
|---|---|---|
| `baseline` | Python + NumPy + SciPy k-d tree | point-to-point ICP, identity initial guess |
| `optimized` | same, faster voxel filter, cached tree, threaded queries | identical result to `baseline` (tested) |
| `p2plane` | Python | point-to-plane ICP, constant-velocity guess |
| `c-icp` | C++ (small_gicp), one solver iteration per call | the `baseline` algorithm and stopping rule (DEC-032) |
| `c-gicp` | C++ (small_gicp) | Generalized-ICP, constant-velocity guess |

## Sensor emulation (DEC-025)
From an organized OS0-128 scan (128 rows = beams ordered by elevation, 1024 columns): keep a subset of rows
(beam count and vertical FOV), every k-th column, a capped number of returns, or every k-th frame (frame rate;
the deadline becomes the new period). The memory layout of every recording is checked against the beam
calibration first (`tools/check_layout.py`). Not emulated: optics, noise, exact beam angles, maximum range,
non-repetitive scan patterns.

## Compute profiles
| Profile | How | Allowed claim |
|---|---|---|
| `laptop-full` | no limits (i5-13420H, 12 threads) | development-laptop performance |
| `laptop-4c`, `laptop-1c` | CPU affinity on performance cores + thread env vars | scaling with core count |
| `laptop-4e`, `laptop-1e` | CPU affinity on efficiency cores (Gracemont, 3.4 GHz) | a labelled proxy for Intel N100-class compute (same core and peak clock; different cache, memory, sustained power) |
| `arm-cloud`, `x86-cloud` | GitHub Actions runners, same Spires workload | real ARM Neoverse / x86 server VMs, shared and noisy; **not** drone computers |
| `pi5` | the same CLI on a real board | UNAVAILABLE until measured |

Boards that were not measured are projected by scaling the measured single performance-core P99 with published
Geekbench 6 single-core scores (`ASSUMED`, sources in `artifacts/sizing/sizing.json`). The projection method is
checked on measured pairs (performance vs efficiency core; ARM vs x86 cloud) before it is used.

## Sizing rules (declared before results)
- Real time (DEC-027): FEASIBLE = P99 ≤ 50 % of the frame period and no frame above the period; MARGINAL = P99 ≤ period.
- Accuracy (DEC-028): ADEQUATE = ≥ 99 % registrations accepted, RPE over 10 m ≤ 2 %, ATE RMSE ≤ 0.30 m on the 30 s window.
- Recommendation (DEC-031): fewest points per second ADEQUATE on all four motion windows; then the weakest measured tier that is FEASIBLE with it on the hardest window.

## Verdicts
Generated by `src/autonav_baseline/harness/verdict.py` from `summary.json` with explicit rules (rule text and evidence are stored with each verdict). Deadline: pass = 0 violations; warn = up to 5 %; fail = above 5 %. Registration: pass >= 99 % accepted; warn >= 90 %. Accuracy is described, not graded.

## Evidence classes
`MEASURED`, `DERIVED`, `DECLARED`, `ASSUMED`, `UNAVAILABLE`, `UNVERIFIED`; data kinds `REAL`, `NON-CONSECUTIVE`, `SYNTHETIC` (never published).