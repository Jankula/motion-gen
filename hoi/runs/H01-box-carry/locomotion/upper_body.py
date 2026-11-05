"""Spine, head and arms, for a whole clip at once.

Thorax and head orientations are specified in the world (heading, lean, small oscillations)
and distributed over the spine and neck joints, so the head stays steady while the pelvis
rotates and tilts underneath it.

Heading order.  People turn the eyes and head first, then the trunk, then the pelvis and
feet.  The thorax faces where the pelvis heading program will point thorax_lead_t seconds
later, and the head turns towards where it will point gaze_lead_t seconds later (taking
head_gain of that direction; the eyes do the rest).  This works the same way for a bend in
the path, a corner and a turn on the spot.

All gait oscillations (thorax counter-rotation, arm swing, head bob) are scaled by the step
size envelope g, so they grow over the first steps of a walk and die away when stopping.
When standing there is a slow breathing movement of the chest and a slight drift of the head.
"""
import numpy as np

from .rotations import (DEG, axis_angle, from_rotvec, mv, rot_between, rx, ry, rz, to_rotvec,
                        tr, wrap)
from .skeleton import IDX, J

# rest direction of each arm (shoulder -> wrist), the axis of the visible arm
ARM_REST = {}
for _s in ("left", "right"):
    _v = J[IDX[_s + "_wrist"]] - J[IDX[_s + "_shoulder"]]
    ARM_REST[_s] = _v / np.linalg.norm(_v)


