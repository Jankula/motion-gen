"""Check the juggling measurements, before an agent relies on them.

    python -m hoienv.selftest_juggling            # a correct clip has to pass, every fake has to be caught
    python -m hoienv.selftest_juggling --render   # also renders the correct clip into runs/_selftest_juggling/

Builds a plain but correct juggling clip: legs and trunk from a few simple rules, arms from inverse kinematics,
balls in true free fall between the hands. It has to meet every target, which also shows that the targets can be
reached. Then the clip is broken on purpose, and each fake has to be caught by the measurement made for it.

The agent never sees this file. It is a test of the measuring tool, not an example of good motion.
"""
import argparse
import json

import numpy as np
from scipy.spatial.transform import Rotation

from walkenv.body import Body, _zero_motion

from .evaluate import evaluate
from .juggling import G, pattern
from .paths import BODY_INFO, RUNS_DIR
from .tasks import load_task

FPS = 30
FRAMES = 600
BEAT = 9  # frames between two throws
FLIGHT = 16  # frames in the air
VACANT = 7  # frames from a throw to the next catch of the same hand
FIRST_THROW = 36
THROWS = 45
SIDES = {"left": 1.0, "right": -1.0}
ROWS = {"left": (15, 17, 19), "right": (16, 18, 20)}  # body_pose rows of shoulder, elbow, wrist
JOINTS = {"left": (16, 18, 20), "right": (17, 19, 21)}
THROW_POINT = np.array([0.11, -0.14, 0.24])  # x is mirrored for the right hand
CATCH_POINT = np.array([0.27, -0.01, 0.24])
REST_POINT = np.array([0.17, -0.08, 0.24])
FINGER_SLOT = 0.074  # distance of a second ball from the first, along the fingers
OPEN_HAND, CUPPED_HAND = 1.0, 0.35  # share of the relaxed curl that is removed


def smooth(a, b, t):
    s = np.clip((np.asarray(t, float) - a) / (b - a), 0, 1)
    return s * s * (3 - 2 * s)


def mirrored(point, side):
    return point * np.array([SIDES[side], 1, 1])


def hand_axes(side):
    """The direction the palm faces and the direction the fingers point: palm up, turned in a little."""
    s = SIDES[side]
    normal = np.array([-0.15 * s, 1.0, 0.0])
    normal /= np.linalg.norm(normal)
    fingers = np.array([-0.35 * s, 0.0, 1.0])
    fingers -= (fingers @ normal) * normal
    return normal, fingers / np.linalg.norm(fingers)


def hermite(key_a, key_b, frames):
    """Cubic from (frame, position, velocity) to (frame, position, velocity), evaluated at the given frames."""
    (fa, pa, va), (fb, pb, vb) = key_a, key_b
    duration = (fb - fa) / FPS
    s = ((frames - fa) / (fb - fa))[:, None]
    return ((2 * s**3 - 3 * s**2 + 1) * pa + (s**3 - 2 * s**2 + s) * duration * va
            + (-2 * s**3 + 3 * s**2) * pb + (s**3 - s**2) * duration * vb)


def hand_path(side, throw_frames, catch_frames, throw_speed, catch_speed):
    """Where the palm of one hand is in every frame."""
    throw, catch, rest = (mirrored(p, side) for p in (THROW_POINT, CATCH_POINT, REST_POINT))
    still = np.zeros(3)
    keys = [(0, rest, still), (throw_frames[0] - 15, rest, still)]
    for frame in throw_frames:
        keys.append((frame, throw, throw_speed))
        keys.append((frame + VACANT, catch, catch_speed))
    last = max(catch_frames)
    if last > keys[-1][0]:
        keys.append((last, catch, catch_speed))
    keys += [(last + 30, rest, still), (FRAMES - 1, rest, still)]
    path = np.empty((FRAMES, 3))
    for a, b in zip(keys, keys[1:]):
        frames = np.arange(a[0], b[0] + 1)
        path[frames] = hermite(a, b, frames.astype(float))
    return path


