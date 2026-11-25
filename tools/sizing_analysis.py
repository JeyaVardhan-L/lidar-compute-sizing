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
        # repeats whose medians differ by more than 10 % of their median: timing not reproducible (DEC-036)
        "timing_unstable": (s["repeat_spread"]["p50"]["max"] - s["repeat_spread"]["p50"]["min"]) > 0.10 * s["repeat_spread"]["p50"]["median"],
        "violations": viol["violations"], "violation_pct": viol["violation_percent"],
        "p99_share_of_period_pct": share, "realtime_class": rt,
        "accepted_pct": accepted, "ate_rmse_m": ate, "rpe10_pct": rpe10, "accuracy_class": ac,
        "iterations_p50": _g(s, "registration", "icp_iterations", "p50"),
        "peak_rss_mb": _g(s, "peak_rss_mb", "median"),
        "evidence": {"latency": "MEASURED", "classes": "DERIVED (declared rules DEC-027/028)",
                     "sensor": sm.get("evidence", "REAL")},
    }


def cost_model(rows_by_run):
    """total_ms = a + b * kpts_voxel per (variant, profile), from per-frame rep0 data.
    Only runs that kept tracking (>= 99 % accepted) and only pinned compute tiers: a lost track inflates frame
    time for reasons unrelated to point count, and the unpinned 12-thread profile is bimodal (DEC-036)."""
    groups = {}
    for r, run_dir in rows_by_run:
        if r["phase"] not in ("A", "B", "C", "E") or r["voxel_m"] != 0.15 or (r["accepted_pct"] or 0) < 99.0:
            continue
        if r["variant"].startswith("c-") and r["profile"] == "laptop-full":
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
    def lscpu_model(profile):  # recorded by the cloud workflow; Python cannot name ARM cores
        f = REPO / "artifacts" / "validation" / f"lscpu_{profile}.txt"
        if f.is_file():
            for line in f.read_text().splitlines():
                if line.startswith("Model name:"):
                    return line.split(":", 1)[1].strip()
        return None
    for v in ("c-gicp", "c-icp", "optimized", "baseline"):
        arm = _find(rows, dataset="oxford_spires", variant=v, profile="arm-cloud")
        x86 = _find(rows, dataset="oxford_spires", variant=v, profile="x86-cloud")
        if arm and x86:
            out.append({"what": f"ARM cloud vs x86 cloud, 4 vCPUs each (oxford_spires, {v})",
                        "measured_ratio_p50": arm["latency_ms"]["p50"] / x86["latency_ms"]["p50"],
                        "arm_cpu": lscpu_model("arm-cloud") or arm["cpu_model"],
                        "x86_cpu": lscpu_model("x86-cloud") or x86["cpu_model"]})
    return out


def projection(rows, sensor_id, dataset="ncd21_quad_hard", variant="c-gicp"):
    """ASSUMED projection to boards that were not measured, from two measured anchors:
    1 thread:  P99 on one laptop P-core x (P-core score / board score)
    4 cores:   P99 on four laptop E-cores x (N100 score / board score); E-cores = N100's core (DEC-029).
    Board scores are published Geekbench 6 single-core results (sources listed)."""
    p1 = _find(rows, dataset=dataset, variant=variant, profile="laptop-1c", sensor=sensor_id, voxel_m=0.15)
    e4 = _find(rows, dataset=dataset, variant=variant, profile="laptop-4e", sensor=sensor_id, voxel_m=0.15)
    if not (p1 or e4):
        return None
    ref_p, ref_e = GB6["i5-13420H P-core (this laptop)"]["score"], GB6["Intel N100 (4x Gracemont, 3.4 GHz)"]["score"]
    period = (p1 or e4)["period_ms"]
    cls = lambda ms: "FEASIBLE" if 100 * ms / period <= FEASIBLE_SHARE else ("MARGINAL" if ms <= period else "INFEASIBLE")
    out = {"sensor": sensor_id, "dataset": dataset, "variant": variant, "period_ms": period, "boards": [],
           "anchor_1_thread": p1 and {"profile": "laptop-1c", "p99_ms": p1["latency_ms"]["p99"]},
           "anchor_4_cores": e4 and {"profile": "laptop-4e", "p99_ms": e4["latency_ms"]["p99"]},
           "evidence": "ASSUMED (scaled by published Geekbench 6 single-core scores; not measured)"}
    for name, b in GB6.items():
        row = {"board": name, "gb6_single": b["score"], "cores": b.get("cores"), "sources": b["src"]}
        if p1:
            v = p1["latency_ms"]["p99"] * ref_p / b["score"]
            row.update(p99_1t_ms=v, p99_1t_range_ms=[p1["latency_ms"]["p99"] * ref_p / max(b["range"]), p1["latency_ms"]["p99"] * ref_p / min(b["range"])],
                       class_1t=cls(v))
        if e4 and (b.get("cores") or 0) >= 4:
            v = e4["latency_ms"]["p99"] * ref_e / b["score"]
            row.update(p99_4c_ms=v, p99_4c_range_ms=[e4["latency_ms"]["p99"] * ref_e / max(b["range"]), e4["latency_ms"]["p99"] * ref_e / min(b["range"])],
                       class_4c=cls(v), share_4c_pct=100 * v / period)
        out["boards"].append(row)
    return out


