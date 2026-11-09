"""Which joints come closest to the box around a moment?  (in the box's frame, skeleton only)

    python tools/near_box.py motion.npz task.json t
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from locomotion.rotations import from_rotvec  # noqa: E402
from locomotion.skeleton import IDX, fk  # noqa: E402

m = np.load(os.path.join(ROOT, sys.argv[1]))
task = json.load(open(os.path.join(ROOT, sys.argv[2])))
i = int(float(sys.argv[3]) * int(m["fps"]))
T = len(m["transl"])
R = np.empty((T, 22, 3, 3))
R[:, 0] = from_rotvec(m["global_orient"].astype(float))
R[:, 1:] = from_rotvec(m["body_pose"].astype(float).reshape(T, 21, 3))
W, P = fk(m["transl"].astype(float), R)
Rb = from_rotvec(m["object_orient"].astype(float))[i]
ob = m["object_transl"].astype(float)[i]
half = 0.5 * np.array(task["object"]["size"], dtype=float)
print("box centre height %.2f, half sizes %s" % (ob[1] + 1.3018, np.round(half, 3)))
rows = []
for name in ("left_knee", "right_knee", "left_hip", "right_hip", "pelvis", "spine1", "spine2", "spine3", "neck", "head",
             "left_elbow", "right_elbow", "left_shoulder", "right_shoulder", "left_ankle", "right_ankle",
             "left_foot", "right_foot"):
    loc = Rb.T @ (P[i, IDX[name]] - ob)
    d = np.abs(loc) - half
    rows.append((float(np.linalg.norm(np.maximum(d, 0.0))), name, np.round(loc, 3).tolist()))
for r in sorted(rows)[:6]:
    print("  dist %.3f  %-14s local %s" % r)
