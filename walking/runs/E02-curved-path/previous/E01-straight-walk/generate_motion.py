"""Procedural walking motion for the SMPL-X body (betas = 0).

Run:  python generate_motion.py      -> writes motion.npz next to this file (about 15 s).

Overview (details and reasoning in NOTES.md):
  1. A gait-phase clock drives everything (left heel strike at phase 0, right at 0.5).
     Cadence wanders slowly by about +-1.5 % so that steps are not perfectly identical.
  2. Every footstep is anchored to the floor.  In stance the foot rolls over the rounded
     heel (heel rocker), lies flat, rolls over the ball of the foot (forefoot rocker) and
     finally over the toe pad (toe rocker).  Leg joints in stance come from analytic
     two-bone IK on the SMPL-X skeleton, so a weight-bearing foot never slides.
  3. Pelvis height is solved, not guessed: for the leading stance leg it is the height that
     gives a normal stance-knee flexion curve.  A smooth periodic curve is fitted that never
     exceeds this requirement (so no leg is ever over-stretched).  The heel-strike distance
     and a small static pelvic obliquity are solved so that the requirement is continuous
     when the leading leg changes (the skeleton's two legs differ slightly).
  4. Swing legs are interpolated in joint space with clamped cubic splines: they leave
     toe-off with the stance leg's joint velocities, pass via points taken from normal swing
     kinematics (knee ~60 deg early in swing, late hip-flexion peak), and arrive at the next
     footprint with a rigid-leg approach (heel moving forward/down, knee momentarily still).
  5. Pelvis rotation/obliquity/tilt, lateral sway, thorax counter-rotation, head
     stabilisation, arm swing opposite to the legs with a slight lag, elbow flexion that
     peaks on the forward swing, collar and wrist motion are phase-locked functions.
Deterministic: no random numbers; "variability" comes from fixed slow sinusoids.
"""
import json
import os

import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator
from scipy.optimize import brentq, minimize
from scipy.spatial.transform import Rotation as Rot

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "body_info.json")) as fh:
    BODY = json.load(fh)

NAMES = ["pelvis", "left_hip", "right_hip", "spine1", "left_knee", "right_knee", "spine2",
         "left_ankle", "right_ankle", "spine3", "left_foot", "right_foot", "neck",
         "left_collar", "right_collar", "head", "left_shoulder", "right_shoulder",
         "left_elbow", "right_elbow", "left_wrist", "right_wrist"]
IDX = {n: i for i, n in enumerate(NAMES)}
J = np.array([BODY["joints"][n] for n in NAMES], dtype=float)
PARENT = [-1] + [IDX[BODY["parents"][n]] for n in NAMES[1:]]
FLOOR = float(BODY["floor_y"])
LM = {k: np.array(v, dtype=float) for k, v in BODY["landmarks"].items()}

FPS = 30
NFRAMES = 180
DEG = np.pi / 180.0
EX = np.array([1.0, 0.0, 0.0])


