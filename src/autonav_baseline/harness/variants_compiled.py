"""
Compiled (C++) registration variants, through small_gicp (Koide, JOSS 2024, MIT licence; PyPI wheel).

Why these exist: the Python variants answer "where does the time go"; a drone would run compiled code.
These variants keep everything else identical (same range filter, same voxel size, same correspondence
distance, same iteration cap, same validity gate, same pose convention W_k = W_{k-1} @ T), so the
difference to `baseline` / `p2plane` is the implementation and, for c-gicp, the error metric.

c-icp    Point-to-point ICP, scan-to-scan, identity initial guess: the same algorithm as `baseline`.
c-gicp   Generalized-ICP (plane-to-plane via local covariances), scan-to-scan, constant-velocity initial
         guess (last accepted relative motion; reset on a rejection), as `p2plane` does.

Timing boundaries (same meaning as the Python variants):
  preprocess  range filter (NumPy) + voxel grid (C++) [+ covariance estimation and KD-tree for the new scan]
  register    alignment + validity gate + pose update. For c-gicp the gate's mean residual is measured by a
              nearest-neighbour pass after alignment (its own cost is inside register_ms). For c-icp the
              residual is the RMS of inlier residuals from the solver's final error (error = 0.5 * sum r^2,
              verified against a direct nearest-neighbour check); RMS >= mean, so the gate is at least as
              strict as for baseline.
Threads: one per CPU the process may use (the hardware profile sets the CPU affinity).
"""

from typing import Optional

import numpy as np

from autonav_baseline.harness.variants_impl import _usable_cpus
from autonav_baseline.lidar.odometry import ICPOdometry, ICPResult


def _sg():
    import small_gicp  # optional dependency, imported only when a compiled variant is selected
    return small_gicp


class _CompiledBase(ICPOdometry):
    registration_type = "ICP"
    needs_covariances = False
    constant_velocity = False

    def __init__(self, num_neighbors: int = 20, **params):
        super().__init__(**params)
        self.sg = _sg()
        self.threads = _usable_cpus()
        self.num_neighbors = num_neighbors
        self._prev_cloud = None
        self._prev_tree = None
        self._cur_cloud = None
        self._cur_tree = None
        self._last_rel = np.eye(4)
        self._pending: Optional[ICPResult] = None

    def _preprocess(self, raw_points):
        xyz = np.asarray(raw_points[:, :3], dtype=np.float64)
        r2 = np.einsum("ij,ij->i", xyz, xyz)
        finite = np.isfinite(r2)
        n_valid = int(np.count_nonzero(finite))
        with np.errstate(invalid="ignore"):
            keep = (r2 >= self.min_range ** 2) & (r2 <= self.max_range ** 2)
        n_range = int(np.count_nonzero(keep))
        cloud = self.sg.voxelgrid_sampling(xyz[keep], self.voxel_size, num_threads=self.threads)
        tree = self.sg.KdTree(cloud, num_threads=self.threads)
        if self.needs_covariances:
            self.sg.estimate_covariances(cloud, tree, num_neighbors=self.num_neighbors, num_threads=self.threads)
        self._cur_cloud, self._cur_tree = cloud, tree
        pts = cloud.points()[:, :3]
        return pts, n_valid, n_range

    def _register(self, pts) -> ICPResult:
        sg = self.sg
        init = self._last_rel if self.constant_velocity else np.eye(4)
        res = sg.align(self._prev_cloud, self._cur_cloud, self._prev_tree, init_T_target_source=init,
                       registration_type=self.registration_type,
                       max_correspondence_distance=self.max_correspondence_distance,
                       num_threads=self.threads, max_iterations=self.max_iterations)
        T = np.array(res.T_target_source, dtype=np.float64)
        n = max(self._cur_cloud.size(), 1)
        if self.registration_type == "ICP":
            fitness = float(np.sqrt(2.0 * res.error / res.num_inliers)) if res.num_inliers else float("inf")
            inliers = int(res.num_inliers)
        else:
            moved = pts @ T[:3, :3].T + T[:3, 3]
            _, d2 = self._prev_tree.batch_nearest_neighbor_search(moved, num_threads=self.threads)
            d = np.sqrt(np.asarray(d2, dtype=np.float64))
            m = d <= self.max_correspondence_distance
            inliers = int(np.count_nonzero(m))
            fitness = float(d[m].mean()) if inliers else float("inf")
        out = ICPResult(success=bool(inliers >= 20), transformation=T, rotation=T[:3, :3].copy(),
                        translation=T[:3, 3].copy(), fitness_score=fitness, inlier_ratio=inliers / n,
                        num_inliers=inliers, iterations=int(res.iterations),
                        status="CONVERGED" if res.converged else "MAX_ITERATIONS")
        self._pending = out
        return out

    def process_frame(self, raw_points, frame_index, timestamp=None):
        self._pending = None
        step = super().process_frame(raw_points, frame_index, timestamp)
        # the base class replaces the reference scan only on acceptance (or on the first frame)
        if step.accepted:
            self._prev_cloud, self._prev_tree = self._cur_cloud, self._cur_tree
        if self._pending is not None:
            self._last_rel = self._pending.transformation.copy() if step.accepted else np.eye(4)
        return step


class CompiledICPOdometry(_CompiledBase):
    registration_type = "ICP"


class CompiledGICPOdometry(_CompiledBase):
    registration_type = "GICP"
    needs_covariances = True
    constant_velocity = True
