"""Gait parameters, normal-gait target curves and the gait clock.

The gait clock maps time to the gait phase (left heel strike at phase 0, right at 0.5,
one unit per gait cycle) and to the distance S walked along the walking line.  Cadence
and stride length can vary along the line (slower in bends) and the cadence wanders slowly
(+-1.5 %), so that no two steps are identical.
"""
import math

import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator

from .rotations import DEG

# Normal adult sagittal curves (degrees), written from general biomechanics knowledge.
# Stance-knee flexion of the leading leg (heel strike -> opposite heel strike), used to solve
# the pelvis height.
KNEE_TGT = PchipInterpolator(
    [0.00, 0.03, 0.06, 0.10, 0.14, 0.18, 0.22, 0.27, 0.32, 0.37, 0.41, 0.45, 0.50, 0.55],
    [5.0, 8.5, 12.0, 15.5, 17.5, 16.8, 14.5, 11.0, 8.0, 6.0, 5.0, 6.0, 10.0, 18.0])
# Minimum knee flexion of a stance leg: near zero until terminal stance, then the knee must
# bend quickly in pre-swing (the heel rises further if needed to allow it).
KNEE_FLOOR = PchipInterpolator(
    [0.00, 0.45, 0.50, 0.55, 0.60, 0.62, 0.70],
    [1.5, 1.5, 7.5, 17.5, 31.0, 35.0, 48.0])

GRAVITY = 9.81

DEFAULTS = dict(
    # --- steady gait (straight line); see NOTES.md for the reasoning behind the values
    T=1.06,              # gait cycle on a straight line [s]  (~113 steps / min)
    stride=1.30,         # stride length on a straight line [m] -> 1.23 m/s
    phi0=0.12,           # left-leg phase at t = 0
    heel_x=0.068,        # lateral position of the heel-circle centres (+-) [m]
    toe_out=4.5 * DEG,   # foot progression angle
    d_hs=None,           # heel ahead of the pelvis at heel strike (solved if None)
    roll0=None,          # static pelvic obliquity absorbing skeleton asymmetry (solved if None)
    knee_geo=0.75,       # share of the skeleton's knee asymmetry absorbed by the knees
    v_app=0.30,          # forward heel speed over the floor just before contact [m/s]
    alpha_hs=19.0 * DEG,  # foot pitch (toes up) at heel strike
    toe_hs=8.0 * DEG,    # toe extension at heel strike
    phi_ff=0.08,         # foot flat
    phi_to=0.60,         # toe off
    soft_w=1.0 * DEG,    # softness of the soft maximum in the heel-rise angle
    u_hr=0.31,           # heel off
    alpha_50=14.0 * DEG,  # heel-rise angle at opposite heel strike
    hr_pow=1.7,          # shape of the heel-rise profile
    u_tr=0.50,           # toes start to roll (toe rocker)
    beta_to=22.0 * DEG,  # toe segment pitch at toe off
    z_amp=0.004,         # forward speed fluctuation amplitude [m]
    x_amp=0.021,         # lateral pelvis sway [m]
    x_peak=0.30,         # phase of maximal sway to the left
    yaw_amp=4.5 * DEG,
    roll_amp=3.5 * DEG,
    pitch_mean=3.0 * DEG,
    pitch_amp=1.0 * DEG,
    knee_pk=61.0 * DEG,  # peak swing knee flexion
    knee_pk_s=0.30,      # ... at this fraction of the swing
    hip_retract=4.0 * DEG,  # hip flexion peak above its heel-strike value
    hip_ab_swing=1.5 * DEG,  # slight abduction of the swing leg (clearance)
    var=1.0,             # scale of the slow natural variations (0 = perfectly periodic)
    # --- pelvis height fit
    y_rate=120.0,        # samples per second of the required-height curve
    y_lambda=1500.0,     # smoothness weight (third differences)
    y_margin=0.0003,     # the fitted pelvis stays this far below the required height [m]
    # --- walking a curved line
    line_sigma=0.30,     # smoothing of the marked path along its length [m]
    turn_slow=0.16,      # speed factor 1 / (1 + turn_slow * k + turn_slow2 * k^2), k = |curvature| * 1 m
    turn_slow2=0.06,     # ... (the quadratic term slows tight turns down much more)
    slow_sigma=0.6,      # ... curvature smoothed over this length [m]
    slow_lead=0.4,       # ... and looked up this far ahead (people slow before a bend) [m]
    cad_share=0.4,       # share of the slow-down taken by cadence (rest by stride length)
    lean_gain=0.85,      # fraction of the physical lean angle atan(v^2 k / g)
    lean_max=7.0 * DEG,  # ... but never more than this
    shift_max=0.055,     # largest outward shift of the feet in a bend [m] (< heel_x)
    shift_lead=0.15,     # feet are shifted outwards for the lean found this far ahead [m]
    foot_yaw_lead=0.12,  # a planted foot points along the line this far beyond it [m]
    pelvis_lean=0.5,     # share of the lean shown as pelvis roll
    thorax_lean=1.0,     # share of the lean shown by the thorax (in world)
    head_lean=0.6,       # share of the lean shown by the head (righting reflex keeps it upright)
    thorax_lead=0.25,    # the thorax faces along the line this far ahead [m]
    look_ahead=1.6,      # the gaze is directed at the line this far ahead [m]
    head_gain=0.7,       # share of the gaze direction (relative to the thorax) taken by the head
)


