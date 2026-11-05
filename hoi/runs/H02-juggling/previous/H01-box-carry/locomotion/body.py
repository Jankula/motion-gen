"""The body: from a footstep plan to SMPL-X joint rotations.

Pipeline (each stage only needs the previous ones):
  1. Balance (balance.py): centre of pressure from the plants, centre of mass from the
     inverted pendulum, the pelvis heading program, and the lean against sustained
     accelerations (bends, starts, stops).
  2. Pelvis: horizontal position = centre of mass; heading from the plan plus the gait's
     pelvis rotation; tilt (pelvic drop, forward tilt, lean); all gait oscillations are
     scaled by the step size, so they fade in when starting and out when stopping.
  3. Pelvis height: for every weight-bearing leg the height that gives its target knee angle
     is computed in closed form; the highest smooth curve that never exceeds the lowest of
     these is fitted (asymmetric least squares).
     Every touch-down's requirement is applied to the samples on both sides of it, so the
     curve cannot overshoot between samples when a leg takes the weight.  A second pass adds
     the requirement that a leg swinging along a foot path (side steps, steps on the spot)
     can reach its foot (reach_max), and that stance knees are softer while side-stepping.
  4. Legs.  Stance: foot rockers + analytic IK (a planted foot cannot slide); when the body
     has turned over a planted foot (corners), the foot pivots on the forefoot before toe off.
     Swing: walking steps are clamped cubic splines in joint space (normal swing kinematics),
     with guards that add knee/hip flexion where the toes would pass too low and hip
     abduction where the foot would pass too close to the planted one; small steps on the
     spot and side steps move the foot along a lifted path in space (kept clear of the floor
     and of the other foot) and use IK; a side step is lifted before it moves and stops
     moving before it is put down.
  5. Upper body (upper_body.py).
"""
import numpy as np
import scipy.sparse as sp
from scipy.interpolate import CubicSpline
from scipy.ndimage import gaussian_filter1d
from scipy.sparse.linalg import spsolve

from .balance import cop_path, lipm_com, smoothed_acceleration
from .gait import GRAVITY, KNEE_TGT, knee_target, make_params
from .legs import Leg
from .path import hdir, lnorm
from .plan import SIDES
from .rotations import (DEG, bump, euler_xzy, from_euler_xzy, hermite, mv, rx, ry, rz,
                        smootherstep, smoothstep, to_rotvec, wrap, yaw_of)
from .skeleton import FLOOR, J, NJ, foot_outline, sole_points
from .upper_body import upper_body

DT_GRID = 1.0 / 120.0


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


def foot_pitch(F):
    """Pitch (positive = toes down) of foot orientations F = Ry(yaw) Rx(pitch)."""
    f = F[..., :, 2]
    return np.arctan2(-f[..., 1], np.hypot(f[..., 0], f[..., 2]))


