# LiDAR compute sizing

**Which LiDAR, and which onboard computer, can run real-time LiDAR odometry?** Measured on real recordings
with survey-grade ground truth, before any hardware is bought.

**Results site:** https://jeyavardhan-l.github.io/lidar-compute-sizing/ ·
**Full write-up:** [docs/final-report.md](docs/final-report.md) ·
**Every decision, before and after the results:** [docs/decision-log.md](docs/decision-log.md)

A robot that localises with LiDAR odometry must finish each scan before the next one arrives (100 ms at 10 Hz)
and still leave time for mapping, planning and control. This repository measures what that takes: how many
points the sensor must deliver, how much CPU that costs, and where the method itself stops working.

## Results (168 measured runs)

| | Finding | Evidence |
|---|---|---|
| 1 | **The language decided the first verdict, not the algorithm.** The same point-to-point ICP in compiled code takes **14.5 ms** per scan (median) instead of **170 ms** in Python: **11.7×** faster on the same scans and laptop. | MEASURED |
| 2 | **GICP is the method to run.** Compiled GICP: 16.5 ms median, **0.08 m** position error over 22.5 m (Python ICP: 0.51 m), 1.3 % drift per 10 m. | MEASURED |
| 3 | **Sensor: about 655 k points/s (64 beams at 10 Hz).** Emulated from a real 128-beam scan, 64 beams (90° or 45° FOV, or 128 × 512) stay within 2 % drift at walking-pace motion; **32 beams or fewer lose track** already at medium motion. A Livox Mid-360-like point budget (200 k points/s) is borderline: it passes easy motion and misses medium by one rejected scan of 299. | EMULATED, post-hoc (DEC-036) |
| 4 | **Compute: 4 cores of N100 class.** On four pinned efficiency cores (the N100's core design) that sensor needs **40 ms** per scan at the 99th percentile on the hardest motion, under the 50 ms half-budget; **one core needs 125 ms** and cannot keep up. | MEASURED |
| 5 | **Where the method stops.** With fast turns (up to 34° between scans) **every** sensor fails, even the full 128-beam scan (11.6 % drift over 10 m); most cheaper sensors lose track. No sensor passes the rule declared in advance. Fast-turning platforms need IMU-aided odometry; more beams or cores do not fix it. | MEASURED |
| 6 | **Pin the threads on a hybrid CPU.** Unpinned on all 12 hardware threads, the compiled pipeline is bimodal (repeat medians up to ~49× apart); pinned to one core type, repeats agree within ~2 %. | MEASURED |
| 7 | **Coarser voxels do not buy speed safely.** 0.4 m voxels cut the points to a third and tracking collapsed (6 % of registrations accepted). Size compute for 0.15-0.25 m. | MEASURED |
| 8 | **Operating conditions matter as much as code.** Same laptop, same Python code: 750 ms per scan on Windows (Balanced plan, shared machine) vs 170 ms on Ubuntu with a fixed governor (4.4×). | MEASURED |

Boards that were not measured (Raspberry Pi 5, Jetson Orin, RK3588) are projected from the measured tiers with
published single-core scores and tagged **ASSUMED**; the projection method itself is checked on measured pairs.
See the [sizing page](https://jeyavardhan-l.github.io/lidar-compute-sizing/sizing/).

## How

| Step | What | Where |
|---|---|---|
| Real data, selectively | Newer College 2020 (OS1-64) and 2021 (OS0-128), Oxford Spires. A ROS-bag reader fetches only the chunks of a 30 s window over HTTP range requests (~1.2 GB of a 10 GB recording). | `tools/fetch_bag_window.py`, `tools/fetch_spires.py` |
| Checked before use | Scan spacing, ground-truth coverage, motion; memory layout of every organized scan against the beam calibration (one dataset stores rows column-major despite its header). | `tools/validate_window.py`, `tools/check_layout.py` |
| Cheaper sensors from one real scan | Drop beam rows (count, vertical FOV), columns, returns or whole frames: 64/32/16 beams, OS1-, VLP-16- and Mid-360-like budgets, 5 Hz. | `src/autonav_baseline/lidar/sensor_emulation.py` |
| Five implementations, one frame loop | Python ICP (plain, tuned), Python point-to-plane, compiled ICP and GICP (small_gicp) share the validity gate, pose convention and timer. | `src/autonav_baseline/harness/variants*.py` |
| Pinned compute tiers | 1/4 performance cores, 1/4 efficiency cores; ARM Neoverse and x86 cloud runners on the same workload. Every run records CPU, governor, power state, background load, commit and changed files. | `harness/config.py`, `.github/workflows/arm-benchmark.yml` |
| Rules before results | "Keeps up" = P99 ≤ 50 % of the frame period; "accurate" = ≤ 2 % drift per 10 m, ATE ≤ 0.3 m, ≥ 99 % accepted; selection rule. Written down before the campaign; the one post-hoc analysis is labelled. | `docs/decision-log.md` DEC-027…036 |
| One declared campaign | 150 local runs, resumable, plus cloud runs; turned into a sizing table, cost model, scaling check and projection. | `tools/run_matrix.py`, `tools/sizing_analysis.py` |
| Static site, numbers checked | Astro + Plotly + three.js; a build step compares every rendered number with the run records. | `site/` |

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[data,compiled]"
python -B -m unittest discover -s tests          # 86 tests, no data needed
autonav run --dataset ncd21_quad_hard --variant c-gicp --profile laptop-4e --sensor 64b-90 --repeats 3
```

Data access, window selection and the full campaign: [docs/reproduction.md](docs/reproduction.md). Raw data is
never committed or redistributed.

## Limits

Handheld recordings stand in for a moving platform (its vibration and mounting are not represented).
Scan-to-scan odometry only: no IMU, no map, no loop closure. Emulated sensors match beam count, field of view,
points and rate, not optics, noise or scan pattern. Untested boards are projections. Details and every caveat:
[docs/final-report.md](docs/final-report.md).

## Credits and licences

Code: MIT. Data: Newer College Dataset (Ramezani et al., IROS 2020) and its Multi-Camera LiDAR-Inertial
extension (Zhang et al., 2021), Oxford Spires (Tao et al., 2025), all CC BY-NC-SA 4.0, by the Oxford Robotics
Institute. Compiled registration: [small_gicp](https://github.com/koide3/small_gicp) (Koide, MIT).
This repository grew out of an earlier team project; its history is preserved in git.
