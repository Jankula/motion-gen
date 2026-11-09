"""The hand: finger forward kinematics on the flat-hand rest pose and grip shapes.

The left hand is solved and the right one mirrored (x -> -x, which turns an axis-angle vector
(a, b, c) into (a, -b, -c)).  All shapes are absolute finger rotations in the sense of
SMPLX_INTERFACE.md: R_i = rotation(relaxed_i + hand_pose_i); hand_pose_i = absolute - relaxed.

In the flat hand the fingers lie along +x, the palm faces -y and the thumb side is +z.  A finger
flexes about -z.  The palm surface (palm_center) is at the height PALM_Y; the skin_points named
*_pad are the palm side of the finger bones.  The grip shape presses the pads of all
fingers and of the thumb against a flat surface through the palm: a flat box face.
"""
import numpy as np
from scipy.optimize import least_squares

from locomotion.rotations import DEG, from_rotvec
from locomotion.skeleton import BODY

_H = BODY["hands"]["left"]
NAMES = list(_H["finger_joints"].keys())
_FJ = _H["finger_joints"]
REST = np.array([_FJ[n]["rest"] for n in NAMES])
RELAXED = {"L": np.array([_FJ[n]["relaxed_pose"] for n in NAMES])}
_MIRROR = np.array([1.0, -1.0, -1.0])
RELAXED["R"] = np.array([BODY["hands"]["right"]["finger_joints"]["right" + n[4:]]["relaxed_pose"] for n in NAMES])
WRIST = {"L": np.array(BODY["joints"]["left_wrist"]), "R": np.array(BODY["joints"]["right_wrist"])}
PARENT = [(-1 if _FJ[n]["parent"] == "left_wrist" else NAMES.index(_FJ[n]["parent"])) for n in NAMES]
SKIN = {k: (np.array(v["rest"]), NAMES.index(v["joint"]) if v["joint"] in NAMES else -1)
        for k, v in _H["skin_points"].items()}
PALM = {"L": np.array(_H["skin_points"]["left_palm_center"]["rest"]) - WRIST["L"],
        "R": np.array(BODY["hands"]["right"]["skin_points"]["right_palm_center"]["rest"]) - WRIST["R"]}
PALM_Y = float(_H["skin_points"]["left_palm_center"]["rest"][1])
FINGERS = ("index", "middle", "ring", "pinky")


def finger_fk(absolute):
    """World rotations and positions of the 15 finger joints of a flat left hand with absolute
    rotations (15, 3) (wrist at rest)."""
    Rm = from_rotvec(absolute)
    W = np.empty((15, 3, 3))
    P = np.empty((15, 3))
    for i in range(15):
        p = PARENT[i]
        if p < 0:
            W[i] = Rm[i]
            P[i] = REST[i]
        else:
            W[i] = W[p] @ Rm[i]
            P[i] = P[p] + W[p] @ (REST[i] - REST[p])
    return W, P


def skin(absolute, names):
    """Positions of skin points of the left hand for absolute finger rotations."""
    W, P = finger_fk(absolute)
    out = []
    for n in names:
        x, j = SKIN["left_" + n]
        out.append(P[j] + W[j] @ (x - REST[j]) if j >= 0 else x)
    return np.array(out)


def _finger(abs_pose, name, mcp, pip, dip, spread=0.0):
    i = NAMES.index("left_%s1" % name)
    abs_pose[i] = [0.0, spread, -mcp]
    abs_pose[i + 1] = [0.0, 0.0, -pip]
    abs_pose[i + 2] = [0.0, 0.0, -dip]


def _pad_names(name):
    return ["%s1_pad" % name, "%s2_pad" % name, "%s3_pad" % name]


def _seat_finger(abs_pose, name, pip, dip, spread, surface_y):
    """Choose the knuckle angle so that the finger's pads just reach the surface."""
    lo, hi = -35.0 * DEG, 40.0 * DEG
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        _finger(abs_pose, name, mid, pip, dip, spread)
        if skin(abs_pose, _pad_names(name))[:, 1].min() < surface_y:
            hi = mid
        else:
            lo = mid
    _finger(abs_pose, name, lo, pip, dip, spread)


def _thumb(abs_pose, surface_y, angle):
    """Thumb lying on the surface, opened by angle from the finger direction towards +z."""
    i = NAMES.index("left_thumb1")
    names = ["thumb1_pad", "thumb2_pad", "thumb3_pad"]
    want = np.array([np.cos(angle), 0.0, np.sin(angle)])
    base = abs_pose.copy()

    def resid(x):
        base[i] = x[0:3]
        base[i + 1] = [x[3], 0.0, 0.0]
        base[i + 2] = [x[4], 0.0, 0.0]
        pts = skin(base, names + ["thumb_tip"])
        d = pts[3] - REST[i]
        d = d / np.linalg.norm(d)
        return np.concatenate([12.0 * (pts[:3, 1] - surface_y) / 0.01 * 0.1,
                               2.0 * (d - want), 0.05 * x])

    r = least_squares(resid, np.array([0.3, 0.2, 0.1, -0.1, 0.1]), max_nfev=60)
    resid(r.x)
    abs_pose[i:i + 3] = base[i:i + 3]


class HandShapes:
    """Finger shapes for one hand side, as hand_pose arrays (15, 3)."""

    def __init__(self, side, gap=0.0, press=0.0015):
        # the surface: the mesh of the palm bulges (ball of the thumb) past the palm_center point,
        # so the surface is gap below it, and the pads press a little into it
        s = PALM_Y - gap - press
        grip = np.zeros((15, 3))
        spreads = dict(index=1.5, middle=0.0, ring=-1.0, pinky=-3.0)
        curls = dict(index=(13.0, 8.0), middle=(15.0, 9.0), ring=(15.0, 9.0), pinky=(13.0, 8.0))
        for f in FINGERS:
            _seat_finger(grip, f, curls[f][0] * DEG, curls[f][1] * DEG, spreads[f] * DEG, s)
        _thumb(grip, s, 40.0 * DEG)
        openh = np.zeros((15, 3))
        for f in FINGERS:
            _finger(openh, f, -4.0 * DEG, 10.0 * DEG, 6.0 * DEG, 1.3 * spreads[f] * DEG)
        openh[12:15] = grip[12:15] * 0.85
        m = np.ones(3) if side == "L" else _MIRROR
        self.side = side
        self.grip = grip * m - RELAXED[side]
        self.open = openh * m - RELAXED[side]
        self.relaxed = np.zeros((15, 3))
