"""Measurements for a person juggling balls, on the real SMPL-X mesh.

Used by evaluate.py for every task with "balls". Nobody tells this file when a ball is thrown or caught.
It works that out from the motion itself:

  - a ball is held while palm-side skin of a hand stays within 1.5 cm of it;
  - everything between two holds is a flight, which has to be a free fall: a straight line sideways,
    and a parabola with real gravity up and down.

Most measurements exist to catch one specific way of faking juggling. Nothing in the setup moves a ball,
so a ball could float, change speed in the air or appear in a hand, and only these checks would notice.
"""
import numpy as np
from scipy.spatial.distance import pdist

from walkenv.body import BODY_JOINT_NAMES
from walkenv.cameras import moving_average

from .evaluate import _add_joint_limits, _arm_depth, _body_parts, _center_of_mass, _outside_support

G = 9.81  # m/s2
HOLD_M = 0.015  # palm-side skin further from a ball than this cannot be holding it
TOUCH_M = 0.008  # skin this close to a ball touches it
ON_PARABOLA_M = 0.003  # a ball this close to the fitted flight is still flying
MIN_FLIGHT_FRAMES = 5  # fewer points than this are not enough to fit a flight
FOOT_DOWN_M = 0.02  # a foot with its lowest skin this close to the floor is down
MIN_CONTACT_CM = 5.0  # measured on the mesh: a ball in a hand gives 5.9-7 cm, a ball on a fingertip 3.8-4.4 cm


def runs(values):
    """[(start, end, value)] of equal neighbouring values; end is exclusive."""
    edges = np.flatnonzero(np.diff(values)) + 1
    starts, ends = np.r_[0, edges], np.r_[edges, len(values)]
    return [(int(a), int(b), values[a]) for a, b in zip(starts, ends)]


def hand_states(gap, fps):
    """gap (T, 2): palm-side skin of the left and right hand to one ball. Returns (T,): -1 free, 0 left, 1 right."""
    state = np.where(gap.min(axis=1) <= HOLD_M, gap.argmin(axis=1), -1)
    short = max(2, round(0.1 * fps))
    for a, b, value in runs(state):  # a ball passing close to a hand is not held by it
        if value >= 0 and b - a < short:
            state[a:b] = -1
    for a, b, value in runs(state):  # a hand losing touch for an instant has not let go
        if value < 0 and b - a < short and a > 0 and b < len(state) and state[a - 1] == state[b]:
            state[a:b] = state[a - 1]
    return state


def find_flights(ball, position, state, fps):
    """Every stretch between two holds of one ball, with a free-fall fit: a list of dicts."""
    flights, num_frames = [], len(position)
    for a, b, value in runs(state):
        if value >= 0:
            continue
        flight = dict(ball=ball, first=a, last=b - 1, source=int(state[a - 1]) if a else None,
                      target=int(state[b]) if b < num_frames else None, fitted=b - a >= MIN_FLIGHT_FRAMES)
        if flight["fitted"]:
            _fit(flight, position, fps)
        flights.append(flight)
    return flights


def _fit(flight, position, fps):
    """Fit a free fall to the flight, then find where it really began and ended.

    A ball that has just left the hand is still within 1.5 cm of it, so the real release is earlier than the
    first free frame: it is the first frame that is already on the fitted flight. The same goes for the catch.
    """
    a, b = flight["first"], flight["last"] + 1
    t = (np.arange(a, b) - a) / fps
    fall = np.zeros((len(t), 3))
    fall[:, 1] = 0.5 * G * t**2
    straight = position[a:b] + fall  # a true free fall is a straight line after removing gravity
    design = np.c_[np.ones_like(t), t]
    coef = np.linalg.lstsq(design, straight, rcond=None)[0]  # row 0: position at frame a, row 1: velocity
    flight["fit_rms_mm"] = float(np.sqrt(((straight - design @ coef) ** 2).sum(axis=1).mean()) * 1000)
    flight["gravity"] = float(-2 * np.polyfit(t, position[a:b, 1], 2)[0])

    def place(frame):
        dt = (frame - a) / fps
        return coef[0] + coef[1] * dt - np.array([0, 0.5 * G * dt**2, 0])

    def speed(frame):
        return coef[1] - np.array([0, G * (frame - a) / fps, 0])

    release, catch, last = a, b - 1, len(position) - 1
    while release > 0 and np.linalg.norm(position[release - 1] - place(release - 1)) <= ON_PARABOLA_M:
        release -= 1
    while catch < last and np.linalg.norm(position[catch + 1] - place(catch + 1)) <= ON_PARABOLA_M:
        catch += 1
    flight.update(release=release, catch=catch)
    flight["release_height"] = float(position[release, 1])
    apex_frame = a + coef[1, 1] / G * fps
    flight["peak"] = float(place(apex_frame)[1]) if release <= apex_frame <= catch else float(position[release : catch + 1, 1].max())
    flight["release_jump"] = (
        float(np.linalg.norm(speed(release + 0.5) - (position[release] - position[release - 1]) * fps)) if release > 0 else 0.0)
    flight["catch_jump"] = (
        float(np.linalg.norm((position[catch + 1] - position[catch]) * fps - speed(catch - 0.5))) if catch < last else 0.0)