WINDOWS21 = ["ncd21_quad_easy", "ncd21_quad_medium", "ncd21_quad_hard", "ncd21_stairs"]
TIER_ORDER = ["laptop-1e", "laptop-4e", "laptop-full"]


def recommendation(rows):
    """DEC-031, applied mechanically."""
    by_sensor = {}
    for r in rows:
        if r["phase"] == "C" and r["variant"] == "c-gicp" and r["profile"] == "laptop-full" and r["dataset"] in WINDOWS21:
            by_sensor.setdefault(r["sensor"]["id"], {})[r["dataset"]] = r
    cands = []
    for sid, per in by_sensor.items():
        if set(per) != set(WINDOWS21):
            continue
        ok = all(per[d]["accuracy_class"] == "ADEQUATE" for d in WINDOWS21)
        pps = float(np.median([per[d]["points_per_s"] for d in WINDOWS21]))
        vfov = per["ncd21_quad_hard"]["sensor"].get("vfov_deg") or [0, 0]
        cands.append({"sensor": sid, "label": per["ncd21_quad_hard"]["sensor"]["label"], "adequate_all": ok,
                      "points_per_s": pps, "rate_hz": per["ncd21_quad_hard"]["rate_hz"],
                      "vfov_span_deg": float(vfov[1] - vfov[0]),
                      "per_window": {d: {"accuracy_class": per[d]["accuracy_class"], "ate_rmse_m": per[d]["ate_rmse_m"],
                                         "rpe10_pct": per[d]["rpe10_pct"], "accepted_pct": per[d]["accepted_pct"]} for d in WINDOWS21}})
    out = {"rule": "DEC-031", "candidates": sorted(cands, key=lambda c: (c["rate_hz"], c["points_per_s"]))}
    for hz in (10.0, 5.0):
        ok = [c for c in cands if c["adequate_all"] and c["rate_hz"] == hz]
        ok.sort(key=lambda c: (c["points_per_s"], -c["vfov_span_deg"]))
        pick = ok[0] if ok else None
        tiers = []
        if pick:
            for t in TIER_ORDER:
                r = _find(rows, dataset="ncd21_quad_hard", variant="c-gicp", profile=t, sensor=pick["sensor"], voxel_m=0.15)
                if r:
                    tiers.append({"profile": t, "p99_ms": r["latency_ms"]["p99"], "share_pct": r["p99_share_of_period_pct"],
                                  "class": r["realtime_class"], "violations": r["violations"]})
        weakest = next((t for t in tiers if t["class"] == "FEASIBLE"), None)
        out[f"at_{int(hz)}hz"] = {"sensor": pick, "tiers_on_quad_hard": tiers, "weakest_feasible_measured_tier": weakest}
    return out


ENVELOPE = ["ncd21_quad_easy", "ncd21_quad_medium"]
PINNED = ["laptop-1e", "laptop-4e", "laptop-1c", "laptop-4c"]


