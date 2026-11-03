"""The fixed SMPL-X body (betas = 0): joints, parents, landmarks and forward kinematics.

Data come from body_info.json in the directory that contains this package.
"""
import json
import os

import numpy as np

BODY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "body_info.json")

NAMES = ["pelvis", "left_hip", "right_hip", "spine1", "left_knee", "right_knee", "spine2",
         "left_ankle", "right_ankle", "spine3", "left_foot", "right_foot", "neck",
         "left_collar", "right_collar", "head", "left_shoulder", "right_shoulder",
         "left_elbow", "right_elbow", "left_wrist", "right_wrist"]
IDX = {n: i for i, n in enumerate(NAMES)}
NJ = len(NAMES)

with open(BODY_FILE, encoding="utf-8") as _fh:
    BODY = json.load(_fh)

J = np.array([BODY["joints"][n] for n in NAMES], dtype=float)       # rest joint positions
PARENT = [-1] + [IDX[BODY["parents"][n]] for n in NAMES[1:]]
FLOOR = float(BODY["floor_y"])
LM = {k: np.array(v, dtype=float) for k, v in BODY["landmarks"].items()}
PELVIS_HEIGHT = float(J[0, 1] - FLOOR)   # pelvis joint above the floor in the rest pose (~0.95 m)


def sole_points(side):
    """A few points on the sole and heel of one foot in the rest pose (world coordinates):
    heel back, heel bottom, outer and inner edge, toe tip.  Used to keep a swinging foot
    above the floor and to check foot-to-foot distances."""
    pre = "left_" if side == "L" else "right_"
    return np.array([LM[pre + "heel_back"], LM[pre + "heel_bottom"], LM[pre + "sole_outer_edge"],
                     LM[pre + "sole_inner_edge"], LM[pre + "toe_tip"]])


def foot_outline(side, per_edge=5):
    """Points around the outline of the sole (heel back -> outer edge -> toe tip -> inner edge),
    rest pose, world coordinates: used to keep the feet apart."""
    pre = "left_" if side == "L" else "right_"
    corners = [LM[pre + "heel_back"], LM[pre + "sole_outer_edge"], LM[pre + "toe_tip"],
               LM[pre + "sole_inner_edge"], LM[pre + "heel_back"]]
    pts = []
    for a, b in zip(corners[:-1], corners[1:]):
        for f in np.arange(per_edge) / per_edge:
            pts.append(a + f * (b - a))
    return np.array(pts)


def fk(transl, R):
    """Forward kinematics exactly as in SMPLX_INTERFACE.md, for a whole clip.

    transl (T, 3), R (T, 22, 3, 3) local rotations (R[:, 0] = global orientation).
    Returns world rotations W (T, 22, 3, 3) and joint positions P (T, 22, 3)."""
    T = len(transl)
    W = np.empty((T, NJ, 3, 3))
    P = np.empty((T, NJ, 3))
    W[:, 0] = R[:, 0]
    P[:, 0] = J[0] + transl
    for i in range(1, NJ):
        p = PARENT[i]
        W[:, i] = W[:, p] @ R[:, i]
        P[:, i] = P[:, p] + W[:, p] @ (J[i] - J[p])
    return W, P
