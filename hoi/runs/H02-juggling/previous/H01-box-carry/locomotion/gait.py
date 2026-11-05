"""Gait parameters and the normal-gait target curves.

Stance phase u.  Every period a foot spends on the floor ("plant") has its own stance clock
u(t), which drives the foot rockers, the target knee angle and the centre of pressure.  In
steady walking u runs exactly as in a normal gait cycle (0 = heel strike, 0.1 = the other
foot leaves the floor, 0.5 = the other foot lands, 0.6 = toe off).  A standing foot rests at
u = U_ST (flat foot).  See plan.py for how u(t) is built for starts, stops and turns.
"""
import numpy as np
from scipy.interpolate import PchipInterpolator

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
# Centre of pressure under a foot: distance ahead of the heel-circle centre [m] along the
# foot.  It starts under the heel, crosses the mid-foot, and ends under the toes at toe off.
COP_FWD = PchipInterpolator([0.0, 0.08, 0.20, 0.31, 0.50, 0.60],
                            [-0.010, 0.035, 0.092, 0.120, 0.165, 0.200])

U_ST = 0.20        # stance phase of a standing foot (flat foot, centre of pressure mid-foot)
GRAVITY = 9.81

DEFAULTS = dict(
    # --- steady gait (straight line)
    T=1.06,              # gait cycle on a straight line [s]  (~113 steps / min)
    stride=1.30,         # stride length on a straight line [m] -> 1.23 m/s
    heel_x=0.068,        # lateral position of the heel-circle centres (+-) when walking [m]
    toe_out=4.5 * DEG,   # foot progression angle when walking
    ds_frac=0.20,        # double support as a fraction of the step period
    knee_geo=0.75,       # share of the skeleton's knee asymmetry absorbed by the knees
    v_app=0.30,          # forward heel speed over the floor just before contact [m/s]
    alpha_hs=19.0 * DEG,  # foot pitch (toes up) at heel strike
    toe_hs=8.0 * DEG,    # toe extension at heel strike
    phi_ff=0.08,         # foot flat
    phi_to=0.60,         # toe off
    soft_w=1.0 * DEG,    # softness of the soft maximum in the heel-rise angle
    heel_rise_max=70.0 * DEG,  # largest foot pitch over the ball of the foot
    pivot_gain=0.75,     # in late stance a foot pivots on the ball of the foot towards the
    pivot_free=8.0 * DEG,  # ... body's heading by this share of the misalignment beyond pivot_free
    pivot_max=30.0 * DEG,  # ... but at most this much (turns and corners)
    u_hr=0.31,           # heel off
    alpha_50=14.0 * DEG,  # heel-rise angle at opposite heel strike
    hr_pow=1.7,          # shape of the heel-rise profile
    u_tr=0.50,           # toes start to roll (toe rocker)
    beta_to=22.0 * DEG,  # toe segment pitch at toe off
    yaw_amp=4.5 * DEG,   # pelvis rotation
    roll_amp=3.5 * DEG,  # pelvic drop
    pitch_mean=3.0 * DEG,  # forward pelvic tilt when walking
    pitch_stand=1.0 * DEG,  # ... and when standing
    pitch_amp=1.0 * DEG,
    knee_pk=61.0 * DEG,  # peak swing knee flexion (full-length step)
    knee_pk_min=30.0 * DEG,  # ... for a step of almost no length
    knee_pk_s=0.30,      # ... at this fraction of the swing
    swing_clear=0.014,   # lowest sole point of a walking swing at least this high mid-swing [m]
    hip_retract=4.0 * DEG,  # hip flexion peak above its heel-strike value
    hip_ab_swing=1.5 * DEG,  # slight abduction of the swing leg (clearance)
    var=1.0,             # scale of the slow natural variations (0 = perfectly periodic)
    c_walk=None,         # pelvis ahead of the centre of mass when walking (calibrated if None)
    roll0=None,          # static pelvic obliquity absorbing skeleton asymmetry (calibrated if None)
    # --- pelvis height fit
    y_rate=120.0,        # samples per second of the required-height curve
    y_lambda=1500.0,     # smoothness weight (third differences)
    reach_max=0.985,     # a leg swinging along a foot path reaches at most this share of its length
    y_margin=0.0003,     # the fitted pelvis stays this far below the required height [m]
    # --- balance (inverted pendulum)
    com_height=0.95,     # height of the centre of mass [m]
    lean_sigma=0.22,     # smoothing of the centre-of-mass acceleration that drives the lean [s]
    # --- walking a curved line
    line_sigma=0.25,     # body line: smoothing of the marked path along its length [m]
    fillet_frac=0.35,    # ... polyline corners rounded to stay within this share of the tolerance
    feet_sigma=0.12,     # feet line (where the footprints go): much less smoothing ...
    feet_fillet_frac=0.1,  # ... and tighter corners
    apex_out=0.04,       # the outer foot at the apex of a corner is put this much further out [m]
    after_apex_len=0.8,  # length of the step after the apex (x the normal step)
    sharp_turn=0.7,      # a bend turning faster than this [rad/m, smoothed] is taken as a corner:
    corner_min=40.0 * DEG,  # ... (if it turns at least this much) with the outer foot at its apex
    turn_slow=0.16,      # speed factor 1 / (1 + turn_slow * k + turn_slow2 * k^2), k = |curvature| * 1 m
    turn_slow2=0.12,     # ... (the quadratic term slows tight turns down much more)
    slow_sigma=0.4,      # ... curvature smoothed over this length [m]
    slow_lead=0.4,       # ... and looked up this far ahead (people slow before a bend) [m]
    slow_lag=0.2,        # ... and this far behind (and speed up again only after it) [m]
    cad_share=0.4,       # share of the slow-down taken by cadence (rest by step length)
    lean_gain=0.85,      # fraction of the physical lean angle atan(v^2 k / g)
    lean_max=7.0 * DEG,  # ... but never more than this
    shift_max=0.055,     # largest outward shift of the feet in a bend [m] (< heel_x)
    shift_lead=0.15,     # feet are shifted outwards for the lean found this far ahead [m]
    foot_yaw_lead=0.12,  # a planted foot points along the line this far beyond it [m]
    pelvis_lean=0.5,     # share of the lean shown as pelvis roll
    thorax_lean=1.0,     # share of the lean shown by the thorax (in world)
    head_lean=0.6,       # share of the lean shown by the head (righting reflex keeps it upright)
    # --- standing
    stand_half_width=0.085,  # heel-circle centres +- this far from the midline [m]
    stand_toe_out=7.0 * DEG,
    knee_stand=4.0 * DEG,    # knee flexion when standing
    stand_sway=1.0,          # scale of the slow postural sway
    # --- starting and stopping
    start_wait=0.80,     # standing time before the weight shift of the first step [s]
    unload=0.30,        # a standing foot is unloaded over this time before it lifts [s]
    first_swing=0.40,    # swing time of the first step from standing [s]
    start_len=(0.60, 0.85, 0.97),   # step lengths of the first steps (x the normal step)
    start_time=(1.0, 1.04, 1.02),   # step periods of the first steps (x the normal period)
    stop_len=(0.70, 0.90),          # last steps before the closing step, last first
    stop_time=(1.06, 1.02),
    close_ds=0.13,       # double support before the closing step of a stop [s]
    close_swing=0.48,    # swing time of the closing step [s]
    close_alpha=5.0 * DEG,  # foot pitch when the closing foot touches down
    # --- turning on the spot
    turn_max_step=65.0 * DEG,  # largest rotation of a foot in one step
    turn_half_width=0.11,      # feet a little wider apart while turning [m]
    turn_swing=0.33,           # swing time of a turning step [s]
    turn_ds=0.10,              # double support between turning steps [s]
    turn_alpha=3.0 * DEG,      # foot pitch at touch-down
    turn_lift=0.045,           # lowest sole point this high in mid-swing [m]
    turn_pause=0.15,           # standing time between stopping and starting the turn [s]
    # --- squeezing sideways through a narrow gap (a "passage", see plan._passage_layout)
    body_half_width=0.28,      # half the body's width seen from the front, arms swinging [m]
    body_half_width_still=0.25,  # ... with the arms held still at the sides [m]
    shoulder_half_thickness=0.07,  # half the front-to-back thickness of shoulder and arm [m]
    body_half_depth=0.15,      # half its depth, belly to back [m]
    chest_half_width=0.10,     # the front of the chest is this far to either side of the middle [m]
    hip_half_width=0.192,      # half the width of the hips [m]
    walk_sway=0.025,           # side-to-side sway of the body when walking [m]
    gap_margin=0.035,          # clearance wanted on either side in a gap [m]
    shoulder_turn_max=45.0 * DEG,  # gaps that need a larger shoulder turn are passed sideways
    shoulder_pelvis=0.35,      # share of a shoulder turn taken by the pelvis (the rest by the spine)
    shoulder_in=0.45,          # the shoulders are turned when the body is this far before the gap [m]
    shoulder_out=0.35,         # ... until it is this far past it [m]
    shoulder_ramp=0.6,         # ... turning in and out over this time [s]
    squeeze_turn="L",          # which way the body turns: 'L' faces the left of the path
    squeeze_in=0.15,     # first sideways narrow stance centred this far before the narrow part [m]
    squeeze_out=0.17,    # last one centred this far after it [m]
    squeeze_bias=0.0085,  # sideways, the centre of pressure is this far in front of the gap middle
                         # [m] (centres the body: belly 0.13 m in front, buttocks 0.165 m behind)
    side_narrow=0.20,    # distance between the feet' centres of pressure in a narrow stance [m]
    side_step=0.32,      # largest side step [m]
    side_swing=0.38,     # swing time of a side step [s]
    side_ds=0.12,        # double support between side steps [s]
    side_lift=0.03,      # lowest sole point this high in mid-swing of a side step [m]
    side_hold=0.12,      # share of a side step's swing at either end without horizontal motion
    side_pivot_free=35.0 * DEG,  # in and out of a passage the hips absorb this much twist
    side_alpha=2.0 * DEG,  # foot pitch at touch-down of a side step (nearly flat)
    side_knee=8.0 * DEG,  # extra stance knee flexion while side-stepping
    side_lam=0.3,        # loading response after a side step (x the walking one)
    side_unload=0.15,    # a side-stepping foot is unloaded over this time before it lifts [s]
    side_u_off=0.40,     # ... while its stance clock rises to this (a slight heel rise)
    entry_yaw=60.0 * DEG,  # the leading foot's last walking step lands turned this much sideways
    entry_turn=30.0 * DEG,  # heading offset (turned sideways) when it lands
    entry_ds=0.12,       # double support before the trailing foot comes round [s]
    entry_swing=0.42,    # ... and that step's swing time [s]
    exit_step=0.20,      # the leading foot's step out of the passage [m]
    exit_yaw=35.0 * DEG,  # ... lands turned this much from the line, towards the facing side
    exit_swing=0.34,     # ... swing time [s]
    exit_turn=62.0 * DEG,  # heading offset when it lands
    exit2_ds=0.08,       # double support before the first walking step after a passage [s]
    exit2_swing=0.42,    # ... and that step's swing time [s]
    exit2_lift=0.05,     # ... and its sole clearance in mid-swing [m]
    exit2_turn=10.0 * DEG,  # heading offset when it lands
    approach_len=(0.62, 0.80, 0.92),  # last steps before a passage (entry step first)
    approach_time=(1.12, 1.05, 1.02),
    resume_len=(0.65, 0.82, 0.94),    # first walking steps after a passage
    resume_time=(1.08, 1.04, 1.02),
    # --- upper body
    thorax_lead_t=0.20,  # the thorax faces where the pelvis will face this much later [s]
    gaze_lead_t=0.55,    # the gaze is directed where the body will face this much later [s]
    head_gain=0.75,      # share of the gaze direction (relative to the thorax) taken by the head
    head_yaw_max=65.0 * DEG,  # largest head rotation relative to the thorax (soft limit)
    side_gaze=1.0,       # sideways, the gaze turns this share back towards the direction of travel
    arm_abd_extra=4.0,   # arms this much further out [deg]: the hands clear this body's wide hips
    load_trunk_calm=0.6,  # under a load, this share of the thorax's walking oscillation is held back
)


