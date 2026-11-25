#!/usr/bin/env python3
"""
Check how an organized Ouster scan is laid out in memory before emulating sensors from it (DEC-025).

For each candidate layout (row-major: index = row*W + col; column-major: index = col*H + row) the median
elevation of every row is compared with the calibrated beam altitude angles. The right layout gives
monotonically decreasing row elevations that match the calibration.

Usage: python tools/check_layout.py --dataset ncd21_quad_hard [--frames 5]
Writes artifacts/validation/layout_<dataset>.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from autonav_baseline.datasets.io import load_point_cloud_file, scan_sort_key  # noqa: E402
from autonav_baseline.harness.config import resolve_dataset  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--frames", type=int, default=5)
    a = ap.parse_args()
    ds = resolve_dataset(a.dataset)
    h, w = ds["organized"]
    alt = np.array(json.loads((REPO / ds["beam_altitudes"]).read_text())["beam_altitude_angles_deg"])
    files = sorted(Path(ds["frames"]).glob("*.pcd"), key=scan_sort_key)
    idx = np.linspace(0, len(files) - 1, min(a.frames, len(files))).astype(int)
    res = {"dataset": a.dataset, "configured_layout": ds.get("layout"), "organized": [h, w], "frames_checked": len(idx), "layouts": {}}
    for name in ("row-major", "column-major"):
        errs, mono = [], []
        for i in idx:
            xyz = load_point_cloud_file(files[i])[0].astype(float)
            r = np.linalg.norm(xyz, axis=1)
            el = np.degrees(np.arcsin(np.divide(xyz[:, 2], r, out=np.zeros_like(r), where=r > 0)))
            g, rr = (el.reshape(h, w), r.reshape(h, w)) if name == "row-major" else (el.reshape(w, h).T, r.reshape(w, h).T)
            med = np.array([np.median(g[k][rr[k] > 0.5]) if (rr[k] > 0.5).sum() > 10 else np.nan for k in range(h)])
            ok = ~np.isnan(med)
            errs.append(float(np.nanmedian(np.abs(med - alt))))
            mono.append(bool(np.all(np.diff(med[ok]) < 0.5)))
        res["layouts"][name] = {"median_abs_row_elevation_minus_beam_altitude_deg": float(np.median(errs)),
                                "rows_monotonic_in_all_frames": all(mono)}
    best = min(res["layouts"], key=lambda k: res["layouts"][k]["median_abs_row_elevation_minus_beam_altitude_deg"])
    res["detected_layout"] = best
    res["matches_configuration"] = best == ds.get("layout")
    out = REPO / "artifacts" / "validation" / f"layout_{a.dataset}.json"
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    return 0 if res["matches_configuration"] else 1


if __name__ == "__main__":
    sys.exit(main())
