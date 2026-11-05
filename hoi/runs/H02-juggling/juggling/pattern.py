"""The hands and the balls in space, before any body exists.

The balls come first.  Their flights are exact free falls between planned release and catch points
(schedule.Throw).  The hands are then built to fit:

  * at a release the hand has the position and velocity of the ball, and its acceleration is
    exactly -g.  That is the physics of letting go: a ball leaves a hand at the moment the hand slows
    down faster than gravity can slow the ball.
  * before a catch the hand comes up under the ball and is already moving down with it, at a share
    of the ball's speed.  The rest of the speed is taken up in the first few hundredths of a second
    by the ball sinking from the fingers into the palm (see Hold.give).
  * the dwell (ball in hand) is a scoop: down and in from the catch, then a fast push up from the
    bottom of the dip.  Between a release and the next catch the empty hand follows through upwards
    and swings out under the next ball.

A hand point H(t) stands for the seat of a single ball.  Everything is planned in the person's frame.
"""
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline

from locomotion.rotations import mv, rx, ry, rz
from locomotion.skeleton import FLOOR
from manipulation.hand import NAMES

from .curves import min_jerk, move, wobble
from .fingers import FINGERS, PALM_NORMAL
from .schedule import G

BASE = {"L": np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]]),
        "R": np.array([[0.0, 0.0, -1.0], [0.0, -1.0, 0.0], [-1.0, 0.0, 0.0]])}
SIGN = {"L": 1.0, "R": -1.0}
GIVE_MIN_TIME = 0.03


