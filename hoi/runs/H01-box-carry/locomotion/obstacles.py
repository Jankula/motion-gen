"""Obstacles: upright boxes standing on the floor, and the gaps they leave on the walking line.

A task obstacle has a centre [x, z], a size [extent along x, height, extent along z] before
rotation and yaw_deg, a rotation about the vertical axis (positive turns +z towards +x, like
a heading).

find_passages() walks along the feet line and measures, at every point, the free lateral
interval around the line: from the nearest obstacle on its left to the nearest on its right.
Where that interval is narrower than the body seen from the front with swinging arms, plus
gap_margin on either side, the stretch becomes a Passage:

  * 'shoulder' mode, if holding the arms still and turning the shoulders by at most
    shoulder_turn_max makes the body narrow enough, and the hips fit.  Seen from above, the
    shoulders with the arms are taken as a block of half-width a = body_half_width_still and
    half-thickness c = shoulder_half_thickness, the chest as a front point at half-depth
    b = body_half_depth, e = chest_half_width to the side; turned by beta the body reaches
    max(a cos beta + c sin beta, b sin beta + e cos beta) across the gap, plus walk_sway
    for the side-to-side sway of walking (calibrated with evaluate.py on test gaps);
  * 'side' mode otherwise: the body turns fully sideways and side-steps through
    (plan._passage_layout).  Gaps narrower than the body's depth are reported as impassable
    (and still attempted).

Obstacles that block the line itself, or that leave room on one side only, are reported but
not avoided.
"""
import math
import sys

import numpy as np

from .plan import Passage


class Box:
    def __init__(self, center, size, yaw_deg=0.0, label=""):
        self.c = np.asarray(center, dtype=float)
        self.hx = 0.5 * float(size[0])
        self.height = float(size[1])
        self.hz = 0.5 * float(size[2])
        self.yaw = math.radians(float(yaw_deg))
        self.label = label

    @classmethod
    def from_task(cls, ob):
        return cls(ob["center"], ob["size"], ob.get("yaw_deg", 0.0), ob.get("label", ""))

    def local(self, xz):
        """Floor points (..., 2) in the box frame."""
        d = np.asarray(xz, dtype=float) - self.c
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        return np.stack([c * d[..., 0] - s * d[..., 1], s * d[..., 0] + c * d[..., 1]], -1)

    def floor_distance(self, xz):
        """Signed distance (..., ) from floor points to the box footprint (negative inside)."""
        q = np.abs(self.local(xz)) - np.array([self.hx, self.hz])
        outside = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
        return outside + np.minimum(np.max(q, -1), 0.0)

    def distance(self, pts, floor_y):
        """Signed distance from 3D points (..., 3) to the box (negative inside)."""
        pts = np.asarray(pts, dtype=float)
        loc = self.local(pts[..., [0, 2]])
        y = pts[..., 1] - floor_y - 0.5 * self.height
        q = np.stack([np.abs(loc[..., 0]) - self.hx, np.abs(y) - 0.5 * self.height,
                      np.abs(loc[..., 1]) - self.hz], -1)
        outside = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
        return outside + np.minimum(np.max(q, -1), 0.0)


def boxes_of(task):
    return [Box.from_task(ob) for ob in task.get("obstacles", []) or []]


def corridor(line, boxes, s, half=1.5, dl=0.005):
    """Free lateral interval around the line at arc lengths s: (left, right, blocked), where
    left > 0 is the distance to the nearest obstacle on the left of the line, right < 0 that on
    its right (+-half if there is none), and blocked marks points where the line itself is
    inside an obstacle."""
    s = np.asarray(s, dtype=float)
    l = np.arange(-half, half + 0.5 * dl, dl)
    pts = line.pos(s)[:, None, :] + l[None, :, None] * line.normal(s)[:, None, :]
    occ = np.zeros(pts.shape[:2], dtype=bool)
    for b in boxes:
        occ |= b.floor_distance(pts) < 0.0
    i0 = int(np.argmin(np.abs(l)))
    left = np.full(len(s), half)
    right = np.full(len(s), -half)
    for i in range(len(s)):
        lo = np.nonzero(occ[i, i0:])[0]
        if len(lo):
            left[i] = l[i0 + lo[0]]
        ro = np.nonzero(occ[i, :i0 + 1])[0]
        if len(ro):
            right[i] = l[ro[-1]]
    return left, right, occ[:, i0]


def shoulder_turn(width, p):
    """Shoulder turn (radians) that lets a walker with still arms through a gap of this free
    width with gap_margin on either side, or None if walking through is not possible."""
    r = 0.5 * width - p["gap_margin"] - p["walk_sway"]
    if 0.5 * width < p["hip_half_width"] + p["walk_sway"] + 0.5 * p["gap_margin"]:
        return None
    a, c = p["body_half_width_still"], p["shoulder_half_thickness"]
    b, e = p["body_half_depth"], p["chest_half_width"]
    for beta in np.radians(np.arange(0.0, math.degrees(p["shoulder_turn_max"]) + 0.5, 1.0)):
        if max(a * math.cos(beta) + c * math.sin(beta), b * math.sin(beta) + e * math.cos(beta)) <= r:
            return float(beta)
    return None


def find_passages(line, boxes, p, s_range, tol=0.15, warn=True):
    """Narrow gaps on the line between s_range[0] and s_range[1] -> [Passage]."""
    if not boxes:
        return []
    s = np.arange(s_range[0], s_range[1], 0.01)
    left, right, blocked = corridor(line, boxes, s)
    width = left - right
    narrow = (width < 2.0 * (p["body_half_width"] + p["gap_margin"])) & ~blocked
    out = []
    i = 0
    while i < len(s):
        if not narrow[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(s) and narrow[j + 1]:
            j += 1
        seg = slice(i, j + 1)
        w = float(width[seg].min())
        center = float(np.median(0.5 * (left[seg] + right[seg])))
        if abs(center) > tol:
            if warn:
                print("warning: the gap at s = %.2f is %.2f m off the path; the body keeps within "
                      "the path tolerance" % (s[i], center), file=sys.stderr)
            center = math.copysign(tol, center)
        if warn and w < 2.0 * p["body_half_depth"]:
            print("warning: the gap at s = %.2f is only %.2f m wide, narrower than the body's depth"
                  % (s[i], w), file=sys.stderr)
        # walking through keeps to the line (it is not shifted towards an off-centre gap), so
        # the room that counts is twice the smaller distance from the line to an obstacle
        w_line = 2.0 * float(np.minimum(left[seg], -right[seg]).min())
        beta = shoulder_turn(w_line, p)
        mode = "side" if beta is None else "shoulder"
        out.append(Passage(s[i], s[j], center, w, p["squeeze_turn"], mode, beta or 0.0))
        i = j + 1
    if warn and blocked.any():
        sb = s[blocked]
        print("warning: the path runs through an obstacle at s = %.2f..%.2f; this is not avoided"
              % (sb.min(), sb.max()), file=sys.stderr)
    return out
