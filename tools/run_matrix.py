#!/usr/bin/env python3
"""
Run the study's measurement campaign as one declared matrix (reproducible, resumable).

Every entry is one `autonav run`. An entry whose label already has a completed run in artifacts/runs/ is
skipped, so the campaign can be interrupted and resumed. Entries whose dataset is not on disk are reported
and skipped. The matrix is declared here, before any result is seen, and is not edited to remove runs that
turn out badly.

Usage:
    python tools/run_matrix.py [--phase A,B,C,D] [--dry-run]
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from autonav_baseline.harness.config import resolve_dataset  # noqa: E402

TAG = "v2"
QUADS = ["ncd21_quad_easy", "ncd21_quad_medium", "ncd21_quad_hard", "ncd21_stairs"]
SENSORS = ["native", "128b-90-512c", "64b-90", "32b-90", "16b-90", "64b-45", "32b-45", "16b-30", "mid360-budget"]


def matrix():
    m = []
    # A. Continuity: the previously published comparisons, re-measured on Ubuntu with a fixed governor,
    #    plus the two compiled variants. p2plane on bag 9 gets the 5-repeat controlled run that was interrupted.
    for ds in ["newer_college_bag9", "oxford_spires"]:
        for v in ["baseline", "optimized", "p2plane", "c-icp", "c-gicp"]:
            reps = 5 if (v == "p2plane" and ds == "newer_college_bag9") or v.startswith("c-") else 3
            m.append(dict(phase="A", dataset=ds, variant=v, profile="laptop-full", repeats=reps))
    # B. Compute tiers: performance cores (4, 1) and efficiency cores (4 = N100-class proxy, 1).
    for prof in ["laptop-4c", "laptop-1c", "laptop-4e", "laptop-1e"]:
        for v in ["c-icp", "c-gicp"]:
            m.append(dict(phase="B", dataset="newer_college_bag9", variant=v, profile=prof, repeats=3))
            m.append(dict(phase="B", dataset="ncd21_quad_hard", variant=v, profile=prof, repeats=3))
        if prof in ("laptop-1c", "laptop-4e"):
            m.append(dict(phase="B", dataset="newer_college_bag9", variant="optimized", profile=prof, repeats=3))
    # C. Sensor sweep: emulated sensors x motion difficulty, production-style variant (c-gicp) and c-icp.
    for ds in QUADS:
        for s in SENSORS:
            for v in ["c-gicp", "c-icp"]:
                m.append(dict(phase="C", dataset=ds, variant=v, profile="laptop-full", repeats=3, sensor=s))
        for s in ["native@5hz", "64b-45@5hz", "32b-45@5hz", "16b-30@5hz", "mid360-budget@5hz"]:
            m.append(dict(phase="C", dataset=ds, variant="c-gicp", profile="laptop-full", repeats=3, sensor=s))
    # C2. The same sensors on the N100-class proxy and one slow core (the sizing question), hardest motion.
    for prof in ["laptop-4e", "laptop-1e"]:
        for s in SENSORS:
            m.append(dict(phase="C", dataset="ncd21_quad_hard", variant="c-gicp", profile=prof, repeats=3, sensor=s))
    # D. Voxel size: latency/accuracy frontier.
    for vox in [0.1, 0.25, 0.4, 0.6]:
        for s in ["native", "32b-45"]:
            m.append(dict(phase="D", dataset="ncd21_quad_hard", variant="c-gicp", profile="laptop-full",
                          repeats=3, sensor=s, voxel=vox))
        m.append(dict(phase="D", dataset="newer_college_bag9", variant="optimized", profile="laptop-full",
                      repeats=3, voxel=vox))
    for e in m:
        e.setdefault("sensor", "native")
        e.setdefault("voxel", 0.15)
        e["label"] = (f"{TAG}-{e['phase']}-{e['dataset']}-{e['sensor']}-{e['variant']}-{e['profile']}"
                      f"-vox{e['voxel']}")
    return m


def dataset_ready(ds_id):
    """Frames present and complete: ground truth on disk (when configured) and, for windows fetched from a bag,
    the fetch manifest that tools/fetch_bag_window.py writes only after the last scan."""
    ds = resolve_dataset(ds_id)
    frames = Path(ds["frames"])
    if not frames.is_dir():
        return False
    if ds.get("gt") and not Path(ds["gt"]).is_file():
        return False
    if any(frames.glob("cloud_*.pcd")) and ds_id != "newer_college_bag9" and not (frames / "fetch_manifest.json").is_file():
        return False
    if ds_id == "newer_college_bag9" and not (frames / "fetch_manifest.json").is_file():
        return False
    return True


def completed_labels():
    done = set()
    for rj in (REPO / "artifacts" / "runs").glob("*/run.json"):
        try:
            r = json.loads(rj.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r.get("status") == "completed" and r.get("label"):
            done.add(r["label"])
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="A,B,C,D")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    phases = set(a.phase.split(","))
    todo = [e for e in matrix() if e["phase"] in phases]
    done = completed_labels()
    exe = [sys.executable, "-B", "-m", "autonav_baseline"]
    t_all = time.time()
    skipped_missing = []
    for k, e in enumerate(todo, 1):
        if e["label"] in done:
            continue
        if not dataset_ready(e["dataset"]):
            skipped_missing.append(e["label"])
            continue
        cmd = exe + ["run", "--dataset", e["dataset"], "--variant", e["variant"], "--profile", e["profile"],
                     "--repeats", str(e["repeats"]), "--sensor", e["sensor"], "--voxel", str(e["voxel"]),
                     "--label", e["label"]]
        print(f"[{k}/{len(todo)}] {e['label']}", flush=True)
        if a.dry_run:
            continue
        t0 = time.time()
        rc = subprocess.run(cmd, cwd=REPO).returncode
        print(f"    rc={rc}  {time.time() - t0:.0f} s", flush=True)
    print(f"finished in {time.time() - t_all:.0f} s; missing data for {len(skipped_missing)} entries")
    for lbl in skipped_missing:
        print("  missing:", lbl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
