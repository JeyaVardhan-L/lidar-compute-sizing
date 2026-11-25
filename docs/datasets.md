# Datasets: setup, provenance, licences

Raw data is never committed (see `.gitignore`) and never redistributed. Locations default to repo-relative folders and can be overridden in a git-ignored `config.local.yaml`:

```yaml
dataset_roots:
  newer_college_bag9: /data/ncd20_bag9/point_clouds
  newer_college_bag9_gt: /data/registered_poses.csv
```

For the v2 study the raw data lived outside the repository and was deleted after the campaign; only derived
results, validation records (`artifacts/validation/`) and decimated excerpts for the 3D viewer are kept.

## Newer College Multi-Camera extension, 2021 (primary for sizing)

| | |
|---|---|
| Source | Oxford Robotics Institute (access granted by the ORI team; the same request covers 2020 and 2021) |
| Reference | Zhang, Camurri, Wisth, Fallon. *Multi-Camera LiDAR Inertial Extension to the Newer College Dataset.* arXiv:2112.08854, 2021 |
| Licence | CC BY-NC-SA 4.0 |
| Sensor | Ouster OS0-128 Rev C: 128 beams, 1024 columns, 10 Hz, vertical FOV −45.7° to +46.3° (`configs/sensors/os0-128_beam_altitudes.json`, from the dataset's calibration file) |
| Ground truth | `gt-nc-<sequence>.csv`, 10 Hz, pose of the `base` frame; base ← sensor is a 9.1 cm translation, identity rotation (dataset calibration) |
| Windows (DEC-026) | Collection 1: quad-easy, quad-medium, quad-hard (ground-truth start + 120 s, 30 s each) and stairs (+ 30 s, 30 s). 300 scans each |
| How | `tools/fetch_bag_window.py` reads each 10 GB bag's chunk index over HTTP range requests and downloads only the chunks in the window (about 1.2 GB per window, `artifacts/validation/fetch_*.json`) |
| Checks | `tools/check_layout.py` (row-major, rows match beam calibration to 0.26°), `tools/validate_window.py` (spacing, ground-truth coverage, motion) |

Motion in the windows (ground truth): 95th-percentile angular rate 27 / 53 / 145 °/s for easy / medium / hard;
quad-hard turns up to 34° between consecutive scans (DEC-033).

## Newer College Dataset 2020 (continuity with v1)

| | |
|---|---|
| Source | Oxford Robotics Institute, https://ori.ox.ac.uk/datasets/newer-college-dataset/ (access is granted by the ORI team) |
| Reference | Ramezani, Wang, Camurri, Wisth, Mattamala, Fallon. *The Newer College Dataset: Handheld LiDAR, Inertial and Vision with Ground Truth.* IROS 2020 |
| Licence | CC BY-NC-SA 4.0 (non-commercial; attribution; share-alike) |
| Sensor | Ouster OS1-64 Gen1: 64 beams, 1024 columns, 10 Hz, 65,536 points per frame |
| Sequence | `01_short_experiment` |

Two kinds of data from this sequence are used, for different purposes:

1. **Odometry window** (`newer_college_bag9`): the single recording `rooster_2020-03-10-11-01-34_9.bag` (27 s, 271 consecutive scans), fetched with `tools/fetch_bag_window.py` in v2 (or extracted from a local copy with `tools/extract_bag.py`). The 2020 driver stores each organized scan column by column despite its `WIDTH 1024 / HEIGHT 64` header (`artifacts/validation/layout_newer_college_bag9.json`). Ground truth: `contiguous/registered_poses.csv` (10 Hz). Validate before use:
   `python tools/validate_window.py --frames <dir> --gt <registered_poses.csv> --out artifacts/validation/newer_college_bag9`
   (result: PASS, see `artifacts/validation/newer_college_bag9.md`).
2. **Thinned sample** (`newer_college_sparse`, v1 only): 1,734 scans from the raw PCD release. These are 11.3 % of the scans (median gap 0.6 s, longest consecutive run 4 frames), so they are **never** used for odometry, only for single-frame preprocessing timing and point-count statistics, labelled NON-CONSECUTIVE.

Filenames are `cloud_<sec>_<nsec>.pcd` with an unpadded nanosecond field: frames are sorted by parsed timestamp, never by name.

## Oxford Spires (secondary)

| | |
|---|---|
| Source | https://huggingface.co/datasets/ori-drs/oxford_spires_dataset, project page https://dynamic.robots.ox.ac.uk/datasets/oxford-spires/ |
| Licence | CC BY-NC-SA 4.0 (verified on the dataset card and project page) |
| Sensor | Hesai QT64: 64 channels, 10 Hz, ~104 degree vertical field of view, 60 m range. **Not an OS1-64**: beam layout, field of view and range differ, so Spires results are never presented as OS1-64 results |
| Ground truth | LiDAR registered to a Leica RTC360 survey map; the pose of the **base** frame in the world frame |
| Window | `python tools/fetch_spires.py` fetches 300 consecutive clouds of `2024-03-13-observatory-quarter-01` (largest ground-truth path length) with HTTP range requests, about 240 MB instead of the 2.1 GB archive |

## Evaluated, not used

KITTI (adapter kept; Velodyne HDL-64E, automotive; no run published), MulRan (not evaluated), Hilti / OpenLORIS / TUM RGB-D (adapters removed; in git history). The 2021 collections 2-4 (park, cloister, maths institute, underground mine) are available from the same source and are the natural next windows. Synthetic data (`SyntheticAdapter`) is for unit tests only and is refused by the site export.