def pattern(throws):
    """How the throws follow each other: share of throws from the other hand than the throw before, and share
    of throws caught by the other hand. throws: flights in the order of their release."""
    hands = [f["source"] for f in throws]
    alternate = np.mean([a != b for a, b in zip(hands, hands[1:])]) if len(hands) > 1 else 0.0
    crossing = np.mean([f["source"] != f["target"] for f in throws]) if throws else 0.0
    return float(alternate), float(crossing)


def _ball_gaps(verts, centers, radius, chunk=64):
    """Distance (m) of the closest of these skin points to each ball, negative inside: (T, balls)."""
    out = np.empty(centers.shape[:2], np.float32)
    for a in range(0, len(verts), chunk):
        s = slice(a, a + chunk)
        dist = np.linalg.norm(verts[s, :, None] - centers[s, None], axis=3)
        out[s] = dist.min(axis=1) - radius
    return out


def _palm_side(body, hand):
    """The skin of a hand without the back of the hand, found on the flat template hand (palm facing -Y)."""
    v = body.model.v_template.numpy().astype(np.float64)
    f = body.faces
    face_n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    normals = np.zeros_like(v)
    for k in range(3):
        np.add.at(normals, f[:, k], face_n)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    return hand & (normals[:, 1] < 0.25)


def _feet(body):
    rest = body.rest_vertices
    return {side: np.where((rest[:, 0] * sign > 0) & (rest[:, 1] < body.rest_joints[BODY_JOINT_NAMES.index(f"{side}_ankle"), 1]))[0]
            for side, sign in (("left", 1), ("right", -1))}


