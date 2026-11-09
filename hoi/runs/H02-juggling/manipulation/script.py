"""The script of a pick-up, carry and put-down: what happens when.

compose() turns a task into a footstep plan (locomotion.plan) and a table of event times:

  stop1    last foot down in front of the box
  down0    starts bending down                bottom   lowest point, hands on the box
  contact  palms touch the box                lift0    the box leaves the floor
  lift1    upright with the box               walk2    first step of the carry starts
  stop2    last foot down at the target       low0     starts lowering the box
  touch    the box stands on the floor        open0    fingers start to let go
  away     hands off the box                  rise0    starts standing up
  rise1    upright again                      still    last steps done, standing still

Durations depend on the weight of the box and are scaled by a tempo factor, chosen so that
the whole job fits the clip.
"""
import math

import numpy as np

from locomotion.path import WalkLine, hdir
from locomotion.plan import PlanBuilder
from locomotion.rotations import DEG

from .box import Box
from .route import choose_holds, plan_route

DEFAULTS = dict(
    # --- how to stand at the box
    standoff=0.235,        # from the near face of the box to the point between the feet [m]
    stance_half_width=0.125,   # heel-circle centres this far to either side of the line [m]
    stance_toe_out=13.0 * DEG,
    stance_stagger=0.05,   # the left foot this much ahead of the right one [m]
    approach_speed=1.15,   # expected walking speed without the box [m/s] (for choosing routes)
    carry_speed=0.9,       # ... with the box
    # --- durations [s]
    t_settle=0.30,         # stop -> starts bending
    t_down=1.30,           # bending down
    t_grip=0.40,           # hands on the box -> takes up the load
    t_load=0.32,           # the body braces before the box leaves the floor
    t_lift=1.15,           # lifting time for a weightless box, plus ...
    t_lift_kg=0.03,        # ... this much per kg
    t_hitch=0.40,          # upright with the box -> first step
    t_settle2=0.25,        # stop at the target -> starts lowering
    t_lower=1.90,          # lowering (longer than the lift: it is put down carefully)
    t_lower_min=1.85,      # ... at any tempo
    t_lift_min=1.30,       # lifting at any tempo
    t_hold=0.30,           # the box stands, hands still on it
    t_open=0.32,           # fingers let go, hands leave
    t_rise=1.35,           # standing up
    tempo_relaxed=0.88,    # phases are sped up to this factor to fit the clip, and if that is not
    tempo_min=0.72,        # ... enough to this one
    tempo_last=0.62,       # (the last resort)
    tempo_max=1.12,        # ... or slowed down to this one
    speed_max=1.2,         # and if that is not enough, walking may be this much faster
    end_rest=1.0,          # standing still at the end of the clip, at least [s]
    step_back=0.20,        # after standing up the person steps back this far from the box [m]
    # --- gait under load
    carry_stride=1.40,     # stride = carry_stride - carry_stride_kg * mass
    carry_stride_kg=0.018,
    carry_T=1.05,          # gait cycle = carry_T + carry_T_kg * mass
    carry_T_kg=0.005,
    carry_turn_swing=0.42,
    carry_turn_ds=0.16,
)


def _follow(b, p, target, heading, speed, stance=None, avoid=None):
    """Append the steps of the cheapest route from where the plan stands to (target, heading)."""
    stance = stance or {}
    for _ in range(4):
        _, acts = plan_route(b.center(), b.heading(), target, heading, speed=speed, avoid=avoid)
        if not acts:
            break
        if acts[0][0] == "turn":
            # a turn on the spot moves the feet a little: the rest is planned from where they end up
            b.wait(p["turn_pause"])
            b.turn(acts[0][1], stance=stance if len(acts) == 1 else None)
            continue
        for i, a in enumerate(acts):
            last = i == len(acts) - 1
            if a[0] == "turn":
                b.wait(p["turn_pause"])
                b.turn(a[1], stance=stance if last else None)
            elif a[0] == "step":
                b.reposition(a[1], b.heading(), stance.get("half_width"), stance.get("toe_out"))
            else:
                c, h = b.center(), (b.heading() if a[3] is None else a[3])
                feet = WalkLine(c, h, a[1], sigma=p["feet_sigma"])
                line = WalkLine(c, h, a[1], sigma=p["line_sigma"])
                gait = b.p
                b.p = dict(gait, sharp_turn=9.0)     # the arcs of a route are bends, never corners
                b.walk(feet, line, stop=True, first=a[2], stance=stance if last else None)
                b.p = gait
        break
    miss = float(np.linalg.norm(b.center() - np.asarray(target, dtype=float)))
    if miss > 0.08:
        print("warning: the route ends %.2f m from where the person should stand" % miss)


class Script:
    """Plan, event times and how the box is held."""

    def __init__(self, plan, ev, box, hold, tempo):
        self.plan, self.ev, self.box, self.hold, self.tempo = plan, ev, box, hold, tempo