def posthoc(rows):
    """DEC-036 (written after the results): the same rules on the motion envelope where scan-to-scan LiDAR-only
    odometry can work at all (easy and medium: up to ~53 deg/s at the 95th percentile), and only pinned tiers."""
    by = {}
    for r in rows:
        if r["phase"] == "C" and r["variant"] == "c-gicp" and r["profile"] == "laptop-full" and r["dataset"] in ENVELOPE:
            by.setdefault(r["sensor"]["id"], {})[r["dataset"]] = r
    cands = []
    for sid, per in by.items():
        if set(per) != set(ENVELOPE):
            continue
        cands.append({"sensor": sid, "label": per[ENVELOPE[0]]["sensor"]["label"], "rate_hz": per[ENVELOPE[0]]["rate_hz"],
                      "points_per_s": float(np.median([per[d]["points_per_s"] for d in ENVELOPE])),
                      "adequate_envelope": all(per[d]["accuracy_class"] == "ADEQUATE" for d in ENVELOPE),
                      "vfov_span_deg": float(np.diff(per[ENVELOPE[0]]["sensor"].get("vfov_deg") or [0, 0])[0])})
    out = {"rule": "DEC-036 (post-hoc)", "envelope": ENVELOPE, "candidates": sorted(cands, key=lambda c: (c["rate_hz"], c["points_per_s"]))}
    for hz in (10.0, 5.0):
        # equal points per second: prefer the lower measured P99 on the hardest window with 4 pinned E-cores
        # (a sensor that lost track there sorts last); the FOV tie-break of DEC-031 separated 91 deg from 92 deg
        def hard_cost(c):
            r = _find(rows, dataset="ncd21_quad_hard", variant="c-gicp", profile="laptop-4e", sensor=c["sensor"], voxel_m=0.15)
            return r["latency_ms"]["p99"] if r and (r["accepted_pct"] or 0) >= 99.0 else None  # None: lost track / not run
        for c in cands:
            c["hard_4e_p99_ms"] = hard_cost(c)
        ok = sorted([c for c in cands if c["adequate_envelope"] and c["rate_hz"] == hz],
                    key=lambda c: (c["points_per_s"], c["hard_4e_p99_ms"] if c["hard_4e_p99_ms"] is not None else float("inf"), -c["vfov_span_deg"]))
        pick = ok[0] if ok else None
        alts = [c for c in ok[1:] if pick and c["points_per_s"] == pick["points_per_s"]]
        res = {"sensor": pick, "same_cost_alternatives": alts, "tiers": {}}
        if pick:
            for ds in ("ncd21_quad_medium", "ncd21_quad_hard"):
                tl = []
                for t in PINNED:
                    r = _find(rows, dataset=ds, variant="c-gicp", profile=t, sensor=pick["sensor"], voxel_m=0.15)
                    if r:
                        tl.append({"profile": t, "p50_ms": r["latency_ms"]["p50"], "p99_ms": r["latency_ms"]["p99"],
                                   "share_pct": r["p99_share_of_period_pct"], "class": r["realtime_class"],
                                   "tracking_held": (r["accepted_pct"] or 0) >= 99.0})
                res["tiers"][ds] = tl
            feas = [t for t in PINNED if all(any(x["profile"] == t and x["class"] == "FEASIBLE" for x in res["tiers"].get(ds, []))
                                             for ds in ("ncd21_quad_medium", "ncd21_quad_hard"))]
            res["weakest_feasible_pinned_tier"] = feas[0] if feas else None
        out[f"at_{int(hz)}hz"] = res
    return out


def headline(rows):
    """Named scalar values the site renders through <Num file="sizing"> (checked by check-numbers)."""
    h = {}
    for v in ("baseline", "optimized", "p2plane", "c-icp", "c-gicp"):
        r = _find(rows, dataset="newer_college_bag9", variant=v, profile="laptop-full", phase="A")
        if r:
            key = v.replace("-", "_")
            h[f"bag9_{key}_p50_ms"] = r["latency_ms"]["p50"]
            h[f"bag9_{key}_p99_ms"] = r["latency_ms"]["p99"]
            h[f"bag9_{key}_ate_m"] = r["ate_rmse_m"]
            h[f"bag9_{key}_viol_pct"] = r["violation_pct"]
    if "bag9_baseline_p50_ms" in h and "bag9_c_icp_p50_ms" in h:
        h["python_over_compiled_same_algorithm"] = h["bag9_baseline_p50_ms"] / h["bag9_c_icp_p50_ms"]
    nat = _find(rows, dataset="ncd21_quad_hard", variant="c-gicp", profile="laptop-full", sensor="native", phase="C")
    if nat:
        h["hard_native_rpe10_pct"] = nat["rpe10_pct"]
        h["hard_native_ate_m"] = nat["ate_rmse_m"]
    ph = posthoc(rows)["at_10hz"]
    if ph.get("sensor"):
        h["posthoc_points_per_s_k"] = ph["sensor"]["points_per_s"] / 1000.0
        for t in ("laptop-4e", "laptop-1e", "laptop-4c", "laptop-1c"):
            for ds, key in (("ncd21_quad_hard", "hard"), ("ncd21_quad_medium", "medium")):
                r = _find(rows, dataset=ds, variant="c-gicp", profile=t, sensor=ph["sensor"]["sensor"], voxel_m=0.15)
                if r:
                    h[f"posthoc_{key}_{t[7:]}_p99_ms"] = r["latency_ms"]["p99"]
        h["posthoc_weakest_tier"] = ph.get("weakest_feasible_pinned_tier")
    full = [r for r in rows if r["variant"].startswith("c-") and r["profile"] == "laptop-full" and r["repeat_p50_range_ms"][0] > 0]
    if full:
        h["unpinned_max_spread_x"] = max(r["repeat_p50_range_ms"][1] / r["repeat_p50_range_ms"][0] for r in full)
    pe = [r for r in rows if r["variant"].startswith("c-") and r["profile"] in ("laptop-4e", "laptop-1e")]
    if pe:
        h["pinned_e_max_spread_pct"] = max(100 * (r["repeat_p50_range_ms"][1] - r["repeat_p50_range_ms"][0]) / r["repeat_p50_range_ms"][0] for r in pe)
    v1 = REPO / "artifacts" / "history" / "v1_windows_runs.json"
    if v1.is_file() and "bag9_baseline_p50_ms" in h:
        old = next((r for r in json.loads(v1.read_text())["runs"] if r["dataset"] == "newer_college_bag9" and r["variant"] == "baseline"
                    and r["profile"] == "laptop-full" and r["mode"] == "pipeline"), None)
        if old:
            h["v1_windows_bag9_baseline_p50_ms"] = old["p50_ms"]
            h["windows_over_ubuntu_same_laptop"] = old["p50_ms"] / h["bag9_baseline_p50_ms"]
    for t in ("laptop-full", "laptop-4c", "laptop-1c", "laptop-4e", "laptop-1e"):
        r = _find(rows, dataset="ncd21_quad_hard", variant="c-gicp", profile=t, sensor="native", voxel_m=0.15)
        if r:
            h[f"hard_native_cgicp_{t.replace('-', '_')}_p99_ms"] = r["latency_ms"]["p99"]
            h[f"hard_native_cgicp_{t.replace('-', '_')}_share_pct"] = r["p99_share_of_period_pct"]
    return h


