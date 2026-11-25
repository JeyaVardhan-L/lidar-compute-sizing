# Window validation

Verdict: **PASS**

## spacing

```json
{
  "dt_min_s": 0.09855318069458008,
  "dt_median_s": 0.09996676445007324,
  "dt_max_s": 0.10147333145141602,
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
  "n_poses": 1907,
  "t_range_s": [
    1625135500.1885004,
    1625135690.7783017
  ],
  "median_dt_s": 0.09999418258666992,
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
  "path_length_m": 40.58639402843315,
  "net_displacement_m": 30.71437529675219,
  "total_rotation_deg": 682.2999715016985,
  "speed_mps": {
    "median": 1.40653798525437,
    "p95": 1.5597098313111786,
    "max": 1.6509838052673291
  },
  "moving_fraction": 1.0,
  "moving_threshold_mps": 0.1,
  "per_step_translation_m_max": 0.1669415699489934,
  "per_step_rotation_deg_max": 9.467820499441048
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