def solve_arm(body, side, shoulder, palm):
    """Rotations of shoulder, elbow and wrist that put the palm centre at the palm target. shoulder, palm: (T, 3)."""
    js, je, jw = JOINTS[side]
    rest = body.rest_joints.astype(np.float64)
    upper_rest, fore_rest = rest[je] - rest[js], rest[jw] - rest[je]
    upper, fore = np.linalg.norm(upper_rest), np.linalg.norm(fore_rest)
    normal, fingers = hand_axes(side)
    s = SIDES[side]
    x_axis, y_axis = s * fingers, -normal
    hand = np.stack([x_axis, y_axis, np.cross(x_axis, y_axis)], axis=1)  # columns: where the rest axes of the hand go
    info = json.loads(BODY_INFO.read_text(encoding="utf-8"))
    palm_rest = np.array(info["hands"][side]["skin_points"][f"{side}_palm_center"]["rest"]) - np.array(info["joints"][f"{side}_wrist"])
    wrist = palm - hand @ palm_rest

    to_wrist = wrist - shoulder
    dist = np.linalg.norm(to_wrist, axis=1, keepdims=True)
    reach = upper + fore - 1e-3
    assert dist.max() < reach, f"{side} hand out of reach: {dist.max():.3f} of {reach:.3f}"
    u = to_wrist / dist
    pole = np.array([0.4 * s, -1.0, -0.3])
    perp = pole - (u @ pole)[:, None] * u
    perp /= np.linalg.norm(perp, axis=1, keepdims=True)
    cos_a = (upper**2 + dist**2 - fore**2) / (2 * upper * dist)
    elbow = shoulder + upper * (cos_a * u + np.sqrt(1 - cos_a**2) * perp)

    out = [np.empty((len(palm), 3)) for _ in range(3)]
    for t in range(len(palm)):
        d1 = (elbow[t] - shoulder[t]) / upper
        d2 = (wrist[t] - elbow[t]) / fore
        side_of_bend = d2 - (d2 @ d1) * d1
        side_of_bend /= np.linalg.norm(side_of_bend)
        w_upper = Rotation.align_vectors([d1, side_of_bend], [upper_rest / upper, [0, 0, 1]], weights=[1000, 1])[0]
        w_fore = Rotation.align_vectors([d2, -normal], [fore_rest / fore, [0, 1, 0]], weights=[1000, 1])[0]
        w_hand = Rotation.from_matrix(hand)
        out[0][t] = w_upper.as_rotvec()
        out[1][t] = (w_upper.inv() * w_fore).as_rotvec()
        out[2][t] = (w_fore.inv() * w_hand).as_rotvec()
    return out


