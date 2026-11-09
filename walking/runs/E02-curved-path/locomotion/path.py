"""The walking line: a smooth, arc-length parametrised curve on the floor that the pelvis follows.

Floor coordinates are (x, z) in metres.  A heading h (radians) means the direction
(sin h, cos h): 0 faces +Z, +90 deg faces +X, turning left increases the heading.  The left
normal of heading h is (cos h, -sin h).

The marked path of a task (straight pieces and arcs, or a polyline) has curvature that jumps
where pieces meet.  A walker cannot change its rate of turning instantly, so the line actually
walked is the marked path smoothed with a Gaussian along its length (sigma ~0.3 m): heading
rate then ramps up and down over about a metre, while the line stays within a few
centimetres of the marked path.  The line is extended straight backwards before the start
(the person is already walking) and straight forwards after the end.
"""
import numpy as np
from scipy.ndimage import gaussian_filter1d

DS = 0.005  # sampling step along the line [m]


def _heading_dir(h):
    return np.stack([np.sin(h), np.cos(h)], -1)


def polyline_to_segments(points, tol=0.15, r_pref=2.0):
    """Turn a polyline with corners into straight pieces joined by fillet arcs.

    Each corner is rounded with the largest radius (at most r_pref) that keeps the line
    within 0.5 * tol of the polyline and uses at most half of each adjacent piece.  (The arc
    midpoint of a fillet of radius r for a turn phi is r (1 - cos(phi / 2)) from both legs.)
    Returns (start_xz, start_heading, segments)."""
    pts = np.asarray(points, dtype=float)
    d = np.diff(pts, axis=0)
    lens = np.linalg.norm(d, axis=1)
    keep = lens > 1e-9
    pts = np.concatenate([pts[:1], pts[1:][keep]])
    d = np.diff(pts, axis=0)
    lens = np.linalg.norm(d, axis=1)
    heads = np.arctan2(d[:, 0], d[:, 1])
    n = len(lens)
    turns = np.zeros(n + 1)
    tan_len = np.zeros(n + 1)
    radius = np.zeros(n + 1)
    for i in range(1, n):
        phi = (heads[i] - heads[i - 1] + np.pi) % (2 * np.pi) - np.pi
        turns[i] = phi
        if abs(phi) < 1e-6:
            continue
        half = abs(phi) / 2
        r_tol = 0.5 * tol / (1.0 - np.cos(half))
        r_len = 0.5 * min(lens[i - 1], lens[i]) / np.tan(half)
        radius[i] = min(r_pref, r_tol, r_len)
        tan_len[i] = radius[i] * np.tan(half)
    segs = []
    for i in range(n):
        L = lens[i] - tan_len[i] - tan_len[i + 1]
        if L > 1e-9:
            segs.append({"type": "straight", "length": float(L)})
        if i + 1 < n and abs(turns[i + 1]) > 1e-6:
            segs.append({"type": "arc", "radius": float(radius[i + 1]),
                         "turn_deg": float(np.degrees(turns[i + 1]))})
    return pts[0], float(heads[0]), segs


def _smooth(v, sig):
    """Gaussian smoothing (sigma in samples) with point-symmetric padding, which leaves
    straight lines exactly in place."""
    npad = int(4 * sig) + 2
    left = 2 * v[0] - v[1:npad + 1][::-1]
    right = 2 * v[-1] - v[-npad - 1:-1][::-1]
    w = np.concatenate([left, v, right])
    return gaussian_filter1d(w, sig, mode="nearest", truncate=4.0)[npad:-npad]


