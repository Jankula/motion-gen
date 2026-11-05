"""Routes on the floor: how to get from one standing pose to another.

A route is a list of actions for the footstep planner:
    ("turn", angle)                  turn on the spot (radians, positive = to the left)
    ("walk", segments, first, aim)   walk along straight pieces and arcs (see locomotion.path),
                                     starting along heading aim (None: the current heading)
    ("step", point)                  two small steps to a point close by

Candidates are Dubins curves (arc, straight, arc: the shortest path with a limited curvature
between two poses), optionally after a turn on the spot, and "turn, walk straight, turn".  The
cheapest one in time wins; turning on the spot costs more than walking a bend.
"""
import math

import numpy as np

from locomotion.path import hdir, heading_of, lnorm
from locomotion.rotations import wrap

TWO_PI = 2.0 * math.pi


def _advance(p, h, turn, r):
    """Pose after an arc of radius r turning by angle turn (positive = left)."""
    c = p + np.sign(turn) * r * lnorm(h)
    h2 = h + turn
    return c - np.sign(turn) * r * lnorm(h2), h2


def dubins(p0, h0, p1, h1, r):
    """All arc-straight-arc curves from pose (p0, h0) to (p1, h1): list of (length, turn1, straight,
    turn2) with the turns signed (positive = left)."""
    p0, p1 = np.asarray(p0, dtype=float), np.asarray(p1, dtype=float)
    out = []
    for a in (1.0, -1.0):
        for b in (1.0, -1.0):
            c0 = p0 + a * r * lnorm(h0)
            c1 = p1 + b * r * lnorm(h1)
            d = c1 - c0
            D = float(np.linalg.norm(d))
            if a == b:
                hs_list, L = [float(heading_of(d))] if D > 1e-9 else [h0], D
            else:
                if D < 2.0 * r:
                    continue
                off = math.asin(2.0 * r / D)
                hs_list, L = [float(heading_of(d)) + off, float(heading_of(d)) - off], math.sqrt(D * D - 4 * r * r)
            for hs in hs_list:
                t1 = (hs - h0) % TWO_PI if a > 0 else -((h0 - hs) % TWO_PI)
                t2 = (h1 - hs) % TWO_PI if b > 0 else -((hs - h1) % TWO_PI)
                if abs(t1) > TWO_PI - 1e-6:
                    t1 = 0.0
                if abs(t2) > TWO_PI - 1e-6:
                    t2 = 0.0
                q, h = (_advance(p0, h0, t1, r) if abs(t1) > 1e-9 else (p0, h0))
                q = q + L * hdir(h)
                q, h = (_advance(q, h, t2, r) if abs(t2) > 1e-9 else (q, h))
                if np.linalg.norm(q - p1) < 1e-6:
                    out.append((r * (abs(t1) + abs(t2)) + L, t1, L, t2))
    return out


def _segments(t1, L, t2, r, lead0=0.0, lead1=0.0):
    seg = []
    if lead0 > 1e-6:
        seg.append({"type": "straight", "length": float(lead0)})
    if abs(t1) > 1e-3:
        seg.append({"type": "arc", "radius": float(r), "turn_deg": math.degrees(t1)})
    if L > 1e-3:
        seg.append({"type": "straight", "length": float(L)})
    if abs(t2) > 1e-3:
        seg.append({"type": "arc", "radius": float(r), "turn_deg": math.degrees(t2)})
    if lead1 > 1e-6:
        seg.append({"type": "straight", "length": float(lead1)})
    return seg


def _hits(p0, h0, acts, box, margin=0.30):
    """Does a route pass closer than margin to the box (at its start pose)?"""
    p, h = np.asarray(p0, dtype=float), float(h0)
    pts = []
    for a in acts:
        if a[0] == "turn":
            h += a[1]
            continue
        if a[0] == "step":
            continue
        h = h if a[3] is None else a[3]
        for seg in a[1]:
            if seg["type"] == "straight":
                n = max(2, int(seg["length"] / 0.1))
                pts += [p + hdir(h) * seg["length"] * i / n for i in range(n)]
                p = p + hdir(h) * seg["length"]
            else:
                turn = math.radians(seg["turn_deg"])
                n = max(2, int(abs(turn) * seg["radius"] / 0.1))
                for i in range(n):
                    q, _ = _advance(p, h, turn * (i + 1) / n, seg["radius"])
                    pts.append(q)
                p, h = _advance(p, h, turn, seg["radius"])
    if not pts:
        return False
    d = np.array(pts) - box.start_xz
    x = np.abs(d @ lnorm(box.start_yaw))        # along the box's own x axis
    z = np.abs(d @ hdir(box.start_yaw))         # along its own z axis
    # (the stance point itself lies a standoff from the box, a little inside the margin)
    near = 0.18
    return bool(np.any((x < 0.5 * box.sx + near) & (z < 0.5 * box.sz + near)))