def clip(body, task, lift_foot=True, shift_weight=True, touch_down_at=None, foot_down=466, throw_factor=1.0,
         catch_give=0.5, gravity=G, on_fingertips=False):
    """A correct juggling clip, or one with a single thing wrong. Returns the motion and the throws (ball, from, to, frame)."""
    radius = task["balls"]["radius"]
    frames = np.arange(FRAMES, dtype=float)
    motion = _zero_motion(FRAMES)
    motion["fps"] = FPS

    # --- legs: the pelvis moves over the left foot, then the right leg lifts
    weight = smooth(170, 200, frames) - smooth(foot_down + 22, foot_down + 55, frames)
    shift = (0.095 if shift_weight else 0.0) * weight
    lift = (smooth(200, 222, frames) - smooth(foot_down, foot_down + 22, frames)) * (1.0 if lift_foot else 0.0)
    if touch_down_at is not None:
        lift = lift * (1 - smooth(touch_down_at, touch_down_at + 10, frames) + smooth(touch_down_at + 12, touch_down_at + 22, frames))
    leg = 0.84
    tilt = np.arcsin(shift / leg)
    motion["transl"][:, 0] = shift
    motion["transl"][:, 1] = -leg * (1 - np.cos(tilt))
    for hip, ankle in ((0, 6), (1, 7)):
        motion["body_pose"][:, hip, 2] = -tilt
        motion["body_pose"][:, ankle, 2] = tilt
    motion["body_pose"][:, 1, 0] = -0.75 * lift  # right hip forward
    motion["body_pose"][:, 4, 0] = 1.25 * lift  # right knee
    motion["body_pose"][:, 7, 0] = -0.4 * lift  # right ankle: the foot stays nearly level

    # --- the throws: right hand first, hands alternate
    flight_s = FLIGHT / FPS
    hand_of = lambda k: "right" if k % 2 == 0 else "left"  # noqa: E731
    other = {"left": "right", "right": "left"}
    throw_frames = [FIRST_THROW + k * BEAT for k in range(THROWS)]
    speed = {}
    for side in SIDES:
        start, end = mirrored(THROW_POINT, side), mirrored(CATCH_POINT, other[side])
        speed[side] = (end - start + np.array([0, 0.5 * G * flight_s**2, 0])) / flight_s
    arrival = {side: speed[other[side]] - np.array([0, G * flight_s, 0]) for side in SIDES}

    palm, center = {}, {}
    for side in SIDES:
        mine = [f for k, f in enumerate(throw_frames) if hand_of(k) == side]
        caught = [f + FLIGHT for k, f in enumerate(throw_frames) if hand_of(k) == other[side]]
        palm[side] = hand_path(side, mine, caught, speed[side] * throw_factor, arrival[side] * catch_give)
        palm[side][:, 0] += shift
        js, _, _ = JOINTS[side]
        shoulder = body.rest_joints[js].astype(np.float64) + motion["transl"].astype(np.float64)
        rows = ROWS[side]
        for row, rotvec in zip(rows, solve_arm(body, side, shoulder, palm[side])):
            motion["body_pose"][:, row] = rotvec
        normal, fingers = hand_axes(side)
        center[side] = palm[side] + normal * (radius - 0.002)
        if on_fingertips:
            center[side] = center[side] + fingers * 0.125 + normal * 0.035

    # --- the balls: on the palm while held, in free fall in between
    slot = {side: hand_axes(side)[1] * FINGER_SLOT + hand_axes(side)[0] * -0.006 for side in SIDES}
    balls = np.zeros((FRAMES, 3, 3))
    throws = []
    order = [0, 2, 1]  # the balls in the order of their first throw
    for ball_index, ball in enumerate(order):
        mine = list(range(ball_index, THROWS, 3))
        side = hand_of(mine[0])
        previous_catch = 0
        for k in mine:
            frame = throw_frames[k]
            balls[previous_catch : frame + 1, ball] = center[side][previous_catch : frame + 1]
            start = center[side][frame]
            side = other[side]
            land = frame + FLIGHT
            end = center[side][land]
            velocity = (end - start + np.array([0, 0.5 * gravity * flight_s**2, 0])) / flight_s
            t = ((np.arange(frame, land + 1) - frame) / FPS)[:, None]
            balls[frame : land + 1, ball] = start + velocity * t - np.array([0, 0.5 * gravity, 0]) * t**2
            throws.append((ball, other[side], side, frame))
            previous_catch = land
        balls[previous_catch:, ball] = center[side][previous_catch:]

    # --- two balls in one hand: at the start in the right hand, at the end in the hand that catches twice.
    # The ball that waits lies on the fingers and rolls to the palm when it is free.
    waiting = order[2]
    roll_in = 1 - smooth(FIRST_THROW, FIRST_THROW + 12, frames)
    balls[:, waiting] += roll_in[:, None] * slot["right"]
    first_last = throw_frames[THROWS - 3] + FLIGHT  # third-last throw, caught and kept by the same hand as the last throw
    keeper = order[(THROWS - 3) % 3]
    holder = other[hand_of(THROWS - 3)]
    roll_out = smooth(first_last, first_last + 12, frames)
    balls[:, keeper] += roll_out[:, None] * slot[holder]

    # --- fingers: curled round one ball, open for two
    for side in SIDES:
        mean = getattr(body.model, f"{side}_hand_mean").numpy().reshape(15, 3)
        two = roll_in if side == "right" else 0 * frames
        if side == holder:
            two = np.maximum(two, roll_out)
        share = CUPPED_HAND + (OPEN_HAND - CUPPED_HAND) * two
        motion[f"{side}_hand_pose"] = (-share[:, None, None] * mean).astype(np.float32)
    motion["balls_transl"] = balls.astype(np.float32)
    return motion, throws


def _changed(motion, **changes):
    return {**motion, **changes}