class HandTrack:
    """The path and orientation of one hand over the clip."""

    def __init__(self, plan, side, hand):
        self.plan, self.side, self.hand = plan, side, hand
        self.q = plan.q
        self.sg = SIGN[side]
        self.ev = plan.events[side]
        self._orientation()
        self._position()

    # ---------------------------------------------------------------- orientation
    def _yaw_at(self, p):
        q = self.q
        ex = self.sg * q["elbow_x"]
        return q["hand_yaw_share"] * np.arctan2(p[0] - ex, p[2] - q["elbow_z"])

    def _ready_point(self, t):
        q = self.q
        return self.plan.anchor(np.array(t)) + np.array([self.sg * q["ready_x"], FLOOR + q["ready_y"] + self.plan.lift, q["ready_z"]])

    def _orientation(self):
        q, ev = self.q, self.ev
        keys = []                                   # (t, pitch, roll, yaw)
        p0 = self._ready_point(0.0)

        def add(t, tilt, p):
            keys.append((t, tilt[0], tilt[1], self._yaw_at(p)))

        add(-1.0, q["tilt_ready"], p0)
        add(ev[0].t - 0.62, q["tilt_ready"], p0)
        for i, e in enumerate(ev):
            nxt = ev[i + 1] if i + 1 < len(ev) else None
            if e.kind == "throw":
                add(e.t - q["t_up"], q["tilt_bottom"], e.p)
                add(e.t, q["tilt_throw"], e.p)
                add(e.t + q["t_top"], q["tilt_top"], e.p)
            else:
                add(e.t, q["tilt_catch"], e.p)
                if nxt is not None and nxt.kind == "catch":
                    add(e.t + 0.22, q["tilt_bottom"], e.p)
                    add(nxt.t - 0.14, q["tilt_catch"], nxt.p)
        t_end = ev[-1].t
        add(t_end + 0.25, q["tilt_bottom"], ev[-1].p)
        add(t_end + 0.95, q["tilt_ready"], self._ready_point(t_end + 0.95))
        add(max(self.plan.ev["back1"], t_end + 1.5), q["tilt_ready"], self._ready_point(self.plan.dur))
        add(self.plan.dur + 2.0, q["tilt_ready"], self._ready_point(self.plan.dur))
        keys.sort(key=lambda k: k[0])
        k = [keys[0]]
        for row in keys[1:]:       # (keys closer than a few frames would make the spline swing)
            if row[0] - k[-1][0] > 0.04:
                k.append(row)
        k = np.array(k)
        self.orient = CubicSpline(k[:, 0], k[:, 1:], bc_type="clamped")

    def rot(self, t):
        """World rotation (n, 3, 3) of the wrist joint."""
        t = np.asarray(t, dtype=float)
        o = self.orient(np.clip(t, -1.0, self.plan.dur + 2.0))
        return ry(o[..., 2]) @ rx(-o[..., 0]) @ rz(self.sg * o[..., 1]) @ BASE[self.side]

    def seat(self, name):
        return self.hand.offset(self.side, name)

    def normal(self, t):
        return mv(self.rot(t), PALM_NORMAL)

    # ---------------------------------------------------------------- position
    def _hand_point(self, e):
        """Where H must be for the ball of event e to be where it should."""
        R = self.rot(np.array(e.t))
        off = self.seat(e.seat) - self.seat("one")
        H = e.p - R @ off
        if e.kind == "catch":
            H = H - self.q["catch_give"] * (R @ PALM_NORMAL)
        return H

    def _position(self):
        """Knots of the hand point.  At a release position, velocity and acceleration are the
        ball's; at a catch position and velocity are prescribed.  The bottom of the dip and the
        top of the follow-through are turning points of a prescribed height (zero vertical speed,
        so that they really are the lowest and highest points: the arm's reach depends on it).  All
        the rest is left to min_jerk."""
        q, ev = self.q, self.ev
        free = np.nan
        ky, kx, kz = [], [], []            # knots (t, p, v, a)
        cm, cs = q["catch_match"], q["catch_match_side"]
        p0 = self._ready_point(0.0)
        low = FLOOR + q["y_low"] + self.plan.lift     # the arm cannot follow further down than this
        t_wait = ev[0].t - 0.60
        for t in (-1.0, t_wait):
            ky.append((t, p0[1], 0.0, 0.0))
            kx.append((t, p0[0], 0.0, 0.0))
            kz.append((t, p0[2], 0.0, 0.0))
        self.H_event = []
        for i, e in enumerate(ev):
            H = self._hand_point(e)
            self.H_event.append(H)
            nxt = ev[i + 1] if i + 1 < len(ev) else None
            if e.kind == "throw":
                vy = e.v[1]
                ky.append((e.t - q["t_up"], max(H[1] - q["up_share"] * vy * q["t_up"], low - 0.02), 0.0, free))
                ky.append((e.t, H[1], vy, -G))
                ky.append((e.t + q["t_top"], H[1] + 0.47 * vy * q["t_top"], 0.0, free))
                kx.append((e.t, H[0], e.v[0], 0.0))
                kz.append((e.t, H[2], e.v[2], 0.0))
            else:
                vy = cm * e.v[1]
                ky.append((e.t, H[1], vy, free))
                kx.append((e.t, H[0], cs * e.v[0], free))
                kz.append((e.t, H[2], cs * e.v[2], free))
                if nxt is not None and nxt.kind == "catch":
                    ky.append((e.t + 0.21, max(H[1] + 0.40 * vy * 0.21, low), 0.0, free))
                    ky.append((nxt.t - 0.15, H[1] + 0.05, 0.0, free))
                    kx.append((e.t + 0.21, H[0] + 0.05 * cs * e.v[0], 0.0, free))
                    kz.append((e.t + 0.21, H[2] + 0.05 * cs * e.v[2], 0.0, free))
        # after the last catch: the hand gives way, then settles at the ready position
        e, H = ev[-1], self.H_event[-1]
        vy = cm * e.v[1]
        ky.append((e.t + 0.23, max(H[1] + 0.42 * vy * 0.23, low), 0.0, free))
        t_r = e.t + 0.95
        pr = self._ready_point(t_r)
        # (without this stop the hand keeps the curve of its fast last swing, and the long, slack
        # path to the ready position turns that into a wide swing across the body)
        kx.append((e.t + 0.23, H[0] + 0.05 * cs * e.v[0], 0.0, free))
        kz.append((e.t + 0.23, H[2] + 0.05 * cs * e.v[2], 0.0, free))
        ky.append((t_r, pr[1], 0.0, 0.0))
        kx.append((t_r, pr[0], 0.0, 0.0))
        kz.append((t_r, pr[2], 0.0, 0.0))
        t_e = max(self.plan.ev["back1"], t_r + 0.5)
        pe = self._ready_point(self.plan.dur)
        for t in (t_e, self.plan.dur + 2.0):
            if t <= t_r:
                continue
            ky.append((t, pe[1], 0.0, 0.0))
            kx.append((t, pe[0], 0.0, 0.0))
            kz.append((t, pe[2], 0.0, 0.0))
        self.path = [min_jerk(*np.array(sorted(k, key=lambda r: r[0])).T) for k in (kx, ky, kz)]

    def pos(self, t, deriv=0):
        return np.stack([c(t, deriv) for c in self.path], -1)

    def point(self, t, seat_offset):
        """World position of a point of the hand given relative to the wrist; seat_offset (3,) or
        (n, 3)."""
        R = self.rot(t)
        return self.pos(t) + mv(R, seat_offset - self.seat("one"))

    def wrist(self, t):
        return self.pos(t) - mv(self.rot(t), self.seat("one"))


