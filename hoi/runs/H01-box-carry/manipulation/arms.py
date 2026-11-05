"""Analytic arm inverse kinematics (IK: finding joint rotations that put the hand at a target).

The elbow is a hinge about the local y axis: in the T-pose the forearm flexes forwards (the leg
counterpart is legs.Leg.ik).  The elbow of this skeleton sits off the shoulder-wrist line,
differently on the two sides, so the hinge angle is solved for the real bone vectors.  Which way
the elbow points is set by a pole direction: the hinge axis is put
perpendicular to the plane through the arm's shoulder-wrist line and that direction, which
stays well defined when the arm is almost straight.

The rest pose has the forearm in mid-rotation (palm parallel to the hinge axis).  Forearm
twist needed to reach a hand orientation is shared between the elbow joint and the wrist joint,
as real forearm rotation happens along the whole forearm.
"""
import numpy as np

from locomotion.rotations import DEG, axis_angle, from_rotvec, mtv, mv, rot_between, ry, tr
from locomotion.skeleton import IDX, J


MIN_FLEX = 6.0 * DEG   # an elbow never goes straighter than this


class Arm:
    def __init__(self, side, twist_share=0.5):
        self.side = side
        self.sign = 1.0 if side == "L" else -1.0
        pre = "left_" if side == "L" else "right_"
        self.collar, self.shoulder = IDX[pre + "collar"], IDX[pre + "shoulder"]
        self.elbow, self.wrist = IDX[pre + "elbow"], IDX[pre + "wrist"]
        self.a = J[self.elbow] - J[self.shoulder]
        self.b = J[self.wrist] - J[self.elbow]
        self.b_axis = self.b / np.linalg.norm(self.b)
        a, b = self.a, self.b
        A = a[0] * b[0] + a[2] * b[2]
        B = a[0] * b[2] - a[2] * b[0]
        self._rho = float(np.hypot(A, B))
        self._phi0 = float(np.arctan2(B, A))
        self._K = float(a @ a + b @ b + 2.0 * a[1] * b[1])
        self.twist_share = twist_share
        self.reach = float(np.linalg.norm(a + b))      # arm length with the elbow at its rest angle

    def hinge(self, d):
        """Rotation angle of the elbow about local y giving shoulder-wrist distance d, and the
        reach q (q > 1: out of reach)."""
        q = 0.5 * (d * d - self._K) / self._rho
        ang = np.arccos(np.clip(q, -1.0, 1.0))
        return -self.sign * np.maximum(ang - self.sign * self._phi0, MIN_FLEX), q

    def solve(self, S, Wc, wrist_pos, W_hand, pole):
        """Local rotations of shoulder, elbow and wrist.

        S (n, 3) shoulder position, Wc (n, 3, 3) world rotation of the collar, wrist_pos and W_hand
        the wanted wrist position and world rotation, pole (n, 3) the direction the elbow points."""
        D = mtv(Wc, wrist_pos - S)
        d = np.linalg.norm(D, axis=-1)
        phi, q = self.hinge(d)
        Re = ry(phi)
        v = self.a + mv(Re, self.b)
        R1 = rot_between(v, D)
        n = D / d[:, None]
        hinge_now = R1[:, :, 1]
        hinge_want = self.sign * np.cross(n, mtv(Wc, pole))
        k1 = hinge_now - np.sum(hinge_now * n, -1)[:, None] * n
        k2 = hinge_want - np.sum(hinge_want * n, -1)[:, None] * n
        psi = np.arctan2(np.sum(n * np.cross(k1, k2), -1), np.sum(k1 * k2, -1))
        Rs = axis_angle(n, psi) @ R1
        Rw = tr(Wc @ Rs @ Re) @ W_hand
        # forearm twist: the rotation of the wrist about the forearm's axis is shared with the elbow
        ax = self.b_axis
        qv = 0.5 * np.stack([Rw[:, 2, 1] - Rw[:, 1, 2], Rw[:, 0, 2] - Rw[:, 2, 0], Rw[:, 1, 0] - Rw[:, 0, 1]], -1)
        qw = 0.5 * np.sqrt(np.maximum(1.0 + np.trace(Rw, axis1=1, axis2=2), 1e-9))
        twist = 2.0 * np.arctan2(qv @ ax / (2.0 * qw), qw)
        Rt = from_rotvec(ax[None] * (self.twist_share * twist)[:, None])
        return Rs, Re @ Rt, tr(Rt) @ Rw, q
