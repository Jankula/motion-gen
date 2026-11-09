"""Footstep plans: where and when each foot is on the floor.

A plan is built from *behaviours* that append footsteps one after the other:

  stand(center, heading)   both feet on the floor, side by side
  wait(dt)                 keep standing
  walk(line, stop=...)     start from standing, walk along a WalkLine, optionally stop at its end
  turn(angle)              turn on the spot with small stepping turns

A footstep is one step of one foot: lift-off time, touch-down time and the place, direction
and pitch of the foot when it lands.  From the footsteps the plan derives, for every foot,
its sequence of *plants* (periods on the floor).  Each plant has a stance clock u(t) (see
gait.py) that drives the foot rockers and the target knee angle, and a loading-response
strength lam(t).  The plan also provides

  * a heading program: which way the pelvis faces (along the walking line while walking,
    a smooth progression while turning on the spot),
  * envelopes that scale the gait oscillations: the gait phase (left touch-down at whole
    numbers, right at halves), the step size g(t) (1 = a normal walking step, 0 = standing)
    and the stepping envelope e(t) (1 while stepping, 0 while standing).

The positions of the body follow from the plan by the balance model (balance.py).
"""
import math
import os

import numpy as np
from scipy.interpolate import PchipInterpolator

from .gait import COP_FWD, GRAVITY, U_ST, bend_speed_factor
from .path import hdir, lnorm
from .rotations import DEG, smoothstep
from .skeleton import PELVIS_HEIGHT

T_INF = 1.0e3
_DEBUG = bool(os.environ.get("LOCO_DEBUG"))   # print how steps are distributed between corners
SIDES = ("L", "R")
SIGN = {"L": 1.0, "R": -1.0}
OTHER = {"L": "R", "R": "L"}
D_ST = float(COP_FWD(U_ST))   # heel-circle centre behind the centre of pressure of a standing foot


class Footstep:
    """One step: a foot leaves the floor at t_lo and is put down at t_hs (heel-circle centre of
    the flat foot above floor point xz, heading yaw, toes up by alpha at touch-down).
    kind 'walk' swings the leg like a walking step; 'shuffle' lifts and places the foot
    (turning on the spot).  lam scales the loading response after touch-down, size is the
    step length relative to a normal walking step."""

    def __init__(self, side, t_lo, t_hs, xz, yaw, alpha=0.0, lam=0.0, kind="walk", size=1.0):
        self.side = side
        self.t_lo = float(t_lo)
        self.t_hs = float(t_hs)
        self.xz = np.asarray(xz, dtype=float)
        self.yaw = float(yaw)
        self.alpha = float(alpha)
        self.lam = float(lam)
        self.kind = kind
        self.size = float(size)


class Plant:
    """A period [t_on, t_off] during which one foot is on the floor."""

    def __init__(self, side, t_on, xz, yaw, alpha=0.0, lam=0.0, step=None):
        self.side = side
        self.t_on = float(t_on)
        self.t_off = T_INF
        self.xz = np.asarray(xz, dtype=float)
        self.yaw = float(yaw)
        self.alpha = float(alpha)
        self.lam = float(lam)
        self.step = step          # the footstep that put the foot here (None: initial stance)
        self.lift = None          # the footstep that lifts it again (None: stays)
        self.push = 0.2
        self.knots = None         # (times, u, lam)
        self.ramp_up = 0.0        # load builds up over this time after touch-down
        self.ramp_dn = 0.0        # and is shed over this time before lift-off

    @property
    def landing(self):
        return self.step is not None

    @property
    def lifts(self):
        return self.lift is not None

    def u(self, t):
        return np.interp(t, self.knots[0], self.knots[1])

    def lam_at(self, t):
        return np.interp(t, self.knots[0], self.knots[2])


