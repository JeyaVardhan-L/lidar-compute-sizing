"""
Emulate a cheaper / different LiDAR from a real organized scan of a higher-resolution one.

An Ouster organized cloud has H rows (one per beam, ordered by elevation, top first) and W columns (azimuth
steps). Dropping rows changes the beam count and vertical FOV, dropping columns the horizontal resolution,
capping returns the point budget, and dropping whole frames the frame rate (see the worker).

What this does NOT emulate: the target's optics and range noise, its exact beam elevations (the nearest real
beam is used), maximum range, intensity response, or a non-repetitive scan pattern (Livox). Results from an
emulated model are labelled EMULATED and say which real sensor they were derived from.
"""

from typing import Any, Dict, List, Optional, Sequence

import numpy as np


def select_rows(spec: str, altitudes_deg: Sequence[float]) -> np.ndarray:
    alt = np.asarray(altitudes_deg, dtype=float)
    h = len(alt)
    kind, *args = spec.split(":")
    if kind == "all":
        return np.arange(h)
    if kind == "stride":
        return np.arange(0, h, int(args[0]))
    if kind == "band":
        lo, hi = float(args[0]), float(args[1])
        return np.flatnonzero((alt >= lo) & (alt <= hi))
    if kind == "center":  # the n beams nearest the horizon (a narrower-FOV sensor with the same beam spacing), then every k-th
        n, k = int(args[0]), int(args[1]) if len(args) > 1 else 1
        return np.sort(np.argsort(np.abs(alt), kind="stable")[:n])[::k]
    if kind == "even":
        n, lo, hi = int(args[0]), float(args[1]), float(args[2])
        targets = np.linspace(hi, lo, n)
        rows = sorted({int(np.argmin(np.abs(alt - t))) for t in targets})
        if len(rows) != n:
            raise ValueError(f"'{spec}': only {len(rows)} distinct beams available in that band")
        return np.array(rows)
    raise ValueError(f"unknown row spec '{spec}'")


def emulate(points: np.ndarray, model: Dict[str, Any], organized: Optional[List[int]],
            altitudes_deg: Optional[Sequence[float]], frame_index: int = 0, layout: str = "row-major") -> np.ndarray:
    """
    Return the points this emulated sensor would have delivered for one scan.

    layout: how the driver stored the organized scan. "row-major" = index row * W + col (ouster_ros 2021);
    "column-major" = index col * H + row (the 2020 OS1 driver, despite a WIDTH 1024 / HEIGHT 64 header).
    Verified per dataset from the elevation angle of each row (docs/decision-log.md, DEC-025).
    """
    if not any(k in model for k in ("rows", "col_stride", "max_points")):
        return points
    if organized is None:
        raise ValueError("sensor emulation needs an organized (rows x columns) dataset")
    h, w = organized
    if len(points) != h * w:
        raise ValueError(f"scan has {len(points)} points, expected organized {h}x{w}")
    if layout == "column-major":
        grid = points.reshape(w, h, -1).transpose(1, 0, 2)
    elif layout == "row-major":
        grid = points.reshape(h, w, -1)
    else:
        raise ValueError(f"unknown layout '{layout}'")
    rows = select_rows(model.get("rows", "all"), altitudes_deg) if altitudes_deg is not None else np.arange(h)
    grid = grid[rows, :: int(model.get("col_stride", 1))]
    out = grid.reshape(-1, points.shape[1])
    cap = model.get("max_points")
    if cap:
        r = np.linalg.norm(out[:, :3], axis=1)
        returns = np.flatnonzero(np.isfinite(r) & (r > 0.0))  # no-return cells are (0,0,0) in Ouster clouds
        if len(returns) > cap:
            rng = np.random.default_rng(frame_index)  # deterministic per frame, identical across repeats
            returns = np.sort(rng.choice(returns, size=int(cap), replace=False))
        out = out[returns]
    return out


def describe(model_id: str, model: Dict[str, Any], organized, altitudes_deg) -> Dict[str, Any]:
    """Static description recorded in run.json (beam count, vertical FOV, columns, frame stride)."""
    d: Dict[str, Any] = {"id": model_id, "label": model.get("label", model_id),
                         "frame_stride": int(model.get("frame_stride", 1)),
                         "evidence": "REAL" if model_id == "native" else "EMULATED"}
    if organized and altitudes_deg is not None:
        rows = select_rows(model.get("rows", "all"), altitudes_deg)
        alt = np.asarray(altitudes_deg)[rows]
        d.update(beams=int(len(rows)), vfov_deg=[round(float(alt.min()), 2), round(float(alt.max()), 2)],
                 columns=int(len(range(0, organized[1], int(model.get("col_stride", 1))))),
                 max_points=model.get("max_points"))
    return d