def make_params(overrides=None):
    p = dict(DEFAULTS)
    if overrides:
        unknown = set(overrides) - set(p)
        if unknown:
            raise KeyError("unknown gait parameters: %s" % sorted(unknown))
        p.update(overrides)
    return p


def heel_profile(u, p):
    """Prescribed heel rise (foot pitch about the ball of the foot) from heel-off on."""
    s = (u - p["u_hr"]) / (0.5 - p["u_hr"])
    return p["alpha_50"] * np.maximum(s, 0.0) ** p["hr_pow"]


def toe_beta(u, p):
    """Pitch of the toe segment rolling over the toe pad (toe rocker)."""
    s = (u - p["u_tr"]) / (p["phi_to"] - p["u_tr"])
    return p["beta_to"] * np.maximum(s, 0.0) ** 2


class Clock:
    """Gait phase and distance along the line as functions of time.

    dphase/dt = f_cad(S) (1 + wobble(t)) / T          (wobble: slow +-1.5 % cadence drift)
    dS/dt     = stride * f_str(S) * dphase/dt
    with S(0) chosen so that the pelvis is exactly at s = 0 at t = 0."""

    def __init__(self, p, s_grid, f_cad, f_str, t_lo, t_hi, dt=1.0 / 600.0):
        self.p = p
        s0 = float(s_grid[0])
        ds = float(s_grid[1] - s_grid[0])
        fc = f_cad.tolist()
        fs = f_str.tolist()
        nmax = len(fc) - 2
        T0, L0, var = p["T"], p["stride"], p["var"]
        wob = [(var * 0.012, 2 * math.pi / 4.1, 0.7), (var * 0.007, 2 * math.pi / 2.3, 2.1)]

        def look(arr, S):
            x = (S - s0) / ds
            i = min(max(int(x), 0), nmax)
            f = min(max(x - i, 0.0), 1.0)
            return arr[i] + f * (arr[i + 1] - arr[i])

        def rate(t, S):
            w = 1.0 + sum(a * math.sin(om * t + ph) for a, om, ph in wob)
            dph = look(fc, S) * w / T0
            return dph, L0 * look(fs, S) * dph

        def run(t_end, step):
            ts, phs, Ss = [0.0], [p["phi0"]], [S_init]
            t, ph, S = 0.0, p["phi0"], S_init
            n = int(math.ceil(abs(t_end) / dt)) + 1
            for _ in range(n):
                a1, b1 = rate(t, S)
                a2, b2 = rate(t + 0.5 * step, S + 0.5 * step * b1)
                t += step
                ph += step * a2
                S += step * b2
                ts.append(t)
                phs.append(ph)
                Ss.append(S)
            return ts, phs, Ss

        S_init = 0.0
        for _ in range(3):
            S_init = -p["z_amp"] * look(fs, S_init) * math.sin(4 * math.pi * (p["phi0"] - 0.07))
        tf, pf, sf = run(t_hi, dt)
        tb, pb, sb = run(t_lo, -dt)
        self.t_grid = np.array(tb[::-1] + tf[1:])
        self.ph_grid = np.array(pb[::-1] + pf[1:])
        self.S_grid = np.array(sb[::-1] + sf[1:])
        self._ph = CubicSpline(self.t_grid, self.ph_grid)
        self._S = CubicSpline(self.t_grid, self.S_grid)
        self._dph = self._ph.derivative()
        self.s_grid, self.f_str_grid = s_grid, f_str

    def phase(self, t):
        return self._ph(np.asarray(t, dtype=float))

    def S(self, t):
        return self._S(np.asarray(t, dtype=float))

    def f_str(self, S):
        return np.interp(S, self.s_grid, self.f_str_grid)

    def event_time(self, phase):
        """Time at which the (left-leg) phase reaches the given value(s)."""
        phase = np.asarray(phase, dtype=float)
        t = np.interp(phase, self.ph_grid, self.t_grid)
        for _ in range(2):
            t = t - (self._ph(t) - phase) / self._dph(t)
        return t
