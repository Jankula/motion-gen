"""Leg geometry, the stance foot (heel, forefoot and toe rockers) and analytic leg IK.

All functions are vectorised over samples (frames or event times).  The stance foot is
described by a table of per-sample plant properties (see Body.plant_table):
  Fy (n,3,3) foot yaw rotation, fwd (n,3) foot forward axis, c_flat (n,3) heel-circle centre
  of the flat foot, tip_flat (n,3) toe-pad pivot of the flat foot, alpha (n,) foot pitch at
  touch-down, push (n,) size of the push-off (heel rise, toe roll, pre-swing knee bend).
"""
import numpy as np

from .gait import heel_profile, knee_floor, toe_beta
from .rotations import DEG, mtv, mv, rot_between, rx, ry, axis_angle, smoothstep, softplus, tr, wrap
from .skeleton import FLOOR, IDX, J, LM

HEEL_R = 0.041   # radius of the rounded heel (fit to the heel_back / heel_bottom landmarks)
HEEL_Z = -0.080  # z of the heel-circle centre in the rest pose
PIVOT_BACK = 0.03  # forefoot pivot this far behind the toe-pad pivot [m]


class Leg:
    def __init__(self, side):
        self.side = side
        self.sign = 1.0 if side == "L" else -1.0
        pre = "left_" if side == "L" else "right_"
        self.hip, self.knee = IDX[pre + "hip"], IDX[pre + "knee"]
        self.ankle, self.toe = IDX[pre + "ankle"], IDX[pre + "foot"]
        self.a = J[self.knee] - J[self.hip]             # thigh bone
        self.b = J[self.ankle] - J[self.knee]           # shank bone
        self.hip_off = J[self.hip] - J[0]               # hip joint relative to the pelvis joint
        self.heel_c = np.array([LM[pre + "heel_bottom"][0], FLOOR + HEEL_R, HEEL_Z])
        self.tip = np.array([0.095 * self.sign, FLOOR, 0.127])   # toe-pad pivot (rest)
        self.r_ta = J[self.toe] - J[self.ankle]         # ankle -> ball of the foot
        a, b = self.a, self.b
        self._A = a[1] * b[1] + a[2] * b[2]
        self._B = a[2] * b[1] - a[1] * b[2]
        self._K = a @ a + b @ b + 2 * a[0] * b[0]
        self.straight_knee = np.arctan2(self._B, self._A)   # knee angle of a fully straight leg

    # ---------------------------------------------------------------- knee <-> hip-ankle distance
    def knee_from_distance(self, d):
        """Knee flexion theta (about x) with |a + Rx(theta) b| = d.  Returns (theta, q);
        q > 1 means the target is out of reach (the leg is then fully straight)."""
        rho = np.hypot(self._A, self._B)
        q = (0.5 * (d * d - self._K)) / rho
        return self.straight_knee + np.arccos(np.clip(q, -1.0, 1.0)), q

    def distance_from_knee(self, th):
        return np.sqrt(self._K + 2 * (self._A * np.cos(th) + self._B * np.sin(th)))

    # ---------------------------------------------------------------- foot placement helpers
    def flat_foot(self, xz, Fy):
        """Heel-circle centre and toe pivot of a flat foot whose heel-circle centre is above
        floor point xz (n, 2) and whose yaw rotation is Fy (n, 3, 3)."""
        xz = np.atleast_2d(xz)
        c = np.stack([xz[:, 0], np.full(len(xz), FLOOR + HEEL_R), xz[:, 1]], -1)
        return c, c + mv(Fy, self.tip - self.heel_c)

    def ankle_of(self, F, c_heel):
        """Ankle position of a foot with orientation F whose heel-circle centre is c_heel."""
        return c_heel - mv(F, self.heel_c - J[self.ankle])

    # ---------------------------------------------------------------- stance foot
    def stance_foot(self, tab, u, p, hip=None):
        """Foot orientation F, ankle position and toe angle at stance phase u.

        u < phi_ff: heel rocker (the foot rolls down over the rounded heel).
        otherwise : the foot is flat, then pitches about the ball of the foot (heel rise) while
                    the toes stay on the floor; late in stance the toes roll over the toe pad.
        The heel-rise angle is a soft maximum of a prescribed heel-off profile and the rise
        needed for the knee to bend at least the pre-swing minimum (needs the hip positions;
        without them only the profile is used)."""
        u = np.asarray(u, dtype=float)
        n = len(u)
        F = np.empty((n, 3, 3))
        ank = np.empty((n, 3))
        toe = np.empty(n)
        e = u < p["phi_ff"]
        if e.any():
            s = u[e] / p["phi_ff"]
            # front-loaded: fastest plantarflexion right after contact, soft forefoot landing
            a_up = tab["alpha"][e] * (1.0 - s) ** 2
            Fe = tab["Fy"][e] @ rx(-a_up)
            c = tab["c_flat"][e] - HEEL_R * a_up[:, None] * tab["fwd"][e]
            ank[e] = c - mv(Fe, self.heel_c - J[self.ankle])
            F[e] = Fe
            toe[e] = -p["toe_hs"] * (tab["alpha"][e] / p["alpha_hs"]) * (1.0 - smoothstep(s))
        l = ~e
        if l.any():
            ul = u[l]
            Fy = tab["Fy"][l]
            tip = tab["tip_flat"][l]
            if "pivot" in tab:
                # pivot on the forefoot (about the vertical through the middle of the forefoot
                # contact) while the heel is up, towards where the body is going
                Rp = ry(tab["pivot"][l] * smoothstep((ul - 0.25) / 0.33))
                q = tip - PIVOT_BACK * tab["fwd"][l]
                tip = q + mv(Rp, tip - q)
                Fy = Rp @ Fy
            push = tab["push"][l]
            beta = toe_beta(ul, p, push)
            m = tip + mv(Fy @ rx(beta), J[self.toe] - self.tip)
            al = heel_profile(ul, p, push)
            if hip is not None:
                al = self._soft_heel(al, hip[l], m, Fy, ul, p, push)
            Fl = Fy @ rx(al)
            ank[l] = m - mv(Fl, self.r_ta)
            F[l] = Fl
            toe[l] = beta - al
        return F, ank, toe

    def _soft_heel(self, a_prof, hip, m, Fy, u, p, push):
        """Soft maximum of the heel-off profile and the heel rise that lets the knee bend
        knee_floor(u).  The hip-ankle distance squared is K + A cos(al) + B sin(al) in the
        heel-rise angle al, so the needed rise has a closed form."""
        q = mtv(Fy, hip - m)
        r = self.r_ta
        K = np.sum(q * q, -1) + r @ r + 2 * q[:, 0] * r[0]
        A = 2 * (q[:, 1] * r[1] + q[:, 2] * r[2])
        B = 2 * (q[:, 2] * r[1] - q[:, 1] * r[2])
        rho = np.hypot(A, B)
        psi = np.arctan2(B, A)
        d = self.distance_from_knee(knee_floor(u, push) * DEG)
        c = (d * d - K) / rho
        a_fl = wrap(psi + np.arccos(np.clip(c, -1.0, 1.0)))   # crossing on the decreasing branch
        w = p["soft_w"]
        a_fl = np.where(c > 1.0, -np.inf, a_fl)               # floor satisfied for any rise
        a_fl = np.clip(a_fl, a_prof - 12.0 * w, p["heel_rise_max"])
        return a_prof + softplus(a_fl - a_prof, w)

    # ---------------------------------------------------------------- IK
    def ik(self, P0, W0, F, ank):
        """Analytic two-bone IK.  The knee is a pure flexion about its local x axis; the twist
        about the hip-ankle line points the knee's flexion axis along the foot's lateral axis
        (the knee tracks over the foot); the ankle takes the remaining rotation.
        Returns hip rotation, knee angle, ankle rotation (all local) and the reach q."""
        hip = P0 + mv(W0, self.hip_off)
        Dp = mtv(W0, ank - hip)
        d = np.linalg.norm(Dp, axis=-1)
        th, q = self.knee_from_distance(d)
        v = self.a + mv(rx(th), self.b)
        R1 = rot_between(v, Dp)
        n = Dp / d[:, None]
        k1 = R1[:, :, 0]                           # knee flexion axis after R1
        kd = mtv(W0, F[:, :, 0])                   # the foot's lateral axis
        k1p = k1 - np.sum(k1 * n, -1)[:, None] * n
        kdp = kd - np.sum(kd * n, -1)[:, None] * n
        psi = np.arctan2(np.sum(n * np.cross(k1p, kdp), -1), np.sum(k1p * kdp, -1))
        Rh = axis_angle(n, psi) @ R1
        Ra = tr(W0 @ Rh @ rx(th)) @ F
        return Rh, th, Ra, q