class WalkLine:
    """Smoothed walking line.  s = 0 is the start position; s_end is the end of the marked
    path (the line continues straight beyond it)."""

    def __init__(self, start_xz, heading0, segments, sigma=0.30, pre=8.0, post=30.0):
        lengths = [pre]
        kappas = [0.0]
        for seg in segments:
            if seg["type"] == "straight":
                lengths.append(float(seg["length"]))
                kappas.append(0.0)
            elif seg["type"] == "arc":
                r = float(seg["radius"])
                turn = np.radians(float(seg["turn_deg"]))
                lengths.append(r * abs(turn))
                kappas.append(np.sign(turn) / r)
            else:
                raise ValueError("unknown path segment type %r" % seg["type"])
        self.marked_length = float(sum(lengths[1:]))
        lengths.append(post)
        kappas.append(0.0)
        bounds = -pre + np.concatenate([[0.0], np.cumsum(lengths)])
        n = int(np.ceil((bounds[-1] - bounds[0]) / DS))
        s = -pre + np.arange(n + 1) * DS
        smid = s[:-1] + DS / 2
        seg_i = np.clip(np.searchsorted(bounds, smid, side="right") - 1, 0, len(kappas) - 1)
        kap = np.asarray(kappas)[seg_i]
        th = heading0 + np.concatenate([[0.0], np.cumsum(kap * DS)])
        thm = th[:-1] + kap * DS / 2
        xz = np.concatenate([[[0.0, 0.0]], np.cumsum(DS * _heading_dir(thm), axis=0)])
        i0 = int(round(pre / DS))
        xz += np.asarray(start_xz, dtype=float) - xz[i0]
        self.raw_s, self.raw_xz = s, xz

        # smooth, then re-parametrise by arc length (s = 0 stays at the start sample)
        if sigma > 0:
            xs = np.stack([_smooth(xz[:, 0], sigma / DS), _smooth(xz[:, 1], sigma / DS)], -1)
        else:
            xs = xz
        sl = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(xs, axis=0), axis=1))])
        sl -= sl[i0]
        su = np.arange(np.ceil(sl[0] / DS), np.floor(sl[-1] / DS) + 1) * DS
        x = np.interp(su, sl, xs[:, 0])
        z = np.interp(su, sl, xs[:, 1])
        h = np.unwrap(np.arctan2(np.gradient(x, DS), np.gradient(z, DS)))
        self.s = su
        self.xz = np.stack([x, z], -1)
        self.h = h
        self.k = np.gradient(h, DS)
        self.s_end = float(np.interp(self.marked_length, s - s[i0], sl))
        self.sigma = sigma

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_task(cls, task, sigma=0.30):
        path = task.get("path", {})
        start = task.get("start", {})
        pos = start.get("position", [0.0, 0.0])
        head = np.radians(float(start.get("heading_deg", 0.0)))
        if "segments" in path:
            return cls(pos, head, path["segments"], sigma=sigma)
        if "points" in path:
            p0, h0, segs = polyline_to_segments(path["points"], tol=path.get("tolerance_m", 0.15))
            return cls(p0, h0, segs, sigma=sigma)
        # no path given: walk straight ahead from the start pose
        return cls(pos, head, [{"type": "straight", "length": 50.0}], sigma=sigma)

    # ------------------------------------------------------------------ queries (vectorised)
    def pos(self, s):
        s = np.asarray(s, dtype=float)
        return np.stack([np.interp(s, self.s, self.xz[:, 0]), np.interp(s, self.s, self.xz[:, 1])], -1)

    def heading(self, s):
        return np.interp(np.asarray(s, dtype=float), self.s, self.h)

    def curvature(self, s):
        return np.interp(np.asarray(s, dtype=float), self.s, self.k)

    def normal(self, s):
        """Left normal (x, z)."""
        h = self.heading(s)
        return np.stack([np.cos(h), -np.sin(h)], -1)

    def field(self, values, s):
        """Interpolate an array defined on the line samples."""
        return np.interp(np.asarray(s, dtype=float), self.s, values)

    def smoothed(self, values, sigma):
        """Gaussian smoothing (sigma in metres) of an array defined on the line samples."""
        return gaussian_filter1d(values, sigma / DS, mode="nearest", truncate=4.0)
