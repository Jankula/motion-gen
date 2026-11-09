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