# ====================================================================== builder
class PlanBuilder:
    def __init__(self, p, t0=0.0):
        self.p = p
        self.steps = []
        self.initial = {}
        self.feet = {}
        self.t = float(t0)
        self.heading_prog = []

    # ------------------------------------------------------------------ state
    def foot_cop(self, side):
        xz, yaw = self.feet[side]
        return xz + D_ST * hdir(yaw)

    def center(self):
        """Centre of pressure of the current standing feet."""
        return 0.5 * (self.foot_cop("L") + self.foot_cop("R"))

    def heading(self):
        return 0.5 * (self.feet["L"][1] + self.feet["R"][1])

    def _add(self, step):
        self.steps.append(step)
        self.feet[step.side] = (step.xz, step.yaw)

    # ------------------------------------------------------------------ behaviours
    def stand(self, center, heading, half_width=None, toe_out=None):
        """Start the plan standing with the centre of pressure at center, facing heading."""
        p = self.p
        w = p["stand_half_width"] if half_width is None else half_width
        to = p["stand_toe_out"] if toe_out is None else toe_out
        center = np.asarray(center, dtype=float)
        for side in SIDES:
            s = SIGN[side]
            yaw = heading + s * to
            xz = center + s * w * lnorm(heading) - D_ST * hdir(yaw)
            self.initial[side] = (xz, yaw)
            self.feet[side] = (xz, yaw)
        self.heading_prog.append((-T_INF, "const", float(heading)))
        return self

    def wait(self, dt):
        self.t += float(dt)
        return self

    def walk(self, line, body_line=None, stop=True, t_end=None, first=None):
        """Start walking from standing along the line.  With stop=True the walker comes to a
        standstill with the centre of mass at the end of the marked path (line.s_end), feet side
        by side; otherwise walking continues until t_end.

        line is the *feet line*: footprints are put half a step width to either side of it
        (shifted outwards in bends, to lean into them) and point along it.  body_line (smoother)
        only gives the pelvis heading; the body's path itself follows from the balance model.

        Step lengths: the normal step (stride / 2), shortened in bends (speed factor of the
        curvature ahead, cad_share of the slow-down by cadence), ramped up over the first steps
        (start_len) and down over the last ones (stop_len).  Corners (sharp bends) are anchors:
        the outer foot is put down at the apex, so that the body turns over it while the inner
        foot steps into the new direction (a 'step turn', the commoner and more stable way to
        turn a corner).  Between anchors the step lengths are scaled by one factor so that the
        feet arrive exactly at the next anchor and at the end of the path."""
        p = self.p
        body_line = line if body_line is None else body_line
        L0, P0 = p["stride"] / 2.0, p["T"] / 2.0
        c = self.center()
        s_c = float(line.project(c[None], [_nearest_s(line, c)])[0])
        s_f0 = s_c - D_ST
        fields = _line_fields(line, p)
        f_str, f_cad, shift = fields["f_str"], fields["f_cad"], fields["shift"]
        start_len, stop_len = p["start_len"], p["stop_len"]
        s_hi = line.s_end if stop else s_c + 1.4 * (t_end - self.t) + 2.0
        corners = _corners(line, p, s_c, s_hi)
        targets = [(s - D_ST, side) for s, side in corners]
        # near a corner the body is allowed to round it: no outward shift of the feet there
        for s_ap, _ in corners:
            shift = shift * (1.0 - smoothstep((1.0 - np.abs(line.s - s_ap)) / 0.5))
        if stop:
            targets.append((line.s_end - D_ST, None))

        apex = set()

        def mult(k, n_total):
            m = start_len[k] if k < len(start_len) else 1.0
            if n_total is not None and n_total - 1 - k < len(stop_len):
                m = min(m, stop_len[n_total - 1 - k])
            if k - 1 in apex:          # the inner foot's step into the new direction is short
                m = min(m, p["after_apex_len"])
            return m

        def seg_lengths(n, lam, s_from, k0, n_total):
            s, out = s_from, []
            for i in range(n):
                l0 = lam * L0 * mult(k0 + i, n_total)
                l = l0 * float(np.interp(s + 0.5 * l0, line.s, f_str))
                s += l
                out.append(l)
            return out

        # ---- distribute the steps between the anchors
        ls = []
        side0 = first
        s_from, k0 = s_f0, 0
        for j, (s_to, need) in enumerate(targets):
            final = stop and j == len(targets) - 1
            D = s_to - s_from
            if D < 0.25 * L0:
                continue
            n_est = max(1, int(round(D / L0)))
            cands = []
            for n in range(max(1, n_est - 3), n_est + 4):
                lam = 1.0
                for _ in range(8):
                    tot = sum(seg_lengths(n, lam, s_from, k0, k0 + n if final else None))
                    lam *= D / max(tot, 1e-6)
                lands = None if side0 is None else (side0 if (k0 + n - 1) % 2 == 0 else OTHER[side0])
                ok = need is None or lands is None or lands == need
                # shorter steps are a smaller departure from normal walking than longer ones
                cost = abs(math.log(lam)) * (1.6 if lam > 1.0 else 1.0)
                cands.append((not ok or not 0.65 < lam < 1.25, cost, n, lam))
            bad, _, n, lam = min(cands)
            if _DEBUG:
                print("segment %d: D %.2f need %s -> n %d lam %.2f bad %s; candidates %s"
                      % (j, D, need, n, lam, bad, [(c[2], round(c[3], 2), c[0]) for c in cands]))
            if side0 is None and need is not None:
                side0 = need if (k0 + n - 1) % 2 == 0 else OTHER[need]
            ls += seg_lengths(n, lam, s_from, k0, k0 + n if final else None)
            if need is not None and not bad:
                apex.add(k0 + n - 1)
            s_from, k0 = s_to, k0 + n
        if side0 is None:
            side0 = "R"
        n_all = len(ls) if stop else None

        # ---- the steps
        t_walk0 = self.t
        side = side0
        s_prev = s_f0
        t_hs_prev = None
        k = 0
        prog_t, prog_s = [self.t], [s_c]
        while True:
            if k < len(ls):
                l = float(ls[k])
            elif stop:
                break
            else:
                l0 = L0 * mult(k, None)
                l = l0 * float(np.interp(s_prev + 0.5 * l0, line.s, f_str))
            s_k = s_prev + l
            m_t = p["start_time"][k] if k < len(p["start_time"]) else 1.0
            if stop and n_all - 1 - k < len(p["stop_time"]):
                m_t = max(m_t, p["stop_time"][n_all - 1 - k])
            fc = float(np.interp(s_prev + 0.5 * l, line.s, f_cad))
            wob = _wobble(0.0 if t_hs_prev is None else t_hs_prev - t_walk0, p["var"])
            P = P0 * m_t / fc / wob
            if k == 0:
                t_lo = self.t + p["unload"]
                t_hs = t_lo + p["first_swing"]
            else:
                t_lo = t_hs_prev + p["ds_frac"] * P
                t_hs = t_hs_prev + P
            sg = SIGN[side]
            ph_s = 0.0 if side == "L" else 1.9
            dx = p["var"] * 0.004 * math.sin(2.1 * k + ph_s)
            dyaw = p["var"] * 1.0 * DEG * math.sin(1.3 * k + 0.7 + ph_s)
            if stop and k == n_all - 1:          # braking step: feet end side by side, centred
                lat = sg * 0.5 * (p["heel_x"] + p["stand_half_width"])
                yaw = float(line.heading(line.s_end)) + sg * p["toe_out"]
            else:
                lat = sg * (p["heel_x"] + dx) + float(np.interp(s_k, line.s, shift))
                if k in apex:                   # the outer foot is planted outside the corner
                    lat += sg * p["apex_out"]
                yaw = float(line.heading(s_k + p["foot_yaw_lead"])) + sg * (p["toe_out"] + dyaw)
            xz = line.pos(s_k) + lat * line.normal(s_k)
            size = l / L0
            alpha = p["alpha_hs"] * float(np.clip(0.4 + 0.6 * size, 0.4, 1.0))
            self._add(Footstep(side, t_lo, t_hs, xz, yaw, alpha, float(np.clip(size, 0, 1)), "walk", size))
            prog_t.append(t_hs)
            prog_s.append(s_k - 0.20)
            side, s_prev, t_hs_prev = OTHER[side], s_k, t_hs
            k += 1
            if not stop and t_hs > t_end:
                break
        if stop:
            # closing step: the trailing foot is brought up beside the other one
            sg = SIGN[side]
            lat = sg * 0.5 * (p["heel_x"] + p["stand_half_width"])
            yaw = float(line.heading(line.s_end)) + sg * p["toe_out"]
            xz = line.pos(s_prev) + lat * line.normal(s_prev)
            t_lo = t_hs_prev + p["close_ds"]
            t_hs = t_lo + p["close_swing"]
            self._add(Footstep(side, t_lo, t_hs, xz, yaw, p["close_alpha"], 0.2, "walk", 0.0))
            prog_t.append(t_hs + 1.0)
            prog_s.append(line.s_end)
        # progress guess on the body line (for projecting the centre of mass onto it)
        prog_b = [_nearest_s(body_line, line.pos(s)) for s in prog_s]
        self.heading_prog.append((t_walk0, "line", (body_line, np.array(prog_t), np.array(prog_b))))
        self.t = self.steps[-1].t_hs
        return self

    def turn(self, angle):
        """Turn on the spot by angle (radians, positive = to the left) with stepping turns.

        The inner foot (on the side of the turn) steps first; each foot turns by at most
        turn_max_step per step.  A stepping foot is put down beside the planted one, across
        the mean of the two feet's headings and a little wider apart than when standing, so
        that the heels stay clear of each other while the toes open into a V; the centre of
        the feet is pulled halfway back to where it started at every step, and the last step
        puts the feet side by side, centred exactly there."""
        p = self.p
        h0 = self.heading()
        c = self.center()
        n_pf = max(1, int(math.ceil(abs(angle) / p["turn_max_step"] - 1e-9)))
        inner = "L" if angle > 0 else "R"
        order = [inner, OTHER[inner]] * n_pf
        cur = {s: h0 for s in SIDES}
        cop = {s: self.foot_cop(s) for s in SIDES}
        heel_of = {s: self.feet[s][0] for s in SIDES}
        t_prev = None
        kt, kh = [], []
        for j, side in enumerate(order):
            h_new = h0 + angle * (j // 2 + 1) / n_pf
            other = OTHER[side]
            last = j == len(order) - 1
            to = p["stand_toe_out"] if last else 0.3 * p["stand_toe_out"]
            yaw = h_new + SIGN[side] * to
            if last:                         # final stance: centred on where the turn began
                q = 2.0 * c - cop[other]
            else:
                # heels side by side across the mean heading (toes may open into a V)
                w = p["stand_half_width"] if j == len(order) - 2 else p["turn_half_width"]
                hm = 0.5 * (h_new + cur[other])
                heel = heel_of[other] + SIGN[side] * 2.0 * w * lnorm(hm)
                q = heel + D_ST * hdir(yaw)
                q = q + 0.5 * (c - 0.5 * (q + cop[other]))
                if j == len(order) - 2:
                    # as close to the final standing place as the planted heel allows
                    q_fin = c + SIGN[side] * p["stand_half_width"] * lnorm(h0 + angle)
                    for beta in (0.0, 0.25, 0.5, 0.75, 1.0):
                        qb = q_fin + beta * (q - q_fin)
                        if np.linalg.norm(qb - D_ST * hdir(yaw) - heel_of[other]) >= 0.14:
                            break
                    q = qb
            cop[side] = q
            xz = q - D_ST * hdir(yaw)
            heel_of[side] = xz
            t_lo = (self.t + p["unload"]) if j == 0 else t_prev + p["turn_ds"]
            t_hs = t_lo + p["turn_swing"]
            # pelvis heading: mostly turns while a foot is in the air (most of a step's turn
            # between its lift-off and touch-down, a little during the double support)
            mb = 0.5 * (cur["L"] + cur["R"])
            cur[side] = h_new
            ma = 0.5 * (cur["L"] + cur["R"])
            if j == 0:
                kt += [t_lo - 0.45]
                kh += [h0]
            kt += [t_lo, t_hs]
            kh += [mb + 0.12 * (ma - mb), ma - 0.12 * (ma - mb)]
            self._add(Footstep(side, t_lo, t_hs, xz, yaw, p["turn_alpha"], 0.25, "shuffle", 0.0))
            t_prev = t_hs
        kh[-1] = h0 + angle
        kt.append(t_prev + 0.35)
        kh.append(h0 + angle)
        self.heading_prog.append((kt[0], "interp", PchipInterpolator(kt, kh)))
        self.t = t_prev
        return self

    def finish(self, duration):
        return Plan(self.p, self.initial, self.steps, self.heading_prog, duration)


def _nearest_s(line, xz):
    i = int(np.argmin(np.sum((line.xz - np.asarray(xz)) ** 2, -1)))
    return float(line.s[i])


def _wobble(t, var):
    """Slow +-1.5 % cadence drift (no two steps are exactly alike)."""
    return 1.0 + var * (0.012 * math.sin(2 * math.pi * t / 4.1 + 0.7)
                        + 0.007 * math.sin(2 * math.pi * t / 2.3 + 2.1))


def _corners(line, p, s_lo, s_hi):
    """Corners of the line between s_lo and s_hi: [(s of the apex, outer foot)].
    A corner is a peak of the smoothed curvature above sharp_turn rad/m where the line turns by
    at least corner_min within half a metre, and that is most of its turn within 1.5 m (which
    tells a corner from a long, evenly curved bend)."""
    ks = line.smoothed(line.k, p["slow_sigma"])
    a = np.abs(ks)
    ds = line.s[1] - line.s[0]

    def turn_within(i, r):
        m = (line.s > line.s[i] - r) & (line.s < line.s[i] + r)
        return float(np.sum(line.k[m]) * ds)

    out = []
    i_lo = np.searchsorted(line.s, s_lo + 0.3)
    i_hi = np.searchsorted(line.s, s_hi - 0.2)
    for i in range(max(i_lo, 1), min(i_hi, len(a) - 1)):
        if a[i] >= p["sharp_turn"] and a[i] >= a[i - 1] and a[i] > a[i + 1]:
            near, wide = turn_within(i, 0.5), turn_within(i, 1.5)
            if (abs(near) >= p["corner_min"] and abs(near) >= 0.6 * abs(wide)
                    and (not out or line.s[i] - out[-1][0] > 0.8)):
                out.append((float(line.s[i]), "L" if near < 0 else "R"))
    return out


def _line_fields(line, p):
    """Speed factors and the outward foot shift along the line (see NOTES.md, bends)."""
    k_s = line.smoothed(line.k, p["slow_sigma"])
    k_eff = np.maximum(np.interp(line.s + p["slow_lead"], line.s, np.abs(k_s)),
                       np.interp(line.s - p["slow_lag"], line.s, np.abs(k_s)))
    f = bend_speed_factor(k_eff, p)
    v = p["stride"] / p["T"] * f
    lean = np.clip(p["lean_gain"] * np.arctan(v ** 2 * k_s / GRAVITY), -p["lean_max"], p["lean_max"])
    lean = np.interp(line.s + p["shift_lead"], line.s, lean)
    shift = np.clip(-PELVIS_HEIGHT * np.tan(lean), -p["shift_max"], p["shift_max"])
    return dict(f_str=f ** (1.0 - p["cad_share"]), f_cad=f ** p["cad_share"], shift=shift, v=v)


# ====================================================================== plan
class Plan:
    def __init__(self, p, initial, steps, heading_prog, duration):
        self.p = p
        self.duration = float(duration)
        self.steps = sorted(steps, key=lambda s: s.t_hs)
        self.heading_prog = sorted(heading_prog, key=lambda e: e[0])
        self.plants = {}
        for side in SIDES:
            xz, yaw = initial[side]
            lst = [Plant(side, -T_INF, xz, yaw)]
            for st in (s for s in self.steps if s.side == side):
                prev = lst[-1]
                prev.t_off = st.t_lo
                prev.lift = st
                lst.append(Plant(side, st.t_hs, st.xz, st.yaw, st.alpha, st.lam, step=st))
                st.plant_index = len(lst) - 1
            self.plants[side] = lst
        self.swings = {s: [(a.t_off, b.t_on) for a, b in zip(self.plants[s][:-1], self.plants[s][1:])]
                       for s in SIDES}
        for side in SIDES:
            other = self.swings[OTHER[side]]
            for P in self.plants[side]:
                P.push = self._push(P)
                P.knots = self._knots(P, other)
                P.ramp_up, P.ramp_dn = self._ramps(P, other)
        if self.steps:
            self.t_first = min(s.t_lo for s in self.steps)
            self.t_last = max(s.t_hs for s in self.steps)
        else:
            self.t_first = self.t_last = 0.0
        self._envelopes()

    # ------------------------------------------------------------------ per plant
    def _push(self, P):
        st = P.lift
        if st is None:
            return 0.2
        if st.kind != "walk":
            return 0.25
        travel = float(np.linalg.norm(st.xz - P.xz))
        return float(np.clip(0.2 + 0.8 * travel / self.p["stride"], 0.2, 1.0))

    def _knots(self, P, other_swings):
        """Stance clock u(t) and loading-response strength lam(t) of a plant as knots.

        Walking:  touch-down 0, other foot off 0.1, other foot down 0.5, toe off 0.6.
        Standing: u rests at U_ST; before a lift-off from standing the foot is unloaded and
        u runs from U_ST to 0.6 over p['unload'] seconds."""
        p = self.p
        T, U, L = [], [], []

        def add(t, u, lam):
            if T and t < T[-1] + 1e-3:
                t = T[-1] + 1e-3
            T.append(float(t))
            U.append(float(u))
            L.append(float(lam))

        later = [(a, b) for (a, b) in other_swings if P.t_on - 1e-9 <= a < P.t_off]
        t_unload = P.t_off - p["unload"] if P.lifts else T_INF
        if P.landing:
            add(P.t_on, 0.0, P.lam)
            if later and later[0][0] - P.t_on < 0.35:
                add(later[0][0], 0.1, P.lam)
            else:
                add(P.t_on + 0.15, 0.1, P.lam)
                if P.t_on + 0.45 < t_unload - 0.05:
                    add(P.t_on + 0.45, U_ST, 0.0)
        else:
            add(P.t_on, U_ST, 0.0)
        for (a, b) in later:
            if b > P.t_off + 1e-9:
                break
            walking_like = P.lifts and (P.t_off - b) < 0.35
            if a > T[-1] + 1e-6:
                add(a, max(U[-1], 0.1), L[-1])
            if walking_like:
                add(b, 0.5, L[-1])
            else:
                add(b, max(U[-1], U_ST), 0.0)
        if P.lifts:
            if abs(U[-1] - 0.5) < 1e-9 and P.t_off - T[-1] < 0.35:
                add(P.t_off, 0.6, L[-1])
            else:
                add(max(t_unload, T[-1] + 0.02), max(U[-1], U_ST), 0.0)
                add(P.t_off, 0.6, 0.0)
        return np.array(T), np.array(U), np.array(L)

    def _ramps(self, P, other_swings):
        """Times over which the load on a plant builds up after touch-down and is shed before
        lift-off: the double support when walking, a slower shift of weight otherwise."""
        p = self.p
        up = dn = 0.0
        if P.landing:
            nxt = [a for (a, b) in other_swings if a >= P.t_on - 1e-9]
            up = (nxt[0] - P.t_on) if nxt and nxt[0] - P.t_on < 0.35 else 0.25
        if P.lifts:
            prv = [b for (a, b) in other_swings if b <= P.t_off + 1e-9]
            dn = (P.t_off - prv[-1]) if prv and P.t_off - prv[-1] < 0.35 else p["unload"]
        return max(up, 0.02), max(dn, 0.02)

    # ------------------------------------------------------------------ envelopes
    def _envelopes(self):
        """Gait phase, step-size and stepping envelopes as knots."""
        st = self.steps
        bouts = []
        for s in st:
            if bouts and s.t_lo - bouts[-1][-1].t_hs < 0.30:
                bouts[-1].append(s)
            else:
                bouts.append([s])
        ph_t, ph_v = [], []
        g_t, g_v = [], []
        e_t, e_v = [], []
        ph = 0.0
        for bout in bouts:
            g_t.append(bout[0].t_lo - 0.25)
            g_v.append(0.0)
            for i, s in enumerate(bout):
                frac = 0.0 if s.side == "L" else 0.5
                nxt = math.floor(ph - frac) + 1.0 + frac
                if i == 0:
                    while nxt - 0.4 < ph:
                        nxt += 1.0
                    ph_t.append(s.t_lo)
                    ph_v.append(nxt - 0.4)
                ph_t.append(s.t_hs)
                ph_v.append(nxt)
                ph = nxt
                g_t.append(0.5 * (s.t_lo + s.t_hs))
                g_v.append(s.size)
            g_t.append(bout[-1].t_hs + 0.30)
            g_v.append(0.0)
        spans = []
        for bout in bouts:
            a, b = bout[0].t_lo, bout[-1].t_hs
            if spans and a - spans[-1][1] < 0.55:
                spans[-1][1] = b
            else:
                spans.append([a, b])
        for a, b in spans:
            e_t += [a - 0.30, a, b, b + 0.25]
            e_v += [0.0, 1.0, 1.0, 0.0]
        self.bouts = bouts
        if not st:
            ph_t, ph_v = [0.0, 1.0], [0.0, 0.0]
            g_t, g_v = [0.0, 1.0], [0.0, 0.0]
            e_t, e_v = [0.0, 1.0], [0.0, 0.0]
        self._ph = (np.array(ph_t), np.array(ph_v))
        self._g = _monotone_knots(g_t, g_v)
        self._e = _monotone_knots(e_t, e_v)

    def phase(self, t):
        return np.interp(t, *self._ph)

    def size_env(self, t):
        x, y = self._g
        return np.clip(PchipInterpolator(x, y, extrapolate=False)(np.clip(t, x[0], x[-1])), 0.0, 1.5)

    def step_env(self, t):
        x, y = self._e
        return np.clip(PchipInterpolator(x, y, extrapolate=False)(np.clip(t, x[0], x[-1])), 0.0, 1.0)

    # ------------------------------------------------------------------ heading
    def heading(self, t, com):
        """Pelvis heading program at times t, given the centre of mass com (n, 2)."""
        t = np.asarray(t, dtype=float)
        out = np.zeros(len(t))
        prog = self.heading_prog
        for j, (t0, kind, pay) in enumerate(prog):
            t1 = prog[j + 1][0] if j + 1 < len(prog) else np.inf
            m = (t >= t0) & (t < t1)
            if not m.any():
                continue
            if kind == "const":
                out[m] = pay
            elif kind == "line":
                line, tk, sk = pay
                s0 = np.interp(t[m], tk, sk)
                s = line.project(com[m], s0)
                out[m] = line.heading(s)
            elif kind == "interp":
                out[m] = pay(np.clip(t[m], pay.x[0], pay.x[-1]))
        return out


def _monotone_knots(t, v):
    """Sort knots by time and drop near-duplicates (for PCHIP)."""
    t = np.asarray(t, dtype=float)
    v = np.asarray(v, dtype=float)
    o = np.argsort(t, kind="stable")
    t, v = t[o], v[o]
    keep = np.concatenate([[True], np.diff(t) > 1e-3])
    return t[keep], v[keep]
