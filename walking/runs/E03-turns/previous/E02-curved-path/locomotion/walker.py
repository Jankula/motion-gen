"""The walker: steady walking along a WalkLine, produced as SMPL-X joint rotations.

Pipeline (each stage only needs the previous ones):
  1. Speed field along the line (slower in bends) and the gait clock (phase, distance).
  2. Pelvis track: walking line + lateral sway + small forward-speed fluctuation; pelvis
     yaw = line heading + gait oscillation; roll includes a lean into bends.
  3. Footprints: each heel strike is placed on the line a fixed distance ahead of the
     pelvis, offset sideways by half the step width and shifted outwards in bends (the
     centre of mass must be inside the feet to be pulled round the bend); the foot points
     along the line.
  4. Pelvis height: the height that gives a normal stance-knee curve for the leading stance
     leg is computed in closed form, then the highest smooth curve that never exceeds it is
     fitted (asymmetric least squares).
  5. Stance legs: foot rockers + analytic IK (planted feet cannot slide).
     Swing legs: clamped cubic splines in joint space between toe-off and heel strike.
  6. Upper body (upper_body.py).
"""
import numpy as np
import scipy.sparse as sp
from scipy.interpolate import CubicSpline
from scipy.sparse.linalg import spsolve

from .gait import GRAVITY, KNEE_TGT, Clock, make_params
from .legs import HEEL_R, Leg
from .path import WalkLine
from .rotations import (DEG, bump, euler_xzy, from_euler_xzy, mv, rx, ry, rz, to_rotvec)
from .skeleton import FLOOR, J, NJ, PELVIS_HEIGHT
from .upper_body import upper_body


def fit_below(y, lam, margin, iters=60):
    """Smooth curve z that stays below y - margin and is as close to it as possible:
    minimise sum(w (z - y')^2) + lam * sum((D3 z)^2), with large weights w where z would exceed
    y' = y - margin (asymmetric least squares).  Finally shifted down by any remaining excess."""
    n = len(y)
    D = sp.diags([-1.0, 3.0, -3.0, 1.0], [0, 1, 2, 3], shape=(n - 3, n))
    P = lam * (D.T @ D)
    target = y - margin
    w = np.ones(n)
    z = target
    for _ in range(iters):
        z = spsolve((sp.diags(w) + P).tocsc(), w * target)
        w_new = np.maximum(w, np.where(z > target, 1e5, 1.0))   # once active, stays active
        if np.array_equal(w_new, w):
            break
        w = w_new
    return z - max(0.0, float(np.max(z - target)))