def ball_metrics(motion, task, body, verts, joints, arm_check=True):
    """Returns (metrics, timeline, throws): the metrics, per-frame arrays, and one dict per flight."""
    fps, floor_y = motion["fps"], body.floor_y
    num_frames = len(verts)
    spec, rules = task["balls"], task["juggle"]
    radius, count = spec["radius"], spec["count"]
    centers = motion["balls_transl"].astype(np.float64)
    parts = _body_parts(body)
    out = []

    def add(group, key, label, value, unit, meaning, target=None, ok=None):
        out.append(dict(group=group, key=key, label=label, value=value if isinstance(value, str) else round(float(value), 2),
                        unit=unit, target=target, ok=None if ok is None else bool(ok), meaning=meaning))

    # --- who holds which ball
    c32 = centers.astype(np.float32)
    palm = {s: np.where(_palm_side(body, parts[s]))[0] for s in ("left", "right")}
    gap = np.stack([_ball_gaps(verts[:, palm[s]], c32, radius) for s in ("left", "right")], axis=2)  # (T, balls, hands)
    state = np.stack([hand_states(gap[:, i], fps) for i in range(count)], axis=1)  # (T, balls)
    held = state >= 0
    flights = [f for i in range(count) for f in find_flights(i, centers[:, i], state[:, i], fps)]
    fitted = [f for f in flights if f["fitted"]]
    throws = sorted(fitted, key=lambda f: f["release"])
    all_hand = np.where(parts["left"] | parts["right"])[0]
    hand_depth = np.maximum(0, -_ball_gaps(verts[:, all_hand], c32, radius).min(axis=1))
    body_depth = np.maximum(0, -_ball_gaps(verts[:, np.where(parts["rest"])[0]], c32, radius).min(axis=1))

    # --- the contact of a held ball, in the middle part of every hold
    contact = np.zeros((num_frames, count))
    unsupported = np.zeros((num_frames, count), bool)
    settled = np.zeros((num_frames, count), bool)
    edge = max(2, round(0.07 * fps))
    for i in range(count):
        for a, b, value in runs(state[:, i]):
            if value < 0:
                continue
            first, last = a + (edge if a else 0), b - (edge if b < num_frames else 0)
            ids = palm["left" if value == 0 else "right"]
            for t in range(first, last):
                skin = verts[t, ids].astype(np.float64)
                near = np.linalg.norm(skin - centers[t, i], axis=1) - radius <= TOUCH_M
                contact[t, i] = pdist(skin[near]).max() * 100 if near.sum() > 1 else 0.0
                settled[t, i] = True
                unsupported[t, i] = not near.any() or skin[near, 1].mean() >= centers[t, i, 1]

    # --- the feet
    feet = _feet(body)
    foot_height = {s: (verts[:, feet[s], 1] - floor_y).min(axis=1) for s in feet}
    stand = rules["standing_foot"]
    lifted = "right" if stand == "left" else "left"
    up = foot_height[lifted] > FOOT_DOWN_M
    wrong = foot_height[stand] > FOOT_DOWN_M
    lifts = [(a, b) for a, b, value in runs(up.astype(int)) if value and b - a >= round(0.1 * fps)]
    lift_start, lift_end = max(lifts, key=lambda r: r[1] - r[0]) if lifts else (None, None)

    # --- balance: the centre of mass of the body against the outline of the feet on the floor. The balls weigh
    # about 0.5 % of the body, which moves the centre of mass by about 2 mm, so they are left out.
    com, body_mass = _center_of_mass(verts, body.faces)
    com_speed = np.linalg.norm(np.gradient(moving_average(com[:, [0, 2]], max(1, fps // 6)), 1 / fps, axis=0), axis=1)
    height = verts[:, :, 1] - floor_y
    outside = np.full(num_frames, np.nan)
    for t in range(num_frames):
        on = {s: feet[s][height[t, feet[s]] < 0.015] for s in feet}
        if up[t]:
            if len(on[stand]):
                outside[t] = _outside_support(com[t, [0, 2]], verts[t, on[stand]][:, [0, 2]].astype(np.float64))
        elif len(on["left"]) and len(on["right"]) and com_speed[t] < 0.3:
            both = np.concatenate([on["left"], on["right"]])
            outside[t] = _outside_support(com[t, [0, 2]], verts[t, both][:, [0, 2]].astype(np.float64))

    arm_depth = _arm_depth(verts, body.faces, parts["arm"], parts["trunk_legs"]) if arm_check else np.zeros(num_frames)

    timeline = {
        "frame": np.arange(num_frames),
        "time_s": np.arange(num_frames) / fps,
        "balls_held_left": (state == 0).sum(axis=1),
        "balls_held_right": (state == 1).sum(axis=1),
        "balls_in_air": (~held).sum(axis=1),
        **{f"ball{i + 1}_height_m": centers[:, i, 1] - floor_y for i in range(count)},
        **{f"ball{i + 1}_gap_mm": gap[:, i].min(axis=1) * 1000 for i in range(count)},
        "hand_into_ball_mm": hand_depth * 1000,
        "body_into_ball_mm": body_depth * 1000,
        "arm_into_body_mm": arm_depth * 1000,
        "left_foot_height_cm": foot_height["left"] * 100,
        "right_foot_height_cm": foot_height["right"] * 100,
        "balance_outside_feet_cm": outside * 100,
        "pelvis_height_m": joints[:, 0, 1].astype(np.float64) - floor_y,
    }

    # --- holding the balls
    group = "Holding the balls"
    still = max(2, round(0.5 * fps))
    n = int((~held[:still]).any(axis=1).sum())
    add(group, "start_all_held", "Frames at the start without all balls in the hands", n, "frames",
        "Frames in the first 0.5 s in which a ball is not in a hand. The person starts by holding all of them.", "0", n == 0)
    n = int((~held[-still:]).any(axis=1).sum())
    add(group, "end_all_held", "Frames at the end without all balls in the hands", n, "frames",
        "Frames in the last 0.5 s in which a ball is not in a hand. The person ends by holding all of them.", "0", n == 0)
    n = int(((state == 0).sum(axis=1) > 2).sum() + ((state == 1).sum(axis=1) > 2).sum())
    add(group, "hand_capacity", "Frames with more than two balls in one hand", n, "frames",
        "One hand does not hold all three balls at once.", "0", n == 0)
    value = contact[settled].min() if settled.any() else 0.0
    add(group, "contact_width_min", "Narrowest contact between a hand and a held ball", value, "cm",
        f"While a ball rests in a hand, the width of the palm-side skin within {TOUCH_M * 1000:g} mm of it, at its smallest. The back "
        "of the hand does not count. A ball in the hand gives 6-7 cm; a ball balancing on a fingertip about 4 cm.",
        f"≥ {MIN_CONTACT_CM:g} cm", value >= MIN_CONTACT_CM)
    n = int(unsupported.sum())
    add(group, "frames_unsupported", "Ball-frames in which a held ball has no support from below", n, "frames",
        "Frames and balls in which the skin touching a held ball is not below the ball's centre on average. A ball "
        "lies on a hand. It cannot hang under it or stick to it.", "0", n == 0)
    value = hand_depth.max() * 1000
    add(group, "hand_depth_max", "Deepest hand skin inside a ball", value, "mm",
        f"How far hand skin goes into a ball (worst at frame {int(hand_depth.argmax())}). Skin gives a little, but fingers "
        "must not pass through a ball.", "≤ 8 mm", value <= 8)

    # --- the balls in the air
    group = "The balls in the air"
    if not throws:
        add(group, "juggles", "The balls are thrown", "no", "", "No ball ever flies, so nothing else can be measured.", "yes", False)
        return out, timeline, []
    worst = max(throws, key=lambda f: abs(f["gravity"] - G))
    value = abs(worst["gravity"] - G) / G * 100
    add(group, "gravity_error", "Largest gravity error of a flight", value, "%",
        f"For every flight, the gravity that fits its height over time, against the real {G} m/s². The worst flight "
        f"(ball {worst['ball'] + 1}, frame {worst['first']}) has {worst['gravity']:.2f} m/s².", "≤ 3 %", value <= 3)
    worst = max(throws, key=lambda f: f["fit_rms_mm"])
    value = worst["fit_rms_mm"]
    add(group, "flight_fit_mm", "Largest difference between a flight and a free fall", value, "mm",
        f"Average distance between a flight and the best free fall with real gravity, for the worst flight (ball "
        f"{worst['ball'] + 1}, frame {worst['first']}). A ball in the air cannot steer, slow down or hang.", "≤ 3 mm", value <= 3)
    n = sum(not f["fitted"] for f in flights)
    add(group, "flights_too_short", "Flights too short to be a throw", n, "flights",
        f"Times a ball leaves the hand for less than {MIN_FLIGHT_FRAMES / fps:.2f} s. A ball that hops out of a hand and back "
        "is not thrown, or the hand does not stay with it.", "0", n == 0)
    n = sum(f["target"] is None for f in flights)
    add(group, "flights_uncaught", "Balls that are never caught", n, "flights",
        "Flights that do not end in a hand: the ball is dropped or still flying at the end of the clip.", "0", n == 0)
    value = min(f["peak"] - f["release_height"] for f in throws) * 100
    add(group, "throw_height_min", "Lowest throw", value, "cm",
        "Smallest rise of a ball above the height where it left the hand. A real throw goes up.", "≥ 20 cm", value >= 20)
    value = max(f["peak"] for f in throws) - floor_y
    add(group, "throw_peak_max", "Highest point of any ball", value, "m",
        "The largest height of a ball above the floor. Above about 2.1 m it also leaves the picture.", "≤ 2.1 m", value <= 2.1)
    speed = np.linalg.norm(np.diff(centers, axis=0), axis=2) * fps
    value = speed.max()
    add(group, "ball_speed_max", "Fastest ball", value, "m/s", "Highest speed of a ball. A jump shows up here.", "≤ 6 m/s", value <= 6)
    pairs = [(i, j) for i in range(count) for j in range(i + 1, count)]
    overlap = max((2 * radius - np.linalg.norm(centers[:, i] - centers[:, j], axis=1)).max() for i, j in pairs)
    value = max(0.0, overlap) * 1000
    add(group, "ball_overlap_mm", "Deepest two balls go into each other", value, "mm",
        "Balls are solid: they cannot pass through each other, in the air or in a hand.", "≤ 2 mm", value <= 2)
    value = body_depth.max() * 1000
    add(group, "body_depth_max", "Deepest body skin (not hands) inside a ball", value, "mm",
        f"How far arms, trunk or head go into a ball (worst at frame {int(body_depth.argmax())}).", "≤ 8 mm", value <= 8)

    # --- throwing and catching
    group = "Throwing and catching"
    first_lift = lift_start if lift_start is not None else num_frames
    last_down = lift_end if lift_end is not None else num_frames
    two_feet = sum(f["release"] < first_lift for f in throws)
    one_foot = sum(first_lift <= f["release"] < last_down for f in throws)
    need = rules["min_throws_two_feet"]
    add(group, "throws_two_feet", "Throws before the foot lifts", two_feet, "throws",
        "Throws while the person still stands on both feet.", f"≥ {need}", two_feet >= need)
    need = rules["min_throws_one_foot"]
    add(group, "throws_one_foot", "Throws on one foot", one_foot, "throws",
        "Throws while one foot is in the air.", f"≥ {need}", one_foot >= need)
    per_ball = [sum(f["ball"] == i for f in throws) for i in range(count)]
    need = (rules["min_throws_two_feet"] + rules["min_throws_one_foot"]) // count
    add(group, "throws_per_ball_min", "Throws of the least thrown ball", min(per_ball), "throws",
        f"All {count} balls have to take part: {per_ball} throws per ball.", f"≥ {need}", min(per_ball) >= need)
    alternate, crossing = pattern(throws)
    add(group, "hands_alternate", "Throws that come from the other hand than the throw before", alternate * 100, "%",
        "In the classic pattern the hands take turns.", "≥ 95 %", alternate >= 0.95)
    add(group, "throws_cross", "Throws caught by the other hand", crossing * 100, "%",
        "In the classic pattern every ball crosses from one hand to the other.", "≥ 95 %", crossing >= 0.95)
    pause = max(np.diff([f["release"] for f in throws]) / fps) if len(throws) > 1 else 0.0
    add(group, "longest_pause", "Longest time between two throws", pause, "s",
        "Juggling does not stop, also not while the foot lifts. With three balls, two throws are usually 0.3-0.45 s apart.",
        "≤ 0.6 s", pause <= 0.6)
    value = max(f["release_jump"] for f in throws)
    add(group, "release_jump", "Largest jump in a ball's speed at the release", value, "m/s",
        "Difference between the speed of a ball just before and just after it leaves the hand. A hand has to bring the ball "
        "up to speed and let go: a ball that shoots out of a slow hand shows up here.", "≤ 1.5 m/s", value <= 1.5)
    value = max(f["catch_jump"] for f in throws)
    add(group, "catch_jump", "Largest jump in a ball's speed at the catch", value, "m/s",
        "Difference between the speed of a ball just before and just after it is caught. A hand gives way and goes down with "
        "the ball. A hand that stands still stops it dead: about 3 m/s.", "≤ 2.5 m/s", value <= 2.5)
    dwell = []
    for i in range(count):
        for a, b, value in runs(state[:, i]):
            if value >= 0 and a > 0 and b < num_frames:
                dwell.append((b - a) / fps)
    value = min(dwell) if dwell else 0.0
    add(group, "dwell_min", "Shortest time a ball stays in a hand", value, "s",
        "From catch to next throw. A ball that bounces off the hand is not caught and thrown.", "≥ 0.12 s", value >= 0.12)

    # --- standing on one foot
    group = "Standing on one foot"
    n = len(lifts)
    add(group, "foot_lifts", f"Times the {lifted} foot leaves the floor", n, "times",
        "It is lifted once and comes down once. More means it touches down in between.", "1", n == 1)
    n = int(wrong.sum())
    add(group, "standing_foot_up", f"Frames the {stand} (standing) foot is off the floor", n, "frames",
        f"The person stands on the {stand} foot all the time.", "0", n == 0)
    if lift_start is None:
        add(group, "one_foot_time", "Time on one foot", 0.0, "s", "The foot is never lifted.", f"≥ {rules['min_one_foot_s']:g} s", False)
        return out, timeline, flights
    value = (lift_end - lift_start) / fps
    need = rules["min_one_foot_s"]
    add(group, "one_foot_time", "Time on one foot", value, "s", "Longest time the foot stays off the floor.", f"≥ {need:g} s", value >= need)
    value = np.median(foot_height[lifted][lift_start:lift_end]) * 100
    add(group, "foot_height", "Typical height of the lifted foot", value, "cm",
        "Height of its lowest skin above the floor. It has to be clearly lifted, not hovering.", "≥ 10 cm", value >= 10)
    catches = [f["catch"] for f in throws if f["target"] is not None]
    value = (lift_end - max(catches)) / fps if catches else -1.0
    add(group, "catch_before_foot_down", "Time from the last catch to the foot coming down", value, "s",
        "The person catches all the balls first and only then puts the foot down.", "≥ 0.2 s", value >= 0.2)
    last_held = held[lift_end - 1 :].all()
    add(group, "all_held_at_foot_down", "All balls in the hands when the foot comes down", "yes" if last_held else "no", "",
        "From the moment the foot comes down, no ball leaves a hand.", "yes", bool(last_held))
    during = outside[lift_start:lift_end]
    n = int(np.nansum(during > 0.02) + np.isnan(during).sum())
    add(group, "one_foot_off_balance", "Frames off balance on one foot", n, "frames",
        f"Frames on one foot in which the body's centre of mass ({body_mass:.0f} kg) is more than 2 cm outside the outline of the "
        "standing foot, seen from above. The person would fall over. The weight has to move over the foot before it lifts.",
        "0", n == 0)
    value = np.nanmax(during) * 100 if np.isfinite(during).any() else 99.0
    add(group, "one_foot_balance_worst", "Worst balance margin on one foot", value, "cm",
        "Largest distance of the centre of mass outside the standing foot. Negative means it always stayed inside.")
    both = np.r_[outside[:lift_start], outside[lift_end:]]
    n = int(np.nansum(both > 0.03))
    add(group, "two_feet_off_balance", "Frames off balance on two feet", n, "frames",
        "Frames with both feet on the floor and the body moving slowly in which the centre of mass is more than 3 cm outside "
        "the outline of the feet.", "0", n == 0)
    pelvis = joints[:, 0, [0, 2]].astype(np.float64)
    value = np.linalg.norm(pelvis - pelvis[0], axis=1).max() * 100
    add(group, "stays_on_spot", "Largest distance of the pelvis from where it starts", value, "cm",
        "The person stays in one place. Moving the weight over one foot takes about 10 cm.", "≤ 20 cm", value <= 20)
    head_rest = body.rest_joints[15, 1] - floor_y
    value = (joints[-1, 15, 1] - floor_y) / head_rest * 100
    add(group, "final_upright", "Standing up at the end", value, "% of height",
        "Height of the head in the last frame, as a share of its height in a straight stance.", "≥ 96 %", value >= 96)

    # --- the body
    group = "Body"
    value = arm_depth.max() * 1000
    add(group, "arm_depth_max", "Deepest forearm or hand skin inside the trunk or legs", value, "mm",
        f"How far forearms and hands go into the trunk or legs (worst at frame {int(arm_depth.argmax())}).", "≤ 15 mm", value <= 15)
    _add_joint_limits(add, motion["body_pose"])

    # --- how it looks (information only)
    group = "How the juggling looks"
    releases = [f["release"] for f in throws]
    span = (releases[-1] - releases[0]) / fps
    if span > 0:
        add(group, "throw_rate", "Throws per second", (len(releases) - 1) / span, "1/s", "How fast the balls go round.")
    add(group, "flight_time", "Typical time in the air", np.median([(f["catch"] - f["release"]) / fps for f in throws]), "s",
        "From release to catch.")
    if dwell:
        add(group, "dwell_time", "Typical time in a hand", np.median(dwell), "s", "From catch to next throw.")
    peaks = np.array([f["peak"] - floor_y for f in throws])
    add(group, "peak_height", "Typical highest point of a throw", np.median(peaks), "m", "Height above the floor.")
    add(group, "peak_spread", "Variation of the highest point", peaks.std() * 100, "cm",
        "Real people vary by a few centimetres. 0 looks like a machine.")
    gaps = np.diff(releases) / fps
    add(group, "rhythm_spread", "Variation of the time between throws", gaps.std() * 1000, "ms",
        "Real people vary a little. 0 looks like a machine.")
    value = np.ptp(com[lift_start:lift_end, [0, 2]], axis=0)
    add(group, "one_foot_sway", "Sway of the centre of mass on one foot", np.linalg.norm(value) * 100, "cm",
        "How far the body drifts while balancing. A real person keeps correcting.")
    return out, timeline, flights