class Body:
    def __init__(self, plan, window, solve_height=True):
        self.plan = plan
        self.p = plan.p
        p = self.p
        self.legs = {s: Leg(s) for s in SIDES}
        th0 = {s: self.legs[s].straight_knee for s in SIDES}
        self.knee_offset = {s: p["knee_geo"] * (th0[s] - 0.5 * (th0["L"] + th0["R"])) for s in SIDES}
        self.t_a, self.t_b = window
        self._balance()
        self._tables()
        self._swing_cache = {}
        if solve_height:
            self._solve_height()

    # ================================================================== plant tables
    def _tables(self):
        self.tab = {}
        for side in SIDES:
            pl = self.plan.plants[side]
            leg = self.legs[side]
            yaw = np.array([P.yaw for P in pl])
            Fy = ry(yaw)
            c_flat, tip_flat = leg.flat_foot(np.array([P.xz for P in pl]), Fy)
            self.tab[side] = dict(
                t_on=np.array([P.t_on for P in pl]), t_off=np.array([P.t_off for P in pl]),
                Fy=Fy, fwd=Fy[:, :, 2].copy(), c_flat=c_flat, tip_flat=tip_flat,
                alpha=np.array([P.alpha for P in pl]), push=np.array([P.push for P in pl]),
                pivot=self._pivots(side, pl))

    def _pivots(self, side, plants):
        """Yaw by which each plant pivots on the ball of the foot before toe off: a share of
        the misalignment between the foot and the body heading at toe off (beyond the normal
        toe-out and pivot_free), so that the leg is not twisted and over-stretched when the
        body has turned over a planted foot (corners, turns).  In and out of a passage the
        foot placements and heading program are planned so that the hips can absorb the
        twist (side_pivot_free); the foot only pivots beyond that, because a pivoting foot
        slides on the floor."""
        p = self.p
        out = np.zeros(len(plants))
        sg = 1.0 if side == "L" else -1.0
        for i, P in enumerate(plants):
            if not P.lifts or P.lift.kind == "shuffle" or P.lift.lift_style != "walk":
                continue
            passage = P.lift.kind == "side" or (P.landing and P.step.kind == "side")
            free = p["side_pivot_free"] if passage else p["pivot_free"]
            ex = float(wrap(self.psi([P.t_off])[0] + sg * p["toe_out"] - P.yaw))
            mag = max(0.0, abs(ex) - free) * p["pivot_gain"]
            out[i] = np.sign(ex) * min(mag, p["pivot_max"])
        return out

    def lookup(self, side, t):
        """Index of the current (or last) plant of a foot, and whether it is on the floor."""
        tab = self.tab[side]
        t = np.asarray(t, dtype=float)
        idx = np.clip(np.searchsorted(tab["t_on"], t, side="right") - 1, 0, len(tab["t_on"]) - 1)
        return idx, t < tab["t_off"][idx]

    def gather(self, side, idx):
        tab = self.tab[side]
        idx = np.asarray(idx, dtype=int)
        return {k: tab[k][idx] for k in ("Fy", "fwd", "c_flat", "tip_flat", "alpha", "push", "pivot")}

    def u_lam(self, side, idx, t):
        idx = np.atleast_1d(np.asarray(idx, dtype=int))
        t = np.atleast_1d(np.asarray(t, dtype=float))
        u = np.empty(len(t))
        lam = np.empty(len(t))
        plants = self.plan.plants[side]
        for i in np.unique(idx):
            m = idx == i
            u[m] = plants[i].u(t[m])
            lam[m] = plants[i].lam_at(t[m])
        return u, lam

    # ================================================================== balance
    def _balance(self):
        p, plan = self.p, self.plan
        t0 = min(plan.t_first - 2.0, self.t_a - 1.0)
        t1 = max(plan.t_last + 2.0, self.t_b + 1.0)
        n = int(np.ceil((t1 - t0) / DT_GRID)) + 1
        tg = t0 + np.arange(n) * DT_GRID
        e = plan.step_env(tg)
        g = plan.size_env(tg)
        cop0 = cop_path(plan, tg)
        com0, omega = lipm_com(tg, cop0, p["com_height"])
        psi0 = plan.heading(tg, com0)
        cop = cop_path(plan, tg, dict(heading=psi0, weight=1.0 - e))
        com, _ = lipm_com(tg, cop, p["com_height"])
        psi = gaussian_filter1d(plan.heading(tg, com), 0.04 / DT_GRID, mode="nearest")
        acc = smoothed_acceleration(com, cop, omega, DT_GRID, p["lean_sigma"])
        a_fwd = np.sum(acc * hdir(psi), -1)
        a_lat = np.sum(acc * lnorm(psi), -1)
        self.grid = dict(t=tg, cop=cop, com=com, psi=psi, g=g, e=e,
                         lean_lat=np.clip(p["lean_gain"] * np.arctan(a_lat / GRAVITY),
                                          -p["lean_max"], p["lean_max"]),
                         lean_fwd=np.arctan(a_fwd / GRAVITY))
        self.omega = omega
        self._com = CubicSpline(tg, com)
        self._psi = CubicSpline(tg, psi)

    def _gi(self, key, t):
        G = self.grid
        return np.interp(t, G["t"], G[key])

    def com(self, t):
        G = self.grid["t"]
        return self._com(np.clip(t, G[0], G[-1]))

    def psi(self, t):
        G = self.grid["t"]
        return self._psi(np.clip(t, G[0], G[-1]))

    def envelopes(self, t):
        """Gait phase, step size g and stepping envelope e at times t."""
        return self.plan.phase(t), self._gi("g", t), self._gi("e", t)

    def lean(self, t):
        return self._gi("lean_lat", t), self._gi("lean_fwd", t)

    # ================================================================== pelvis
    def pelvis(self, t, y=None):
        """Pelvis joint position P0 (n, 3) and orientation W0 (n, 3, 3) at times t."""
        p = self.p
        t = np.atleast_1d(np.asarray(t, dtype=float))
        ph, g, e = self.envelopes(t)
        gc = np.minimum(g, 1.0)
        psi = self.psi(t)
        lean_lat, _ = self.lean(t)
        xz = self.com(t) + (p["c_walk"] * gc)[:, None] * hdir(psi)
        # posture program (bending down, carrying a load): y given explicitly means the pelvis
        # height is being solved, which is done for the upright body (see Posture)
        post = self.plan.posture
        solving = y is not None
        if post is not None:
            xz = xz + post.shift(t, upright_only=solving)
        if y is None:
            y = self.height(t)
            if post is not None:
                y = y - post.drop(t)
        P0 = np.stack([xz[:, 0], J[0, 1] + y, xz[:, 1]], -1)
        yaw = psi - p["yaw_amp"] * g * np.cos(2 * np.pi * (ph + 0.02))
        a_roll = e * (0.4 + 0.6 * gc) * (1.0 - self.plan.side_env(t))   # no swing-side drop sideways
        roll = p["roll_amp"] * a_roll * (np.sin(2 * np.pi * (ph + 0.03)) + 0.15 * np.sin(6 * np.pi * (ph + 0.03)))
        roll = roll + p["roll0"] - p["pelvis_lean"] * lean_lat
        pitch = (p["pitch_stand"] + (p["pitch_mean"] - p["pitch_stand"]) * gc
                 + p["pitch_amp"] * g * np.cos(4 * np.pi * (ph - 0.45)))
        if post is not None and not solving:
            pitch = pitch + post.tilt(t)
            yaw = yaw + post.pelvis_yaw(t)
            roll = roll + post.pelvis_roll(t)
        W0 = ry(yaw) @ rx(pitch) @ rz(roll)
        return P0, W0

    def height(self, t):
        tg = self._y.x
        return self._y(np.clip(t, tg[0], tg[-1]))

    # ================================================================== pelvis height
    def y_required(self, side, idx, t, u, lam):
        """Pelvis height offset that gives the target knee flexion of a weight-bearing leg
        (closed form: the target knee angle fixes the hip-ankle distance)."""
        leg = self.legs[side]
        t = np.atleast_1d(np.asarray(t, dtype=float))
        _, ank, _ = leg.stance_foot(self.gather(side, idx), u, self.p)
        P0, W0 = self.pelvis(t, y=np.zeros(len(t)))
        hip = P0 + mv(W0, leg.hip_off)
        # side-stepping through a gap is done on softer knees (gives the legs more reach), and
        # so is walking under a load
        knee = knee_target(u, lam, self.p) * DEG + self.p["side_knee"] * self.plan.side_env(t)
        if self.plan.posture is not None:
            knee = knee + self.plan.posture.soft_knee(t)
        d = leg.distance_from_knee(knee + self.knee_offset[side])
        dv = hip - ank
        h2 = dv[:, 0] ** 2 + dv[:, 2] ** 2
        return -dv[:, 1] + np.sqrt(np.maximum(d * d - h2, 0.0))

    def _solve_height(self):
        p = self.p
        tg = np.arange(self.t_a, self.t_b, 1.0 / p["y_rate"])
        yreq = np.full(len(tg), np.inf)
        for side in SIDES:
            idx, contact = self.lookup(side, tg)
            u, lam = self.u_lam(side, idx, tg)
            role = contact & (u < 0.5)
            i = np.nonzero(role)[0]
            if len(i):
                yreq[i] = np.minimum(yreq[i], self.y_required(side, idx[i], tg[i], u[i], lam[i]))
        # the requirement drops sharply when a leg takes the weight: make the samples on both
        # sides of each touch-down respect it, so the fitted curve cannot overshoot in between
        dt = 1.0 / p["y_rate"]
        for side in SIDES:
            t_on = self.tab[side]["t_on"]
            for i in np.nonzero((t_on > tg[0] + dt) & (t_on < tg[-1] - dt))[0]:
                tt = np.array([t_on[i], t_on[i] + 0.5 * dt])
                u, lam = self.u_lam(side, [i, i], tt)
                y = self.y_required(side, [i, i], tt, u, lam).min()
                j = np.searchsorted(tg, t_on[i])
                yreq[j - 1:j + 1] = np.minimum(yreq[j - 1:j + 1], y)
        ok = np.isfinite(yreq)
        if not ok.all():
            yreq[~ok] = np.interp(tg[~ok], tg[ok], yreq[ok])
        lam_y = p["y_lambda"] * (p["y_rate"] / 120.0) ** 6
        yfit = fit_below(yreq, lam_y, p["y_margin"])
        self._y = CubicSpline(tg, yfit)
        # second pass: the pelvis must also be low enough for a leg swinging along a foot path
        # (side steps, steps on the spot) to reach its foot; the paths depend a little on the
        # pelvis height, so they are recomputed afterwards
        y_sw = self._swing_reach(tg)
        if np.any(y_sw < yfit + p["y_margin"]):
            yreq = np.minimum(yreq, y_sw)
            yfit = fit_below(yreq, lam_y, p["y_margin"])
            self._y = CubicSpline(tg, yfit)
            self._swing_cache = {}
        self.y_samples = (tg, yreq, yfit)

    def _swing_reach(self, tg):
        """Highest pelvis height offset at which every foot-path swing leg reaches its planned
        ankle position with the hip-ankle distance at most reach_max of the straight leg."""
        out = np.full(len(tg), np.inf)
        for side, leg in self.legs.items():
            idx, contact = self.lookup(side, tg)
            sw = np.nonzero(~contact)[0]
            d_lim = self.p["reach_max"] * float(leg.distance_from_knee(np.array(leg.straight_knee)))
            for k in np.unique(idx[sw]):
                if self.plan.plants[side][k + 1].step.kind == "walk":
                    continue
                i = sw[idx[sw] == k]
                _, A, _ = self.shuffle_foot(side, int(k), tg[i])
                P0, W0 = self.pelvis(tg[i], y=np.zeros(len(i)))
                dv = P0 + mv(W0, leg.hip_off) - A
                h2 = dv[:, 0] ** 2 + dv[:, 2] ** 2
                out[i] = -dv[:, 1] + np.sqrt(np.maximum(d_lim * d_lim - h2, 0.0))
        return out

    # ================================================================== stance
    def stance_pose(self, side, idx, t):
        leg = self.legs[side]
        t = np.atleast_1d(np.asarray(t, dtype=float))
        idx = np.atleast_1d(np.asarray(idx, dtype=int))
        u, _ = self.u_lam(side, idx, t)
        P0, W0 = self.pelvis(t)
        hip = P0 + mv(W0, leg.hip_off)
        F, ank, toe = leg.stance_foot(self.gather(side, idx), u, self.p, hip)
        Rh, th, Ra, q = leg.ik(P0, W0, F, ank)
        return Rh, th, Ra, toe, q

    def stance_foot_pose(self, side, idx, t):
        leg = self.legs[side]
        t = np.atleast_1d(np.asarray(t, dtype=float))
        idx = np.full(len(t), idx, dtype=int)
        u, _ = self.u_lam(side, idx, t)
        P0, W0 = self.pelvis(t)
        hip = P0 + mv(W0, leg.hip_off)
        return leg.stance_foot(self.gather(side, idx), u, self.p, hip)

    def stance_channels(self, side, idx, t):
        """Channels: hip (X, Z, Y), knee, ankle (X, Z, Y), toe."""
        Rh, th, Ra, toe, _ = self.stance_pose(side, idx, t)
        return np.concatenate([euler_xzy(Rh), th[:, None], euler_xzy(Ra), toe[:, None]], -1)

    # ================================================================== walking swing
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

    def approach_velocity(self, side, idx, t1, c1, v_app):
        """Joint velocities just before heel strike for a rigid-leg approach: the knee is
        momentarily still, the foot keeps its pitch, and the hip moves so that the heel travels
        forward over the floor at v_app (m/s) without sideways drift.  The heel then comes
        down at whatever speed this geometry gives."""
        h = 2e-3
        heel1, pitch1 = self.leg_points(side, t1, c1[None])
        fwd = self.tab[side]["fwd"][idx]
        lat = np.array([fwd[2], 0.0, -fwd[0]])
        sel = [0, 1, 4]            # hip flexion, hip ab/adduction, ankle flexion

        def resid(X):              # X (m, 3) candidate velocities -> residuals (m, 3)
            V = np.zeros((len(X), 8))
            V[:, sel] = X
            heel0, pitch0 = self.leg_points(side, t1 - h, c1[None] - h * V)
            vel = (heel1 - heel0) / h
            return np.stack([vel @ fwd - v_app, vel @ lat, (pitch1 - pitch0) / h], -1)

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
        v[sel] = x
        return v

    def swing_splines(self, side, i):
        """Per-channel clamped cubic splines over the swing from plant i to plant i+1
        (s in [0, 1]).

        Signs: hip X < 0 is flexion, knee > 0 is flexion, ankle X < 0 is dorsiflexion,
        toe < 0 is extension.  Start: angle and velocity of the stance leg at toe-off.  End:
        the stance pose at the next heel strike with the rigid-leg approach velocity.  Via
        points follow normal swing kinematics, scaled down for short steps: knee flexion peaks
        (~60 deg for a full step) at ~30 % of swing and is almost straight just before
        contact; hip flexion peaks late in swing and retracts slightly into contact; the ankle
        keeps plantarflexing briefly after toe-off, then dorsiflexes to about neutral.  Hip
        ab/adduction and rotation, which re-orient the foot for the next footprint, go smoothly
        from start to end."""
        key = ("walk", side, i)
        if key in self._swing_cache:
            return self._swing_cache[key]
        p = self.p
        tab = self.tab[side]
        t0, t1 = float(tab["t_off"][i]), float(tab["t_on"][i + 1])
        h = 2e-3
        c = self.stance_channels(side, np.full(3, i), np.array([t0, t0 - h, t0 - 2 * h]))
        c0 = c[0]
        v0 = (3 * c[0] - 4 * c[1] + c[2]) / (2 * h)       # stance-side velocity at toe-off
        c1 = self.stance_channels(side, [i + 1], [t1])[0]
        travel = float(np.linalg.norm(tab["c_flat"][i + 1] - tab["c_flat"][i]))
        sc = float(np.clip(travel / p["stride"], 0.0, 1.2))
        v1 = self.approach_velocity(side, i + 1, t1, c1, p["v_app"] * min(1.0, np.sqrt(sc / 0.8)))
        D = t1 - t0
        knots = {}
        f0, f1 = -c0[0], -c1[0]
        fpk = f1 + p["hip_retract"] * min(1.0, sc)
        knots[0] = ([0.0, 0.35, 0.80, 1.0], [-f0, -(f0 + 0.68 * (fpk - f0)), -fpk, -f1])
        k0, k1 = c0[3], c1[3]
        kpk = p["knee_pk_min"] + (p["knee_pk"] - p["knee_pk_min"]) * min(1.0, sc) ** 0.6
        kpk = max(kpk, k0 + 5.0 * DEG)
        k66 = max(0.574 * kpk, k1 + 6.0 * DEG)
        knots[3] = ([0.0, p["knee_pk_s"], 0.50, 0.66, 0.86, 1.0],
                    [k0, kpk, max(0.9 * kpk, k66 + 2 * DEG), k66, k1 + 3.0 * DEG, k1])
        d0, d1 = -c0[4], -c1[4]
        knots[4] = ([0.0, 0.12, 0.40, 0.72, 1.0],
                    [-d0, -(d0 - 5.0 * DEG * min(1.0, sc + 0.3)), -4.0 * DEG, -(d1 + 3.0 * DEG), -d1])
        e0, e1 = -c0[7], -c1[7]
        knots[7] = ([0.0, 0.25, 0.50, 1.0], [-e0, -0.5 * e0, -2.0 * DEG, -e1])
        for ch in (1, 2, 5, 6):     # large re-orientations (corners) mostly in mid-swing
            dc = c1[ch] - c0[ch]
            if abs(dc) > 10.0 * DEG:
                knots[ch] = ([0.0, 0.25, 0.75, 1.0],
                             [c0[ch], c0[ch] + 0.15 * dc, c0[ch] + 0.85 * dc, c1[ch]])
        spl = []
        for ch in range(8):
            S, V = knots.get(ch, ([0.0, 1.0], [c0[ch], c1[ch]]))
            spl.append(CubicSpline(S, V, bc_type=((1, v0[ch] * D), (1, v1[ch] * D))))
        out = [t0, D, spl, []]
        self._swing_cache[key] = out
        self._clear_swing(side, out)
        return out

    def swing_channels(self, side, i, t):
        t0, D, spl, extra = self.swing_splines(side, i)
        return self._channels(side, spl, extra, (np.asarray(t, dtype=float) - t0) / D)

    def _channels(self, side, spl, extra, s):
        c = np.stack([f(s) for f in spl], -1)
        sign = self.legs[side].sign
        c[:, 1] += sign * self.p["hip_ab_swing"] * bump(s, 3.0, 3.0)
        for kind, s_pk, amt in extra:    # guard corrections (see _clear_swing)
            w = np.exp(-((s - s_pk) / 0.22) ** 2) * bump(s, 2.0, 2.0) / bump(np.array(s_pk), 2.0, 2.0)
            if kind == "lift":           # more knee and hip flexion
                c[:, 3] += amt * w
                c[:, 0] -= 0.6 * amt * w
            else:                        # more hip abduction (foot further out)
                c[:, 1] += sign * amt * w
        return c

    def foot_frames(self, side, t, ch):
        """World ankle rotation and position for leg channels ch (n, 8) at times t."""
        leg = self.legs[side]
        P0, W0 = self.pelvis(t)
        Wh = W0 @ from_euler_xzy(ch[:, 0:3])
        Ph = P0 + mv(W0, leg.hip_off)
        Wk = Wh @ rx(ch[:, 3])
        Pk = Ph + mv(Wh, leg.a)
        return Wk @ from_euler_xzy(ch[:, 4:7]), Pk + mv(Wk, leg.b)

    def sole_height(self, side, t, ch):
        """Lowest of a few sole points (heel, sole edges, and the toe tip on the toe segment)
        above the floor for leg channels ch (n, 8) at times t."""
        leg = self.legs[side]
        Wa, Pa = self.foot_frames(side, t, ch)
        pts = sole_points(side)[:4] - J[leg.ankle]
        y = Pa[:, None, 1] + np.einsum("nj,kj->nk", Wa[:, 1, :], pts)
        Wt = Wa @ rx(ch[:, 7])
        tip = sole_points(side)[4] - J[leg.toe]
        y_toe = Pa[:, 1] + Wa[:, 1, :] @ (J[leg.toe] - J[leg.ankle]) + Wt[:, 1, :] @ tip
        return np.minimum(y.min(1), y_toe) - FLOOR

    def _other_foot_outline(self, side, tm):
        """Floor outline (k, 2) of the other foot if it is planted at time tm, else None."""
        other = "R" if side == "L" else "L"
        io, on = self.lookup(other, [tm])
        if not on[0]:
            return None
        Fo, ao, _ = self.stance_foot_pose(other, int(io[0]), [tm])
        return (ao[0] + mv(Fo[0], foot_outline(other) - J[self.legs[other].ankle]))[:, [0, 2]]

    def _clear_swing(self, side, sw, gap=0.035):
        """Guards for a walking swing, as a person lifts the foot a little more or swings it a
        little wider when needed:
          * toe clearance: if the swinging foot would pass closer to the floor than swing_clear
            in mid-swing (where it passes the standing leg), add a smooth bump of knee and hip
            flexion where it is lowest;
          * foot clearance: if it would pass closer than gap to the planted foot (tight turns),
            add a smooth bump of hip abduction there."""
        t0, D, spl, extra = sw
        s = np.linspace(0.0, 1.0, 61)
        tt = t0 + s * D
        # clearance wanted: none at lift-off and touch-down, swing_clear where the foot passes
        # the standing leg
        want = self.p["swing_clear"] * np.clip(np.minimum((s - 0.04) / 0.21, (0.92 - s) / 0.07), 0.0, 1.0)
        mid = (s > 0.04) & (s < 0.92)
        po = self._other_foot_outline(side, t0 + 0.5 * D)
        pts = foot_outline(side) - J[self.legs[side].ankle]
        for _ in range(5):
            ch = self._channels(side, spl, extra, s)
            h = self.sole_height(side, tt, ch)
            deficit = np.where(mid, want - h, -1.0)
            i = int(np.argmax(deficit))
            lift = sum(e[2] for e in extra if e[0] == "lift")
            done = True
            if deficit[i] >= 0.001 and lift < 10.0 * DEG:
                extra.append(("lift", float(s[i]), float(deficit[i] / 0.22 + 1.0 * DEG)))
                done = False
            if po is not None:
                Wa, Pa = self.foot_frames(side, tt, ch)
                pw = (Pa[:, None, :] + np.einsum("nij,kj->nki", Wa, pts))[:, :, [0, 2]]
                d = np.linalg.norm(pw[:, :, None, :] - po[None, None, :, :], axis=-1).min(axis=(1, 2))
                short = np.where((s > 0.1) & (s < 0.9), gap - d, -1.0)
                i = int(np.argmax(short))
                wide = sum(e[2] for e in extra if e[0] == "abd")
                if short[i] >= 0.002 and wide < 8.0 * DEG:
                    extra.append(("abd", float(np.clip(s[i], 0.25, 0.75)), float(short[i] / 0.8 + 0.5 * DEG)))
                    done = False
            if done:
                break

    # ================================================================== stepping swing
    def shuffle_path(self, side, i):
        """Foot path of a small step from plant i to plant i+1 (kinds shuffle and side): the
        ankle moves on a cubic Hermite curve that leaves and arrives with the stance foot's own
        velocity, the foot turns smoothly to its new heading, and the path is lifted so that
        the lowest point of the sole clears the floor by the step's lift height in mid-swing
        (and never touches it).

        Side steps: the foot is picked up before it moves and has stopped moving before it is
        put down (the horizontal motion runs over the middle of the swing, between side_hold
        at either end, while the lift rises and falls over the first and last quarter), so
        that it neither scuffs nor slides on the floor.  A foot leaving with a walking push-off
        (lift_style 'walk') keeps its toe-off velocity instead of the initial hold."""
        key = ("shuffle", side, i)
        if key in self._swing_cache:
            return self._swing_cache[key]
        p = self.p
        leg = self.legs[side]
        tab = self.tab[side]
        t0, t1 = float(tab["t_off"][i]), float(tab["t_on"][i + 1])
        D = t1 - t0
        h = 2e-3
        step = self.plan.plants[side][i + 1].step
        F0, a0, toe0 = self.stance_foot_pose(side, i, [t0, t0 - h])
        F1, a1, toe1 = self.stance_foot_pose(side, i + 1, [t1, t1 + h])
        y0 = yaw_of(F0[0])
        y1 = y0 + wrap(yaw_of(F1[0]) - y0)
        pd0, pd1 = foot_pitch(F0), foot_pitch(F1)
        s = np.linspace(0.0, 1.0, 81)
        v0 = (a0[0] - a0[1]) / h * D
        v1 = (a1[1] - a1[0]) / h * D
        if step.kind == "side":
            # holds without horizontal motion after a flat lift-off and before a flat landing;
            # a walking push-off keeps its toe-off velocity, a heel landing its approach
            h0 = p["side_hold"] if step.lift_style == "flat" else 0.0
            h1 = p["side_hold"] if step.land_style == "flat" else 0.0
            span = 1.0 - h0 - h1
            w = np.clip((s - h0) / span, 0.0, 1.0)
            if h0 > 0.0 and h1 > 0.0:
                w = smoothstep(w)
            v0 = np.zeros(3) if h0 > 0.0 else v0 * span
            v1 = np.zeros(3) if h1 > 0.0 else v1 * span
            ank = hermite(w, a0[0], v0, a1[0], v1)
            yaw = y0 + (y1 - y0) * smootherstep(w)
            clr = step.lift_h * smoothstep(s / 0.25) * smoothstep((1.0 - s) / 0.25)
            # pitch: the toe-off pitch is released over the first half of the swing (keeping
            # its rate at lift-off), the foot is level in mid-swing, and the landing pitch is
            # taken over the last 45 %
            a_s = np.clip(s / 0.5, 0.0, 1.0)
            b_s = np.clip((s - 0.55) / 0.45, 0.0, 1.0)
            pit = (hermite(a_s, pd0[0], (pd0[0] - pd0[1]) / h * D * 0.5, 0.0, 0.0)
                   + hermite(b_s, 0.0, 0.0, pd1[0], 0.0))
        else:
            ank = hermite(s, a0[0], v0, a1[0], v1)
            yaw = y0 + (y1 - y0) * smootherstep(s)
            lift_h = p["turn_lift"] if step.lift_h is None else step.lift_h
            clr = lift_h * bump(s, 2.0, 2.0)
            pit = hermite(s, pd0[0], (pd0[0] - pd0[1]) / h * D, pd1[0], (pd1[1] - pd1[0]) / h * D)
        F = ry(yaw) @ rx(pit)
        pts = sole_points(side) - J[leg.ankle]
        world = ank[:, None, :] + np.einsum("nij,kj->nki", F, pts)
        minh = world[:, :, 1].min(1) - FLOOR
        lift = np.maximum(clr - minh, 0.0)
        lift = np.maximum(gaussian_filter1d(lift, 3.0, mode="nearest"), lift)
        lift *= smoothstep(s / 0.06) * smoothstep((1.0 - s) / 0.06)
        ank = ank.copy()
        ank[:, 1] += lift
        ank = self._clear_other_foot(side, t0, D, s, F, ank)
        toe = toe0[0] * (1.0 - smoothstep(s / 0.4)) + toe1[0] * smoothstep((s - 0.6) / 0.4)
        out = (t0, D, s, yaw, pit, ank, toe)
        self._swing_cache[key] = out
        return out

    def _clear_other_foot(self, side, t0, D, s, F, ank, gap=0.04):
        """Push the path of a small step sideways, away from the planted foot, wherever the two
        sole outlines would come closer than gap (horizontally)."""
        po = self._other_foot_outline(side, t0 + 0.5 * D)
        if po is None:
            return ank
        pts = foot_outline(side) - J[self.legs[side].ankle]
        env = bump(s, 2.0, 2.0)
        for _ in range(3):
            pw = (ank[:, None, :] + np.einsum("nij,kj->nki", F, pts))[:, :, [0, 2]]
            d = np.linalg.norm(pw[:, :, None, :] - po[None, None, :, :], axis=-1).min(axis=(1, 2))
            need = gaussian_filter1d(np.maximum(gap - d, 0.0), 3.0, mode="nearest") * env
            if need.max() < 0.002:
                break
            away = pw.mean(1) - po.mean(0)
            away /= np.linalg.norm(away, axis=-1, keepdims=True)
            ank = ank.copy()
            ank[:, 0] += 1.3 * need * away[:, 0]
            ank[:, 2] += 1.3 * need * away[:, 1]
        return ank

    def shuffle_foot(self, side, i, t):
        t0, D, s, yaw, pit, ank, toe = self.shuffle_path(side, i)
        u = np.clip((np.asarray(t, dtype=float) - t0) / D, 0.0, 1.0)
        F = ry(np.interp(u, s, yaw)) @ rx(np.interp(u, s, pit))
        A = np.stack([np.interp(u, s, ank[:, k]) for k in range(3)], -1)
        return F, A, np.interp(u, s, toe)

    # ================================================================== whole clip
    def pose_rotations(self, t):
        """Pelvis position (n, 3) and local rotations R (n, 22, 3, 3) at times t."""
        t = np.asarray(t, dtype=float)
        n = len(t)
        P0, W0 = self.pelvis(t)
        R = np.tile(np.eye(3), (n, NJ, 1, 1))
        R[:, 0] = W0
        self.diag = {}
        for side, leg in self.legs.items():
            idx, contact = self.lookup(side, t)
            i = np.nonzero(contact)[0]
            if len(i):
                Rh, th, Ra, toe, q = self.stance_pose(side, idx[i], t[i])
                R[i, leg.hip], R[i, leg.knee], R[i, leg.ankle], R[i, leg.toe] = Rh, rx(th), Ra, rx(toe)
                self.diag[side + "_q"] = q
            sw = np.nonzero(~contact)[0]
            for k in np.unique(idx[sw]):
                i = sw[idx[sw] == k]
                kind = self.plan.plants[side][k + 1].step.kind
                if kind == "walk":
                    c = self.swing_channels(side, int(k), t[i])
                    R[i, leg.hip] = from_euler_xzy(c[:, 0:3])
                    R[i, leg.knee] = rx(c[:, 3])
                    R[i, leg.ankle] = from_euler_xzy(c[:, 4:7])
                    R[i, leg.toe] = rx(c[:, 7])
                else:
                    F, A, toe = self.shuffle_foot(side, int(k), t[i])
                    Rh, th, Ra, _ = leg.ik(P0[i], W0[i], F, A)
                    R[i, leg.hip], R[i, leg.knee], R[i, leg.ankle], R[i, leg.toe] = Rh, rx(th), Ra, rx(toe)
        for j, M in upper_body(self, t, W0).items():
            R[:, j] = M
        return P0, R

    def generate(self, n_frames, fps):
        t = np.arange(n_frames) / float(fps)
        P0, R = self.pose_rotations(t)
        return dict(fps=int(fps), transl=P0 - J[0], global_orient=to_rotvec(R[:, 0]),
                    body_pose=to_rotvec(R[:, 1:]))