class Walker:
    def __init__(self, line, params=None, duration=10.0, calibrate=True):
        self.p = make_params(params)
        p = self.p
        self.line = line
        self.legs = {"L": Leg("L"), "R": Leg("R")}
        self.t_lo, self.t_hi = -2.5, duration + 2.5
        self._speed_field()
        self.clock = Clock(p, line.s, self.f_cad_line, self.f_str_line,
                           self.t_lo - 1.5, self.t_hi + 1.5)
        th0 = {s: self.legs[s].straight_knee for s in "LR"}
        self.knee_offset = {s: p["knee_geo"] * (th0[s] - 0.5 * (th0["L"] + th0["R"])) for s in "LR"}
        if calibrate:
            if p["d_hs"] is None or p["roll0"] is None:
                p["d_hs"], p["roll0"] = calibrate_straight(params)
            self._build_footprints()
            self._solve_height()
        self._swing_cache = {}

    # ================================================================== speed and lean
    def _speed_field(self):
        p, line = self.p, self.line
        k_eff = line.smoothed(np.abs(line.k), p["slow_sigma"])
        k_eff = np.interp(line.s + p["slow_lead"], line.s, k_eff)
        f = 1.0 / (1.0 + p["turn_slow"] * k_eff + p["turn_slow2"] * k_eff ** 2)
        self.f_cad_line = f ** p["cad_share"]
        self.f_str_line = f ** (1.0 - p["cad_share"])
        self.v_line = p["stride"] / p["T"] * f
        lean = p["lean_gain"] * np.arctan(self.v_line ** 2 * line.k / GRAVITY)
        self.lean_line = np.clip(lean, -p["lean_max"], p["lean_max"])

    def lean(self, s):
        """Lean into the bend [rad] at line position s (positive = towards the left)."""
        return self.line.field(self.lean_line, s)

    def foot_shift(self, s):
        """Sideways shift of the feet relative to the pelvis line (positive = to the left).
        Limited so that the inner foot never lands beyond the pelvis line."""
        m = self.p["shift_max"]
        return np.clip(-PELVIS_HEIGHT * np.tan(self.lean(s)), -m, m)

    # ================================================================== pelvis
    def s_pelvis(self, t):
        p = self.p
        ph = self.clock.phase(t)
        S = self.clock.S(t)
        return S + p["z_amp"] * self.clock.f_str(S) * np.sin(4 * np.pi * (ph - 0.07)), ph

    def pelvis(self, t, y=None, extra=False):
        """Pelvis joint position P0 (n, 3) and orientation W0 (n, 3, 3) at times t."""
        p = self.p
        t = np.atleast_1d(np.asarray(t, dtype=float))
        s, ph = self.s_pelvis(t)
        sway = p["x_amp"] * np.cos(2 * np.pi * (ph - p["x_peak"]))
        xz = self.line.pos(s)
        h = self.line.heading(s)
        if y is None:
            y = self._y(t)
        P0 = np.empty((len(t), 3))
        P0[:, 0] = xz[:, 0] + sway * np.cos(h)
        P0[:, 1] = J[0, 1] + y
        P0[:, 2] = xz[:, 1] - sway * np.sin(h)
        yaw = h - p["yaw_amp"] * np.cos(2 * np.pi * (ph + 0.02))
        roll = p["roll_amp"] * (np.sin(2 * np.pi * (ph + 0.03)) + 0.15 * np.sin(6 * np.pi * (ph + 0.03)))
        roll = roll + p["roll0"] - p["pelvis_lean"] * self.lean(s)
        pitch = p["pitch_mean"] + p["pitch_amp"] * np.cos(4 * np.pi * (ph - 0.45))
        W0 = ry(yaw) @ rx(pitch) @ rz(roll)
        if extra:
            return P0, W0, s
        return P0, W0

    # ================================================================== footprints
    def footprints(self, side, ks):
        """Footprint geometry for heel strikes k of one side (vectorised).  Footprint k of a leg
        is placed when its leg phase (gait phase + offset) equals k."""
        p, leg, line = self.p, self.legs[side], self.line
        ks = np.atleast_1d(np.asarray(ks, dtype=float))
        t_hs = self.clock.event_time(ks - leg.offset)
        s_pel, _ = self.s_pelvis(t_hs)
        s_fp = s_pel + p["d_hs"] * self.clock.f_str(self.clock.S(t_hs))
        ph_s = 0.0 if side == "L" else 1.9
        # small step-to-step scatter of foot placement (deterministic): +-4 mm sideways and
        # +-1 deg toe-out, as in real walking
        dx = p["var"] * 0.004 * np.sin(2.1 * ks + ph_s)
        dyaw = p["var"] * 1.0 * DEG * np.sin(1.3 * ks + 0.7 + ph_s)
        yaw = line.heading(s_fp + p["foot_yaw_lead"]) + leg.sign * (p["toe_out"] + dyaw)
        lat = leg.sign * (p["heel_x"] + dx) + self.foot_shift(s_fp + p["shift_lead"])
        base = line.pos(s_fp)
        nrm = line.normal(s_fp)
        n = len(ks)
        c_hs = np.stack([base[:, 0] + lat * nrm[:, 0], np.full(n, FLOOR + HEEL_R),
                         base[:, 1] + lat * nrm[:, 1]], -1)
        fwd = np.stack([np.sin(yaw), np.zeros(n), np.cos(yaw)], -1)
        Fy = ry(yaw)
        c_flat = c_hs + HEEL_R * p["alpha_hs"] * fwd      # the heel rolls forward
        tip_flat = c_flat + mv(Fy, leg.tip - leg.heel_c)
        return dict(t_hs=t_hs, c_flat=c_flat, tip_flat=tip_flat, fwd=fwd, Fy=Fy, yaw=yaw)

    def _build_footprints(self):
        self.fp = {}
        ph_lo = float(self.clock.phase(self.t_lo))
        ph_hi = float(self.clock.phase(self.t_hi))
        for side, leg in self.legs.items():
            k0 = int(np.floor(ph_lo + leg.offset)) - 2
            k1 = int(np.floor(ph_hi + leg.offset)) + 3
            ks = np.arange(k0, k1 + 1)
            self.fp[side] = (k0, self.footprints(side, ks))

    def fp_gather(self, side, k):
        k0, tab = self.fp[side]
        i = np.asarray(k, dtype=int) - k0
        return {key: val[i] for key, val in tab.items()}

    # ================================================================== pelvis height
    def y_required(self, side, k, t, fp=None):
        """Pelvis height offset that gives the target knee flexion of a leading stance leg
        (closed form: the target knee angle fixes the hip-ankle distance)."""
        leg = self.legs[side]
        t = np.atleast_1d(np.asarray(t, dtype=float))
        k = np.atleast_1d(k)
        u = self.clock.phase(t) + leg.offset - k
        if fp is None:
            fp = self.fp_gather(side, k)
        _, ank, _ = leg.stance_foot(fp, u, self.p)
        P0, W0 = self.pelvis(t, y=np.zeros(len(t)))
        hip = P0 + mv(W0, leg.hip_off)
        d = leg.distance_from_knee(KNEE_TGT(u) * DEG + self.knee_offset[side])
        dv = hip - ank
        h2 = dv[:, 0] ** 2 + dv[:, 2] ** 2
        return -dv[:, 1] + np.sqrt(np.maximum(d * d - h2, 0.0))

    def _solve_height(self):
        p = self.p
        tg = np.arange(self.t_lo, self.t_hi, 1.0 / p["y_rate"])
        ph = self.clock.phase(tg)
        yreq = np.empty(len(tg))
        for side, leg in self.legs.items():
            lp = ph + leg.offset
            k = np.floor(lp)
            lead = (lp - k) < 0.5
            yreq[lead] = self.y_required(side, k[lead].astype(int), tg[lead])
        yfit = fit_below(yreq, p["y_lambda"] * (p["y_rate"] / 120.0) ** 6, p["y_margin"])
        self.y_samples = (tg, yreq, yfit)
        self._y = CubicSpline(tg, yfit)

    # ================================================================== stance
    def stance_pose(self, side, k, t):
        leg = self.legs[side]
        t = np.atleast_1d(np.asarray(t, dtype=float))
        k = np.atleast_1d(k)
        u = self.clock.phase(t) + leg.offset - k
        P0, W0 = self.pelvis(t)
        hip = P0 + mv(W0, leg.hip_off)
        F, ank, toe = leg.stance_foot(self.fp_gather(side, k), u, self.p, hip)
        Rh, th, Ra, q = leg.ik(P0, W0, F, ank)
        return Rh, th, Ra, toe, q

    def stance_channels(self, side, k, t):
        """Channels: hip (X, Z, Y), knee, ankle (X, Z, Y), toe."""
        Rh, th, Ra, toe, _ = self.stance_pose(side, k, t)
        return np.concatenate([euler_xzy(Rh), th[:, None], euler_xzy(Ra), toe[:, None]], -1)

    # ================================================================== swing
    def leg_points(self, side, t, ch):
        """World heel-circle centre and foot pitch for leg channels ch (m, 8) at time t."""
        leg = self.legs[side]
        m = len(ch)
        P0, W0 = self.pelvis(np.full(m, t))
        Wh = W0 @ from_euler_xzy(ch[:, 0:3])
        Ph = P0 + mv(W0, leg.hip_off)
        Wk = Wh @ rx(ch[:, 3])
        Pk = Ph + mv(Wh, leg.a)
        Wa = Wk @ from_euler_xzy(ch[:, 4:7])
        Pa = Pk + mv(Wk, leg.b)
        heel = Pa + mv(Wa, leg.heel_c - J[leg.ankle])
        fwd = Wa[:, :, 2]
        return heel, np.arctan2(-fwd[:, 1], np.hypot(fwd[:, 0], fwd[:, 2]))

    def approach_velocity(self, side, k, t1, c1):
        """Joint velocities just before heel strike for a rigid-leg approach: the knee is
        momentarily still, the foot keeps its pitch, and the hip moves so that the heel travels
        forward over the floor at v_app (m/s) without sideways drift.  The heel then comes
        down at whatever speed this geometry gives."""
        h = 2e-3
        heel1, pitch1 = self.leg_points(side, t1, c1[None])
        fwd = self.fp_gather(side, [k])["fwd"][0]
        lat = np.array([fwd[2], 0.0, -fwd[0]])
        idx = [0, 1, 4]            # hip flexion, hip ab/adduction, ankle flexion

        def resid(X):              # X (m, 3) candidate velocities -> residuals (m, 3)
            V = np.zeros((len(X), 8))
            V[:, idx] = X
            heel0, pitch0 = self.leg_points(side, t1 - h, c1[None] - h * V)
            vel = (heel1 - heel0) / h
            return np.stack([vel @ fwd - self.p["v_app"], vel @ lat, (pitch1 - pitch0) / h], -1)

        x = np.zeros(3)
        eps = 1e-4
        for _ in range(10):
            X = np.vstack([x, x + eps * np.eye(3)])
            Rr = resid(X)
            r = Rr[0]
            if np.max(np.abs(r)) < 1e-9:
                break
            Jm = (Rr[1:] - r).T / eps
            x = x - np.linalg.solve(Jm, r)
        v = np.zeros(8)
        v[idx] = x
        return v

    def swing_splines(self, side, k):
        """Per-channel clamped cubic splines over the swing that follows stance k (s in [0, 1]).

        Signs: hip X < 0 is flexion, knee > 0 is flexion, ankle X < 0 is dorsiflexion,
        toe < 0 is extension.  Start: angle and velocity of the stance leg at toe-off.  End:
        the stance pose at the next heel strike with the rigid-leg approach velocity.  Via
        points follow normal swing kinematics: knee flexion peaks (~60 deg) at ~30 % of swing
        and is almost straight just before contact; hip flexion peaks late in swing and
        retracts slightly into contact; the ankle keeps plantarflexing briefly after toe-off,
        then dorsiflexes to about neutral.  Hip ab/adduction and rotation, which re-orient the
        foot for the next footprint in a bend, go smoothly from start to end."""
        key = (side, k)
        if key in self._swing_cache:
            return self._swing_cache[key]
        p, leg = self.p, self.legs[side]
        t0 = float(self.clock.event_time(k + p["phi_to"] - leg.offset))
        t1 = float(self.clock.event_time(k + 1 - leg.offset))
        h = 2e-3
        c = self.stance_channels(side, np.full(3, k), np.array([t0, t0 - h, t0 - 2 * h]))
        c0 = c[0]
        v0 = (3 * c[0] - 4 * c[1] + c[2]) / (2 * h)       # stance-side velocity at toe-off
        c1 = self.stance_channels(side, [k + 1], [t1])[0]
        v1 = self.approach_velocity(side, k + 1, t1, c1)
        D = t1 - t0
        knots = {}
        f0, f1 = -c0[0], -c1[0]
        fpk = f1 + p["hip_retract"]
        knots[0] = ([0.0, 0.35, 0.80, 1.0], [-f0, -(f0 + 0.68 * (fpk - f0)), -fpk, -f1])
        k0, k1 = c0[3], c1[3]
        knots[3] = ([0.0, p["knee_pk_s"], 0.50, 0.66, 0.86, 1.0],
                    [k0, p["knee_pk"], 55.0 * DEG, 35.0 * DEG, k1 + 3.0 * DEG, k1])
        d0, d1 = -c0[4], -c1[4]
        knots[4] = ([0.0, 0.12, 0.40, 0.72, 1.0],
                    [-d0, -(d0 - 5.0 * DEG), -4.0 * DEG, -(d1 + 3.0 * DEG), -d1])
        e0, e1 = -c0[7], -c1[7]
        knots[7] = ([0.0, 0.25, 0.50, 1.0], [-e0, -0.35 * e0, -2.0 * DEG, -e1])
        spl = []
        for ch in range(8):
            S, V = knots.get(ch, ([0.0, 1.0], [c0[ch], c1[ch]]))
            spl.append(CubicSpline(S, V, bc_type=((1, v0[ch] * D), (1, v1[ch] * D))))
        out = (t0, D, spl)
        self._swing_cache[key] = out
        return out

    def swing_channels(self, side, k, t):
        t0, D, spl = self.swing_splines(side, k)
        s = (np.asarray(t, dtype=float) - t0) / D
        c = np.stack([f(s) for f in spl], -1)
        c[:, 1] += self.legs[side].sign * self.p["hip_ab_swing"] * bump(s, 3.0, 3.0)
        return c

    # ================================================================== whole clip
    def pose_rotations(self, t):
        """Pelvis position (n, 3) and local rotations R (n, 22, 3, 3) at times t."""
        t = np.asarray(t, dtype=float)
        n = len(t)
        P0, W0, s_pel = self.pelvis(t, extra=True)
        R = np.tile(np.eye(3), (n, NJ, 1, 1))
        R[:, 0] = W0
        ph = self.clock.phase(t)
        self.diag = {}
        for side, leg in self.legs.items():
            lp = ph + leg.offset
            k = np.floor(lp).astype(int)
            u = lp - k
            st = u < self.p["phi_to"]
            i = np.nonzero(st)[0]
            if len(i):
                Rh, th, Ra, toe, q = self.stance_pose(side, k[i], t[i])
                R[i, leg.hip], R[i, leg.knee], R[i, leg.ankle], R[i, leg.toe] = Rh, rx(th), Ra, rx(toe)
                self.diag[side + "_q"] = q
            for kk in np.unique(k[~st]):
                i = np.nonzero(~st & (k == kk))[0]
                c = self.swing_channels(side, int(kk), t[i])
                R[i, leg.hip] = from_euler_xzy(c[:, 0:3])
                R[i, leg.knee] = rx(c[:, 3])
                R[i, leg.ankle] = from_euler_xzy(c[:, 4:7])
                R[i, leg.toe] = rx(c[:, 7])
        for j, M in upper_body(self, t, W0, s_pel).items():
            R[:, j] = M
        return P0, R

    def generate(self, n_frames, fps):
        t = np.arange(n_frames) / float(fps)
        P0, R = self.pose_rotations(t)
        return dict(fps=int(fps), transl=P0 - J[0], global_orient=to_rotvec(R[:, 0]),
                     body_pose=to_rotvec(R[:, 1:]))


