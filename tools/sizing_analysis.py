#!/usr/bin/env python3
"""
Turn the v2 measurement campaign into the sizing answer: which LiDAR, which onboard computer.

Reads every completed run whose label starts with "v2-" (artifacts/runs/, including cloud runs downloaded
from the cloud-benchmark workflow) and writes artifacts/sizing/sizing.json and site/public/data/sizing.json:

  rows         one row per run: emulated sensor, motion level, variant, compute tier, points, latency
               percentiles, share of the frame period, the declared real-time class (DEC-027) and accuracy
               class (DEC-028).
  cost_model   per (variant, tier): least-squares fit  total_ms = a + b * (points after voxel / 1000),
               on per-frame data, with R^2. MEASURED inputs, DERIVED fit.
  scaling      measured speed ratios between tiers (P-core vs E-core, 1 vs 4 cores, ARM vs x86 cloud) next to
               the ratio predicted by published single-core benchmark scores: a check of the projection method.
  projection   ASSUMED: P99 latency of the recommended sensor on boards that were not measured, scaled from
               the measured single-core tier by published Geekbench 6 single-core scores (sources listed).
  data_rate    MEASURED LiDAR output in Mbit/s from the bag windows (tools/fetch_bag_window.py manifests).

Nothing here re-runs a benchmark. Every number carries an evidence tag.
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
RUNS = REPO / "artifacts" / "runs"

FEASIBLE_SHARE = 50.0   # DEC-027: P99 <= 50 % of the frame period, no frame above the period
ADEQ = {"accepted_pct": 99.0, "rpe10_pct": 2.0, "ate_rmse_m": 0.30}  # DEC-028

MOTION = {"ncd21_quad_easy": "easy", "ncd21_quad_medium": "medium", "ncd21_quad_hard": "hard",
          "ncd21_stairs": "stairs", "newer_college_bag9": "walk (2020)", "oxford_spires": "walk (Spires)"}

# Published Geekbench 6 single-core scores (user-submitted results, approximate; ASSUMED inputs).
GB6 = {
    "i5-13420H P-core (this laptop)": {"score": 2200, "range": [2169, 2227],
        "src": ["https://browser.geekbench.com/v6/cpu/15989553", "https://browser.geekbench.com/v6/cpu/baseline/10753211"]},
    "Intel N100 (4x Gracemont, 3.4 GHz)": {"score": 1160, "range": [1100, 1230], "cores": 4,
        "src": ["https://browser.geekbench.com/v6/cpu/17041237"]},
    "Azure Cobalt 100 (GitHub ARM runner)": {"score": 1629, "range": [1629, 1629],
        "src": ["https://browser.geekbench.com/v6/cpu/baseline/9013329"]},
    "Jetson AGX Orin (12x A78AE)": {"score": 966, "range": [966, 966], "cores": 12,
        "src": ["https://browser.geekbench.com/v6/cpu/9113690"]},
    "Jetson Orin NX (8x A78AE)": {"score": 875, "range": [869, 913], "cores": 8,
        "src": ["https://browser.geekbench.com/v6/cpu/18785251", "https://browser.geekbench.com/v6/cpu/10489182"]},
    "RK3588 (4x A76 + 4x A55)": {"score": 852, "range": [852, 852], "cores": 4,
        "src": ["https://browser.geekbench.com/v6/cpu/baseline/8363422"]},
    "Raspberry Pi 5 (4x A76, 2.4 GHz)": {"score": 800, "range": [740, 833], "cores": 4,
        "src": ["https://browser.geekbench.com/v6/cpu/baseline/8820089", "https://browser.geekbench.com/v6/cpu/8840458"]},
}


def _load(run_dir: Path):
    try:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        summ = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    if run.get("status") != "completed" or not str(run.get("label", "")).startswith("v2-"):
        return None
    return run, summ


def _g(d, *keys):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def row_for(run, s, run_dir):
    sm = run.get("sensor_model") or {"id": "native", "label": "as recorded", "frame_stride": 1, "evidence": "REAL"}
    hz = run["dataset"]["nominal_hz"]
    period = 1000.0 / hz
    lat = s["latency_ms"]["total_ms"]
    viol = s["deadline"]["pipeline_total_ms"]
    acc = s.get("accuracy") or {}
    ate = _g(acc, "ate_m", "rmse")
    rpe10 = _g(acc, "rpe", "distance_10m", "translation_percent_of_length")
    accepted = _g(s, "registration", "accepted_percent")
    share = 100.0 * lat["p99"] / period
    if share <= FEASIBLE_SHARE and viol["violations"] == 0:
        rt = "FEASIBLE"
    elif lat["p99"] <= period:
        rt = "MARGINAL"
    else:
        rt = "INFEASIBLE"
    if ate is None or rpe10 is None or accepted is None:
        ac = "UNAVAILABLE"
    elif accepted >= ADEQ["accepted_pct"] and rpe10 <= ADEQ["rpe10_pct"] and ate <= ADEQ["ate_rmse_m"]:
        ac = "ADEQUATE"
    else:
        ac = "INADEQUATE"
    pts_raw = _g(s, "points_per_frame", "points_raw", "p50")
    pts_vox = _g(s, "points_per_frame", "points_voxel", "p50")
    label = run["label"]
    return {
        "run_id": run["run_id"], "label": label, "phase": label.split("-")[1],
        "dataset": run["dataset"]["id"], "motion": MOTION.get(run["dataset"]["id"], run["dataset"]["id"]),
        "sensor": {k: sm.get(k) for k in ("id", "label", "beams", "vfov_deg", "columns", "max_points", "evidence")},
        "rate_hz": hz, "period_ms": period, "variant": run["variant"], "profile": run["profile"]["id"],
        "cpu_model": run["environment"].get("cpu_model"), "arch": run["environment"].get("cpu_architecture"),
        "power": _g(run, "environment", "conditions_before_run", "power_plan"),
        "voxel_m": run["parameters"]["voxel_size"], "repeats": run["methodology"]["repeats"],
        "frames_measured": viol["of"],
        "points_raw_p50": pts_raw, "points_voxel_p50": pts_vox,
        "points_per_s": None if pts_raw is None else pts_raw * hz,
        "latency_ms": {k: lat[k] for k in ("p50", "p95", "p99", "max")},
        "preprocess_p50_ms": s["latency_ms"]["preprocess_ms"]["p50"], "register_p50_ms": s["latency_ms"]["register_ms"]["p50"],
        "repeat_p50_range_ms": [s["repeat_spread"]["p50"]["min"], s["repeat_spread"]["p50"]["max"]],
        "violations": viol["violations"], "violation_pct": viol["violation_percent"],
        "p99_share_of_period_pct": share, "realtime_class": rt,
        "accepted_pct": accepted, "ate_rmse_m": ate, "rpe10_pct": rpe10, "accuracy_class": ac,
        "iterations_p50": _g(s, "registration", "icp_iterations", "p50"),
        "peak_rss_mb": _g(s, "peak_rss_mb", "median"),
        "evidence": {"latency": "MEASURED", "classes": "DERIVED (declared rules DEC-027/028)",
                     "sensor": sm.get("evidence", "REAL")},
    }


def cost_model(rows_by_run):
    """total_ms = a + b * kpts_voxel per (variant, profile), from per-frame rep0 data."""
    groups = {}
    for r, run_dir in rows_by_run:
        if r["phase"] not in ("C", "A", "B") or r["voxel_m"] != 0.15:
            continue
        f = run_dir / "frames.csv"
        if not f.is_file():
            continue
        with open(f, newline="", encoding="utf-8") as fh:
            rows = [x for x in csv.DictReader(fh) if x["warmup"] == "0" and x["register_ms"] not in ("", "0.0")]
        g = groups.setdefault((r["variant"], r["profile"]), {"x": [], "y": [], "runs": 0})
        g["x"] += [float(x["points_voxel"]) / 1000.0 for x in rows]
        g["y"] += [float(x["total_ms"]) for x in rows]
        g["runs"] += 1
    out = []
    for (v, p), g in sorted(groups.items()):
        x, y = np.array(g["x"]), np.array(g["y"])
        if len(x) < 20 or np.ptp(x) == 0:
            continue
        A = np.c_[np.ones_like(x), x]
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        pred = A @ coef
        r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        out.append({"variant": v, "profile": p, "a_ms": float(coef[0]), "b_ms_per_kpt": float(coef[1]),
                    "r2": float(r2), "frames": int(len(x)), "runs": g["runs"],
                    "kpts_range": [float(x.min()), float(x.max())], "evidence": "DERIVED (fit to MEASURED frames)"})
    return out


def _find(rows, **kw):
    for r in rows:
        if all((r["sensor"]["id"] if k == "sensor" else r[k]) == v for k, v in kw.items()):
            return r
    return None


def scaling(rows):
    """Measured tier ratios on identical workloads vs ratios predicted from single-core scores."""
    out = []
    for ds in ("ncd21_quad_hard", "newer_college_bag9"):
        for v in ("c-gicp", "c-icp"):
            p1, e1 = _find(rows, dataset=ds, variant=v, profile="laptop-1c", sensor="native", voxel_m=0.15), \
                _find(rows, dataset=ds, variant=v, profile="laptop-1e", sensor="native", voxel_m=0.15)
            e4 = _find(rows, dataset=ds, variant=v, profile="laptop-4e", sensor="native", voxel_m=0.15)
            if p1 and e1:
                out.append({"what": f"P-core vs E-core, 1 thread ({ds}, {v})",
                            "measured_ratio_p50": e1["latency_ms"]["p50"] / p1["latency_ms"]["p50"],
                            "predicted_ratio": GB6["i5-13420H P-core (this laptop)"]["score"] / GB6["Intel N100 (4x Gracemont, 3.4 GHz)"]["score"],
                            "predicted_basis": "Geekbench 6 single-core, i5-13420H vs N100 (same E-core design as the laptop's E-cores)"})
            if e1 and e4:
                out.append({"what": f"4 E-cores vs 1 E-core ({ds}, {v})",
                            "measured_speedup_p50": e1["latency_ms"]["p50"] / e4["latency_ms"]["p50"],
                            "note": "how much of the frame cost the compiled pipeline spreads over 4 cores"})
    for v in ("c-gicp", "c-icp", "optimized", "baseline"):
        arm = _find(rows, dataset="oxford_spires", variant=v, profile="arm-cloud")
        x86 = _find(rows, dataset="oxford_spires", variant=v, profile="x86-cloud")
        lap = _find(rows, dataset="oxford_spires", variant=v, profile="laptop-full", voxel_m=0.15)
        if arm and x86:
            out.append({"what": f"ARM cloud vs x86 cloud (oxford_spires, {v})",
                        "measured_ratio_p50": arm["latency_ms"]["p50"] / x86["latency_ms"]["p50"],
                        "arm_cpu": arm["cpu_model"], "x86_cpu": x86["cpu_model"]})
        if arm and lap:
            out.append({"what": f"ARM cloud vs this laptop, all cores (oxford_spires, {v})",
                        "measured_ratio_p50": arm["latency_ms"]["p50"] / lap["latency_ms"]["p50"],
                        "arm_cpu": arm["cpu_model"]})
    return out


def projection(rows, sensor_id, dataset="ncd21_quad_hard", variant="c-gicp"):
    """ASSUMED: P99 on boards not measured = measured P-core single-thread P99 x (2200 / board score)."""
    p1 = _find(rows, dataset=dataset, variant=variant, profile="laptop-1c", sensor=sensor_id, voxel_m=0.15)
    e1 = _find(rows, dataset=dataset, variant=variant, profile="laptop-1e", sensor=sensor_id, voxel_m=0.15)
    if not p1:
        return None
    ref = GB6["i5-13420H P-core (this laptop)"]["score"]
    out = {"sensor": sensor_id, "dataset": dataset, "variant": variant,
           "anchor": {"profile": "laptop-1c", "p99_ms": p1["latency_ms"]["p99"], "p50_ms": p1["latency_ms"]["p50"]},
           "anchor_e_core": None if not e1 else {"profile": "laptop-1e", "p99_ms": e1["latency_ms"]["p99"]},
           "period_ms": p1["period_ms"], "boards": [],
           "evidence": "ASSUMED (single-thread scaling by published Geekbench 6 single-core scores; not measured)"}
    for name, b in GB6.items():
        f = ref / b["score"]
        lo, hi = ref / max(b["range"]), ref / min(b["range"])
        p99 = p1["latency_ms"]["p99"] * f
        out["boards"].append({"board": name, "gb6_single": b["score"], "factor": f,
                              "p99_single_thread_ms": p99, "p99_range_ms": [p1["latency_ms"]["p99"] * lo, p1["latency_ms"]["p99"] * hi],
                              "share_of_period_pct": 100 * p99 / p1["period_ms"],
                              "class_single_thread": "FEASIBLE" if 100 * p99 / p1["period_ms"] <= FEASIBLE_SHARE else (
                                  "MARGINAL" if p99 <= p1["period_ms"] else "INFEASIBLE"),
                              "sources": b["src"]})
    return out


def data_rates():
    out = []
    for m in sorted((REPO / "artifacts" / "validation").glob("fetch_*.json")):
        d = json.loads(m.read_text(encoding="utf-8"))
        tp = d.get("topic_payload_in_window", {})
        pts = tp.get(d["topic"], {})
        pkt = next((v for k, v in tp.items() if k.endswith("lidar_packets")), None)
        out.append({"window": m.stem.replace("fetch_", ""), "points_topic": d["topic"],
                    "pointcloud2_mbit_s": pts.get("mbit_per_s"), "raw_lidar_packets_mbit_s": pkt and pkt["mbit_per_s"],
                    "scans": d["scans_written"], "evidence": "MEASURED (payload bytes in the bag window)"})
    return out


def main() -> int:
    rows_by_run = []
    for rd in sorted(RUNS.glob("*")):
        got = _load(rd)
        if got:
            rows_by_run.append((row_for(*got, rd), rd))
    # one row per label: the most recent completed run wins (a label is re-run only after a failure)
    latest = {}
    for r, rd in rows_by_run:
        latest[r["label"]] = (r, rd)
    rows_by_run = list(latest.values())
    rows = [r for r, _ in rows_by_run]
    recommended = ["native", "64b-45", "32b-45", "16b-30", "mid360-budget", "32b-90", "64b-90"]
    out = {
        "generated_from_runs": len(rows),
        "rules": {"realtime": {"FEASIBLE": f"P99 <= {FEASIBLE_SHARE:.0f} % of the frame period and no frame above it",
                               "MARGINAL": "P99 <= frame period", "INFEASIBLE": "P99 > frame period", "decision": "DEC-027"},
                  "accuracy": {"ADEQUATE": f"accepted >= {ADEQ['accepted_pct']} %, RPE(10 m) <= {ADEQ['rpe10_pct']} %, ATE RMSE <= {ADEQ['ate_rmse_m']} m",
                               "decision": "DEC-028"}},
        "rows": rows,
        "cost_model": cost_model(rows_by_run),
        "scaling": scaling(rows),
        "projection": [p for p in (projection(rows, s) for s in recommended) if p],
        "gb6_sources": GB6,
        "data_rate": data_rates(),
    }
    for dest in (REPO / "artifacts" / "sizing" / "sizing.json", REPO / "site" / "public" / "data" / "sizing.json"):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"{len(rows)} v2 runs -> artifacts/sizing/sizing.json and site/public/data/sizing.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
