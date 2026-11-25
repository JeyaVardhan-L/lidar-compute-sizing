# src/autonav_baseline

The measurement pipeline (installed as the `autonav` command). Module map: [docs/architecture.md](../docs/architecture.md).

| Package | Contents |
|---|---|
| `datasets/` | adapters (Newer College, Oxford Spires, KITTI, synthetic for tests), PCD reader, ground-truth loader |
| `lidar/` | filters, scan-to-scan ICP with validity gate, point-to-plane ICP, sensor emulation |
| `metrics/` | ATE / RPE with timestamp association and Umeyama alignment |
| `harness/` | datasets, sensor models and compute profiles; worker, runner, variants (Python and compiled), verdicts |
| `lab/` | local web UI that launches runs (no algorithm logic) |
