# Window validation

Verdict: **REVIEW**

## spacing

```json
{
  "dt_min_s": 0.09729886054992676,
  "dt_median_s": 0.10004878044128418,
  "dt_max_s": 0.10223793983459473,
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
  "n_poses": 1724,
  "t_range_s": [
    1625135721.0764832,
    1625135908.864806
  ],
  "median_dt_s": 0.10008764266967773,
  "covers_window": true
}
```

## association

```json
{
  "max_dt_s": 0.02,
  "frames_with_pose": 277,
  "frames_without_pose": 23,
  "max_offset_s": 0.0
}
```

## motion

```json
{
  "path_length_m": 34.54088505606858,
  "net_displacement_m": 19.61199431179851,
  "total_rotation_deg": 1667.144270366964,
  "speed_mps": {
    "median": 1.378385519905747,
    "p95": 1.6978998642004843,
    "max": 2.0271975916690934
  },
  "moving_fraction": 0.9891304347826086,
  "moving_threshold_mps": 0.1,
  "per_step_translation_m_max": 0.32192569294440493,
  "per_step_rotation_deg_max": 34.24813869982896
}
```

## selected_window

```json
{
  "rule": "trim leading/trailing steps slower than 0.1 m/s",
  "first_frame_index": 0,
  "last_frame_index": 276,
  "n_frames": 277,
  "leading_stationary_frames": 0,
  "trailing_stationary_frames": 23
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
