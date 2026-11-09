"""Print leg joint angles and pelvis heading frame by frame (my own checking tool).

    python tools/joints.py motion.npz 200 250 [L|R]"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import analyze as A  # noqa: E402
from locomotion.rotations import DEG, euler_xzy  # noqa: E402
from locomotion.skeleton import FLOOR, IDX, fk  # noqa: E402

path, f0, f1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
sides = sys.argv[4:] or ["L", "R"]
tr, R, fps = A.load(path)
W, P = fk(tr, R)
fwd = W[:, 0, :, 2]
yaw = np.degrees(np.arctan2(fwd[:, 0], fwd[:, 2]))
for f in range(f0, min(f1, len(tr))):
    row = "%3d t %5.2f pel (%6.3f %6.3f) yaw %6.1f |" % (f, f / fps, P[f, 0, 0], P[f, 0, 2], yaw[f])
    for side in sides:
        pre = "left_" if side == "L" else "right_"
        sg = 1.0 if side == "L" else -1.0
        h = euler_xzy(R[f, IDX[pre + "hip"]]) / DEG
        k = euler_xzy(R[f, IDX[pre + "knee"]])[0] / DEG
        a = euler_xzy(R[f, IDX[pre + "ankle"]]) / DEG
        fy = W[f, IDX[pre + "ankle"], :, 2]
        fyaw = np.degrees(np.arctan2(fy[0], fy[2]))
        ank = P[f, IDX[pre + "ankle"]]
        row += (" %s hip f%6.1f a%6.1f r%6.1f knee %5.1f ank d%6.1f i%6.1f | foot yaw %6.1f ank (%6.3f %5.3f %6.3f)"
                % (side, -h[0], sg * h[1], -sg * h[2], k, -a[0], sg * a[1], fyaw, ank[0], ank[1] - FLOOR, ank[2]))
    print(row)
