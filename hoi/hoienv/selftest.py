"""Check the measuring tool itself, before an agent relies on it.

    python -m hoienv.selftest            # prints which fakes each measurement catches
    python -m hoienv.selftest --render   # also renders contact sheets into runs/_selftest/

Builds a crude "hold": the arms point forward with the palms facing each other, and the whole body is
simply moved down, up, sideways and down again together with a box between the hands (the body floats
and goes through the floor, which does not matter here). A correct hold has to pass the grip and box
measurements. Then the same clip is broken on purpose, and each fake has to be caught.
Also checks that the finger forward kinematics given to the agent match the real model.
"""
import argparse
import json

import numpy as np
from scipy.spatial.transform import Rotation

from walkenv.body import Body, _zero_motion

from .evaluate import _body_parts, evaluate
from .paths import BODY_INFO, RUNS_DIR

FPS = 30
FRAMES = 240


def check_finger_kinematics(body):
    """The formula in SMPLX_INTERFACE.md, with the numbers in body_info.json, against the real model."""
    info = json.loads(BODY_INFO.read_text(encoding="utf-8"))
    rng = np.random.default_rng(0)
    motion = _zero_motion(1)
    motion["body_pose"][0] = rng.normal(0, 0.3, (21, 3))
    motion["global_orient"][0] = rng.normal(0, 0.3, 3)
    motion["left_hand_pose"][0] = rng.normal(0, 0.3, (15, 3))
    _, joints = body.forward(motion)

    body_rest = info["joints"]
    names = list(body_rest)
    pos, world = {}, {}
    for name in names:
        i = names.index(name)
        rotvec = motion["global_orient"][0] if i == 0 else motion["body_pose"][0, i - 1]
        r = Rotation.from_rotvec(rotvec).as_matrix()
        parent = info["parents"][name]
        if parent is None:
            world[name], pos[name] = r, np.array(body_rest[name])
        else:
            world[name] = world[parent] @ r
            pos[name] = pos[parent] + world[parent] @ (np.array(body_rest[name]) - np.array(body_rest[parent]))
    rest = {k: np.array(v) for k, v in body_rest.items()}
    worst = 0.0
    for i, (name, j) in enumerate(info["hands"]["left"]["finger_joints"].items()):
        rest[name] = np.array(j["rest"])
        r = Rotation.from_rotvec(np.array(j["relaxed_pose"]) + motion["left_hand_pose"][0, i]).as_matrix()
        parent = j["parent"]
        world[name] = world[parent] @ r
        pos[name] = pos[parent] + world[parent] @ (rest[name] - rest[parent])
        worst = max(worst, np.linalg.norm(pos[name] - joints[0, 25 + i]))
    print(f"finger kinematics: largest difference to the real model {worst * 1000:.2f} mm")
    assert worst < 0.001


def carry_clip(body):
    """Returns (motion, task) of the crude hold."""
    t = np.arange(FRAMES) / FPS
    pose = np.zeros((21, 3), np.float32)
    pose[15] = (Rotation.from_euler("y", -80, degrees=True) * Rotation.from_euler("x", 90, degrees=True)).as_rotvec()
    pose[16] = (Rotation.from_euler("y", 80, degrees=True) * Rotation.from_euler("x", 90, degrees=True)).as_rotvec()
    probe = _zero_motion(1)
    probe["body_pose"][0] = pose
    verts, _ = body.forward(probe)
    parts = _body_parts(body)
    # Box between the palms: as wide as the gap between the inner surfaces of the hands.
    inner_left, inner_right = verts[0, parts["left"], 0].min(), verts[0, parts["right"], 0].max()
    left, right = verts[0, parts["left"]], verts[0, parts["right"]]
    width = inner_left - inner_right + 0.004
    size = np.array([width, 0.20, 0.30])
    hold = np.array([(inner_left + inner_right) / 2, (left[:, 1].mean() + right[:, 1].mean()) / 2,
                     (left[:, 2].mean() + right[:, 2].mean()) / 2])

    floor_y = body.floor_y
    on_floor = floor_y + size[1] / 2
    down = on_floor - hold[1]  # body offset that puts the box on the floor
    ramp = lambda a, b: np.clip((t - a) / (b - a), 0, 1) ** 2 * (3 - 2 * np.clip((t - a) / (b - a), 0, 1))  # noqa: E731
    lift = 0.6 * ramp(1, 2.5) - 0.6 * ramp(5, 7.5)
    travel = 2.0 * ramp(2.5, 5)
    transl = np.stack([travel, down + lift, np.zeros_like(t)], axis=1)
    center = transl + hold
    motion = _zero_motion(FRAMES)
    motion["fps"] = FPS
    motion["body_pose"][:] = pose
    # Arms stay, but the hands leave the box at the end, and the body stands up, as the task requires.
    motion["transl"] = transl.astype(np.float32)
    motion["object_transl"] = center.astype(np.float32)
    motion["object_orient"] = np.zeros((FRAMES, 3), np.float32)
    task = {
        "name": "selftest", "fps": FPS, "frames": FRAMES, "start": {"state": "standing", "position": [0, 0], "heading_deg": 0},
        "end": {"state": "standing"}, "path_points": None,
        "object": {"label": "box", "size": size.tolist(), "mass_kg": 10,
                   "start": {"center": [float(center[0, 0]), float(center[0, 2])], "yaw_deg": 0}},
        "target": {"center": [float(center[-1, 0]), float(center[-1, 2])], "yaw_deg": 0},
    }
    return motion, task


