"""Task files -> footstep plan -> motion.

A task (see task.json) gives fps, number of frames, the start pose and state, the end state
(and for a standing end the end pose) and a path (segments or a polyline).

Supported:
  start "standing": stand at the start pose for start_wait seconds, then start walking.
  start "walking" : the person is already walking: the plan starts from standing 6 m behind
                    the start on the backward extension of the path, and is then shifted in
                    time so that the centre of mass passes the start position at t = 0.
  end "standing"  : stop with the centre of mass at the end of the path, then turn on the
                    spot to the end heading (if one is given) and stand.
  end "walking"   : keep walking past the end of the clip.
Obstacles (upright boxes): gaps on the path too narrow to walk through facing forward are
squeezed through sideways (obstacles.find_passages, plan._passage_layout).  Other obstacles
are not avoided (a warning is printed if the path runs through one).
"""
import json
import math
import sys

import numpy as np

from .body import Body, calibrate
from .gait import make_params
from .obstacles import boxes_of, find_passages
from .path import WalkLine
from .plan import PlanBuilder
from .rotations import DEG, wrap

S_PRE = 6.0      # an already-walking person starts this far behind the start position [m]


def load_task(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _compose(task, p, lines, offset, warn=True):
    line, body_line, passages = lines
    fps = int(task.get("fps", 30))
    dur = int(task.get("frames", 300)) / fps
    start, end = task.get("start", {}), task.get("end", {})
    stop = end.get("state", "walking") == "standing"
    b = PlanBuilder(p)
    if start.get("state", "walking") == "standing":
        pos = np.asarray(start.get("position", [0.0, 0.0]), dtype=float)
        b.stand(pos, math.radians(float(start.get("heading_deg", 0.0))))
        b.wait(p["start_wait"])
    else:
        b.t = offset
        b.stand(line.pos(-S_PRE), float(line.heading(-S_PRE)))
    b.walk(line, body_line, stop=stop, t_end=dur + 3.0, passages=passages)
    if stop and "heading_deg" in end:
        dh = float(wrap(math.radians(float(end["heading_deg"])) - b.heading()))
        if abs(dh) > 3.0 * DEG:
            if abs(abs(dh) - math.pi) < 10.0 * DEG:
                # turning round: either way is fine; turn towards the side of the foot that
                # was put down last, so that it is the one that steps first
                dh = abs(dh) if b.steps[-1].side == "L" else -abs(dh)
            b.wait(p["turn_pause"])
            b.turn(dh)
    plan = b.finish(dur)
    if warn and stop and plan.t_last > dur - 0.5:
        print("warning: the plan needs %.1f s but the clip lasts %.1f s" % (plan.t_last + 0.5, dur),
              file=sys.stderr)
    return plan


def build_plan(task, p, lines):
    """Footstep plan for a task (see module docstring)."""
    dur = int(task.get("frames", 300)) / int(task.get("fps", 30))
    if task.get("start", {}).get("state", "walking") == "standing":
        return _compose(task, p, lines, 0.0)
    plan = _compose(task, p, lines, 0.0, warn=False)
    body = Body(plan, (0.0, dur), solve_height=False)
    G = body.grid
    walk = next(e for e in plan.heading_prog if e[1] == "line")
    body_line, tk, sk = walk[2]
    # (the clip starts while walking normally, before any passage: the projection is valid)
    s = body_line.project(G["com"], np.interp(G["t"], tk, sk)) + p["c_walk"]   # pelvis, not COM
    i = int(np.argmax(s >= 0.0))
    tau = float(np.interp(0.0, s[i - 1:i + 1], G["t"][i - 1:i + 1]))
    return _compose(task, p, lines, -tau)


def make_lines(task, p, warn=True):
    """The feet line (where footprints go: close to the marked path), the body line
    (smoother: gives the pelvis heading) and the passages (narrow gaps) on the feet line."""
    feet = WalkLine.from_task(task, sigma=p["feet_sigma"], fillet_frac=p["feet_fillet_frac"])
    body = WalkLine.from_task(task, sigma=p["line_sigma"], fillet_frac=p["fillet_frac"])
    tol = float(task.get("path", {}).get("tolerance_m", 0.15))
    passages = find_passages(feet, boxes_of(task), p, (-S_PRE + 1.0, feet.s[-1] - 1.0), tol, warn)
    return feet, body, passages


def generate_motion(task, params=None):
    """Return a dict with fps, transl, global_orient and body_pose for the task (and the Body
    object under 'body' for inspection)."""
    fps = int(task.get("fps", 30))
    frames = int(task.get("frames", 300))
    p = make_params(params)
    if p["c_walk"] is None or p["roll0"] is None:
        p["c_walk"], p["roll0"] = calibrate(params)
    lines = make_lines(task, p)
    plan = build_plan(task, p, lines)
    body = Body(plan, (-2.5, frames / fps + 2.5))
    motion = body.generate(frames, fps)
    motion["body"] = body
    return motion


def save_motion(path, motion):
    np.savez(path, fps=np.int64(motion["fps"]),
             transl=np.asarray(motion["transl"], dtype=np.float32),
             global_orient=np.asarray(motion["global_orient"], dtype=np.float32),
             body_pose=np.asarray(motion["body_pose"], dtype=np.float32))
