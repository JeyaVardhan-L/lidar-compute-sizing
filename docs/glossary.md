# Glossary

| Term | Meaning |
|---|---|
| **ATE** | Absolute trajectory error: RMS position error after rigidly aligning the estimate to ground truth |
| **RPE** | Relative pose error: error of the displacement over a fixed time or distance window; here as % of distance |
| **ICP** | Iterative Closest Point: aligns two scans by alternating nearest-neighbour matching and a rigid fit |
| **GICP** | Generalized-ICP: ICP with a plane-to-plane error built from local point covariances |
| **Scan-to-scan odometry** | Pose from chaining the rigid motion between consecutive scans (no map, no loop closure) |
| **Voxel filter** | Replaces all points in each cube of a given size by their centroid |
| **Frame period** | Time between scans (100 ms at 10 Hz): the budget a scan must be processed in |
| **P50 / P99** | Median and 99th-percentile frame time |
| **FEASIBLE / MARGINAL** | Declared real-time classes (DEC-027) |
| **ADEQUATE** | Declared accuracy class (DEC-028) |
| **Emulated sensor** | A cheaper sensor derived from a real high-resolution scan by dropping beams, columns, points or frames (DEC-025) |
| **E-core / P-core** | Efficiency and performance cores of a hybrid Intel CPU |
| **MEASURED / DERIVED / ASSUMED** | Evidence tags on every published number |