def calibrate(params=None):
    """Pelvis offset c_walk and static pelvic obliquity roll0 for steady straight walking.

    The SMPL-X skeleton is slightly asymmetric, and where the pelvis sits relative to the feet
    follows from the balance model; with the wrong values the required pelvis height would
    jump when the leading leg changes.  Newton iteration on (c_walk, roll0) makes both
    hand-overs continuous."""
    from .path import WalkLine
    from .plan import PlanBuilder
    q = make_params(params)
    q.update(var=0.0, c_walk=0.0, roll0=0.0)
    line = WalkLine([0.0, 0.0], 0.0, [{"type": "straight", "length": 40.0}])
    b = PlanBuilder(q)
    b.stand([0.0, 0.0], 0.0)
    b.wait(0.5)
    b.walk(line, stop=False, t_end=8.0, first="R")
    plan = b.finish(8.0)
    body = Body(plan, (0.0, 8.0), solve_height=False)
    st = plan.steps
    j = next(k for k, s in enumerate(st) if s.t_hs > 5.0)
    A, B, C = st[j - 1], st[j], st[j + 1]      # three consecutive touch-downs
    eps = 1e-6

    def yr(step, t):
        idx = step.plant_index
        u, lam = body.u_lam(step.side, [idx], [t])
        return body.y_required(step.side, [idx], [t], u, lam)[0]

    def mismatch(x):
        q["c_walk"], q["roll0"] = float(x[0]), float(x[1])
        return np.array([yr(A, B.t_hs - eps) - yr(B, B.t_hs), yr(B, C.t_hs - eps) - yr(C, C.t_hs)])

    x = np.array([0.0, 0.0])
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
