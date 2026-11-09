"""Small curve tools: smooth piecewise paths, slow random wobble, eases.

Quintic is a path through knots at which position, velocity and acceleration are all given, so
the result has no jump in acceleration.  That matters for a hand that takes a ball over from free
flight: the hand's speed and acceleration at the moment of release are prescribed by the ball.
"""
import numpy as np

from locomotion.rotations import smootherstep


class Quintic:
    """Piecewise fifth-degree polynomial through knots (t, p, v, a).  Outside the knots it holds
    the end value."""

    def __init__(self, t, p, v=None, a=None):
        t = np.asarray(t, dtype=float)
        p = np.asarray(p, dtype=float)
        v = np.zeros_like(p) if v is None else np.asarray(v, dtype=float)
        a = np.zeros_like(p) if a is None else np.asarray(a, dtype=float)
        if np.any(np.diff(t) <= 0.0):
            raise ValueError("knot times must increase: %s" % t)
        h = np.diff(t)
        V0, V1 = v[:-1] * h, v[1:] * h
        A0, A1 = a[:-1] * h * h, a[1:] * h * h
        d = p[1:] - p[:-1] - V0 - 0.5 * A0
        dv = V1 - V0 - A0
        da = A1 - A0
        self.t, self.h, self.p = t, h, p
        self.c = np.stack([p[:-1], V0, 0.5 * A0, 10.0 * d - 4.0 * dv + 0.5 * da,
                           -15.0 * d + 7.0 * dv - da, 6.0 * d - 3.0 * dv + 0.5 * da], -1)

    def __call__(self, x, deriv=0):
        x = np.asarray(x, dtype=float)
        i = np.clip(np.searchsorted(self.t, x, side="right") - 1, 0, len(self.h) - 1)
        s = np.clip((x - self.t[i]) / self.h[i], 0.0, 1.0)
        c = self.c[i]
        if deriv == 0:
            return c[..., 0] + s * (c[..., 1] + s * (c[..., 2] + s * (c[..., 3] + s * (c[..., 4] + s * c[..., 5]))))
        inside = (x >= self.t[0]) & (x <= self.t[-1])
        if deriv == 1:
            y = c[..., 1] + s * (2 * c[..., 2] + s * (3 * c[..., 3] + s * (4 * c[..., 4] + s * 5 * c[..., 5])))
            return np.where(inside, y / self.h[i], 0.0)
        y = 2 * c[..., 2] + s * (6 * c[..., 3] + s * (12 * c[..., 4] + s * 20 * c[..., 5]))
        return np.where(inside, y / self.h[i] ** 2, 0.0)


def min_jerk(t, p, v, a):
    """Quintic through knots where only some values are prescribed.

    t, p (n,) are the knot times and positions; v and a (n,) hold the velocities and accelerations
    that are prescribed and NaN for the free ones.  The free ones are chosen so that the integral
    of the squared jerk (the rate of change of acceleration) along the whole path is as small as
    possible.  Smooth human arm movements are close to such paths.  The problem is linear, so
    one least-squares solve does it."""
    t = np.asarray(t, dtype=float)
    p = np.asarray(p, dtype=float)
    v = np.array(v, dtype=float)
    a = np.array(a, dtype=float)
    n = len(t)
    h = np.diff(t)
    s = np.array([0.04, 0.2, 0.5, 0.8, 0.96])
    wq = np.sqrt(np.array([0.12, 0.25, 0.26, 0.25, 0.12]))
    basis = np.stack([6.0 + 0.0 * s, 24.0 * s, 60.0 * s * s], -1)              # jerk per c3, c4, c5
    mix = np.array([[10.0, -4.0, 0.5], [-15.0, 7.0, -1.0], [6.0, -3.0, 0.5]])   # c from (d, dv, da)
    free_v = np.nonzero(np.isnan(v))[0]
    free_a = np.nonzero(np.isnan(a))[0]
    col = {("v", int(i)): c for c, i in enumerate(free_v)}
    col.update({("a", int(i)): c + len(free_v) for c, i in enumerate(free_a)})
    if not col:
        return Quintic(t, p, v, a)
    m = len(s)
    A = np.zeros(((n - 1) * m, len(col)))
    b = np.zeros((n - 1) * m)
    for i in range(n - 1):
        hi = h[i]
        # (d, dv, da) from the state (p0, v0, a0, p1, v1, a1)
        D = np.array([[-1.0, -hi, -0.5 * hi * hi, 1.0, 0.0, 0.0],
                      [0.0, -hi, -hi * hi, 0.0, hi, 0.0],
                      [0.0, 0.0, -hi * hi, 0.0, 0.0, hi * hi]])
        B = (wq[:, None] * basis) @ mix @ D * (hi ** -2.5)
        rows = slice(i * m, (i + 1) * m)
        state = [("p", i), ("v", i), ("a", i), ("p", i + 1), ("v", i + 1), ("a", i + 1)]
        for c, (kind, k) in enumerate(state):
            if (kind, k) in col:
                A[rows, col[(kind, k)]] += B[:, c]
            else:
                b[rows] -= B[:, c] * {"p": p, "v": v, "a": a}[kind][k]
    x = np.linalg.lstsq(A, b, rcond=None)[0]
    v[free_v] = x[:len(free_v)]
    a[free_a] = x[len(free_v):]
    return Quintic(t, p, v, a)


def wobble(t, seed, f_lo, f_hi, n=6):
    """Slow pseudo-random signal of unit RMS: a fixed sum of sines between f_lo and f_hi [Hz].
    Deterministic: the same seed gives the same signal."""
    rng = np.random.default_rng(seed)
    f = rng.uniform(f_lo, f_hi, n)
    ph = rng.uniform(0.0, 2.0 * np.pi, n)
    a = rng.uniform(0.5, 1.0, n)
    t = np.asarray(t, dtype=float)
    y = (a * np.sin(2.0 * np.pi * f * t[..., None] + ph)).sum(-1)
    return y / np.sqrt(0.5 * np.sum(a * a))


def move(t, ta, tb, ease=smootherstep):
    """0 before ta, 1 after tb, a smooth rise in between."""
    return ease((np.asarray(t, dtype=float) - ta) / max(tb - ta, 1e-6))


def window(t, a, b, c, d):
    """Rises from a to b, falls from c to d."""
    return move(t, a, b) * (1.0 - move(t, c, d))
