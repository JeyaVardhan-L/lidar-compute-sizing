"""
Dataset ids, hardware profiles and window parsing for `autonav run`.

Dataset locations are repo-relative defaults. A git-ignored `config.local.yaml` may override them:

    dataset_roots:
      newer_college_bag9: D:/data/ncd/bag9/point_clouds
      newer_college_bag9_gt: D:/data/ncd/registered_poses.csv
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]

DATASETS: Dict[str, Dict[str, Any]] = {
    "newer_college_bag9": {
        "adapter": "newer_college",
        "frames": "datasets/newer-college/01_short_experiment/contiguous_bag9/point_clouds",
        "gt": "datasets/newer-college/01_short_experiment/contiguous/registered_poses.csv",
        "sensor": "Ouster OS1-64 Gen1 (64 beams, 1024 columns, 10 Hz)",
        "sequence": "Newer College 2020, 01_short_experiment, bag 9 (last 27 s)",
        "licence": "CC BY-NC-SA 4.0",
        "evidence": "REAL",
        "consecutive": True,
        "nominal_hz": 10.0,
        "default_window": "0:270",
        "same_sensor_as_target": True,
    },
    "newer_college_sparse": {
        "adapter": "newer_college",
        "frames": "datasets/newer-college/01_short_experiment/contiguous/point_clouds/ouster_scan",
        "gt": None,
        "sensor": "Ouster OS1-64 Gen1 (64 beams, 1024 columns, 10 Hz)",
        "sequence": "Newer College 2020, 01_short_experiment, thinned sample (11.3 % of scans)",
        "licence": "CC BY-NC-SA 4.0",
        "evidence": "REAL-NON-CONSECUTIVE",
        "consecutive": False,
        "nominal_hz": 10.0,
        "default_window": "0:200",
        "same_sensor_as_target": True,
    },
    "oxford_spires": {
        "adapter": "oxford_spires",
        "frames": "datasets/oxford-spires/window/lidar",
        "gt": "datasets/oxford-spires/window/gt.csv",
        "sensor": "Hesai QT64 (64 beams) - DIFFERENT from OS1-64 (beam layout, FOV, range)",
        "sequence": "Oxford Spires, one window",
        "licence": "see docs/decision-log.md",
        "evidence": "REAL",
        "consecutive": True,
        "nominal_hz": 10.0,
        "default_window": "0:300",
        "same_sensor_as_target": False,
    },
    "synthetic": {
        "adapter": "synthetic",
        "frames": None,
        "gt": None,
        "sensor": "none (SYNTHETIC room)",
        "sequence": "synthetic",
        "licence": "n/a",
        "evidence": "SYNTHETIC",
        "consecutive": True,
        "nominal_hz": 10.0,
        "default_window": "0:20",
        "same_sensor_as_target": False,
    },
}


_NCD21 = {
    "adapter": "newer_college",
    "sensor": "Ouster OS0-128 Rev C (128 beams, 1024 columns, 90 deg vertical FOV, 10 Hz)",
    "licence": "CC BY-NC-SA 4.0",
    "evidence": "REAL",
    "consecutive": True,
    "nominal_hz": 10.0,
    "default_window": "all",
    "same_sensor_as_target": False,
    "organized": [128, 1024],
    "layout": "row-major",
    "beam_altitudes": "configs/sensors/os0-128_beam_altitudes.json",
}
for _key, _title, _gt, _offset in [
    ("ncd21_quad_easy", "quad-easy", "gt-nc-quad-easy.csv", 120),
    ("ncd21_quad_medium", "quad-medium", "gt-nc-quad-medium.csv", 120),
    ("ncd21_quad_hard", "quad-hard", "gt-nc-quad-hard.csv", 120),
    ("ncd21_stairs", "stairs", "gt-nc-stairs.csv", 30),
]:
    DATASETS[_key] = dict(
        _NCD21,
        frames=f"datasets/newer-college-2021/{_key}/point_clouds",
        gt=f"datasets/newer-college-2021/{_gt}",
        sequence=f"Newer College Multi-Cam 2021, collection 1, {_title}: 30 s window from ground-truth start + {_offset} s",
    )
DATASETS["newer_college_bag9"]["organized"] = [64, 1024]
DATASETS["newer_college_bag9"]["layout"] = "column-major"  # 2020 driver; checked from row elevations
DATASETS["newer_college_bag9"]["beam_altitudes"] = "configs/sensors/os1-64_beam_altitudes.json"

# Sensor emulation. Each model is derived from a real recording by dropping beams (rows of the organized
# cloud), columns, points or frames before the pipeline sees the scan (the sensor would deliver it that way,
# so it is not timed). Beam rows are ordered by elevation (top first), as the Ouster driver publishes them.
# An emulated model has the target's beam count, vertical FOV, columns, points per frame and frame rate;
# it does NOT reproduce the target's optics, range noise, beam pattern or (for Livox) non-repetitive scan.
SENSOR_MODELS: Dict[str, Dict[str, Any]] = {
    "native":        {"label": "as recorded"},
    "128b-90-512c":  {"label": "128 beams, 90 deg vFOV, 512 columns", "rows": "all", "col_stride": 2},
    "64b-90":        {"label": "64 beams, 90 deg vFOV (OS0-64 class)", "rows": "stride:2"},
    "32b-90":        {"label": "32 beams, 90 deg vFOV (OS0-32 class)", "rows": "stride:4"},
    "16b-90":        {"label": "16 beams, 90 deg vFOV", "rows": "stride:8"},
    "64b-45":        {"label": "64 beams, 45 deg vFOV (OS1-64 class)", "rows": "center:64"},
    "32b-45":        {"label": "32 beams, 45 deg vFOV (OS1-32 class)", "rows": "center:64:2"},
    "16b-30":        {"label": "16 beams, 30 deg vFOV (VLP-16 class)", "rows": "even:16:-15:15"},
    "mid360-budget": {"label": "-7..+46 deg vFOV, 20 000 points per frame (Livox Mid-360 point budget; NOT its scan pattern)",
                      "rows": "band:-7:46", "max_points": 20000},
}
for _m in list(SENSOR_MODELS):
    if _m != "native":
        SENSOR_MODELS[_m + "@5hz"] = dict(SENSOR_MODELS[_m], label=SENSOR_MODELS[_m]["label"] + ", 5 Hz", frame_stride=2)
SENSOR_MODELS["native@5hz"] = {"label": "as recorded, 5 Hz", "frame_stride": 2}

# CPU affinity: one logical CPU per core, taking every other logical CPU from 0 (assumes SMT pairs are
# adjacent, true on Windows/Intel). Recorded exactly in run.json.
PROFILES: Dict[str, Dict[str, Any]] = {
    "laptop-full": {
        "threads": None, "n_cpus": None,
        "claim": "Development-laptop performance (no limits).",
    },
    "laptop-4c": {
        "threads": 4, "n_cpus": 4,
        "claim": "Scaling with core count on the development laptop. One-way inference only: a miss here makes a miss on a Raspberry Pi 5 very likely; a pass says nothing about the Pi.",
    },
    "laptop-1c": {
        "threads": 1, "n_cpus": 1,
        "claim": "Single-core scaling on the development laptop. One-way inference only (see laptop-4c).",
    },
}

# Efficiency cores of the i5-13420H (logical CPUs 8-11, Intel Gracemont, 3.4 GHz max; Linux numbering).
# Gracemont at up to 3.4 GHz is also the core of the Intel N100, so these are a labelled PROXY for N100-class
# compute: same microarchitecture and peak clock, but different cache, memory and sustained power.
PROFILES["laptop-4e"] = {
    "threads": 4, "n_cpus": 4, "cpus": [8, 9, 10, 11],
    "claim": "Four efficiency cores (Gracemont, 3.4 GHz) of the development laptop: a proxy for Intel N100-class compute, not an N100.",
}
PROFILES["laptop-1e"] = {
    "threads": 1, "n_cpus": 1, "cpus": [8],
    "claim": "One efficiency core (Gracemont, 3.4 GHz) of the development laptop: slow-core proxy, not embedded hardware.",
}
PROFILES["x86-cloud"] = {
    "threads": None, "n_cpus": None,
    "claim": "Shared x86 cloud VM (GitHub Actions ubuntu-latest). Noisy. Reference for the ARM VM on the same workload.",
}

PROFILES["arm-cloud"] = {
    "threads": None, "n_cpus": None,
    "claim": "Real ARM server-class shared cloud VM (GitHub Actions). Noisy. NOT a Raspberry Pi.",
}
PROFILES["pi5"] = {
    "threads": None, "n_cpus": None,
    "claim": "Raspberry Pi 5 measurement. Valid only when this profile is run on a real Pi 5; the CPU model recorded in run.json must say so.",
}

VARIANTS = ("baseline", "optimized", "p2plane", "c-icp", "c-gicp")


def load_local_config() -> Dict[str, Any]:
    p = REPO_ROOT / "config.local.yaml"
    if not p.is_file():
        return {}
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def resolve_dataset(dataset_id: str) -> Dict[str, Any]:
    if dataset_id not in DATASETS:
        raise ValueError(f"Unknown dataset id '{dataset_id}'. Known: {', '.join(DATASETS)}")
    info = dict(DATASETS[dataset_id])
    over = (load_local_config().get("dataset_roots") or {})
    if dataset_id in over:
        info["frames"] = over[dataset_id]
    if f"{dataset_id}_gt" in over:
        info["gt"] = over[f"{dataset_id}_gt"]
    for key in ("frames", "gt"):
        if info.get(key):
            p = Path(info[key])
            info[key] = str(p if p.is_absolute() else REPO_ROOT / p)
    info["id"] = dataset_id
    return info


def parse_window(spec: str, n_total: int) -> Tuple[int, int]:
    """'0:270' -> frames [0, 270); 'first:50' -> [0, 50); 'all' -> everything."""
    spec = spec.strip().lower()
    if spec == "all":
        return 0, n_total
    if spec.startswith("first:"):
        return 0, min(int(spec.split(":")[1]), n_total)
    a, b = spec.split(":")
    start, stop = int(a), min(int(b), n_total)
    if not 0 <= start < stop:
        raise ValueError(f"Invalid window '{spec}' for {n_total} frames")
    return start, stop


def profile_cpus(profile_id: str, logical: int) -> Optional[List[int]]:
    if PROFILES[profile_id].get("cpus"):
        return [c for c in PROFILES[profile_id]["cpus"] if c < logical] or None
    n = PROFILES[profile_id]["n_cpus"]
    if n is None:
        return None
    cpus = list(range(0, min(2 * n, logical), 2))[:n]
    return cpus if len(cpus) == n else list(range(min(n, logical)))