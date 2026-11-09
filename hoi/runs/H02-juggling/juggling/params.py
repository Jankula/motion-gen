"""All tunable numbers of the juggling motion, in one place.

Lengths in meters above the floor or relative to the middle of the pattern, times in seconds, angles
in radians.  x is the person's left, z the person's front (the pattern is planned facing +z).
"""
from locomotion.rotations import DEG

DEFAULTS = dict(
    # --- rhythm of the cascade
    beat=0.33,             # time between two throws (a real three-ball cascade: 0.3-0.45)
    beat_min=0.29,         # fastest beat used when a clip is too short for what it must contain
    beat_max=0.40,
    beat_per_kg=0.10,      # heavier balls are thrown a little lower and slower [s per kg above 0.12]
    dwell=0.42,            # time a ball stays in the hand, from catch to throw
    # --- how long things take
    lead=1.0,              # standing with the balls before the first throw
    lead_min=0.6,
    tail=3.7,              # from the last catch to the end of the clip
    tail_min=2.6,
    margin_throws=2.5,     # this many throws more than the task's minimum on each part
    margin_time=1.0,       # this much longer on one foot than the task's minimum
    two_foot_share=0.38,   # share of the spare time spent on two feet
    shift_time=1.5,        # the weight moves onto the standing foot in this time
    heel_time=0.32,        # the heel of the free foot rises for this long before the toes leave
    raise_time=0.62,       # from the toes leaving the floor to the foot being fully up
    wait_after_catch=0.55, # the last catch comes this long before the free foot starts down
    lower_time=0.62,       # the free foot comes down in this time
    flatten_time=0.22,     # from the toes touching to the foot being flat
    return_time=1.15,      # the weight moves back between the feet in this time
    # --- the pattern, relative to its centre (see Plan.anchor)
    x_throw=0.105,         # half the distance between the throwing points
    x_catch=0.255,         # half the distance between the catching points
    y_throw=1.18,          # height of the balls at release
    y_catch=1.18,          # height of the balls at the catch
    z_throw=0.285,         # in front of the pelvis
    z_catch=0.275,
    follow=0.90,           # the pattern follows this share of the sideways shift of the weight
    # --- how the hand moves
    catch_match=0.55,      # the hand moves at this share of the ball's fall speed at the catch ...
    catch_match_side=0.45, # ... and of its sideways speed
    catch_give=0.016,      # the ball touches the fingers this far above its seat in the palm
    t_top=0.075,           # the hand stops rising this long after the release
    t_up=0.13,             # the throw starts from the bottom of the dip this long before the release
    up_share=0.45,         # height of the throw = up_share * release speed * t_up
    a_bottom=20.0,         # acceleration at the bottom of the dip [m/s2]
    a_top=-25.0,           # acceleration at the top of the hand's path [m/s2]
    y_low=1.03,            # a hand that gives way after a catch goes no lower than this
    ready_x=0.175,         # hands at the start and at the end
    ready_y=1.12,
    ready_z=0.27, 
    # --- the hand's orientation at the moments of its cycle: (fingers up, thumb side up)
    tilt_catch=(10.0 * DEG, 8.0 * DEG),
    tilt_bottom=(-3.0 * DEG, 15.0 * DEG),
    tilt_throw=(24.0 * DEG, 13.0 * DEG),
    tilt_top=(30.0 * DEG, 12.0 * DEG),
    tilt_ready=(6.0 * DEG, 16.0 * DEG),
    hand_yaw_share=0.75,   # the hand follows this share of the forearm's direction
    elbow_x=0.215,         # where the forearm pivots, for that direction
    elbow_z=0.01,
    # --- natural variation between throws
    var_time=0.010,        # of the throw times [s]
    var_flight=0.018,      # of the flight time (share)
    var_pos=0.012,         # of the throwing and catching points [m]
    var_tempo=0.012,       # slow changes of the beat (share)
    var_one_foot=1.35,     # all a little larger while on one foot
    # --- the body
    toe_out=7.0 * DEG,     # the feet turn out this much
    stance_extra=0.0,      # the feet stand this much wider each than the rest pose
    knee_drop=0.013,       # the pelvis stands this much lower than with straight legs
    knee_drop_one=0.006,   # ... and on one foot this much lower still
    bounce=0.005,          # the knees give this much with every throw
    leg_soft=9.0 * DEG,    # a leg with weight on it never goes straighter than this
    com_side=0.0,          # the centre of mass sits this far to the left of the middle of the feet
    com_fwd=0.012,         # ... and this far in front of the middle of the feet
    com_foot_fwd=0.015,    # on one foot, this far in front of the middle of that foot
    com_foot_in=0.002,     # ... and this far on the inside of it
    sway_two=0.0035,       # slow sway of the centre of mass on two feet [m, RMS]
    sway_one=0.0065,       # ... and on one foot
    thorax_pitch=4.0 * DEG,  # chest leaning forward
    thorax_yaw_amp=2.6 * DEG,   # the chest turns against the arms
    thorax_roll_amp=1.5 * DEG,
    pelvis_tilt=1.5 * DEG,
    hike=1.8 * DEG,        # the pelvis rises on the free side while on one foot
    pelvis_turn=3.0 * DEG, # and turns with the lifted leg
    pelvis_back=4.0 * DEG, # and tips back with it
    lean_one=1.5 * DEG,    # the chest leans over the standing foot
    # --- the free leg
    thigh_up=60.0 * DEG,   # thigh above straight down when the foot is up
    knee_up=80.0 * DEG,    # knee bend when the foot is up
    foot_drop=16.0 * DEG,  # the toes hang down this much when the foot is up
    heel_rise=30.0 * DEG,  # the heel rises this much before the toes leave
    land_pitch=9.0 * DEG,  # the toes touch first with the foot tilted this much
    land_offset=(0.012, 0.016),  # the foot comes down this far from where it left (outwards, forwards)
    leg_wander=0.012,      # the lifted foot moves about this much for balance [m, RMS]
    # --- arms
    pole=(0.52, -0.80, -0.30),  # the direction the elbow points, in the chest frame (left arm)
    collar_fwd=12.0 * DEG,  # the shoulders come forward with the arms in front of the body
    collar_up=1.0 * DEG,   # and rise a little ...
    collar_follow=2.5 * DEG,  # ... and with the hands [per 0.2 m of hand height]
    forearm_twist=0.68,    # share of the forearm rotation taken at the elbow joint, the rest at the wrist
    # --- head and eyes
    head_down_max=24.0 * DEG,  # the head looks down at most this much
    look_up_share=0.92,    # the head turns this far towards the point looked at
    look_height=0.30,      # the eyes rest this far above the throwing height
    gaze_side=0.06,        # the gaze follows the top of the arcs sideways this far
    # --- the balls in the hand
    seat_along=0.020,      # the seat of one ball, this far along the hand from the palm centre
    seat_along_big=0.010,  # ... and this far for a large ball
    seat_big_from=0.0335,  # balls count as large from this radius ...
    seat_big_to=0.037,     # ... fully from this one
    seat_across=-0.004,    # ... towards the little finger, away from the ball of the thumb
    seat_gap=0.005,        # palm centre to ball skin
    finger_press=-0.001,    # the finger pads press this far into the ball
    rear_along=-0.006,     # two balls: the rear one, along the hand from the palm centre
    tray=(10.0 * DEG, 20.0 * DEG, 10.0 * DEG),  # two balls: the bend of the fingers under the front ball
    tray_gap=((0.025, 0.010), (0.0325, 0.023), (0.038, 0.023), (0.045, 0.014)),  # (ball radius, pads to ball skin)
    radius_ref=0.0325,     # the heights of the pattern are given for a ball of this radius
    two_space=0.0015,      # gap between the two balls
    two_wrap=30.0 * DEG,   # the fingers bend at most this much under the front ball
)


def make_params(overrides=None):
    q = dict(DEFAULTS)
    if overrides:
        unknown = set(overrides) - set(q)
        if unknown:
            raise KeyError("unknown parameters: %s" % sorted(unknown))
        q.update(overrides)
    return q
