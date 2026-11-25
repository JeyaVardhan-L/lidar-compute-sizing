"""Compiled variants (small_gicp) and sensor emulation: known-answer tests."""

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from autonav_baseline.datasets.synthetic import SyntheticAdapter
from autonav_baseline.harness.config import SENSOR_MODELS
from autonav_baseline.harness.variants import make_odometry
from autonav_baseline.lidar.sensor_emulation import describe, emulate, select_rows

PARAMS = {"voxel_size": 0.15, "min_range": 0.5, "max_range": 50.0, "max_correspondence_distance": 1.5,
          "max_iterations": 30, "tolerance": 1e-4}
HAS_SG = importlib.util.find_spec("small_gicp") is not None


def _run(variant, frames=8):
    ad = SyntheticAdapter(config={"num_frames": frames, "step_m": 0.3, "yaw_step_deg": 2.0})
    odo = make_odometry(variant, dict(PARAMS))
    for f in ad.get_lidar_frames():
        odo.process_frame(f.points, f.index, f.timestamp)
    _, gt = ad.ground_truth()
    truth = np.linalg.inv(gt[0]) @ gt
    return odo, np.linalg.norm(odo.get_trajectory_poses()[:, :3, 3] - truth[:, :3, 3], axis=1)


@unittest.skipUnless(HAS_SG, "small_gicp not installed")
class TestCompiledVariants(unittest.TestCase):
    def test_c_icp_is_the_same_algorithm_as_baseline(self):
        base, _ = _run("baseline")
        comp, _ = _run("c-icp")
        self.assertEqual(base.successful_steps, comp.successful_steps)
        # same estimator, different nearest-neighbour library and stopping rule: millimetre agreement
        d = np.abs(base.get_trajectory_poses()[:, :3, 3] - comp.get_trajectory_poses()[:, :3, 3]).max()
        self.assertLess(d, 5e-3)

    def test_c_gicp_tracks_ground_truth(self):
        odo, err = _run("c-gicp")
        self.assertEqual(odo.failed_steps, 0)
        self.assertLess(err.max(), 0.15)

    def test_pose_convention_is_not_mirrored(self):
        # the synthetic sensor moves +x; a mirrored composition would end at negative x
        odo, _ = _run("c-gicp")
        self.assertGreater(odo.get_trajectory_poses()[-1, 0, 3], 1.0)


class TestSensorEmulation(unittest.TestCase):
    ALT = list(np.linspace(45, -45, 16))  # 16 beams, top first, 6 deg apart

    def _grid(self, h=16, w=8):
        # point (row, col) = (row, col, 1) so the selection can be read back
        r, c = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        return np.c_[r.ravel(), c.ravel(), np.ones(h * w)].astype(float)

    def test_row_stride_and_column_stride(self):
        out = emulate(self._grid(), {"rows": "stride:4", "col_stride": 2}, [16, 8], self.ALT)
        self.assertEqual(sorted(set(out[:, 0])), [0, 4, 8, 12])
        self.assertEqual(sorted(set(out[:, 1])), [0, 2, 4, 6])
        self.assertEqual(len(out), 4 * 4)

    def test_column_major_layout_is_read_as_beams(self):
        g = self._grid()                                   # row-major (row, col, 1)
        cm = g.reshape(16, 8, 3).transpose(1, 0, 2).reshape(-1, 3)  # the same scan stored column by column
        a = emulate(g, {"rows": "stride:4"}, [16, 8], self.ALT)
        b = emulate(cm, {"rows": "stride:4"}, [16, 8], self.ALT, layout="column-major")
        self.assertTrue(np.array_equal(a, b))

    def test_band_keeps_only_beams_inside_the_fov(self):
        rows = select_rows("band:-10:10", self.ALT)
        self.assertTrue(all(-10 <= self.ALT[i] <= 10 for i in rows))
        self.assertEqual(len(rows), 4)  # 9, 3, -3, -9 deg

    def test_center_takes_beams_nearest_the_horizon(self):
        rows = select_rows("center:4", self.ALT)
        self.assertEqual(list(rows), [6, 7, 8, 9])  # 9, 3, -3, -9 deg
        self.assertEqual(list(select_rows("center:4:2", self.ALT)), [6, 8])

    def test_even_picks_distinct_nearest_beams(self):
        rows = select_rows("even:4:-45:45", self.ALT)
        self.assertEqual(list(rows), [0, 5, 10, 15])
        with self.assertRaises(ValueError):
            select_rows("even:8:-5:5", self.ALT)  # only 2 real beams in that band

    def test_point_budget_excludes_no_return_cells_and_is_deterministic(self):
        pts = self._grid()
        pts[::3] = 0.0  # no-return cells
        m = {"rows": "all", "max_points": 20}
        a = emulate(pts, m, [16, 8], self.ALT, frame_index=7)
        b = emulate(pts, m, [16, 8], self.ALT, frame_index=7)
        self.assertEqual(len(a), 20)
        self.assertTrue(np.array_equal(a, b))
        self.assertTrue(np.all(np.linalg.norm(a, axis=1) > 0))

    def test_native_is_untouched_and_unorganized_is_rejected(self):
        pts = self._grid()
        self.assertIs(emulate(pts, {}, None, None), pts)
        with self.assertRaises(ValueError):
            emulate(pts[:-1], {"rows": "all"}, [16, 8], self.ALT)

    def test_every_configured_model_describes_itself(self):
        alt128 = list(np.linspace(46.27, -45.73, 128))
        for mid, model in SENSOR_MODELS.items():
            d = describe(mid, model, [128, 1024], alt128)
            self.assertIn("beams", d)
            if mid.endswith("@5hz"):
                self.assertEqual(d["frame_stride"], 2)
        self.assertEqual(describe("16b-30", SENSOR_MODELS["16b-30"], [128, 1024], alt128)["beams"], 16)


if __name__ == "__main__":
    unittest.main()
