# Architecture

```
remote ROS bags (ORI)  --tools/fetch_bag_window.py (HTTP range, index first)-->  data/<window>/point_clouds/*.pcd
Hugging Face (Spires)  --tools/fetch_spires.py ------------------------------>  data/oxford_spires_window/
                          (raw data lives outside the repo, git-ignored, deleted after use)
        |
src/autonav_baseline/
  datasets/   adapters (newer_college, oxford_spires, kitti, synthetic[tests only]), io (PCD), groundtruth
  lidar/      filtering, odometry (ICP + validity gate + pose convention), fast_voxel, registration_p2plane,
              sensor_emulation (beams / vertical FOV / columns / point budget from an organized scan)
  metrics/    trajectory_evaluation (association, Umeyama ATE, RPE), classification (evidence tags)
  harness/    config (datasets, sensor models, compute profiles), worker (one measured repeat, fresh process),
              runner (repeats, aggregation), variants (+_impl Python, +_compiled small_gicp), verdict, viz, env
  lab/        stdlib http.server: spawns the CLI, serves artifacts; no algorithm logic
  cli.py      autonav run | list | publish | unpublish | postprocess | lab
        |
artifacts/runs/<run-id>/  run.json  frames.csv  summary.json  verdicts.json  viz/   (git-ignored)
artifacts/validation/     window, layout and fetch checks (committed)
artifacts/sizing/         sizing.json: table, cost model, scaling check, projection, recommendation (committed)
artifacts/published.json  which runs the public site may show
        |
tools/run_matrix.py        the declared campaign (resumable)
tools/sizing_analysis.py   runs -> sizing.json (rules DEC-027/028/031 applied mechanically)
tools/export_site_data.py  published runs + sizing.json -> site/public/data -> site/ (Astro, static)
```

The Python pipeline is the source of truth and is independent of the site at runtime. The site never recomputes
a metric; `npm run check:numbers` compares every rendered number with `artifacts/`.

Every variant shares one frame loop (`ICPOdometry.process_frame`): preprocessing and registration are the only
overridden steps, so the validity gate, pose convention (`W_k = W_{k-1} @ T`) and timing boundaries are identical
across Python and compiled code.