def make_params(overrides=None):
    p = dict(DEFAULTS)
    if overrides:
        unknown = set(overrides) - set(p)
        if unknown:
            raise KeyError("unknown gait parameters: %s" % sorted(unknown))
        p.update(overrides)
    return p


def heel_profile(u, p, push=1.0):
    """Prescribed heel rise (foot pitch about the ball of the foot) from heel-off on."""
    s = (u - p["u_hr"]) / (0.5 - p["u_hr"])
    return push * p["alpha_50"] * np.maximum(s, 0.0) ** p["hr_pow"]


def toe_beta(u, p, push=1.0):
    """Pitch of the toe segment rolling over the toe pad (toe rocker)."""
    s = (u - p["u_tr"]) / (p["phi_to"] - p["u_tr"])
    return push * p["beta_to"] * np.maximum(s, 0.0) ** 2


def knee_floor(u, push=1.0):
    """Minimum stance knee flexion [deg]; a smaller push-off needs less pre-swing flexion."""
    return 1.5 + push * (KNEE_FLOOR(u) - 1.5)


def knee_target(u, lam, p):
    """Target knee flexion [deg] of a weight-bearing leg: the normal loading response scaled
    by lam (1 = walking heel strike, 0 = standing)."""
    ks = p["knee_stand"] / DEG
    return ks + lam * (KNEE_TGT(u) - ks)


def bend_speed_factor(k, p):
    """Speed factor in a bend of curvature k [1/m]."""
    k = np.abs(k)
    return 1.0 / (1.0 + p["turn_slow"] * k + p["turn_slow2"] * k ** 2)