def data_rates():
    """MEASURED PointCloud2 rate in each fetched window. Only the point-cloud topic is complete: the fetcher
    downloads only chunks that contain it, so other topics in those windows are undercounted and not reported."""
    out = []
    for m in sorted((REPO / "artifacts" / "validation").glob("fetch_*.json")):
        d = json.loads(m.read_text(encoding="utf-8"))
        pts = d.get("topic_payload_in_window", {}).get(d["topic"], {})
        if not pts:
            continue
        span = d.get("window_span_s") or (d["window_s"][1] - d["window_s"][0])
        out.append({"window": m.stem.replace("fetch_", ""), "points_topic": d["topic"], "scans": d["scans_written"],
                    "pointcloud2_mbit_s": pts["mbit_per_s"], "mbytes_per_scan": pts["bytes"] / max(pts["messages"], 1) / 1e6,
                    "scans_per_s": pts["messages"] / span,
                    "bag_fraction_downloaded_pct": 100.0 * d["bytes_transferred"] / d["bag_size_bytes"],
                    "evidence": "MEASURED (payload bytes of the point-cloud topic in the bag window)"})
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
    recommended = ["64b-90", "128b-90-512c", "native"]
    out = {
        "generated_from_runs": len(rows),
        "rules": {"realtime": {"FEASIBLE": f"P99 <= {FEASIBLE_SHARE:.0f} % of the frame period and no frame above it",
                               "MARGINAL": "P99 <= frame period", "INFEASIBLE": "P99 > frame period", "decision": "DEC-027"},
                  "accuracy": {"ADEQUATE": f"accepted >= {ADEQ['accepted_pct']} %, RPE(10 m) <= {ADEQ['rpe10_pct']} %, ATE RMSE <= {ADEQ['ate_rmse_m']} m",
                               "decision": "DEC-028"}},
        "rows": rows,
        "cost_model": cost_model(rows_by_run),
        "scaling": scaling(rows),
        "projection": [p for p in (projection(rows, s, ds) for s in recommended for ds in ("ncd21_quad_medium", "ncd21_quad_hard")) if p],
        "gb6_sources": GB6,
        "data_rate": data_rates(),
        "recommendation": recommendation(rows),
        "posthoc": posthoc(rows),
    }
    out["headline"] = headline(rows)
    for dest in (REPO / "artifacts" / "sizing" / "sizing.json", REPO / "site" / "public" / "data" / "sizing.json"):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(out, indent=1, default=float, allow_nan=False), encoding="utf-8")  # strict JSON for the site
    print(f"{len(rows)} v2 runs -> artifacts/sizing/sizing.json and site/public/data/sizing.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