def fakes(body, task):
    """(name, motion, the measurements that have to catch it)."""
    good, throws = clip(body, task)
    balls = good["balls_transl"]
    ball, _, _, frame = throws[20]
    span = np.arange(frame, frame + FLIGHT + 1)

    straight = balls.copy()  # a ball flies in a straight line, as if there were no gravity
    straight[span, ball] = np.linspace(balls[span[0], ball], balls[span[-1], ball], len(span))
    teleport = balls.copy()  # a ball jumps sideways in the middle of a flight
    teleport[span[8:-1], ball] += [0.25, 0, 0]
    dropped = balls.copy()  # a catch is missed: the ball falls to the floor and stays there
    t = (np.arange(frame, FRAMES) - frame) / FPS
    at = balls[frame, ball]
    velocity = (balls[frame + 1, ball] - balls[frame, ball]) * FPS
    fall = at + velocity * t[:, None] - np.array([0, 0.5 * G, 0]) * t[:, None] ** 2
    floor = body.floor_y + task["balls"]["radius"]
    landed = np.argmax(fall[:, 1] < floor)
    fall[landed:] = fall[landed] * [1, 0, 1] + [0, floor, 0]
    dropped[frame:, ball] = fall
    under = balls.copy()  # the balls hang under the hands
    under[:] -= [0, 2 * task["balls"]["radius"] + 0.04, 0]
    through = balls.copy()  # a ball flies through the chest
    through[span[1:-1], ball] += [0, 0, -0.3]
    same_place = balls.copy()  # two balls in the same place in the hand
    same_place[: FIRST_THROW - 2, 2] = balls[: FIRST_THROW - 2, 0] + [0.01, 0, 0]

    return good, [
        ("a ball flies straight", _changed(good, balls_transl=straight), ["gravity_error", "flight_fit_mm"]),
        ("gravity is too weak", clip(body, task, gravity=6.0)[0], ["gravity_error"]),
        ("a ball jumps in the air", _changed(good, balls_transl=teleport), ["flight_fit_mm", "ball_speed_max"]),
        ("a catch is missed", _changed(good, balls_transl=dropped), ["flights_uncaught", "end_all_held"]),
        ("the balls hang under the hands", _changed(good, balls_transl=under), ["start_all_held"]),
        ("a ball flies through the chest", _changed(good, balls_transl=through), ["body_depth_max"]),
        ("two balls in the same place", _changed(good, balls_transl=same_place), ["ball_overlap_mm"]),
        ("the balls balance on the fingertips", clip(body, task, on_fingertips=True)[0], ["contact_width_min"]),
        ("the hand does not throw", clip(body, task, throw_factor=0.2)[0], ["release_jump"]),
        ("the hand does not give way", clip(body, task, catch_give=-0.1)[0], ["catch_jump"]),
        ("the foot is never lifted", clip(body, task, lift_foot=False)[0], ["foot_lifts", "one_foot_time"]),
        ("the foot touches down in between", clip(body, task, touch_down_at=320)[0], ["foot_lifts"]),
        ("no weight shift before the lift", clip(body, task, shift_weight=False)[0], ["one_foot_off_balance"]),
        ("the foot comes down before the last catch", clip(body, task, foot_down=420)[0], ["catch_before_foot_down"]),
    ]


def check_pattern():
    """The pattern measurement on hand-made lists of throws."""
    cascade = [dict(source=k % 2, target=1 - k % 2) for k in range(12)]
    one_hand = [dict(source=0, target=1) for _ in range(12)]
    columns = [dict(source=k % 2, target=k % 2) for k in range(12)]
    assert pattern(cascade) == (1.0, 1.0)
    assert pattern(one_hand) == (0.0, 1.0)
    assert pattern(columns) == (1.0, 0.0)
    print("ok   pattern: alternating hands and crossing throws are told apart")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--only-correct", action="store_true", help="skip the fakes")
    args = ap.parse_args()
    body = Body()
    task = load_task("juggling")
    check_pattern()
    good, broken = fakes(body, task) if not args.only_correct else (clip(body, task)[0], [])

    metrics = evaluate(good, task, body)[0]
    failed = [m for m in metrics if m["ok"] is False]
    print(f"{'ok  ' if not failed else 'FAIL'} correct clip: {sum(m['ok'] is True for m in metrics)} targets met, {len(failed)} missed")
    for m in metrics:
        print(f"       {'    ' if m['ok'] is None else (' ok ' if m['ok'] else 'MISS')} {m['label']}: {m['value']} {m['unit']}  ({m['target']})")
    all_ok = not failed
    for name, motion, must_fail in broken:
        result = evaluate(motion, task, body, arm_check=False)[0]
        caught = [m["key"] for m in result if m["ok"] is False]
        ok = all(k in caught for k in must_fail)
        all_ok &= ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}: caught {caught} (expected {must_fail})", flush=True)
    if broken:  # the task asks for the other foot: the same clip now stands on the wrong one
        other_foot = {**task, "juggle": {**task["juggle"], "standing_foot": "right"}}
        caught = [m["key"] for m in evaluate(good, other_foot, body, arm_check=False)[0] if m["ok"] is False]
        ok = "standing_foot_up" in caught
        all_ok &= ok
        print(f"{'ok  ' if ok else 'FAIL'} stands on the wrong foot: caught {caught}", flush=True)
    print("ALL OK" if all_ok else "SOME CHECKS FAILED")

    if args.render:
        from walkenv.render import render
        out = RUNS_DIR / "_selftest_juggling"
        out.mkdir(parents=True, exist_ok=True)
        path = out / "motion.npz"
        np.savez(path, **good)
        for written in render(path, out, task=task, videos=False, sheet_start=6.5, sheet_duration=0.6, sheet_cols=8, body=body):
            print(written)


if __name__ == "__main__":
    main()
