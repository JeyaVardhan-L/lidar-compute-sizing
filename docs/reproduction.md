# Reproduce a result

Everything below runs from a clean clone on Linux (the v2 campaign ran on Ubuntu 26.04, Python 3.14).
Windows works too (CI runs both); replace `source .venv/bin/activate` with `.venv\Scripts\Activate.ps1`.

```bash
git clone https://github.com/JeyaVardhan-L/lidar-compute-sizing.git && cd lidar-compute-sizing
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[data,compiled]"                 # compiled = small_gicp wheel (C++ registration)
python -B -m unittest discover -s tests -v        # no datasets needed
```

## 1. Get the data (never committed; see docs/datasets.md)

| Data | How | Transfer |
|---|---|---|
| Oxford Spires window (public) | `python tools/fetch_spires.py --out <dir>` | ~240 MB |
| Newer College 2020 bag 9, Newer College 2021 quad-easy/medium/hard, stairs | Request access from the Oxford Robotics Institute. With the link you receive, fetch only the window you need: `python tools/fetch_bag_window.py --url <file-id-or-url> --out <dir>/point_clouds --start-unix <t> --duration-s 30` | ~1.6 GB per 30 s window of a 10 GB bag |

Window start times (declared in DEC-026): 2021 quads = ground-truth start + 120 s; stairs = + 30 s; bag 9 = whole bag.
Point the harness at your copies in a git-ignored `config.local.yaml`:

```yaml
dataset_roots:
  ncd21_quad_hard: /data/ncd21_quad_hard/point_clouds
  ncd21_quad_hard_gt: /data/gt-nc-quad-hard.csv
  # ... one pair per dataset id (see src/autonav_baseline/harness/config.py)
```

Check every new recording before emulating sensors from it: `python tools/check_layout.py --dataset ncd21_quad_hard`
(confirms how the organized scan is stored; exits non-zero on a mismatch).

## 2. Run

One run:
```bash
autonav run --dataset ncd21_quad_hard --variant c-gicp --profile laptop-4e --sensor 32b-45 --repeats 3
```

The whole campaign (150 runs, resumable, entries skipped when their label already completed):
```bash
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor   # recorded in run.json
python tools/run_matrix.py --phase A,B,C,D
python tools/sizing_analysis.py                    # -> artifacts/sizing/sizing.json
```
Do not run anything heavy at the same time: concurrent load corrupts timings. Profiles pin CPUs by Linux
numbering on the i5-13420H (0-7 performance threads, 8-11 efficiency cores); on another CPU, edit `PROFILES`.

Cloud tiers: Actions → `cloud-benchmark` → Run workflow (ARM Neoverse and x86 runners, same Spires workload).
Download its artifacts into `artifacts/runs/` before `sizing_analysis.py`.

## 3. Compare with published records
Poses, accepted-registration counts and accuracy are deterministic for every variant and match exactly on the
same inputs. Latency depends on CPU, clocks, governor, background load and library versions: expect the same
ordering and classes, not identical milliseconds, and compare per-repeat spread (`summary.json: repeat_spread`)
before calling a difference real.

## 4. Publish and view
```bash
autonav publish <run-id>                 # marks a run as publishable
python tools/export_site_data.py         # published runs + sizing.json -> site/public/data (scans for private data)
cd site && npm ci && npm run build && npm run check && npm run check:numbers
```

## 5. Measure a real board
On the candidate onboard computer (Raspberry Pi 5, Jetson, N100 box ...): install as above, copy one window,
and run `autonav run --dataset ncd21_quad_hard --variant c-gicp --profile pi5 --sensor <model> --repeats 3`.
The CPU model in `run.json` identifies the board; that measurement replaces the ASSUMED projection.
