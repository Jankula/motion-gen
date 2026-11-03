"""Batched 3x3 rotation helpers.

Every function accepts arrays of any leading shape ("batch" dimensions) and works on all of
them at once, so whole clips can be processed without Python loops over frames.
Angles are in radians.  Matrices act on column vectors: v_world = M @ v_local.
"""
import numpy as np
from scipy.spatial.transform import Rotation

DEG = np.pi / 180.0


def _prep(a):
    a = np.asarray(a, dtype=float)
    return a, np.cos(a), np.sin(a), np.zeros(a.shape + (3, 3))


def rx(a):
    """Rotation about +x (pitch; for the leg joints +x flexes the knee)."""
    a, c, s, M = _prep(a)
    M[..., 0, 0] = 1.0
    M[..., 1, 1] = c
    M[..., 1, 2] = -s
    M[..., 2, 1] = s
    M[..., 2, 2] = c
    return M


def ry(a):
    """Rotation about +y (yaw; positive turns the body to its left)."""
    a, c, s, M = _prep(a)
    M[..., 1, 1] = 1.0
    M[..., 0, 0] = c
    M[..., 0, 2] = s
    M[..., 2, 0] = -s
    M[..., 2, 2] = c
    return M


def rz(a):
    """Rotation about +z (roll about the walking direction; positive lifts the left side)."""
    a, c, s, M = _prep(a)
    M[..., 2, 2] = 1.0
    M[..., 0, 0] = c
    M[..., 0, 1] = -s
    M[..., 1, 0] = s
    M[..., 1, 1] = c
    return M


def tr(M):
    """Transpose (= inverse) of a batch of rotation matrices."""
    return np.swapaxes(M, -1, -2)


def mv(M, v):
    """M @ v for batches."""
    return np.einsum("...ij,...j->...i", M, v)


def mtv(M, v):
    """M.T @ v for batches."""
    return np.einsum("...ji,...j->...i", M, v)


def from_rotvec(v):
    v = np.asarray(v, dtype=float)
    sh = v.shape[:-1]
    return Rotation.from_rotvec(v.reshape(-1, 3)).as_matrix().reshape(sh + (3, 3))


def to_rotvec(M):
    M = np.asarray(M, dtype=float)
    sh = M.shape[:-2]
    return Rotation.from_matrix(M.reshape(-1, 3, 3)).as_rotvec().reshape(sh + (3,))


def axis_angle(axis, ang):
    """Rotation by angle ang about axis (axis need not be normalised; a zero axis gives I)."""
    axis = np.asarray(axis, dtype=float)
    ang = np.asarray(ang, dtype=float)
    n = np.linalg.norm(axis, axis=-1)
    u = axis / np.where(n < 1e-12, 1.0, n)[..., None]
    return from_rotvec(u * ang[..., None])


def rot_between(a, b):
    """Smallest rotation taking direction a to direction b."""
    a = a / np.linalg.norm(a, axis=-1, keepdims=True)
    b = b / np.linalg.norm(b, axis=-1, keepdims=True)
    c = np.cross(a, b)
    ang = np.arctan2(np.linalg.norm(c, axis=-1), np.clip(np.sum(a * b, -1), -1.0, 1.0))
    return axis_angle(c, ang)


def euler_xzy(M):
    """Angles (a, b, c) with M = Rx(a) Rz(b) Ry(c).

    For hips and ankles: a = flexion (x), b = ab/adduction (z), c = axial rotation (y)."""
    b = np.arcsin(np.clip(-M[..., 0, 1], -1.0, 1.0))
    a = np.arctan2(M[..., 2, 1], M[..., 1, 1])
    c = np.arctan2(M[..., 0, 2], M[..., 0, 0])
    return np.stack([a, b, c], -1)


def from_euler_xzy(e):
    e = np.asarray(e, dtype=float)
    return rx(e[..., 0]) @ rz(e[..., 1]) @ ry(e[..., 2])


def frac_rot(M, f):
    """Rotation about the same axis as M by f times its angle."""
    return from_rotvec(to_rotvec(M) * np.asarray(f, dtype=float)[..., None])


def wrap(a):
    """Wrap angles to (-pi, pi]."""
    return np.pi - np.mod(np.pi - np.asarray(a, dtype=float), 2.0 * np.pi)


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def softplus(x, w):
    return w * np.logaddexp(0.0, x / w)


def bump(s, a, b):
    """s^a (1-s)^b scaled to peak 1 (zero value, slope and curvature at both ends)."""
    s = np.clip(s, 0.0, 1.0)
    sp = a / (a + b)
    return (s ** a * (1 - s) ** b) / (sp ** a * (1 - sp) ** b)
