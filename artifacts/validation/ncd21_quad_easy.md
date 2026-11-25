# Window validation

Verdict: **PASS**

## spacing

```json
{
  "dt_min_s": 0.09870791435241699,
  "dt_median_s": 0.09998226165771484,
  "dt_max_s": 0.10159826278686523,
  "gaps_near_nominal": 299,
  "gaps_other": 0,
  "longest_consecutive_run_frames": 300,
  "longest_run_index_range": [
    0,
    299
  ],
  "monotonic": true
}
```

## ground_truth

```json
{
  "n_poses": 1988,
  "t_range_s": [
    1625132069.158812,
    1625132267.8413587
  ],
  "median_dt_s": 0.10000324249267578,
  "covers_window": true
}
```

## association

```json
{
  "max_dt_s": 0.02,
  "frames_with_pose": 300,
  "frames_without_pose": 0,
  "max_offset_s": 0.0
}
```

## motion

```json
{
  "path_length_m": 38.060920473699795,
  "net_displacement_m": 29.93818755516255,
  "total_rotation_deg": 401.80329474751375,
  "speed_mps": {
    "median": 1.2791158434665124,
    "p95": 1.3965802051105751,
    "max": 1.430153945747009
  },
  "moving_fraction": 1.0,
  "moving_threshold_mps": 0.1,
  "per_step_translation_m_max": 0.14328701547609052,
  "per_step_rotation_deg_max": 4.274390391631231
}
```

## selected_window

```json
{
  "rule": "trim leading/trailing steps slower than 0.1 m/s",
  "first_frame_index": 0,
  "last_frame_index": 299,
  "n_frames": 300,
  "leading_stationary_frames": 0,
  "trailing_stationary_frames": 0
}
```

## headers

```json
{
  "distinct_POINTS": [
    131072
  ],
  "bad_files": []
}
```
