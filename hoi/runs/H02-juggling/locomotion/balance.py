"""Balance: from the planted feet to the path of the centre of mass.

Centre of pressure (COP).  The point on the floor through which the body's weight acts.
Under one foot it runs from the heel to the toes during the stance (gait.COP_FWD).  When both
feet are on the floor, the weight is shared: each plant carries a load that builds up after
touch-down and is shed before lift-off (smooth ramps over the double support, or over a
slower weight shift when starting from standing), and the COP is the load-weighted mean.
While standing, a small slow postural sway is added.

Centre of mass (COM).  The linear inverted pendulum model: the body is a point mass at a
constant height z_c balanced on the COP, so its horizontal acceleration is
    x'' = omega^2 (x - p),   omega = sqrt(g / z_c).
Given the whole COP trajectory p(t), the solution that stays bounded (the body does not fall
over) is found by solving this as a boundary-value problem; it is the COP smoothed with the
two-sided kernel (omega / 2) exp(-omega |t|).  This one model produces the side-to-side sway
of walking, the forward fall that starts a walk, the braking at a stop, the cutting inside of
corners and the small weight shifts of stepping on the spot, all consistent with the feet.
"""
import numpy as np
from scipy.linalg import solve_banded
from scipy.ndimage import gaussian_filter1d

from .gait import COP_FWD, GRAVITY
from .path import hdir, lnorm
from .plan import SIDES
from .rotations import smoothstep


def cop_path(plan, t, stand_env=None):
    """Centre of pressure (n, 2) at times t."""
    p = plan.p
    t = np.asarray(t, dtype=float)
    num = np.zeros((len(t), 2))
    den = np.zeros(len(t))
    for side in SIDES:
        for P in plan.plants[side]:
            m = (t >= P.t_on) & (t <= P.t_off)
            if not m.any():
                continue
            tt = t[m]
            load = np.ones(len(tt))
            if P.landing:
                load *= smoothstep((tt - P.t_on) / P.ramp_up)
            if P.lifts:
                load *= smoothstep((P.t_off - tt) / P.ramp_dn)
            load = np.maximum(load, 1e-9)
            c = P.xz + COP_FWD(P.u(tt))[:, None] * hdir(P.yaw)
            num[m] += load[:, None] * c
            den[m] += load
    cop = num / np.maximum(den, 1e-12)[:, None]
    if stand_env is not None:
        # quiet standing: slow sway of a few millimetres, front-back larger than sideways
        v = p["stand_sway"] * p["var"]
        ap = 0.0035 * (np.sin(2 * np.pi * t / 7.3 + 0.4) + 0.6 * np.sin(2 * np.pi * t / 3.1 + 1.9))
        ml = 0.0020 * (np.sin(2 * np.pi * t / 5.9 + 2.3) + 0.5 * np.sin(2 * np.pi * t / 2.7 + 0.8))
        h = stand_env["heading"]
        w = v * stand_env["weight"]
        cop += (w * ap)[:, None] * hdir(h) + (w * ml)[:, None] * lnorm(h)
    return cop


def lipm_com(t, cop, com_height):
    """Bounded solution of x'' = omega^2 (x - p) on a uniform time grid, with the COM at rest
    over the COP at both ends.  Returns the COM (n, 2) and omega."""
    omega = np.sqrt(GRAVITY / com_height)
    dt = float(t[1] - t[0])
    n = len(t)
    a = 1.0 / (omega * dt) ** 2
    ab = np.zeros((3, n))
    ab[0, 2:] = -a
    ab[1, :] = 1.0 + 2.0 * a
    ab[2, :-2] = -a
    ab[1, 0] = ab[1, -1] = 1.0
    return solve_banded((1, 1), ab, cop), omega


def smoothed_acceleration(com, cop, omega, dt, sigma):
    """Low-passed COM acceleration (n, 2): the sustained part that the body leans against
    (bends, starting, stopping), without the step-by-step sway."""
    acc = omega ** 2 * (com - cop)
    return gaussian_filter1d(acc, sigma / dt, axis=0, mode="nearest")