def carry_gait(p, q, mass):
    """Gait parameters under a load."""
    g = dict(p)
    g["stride"] = q["carry_stride"] - q["carry_stride_kg"] * mass
    g["T"] = q["carry_T"] + q["carry_T_kg"] * mass
    g["turn_swing"] = q["carry_turn_swing"]
    g["turn_ds"] = q["carry_turn_ds"]
    return g


def _build(task, p, q, tempo, end_steps=True, speed=1.0):
    box = Box.from_task(task)
    st = task.get("start", {})
    start = np.asarray(st.get("position", [0.0, 0.0]), dtype=float)
    h0 = math.radians(float(st.get("heading_deg", 0.0)))
    hold = choose_holds(box, start, h0, q["standoff"], q)
    stance = dict(half_width=q["stance_half_width"], toe_out=q["stance_toe_out"],
                  stagger=q["stance_stagger"])
    f = tempo
    hurry = dict(stride=p["stride"] * speed ** 0.7, T=p["T"] / speed ** 0.3)
    b = PlanBuilder(p)
    b.stand(start, h0)
    b.wait(max(0.6, p["start_wait"] * min(f, 1.0)))
    b.p = dict(p, **hurry)
    _follow(b, p, hold["s_pick"], hold["h_pick"], q["approach_speed"], stance, avoid=box)
    b.p = p
    ev = dict(t0=max(0.6, p["start_wait"] * min(f, 1.0)), stop1=b.t)
    ev["down0"] = ev["stop1"] + q["t_settle"] * f
    ev["bottom"] = ev["down0"] + q["t_down"] * f
    ev["contact"] = ev["bottom"] - 0.12 * f
    ev["load0"] = ev["bottom"] + q["t_grip"] * f
    ev["lift0"] = ev["load0"] + q["t_load"] * f
    ev["lift1"] = ev["lift0"] + max(q["t_lift_min"], (q["t_lift"] + q["t_lift_kg"] * box.mass) * f)
    ev["walk2"] = ev["lift1"] + q["t_hitch"] * f
    b.wait(ev["walk2"] - b.t)
    b.p = carry_gait(p, q, box.mass)
    b.p["stride"] *= speed ** 0.7
    b.p["T"] /= speed ** 0.3
    _follow(b, p, hold["s_put"], hold["h_put"], q["carry_speed"], stance)
    b.p = p
    ev["stop2"] = b.t
    ev["low0"] = ev["stop2"] + q["t_settle2"] * f
    ev["touch"] = ev["low0"] + max(q["t_lower_min"], q["t_lower"] * f)
    ev["open0"] = ev["touch"] + q["t_hold"] * f
    ev["away"] = ev["open0"] + q["t_open"] * f
    ev["rise0"] = ev["away"] + 0.10 * f
    ev["rise1"] = ev["rise0"] + q["t_rise"] * f
    ev["still"] = ev["rise1"]
    if end_steps:
        # the wide lifting stance is left with two small steps back from the box
        b.wait(ev["rise1"] + 0.15 * f - b.t)
        c = b.center() - q["step_back"] * hdir(hold["h_put"])
        b.reposition(c, hold["h_put"], first="R" if q["stance_stagger"] > 0 else "L")
        ev["still"] = b.t + 0.4
    return b, ev, box, hold


def compose(task, p, q):
    """Script for a task.  Tries the normal tempo and slows down or speeds up to fit the clip."""
    dur = int(task.get("frames", 300)) / float(task.get("fps", 30))

    def fit(end_steps, speed, t_min):
        """The tempo in [t_min, tempo_max] that uses the clip best, and the time left over."""
        tempo = 1.0
        for _ in range(6):
            b, ev, _, _ = _build(task, p, q, tempo, end_steps, speed)
            spare = dur - q["end_rest"] - ev["still"]
            phases = ev["rise1"] - ev["stop2"] + ev["walk2"] - ev["stop1"]
            new = float(np.clip(tempo * (1.0 + spare / phases), t_min, q["tempo_max"]))
            if abs(new - tempo) < 0.005:
                break
            tempo = new
        return tempo, spare

    # first choice: all of it at a relaxed tempo; then without the last steps; then quicker
    for end_steps, speed, t_min in ((True, 1.0, q["tempo_relaxed"]), (False, 1.0, q["tempo_relaxed"]),
                                    (False, 1.0, q["tempo_min"]), (False, 0.5 * (1.0 + q["speed_max"]), q["tempo_min"]),
                                    (False, q["speed_max"], q["tempo_min"]), (False, q["speed_max"], q["tempo_last"])):
        tempo, spare = fit(end_steps, speed, t_min)
        if spare > -0.05:
            break
    b, ev, box, hold = _build(task, p, q, tempo, end_steps, speed)
    if ev["still"] > dur - 0.3:
        print("warning: the job needs %.1f s but the clip lasts %.1f s" % (ev["still"] + 0.3, dur))
    return Script(b.finish(dur), ev, box, hold, tempo)