@dataclass
class Hold:
    """A ball lying in a hand from t0 to t1."""
    ball: int
    side: str
    t0: float
    t1: float
    keys: list                   # [(t_start, t_end, seat before, seat after)]
    first: str
    give: tuple = None           # (time of the catch, duration, offset, relative velocity)


class Scene:
    """Hands and balls together: where every ball is at any time, and what the fingers do."""

    def __init__(self, plan, hand):
        self.plan, self.hand = plan, hand
        self.q = plan.q
        self.tracks = {s: HandTrack(plan, s, hand) for s in "LR"}
        self._holds()

    def _holds(self):
        plan, q = self.plan, self.q
        holds = {b: [] for b in range(plan.n_balls)}
        release = {}
        for th in plan.throws:
            release.setdefault(th.ball, []).append(th)
        big = plan.dur + 10.0
        for side, items in plan.start_hold.items():
            for b, seat in items:
                t1 = release[b][0].t_rel if b in release else big
                holds[b].append(Hold(b, side, -10.0, t1, [], seat))
        # the ball behind the first thrown ball moves up into the single seat after that throw
        first = plan.events["R"][0]
        for h in holds[2]:
            h.keys.append((first.t + 0.05, first.t + 0.34, "rear", "one"))
        for th in plan.throws:
            nxt = [x for x in release[th.ball] if x.t_rel > th.t_rel]
            t1 = nxt[0].t_rel if nxt else big
            tr = self.tracks[th.dst]
            ev = next(e for e in plan.events[th.dst] if e.kind == "catch" and e.ball == th.ball and abs(e.t - th.t_catch) < 1e-9)
            v_hand = tr.pos(np.array(th.t_catch), 1)
            rel = th.v_catch - v_hand
            n = tr.normal(np.array(th.t_catch))
            D0 = q["catch_give"] * n
            speed_in = max(-float(rel @ n), 1e-3)
            T = float(np.clip(2.8 * q["catch_give"] / speed_in, GIVE_MIN_TIME, 0.10))
            holds[th.ball].append(Hold(th.ball, th.dst, th.t_catch, t1, [], ev.seat, (th.t_catch, T, D0, rel)))
        # a ball that waits for a second one to arrive moves back towards the heel of the hand
        for side in "LR":
            e = plan.events[side]
            if len(e) >= 2 and e[-1].kind == "catch" and e[-2].kind == "catch":
                for h in holds[e[-2].ball]:
                    if h.side == side and h.t0 == e[-2].t:
                        h.keys.append((e[-1].t - 0.42, e[-1].t - 0.10, "one", "rear"))
        self.holds = holds

    def _seat_of(self, h, t):
        tr = self.tracks[h.side]
        o = np.broadcast_to(tr.seat(h.first), (len(t), 3)).copy()
        for ta, tb, a, b in h.keys:
            w = move(t, ta, tb)[:, None]
            o = o * (1.0 - w) + w * tr.seat(b)
        return o

    def balls(self, t):
        """Positions (n, N, 3) of all balls at times t."""
        plan = self.plan
        t = np.asarray(t, dtype=float)
        out = np.zeros((len(t), plan.n_balls, 3))
        for b, items in self.holds.items():
            for h in items:
                m = (t >= h.t0) & (t < h.t1)
                if not m.any():
                    continue
                tm = t[m]
                p = self.tracks[h.side].point(tm, self._seat_of(h, tm))
                if h.give is not None:
                    tc, T, D0, rel = h.give
                    s = np.clip((tm - tc) / T, 0.0, 1.0)[:, None]
                    p = p + (2 * s ** 3 - 3 * s ** 2 + 1) * D0 + (s ** 3 - 2 * s ** 2 + s) * T * rel
                out[m, b] = p
        for th in plan.throws:
            m = (t >= th.t_rel) & (t < th.t_catch)
            if m.any():
                out[m, th.ball] = th.at(t[m])
        return out

    def held_by(self, t):
        """(n, N) masks: is ball b in the left, in the right hand at time t."""
        t = np.asarray(t, dtype=float)
        L = np.zeros((len(t), self.plan.n_balls), dtype=bool)
        Rr = np.zeros_like(L)
        for b, items in self.holds.items():
            for h in items:
                m = (t >= h.t0) & (t < h.t1)
                (L if h.side == "L" else Rr)[m, b] = True
        return L, Rr

    # ---------------------------------------------------------------- fingers
    def fingers(self, t, side):
        """hand_pose (n, 15, 3)."""
        t = np.asarray(t, dtype=float)
        S = self.hand.shapes[side]
        n = len(t)
        lags = dict(index=-0.012, middle=-0.004, ring=0.006, pinky=0.014, thumb=-0.006)
        out = np.zeros((n, 15, 3))
        groups = {}
        for i, name in enumerate(NAMES):
            key = next(f for f in FINGERS + ("thumb",) if f in name)
            groups.setdefault(key, []).append(i)
        for f, idx in groups.items():
            tl = t - lags[f]
            w2, wo, wf = self._finger_weights(tl, side)
            hold = S["one"][None, idx] + w2[:, None, None] * (S["two"] - S["one"])[None, idx]
            shape = hold + wo[:, None, None] * (S["ready"] - S["one"])[None, idx] \
                + wf[:, None, None] * (S["flick"] - S["ready"])[None, idx]
            out[:, idx] = shape
        # no finger ever holds perfectly still
        for j, (f, idx) in enumerate(groups.items()):
            jig = 0.012 * wobble(t, 40 + j + (0 if side == "L" else 10), 0.3, 1.1)
            out[:, idx, 2] += (-SIGN[side]) * jig[:, None]
        return out

    def _finger_weights(self, t, side):
        """Shares of the two-ball shape, the open hand and the stretched fingers."""
        ev = self.plan.events[side]
        two = np.zeros(len(t))
        opened = np.zeros(len(t))
        flick = np.zeros(len(t))
        if self.plan.start_hold[side] and len(self.plan.start_hold[side]) == 2:
            two = 1.0 - move(t, ev[0].t + 0.05, ev[0].t + 0.34)
        for i, e in enumerate(ev):
            if e.kind == "throw":
                keeps = i == 0 and len(self.plan.start_hold[side]) == 2
                if not keeps:
                    opened = opened + move(t, e.t - 0.045, e.t + 0.075)
                    a = move(t, e.t - 0.06, e.t + 0.02)
                    b = move(t, e.t + 0.05, e.t + 0.19)
                    flick = flick + a * (1.0 - b)
            else:
                if e.seat == "front":
                    two = two + move(t, e.t - 0.40, e.t - 0.08)
                else:
                    opened = opened - move(t, e.t - 0.05, e.t + 0.06)
        return two, np.clip(opened, 0.0, 1.0), np.clip(flick, 0.0, 1.0)