# ----------------------------------------------------------------------------- rotation helpers
def rx(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def ry(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def rodrigues(axis, ang):
    n = np.linalg.norm(axis)
    if n < 1e-12 or abs(ang) < 1e-15:
        return np.eye(3)
    x, y, z = axis / n
    K = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * (K @ K)


def rot_between(a, b):
    """Minimal rotation taking direction a to direction b."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    c = np.cross(a, b)
    return rodrigues(c, np.arctan2(np.linalg.norm(c), np.clip(a @ b, -1, 1)))


def euler(M):
    """Angles (a, b, c) with M = Rx(a) Rz(b) Ry(c): flexion, ab/adduction, axial rotation."""
    b = np.arcsin(np.clip(-M[0, 1], -1.0, 1.0))
    a = np.arctan2(M[2, 1], M[1, 1])
    c = np.arctan2(M[0, 2], M[0, 0])
    return np.array([a, b, c])


def from_euler(e):
    return rx(e[0]) @ rz(e[1]) @ ry(e[2])


def frac_rot(M, f):
    """Rotation about the same axis as M by f times its angle."""
    return Rot.from_rotvec(Rot.from_matrix(M).as_rotvec() * f).as_matrix()


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


# ----------------------------------------------------------------------------- gait targets
# Normal adult sagittal curves (degrees) written from general biomechanics knowledge.
# Stance knee flexion of the leading leg, used to solve the pelvis height.
KNEE_TGT = PchipInterpolator(
    [0.00, 0.03, 0.06, 0.10, 0.14, 0.18, 0.22, 0.27, 0.32, 0.37, 0.41, 0.45, 0.50, 0.55],
    [5.0, 8.5, 12.0, 15.5, 17.5, 16.8, 14.5, 11.0, 8.0, 6.0, 5.0, 6.0, 10.0, 18.0])
# Minimum knee flexion of a stance leg: near zero until terminal stance, then the knee
# must bend quickly in pre-swing (the heel rises further if needed to allow it).
KNEE_FLOOR = PchipInterpolator(
    [0.00, 0.45, 0.50, 0.55, 0.60, 0.62, 0.70],
    [1.5, 1.5, 7.5, 17.5, 31.0, 35.0, 48.0])


# ----------------------------------------------------------------------------- pelvis height fit
NHARM = 8


def height_basis(ph):
    cols = [np.ones_like(ph)]
    for h in range(1, NHARM + 1):
        cols += [np.cos(2 * np.pi * h * ph), np.sin(2 * np.pi * h * ph)]
    return np.stack(cols, -1)


def fit_below(phs, ys, margin=0.0003, lam=2e-7):
    """Smooth periodic fit (harmonics 0..NHARM) that stays below the samples by margin."""
    A = height_basis(phs)
    hw = np.concatenate([[0.0], np.repeat(np.arange(1, NHARM + 1) ** 2, 2)]).astype(float)
    c0, *_ = np.linalg.lstsq(A, ys, rcond=None)
    c0[0] -= np.max(A @ c0 - ys) + margin          # feasible start

    def obj(c):
        r = A @ c - ys
        return r @ r + lam * np.sum((hw * c) ** 2)

    def jac(c):
        return 2 * A.T @ (A @ c - ys) + 2 * lam * hw ** 2 * c

    cons = dict(type="ineq", fun=lambda c: ys - margin - A @ c, jac=lambda c: -A)
    sol = minimize(obj, c0, jac=jac, constraints=[cons], method="SLSQP",
                   options=dict(maxiter=500, ftol=1e-14))
    return sol.x


# ----------------------------------------------------------------------------- legs
SIDES = {
    "L": dict(hip=IDX["left_hip"], knee=IDX["left_knee"], ankle=IDX["left_ankle"],
              toe=IDX["left_foot"], sign=1.0, offset=0.0),
    "R": dict(hip=IDX["right_hip"], knee=IDX["right_knee"], ankle=IDX["right_ankle"],
              toe=IDX["right_foot"], sign=-1.0, offset=0.5),
}
HEEL_R = 0.041   # radius of the rounded heel (fit to the heel_back / heel_bottom landmarks)
HEEL_Z = -0.080  # z of the heel-circle centre in the rest pose
for _s, _d in SIDES.items():
    _hx = LM["left_heel_bottom" if _s == "L" else "right_heel_bottom"][0]
    _d["heel_c"] = np.array([_hx, FLOOR + HEEL_R, HEEL_Z])
    _d["tip"] = np.array([0.095 * _d["sign"], FLOOR, 0.127])   # toe-pad pivot (rest)
    _d["a"] = J[_d["knee"]] - J[_d["hip"]]
    _d["b"] = J[_d["ankle"]] - J[_d["knee"]]


# rest direction of each arm (shoulder -> wrist), the axis of the visible arm
ARM_REST = {s: (J[IDX[s + "_wrist"]] - J[IDX[s + "_shoulder"]]) /
            np.linalg.norm(J[IDX[s + "_wrist"]] - J[IDX[s + "_shoulder"]]) for s in ("left", "right")}


def knee_from_distance(a, b, d):
    """Knee flexion theta (about x) with |a + Rx(theta) b| = d.  Returns (theta, q);
    q > 1 means the target is out of reach (the leg is then fully straight)."""
    A = a[1] * b[1] + a[2] * b[2]
    B = a[2] * b[1] - a[1] * b[2]
    C = 0.5 * (d * d - a @ a - b @ b) - a[0] * b[0]
    rho = np.hypot(A, B)
    q = C / rho
    return np.arctan2(B, A) + np.arccos(np.clip(q, -1.0, 1.0)), q


def _knee_ab_terms(sd):
    """(B, A) of knee_from_distance: atan2(B, A) is the knee angle of a fully straight leg."""
    a, b = sd["a"], sd["b"]
    return a[2] * b[1] - a[1] * b[2], a[1] * b[1] + a[2] * b[2]


class Gait:
    P = dict(
        T=1.06,              # gait cycle [s]  (~113 steps / min)
        stride=1.30,         # stride length [m] -> 1.23 m/s
        phi0=0.12,           # left-leg phase at t = 0
        heel_x=0.068,        # lateral position of the heel-circle centres (+-) [m]
        toe_out=4.5 * DEG,   # foot progression angle
        d_hs=None,           # heel ahead of the pelvis at heel strike (solved if None)
        roll0=None,          # static pelvic obliquity absorbing skeleton asymmetry (solved)
        knee_geo=0.75,       # share of the skeleton's knee asymmetry absorbed by the knees
        v_app=0.30,          # forward heel speed over the floor just before contact [m/s]
        alpha_hs=19.0 * DEG,  # foot pitch (toes up) at heel strike
        toe_hs=8.0 * DEG,    # toe extension at heel strike
        phi_ff=0.08,         # foot flat
        phi_to=0.60,         # toe off
        soft_w=1.0 * DEG,    # softness of the soft maximum in heel_alpha
        u_hr=0.31,           # heel off
        alpha_50=14.0 * DEG,  # heel-rise angle at opposite heel strike
        hr_pow=1.7,          # shape of the heel-rise profile
        u_tr=0.50,           # toes start to roll (toe rocker)
        beta_to=22.0 * DEG,  # toe segment pitch at toe off
        z_amp=0.004,         # forward speed fluctuation amplitude [m]
        x_amp=0.021,         # lateral pelvis sway [m]
        x_peak=0.30,         # phase of maximal sway to the left
        yaw_amp=4.5 * DEG,
        roll_amp=3.5 * DEG,
        pitch_mean=3.0 * DEG,
        pitch_amp=1.0 * DEG,
        knee_pk=61.0 * DEG,  # peak swing knee flexion
        knee_pk_s=0.30,      # ... at this fraction of the swing
        hip_retract=4.0 * DEG,  # hip flexion peak above its heel-strike value
        hip_ab_swing=1.5 * DEG,  # slight abduction of the swing leg (clearance)
        var=1.0,             # scale of the slow natural variations
        ycoef=None,          # pelvis height Fourier coefficients (solved if None)
    )

    def __init__(self, **kw):
        self.p = dict(self.P)
        self.p.update(kw)
        self._swing_cache = {}
        self._fp_cache = {}
        if self.p["d_hs"] is None or self.p["ycoef"] is None or self.p["roll0"] is None:
            self.solve_pelvis_height()

    def _clear(self):
        self._swing_cache = {}
        self._fp_cache = {}

    # ---------------------------------------------------------------- timing
    def phase(self, t):
        """Left-leg gait phase (cycles)."""
        return t / self.p["T"] + self.p["phi0"] + self._wob_int(t)

    def _wob_int(self, t):
        # phase = int (1 + c(t)) / T dt with a small slow cadence modulation c(t)
        T = self.p["T"]
        out = 0.0
        for amp, per, ph in ((0.012, 4.1, 0.7), (0.007, 2.3, 2.1)):
            w = 2 * np.pi / per
            out += self.p["var"] * amp / T * (-(np.cos(w * t + ph) - np.cos(ph)) / w)
        return out

    def leg_phase(self, side, t):
        return self.phase(t) + SIDES[side]["offset"]

    def event_time(self, side, value):
        """Time at which the leg phase equals value (phase is strictly increasing)."""
        target = value - SIDES[side]["offset"]
        t = (target - self.p["phi0"]) * self.p["T"]
        for _ in range(50):
            f = self.phase(t) - target
            if abs(f) < 1e-13:
                break
            h = 1e-5
            df = (self.phase(t + h) - self.phase(t - h)) / (2 * h)
            t -= f / df
        return t

    # ---------------------------------------------------------------- pelvis
    def pelvis_y(self, ph):
        return float((height_basis(np.atleast_1d(ph)) @ self.p["ycoef"])[0])

    def pelvis_pos(self, t, y=None):
        p = self.p
        ph = self.phase(t)
        z = p["stride"] * (ph - p["phi0"]) + p["z_amp"] * np.sin(4 * np.pi * (ph - 0.07))
        x = p["x_amp"] * np.cos(2 * np.pi * (ph - p["x_peak"]))
        if y is None:
            y = self.pelvis_y(ph)
        return J[0] + np.array([x, y, z])

    def pelvis_angles(self, t):
        p = self.p
        ph = self.phase(t)
        yaw = -p["yaw_amp"] * np.cos(2 * np.pi * (ph + 0.02))
        roll = p["roll_amp"] * (np.sin(2 * np.pi * (ph + 0.03)) + 0.15 * np.sin(6 * np.pi * (ph + 0.03)))
        roll += p["roll0"] or 0.0
        pitch = p["pitch_mean"] + p["pitch_amp"] * np.cos(4 * np.pi * (ph - 0.45))
        return yaw, pitch, roll

    def pelvis_rot(self, t):
        yaw, pitch, roll = self.pelvis_angles(t)
        return ry(yaw) @ rx(pitch) @ rz(roll)

    # ---------------------------------------------------------------- feet
    def footprint(self, side, k):
        key = (side, k)
        if key in self._fp_cache:
            return self._fp_cache[key]
        p = self.p
        sd = SIDES[side]
        t_hs = self.event_time(side, k)
        # small step-to-step scatter of foot placement (deterministic): +-4 mm sideways,
        # +-1 deg toe-out, as in real walking
        ph_s = 0.0 if side == "L" else 1.9
        dx = p["var"] * 0.004 * np.sin(2.1 * k + ph_s)
        dyaw = p["var"] * 1.0 * DEG * np.sin(1.3 * k + 0.7 + ph_s)
        yaw = sd["sign"] * (p["toe_out"] + dyaw)
        fwd = np.array([np.sin(yaw), 0.0, np.cos(yaw)])
        z_hs = self.pelvis_pos(t_hs, y=0.0)[2] + p["d_hs"]
        c_hs = np.array([sd["sign"] * (p["heel_x"] + dx), FLOOR + HEEL_R, z_hs])
        c_flat = c_hs + HEEL_R * p["alpha_hs"] * fwd   # the heel rolls forward
        Fy = ry(yaw)
        m_flat = c_flat + Fy @ (J[sd["toe"]] - sd["heel_c"])
        tip_flat = c_flat + Fy @ (sd["tip"] - sd["heel_c"])
        fp = dict(yaw=yaw, Fy=Fy, c_flat=c_flat, m_flat=m_flat, tip_flat=tip_flat, fwd=fwd,
                  t_hs=t_hs)
        self._fp_cache[key] = fp
        return fp

    def toe_beta(self, u):
        p = self.p
        s = (u - p["u_tr"]) / (p["phi_to"] - p["u_tr"])
        return p["beta_to"] * max(s, 0.0) ** 2

    def foot_heelrise(self, side, k, alpha, beta=0.0):
        """Foot pitched by alpha (heel up) about the ball of the foot, while the toe segment
        is pitched by beta about the toe pad (toe rocker).  Returns F, ankle, toe angle."""
        sd = SIDES[side]
        fp = self.footprint(side, k)
        if beta > 0.0:
            m = fp["tip_flat"] + fp["Fy"] @ rx(beta) @ (J[sd["toe"]] - sd["tip"])
        else:
            m = fp["m_flat"]
        F = fp["Fy"] @ rx(alpha)
        ank = m - F @ (J[sd["toe"]] - J[sd["ankle"]])
        return F, ank, beta - alpha

    def heel_profile(self, u):
        """Prescribed heel rise (foot pitch about the ball of the foot) from heel-off on."""
        p = self.p
        s = (u - p["u_hr"]) / (0.5 - p["u_hr"])
        return p["alpha_50"] * max(s, 0.0) ** p["hr_pow"]

    def heel_alpha(self, side, k, u, t, y=None):
        """Heel-rise angle = soft max of the prescribed heel-off profile and the rise needed
        for the knee to bend at least KNEE_FLOOR(u) (pre-swing knee flexion, leg reach)."""
        P0 = self.pelvis_pos(t, y)
        W0 = self.pelvis_rot(t)
        beta = self.toe_beta(u)
        floor = float(KNEE_FLOOR(u)) * DEG
        hi = 95 * DEG

        def knee(al):
            F, ank, _ = self.foot_heelrise(side, k, al, beta)
            return self.leg_ik(side, P0, W0, F, ank)[1]

        # f decreases with alpha near the profile value (the knee bends as the heel rises);
        # search locally so that far-away, unreachable configurations never matter.
        f = lambda al: floor - knee(al)
        a_prof = self.heel_profile(u)
        w = self.p["soft_w"]
        step = 3.0 * DEG
        a_floor = a_prof - 12.0 * w                # inactive unless a crossing is found
        if f(a_prof) > 0:                          # knee too straight: raise the heel more
            a0 = a_prof
            while a0 < hi:
                a1 = min(a0 + step, hi)
                if f(a1) <= 0:
                    a_floor = brentq(f, a0, a1, xtol=1e-10)
                    break
                a0 = a1
            else:
                a_floor = hi
        else:                                      # find the (inactive) crossing just below
            a1 = a_prof
            while a1 > a_prof - 12.0 * w:
                a0 = a1 - step
                if f(a0) > 0:
                    a_floor = brentq(f, a0, a1, xtol=1e-10)
                    break
                a1 = a0
        return a_prof + softplus(a_floor - a_prof, w)

    def stance_foot(self, side, k, u, t, y=None):
        """Foot orientation F, ankle position, toe angle at stance phase u of footprint k."""
        p = self.p
        sd = SIDES[side]
        fp = self.footprint(side, k)
        if u < p["phi_ff"]:
            s = u / p["phi_ff"]
            # front-loaded: fastest plantarflexion right after contact, soft forefoot landing
            a_up = p["alpha_hs"] * (1.0 - s) ** 2
            F = fp["Fy"] @ rx(-a_up)
            c = fp["c_flat"] - HEEL_R * a_up * fp["fwd"]
            ank = c - F @ (sd["heel_c"] - J[sd["ankle"]])
            toe = -p["toe_hs"] * (1.0 - smoothstep(s))
            return F, ank, toe
        al = self.heel_alpha(side, k, u, t, y)
        return self.foot_heelrise(side, k, al, self.toe_beta(u))

    # ---------------------------------------------------------------- IK
    def leg_ik(self, side, P0, W0, F, ank):
        sd = SIDES[side]
        a, b = sd["a"], sd["b"]
        hip = P0 + W0 @ (J[sd["hip"]] - J[0])
        Dp = W0.T @ (ank - hip)
        d = np.linalg.norm(Dp)
        th, q = knee_from_distance(a, b, d)
        v = a + rx(th) @ b
        R1 = rot_between(v, Dp)
        n = Dp / d
        k1 = R1 @ EX                      # knee flexion axis after R1
        kd = W0.T @ (F @ EX)              # foot's lateral axis: the knee should follow it
        k1p = k1 - (k1 @ n) * n
        kdp = kd - (kd @ n) * n
        psi = np.arctan2(n @ np.cross(k1p, kdp), k1p @ kdp)
        Rh = rodrigues(n, psi) @ R1
        Ra = (W0 @ Rh @ rx(th)).T @ F
        return Rh, th, Ra, q

    def stance_channels(self, side, t, k, want_q=False):
        u = self.leg_phase(side, t) - k
        F, ank, toe = self.stance_foot(side, k, u, t)
        Rh, th, Ra, q = self.leg_ik(side, self.pelvis_pos(t), self.pelvis_rot(t), F, ank)
        ch = np.concatenate([euler(Rh), [th], euler(Ra), [toe]])
        return (ch, q) if want_q else ch

    # ---------------------------------------------------------------- pelvis height
    def knee_at(self, side, k, u, t, y):
        F, ank, _ = self.stance_foot(side, k, u, t, y)
        return self.leg_ik(side, self.pelvis_pos(t, y), self.pelvis_rot(t), F, ank)[1]

    def knee_offset(self, side):
        """Per-side stance-knee offset: a fraction of the difference in rest-pose knee bend
        of the two skeleton legs (left 3.1 deg, right 0.2 deg geometric flexion)."""
        th0 = {s: np.arctan2(*_knee_ab_terms(SIDES[s])) for s in ("L", "R")}
        return self.p["knee_geo"] * (th0[side] - 0.5 * (th0["L"] + th0["R"]))

    def y_required(self, side, k, u):
        """Pelvis height offset that gives the target knee flexion for a stance leg."""
        t = self.event_time(side, k + u)
        tgt = float(KNEE_TGT(u)) * DEG + self.knee_offset(side)
        return brentq(lambda y: self.knee_at(side, k, u, t, y) - tgt, -0.20, 0.06, xtol=1e-7)

    def switch_mismatch(self, x, k=3):
        """Jumps of the required pelvis height when the leading leg changes (both steps),
        as a function of x = (heel-strike distance, static pelvic obliquity)."""
        self.p["d_hs"] = float(x[0])
        self.p["roll0"] = float(x[1])
        self._clear()
        m1 = self.y_required("L", k, 0.5 - 1e-6) - self.y_required("R", k, 0.0)
        m2 = self.y_required("R", k, 0.5 - 1e-6) - self.y_required("L", k + 1, 0.0)
        return np.array([m1, m2])

    def solve_pelvis_height(self, n=60):
        """Sample the required pelvis height for the leading stance leg over a whole cycle and
        fit the highest smooth periodic curve that never exceeds it (a lower pelvis only
        adds a little knee flexion; a higher one would over-stretch the leg)."""
        var = self.p["var"]
        self.p["var"] = 0.0
        if self.p["d_hs"] is None or self.p["roll0"] is None:
            # Newton iteration: one symmetric heel-strike distance plus a static obliquity
            # (the SMPL-X skeleton is slightly asymmetric) make both hand-overs continuous
            d = np.array([0.235, 0.0])
            for _ in range(12):
                m = self.switch_mismatch(d)
                if np.max(np.abs(m)) < 1e-6:
                    break
                Jm = np.zeros((2, 2))
                for i in range(2):
                    dd = d.copy()
                    dd[i] += 1e-4
                    Jm[:, i] = (self.switch_mismatch(dd) - m) / 1e-4
                d = d - np.linalg.solve(Jm, m)
            self.p["d_hs"], self.p["roll0"] = float(d[0]), float(d[1])
        self._clear()
        k = 3
        us = (np.arange(n) + 0.5) / n * 0.5
        phs, ys = [], []
        for side in ("L", "R"):
            for u in us:
                phs.append(u + SIDES[side]["offset"])
                ys.append(self.y_required(side, k, u))
        phs, ys = np.array(phs), np.array(ys)
        self.p["ycoef"] = fit_below(phs, ys)
        self.y_samples = (phs, ys)
        self.p["var"] = var
        self._clear()

    # ---------------------------------------------------------------- swing
    def swing_spec(self, side, k):
        key = (side, k)
        if key in self._swing_cache:
            return self._swing_cache[key]
        p = self.p
        t0 = self.event_time(side, k + p["phi_to"])
        t1 = self.event_time(side, k + 1)
        h = 2e-3
        c0, c0a, c0b = (self.stance_channels(side, t0 - i * h, k) for i in range(3))
        v0 = (3 * c0 - 4 * c0a + c0b) / (2 * h)       # stance-side velocity at toe-off
        c1 = self.stance_channels(side, t1, k + 1)
        v1 = self.approach_velocity(side, k + 1, t1, c1)
        spec = dict(t0=t0, t1=t1, c0=c0, v0=v0, c1=c1, v1=v1)
        self._swing_cache[key] = spec
        return spec

    def leg_points(self, side, t, ch):
        """World heel-circle centre and foot pitch for leg channels ch at time t."""
        sd = SIDES[side]
        W0 = self.pelvis_rot(t)
        P0 = self.pelvis_pos(t)
        Wh = W0 @ from_euler(ch[0:3])
        Ph = P0 + W0 @ (J[sd["hip"]] - J[0])
        Wk = Wh @ rx(ch[3])
        Pk = Ph + Wh @ sd["a"]
        Wa = Wk @ from_euler(ch[4:7])
        Pa = Pk + Wk @ sd["b"]
        heel = Pa + Wa @ (sd["heel_c"] - J[sd["ankle"]])
        fwd = Wa @ np.array([0.0, 0.0, 1.0])
        return heel, np.arctan2(-fwd[1], np.hypot(fwd[0], fwd[2]))

    def approach_velocity(self, side, k, t1, c1):
        """Joint velocities just before heel strike for a rigid-leg approach: the knee is
        momentarily still (it reaches its most extended point at contact), the foot keeps its
        pitch, and the hip extends so that the heel moves forward over the floor at
        v_app (m/s).  The heel then comes down at whatever speed this geometry gives."""
        h = 2e-3
        v_fwd = self.p["v_app"]
        heel1, pitch1 = self.leg_points(side, t1, c1)
        fwd = self.footprint(side, k)["fwd"]
        lat = np.array([fwd[2], 0.0, -fwd[0]])
        idx = (0, 1, 4)            # hip flexion, hip ab/adduction, ankle flexion

        def resid(x):
            v = np.zeros(8)
            v[list(idx)] = x
            heel0, pitch0 = self.leg_points(side, t1 - h, c1 - h * v)
            vel = (heel1 - heel0) / h
            return np.array([vel @ fwd - v_fwd, vel @ lat, (pitch1 - pitch0) / h])

        x = np.zeros(3)
        for _ in range(10):
            r = resid(x)
            if np.max(np.abs(r)) < 1e-9:
                break
            Jm = np.zeros((3, 3))
            for i in range(3):
                dx = np.zeros(3)
                dx[i] = 1e-4
                Jm[:, i] = (resid(x + dx) - r) / 1e-4
            x = x - np.linalg.solve(Jm, r)
        v = np.zeros(8)
        v[list(idx)] = x
        return v

    def swing_splines(self, side, k):
        """Per-channel clamped cubic splines over the swing (s in [0, 1]).

        Channel order: hip (X, Z, Y), knee, ankle (X, Z, Y), toe.  Signs: hip X < 0 is
        flexion, knee > 0 is flexion, ankle X < 0 is dorsiflexion, toe < 0 is extension.
        Start: angle and velocity of the stance leg at toe-off.  End: angle of the stance leg
        at heel strike, with the rigid-leg approach velocity of approach_velocity().
        Via points follow normal swing kinematics: knee flexion peaks (~60 deg) at ~30 % of
        swing and is almost straight just before contact; hip flexion peaks late in swing
        and retracts slightly into contact; the ankle keeps plantarflexing briefly after
        toe-off, then dorsiflexes to about neutral."""
        key = ("spl", side, k)
        if key in self._swing_cache:
            return self._swing_cache[key]
        p = self.p
        sp = self.swing_spec(side, k)
        D = sp["t1"] - sp["t0"]
        c0, c1, v0, v1 = sp["c0"], sp["c1"], sp["v0"], sp["v1"]
        knots = {}
        # hip flexion (negative X)
        f0, f1 = -c0[0], -c1[0]
        fpk = f1 + p["hip_retract"]
        knots[0] = ([0.0, 0.35, 0.80, 1.0], [-f0, -(f0 + 0.68 * (fpk - f0)), -fpk, -f1])
        # knee
        k0, k1 = c0[3], c1[3]
        knots[3] = ([0.0, p["knee_pk_s"], 0.50, 0.66, 0.86, 1.0],
                    [k0, p["knee_pk"], 55.0 * DEG, 35.0 * DEG, k1 + 3.0 * DEG, k1])
        # ankle dorsiflexion (negative X)
        d0, d1 = -c0[4], -c1[4]
        knots[4] = ([0.0, 0.12, 0.40, 0.72, 1.0],
                    [-d0, -(d0 - 5.0 * DEG), -4.0 * DEG, -(d1 + 3.0 * DEG), -d1])
        # toes relax from push-off extension, slight extension again before contact
        e0, e1 = -c0[7], -c1[7]
        knots[7] = ([0.0, 0.25, 0.50, 1.0], [-e0, -0.35 * e0, -2.0 * DEG, -e1])
        spl = []
        for ch in range(8):
            S, V = knots.get(ch, ([0.0, 1.0], [c0[ch], c1[ch]]))
            spl.append(CubicSpline(S, V, bc_type=((1, v0[ch] * D), (1, v1[ch] * D))))
        out = (sp, D, spl)
        self._swing_cache[key] = out
        return out

    def swing_channels(self, side, t, k):
        p = self.p
        sp, D, spl = self.swing_splines(side, k)
        s = (t - sp["t0"]) / D
        c = np.array([float(f(s)) for f in spl])
        c[1] += SIDES[side]["sign"] * p["hip_ab_swing"] * bump(s, 3.0, 3.0)  # abduct a little
        return c

    def leg_channels(self, side, t):
        lp = self.leg_phase(side, t)
        k = int(np.floor(lp))
        u = lp - k
        if u < self.p["phi_to"]:
            return self.stance_channels(side, t, k), True
        return self.swing_channels(side, t, k), False

    # ---------------------------------------------------------------- upper body
    def upper_body(self, t, W0):
        """Relative rotations for spine, neck, head, collars, arms and wrists."""
        p = self.p
        ph = self.phase(t)
        v = p["var"]
        out = {}
        # thorax (world): counter-rotates against the pelvis, slight forward lean,
        # small lateral lean toward the stance leg, tiny pitch bob
        t_yaw = 3.2 * DEG * np.cos(2 * np.pi * (ph - 0.04))
        t_pitch = 4.0 * DEG + 0.8 * DEG * np.cos(4 * np.pi * (ph - 0.12))
        t_roll = -1.2 * DEG * np.sin(2 * np.pi * ph)
        Wt = ry(t_yaw) @ rx(t_pitch) @ rz(t_roll)
        Q = W0.T @ Wt
        for name, f in zip(("spine1", "spine2", "spine3"), (0.30, 0.35, 0.35)):
            out[IDX[name]] = frac_rot(Q, f)
        # head: stabilised in space, looking slightly down the path, slow small drift
        h_yaw = 0.25 * t_yaw + v * 1.5 * DEG * np.sin(2 * np.pi * t / 5.3 + 0.4)
        h_pitch = (7.0 * DEG - 0.6 * DEG * np.cos(4 * np.pi * (ph - 0.30))
                   + v * 1.0 * DEG * np.sin(2 * np.pi * t / 3.7 + 1.3))
        h_roll = 0.3 * t_roll
        Wh = ry(h_yaw) @ rx(h_pitch) @ rz(h_roll)
        Qh = Wt.T @ Wh
        out[IDX["neck"]] = frac_rot(Qh, 0.55)
        out[IDX["head"]] = frac_rot(Qh, 0.45)

        # arms.  The visible arm is the shoulder->wrist line of the rest mesh (the elbow
        # joints of this skeleton sit off that line, differently on the two sides), so the
        # shoulder rotation aligns that rest vector with the wanted hang direction.
        for side, sign, off in (("left", 1.0, 0.0), ("right", -1.0, 0.5)):
            phs = ph - off
            amp_var = 1.0 + v * 0.06 * np.sin(2 * np.pi * t / 4.7 + (0.9 if sign > 0 else 2.6))
            fwd = np.cos(2 * np.pi * (phs - 0.55))           # +1 = arm most forward
            fwd2 = np.cos(4 * np.pi * (phs - 0.55))
            swing = (16.0 * DEG * fwd + 2.0 * DEG * fwd2) * amp_var
            # shoulder flexion (+ forward) in the thorax frame; arms hang with gravity, so add
            # the thorax forward lean; mean slightly behind the body line
            flex = -6.0 * DEG + swing + t_pitch
            # a bit wider when behind; the right shoulder joint of this skeleton sits 1.2 cm
            # closer to the midline, so that arm gets 1.2 deg more to mirror the left one
            abd = (11.0 + (1.2 if sign < 0 else 0.0)) * DEG - 1.5 * DEG * fwd
            col = rz(-sign * 5.0 * DEG) @ ry(-sign * 3.0 * DEG * fwd)   # drop + protract
            out[IDX[side + "_collar"]] = col
            d = rx(-flex) @ rz(sign * abd) @ np.array([0.0, -1.0, 0.0])   # wanted arm axis
            base = rz(-sign * 90.0 * DEG)                    # T-pose -> arm down, palm medial
            Q = rot_between(base @ ARM_REST[side], d) @ base
            Q = rodrigues(d, sign * 14.0 * DEG) @ Q          # humeral internal rotation
            out[IDX[side + "_shoulder"]] = col.T @ Q
            # elbow: flexion peaks just after the most forward arm position
            fwd_e = np.cos(2 * np.pi * (phs - 0.60))
            el = (22.0 * DEG + 12.0 * DEG * fwd_e) * (0.5 + 0.5 * amp_var)
            out[IDX[side + "_elbow"]] = ry(-sign * el)
            # wrist: slight flexion with a passive lag
            wr = 7.0 * DEG + 4.0 * DEG * np.cos(2 * np.pi * (phs - 0.72))
            out[IDX[side + "_wrist"]] = rz(-sign * wr) @ ry(-sign * 3.0 * DEG)
        return out

    # ---------------------------------------------------------------- full pose
    def pose(self, t):
        P0 = self.pelvis_pos(t)
        W0 = self.pelvis_rot(t)
        R = [np.eye(3) for _ in range(22)]
        R[0] = W0
        info = {}
        for side in ("L", "R"):
            sd = SIDES[side]
            ch, stance = self.leg_channels(side, t)
            R[sd["hip"]] = from_euler(ch[0:3])
            R[sd["knee"]] = rx(ch[3])
            R[sd["ankle"]] = from_euler(ch[4:7])
            R[sd["toe"]] = rx(ch[7])
            info[side] = dict(ch=ch, stance=stance)
        for j, M in self.upper_body(t, W0).items():
            R[j] = M
        return P0, R, info

    def generate(self, nframes=NFRAMES, fps=FPS):
        transl = np.zeros((nframes, 3))
        go = np.zeros((nframes, 3))
        bp = np.zeros((nframes, 21, 3))
        for f in range(nframes):
            P0, R, _ = self.pose(f / fps)
            transl[f] = P0 - J[0]
            go[f] = Rot.from_matrix(R[0]).as_rotvec()
            bp[f] = Rot.from_matrix(np.stack(R[1:])).as_rotvec()
        # pelvis above the origin at frame 0 (x and z of transl = 0)
        transl[:, 0] -= transl[0, 0]
        transl[:, 2] -= transl[0, 2]
        return transl, go, bp


# ----------------------------------------------------------------------------- forward kinematics
def fk(transl, R):
    """World rotations W and positions P of the 22 body joints (as in SMPLX_INTERFACE.md)."""
    W = [None] * 22
    P = np.zeros((22, 3))
    for i in range(22):
        if i == 0:
            W[0] = R[0]
            P[0] = J[0] + transl
        else:
            pa = PARENT[i]
            W[i] = W[pa] @ R[i]
            P[i] = P[pa] + W[pa] @ (J[i] - J[pa])
    return W, P


def main():
    g = Gait()
    transl, go, bp = g.generate()
    out = os.path.join(HERE, "motion.npz")
    np.savez(out, fps=np.int64(FPS), transl=transl.astype(np.float32),
             global_orient=go.astype(np.float32), body_pose=bp.astype(np.float32))
    print("d_hs = %.4f m, static obliquity = %.2f deg" % (g.p["d_hs"], g.p["roll0"] / DEG))
    print("pelvis-height coefficients:", np.round(g.p["ycoef"], 4))
    print("wrote", out)


if __name__ == "__main__":
    main()