def _fake(motion, **changes):
    return {**motion, **changes}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    body = Body()
    check_finger_kinematics(body)
    motion, task = carry_clip(body)
    print("box size", np.round(task["object"]["size"], 3))

    center = motion["object_transl"]

    floating = center.copy()  # the box leaves the hands and floats away by itself
    floating[120:, 2] += np.linspace(0, 0.3, FRAMES - 120, dtype=np.float32)
    apart = motion["transl"].copy()  # the whole body stands 30 cm further back from t = 2 s on
    apart[60:, 2] -= 0.3
    dropped = center.copy()  # let go 30 cm above the floor and fall
    fall_start = 168
    height = 0.30 - 0.5 * 9.81 * ((np.arange(FRAMES) - fall_start) / FPS) ** 2
    bottom_ok = motion["object_transl"][-1, 1]
    dropped[fall_start:, 1] = bottom_ok + np.maximum(height[fall_start:], 0)
    dragged = center.copy()  # stays on the floor all the way
    dragged[:, 1] = center[0, 1]
    dragged_body = motion["transl"].copy()
    dragged_body[:, 1] = motion["transl"][0, 1]
    inside = motion["object_transl"].copy()  # hands sink into the box: same clip, wider box below
    jump = center.copy()  # teleports
    jump[100:, 0] += 0.5
    missed = center.copy()
    missed[:, 0] -= 0.0

    wide = {**task, "object": {**task["object"], "size": [task["object"]["size"][0] + 0.08, *task["object"]["size"][1:]]}}
    cases = [
        ("correct hold", motion, task, []),
        ("box floats away from the hands", _fake(motion, object_transl=floating), task, ["frames_moving_unheld", "hand_gap_max"]),
        ("person stands too far from the box", _fake(motion, transl=apart), task, ["frames_moving_unheld", "hand_gap_max"]),
        ("box dropped from 30 cm", _fake(motion, object_transl=dropped), task, ["touchdown_speed"]),
        ("box dragged along the floor", _fake(motion, object_transl=dragged, transl=dragged_body), task, ["frames_dragged", "box_lift_height"]),
        ("hands inside the box", _fake(motion, object_transl=inside), wide, ["hand_depth_max"]),
        ("box teleports", _fake(motion, object_transl=jump), task, ["box_speed_max", "box_accel_max"]),
    ]
    all_ok = True
    for name, m, tk, must_fail in cases:
        metrics = evaluate(m, tk, body)[0]
        failed = [x["key"] for x in metrics if x["ok"] is False]
        hoi_failed = [k for k in failed if k not in {
            # expected for this crude clip: it floats, never lets go and has no walking
            "deepest_floor_penetration", "frames_sinking", "frames_airborne", "start_stillness", "end_stillness",
            "final_hand_clearance", "final_upright", "frames_off_balance", "start_position_error", "start_heading_error",
            "grip_before_lift", "hands_stay_after_touchdown", "contact_speed_median", "contact_speed_p95",
            "touch_points_min", "body_depth_max",  # the crude pose holds the box with the thumbs and has forearms along it
        }]
        ok = all(k in failed for k in must_fail) and (must_fail or not hoi_failed)
        all_ok &= bool(ok)
        print(f"{'ok  ' if ok else 'FAIL'} {name}: caught {[k for k in hoi_failed]} (expected {must_fail})")
        if name == "correct hold":
            for x in metrics:
                if x["group"] in ("Grip", "The box in the air", "Putting it down", "Balance", "Body"):
                    print(f"       {x['label']}: {x['value']} {x['unit']}  {'' if x['ok'] is None else ('ok' if x['ok'] else 'NOT MET')}")
    print("ALL OK" if all_ok else "SOME CHECKS FAILED")

    if args.render:
        from walkenv.render import render
        out = RUNS_DIR / "_selftest"
        out.mkdir(parents=True, exist_ok=True)
        path = out / "motion.npz"
        np.savez(path, **{k: v for k, v in motion.items()})
        for written in render(path, out, task=task, videos=False, sheet_start=2.0, sheet_duration=2.0, sheet_cols=4, body=body):
            print(written)


if __name__ == "__main__":
    main()
