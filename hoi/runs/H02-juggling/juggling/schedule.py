"""What happens when: the timeline of the clip and the list of throws.

Everything here is planned in the person's own frame: the pelvis stands at x = z = 0 at the start,
facing +z, and y is the height in world coordinates.  Rig.generate() moves the result to the start
position and heading of the task at the very end.

The classic three-ball pattern (the cascade) has a simple law.  The hands throw in turns, one beat
apart, and every ball is thrown again three beats after it was last thrown.  So the time in the air
and the time in the hand add up to three beats:   flight + dwell = 3 * beat.
"""
import sys
from dataclasses import dataclass, field

import numpy as np

from locomotion.skeleton import FLOOR

from .curves import move, wobble

G = 9.81
GRAV = np.array([0.0, -G, 0.0])


@dataclass
class Throw:
    """One flight of one ball: an exact free fall from the release to the catch."""
    k: int
    ball: int
    src: str                # the hand that throws
    dst: str                # the hand that catches
    t_rel: float
    t_catch: float
    p_rel: np.ndarray
    p_catch: np.ndarray
    v_rel: np.ndarray = field(init=False)
    v_catch: np.ndarray = field(init=False)

    def __post_init__(self):
        F = self.t_catch - self.t_rel
        self.v_rel = (self.p_catch - self.p_rel - 0.5 * GRAV * F * F) / F
        self.v_catch = self.v_rel + GRAV * F

    def at(self, t):
        s = (np.asarray(t, dtype=float) - self.t_rel)[..., None]
        return self.p_rel + self.v_rel * s + 0.5 * GRAV * s * s

    @property
    def apex(self):
        return float(self.p_rel[1] + self.v_rel[1] ** 2 / (2.0 * G))


@dataclass
class HandEvent:
    kind: str               # "throw" or "catch"
    t: float
    ball: int
    p: np.ndarray           # where the ball is
    v: np.ndarray           # how fast the ball is moving
    seat: str = "one"       # where in the hand the ball is at that moment


