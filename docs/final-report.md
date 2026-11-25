# Final report — LiDAR compute sizing (v2, 2026-11-26)

## 1. Question and answer

> Which LiDAR (points per second, beams, rate) and which onboard computer let scan-to-scan LiDAR odometry keep
> up with the sensor while leaving half of each frame period for the rest of the stack, and stay accurate?

| | Answer | Evidence |
|---|---|---|
| Declared rule (DEC-031) | **No sensor qualifies.** Every emulated sensor fails the hardest motion window (up to 34° of rotation between scans). The full 128-beam scan keeps tracking but drifts 11.6 % over 10 m (ATE 0.90 m); most cheaper sensors lose track. | MEASURED, rule declared before results |
| Sensor, walking-pace motion | **~655 k points/s at 10 Hz**: 64 beams over 90° (or 45°), or 128 beams × 512 columns. Drift 0.6-1.3 % over 10 m, ATE 0.06-0.10 m. 32 beams or fewer lose track at medium motion. | EMULATED, POST-HOC (DEC-036) |
| Compute for that sensor | **4 cores of N100 class**: four pinned E-cores (the N100's core) give P99 36.9 ms on medium and 39.8 ms on hard motion (≤ 50 ms rule); one E-core 116 / 125 ms (cannot keep up); one P-core 77 ms (keeps up, uses 77 % of the period). | MEASURED |
| Boards not measured | 4-core projection on hard motion: Jetson AGX Orin 48 ms (FEASIBLE), Jetson Orin NX 53 ms, RK3588 54 ms, Raspberry Pi 5 58 ms (all MARGINAL: they keep up but use more than half the period). | ASSUMED (published Geekbench 6 single-core ratios) |
| Fast-turning motion | Needs IMU-aided odometry (deskewing, rotation prior); neither more beams nor more compute fixes scan-to-scan LiDAR-only tracking at these rates. | MEASURED (all 9 sensor models, 2 rates) |

## 2. What was measured (168 runs)

| Phase | Runs | Content |
|---|---|---|
| A | 10 | Bag 9 (OS1-64, walking) and Oxford Spires (Hesai QT64): five implementations, laptop, 3-5 repeats |
| B | 18 | Compiled ICP/GICP (and tuned Python) on 1/4 P-cores and 1/4 E-cores, bag 9 and quad-hard |
| C | 110 | 9 emulated sensors × 4 motion windows × compiled ICP and GICP at 10 Hz, 5 sensors at 5 Hz, every sensor on 4 and 1 E-cores (quad-hard) |
| D | 12 | Voxel size 0.10-0.60 m (compiled GICP on quad-hard; tuned Python on bag 9) |
| E | 10 | Post-hoc: the 64-beam-class sensors on pinned P- and E-core tiers, medium and hard motion |
| cloud | 8 | ARM Neoverse-N2 and Intel Xeon 6975P-C GitHub runners (4 vCPU each), Spires, four implementations |

Machine: Intel Core i5-13420H (4 P-cores with SMT + 4 E-cores, 12 threads), 14.7 GB RAM, Ubuntu (Linux 7.0),
Python 3.14.4, NumPy 2.5.5, SciPy 1.18.1, small_gicp 1.0.1. `performance` governor, AC, sleep inhibited, nothing
else running; pre-run load median 3.2 %. All 160 local runs come from commit 69b5e25 with no code changes
(`dirty_code = false`); 17:14-22:14 UTC on 2026-11-25. Disturbances and re-runs: DEC-035, DEC-037.

## 3. Results

### 3.1 Implementation (bag 9, 271 scans, laptop)

| Implementation | median | P99 | late scans (> 100 ms) | ATE | RPE 10 m |
|---|---|---|---|---|---|
| Python ICP | 170 ms | 435 ms | 88 % | 0.51 m | 7.8 % |
| Python ICP, tuned | 59 ms | 162 ms | 10 % | 0.51 m | 7.8 % |
| Python point-to-plane | 186 ms | 256 ms | 100 % | 0.15 m | 2.5 % |
| Compiled ICP (same algorithm) | 14.5 ms | 70 ms* | 0.8 % | 0.55 m | 8.4 % |
| **Compiled GICP** | **16.5 ms** | 91 ms* | 0.2 % | **0.08 m** | **1.3 %** |

\* 12-thread unpinned profile; pinned to 4 P-cores compiled GICP has P99 30.9 ms, to 4 E-cores 48.5 ms (3.2).
Same algorithm, compiled vs Python: **11.7×**. Same laptop and Python code, v1 on Windows (Balanced plan,
shared) vs v2 on Ubuntu (fixed governor): 750 → 170 ms median (**4.4×**).

### 3.2 Sensors (compiled GICP, 10 Hz; RPE over 10 m, "lost" = < 90 % registrations accepted)

| Emulated sensor | points/s | easy | medium | hard | stairs |
|---|---|---|---|---|---|
| 128 beams, 90° (as recorded) | 1311 k | 0.72 % | 0.89 % | 11.65 % | 3.87 % |
| 128 beams × 512 columns | 655 k | 0.64 % | 0.84 % | 10.63 % | 4.05 % |
| 64 beams, 90° | 655 k | 0.84 % | 1.33 % | 11.16 % | 4.26 % |
| 64 beams, 45° (OS1-64 class) | 655 k | 0.82 % | 0.85 % | lost | 8.78 % |
| Mid-360 point budget (−7..+46°, 20 k/scan) | 200 k | 1.13 % | 1.16 % (296 of 299 accepted: one short of the 99 % rule) | lost | 5.78 % |
| 32 beams, 90° | 328 k | lost | lost | lost | 3.80 % |
| 32 beams, 45° | 328 k | 0.75 % (95 % accepted) | lost | lost | 8.98 % |
| 16 beams, 90° | 164 k | 12.22 % | lost | lost | 9.16 % |
| 16 beams, 30° (VLP-16 class) | 164 k | lost | lost | lost | 12.72 % |

At 5 Hz the full sensor tracks easy (0.54 %), medium (1.10 %) and stairs (1.57 %) and loses hard. Stairs has only
12.4 m of path, so its 10 m drift rests on few segments; its ATE stays 0.07-0.50 m for every sensor.

### 3.3 Compute (compiled GICP, P99 per scan, pinned tiers)

| Sensor, window | 1 E-core | 4 E-cores | 1 P-core | 4 P-cores |
|---|---|---|---|---|
| 64 beams 90°, medium | 116 ms | **36.9 ms** | — | 23.0 ms |
| 64 beams 90°, hard | 125 ms | **39.8 ms** | 77 ms | 25.3 ms |
| 128 × 512, hard | 170 ms | 53.1 ms | 102 ms | 34.2 ms |
| 128 beams (full), hard | 259 ms | 82.2 ms | 159 ms | 51.8 ms |
| OS1-64 (bag 9), walking | 156 ms | 48.5 ms | 94 ms | 30.9 ms |

Cost model (compiled GICP, runs that kept tracking): about **1.45 ms per 1000 points** surviving the 0.15 m voxel
filter on 4 E-cores and 4.5 ms on one (R² 0.85-0.88). Four cores are 2.9-3.1× one core.

### 3.4 Other measured findings

- **Pinning:** unpinned on 12 threads, compiled runs were bimodal (repeat medians up to 49× apart; e.g. 4.1 vs
  70.1 ms on stairs); pinned tiers agree within ~2 % (worst 10 %). Pin odometry threads to one core type.
- **Voxel size:** 0.25 m kept tracking on hard motion with more drift (13.2 %); 0.4 m and 0.6 m lost track (≤ 6 %
  accepted) although they cut points to a third. Python on bag 9 lost track at 0.4 m (72 % accepted).
- **Benchmark scaling:** single-core scores predict the P- vs E-core gap for compiled ICP on the hardest window (1.94× measured,
  1.90× predicted) but overstate it elsewhere (1.6× measured for GICP and for ICP on bag 9), so P-core-based projections are pessimistic.
- **ARM vs x86:** on the same Spires scans compiled GICP took 0.83× the x86 time on the ARM Neoverse-N2 runner.
- **Data rate:** the decoded OS0-128 point cloud is 6.3 MB per scan, 503 Mbit/s at 10 Hz (OS1-64: 252 Mbit/s).
- **Selective download:** 1.1-1.2 GB transferred per 30 s window instead of 6-11 GB per bag (11-18 %).

## 4. Problems found and fixed during the work

| Problem | How it was found | Fix | Record |
|---|---|---|---|
| Compiled ICP rejected 82 % of Spires scans (ATE 11 m) | First cloud run | Baseline stopping rule; gate residual computed as for Python | DEC-032 |
| 2021 hard motion exceeds the 20°/scan plausibility bound | Ground-truth validation before any odometry | 45° for 2021 datasets | DEC-033 |
| 2020 scans stored column-major despite their header | Row-elevation check | Explicit per-dataset layout + `check_layout.py` | DEC-025 |
| Stairs ground truth has 2 non-unit quaternions | Loader refused it | Documented renormalised copy | DEC-034 |
| `Infinity` in the site JSON; `@5hz` labels matched the e-mail scan | Site build / export | Strict JSON; tighter e-mail pattern | this report |
| Runs disturbed by downloads, another build, background load | Pre-run load, start/end times, build logs | Deleted and re-measured | DEC-035, DEC-037 |

## 5. Verification run

| Check | Result |
|---|---|
| `python -B -m unittest discover -s tests` | 86 tests OK (also in CI on Ubuntu and Windows, Python 3.11 and 3.13) |
| `npm run build` / `npm run check` | 9 pages; 0 errors, 0 warnings |
| `npm run check:numbers` | every rendered number equals the run records; no private path, Drive link or e-mail address in the build |
| Visual | headless Chrome at 1280 px: overview, sizing, hardware pages, all charts render |
| Repeat stability | pinned tiers: median repeat spread ~2 %; unpinned compiled runs flagged `timing_unstable` and excluded from sizing |

## 6. Not established

- No embedded board was measured; their numbers are projections (ASSUMED). Measure one candidate board with the
  same command before buying several.
- Emulated sensors reproduce beam count, FOV, points and rate, not optics, range noise, exact beam angles or a
  non-repetitive scan pattern (Livox).
- Handheld data: no platform vibration; motion profiles stand in for the target platform's.
- Scan-to-scan odometry only. IMU-aided LiDAR odometry and mapping add work per scan; the cost model is the
  starting point for sizing them.
- Rotation RPE is not reported (extrinsic-free RPE, DEC-012).

## 7. Next experiments

1. Run `c-gicp` with the 64-beam model on a real Raspberry Pi 5 and an N100 board (`--profile pi5`).
2. Add IMU-aided deskewing / a rotation prior and re-run quad-hard: the one failure the rules found.
3. Newer College 2021 collections 2-4 (park, cloister, underground mine) for scene variety.
4. A local map (scan-to-map) variant to size a full odometry stack, not only scan-to-scan.
