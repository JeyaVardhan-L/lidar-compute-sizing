#!/usr/bin/env python3
"""
Write a copy of a ground-truth CSV (sec,nsec,x,y,z,qx,qy,qz,qw) with every quaternion scaled to unit length.

The loader refuses quaternions more than 1e-3 from unit length. Newer College 2021 `gt-nc-stairs.csv` has two
such rows (norm 0.993; qw printed with two digits). Rescaling changes those two orientations by well under
a degree and nothing else. Rows further than --max-dev from unit length are refused, not repaired.

Usage: python tools/normalize_gt.py IN.csv OUT.csv [--max-dev 0.01]   (prints a JSON report)
"""
import argparse
import json
import sys

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("dst"); ap.add_argument("--max-dev", type=float, default=0.01)
a = ap.parse_args()
header = open(a.src, encoding="utf-8").readline()
d = np.loadtxt(a.src, delimiter=",", skiprows=1 if header.startswith("#") else 0)
n = np.linalg.norm(d[:, 5:9], axis=1)
if np.any(np.abs(n - 1) > a.max_dev):
    sys.exit(f"refusing: {int(np.sum(np.abs(n - 1) > a.max_dev))} quaternions deviate more than {a.max_dev}")
fixed = np.flatnonzero(np.abs(n - 1) > 1e-3)
d[:, 5:9] /= n[:, None]
with open(a.dst, "w", encoding="utf-8") as f:
    f.write(header if header.startswith("#") else "#sec,nsec,x,y,z,qx,qy,qz,qw\n")
    for r in d:
        f.write(f"{int(r[0])},{int(r[1])}," + ",".join(f"{v:.9g}" for v in r[2:]) + "\n")
print(json.dumps({"rows": int(len(d)), "renormalised_beyond_1e-3": [int(i) for i in fixed],
                  "their_norms": [float(n[i]) for i in fixed]}))