def upper_body(body, t, W0):
    """Local rotations {joint index: (n, 3, 3)} of spine, neck, head, collars, arms, wrists."""
    p = body.p
    t = np.asarray(t, dtype=float)
    ph, g, e = body.envelopes(t)
    gc = np.minimum(g, 1.0)
    v = p["var"]
    n = len(t)
    out = {}
    lean_lat, lean_fwd = body.lean(t)
    q = body.plan.side_env(t)          # 1 while squeezing sideways through a gap
    still = body.plan.arm_still(t)     # 1 while the arms are held still (narrow gaps)

    # thorax (world): faces slightly ahead of the pelvis heading, counter-rotates against the
    # pelvis, leans forward a little (more when walking, and while speeding up), leans into
    # bends, small lateral lean toward the stance leg; breathing when standing.  Sideways in a
    # gap the trunk is held upright (no forward lean).
    post = body.plan.posture           # optional posture program (bending down, carrying a load)
    osc = 1.0 if post is None else 1.0 - post.loaded(t) * p["load_trunk_calm"]
    t_yaw = 3.2 * DEG * g * np.cos(2 * np.pi * (ph - 0.04)) * osc
    breath = (1.0 - gc) * 0.5 * DEG * np.sin(2 * np.pi * t / 4.3 + 0.3)
    t_pitch = ((1.5 * (1.0 - 0.7 * q) + 2.5 * gc) * DEG + 0.8 * DEG * g * np.cos(4 * np.pi * (ph - 0.12))
               + 0.4 * np.maximum(lean_fwd, 0.0) + breath)
    t_roll = -1.2 * DEG * e * (0.3 + 0.7 * gc) * np.sin(2 * np.pi * ph)
    t_tx = t + p["thorax_lead_t"]
    h_tx = body.psi(t_tx) + body.plan.thorax_offset(t_tx)   # (+ shoulder turn in a narrow gap)
    if post is not None:
        t_pitch = t_pitch + post.thorax_pitch(t)
        h_tx = h_tx + post.thorax_yaw(t)
        t_roll = t_roll + post.thorax_roll(t)
    Wt = ry(h_tx + t_yaw) @ rx(t_pitch) @ rz(t_roll - p["thorax_lean"] * lean_lat)
    rv = to_rotvec(tr(W0) @ Wt)
    for name, f in zip(("spine1", "spine2", "spine3"), (0.30, 0.35, 0.35)):
        out[IDX[name]] = from_rotvec(rv * f)

    # head: turns toward where the body is about to face, stabilised in space, slow drift.
    # When the body is turned sideways (a passage) the gaze stays on the direction of travel,
    # i.e. the heading offset is taken back out of it; the neck rotation is softly limited.
    t_g = t + p["gaze_lead_t"]
    gaze = (body.psi(t_g) - p["side_gaze"] * body.plan.heading_offset(t_g)
            - body.plan.thorax_offset(t_g))
    h_rel = _soft_limit(p["head_gain"] * wrap(gaze - h_tx), p["head_yaw_max"])
    h_yaw = (h_tx + h_rel + 0.25 * t_yaw
             + v * 1.5 * DEG * np.sin(2 * np.pi * t / 5.3 + 0.4))
    h_pitch = ((4.0 + 3.0 * gc + 5.0 * q) * DEG - 0.6 * DEG * g * np.cos(4 * np.pi * (ph - 0.30))
               + v * 1.0 * DEG * np.sin(2 * np.pi * t / 3.7 + 1.3))   # (looks down a little in a gap)
    h_roll = 0.3 * t_roll - p["head_lean"] * lean_lat
    Wh = ry(h_yaw) @ rx(h_pitch) @ rz(h_roll)
    rvh = to_rotvec(tr(Wt) @ Wh)
    out[IDX["neck"]] = from_rotvec(rvh * 0.55)
    out[IDX["head"]] = from_rotvec(rvh * 0.45)

    # arms.  The visible arm is the shoulder->wrist line of the rest mesh (the elbow joints of
    # this skeleton sit off that line, differently on the two sides), so the shoulder rotation
    # aligns that rest vector with the wanted hang direction.  In a bend the effective gravity
    # (gravity plus centrifugal) tilts with the body lean, so the arms keep hanging the same way
    # relative to the thorax.
    down = np.array([0.0, -1.0, 0.0])
    for side, sign, off in (("left", 1.0, 0.0), ("right", -1.0, 0.5)):
        phs = ph - off
        amp_var = 1.0 + v * 0.06 * np.sin(2 * np.pi * t / 4.7 + (0.9 if sign > 0 else 2.6))
        fwd = np.cos(2 * np.pi * (phs - 0.55))           # +1 = arm most forward
        fwd2 = np.cos(4 * np.pi * (phs - 0.55))
        swing = (16.0 * DEG * fwd + 2.0 * DEG * fwd2) * amp_var * g * (1.0 - 0.85 * still)
        # shoulder flexion (+ forward) in the thorax frame; arms hang with gravity, so add the
        # thorax forward lean; mean slightly behind the body line when walking
        flex = -(1.0 + 5.0 * gc) * DEG + swing + t_pitch
        # a bit wider when behind; the right shoulder joint of this skeleton sits 1.2 cm closer
        # to the midline, so that arm gets 1.2 deg more to mirror the left one
        abd = (((9.0 + p["arm_abd_extra"] + 2.0 * gc) * (1.0 - 0.45 * np.maximum(q, still)) + (1.2 if sign < 0 else 0.0)) * DEG
               - 1.5 * DEG * g * fwd)   # arms closer to the body in a gap
        if post is not None:
            abd = abd + post.arm_out(t)
        col = rz(np.full(n, -sign * 5.0 * DEG)) @ ry(-sign * 3.0 * DEG * g * fwd)   # drop + protract
        out[IDX[side + "_collar"]] = col
        d = mv(rx(-flex) @ rz(sign * abd), down)                                     # wanted arm axis
        base = rz(-sign * 90.0 * DEG)                    # T-pose -> arm down, palm medial
        Q = rot_between(np.broadcast_to(base @ ARM_REST[side], (n, 3)), d) @ base
        Q = axis_angle(d, np.full(n, sign * 14.0 * DEG)) @ Q    # humeral internal rotation
        out[IDX[side + "_shoulder"]] = tr(col) @ Q
        # elbow: relaxed bend; when walking, flexion peaks just after the most forward position
        fwd_e = np.cos(2 * np.pi * (phs - 0.60))
        el = (((12.0 + 10.0 * gc + 8.0 * q) * DEG + 12.0 * DEG * g * fwd_e * (1.0 - 0.85 * still))
              * (0.5 + 0.5 * amp_var))
        out[IDX[side + "_elbow"]] = ry(-sign * el)
        # wrist: slight flexion with a passive lag
        wr = 7.0 * DEG + 4.0 * DEG * g * np.cos(2 * np.pi * (phs - 0.72))
        out[IDX[side + "_wrist"]] = rz(-sign * wr) @ ry(np.full(n, -sign * 3.0 * DEG))
    return out


def _soft_limit(x, m):
    """Identity for |x| < 0.6 m, then a smooth approach to +-m."""
    a = np.abs(x)
    k = 0.6 * m
    return np.sign(x) * np.where(a < k, a, k + (m - k) * np.tanh((a - k) / (m - k)))
