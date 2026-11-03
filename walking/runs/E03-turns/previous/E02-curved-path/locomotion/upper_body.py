"""Spine, head and arms, for a whole clip at once.

Thorax and head orientations are specified in the world (heading, lean, small oscillations)
and distributed over the spine and neck joints, so the head stays steady while the pelvis
rotates and tilts underneath it.  In bends the thorax faces slightly ahead along the line
and the head turns towards a point about 1.6 m ahead on the line (people look where they
are going, so the head leads the body into a turn).  The arms swing opposite to the legs.
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


def upper_body(walker, t, W0, s_pel):
    """Local rotations {joint index: (n, 3, 3)} of spine, neck, head, collars, arms, wrists."""
    p = walker.p
    line = walker.line
    ph = walker.clock.phase(t)
    v = p["var"]
    n = len(t)
    out = {}
    lean = walker.lean(s_pel)

    # thorax (world): faces slightly ahead along the line, counter-rotates against the pelvis,
    # leans forward a little and into bends, small lateral lean toward the stance leg
    t_yaw = 3.2 * DEG * np.cos(2 * np.pi * (ph - 0.04))
    t_pitch = 4.0 * DEG + 0.8 * DEG * np.cos(4 * np.pi * (ph - 0.12))
    t_roll = -1.2 * DEG * np.sin(2 * np.pi * ph)
    h_tx = line.heading(s_pel + p["thorax_lead"])
    Wt = ry(h_tx + t_yaw) @ rx(t_pitch) @ rz(t_roll - p["thorax_lean"] * lean)
    rv = to_rotvec(tr(W0) @ Wt)
    for name, f in zip(("spine1", "spine2", "spine3"), (0.30, 0.35, 0.35)):
        out[IDX[name]] = from_rotvec(rv * f)

    # head: looks at the line ~1.6 m ahead (partly with the eyes, so the head turns only
    # head_gain of the way), stabilised in space, small slow drift
    here = line.pos(s_pel)
    look = line.pos(s_pel + p["look_ahead"]) - here
    gaze = h_tx + wrap(np.arctan2(look[:, 0], look[:, 1]) - h_tx)
    h_yaw = (h_tx + p["head_gain"] * (gaze - h_tx) + 0.25 * t_yaw
             + v * 1.5 * DEG * np.sin(2 * np.pi * t / 5.3 + 0.4))
    h_pitch = (7.0 * DEG - 0.6 * DEG * np.cos(4 * np.pi * (ph - 0.30))
               + v * 1.0 * DEG * np.sin(2 * np.pi * t / 3.7 + 1.3))
    h_roll = 0.3 * t_roll - p["head_lean"] * lean
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
        swing = (16.0 * DEG * fwd + 2.0 * DEG * fwd2) * amp_var
        # shoulder flexion (+ forward) in the thorax frame; arms hang with gravity, so add the
        # thorax forward lean; mean slightly behind the body line
        flex = -6.0 * DEG + swing + t_pitch
        # a bit wider when behind; the right shoulder joint of this skeleton sits 1.2 cm closer
        # to the midline, so that arm gets 1.2 deg more to mirror the left one
        abd = (11.0 + (1.2 if sign < 0 else 0.0)) * DEG - 1.5 * DEG * fwd
        col = rz(np.full(n, -sign * 5.0 * DEG)) @ ry(-sign * 3.0 * DEG * fwd)   # drop + protract
        out[IDX[side + "_collar"]] = col
        d = mv(rx(-flex) @ rz(sign * abd), down)                                # wanted arm axis
        base = rz(-sign * 90.0 * DEG)                    # T-pose -> arm down, palm medial
        Q = rot_between(np.broadcast_to(base @ ARM_REST[side], (n, 3)), d) @ base
        Q = axis_angle(d, np.full(n, sign * 14.0 * DEG)) @ Q    # humeral internal rotation
        out[IDX[side + "_shoulder"]] = tr(col) @ Q
        # elbow: flexion peaks just after the most forward arm position
        fwd_e = np.cos(2 * np.pi * (phs - 0.60))
        el = (22.0 * DEG + 12.0 * DEG * fwd_e) * (0.5 + 0.5 * amp_var)
        out[IDX[side + "_elbow"]] = ry(-sign * el)
        # wrist: slight flexion with a passive lag
        wr = 7.0 * DEG + 4.0 * DEG * np.cos(2 * np.pi * (phs - 0.72))
        out[IDX[side + "_wrist"]] = rz(-sign * wr) @ ry(np.full(n, -sign * 3.0 * DEG))
    return out