def calibrate_straight(params=None, k=2):
    """Heel-strike distance d_hs and static pelvic obliquity roll0 for steady straight walking.

    The SMPL-X skeleton is slightly asymmetric, so with one heel-strike distance for both feet
    the required pelvis height would jump when the leading leg changes.  Newton iteration on
    (d_hs, roll0) makes both hand-overs continuous."""
    q = make_params(params)
    q.update(var=0.0, d_hs=0.235, roll0=0.0)
    w = Walker(WalkLine([0.0, 0.0], 0.0, [{"type": "straight", "length": 20.0}]), q,
               duration=4.0, calibrate=False)
    t1 = float(w.clock.event_time(k + 0.5))
    t2 = float(w.clock.event_time(k + 1.0))
    eps = 1e-6

    def mismatch(x):
        w.p["d_hs"], w.p["roll0"] = float(x[0]), float(x[1])
        yr = lambda side, kk, t: w.y_required(side, [kk], [t], fp=w.footprints(side, [kk]))[0]
        return np.array([yr("L", k, t1 - eps) - yr("R", k + 1, t1),
                         yr("R", k + 1, t2 - eps) - yr("L", k + 1, t2)])

    x = np.array([0.235, 0.0])
    for _ in range(15):
        m = mismatch(x)
        if np.max(np.abs(m)) < 1e-7:
            break
        Jm = np.zeros((2, 2))
        for i in range(2):
            dx = np.zeros(2)
            dx[i] = 1e-4
            Jm[:, i] = (mismatch(x + dx) - m) / 1e-4
        x = x - np.linalg.solve(Jm, m)
    return float(x[0]), float(x[1])
