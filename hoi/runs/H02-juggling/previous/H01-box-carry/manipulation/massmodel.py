"""Where the body's mass is: a segment model on the skeleton.

Segment mass shares and centre positions are the usual anthropometric values (from general
biomechanics knowledge), placed on the bones of this skeleton.  Used to keep the combined
centre of mass of the person and the load over the feet.
"""
import numpy as np

from locomotion.rotations import mv
from locomotion.skeleton import IDX

BODY_MASS = 76.0

# (mass share, joint a, joint b, position from a to b)
SEGMENTS = [(0.112, "pelvis", "spine1", 0.3), (0.163, "spine1", "spine3", 0.5),
            (0.159, "spine3", "neck", 0.5)]
for _s in ("left_", "right_"):
    SEGMENTS += [(0.027, _s + "shoulder", _s + "elbow", 0.45), (0.016, _s + "elbow", _s + "wrist", 0.43),
                 (0.142, _s + "hip", _s + "knee", 0.41), (0.043, _s + "knee", _s + "ankle", 0.44),
                 (0.014, _s + "ankle", _s + "foot", 0.5)]
_A = np.array([IDX[s[1]] for s in SEGMENTS])
_B = np.array([IDX[s[2]] for s in SEGMENTS])
_F = np.array([s[3] for s in SEGMENTS])[None, :, None]
_M = np.array([s[0] for s in SEGMENTS])
_HEAD, _HEAD_C = 0.069, np.array([0.0, 0.09, 0.02])
_HAND = 0.006


def body_com(W, P):
    """Centre of mass of the body (T, 3) from world joint rotations W and positions P."""
    c = P[:, _A] + _F * (P[:, _B] - P[:, _A])
    num = np.einsum("s,tsk->tk", _M, c)
    num = num + _HEAD * (P[:, IDX["head"]] + mv(W[:, IDX["head"]], _HEAD_C))
    for name, sg in (("left_wrist", 1.0), ("right_wrist", -1.0)):
        num = num + _HAND * (P[:, IDX[name]] + mv(W[:, IDX[name]], np.array([sg * 0.08, -0.01, 0.0])))
    return num / (_M.sum() + _HEAD + 2 * _HAND)


def total_com(W, P, load_pos=None, load_mass=None):
    """Combined centre of mass with a load (positions (T, 3), mass (T,) as carried by the body)."""
    c = body_com(W, P)
    if load_pos is None:
        return c
    m = np.asarray(load_mass, dtype=float)[:, None]
    return (BODY_MASS * c + m * load_pos) / (BODY_MASS + m)
