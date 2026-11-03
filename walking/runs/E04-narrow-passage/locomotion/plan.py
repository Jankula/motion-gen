"""Footstep plans: where and when each foot is on the floor.

A plan is built from *behaviours* that append footsteps one after the other:

  stand(center, heading)   both feet on the floor, side by side
  wait(dt)                 keep standing
  walk(line, stop=..., passages=...)
                           start from standing, walk along a WalkLine, optionally stop at its
                           end; on the way, squeeze sideways through narrow gaps (passages)
  turn(angle)              turn on the spot with small stepping turns

A footstep is one step of one foot: lift-off time, touch-down time and the place, direction
and pitch of the foot when it lands.  From the footsteps the plan derives, for every foot,
its sequence of *plants* (periods on the floor).  Each plant has a stance clock u(t) (see
gait.py) that drives the foot rockers and the target knee angle, and a loading-response
strength lam(t).  The plan also provides

  * a heading program: which way the pelvis faces (along the walking line while walking,
    a smooth progression while turning on the spot), plus heading offsets (the body turned
    sideways in a passage),
  * envelopes that scale the gait oscillations: the gait phase (left touch-down at whole
    numbers, right at halves), the step size g(t) (1 = a normal walking step, 0 = standing)
    and the stepping envelope e(t) (1 while stepping, 0 while standing), and the sideways
    envelope q(t) (1 while side-stepping through a passage).

Footstep kinds (how the foot travels through the air):
  walk     joint-space walking swing (heel strike, toe off)
  shuffle  small step on the spot: the foot follows a lifted path in space (turning)
  side     side step: like shuffle, lower and longer, the foot lifted and put down nearly flat

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
_DEBUG = bool(os.environ.get("LOCO_DEBUG"))   # print how steps are distributed between anchors
SIDES = ("L", "R")
SIGN = {"L": 1.0, "R": -1.0}
OTHER = {"L": "R", "R": "L"}
D_ST = float(COP_FWD(U_ST))   # heel-circle centre behind the centre of pressure of a standing foot


class Footstep:
    """One step: a foot leaves the floor at t_lo and is put down at t_hs (heel-circle centre of
    the flat foot above floor point xz, heading yaw, toes up by alpha at touch-down).
    kind: see the module docstring.  lam scales the loading response after touch-down, size is
    the step length relative to a normal walking step.
    lift_style 'walk': the foot leaves the floor with a heel rise and push-off over the toes;
    'flat': it is lifted nearly flat.  land_style 'heel': heel first; 'flat': whole foot.
    lift_h: clearance of the sole in mid-swing for foot-path swings (shuffle, side)."""

    def __init__(self, side, t_lo, t_hs, xz, yaw, alpha=0.0, lam=0.0, kind="walk", size=1.0,
                 lift_style=None, land_style=None, lift_h=None):
        self.side = side
        self.t_lo = float(t_lo)
        self.t_hs = float(t_hs)
        self.xz = np.asarray(xz, dtype=float)
        self.yaw = float(yaw)
        self.alpha = float(alpha)
        self.lam = float(lam)
        self.kind = kind
        self.size = float(size)
        self.lift_style = lift_style or ("flat" if kind == "side" else "walk")
        self.land_style = land_style or ("flat" if kind == "side" else "heel")
        self.lift_h = lift_h


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


class Passage:
    """A gap on the walking line too narrow to walk through normally.

    s_a, s_b  arc lengths on the feet line where the narrow part begins and ends [m]
    center    lateral offset of the middle of the free gap from the line (+ = left) [m]
    width     free width of the gap [m]
    turn      'L': the body turns towards the left of the line (sideways: faces it, the right
              foot leads), 'R': towards the right
    mode      'side': squeezed through sideways with side steps (very narrow gaps);
              'shoulder': walked through with the arms held still and the shoulders turned by
              beta (radians; 0 = arms still only)"""

    def __init__(self, s_a, s_b, center=0.0, width=0.0, turn="L", mode="side", beta=0.0):
        self.s_a = float(s_a)
        self.s_b = float(s_b)
        self.center = float(center)
        self.width = float(width)
        self.turn = turn
        self.mode = mode
        self.beta = float(beta)

    def __repr__(self):
        return ("Passage(%s, s %.2f..%.2f, centre %+.3f, width %.3f, turn %s, beta %.0f deg)"
                % (self.mode, self.s_a, self.s_b, self.center, self.width, self.turn,
                   math.degrees(self.beta)))


# ====================================================================== builder
class PlanBuilder:
    def __init__(self, p, t0=0.0):
        self.p = p
        self.steps = []
        self.initial = {}
        self.feet = {}
        self.t = float(t0)
        self.heading_prog = []
        self.offsets = []         # heading offset programs (PCHIP in time, zero at both ends)
        self.side_knots = []      # sideways envelopes (PCHIP in time, zero at both ends)
        self.thorax_offsets = []  # extra thorax rotation (shoulder turns), PCHIP in time
        self.arm_knots = []       # arm-swing suppression envelopes (0..1), PCHIP in time

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

    def walk(self, line, body_line=None, stop=True, t_end=None, first=None, passages=()):
        """Start walking from standing along the line.  With stop=True the walker comes to a
        standstill with the centre of mass at the end of the marked path (line.s_end), feet side
        by side; otherwise walking continues until t_end.  Narrow gaps on the way (passages)
        are squeezed through sideways (see _passage_layout).

        line is the *feet line*: footprints are put half a step width to either side of it
        (shifted outwards in bends, to lean into them) and point along it.  body_line (smoother)
        only gives the pelvis heading; the body's path itself follows from the balance model.

        The walk is split into stretches: from the start (standing) or from the exit of a
        passage, to the entry of the next passage, the stop or the end of the clip.  Step
        lengths: the normal step (stride / 2), shortened in bends (speed factor of the curvature
        ahead, cad_share of the slow-down by cadence), ramped up over the first steps of a
        stretch (start_len from standing, resume_len after a passage) and down over its last
        ones (stop_len before stopping, approach_len before a passage).  Corners (sharp bends)
        are anchors: the outer foot is put down at the apex, so that the body turns over it
        while the inner foot steps into the new direction (a 'step turn').  A passage entry is
        an anchor too: its leading foot lands at the entry point.  Between anchors the step
        lengths are scaled by one factor so that the feet arrive exactly at them."""
        p = self.p
        body_line = line if body_line is None else body_line
        L0, P0 = p["stride"] / 2.0, p["T"] / 2.0
        c = self.center()
        s_c = float(line.project(c[None], [_nearest_s(line, c)])[0])
        s_f0 = s_c - D_ST
        fields = _line_fields(line, p)
        f_str, f_cad, shift = fields["f_str"], fields["f_cad"], fields["shift"]
        s_hi = line.s_end if stop else s_c + 1.4 * (t_end - self.t) + 2.0
        passages = sorted((pa for pa in passages if s_c + 1.2 < pa.s_a < s_hi), key=lambda pa: pa.s_a)
        shoulder = [pa for pa in passages if pa.mode == "shoulder"]
        layouts = [_passage_layout(line, pa, p) for pa in passages if pa.mode == "side"]
        corners = [cn for cn in _corners(line, p, s_c, s_hi)
                   if not any(lay["s_lo"] - 1.0 < cn[0] < lay["s_hi"] + 1.0 for lay in layouts)]
        # near a corner the body is allowed to round it: no outward shift of the feet there
        for s_ap, _ in corners:
            shift = shift * (1.0 - smoothstep((1.0 - np.abs(line.s - s_ap)) / 0.5))
        for lay in layouts:     # and none around a passage
            shift = shift * smoothstep(np.maximum(lay["s_lo"] - 1.0 - line.s, line.s - lay["s_hi"] - 1.0))

        # ---- stretches between passages
        stretches = []
        s_from, start = s_f0, "stand"
        for lay in layouts:
            stretches.append(dict(s0=s_from, start=start, end="passage", lay=lay,
                                  s1=lay["s_entry"], need=lay["lead"]))
            s_from, start = lay["s_exit"], "resume"
        stretches.append(dict(s0=s_from, start=start, end="stop" if stop else "open", lay=None,
                              s1=line.s_end - D_ST if stop else None, need=None))

        # ---- distribute the steps of each stretch between its anchors
        side_first = first
        for st in stretches:
            if st["start"] == "resume":
                side_first = OTHER[st_prev["lay"]["lead"]]
            targets = []
            for s_ap, side in corners:
                s_t = s_ap - D_ST
                if s_t > st["s0"] + 0.3 and (st["s1"] is None or s_t < st["s1"] - 0.3):
                    targets.append((s_t, side))
            if st["s1"] is not None:
                targets.append((st["s1"], st["need"]))
            st["side0"] = self._distribute(line, f_str, st, targets, side_first, L0)
            side_first = None
            st_prev = st
        if stretches[0]["side0"] is None:
            stretches[0]["side0"] = "R"

        # ---- the steps
        t_walk0 = self.t
        t_hs_prev = None
        prog_t, prog_s = [self.t], [s_c]
        for st in stretches:
            ls = st["ls"]
            n_all = len(ls) if st["end"] != "open" else None
            mult = st["mult"]
            side = st["side0"]
            s_prev = st["s0"]
            k = 0
            while True:
                if k < len(ls):
                    l = float(ls[k])
                elif st["end"] != "open":
                    break
                else:
                    l0 = L0 * mult(k, None)
                    l = l0 * float(np.interp(s_prev + 0.5 * l0, line.s, f_str))
                s_k = s_prev + l
                ramp_t = p["start_time"] if st["start"] == "stand" else p["resume_time"]
                m_t = ramp_t[k] if k < len(ramp_t) else 1.0
                if n_all is not None:
                    tail_t = p["stop_time"] if st["end"] == "stop" else p["approach_time"]
                    if n_all - 1 - k < len(tail_t):
                        m_t = max(m_t, tail_t[n_all - 1 - k])
                fc = float(np.interp(s_prev + 0.5 * l, line.s, f_cad))
                wob = _wobble(0.0 if t_hs_prev is None else t_hs_prev - t_walk0, p["var"])
                P = P0 * m_t / fc / wob
                if k == 0 and st["start"] == "stand":
                    t_lo = self.t + p["unload"]
                    t_hs = t_lo + p["first_swing"]
                elif k == 0:                         # first walking step after a passage
                    t_lo = t_hs_prev + p["exit2_ds"]
                    t_hs = t_lo + p["exit2_swing"]
                else:
                    t_lo = t_hs_prev + p["ds_frac"] * P
                    t_hs = t_hs_prev + P
                sg = SIGN[side]
                ph_s = 0.0 if side == "L" else 1.9
                dx = p["var"] * 0.004 * math.sin(2.1 * k + ph_s)
                dyaw = p["var"] * 1.0 * DEG * math.sin(1.3 * k + 0.7 + ph_s)
                last = n_all is not None and k == n_all - 1
                if last and st["end"] == "stop":     # braking step: feet end side by side, centred
                    lat = sg * 0.5 * (p["heel_x"] + p["stand_half_width"])
                    yaw = float(line.heading(line.s_end)) + sg * p["toe_out"]
                elif last and st["end"] == "passage":   # entry step, foot turned towards the side
                    lay = st["lay"]
                    lat = lay["n_entry"]
                    yaw = float(line.heading(s_k)) + lay["a_entry"]
                else:
                    lat = sg * (p["heel_x"] + dx) + float(np.interp(s_k, line.s, shift))
                    if k in st["apex"]:              # the outer foot is planted outside the corner
                        lat += sg * p["apex_out"]
                    yaw = float(line.heading(s_k + p["foot_yaw_lead"])) + sg * (p["toe_out"] + dyaw)
                xz = line.pos(s_k) + lat * line.normal(s_k)
                size = l / L0
                alpha = p["alpha_hs"] * float(np.clip(0.4 + 0.6 * size, 0.4, 1.0))
                lam = float(np.clip(size, 0, 1))
                if k == 0 and st["start"] == "resume":
                    # out of the sideways stance: the trailing foot pushes off with a heel rise
                    # (which lets the leg reach the body that has moved on), is swung round along
                    # a path in space (a joint-space walking swing would sweep the toes of a foot
                    # pointing sideways over the floor) and lands on the heel as in walking
                    step = Footstep(side, t_lo, t_hs, xz, yaw, alpha, lam, "side", size,
                                    lift_style="walk", land_style="heel", lift_h=p["exit2_lift"])
                else:
                    step = Footstep(side, t_lo, t_hs, xz, yaw, alpha, lam, "walk", size)
                self._add(step)
                prog_t.append(t_hs)
                prog_s.append(s_k - 0.20)
                side, s_prev, t_hs_prev = OTHER[side], s_k, t_hs
                k += 1
                if st["end"] == "open" and t_hs > t_end:
                    break
            if st["end"] == "stop":
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
            elif st["end"] == "passage":
                t_hs_prev = self._passage_steps(line, st["lay"], self.steps[-1], prog_t, prog_s)
        for pa in shoulder:
            self._shoulder_turn(pa, prog_t, prog_s)
        # progress guess on the body line (for projecting the centre of mass onto it)
        prog_b = [_nearest_s(body_line, line.pos(s)) for s in prog_s]
        self.heading_prog.append((t_walk0, "line", (body_line, np.array(prog_t), np.array(prog_b))))
        self.t = self.steps[-1].t_hs
        return self

    def _distribute(self, line, f_str, st, targets, side0, L0):
        """Step lengths of one stretch (stored in st['ls']), so that the feet land exactly at its
        anchors with the required feet.  Returns the side of the first step (None if free)."""
        p = self.p
        apex = set()
        ramp = p["start_len"] if st["start"] == "stand" else p["resume_len"]
        tail = p["stop_len"] if st["end"] == "stop" else p["approach_len"]

        def mult(k, n_total):
            m = ramp[k] if k < len(ramp) else 1.0
            if n_total is not None and n_total - 1 - k < len(tail):
                m = min(m, tail[n_total - 1 - k])
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

        ls = []
        s_from, k0 = st["s0"], 0
        for j, (s_to, need) in enumerate(targets):
            final = j == len(targets) - 1 and st["end"] != "open"
            D = s_to - s_from
            if D < 0.25 * L0 and not final:
                continue
            if D < 0.1:
                print("warning: no room for steps before an anchor at s = %.2f" % s_to)
                D = 0.1
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
            if need is not None and not bad and not final:
                apex.add(k0 + n - 1)
            s_from, k0 = s_to, k0 + n
        st["ls"], st["apex"], st["mult"] = ls, apex, mult
        return side0

    def _passage_steps(self, line, lay, e1, prog_t, prog_s):
        """Append the side steps of a passage after its entry step e1: the trailing foot comes
        round and is put down beside the leading one, turned sideways; side steps with the
        leading foot alternate with closing steps of the trailing one; the leading foot steps
        out turned back towards the line.  Adds the heading offset (the body turned sideways)
        and the sideways envelope.  Returns the touch-down time of the last side step."""
        p = self.p
        t_prev = e1.t_hs
        side_steps = []
        for j, f in enumerate(lay["steps"]):
            t_lo = t_prev + (p["entry_ds"] if j == 0 else p["side_ds"])
            t_hs = t_lo + f["swing"]
            xz = line.pos(f["s"]) + f["n"] * line.normal(f["s"])
            yaw = float(line.heading(f["s"])) + f["a"]
            st = Footstep(f["side"], t_lo, t_hs, xz, yaw, p["side_alpha"], p["side_lam"], "side", 0.0,
                          lift_style=f["lift"], lift_h=p["side_lift"])
            self._add(st)
            side_steps.append(st)
            prog_t.append(t_hs)
            prog_s.append(f["m"])
            t_prev = t_hs
        e2, x1 = side_steps[0], side_steps[-1]
        t_x2 = x1.t_hs + p["exit2_ds"] + p["exit2_swing"]   # touch-down of the first walking step
        sig = lay["sig"]
        kt = [e1.t_lo - 0.10, e1.t_hs, e2.t_hs, e2.t_hs + 0.25, x1.t_lo, x1.t_hs, t_x2, t_x2 + 0.40]
        kv = [0.0, p["entry_turn"], 86.0 * DEG, 90.0 * DEG, 90.0 * DEG, p["exit_turn"], p["exit2_turn"], 0.0]
        self.offsets.append(PchipInterpolator(kt, sig * np.array(kv)))
        self.side_knots.append(PchipInterpolator([e1.t_lo, e2.t_hs, x1.t_lo, t_x2], [0.0, 1.0, 1.0, 0.0]))
        return x1.t_hs

    def _shoulder_turn(self, pa, prog_t, prog_s):
        """A gap walked through with the arms held still and the shoulders turned by pa.beta
        (the thorax by all of it, the pelvis by shoulder_pelvis of it), from shoulder_in before
        the narrow part until shoulder_out after it.  The times come from the walking progress
        (where the body is when each foot lands)."""
        p = self.p
        o = np.argsort(prog_t)
        tk, sk = np.asarray(prog_t)[o], np.maximum.accumulate(np.asarray(prog_s)[o])
        t_in = float(np.interp(pa.s_a - p["shoulder_in"], sk, tk))
        t_out = float(np.interp(pa.s_b + p["shoulder_out"], sk, tk))
        sig = 1.0 if pa.turn == "L" else -1.0
        ramp = p["shoulder_ramp"]
        kt = [t_in - ramp, t_in, t_out, t_out + ramp]
        b = sig * pa.beta
        self.offsets.append(PchipInterpolator(kt, [0.0, p["shoulder_pelvis"] * b, p["shoulder_pelvis"] * b, 0.0]))
        self.thorax_offsets.append(PchipInterpolator(kt, [0.0, (1.0 - p["shoulder_pelvis"]) * b,
                                                          (1.0 - p["shoulder_pelvis"]) * b, 0.0]))
        self.arm_knots.append(PchipInterpolator([kt[0] - 0.2, kt[1] - 0.2, kt[2], kt[3]], [0.0, 1.0, 1.0, 0.0]))

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
            self._add(Footstep(side, t_lo, t_hs, xz, yaw, p["turn_alpha"], 0.25, "shuffle", 0.0,
                               lift_h=p["turn_lift"]))
            t_prev = t_hs
        kh[-1] = h0 + angle
        kt.append(t_prev + 0.35)
        kh.append(h0 + angle)
        self.heading_prog.append((kt[0], "interp", PchipInterpolator(kt, kh)))
        self.t = t_prev
        return self

    def finish(self, duration):
        return Plan(self.p, self.initial, self.steps, self.heading_prog, duration,
                    self.offsets, self.side_knots, self.thorax_offsets, self.arm_knots)


def _passage_layout(line, pa, p):
    """Where the feet go in a passage, in line coordinates (s along the line, n to its left).

    Sideways, the body faces the side 'turn' of the line (sig = +1 left, -1 right); the leading
    foot is the one on the side the body travels to.  The standing centre of pressure of every
    sideways foot is on the lateral line n = centre + sig * squeeze_bias (which centres the
    body, belly to back, in the gap).  The feet alternate between a narrow stance (side_narrow
    apart) and a wide one (one side step further apart); the narrow stances are centred at
    m_0 ... m_n, from squeeze_in before the narrow part to squeeze_out after it, in n equal
    side steps of at most side_step.

      entry (E1)  the leading foot's last walking step, put down turned by entry_yaw towards
                  the facing side, where it will stand in the first narrow stance (at m_0)
      E2          the trailing foot comes round and is put down sideways behind it
      S_k, C_k    side step of the leading foot, closing step of the trailing foot
      exit (X1)   the leading foot steps out by exit_step, turned back to exit_yaw from the
                  line; the trailing foot then takes the first walking step (in walk())"""
    sig = 1.0 if pa.turn == "L" else -1.0
    lead = "R" if sig > 0 else "L"
    trail = OTHER[lead]
    wn = p["side_narrow"]
    m0 = pa.s_a - p["squeeze_in"]
    m1 = max(pa.s_b + p["squeeze_out"], m0 + 0.1)
    n = max(1, int(math.ceil((m1 - m0) / p["side_step"] - 1e-9)))
    d = (m1 - m0) / n
    nc = pa.center + sig * p["squeeze_bias"]
    a_side = sig * 0.5 * math.pi

    def heel(sq, nq, a):
        """Heel-circle centre (s, n) of a foot at yaw a (relative to the line) whose standing
        centre of pressure is at (sq, nq)."""
        return sq - D_ST * math.cos(a), nq - D_ST * math.sin(a)

    steps = []

    def add(side, sq, a, m, swing, lift="flat"):
        s, n_ = heel(sq, nc, a)
        steps.append(dict(side=side, s=s, n=n_, a=a, m=m, swing=swing, lift=lift))

    a_e = sig * p["entry_yaw"]
    s_e, n_e = heel(m0 + 0.5 * wn, nc, a_e)
    add(trail, m0 - 0.5 * wn, a_side, m0, p["entry_swing"], lift="walk")
    # no two side steps exactly alike: small variations of length (the narrow stances still
    # start at m_0 and end at m_n) and of swing time
    v = p["var"]
    dk = d * (1.0 + v * 0.05 * np.sin(1.9 * np.arange(n) + 0.4))
    dk *= (m1 - m0) / dk.sum()
    mk = m0
    for k in range(n):
        sw = p["side_swing"] * (1.0 + v * 0.04 * math.sin(2.3 * k + 1.1))
        add(lead, mk + 0.5 * wn + dk[k], a_side, mk + 0.5 * dk[k], sw)
        sw = p["side_swing"] * (1.0 + v * 0.04 * math.sin(2.3 * k + 2.6))
        add(trail, mk + dk[k] - 0.5 * wn, a_side, mk + dk[k], sw)
        mk += dk[k]
    a_x = sig * p["exit_yaw"]
    s_x = m1 + 0.5 * wn + p["exit_step"] - D_ST * math.cos(a_x)
    n_x = 0.5 * pa.center - sig * p["heel_x"]
    steps.append(dict(side=lead, s=s_x, n=n_x, a=a_x, m=m1 + 0.5 * p["exit_step"],
                      swing=p["exit_swing"], lift="flat"))
    if _DEBUG:
        print("passage %r: %d side steps of %.3f m, stance centres %.2f..%.2f" % (pa, n, d, m0, m1))
    return dict(sig=sig, lead=lead, trail=trail, s_entry=s_e, n_entry=n_e, a_entry=a_e,
                s_exit=s_x, steps=steps, s_lo=pa.s_a, s_hi=pa.s_b, n_cycles=n, d=d, m0=m0, m1=m1)


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
    def __init__(self, p, initial, steps, heading_prog, duration, offsets=(), side_knots=(),
                 thorax_offsets=(), arm_knots=()):
        self.p = p
        self.duration = float(duration)
        self.steps = sorted(steps, key=lambda s: s.t_hs)
        self.heading_prog = sorted(heading_prog, key=lambda e: e[0])
        self.offsets = list(offsets)
        self.side_knots = list(side_knots)
        self.thorax_offsets = list(thorax_offsets)
        self.arm_knots = list(arm_knots)
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
        if st.kind == "shuffle" or st.lift_style != "walk":
            return 0.25
        travel = float(np.linalg.norm(st.xz - P.xz))
        return float(np.clip(0.2 + 0.8 * travel / self.p["stride"], 0.2, 1.0))

    def _knots(self, P, other_swings):
        """Stance clock u(t) and loading-response strength lam(t) of a plant as knots.

        Walking:  touch-down 0, other foot off 0.1, other foot down 0.5, toe off 0.6.
        Standing: u rests at U_ST; before a lift-off from standing the foot is unloaded and
        u runs from U_ST to 0.6 over p['unload'] seconds.
        Flat landing (side steps): the foot lands flat (phi_ff) and settles at U_ST.
        Flat lift-off (side steps): u only rises to side_u_off (a slight heel rise) over the
        last side_unload seconds."""
        p = self.p
        T, U, L = [], [], []

        def add(t, u, lam):
            if T and t < T[-1] + 1e-3:
                t = T[-1] + 1e-3
            T.append(float(t))
            U.append(float(u))
            L.append(float(lam))

        flat_off = P.lifts and P.lift.lift_style == "flat"
        later = [(a, b) for (a, b) in other_swings if P.t_on - 1e-9 <= a < P.t_off]
        t_unload = P.t_off - (p["side_unload"] if flat_off else p["unload"]) if P.lifts else T_INF
        if P.landing and P.step.land_style == "flat":
            add(P.t_on, p["phi_ff"], P.lam)
            add(P.t_on + min(0.12, 0.4 * (P.t_off - P.t_on)), U_ST, P.lam)
        elif P.landing:
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
            walking_like = P.lifts and (P.t_off - b) < 0.35 and not flat_off
            if a > T[-1] + 1e-6:
                add(a, max(U[-1], 0.1), L[-1])
            if walking_like:
                add(b, 0.5, L[-1])
            else:
                add(b, max(U[-1], U_ST), 0.0)
        if P.lifts:
            if flat_off:
                add(max(t_unload, T[-1] + 0.02), max(U[-1], U_ST), 0.0)
                add(P.t_off, max(U[-1], p["side_u_off"]), 0.0)
            elif abs(U[-1] - 0.5) < 1e-9 and P.t_off - T[-1] < 0.35:
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

    def side_env(self, t):
        """Sideways envelope: 1 while side-stepping through a passage, 0 otherwise."""
        return _sum_programs(self.side_knots, t)

    def heading_offset(self, t):
        """Heading offset of the body (turned sideways in passages)."""
        return _sum_programs(self.offsets, t)

    def thorax_offset(self, t):
        """Extra rotation of the thorax relative to the pelvis heading (shoulder turns)."""
        return _sum_programs(self.thorax_offsets, t)

    def arm_still(self, t):
        """1 where the arms are held still (narrow gaps), 0 otherwise."""
        return np.clip(_sum_programs(self.arm_knots, t), 0.0, 1.0)

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
        return out + self.heading_offset(t)


def _sum_programs(progs, t):
    """Sum of PCHIP programs that are zero outside their knots."""
    t = np.asarray(t, dtype=float)
    out = np.zeros(t.shape)
    for f in progs:
        x = f.x
        m = (t > x[0]) & (t < x[-1])
        if m.any():
            out[m] += f(t[m])
    return out


def _monotone_knots(t, v):
    """Sort knots by time and drop near-duplicates (for PCHIP)."""
    t = np.asarray(t, dtype=float)
    v = np.asarray(v, dtype=float)
    o = np.argsort(t, kind="stable")
    t, v = t[o], v[o]
    keep = np.concatenate([[True], np.diff(t) > 1e-3])
    return t[keep], v[keep]