class Plan:
    """Timeline (ev), throws, the events of each hand and the sideways drift of the pattern."""

    def __init__(self, task, q, stance, hand):
        self.q = q
        self.stance = stance
        self.hand = hand
        self.fps = int(task.get("fps", 30))
        self.frames = int(task.get("frames", 600))
        self.dur = self.frames / float(self.fps)
        balls = task["balls"]
        self.n_balls = int(balls["count"])
        if self.n_balls != 3:
            raise ValueError("the cascade is built for three balls, the task has %d" % self.n_balls)
        self.radius = float(balls["radius"])
        self.ball_mass = float(balls["mass_kg"])
        # the plan gives the height of the ball's centre: a larger ball lies higher above the palm, and
        # it is the palm that has to stay in reach
        self.lift = self.radius - q["radius_ref"]
        j = task["juggle"]
        self.stand = "L" if j.get("standing_foot", "left") == "left" else "R"
        self.free = "R" if self.stand == "L" else "L"
        self.sign_stand = 1.0 if self.stand == "L" else -1.0
        self.shift_size = stance.travel(self.stand)     # how far the weight travels sideways
        self._timeline(j)
        self._throws()
        self._hand_events()

    # ------------------------------------------------------------------ timeline
    def _timeline(self, j):
        q = self.q
        n2 = float(j.get("min_throws_two_feet", 9))
        n1 = float(j.get("min_throws_one_foot", 12))
        one_s = float(j.get("min_one_foot_s", 5.0))
        heavy = np.clip(self.ball_mass - 0.12, -0.1, 0.5)
        beat = float(np.clip(q["beat"] + q["beat_per_kg"] * heavy, q["beat_min"], q["beat_max"]))

        def needs(beat):
            flight = 3.0 * beat - self._dwell(beat)
            after = q["wait_after_catch"] + q["lower_time"]   # last catch -> toes on the floor
            a = (n2 + q["margin_throws"]) * beat
            b = max((n1 + q["margin_throws"]) * beat + flight, one_s + q["margin_time"] - after)
            return a, b

        lead, tail = q["lead"], q["tail"]
        a, b = needs(beat)
        spare = self.dur - lead - tail - a - b
        if spare < 0.0:      # a tight clip: first shorten the rest at both ends, then speed up
            cut = min(-spare, (lead - q["lead_min"]) + (tail - q["tail_min"]))
            share = (tail - q["tail_min"]) / max((lead - q["lead_min"]) + (tail - q["tail_min"]), 1e-6)
            tail -= cut * share
            lead -= cut * (1.0 - share)
            spare = self.dur - lead - tail - a - b
        while spare < 0.0 and beat > q["beat_min"] + 1e-9:
            beat = max(beat - 0.005, q["beat_min"])
            a, b = needs(beat)
            spare = self.dur - lead - tail - a - b
        spare = max(spare, 0.0)
        self.beat = beat
        self.dwell = self._dwell(beat)
        self.flight = 3.0 * beat - self.dwell
        t0 = lead
        t_off = t0 + a + q["two_foot_share"] * spare
        t_last = t_off + b + (1.0 - q["two_foot_share"]) * spare

        # throw times: a steady beat with a slowly changing tempo and small errors
        tg = np.arange(t0, self.dur + 1.0, 0.01)
        rate = 1.0 + q["var_tempo"] * wobble(tg, 11, 0.05, 0.25)
        clock = np.concatenate([[0.0], np.cumsum(rate[:-1] * 0.01)]) / beat   # in beats
        n = int(np.floor(np.interp(t_last - self.flight, tg, clock))) + 1
        n = max(n, 4)
        self.n_throws = n
        rng = np.random.default_rng(5)
        self.t_throw = np.interp(np.arange(n), clock, tg) + q["var_time"] * np.clip(rng.standard_normal(n), -2.0, 2.0)
        self.t_throw[0] = t0
        self.rng = rng
        t_last = float(self.t_throw[-1] + self.flight)

        ev = {}
        ev["first"] = t0
        ev["off"] = t_off                                    # the toes of the free foot leave
        ev["heel"] = t_off - q["heel_time"]                  # the heel starts to rise
        ev["shift0"] = ev["heel"] - q["shift_time"] - 0.25   # the weight starts to move
        ev["shift1"] = ev["heel"] - 0.25                     # the weight is on the standing foot
        ev["up"] = t_off + q["raise_time"]
        ev["last"] = t_last
        ev["down0"] = t_last + q["wait_after_catch"]
        ev["touch"] = ev["down0"] + q["lower_time"]          # the toes touch
        ev["flat"] = ev["touch"] + q["flatten_time"]
        ev["back0"] = ev["touch"] - 0.05
        ev["back1"] = ev["back0"] + q["return_time"]
        self.ev = ev

    def _dwell(self, beat):
        return self.q["dwell"] * beat / self.q["beat"]

    def var_scale(self, t):
        """Throws get a little less exact on one foot."""
        ev = self.ev
        w = move(t, ev["heel"], ev["off"] + 0.4) * (1.0 - move(t, ev["down0"], ev["touch"]))
        return 1.0 + (self.q["var_one_foot"] - 1.0) * w

    def weight_on_foot(self, t):
        """0: the weight is between the feet, 1: it is on the standing foot."""
        ev = self.ev
        return move(t, ev["shift0"], ev["shift1"]) * (1.0 - move(t, ev["back0"], ev["back1"]))

    def anchor(self, t):
        """Centre of the pattern (n, 3): it moves with the upper body, and wanders slowly."""
        t = np.asarray(t, dtype=float)
        q = self.q
        sway = self.weight_on_foot(t) * self.sign_stand * q["follow"] * self.shift_size
        ax = sway + 0.006 * wobble(t, 21, 0.03, 0.15)
        az = 0.006 * wobble(t, 22, 0.03, 0.15)
        return np.stack([ax, np.zeros_like(ax), az], -1)

    # ------------------------------------------------------------------ throws
    def _throws(self):
        q, rng = self.q, self.rng
        n = self.n_throws
        self.throws = []
        sgn = {"L": 1.0, "R": -1.0}
        for k in range(n):
            src = "R" if k % 2 == 0 else "L"
            dst = "L" if src == "R" else "R"
            t_r = float(self.t_throw[k])
            v = float(self.var_scale(np.array(t_r)))
            F = self.flight * (1.0 + q["var_flight"] * v * float(np.clip(rng.standard_normal(), -2.0, 2.0)))
            if k + 3 < n:      # the ball must arrive in time for its next throw
                F = min(F, float(self.t_throw[k + 3]) - t_r - 0.8 * self.dwell)
            t_c = t_r + F
            jr = q["var_pos"] * v * np.clip(rng.standard_normal(3), -2.0, 2.0) * np.array([0.8, 0.6, 0.8])
            jc = q["var_pos"] * v * np.clip(rng.standard_normal(3), -2.0, 2.0) * np.array([1.4, 1.0, 1.2])
            a_r = self.anchor(np.array(t_r))
            a_c = self.anchor(np.array(t_c))
            s = sgn[src]
            p_r = a_r + np.array([s * q["x_throw"], FLOOR + q["y_throw"] + self.lift, q["z_throw"]]) + jr
            p_c = a_c + np.array([-s * q["x_catch"], FLOOR + q["y_catch"] + self.lift, q["z_catch"]]) + jc
            # the front seat lies further along the fingers and higher: the ball moves out and up, so
            # that the hand can stay where it always is
            if k == 0:
                p_r = p_r + self.hand.front_offset
            if k == n - 1:
                p_c = p_c + self.hand.front_offset
            self.throws.append(Throw(k, k % 3, src, dst, t_r, t_c, p_r, p_c))
        self.ev["last"] = max(th.t_catch for th in self.throws)
        ev = self.ev
        q = self.q
        ev["down0"] = ev["last"] + q["wait_after_catch"]
        ev["touch"] = ev["down0"] + q["lower_time"]
        ev["flat"] = ev["touch"] + q["flatten_time"]
        ev["back0"] = ev["touch"] - 0.05
        ev["back1"] = ev["back0"] + q["return_time"]
        if ev["back1"] > self.dur - 0.3:
            print("warning: the clip is too short: the person is still settling %.1f s before its end"
                  % (self.dur - ev["back1"]), file=sys.stderr)

    def _hand_events(self):
        self.events = {"L": [], "R": []}
        for th in self.throws:
            self.events[th.src].append(HandEvent("throw", th.t_rel, th.ball, th.p_rel, th.v_rel))
            self.events[th.dst].append(HandEvent("catch", th.t_catch, th.ball, th.p_catch, th.v_catch))
        for side in "LR":
            self.events[side].sort(key=lambda e: e.t)
        # the very first throw comes out of a hand holding two balls, and a hand that catches a
        # ball while it holds another takes it on the fingers, in front of the other one
        self.events["R"][0].seat = "front"
        self.start_hold = {"L": [(1, "one")], "R": [(0, "front"), (2, "rear")]}
        for side in "LR":
            e = self.events[side]
            if len(e) >= 2 and e[-1].kind == "catch" and e[-2].kind == "catch":
                e[-1].seat = "front"
