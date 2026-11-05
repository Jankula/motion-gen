"""Measure a motion with an object on the real SMPL-X mesh.

    python -m hoienv.evaluate runs/H01-box-carry               # motion.npz and task.json in that folder
    python -m hoienv.evaluate motion.npz --task box-carry      # task by name (tasks/) or by path

All the walking measurements (floor, foot sliding, smoothness, ...) plus the ones here: contact between
hands and box, whether the box behaves like a real object, how it is put down, and whether the body
stays balanced and intact. Most of them exist to catch one specific way of faking the interaction.
Tasks with balls are measured by juggling.py instead of the box measurements.

Prints a table and writes next to the motion:
  <motion name>.metrics.json     every number, with its target and plain-language meaning
  <motion name>.timeline.csv     the contact and balance numbers for every frame, to find *when* something goes wrong
  <motion name>.throws.csv       tasks with balls: every flight, with its times, height and fit
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull, QhullError, cKDTree
from scipy.spatial.transform import Rotation

from walkenv.body import BODY_JOINT_NAMES, Body
from walkenv.cameras import moving_average
from walkenv.evaluate import evaluate as evaluate_walking, metrics_table
from walkenv.motion_format import load_motion

from .tasks import load_task

TOUCH_M = 0.008  # hand skin this close to the box surface touches it
HOLD_M = 0.015  # a hand further from the box than this cannot be holding it
AT_REST_M = 0.005  # box bottom this close to the floor stands on it
MOVED_M = 0.003  # the box counts as moved if it is this far from its resting pose
MOVED_DEG = 1.0
BODY_DENSITY = 1000.0  # kg/m3; gives the body's mass from the volume of the mesh
MIN_TOUCH_POINTS = 40  # measured: a flat hand on a flat surface gives 41 (about 86 pressed in by 4 mm), one fingertip at most 28

LEFT_HAND_JOINTS = [20, *range(25, 40)]
RIGHT_HAND_JOINTS = [21, *range(40, 55)]
FOREARM_JOINTS = [18, 19]
TORSO_JOINTS = [0, 3, 6, 9]
LEG_JOINTS = [1, 2, 4, 5]


def evaluate(motion, task, body, arm_check=True):
    """Returns (metrics, timeline, throws): the list of metrics, a dict of per-frame arrays, and the flights of the balls.

    arm_check=False skips the slowest measurement (forearms against the body), for tasks with balls.
    """
    verts, joints = body.forward(motion)
    metrics = evaluate_walking(motion, task, body, fk=(verts, joints))
    if "balls" in task:
        from .juggling import ball_metrics  # juggling.py uses the helpers in this file

        more, timeline, throws = ball_metrics(motion, task, body, verts.astype(np.float32), joints, arm_check)
        return metrics + more, timeline, throws
    more, timeline = _object_metrics(motion, task, body, verts.astype(np.float32), joints)
    return metrics + more, timeline, []


def _body_parts(body):
    owner = body.model.lbs_weights.numpy().argmax(axis=1)
    rest = body.rest_vertices
    left = np.isin(owner, LEFT_HAND_JOINTS) & (rest[:, 0] > body.rest_joints[20, 0])
    right = np.isin(owner, RIGHT_HAND_JOINTS) & (rest[:, 0] < body.rest_joints[21, 0])
    return {
        "left": left,
        "right": right,
        "rest": ~(left | right),
        "arm": np.isin(owner, FOREARM_JOINTS) | left | right,
        "trunk_legs": np.isin(owner, TORSO_JOINTS + LEG_JOINTS),
    }


def _box_distance(verts, center, rot, half, chunk=64):
    """Signed distance (m) of every vertex to the box surface, negative inside: (T, V)."""
    out = np.empty(verts.shape[:2], np.float32)
    for a in range(0, len(verts), chunk):
        s = slice(a, a + chunk)
        local = np.einsum("tvj,tjk->tvk", verts[s] - center[s, None], rot[s])
        d = np.abs(local) - half
        out[s] = np.linalg.norm(np.maximum(d, 0), axis=-1) + np.minimum(d.max(axis=-1), 0)
    return out


def _center_of_mass(verts, faces, chunk=32):
    """Centre of mass (T, 3) and mass of the closed body mesh at uniform density."""
    com, mass = np.empty((len(verts), 3)), 0.0
    for a in range(0, len(verts), chunk):
        v = verts[a : a + chunk].astype(np.float64)
        origin = v.mean(axis=1, keepdims=True)
        tri = (v - origin)[:, faces]  # (t, F, 3 corners, 3)
        vol = np.einsum("tfi,tfi->tf", tri[:, :, 0], np.cross(tri[:, :, 1], tri[:, :, 2])) / 6
        com[a : a + chunk] = origin[:, 0] + np.einsum("tf,tfi->ti", vol, tri.sum(axis=2) / 4) / vol.sum(axis=1, keepdims=True)
        mass = abs(vol[0].sum()) * BODY_DENSITY
    return com, mass


def _outside_support(point, foot_points):
    """How far (m) a point on the floor plane is outside the convex outline of the feet; <= 0 is inside."""
    try:
        hull = ConvexHull(foot_points)
    except (QhullError, ValueError):
        return np.nan
    return float((hull.equations[:, :2] @ point + hull.equations[:, 2]).max())


def _arm_depth(verts, faces, arm, other, max_gap=0.08):
    """Per frame, how deep (m) forearm or hand skin goes into the trunk or legs.

    For every arm point: the nearest trunk or leg point, and which side of the skin it is on.
    """
    arm_ids, other_ids = np.where(arm)[0], np.where(other)[0]
    depth = np.zeros(len(verts))
    for t, v in enumerate(verts):
        v = v.astype(np.float64)
        dist, idx = cKDTree(v[other_ids]).query(v[arm_ids], distance_upper_bound=max_gap)
        near = np.isfinite(dist)
        if not near.any():
            continue
        face_n = np.cross(v[faces[:, 1]] - v[faces[:, 0]], v[faces[:, 2]] - v[faces[:, 0]])
        normals = np.zeros_like(v)
        for k in range(3):
            np.add.at(normals, faces[:, k], face_n)
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
        q = other_ids[idx[near]]
        depth[t] = max(0.0, (-np.einsum("ij,ij->i", v[arm_ids[near]] - v[q], normals[q])).max())
    return depth


def _add_joint_limits(add, pose):
    wrong = max(
        np.degrees(-pose[:, 3, 0].min()), np.degrees(-pose[:, 4, 0].min()),  # knees bend about +x
        np.degrees(pose[:, 17, 1].max()), np.degrees(-pose[:, 18, 1].min()),  # elbows: left about -y, right about +y
    )
    add("Body", "joints_wrong_way", "Knees and elbows bending the wrong way", max(0.0, wrong), "°",
        "How far a knee or elbow ever bends backwards.", "≤ 5°", wrong <= 5)
    value = np.degrees(np.linalg.norm(pose[:, 19:21], axis=2)).max()
    add("Body", "wrist_bend_max", "Largest wrist rotation", value, "°",
        "Largest total rotation of a wrist. Real wrists stop at about 80°.", "≤ 85°", value <= 85)


def _object_metrics(motion, task, body, verts, joints):
    fps, floor_y = motion["fps"], body.floor_y
    num_frames = len(verts)
    ob = task["object"]
    label = ob["label"]
    size = np.array(ob["size"], float)
    half = size / 2
    mass = ob["mass_kg"]
    center = motion["object_transl"].astype(np.float64)
    rotation = Rotation.from_rotvec(motion["object_orient"].astype(np.float64))
    rot = rotation.as_matrix()
    parts = _body_parts(body)
    out = []

    def add(group, key, lbl, value, unit, meaning, target=None, ok=None):
        out.append(dict(group=group, key=key, label=lbl, value=value if isinstance(value, str) else round(float(value), 2),
                        unit=unit, target=target, ok=None if ok is None else bool(ok), meaning=meaning))

    # --- where the box is
    corners = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]) * half
    bottom = (center[:, None] + corners @ rot.transpose(0, 2, 1))[:, :, 1].min(axis=1) - floor_y
    start_center = np.array([ob["start"]["center"][0], floor_y + half[1], ob["start"]["center"][1]])
    start_rot = Rotation.from_euler("y", ob["start"]["yaw_deg"], degrees=True)
    from_start = (np.linalg.norm(center - start_center, axis=1) > MOVED_M) | ((rotation * start_rot.inv()).magnitude() > np.radians(MOVED_DEG))
    from_end = (np.linalg.norm(center - center[-1], axis=1) > MOVED_M) | ((rotation * rotation[-1].inv()).magnitude() > np.radians(MOVED_DEG))
    velocity = np.gradient(center, 1 / fps, axis=0)
    speed = np.linalg.norm(velocity, axis=1)
    turn_speed = np.zeros(num_frames)
    turn_speed[1:] = np.degrees((rotation[1:] * rotation[:-1].inv()).magnitude()) * fps

    # --- hands against the box
    sd = _box_distance(verts, center.astype(np.float32), rot.astype(np.float32), half.astype(np.float32))
    gap = {s: sd[:, parts[s]].min(axis=1) for s in ("left", "right")}  # negative: skin inside the box
    touching = {s: (sd[:, parts[s]] <= TOUCH_M).sum(axis=1) for s in ("left", "right")}
    both_on = (gap["left"] <= HOLD_M) & (gap["right"] <= HOLD_M)
    worst_gap = np.maximum(gap["left"], gap["right"])
    hand_depth = np.maximum(0, -np.minimum(gap["left"], gap["right"]))
    body_depth = np.maximum(0, -sd[:, parts["rest"]].min(axis=1))

    # --- balance: the body's centre of mass plus the box while it is held, against the outline of the feet
    body_com, body_mass = _center_of_mass(verts, body.faces)
    first = int(from_start.argmax()) if from_start.any() else None
    last = int(np.where(from_end)[0].max()) if from_end.any() else None
    carried = np.zeros(num_frames, bool)
    if first is not None and last is not None and last >= first:
        carried[first : last + 1] = True
    total_mass = np.where(carried, body_mass + mass, body_mass)[:, None]
    com = (body_com * body_mass + np.where(carried[:, None], center * mass, 0.0)) / total_mass
    com_speed = np.linalg.norm(np.gradient(moving_average(com[:, [0, 2]], max(1, fps // 6)), 1 / fps, axis=0), axis=1)
    height = verts[:, :, 1] - floor_y
    rest = body.rest_vertices
    outside = np.full(num_frames, np.nan)
    feet = [np.where((rest[:, 0] * sign > 0) & (rest[:, 1] < body.rest_joints[BODY_JOINT_NAMES.index(a), 1]))[0]
            for sign, a in ((1, "left_ankle"), (-1, "right_ankle"))]
    for t in range(num_frames):
        on = [f[height[t, f] < 0.015] for f in feet]
        if len(on[0]) and len(on[1]) and com_speed[t] < 0.3:  # both feet down, not in the middle of a step
            outside[t] = _outside_support(com[t, [0, 2]], verts[t, np.concatenate(on)][:, [0, 2]].astype(np.float64))

    # --- the body: forearms against trunk and legs
    arm_depth = _arm_depth(verts, body.faces, parts["arm"], parts["trunk_legs"])

    # --- posture
    pelvis = joints[:, 0].astype(np.float64)
    spine = joints[:, 12].astype(np.float64) - pelvis
    facing = Rotation.from_rotvec(motion["global_orient"].astype(np.float64)).apply([0.0, 0.0, 1.0])
    facing[:, 1] = 0
    facing /= np.maximum(np.linalg.norm(facing, axis=1, keepdims=True), 1e-9)
    lean = np.degrees(np.arctan2(np.einsum("ij,ij->i", spine, facing), spine[:, 1]))  # + forward, - backward
    window = max(1, round(0.5 * fps))
    walk_speed = np.linalg.norm(np.gradient(moving_average(pelvis[:, [0, 2]], window), 1 / fps, axis=0), axis=1)

    timeline = {
        "frame": np.arange(num_frames),
        "time_s": np.arange(num_frames) / fps,
        "left_hand_gap_mm": gap["left"] * 1000,
        "right_hand_gap_mm": gap["right"] * 1000,
        "left_touch_points": touching["left"],
        "right_touch_points": touching["right"],
        "body_into_box_mm": body_depth * 1000,
        "arm_into_body_mm": arm_depth * 1000,
        "box_bottom_above_floor_mm": bottom * 1000,
        "box_speed_m_s": speed,
        "balance_outside_feet_cm": outside * 100,
        "pelvis_height_m": pelvis[:, 1] - floor_y,
        "trunk_lean_deg": lean,
    }

    # --- the box before it moves
    err = np.linalg.norm(center[0] - start_center) * 1000
    add("Grip", "box_start_error", f"The {label} starts where the task says", err, "mm",
        f"Distance between the {label} in the first frame and its required start position.", "≤ 5 mm", err <= 5)
    if first is None or first == 0 or last is None:
        add("Grip", "box_never_moved", f"The {label} is picked up", "no", "",
            f"The {label} never leaves its start pose, or does not start there, so nothing else can be measured.", "yes", False)
        return out, timeline

    # --- grip
    k = first
    while k > 0 and worst_gap[k - 1] <= 0.01:
        k -= 1
    held_before = (first - k) / fps
    add("Grip", "grip_before_lift", "Hands on the box before it moves", held_before, "s",
        f"How long both hands are on the {label} before it starts to move. A person takes hold first and then lifts.",
        "≥ 0.15 s", held_before >= 0.15)
    moving = (speed > 0.01) | (turn_speed > 5)
    n = int((moving & ~both_on).sum())
    add("Grip", "frames_moving_unheld", f"Frames the {label} moves without both hands on it", n, "frames",
        f"Frames in which the {label} moves although at least one hand is more than {HOLD_M * 100:g} cm away from it. "
        "A semi-heavy box does not move by itself.", "0", n == 0)
    value = max(0.0, worst_gap[carried].max()) * 1000
    add("Grip", "hand_gap_max", "Largest gap between a hand and the box while carrying", value, "mm",
        "The worst moment of the worse hand: how far its closest skin is from the box surface. 0 means the skin touches.",
        "≤ 10 mm", value <= 10)
    value = hand_depth.max() * 1000
    add("Grip", "hand_depth_max", "Deepest hand skin inside the box", value, "mm",
        f"How far hand skin goes into the {label} over the whole clip. Skin is soft, so a few millimetres are fine; more "
        "shows as fingers passing through the box.", "≤ 10 mm", value <= 10)
    value = min(touching["left"][carried].min(), touching["right"][carried].min())
    add("Grip", "touch_points_min", "Fewest hand skin points touching the box", value, "points",
        f"While carrying, the smallest number of skin points of a hand within {TOUCH_M * 1000:g} mm of the box. A flat hand on a "
        "surface gives about 40, or about 85 pressed in by 4 mm; one fingertip gives at most 28. A real grip needs a real contact area.",
        f"≥ {MIN_TOUCH_POINTS}", value >= MIN_TOUCH_POINTS)

    local, contact = {}, {}
    window_frames = np.where(carried)[0]
    mid = window_frames[len(window_frames) // 2]
    for s in ("left", "right"):
        ids = np.where(parts[s])[0]
        local[s] = np.einsum("tvj,tjk->tvk", verts[window_frames][:, ids].astype(np.float64) - center[window_frames, None], rot[window_frames])
        contact[s] = sd[window_frames][:, ids] <= TOUCH_M
    slide = 0.0
    for s in ("left", "right"):
        at_mid = contact[s][window_frames.searchsorted(mid)]
        if at_mid.any():
            ref = local[s][window_frames.searchsorted(mid)][at_mid]
            slide = max(slide, np.linalg.norm(local[s][:, at_mid] - ref, axis=2).mean(axis=1).max())
        else:
            slide = np.inf
    slide = min(slide * 100, 999.0)
    add("Grip", "hand_slide", "Hands sliding over the box while carrying", slide, "cm",
        f"How far the skin that touches the {label} moves over its surface while it is carried. A firm grip does not move.",
        "≤ 2 cm", slide <= 2)
    angles = []
    for i in range(len(window_frames)):
        if contact["left"][i].any() and contact["right"][i].any():
            a = local["left"][i][contact["left"][i]].mean(axis=0)
            b = local["right"][i][contact["right"][i]].mean(axis=0)
            angles.append(np.degrees(np.arccos(np.clip(a @ b / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-9), -1, 1))))
    value = min(angles) if angles else 0.0
    add("Grip", "grip_opposition", "How opposite the two hands are", value, "°",
        f"Angle at the centre of the {label} between the two hands, at its smallest. 180° means exactly opposite sides. Two hands "
        "resting on top, or on the same side, cannot carry a box.", "≥ 120°", value >= 120)

    # --- the box in the air
    value = bottom.max()
    add("The box in the air", "box_lift_height", "Highest the bottom of the box gets", value * 100, "cm",
        f"Largest height of the {label}'s lowest corner above the floor. It has to be really picked up.", "≥ 20 cm", value >= 0.2)
    horizontal = np.linalg.norm(velocity[:, [0, 2]], axis=1)
    n = int(((bottom < AT_REST_M) & (horizontal > 0.03)).sum())
    add("The box in the air", "frames_dragged", "Frames the box slides along the floor", n, "frames",
        f"Frames in which the {label} stands on the floor but moves sideways: it is dragged, not carried.", "0", n == 0)
    value = max(0.0, -bottom.min()) * 1000
    add("The box in the air", "box_floor_depth", "Deepest the box goes into the floor", value, "mm",
        f"How far the {label}'s lowest corner goes below the floor at any moment.", "≤ 3 mm", value <= 3)
    tilt = np.degrees(np.arccos(np.clip(rot[:, 1, 1], -1, 1)))
    add("The box in the air", "box_tilt_max", "Largest tilt of the box while carrying", tilt[carried].max(), "°",
        f"How far the {label}'s top leans away from horizontal.", "≤ 15°", tilt[carried].max() <= 15)
    value = speed.max()
    add("The box in the air", "box_speed_max", "Fastest the box moves", value, "m/s",
        f"Highest speed of the {label}. A jump shows up here.", "≤ 2 m/s", value <= 2)
    accel = np.linalg.norm(np.gradient(moving_average(velocity, max(1, fps // 6)), 1 / fps, axis=0), axis=1)
    add("The box in the air", "box_accel_max", "Strongest acceleration of the box", accel.max(), "m/s²",
        f"Largest change of the {label}'s speed, smoothed over 0.17 s. A semi-heavy box cannot be jerked around: at 10 kg, "
        "5 m/s² already takes a 50 N push on top of its weight.", "≤ 5 m/s²", accel.max() <= 5)

    # --- putting it down
    tgt = task["target"]
    value = np.linalg.norm(center[-1, [0, 2]] - np.asarray(tgt["center"], float)) * 100
    add("Putting it down", "target_error", "Distance from the marked spot", value, "cm",
        f"Distance between the {label}'s final centre and the centre of the marked spot, seen from above.", "≤ 10 cm", value <= 10)
    x_axis = rot[-1][:, 0]
    yaw = np.degrees(np.arctan2(-x_axis[2], x_axis[0]))
    value = abs((yaw - tgt["yaw_deg"] + 90) % 180 - 90)
    add("Putting it down", "target_yaw_error", "Final rotation error of the box", value, "°",
        f"Difference between the {label}'s final rotation and the marked one (turned by 180° counts as the same).", "≤ 15°", value <= 15)
    value = abs(bottom[-1]) * 1000
    add("Putting it down", "final_floor_gap", "The box stands on the floor at the end", value, "mm",
        f"Height of the {label}'s lowest corner in the last frame. It should be 0.", "≤ 3 mm", value <= 3)
    add("Putting it down", "final_tilt", "Final tilt of the box", tilt[-1], "°", f"The {label} should stand flat.", "≤ 1°", tilt[-1] <= 1)
    airborne = np.where(bottom > AT_REST_M)[0]
    touchdown = int(airborne.max()) + 1 if len(airborne) else None
    if touchdown is None or touchdown >= num_frames:
        add("Putting it down", "box_lands", "The box lands", "no", "", f"The {label} never comes to the floor.", "yes", False)
    else:
        before = max(0, touchdown - round(0.1 * fps))
        value = np.abs(velocity[before : touchdown + 1, 1]).max()
        add("Putting it down", "touchdown_speed", "Speed at touchdown", value, "m/s",
            f"Downward speed of the {label} in the last 0.1 s before it reaches the floor. Set down carefully means slowly; dropped "
            "from 10 cm would be 1.4 m/s.", "≤ 0.15 m/s", value <= 0.15)
        off = np.where(worst_gap[touchdown:] > 0.02)[0]
        value = off[0] / fps if len(off) else (num_frames - touchdown) / fps
        add("Putting it down", "hands_stay_after_touchdown", "Hands stay on the box after it lands", value, "s",
            f"Time between the {label} reaching the floor and the first hand leaving it. A careful person lets go after the box "
            "stands, not before.", "≥ 0.1 s", value >= 0.1)
    value = min(gap["left"][-1], gap["right"][-1]) * 100
    add("Putting it down", "final_hand_clearance", "Hands off the box at the end", value, "cm",
        f"Distance from the {label} to the closer hand in the last frame.", "≥ 5 cm", value >= 5)
    head_rest = body.rest_joints[15, 1] - floor_y
    value = (joints[-1, 15, 1] - floor_y) / head_rest * 100
    add("Putting it down", "final_upright", "Standing up at the end", value, "% of height",
        "Height of the head in the last frame, as a share of its height in a straight stance.", "≥ 96 %", value >= 96)

    # --- the body
    value = body_depth.max() * 1000
    add("Body", "body_depth_max", "Deepest body skin (not hands) inside the box", value, "mm",
        f"How far torso, arms, legs or feet ever go into the {label}. Clothes and soft tissue give a little.", "≤ 15 mm", value <= 15)
    value = arm_depth.max() * 1000
    add("Body", "arm_depth_max", "Deepest forearm or hand skin inside the trunk or legs", value, "mm",
        f"How far forearms and hands go into the trunk or legs (worst at frame {int(arm_depth.argmax())}). A few millimetres of "
        "pressing is natural; more shows as an arm passing through the body.", "≤ 15 mm", value <= 15)
    _add_joint_limits(add, motion["body_pose"])

    # --- balance
    n = int(np.nansum(outside > 0.03))
    add("Balance", "frames_off_balance", "Frames off balance with both feet down", n, "frames",
        f"Frames in which both feet are on the floor, the body moves slowly, and the combined centre of mass of body ({body_mass:.0f} kg) "
        f"and held {label} ({mass:g} kg) is more than 3 cm outside the outline of the feet. The person would topple. This is what "
        "the weight of the box demands: holding it far from the body pushes the balance point forward.", "0", n == 0)
    value = np.nanmax(outside) * 100 if np.isfinite(outside).any() else 0.0
    add("Balance", "balance_worst", "Worst balance margin", value, "cm",
        "Largest distance of the centre of mass outside the outline of the feet in those frames. Negative means it stayed inside.")

    # --- how the weight shows (information only)
    group = "How the weight shows"
    add(group, "lowest_pelvis", "Lowest pelvis height", (pelvis[:, 1] - floor_y).min(), "m",
        f"How far the person goes down. Standing is {body.rest_joints[0, 1] - floor_y:.2f} m.")
    value = lean[max(0, first - round(0.3 * fps)) : first + 1].max()
    add(group, "lean_at_grip", "Trunk lean at the grip", value, "°", "Forward lean of the trunk (pelvis to neck) when the lift begins.")
    before = (np.arange(num_frames) < first) & (walk_speed > 0.3)
    during = carried & (walk_speed > 0.3)
    if before.any():
        add(group, "speed_before", "Walking speed without the box", np.median(walk_speed[before]), "m/s", "Typical speed on the way to the box.")
        add(group, "lean_before", "Trunk lean without the box", np.median(lean[before]), "°", "Typical lean while walking to the box. Positive is forward.")
    if during.any():
        add(group, "speed_carrying", "Walking speed with the box", np.median(walk_speed[during]), "m/s", "Typical speed while carrying.")
        add(group, "lean_carrying", "Trunk lean with the box", np.median(lean[during]), "°", "Typical lean while carrying. Negative means leaning back against the weight.")
        chest = joints[:, 9].astype(np.float64)
        ahead = np.einsum("ij,ij->i", (center - chest), facing)[during]
        add(group, "box_ahead_of_chest", "Box centre in front of the chest while carrying", np.median(ahead) * 100, "cm",
            "How far in front of the chest the box is held. Close to the body is how a heavy load is carried.")
        add(group, "box_height_carrying", "Height of the box centre while carrying", np.median(center[during, 1] - floor_y), "m",
            "How high the box is carried.")
    return out, timeline


def _write_throws(path, flights, fps, floor_y):
    """One line per flight, in the order of the clip, to find which throw or catch goes wrong."""
    hand = {0: "left", 1: "right", None: "none"}
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ball", "from_hand", "to_hand", "release_s", "catch_s", "peak_height_m", "gravity_m_s2", "fit_mm",
                         "release_jump_m_s", "catch_jump_m_s"])
        for x in sorted(flights, key=lambda x: x["first"]):
            if not x["fitted"]:
                writer.writerow([x["ball"] + 1, hand[x["source"]], hand[x["target"]], round(x["first"] / fps, 3),
                                 round(x["last"] / fps, 3), "too short", "", "", "", ""])
                continue
            writer.writerow([x["ball"] + 1, hand[x["source"]], hand[x["target"]], round(x["release"] / fps, 3), round(x["catch"] / fps, 3),
                             round(x["peak"] - floor_y, 3), round(x["gravity"], 2), round(x["fit_rms_mm"], 2),
                             round(x["release_jump"], 2), round(x["catch_jump"], 2)])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("motion", type=Path, help="motion .npz, or an experiment folder with motion.npz and task.json")
    ap.add_argument("--task", help="task name or task .json (default: task.json next to the motion)")
    ap.add_argument("--out", type=Path, help="where to write the metrics JSON")
    args = ap.parse_args()

    motion_path = args.motion / "motion.npz" if args.motion.is_dir() else args.motion
    task = load_task(args.task or motion_path.parent / "task.json")
    balls = task["balls"]["count"] if "balls" in task else None
    motion = load_motion(motion_path, expect_object="object" in task, expect_balls=balls)
    body = Body()
    metrics, timeline, throws = evaluate(motion, task, body)
    out = args.out or motion_path.with_name(f"{motion_path.stem}.metrics.json")
    out.write_text(json.dumps({"task": task["name"], "metrics": metrics}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    timeline_path = out.with_name(out.name.replace(".metrics.json", ".timeline.csv"))
    with open(timeline_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(timeline)
        writer.writerows(zip(*[np.round(np.asarray(c, float), 3).tolist() for c in timeline.values()]))
    if "balls" in task:
        _write_throws(out.with_name(out.name.replace(".metrics.json", ".throws.csv")), throws, motion["fps"], body.floor_y)
    passed = sum(m["ok"] is True for m in metrics)
    checked = sum(m["ok"] is not None for m in metrics)
    print(metrics_table(metrics))
    print(f"\n{passed} of {checked} targets met. Details and meanings: {out}. Frame by frame: {timeline_path}")


if __name__ == "__main__":
    main()