def plan_route(p0, h0, p1, h1, speed=1.0, radius=1.4, lead_in=0.5, lead_out=0.1,
               turn_rate=1.0, turn_cost=1.0, turn_min=0.06, avoid=None):
    """Cheapest route from standing pose (p0, h0) to (p1, h1).  Returns (time estimate, actions).

    lead_in: the route ends with this much straight walking, so that the person arrives lined up.
    turn_rate [rad/s], turn_cost [s]: how long a turn on the spot takes.
    Headings closer than turn_min need no turn.
    avoid: a Box standing at its start position; routes through it cost a lot."""
    p0, p1 = np.asarray(p0, dtype=float), np.asarray(p1, dtype=float)
    d = p1 - p0
    dist = float(np.linalg.norm(d))
    cands = []

    def turn_time(a):
        return 0.0 if abs(a) < turn_min else turn_cost + abs(a) / turn_rate

    def add_dubins(h_start, pre):
        for r in (radius, 0.8 * radius):
            q0 = p0 + lead_out * hdir(h_start)
            q1 = p1 - lead_in * hdir(h1)
            for L, t1, S, t2 in dubins(q0, h_start, q1, h1, r):
                if abs(t1) + abs(t2) > 1.25 * math.pi:
                    continue                      # no loops
                total = L + lead_in + lead_out
                cost = total / speed + 0.25 * (abs(t1) + abs(t2)) + turn_time(pre) + 0.25 * (r < radius)
                segs = _segments(t1, S, t2, r, lead_out, lead_in)
                acts = ([("turn", pre)] if abs(pre) >= turn_min else [])
                acts = acts + [("walk", segs, "L" if t1 + t2 > 0 else "R", None)]
                cands.append((cost, len(cands), acts))

    add_dubins(h0, 0.0)
    if dist > 0.3:
        hd = float(heading_of(d))
        a1 = float(wrap(hd - h0))
        a2 = float(wrap(h1 - hd))
        if abs(a1) >= turn_min:
            add_dubins(h0 + a1, a1)
        # A straight walk always aims exactly at the target: a heading a little off is no reason
        # for a turn on the spot, but walking on along it would miss the target (15 cm in 3 m at
        # 3 degrees).
        acts = [("turn", a1)] if abs(a1) >= turn_min else []
        acts = acts + [("walk", [{"type": "straight", "length": dist}], "L" if a1 > 0 else "R", hd)]
        if abs(a2) >= turn_min:
            acts = acts + [("turn", a2)]
        cands.append((dist / speed + turn_time(a1) + turn_time(a2), len(cands), acts))
    else:
        # hardly any distance: a turn on the spot if needed, then small steps to the place
        a2 = float(wrap(h1 - h0))
        acts = [("turn", a2)] if abs(a2) >= turn_min else []
        if dist > 0.03:
            acts = acts + [("step", p1)]
        cands.append((turn_time(a2) + 1.0, len(cands), acts))
    if avoid is not None:
        cands = [(c + (30.0 if _hits(p0, h0, a, avoid) else 0.0), i, a) for c, i, a in cands]
    cost, _, acts = min(cands, key=lambda c: (c[0], c[1]))
    return cost, acts


def choose_holds(box, start_xz, start_heading, standoff, p):
    """Which face to walk up to and from which side to put the box down.

    Every combination of k (heading at the pick-up is box yaw + k * 90 deg) and m (at the target the
    person stands on one or the other side: the box looks the same turned by 180 deg) is priced by
    the time of the two routes and by how awkward that grip is.  Returns a dict with k, the two
    headings, the two stance points, the width and the depth of the box as held."""
    best = None
    for k in range(4):
        h_pick = box.start_yaw + k * 0.5 * math.pi
        width, depth = box.extents(k)
        # (arms holding a narrow box pass in front of the knees, not beside them)
        off = standoff + float(np.clip(0.5 * (0.4 - width), 0.0, 0.06))
        s_pick = box.stance_point(box.start_xz, h_pick, depth, off)
        c1, _ = plan_route(start_xz, start_heading, s_pick, h_pick, speed=p["approach_speed"], avoid=box)
        # people walk up to the side of the box that faces them
        c1 += 2.0 * abs(float(wrap(h_pick - float(heading_of(box.start_xz - np.asarray(start_xz, dtype=float)))))) / (0.5 * math.pi)
        for m in range(2):
            h_put = box.target_yaw + k * 0.5 * math.pi + m * math.pi
            s_put = box.stance_point(box.target_xz, h_put, depth, off)
            c2, _ = plan_route(s_pick, h_pick, s_put, h_put, speed=p["carry_speed"])
            # a box wider than it is deep sits closer to the body, a very wide one is a long reach
            awkward = (0.5 * max(0.0, depth - width) / 0.1 + 2.0 * max(0.0, width - 0.6) / 0.1
                       + 2.0 * max(0.0, 0.25 - width) / 0.1)
            cost = c1 + c2 + awkward
            if best is None or cost < best["cost"] - 1e-6:
                best = dict(cost=cost, k=k, m=m, h_pick=h_pick, h_put=h_put, s_pick=s_pick, s_put=s_put,
                            width=width, depth=depth)
    return best
