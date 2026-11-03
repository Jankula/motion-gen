"""Measure a motion on the real SMPL-X mesh: floor contact, foot sliding, path following,
start/end poses, obstacles and smoothness.

    python -m walkenv.evaluate runs/E02-curved-path            # motion.npz and task.json in that folder
    python -m walkenv.evaluate motion.npz --task curved-path   # task by name (tasks/) or by path

Prints a table and writes <motion name>.metrics.json next to the motion (or --out). Every metric
carries a plain-language meaning and, where one makes sense, a target, so the same numbers can be
read by the agent, in the reports, and by people who are not animation specialists.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .body import BODY_JOINT_NAMES, Body
from .cameras import moving_average
from .motion_format import load_motion
from .tasks import load_task

CONTACT_M = 0.005  # a skin point this close to the floor counts as touching it
POP_DEG_PER_S = 1500.0  # a joint rotating faster than this between two frames is a glitch


def evaluate(motion, task, body):
    """Returns a list of metrics: dicts with group, key, label, value, unit, target, ok, meaning."""
    verts, joints = body.forward(motion)
    fps = motion["fps"]
    height = verts[:, :, 1] - body.floor_y
    pelvis = joints[:, 0, [0, 2]]
    heading = _heading_deg(motion["global_orient"])
    out = []

    def add(group, key, label, value, unit, meaning, target=None, ok=None):
        value = round(float(value), 2) if not isinstance(value, str) else value
        out.append(dict(group=group, key=key, label=label, value=value, unit=unit, target=target,
                        ok=None if ok is None else bool(ok), meaning=meaning))

    # --- ground contact
    lowest = height.min(axis=1)
    sink = max(0.0, -lowest.min()) * 1000
    add("Ground contact", "deepest_floor_penetration", "Deepest sinking into the floor", sink, "mm",
        "How far any part of the skin ever goes below the floor. 0 means never.", "≤ 10 mm", sink <= 10)
    n = int((lowest < -0.010).sum())
    add("Ground contact", "frames_sinking", "Frames sinking more than 1 cm", n, "frames",
        "Frames in which some skin is more than 1 cm below the floor.", "0", n == 0)
    n = int((lowest > 0.02).sum())
    add("Ground contact", "frames_airborne", "Frames with nothing on the floor", n, "frames",
        "Frames in which no part of the body is within 2 cm of the floor. A walking person always has "
        "at least one foot on the ground.", "0", n == 0)

    # --- foot sliding: horizontal speed of skin points that touch the floor in two consecutive frames
    speeds = []
    for sign, ankle in ((1, "left_ankle"), (-1, "right_ankle")):
        rest = body.rest_vertices
        foot = np.where((rest[:, 0] * sign > 0) & (rest[:, 1] < body.rest_joints[BODY_JOINT_NAMES.index(ankle), 1]))[0]
        on = (height[:-1, foot] < CONTACT_M) & (height[1:, foot] < CONTACT_M)
        step = np.linalg.norm(verts[1:, foot][:, :, [0, 2]] - verts[:-1, foot][:, :, [0, 2]], axis=2) * fps
        speeds.append(step[on])
    s = np.concatenate(speeds) * 100
    if len(s):
        add("Foot sliding", "contact_speed_median", "Typical speed of floor-touching skin", np.median(s), "cm/s",
            "How fast skin points that touch the floor move along it, typically. A planted foot should not "
            "move, so this should be close to 0.", "≤ 1 cm/s", np.median(s) <= 1)
        p95 = np.percentile(s, 95)
        add("Foot sliding", "contact_speed_p95", "Speed of floor-touching skin, 95th percentile", p95, "cm/s",
            "95 % of floor-touching skin points move slower than this. It catches brief slips. Turning on the "
            "spot legitimately raises it a little, because a foot pivots on the ball.", "≤ 3 cm/s", p95 <= 3)

    # --- path and poses
    distance = np.linalg.norm(np.diff(moving_average(pelvis, max(1, round(0.5 * fps))), axis=0), axis=1).sum()
    add("Path", "distance_travelled", "Distance travelled by the pelvis", distance, "m",
        "Length of the pelvis track seen from above, with the side-to-side sway of each step smoothed out.")
    add("Path", "average_speed", "Average speed", distance / ((len(pelvis) - 1) / fps), "m/s",
        "Distance travelled divided by the clip length (pauses included). Comfortable walking is about "
        "1.2-1.4 m/s.")
    if task.get("path_points") is not None:
        tol = task["path"]["tolerance_m"] * 100
        dev = _distance_to_polyline(pelvis, task["path_points"]) * 100
        add("Path", "path_deviation_mean", "Average distance from the path", dev.mean(), "cm",
            "Average distance of the pelvis from the marked path, seen from above.", f"≤ {tol:g} cm", dev.mean() <= tol)
        add("Path", "path_deviation_max", "Largest distance from the path", dev.max(), "cm",
            "Largest distance of the pelvis from the marked path at any moment.", f"≤ {tol:g} cm", dev.max() <= tol)
    for which, idx in (("start", 0), ("end", -1)):
        spec = task.get(which, {})
        if "position" in spec:
            err = np.linalg.norm(pelvis[idx] - np.asarray(spec["position"], float)) * 100
            add("Path", f"{which}_position_error", f"{which.capitalize()} position error", err, "cm",
                f"Distance between the pelvis and the required {which} position, in the {which} frame.",
                "≤ 15 cm", err <= 15)
        if "heading_deg" in spec:
            err = abs(_angle_diff(heading[idx], spec["heading_deg"]))
            add("Path", f"{which}_heading_error", f"{which.capitalize()} heading error", err, "°",
                f"Difference between the direction the pelvis faces and the required {which} heading.",
                "≤ 15°", err <= 15)
        if spec.get("state") == "standing":
            k = max(2, round(0.5 * fps))
            seg = pelvis[:k] if which == "start" else pelvis[-k:]
            v = np.linalg.norm(np.diff(seg, axis=0), axis=1).max() * fps * 100
            add("Path", f"{which}_stillness", f"Pelvis speed while standing at the {which}", v, "cm/s",
                f"Fastest horizontal pelvis movement in the {'first' if which == 'start' else 'last'} 0.5 s, "
                "where the person should be standing still. Small values are natural sway.", "≤ 10 cm/s", v <= 10)

    # --- obstacles
    for ob in task.get("obstacles", []):
        sd = _box_signed_distance(verts, ob, body.floor_y).min(axis=1)  # per frame, closest skin point
        add("Obstacles", f"clearance:{ob['label']}", f"Closest approach to the {ob['label']}", sd.min() * 100, "cm",
            f"Smallest distance between the skin and the {ob['label']} over the whole clip. Negative means "
            "the body goes into it.", "> 0 cm", sd.min() > 0)
        n = int((sd < 0).sum())
        add("Obstacles", f"collision_frames:{ob['label']}", f"Frames touching the {ob['label']}", n, "frames",
            f"Frames in which some skin is inside the {ob['label']}.", "0", n == 0)

    # --- smoothness: rotation of every controlled joint from one frame to the next
    rotvecs = np.concatenate([motion["global_orient"][:, None], motion["body_pose"]], axis=1)  # (T, 22, 3)
    r = Rotation.from_rotvec(rotvecs.reshape(-1, 3)).as_matrix().reshape(len(rotvecs), 22, 3, 3)
    rel = np.einsum("tjki,tjkl->tjil", r[:-1], r[1:])  # R_t^T R_{t+1}
    ang = np.degrees(np.arccos(np.clip((np.trace(rel, axis1=2, axis2=3) - 1) / 2, -1, 1))) * fps
    t, j = np.unravel_index(ang.argmax(), ang.shape)
    add("Smoothness", "max_joint_speed", "Fastest joint rotation", ang.max(), "°/s",
        f"Fastest rotation of any joint between two frames ({BODY_JOINT_NAMES[j]}, frame {t}). In walking "
        "the swinging knee peaks at roughly 400-600°/s; far higher values mean a jerk.", "≤ 800 °/s", ang.max() <= 800)
    n = int((ang > POP_DEG_PER_S).any(axis=1).sum())
    add("Smoothness", "frames_with_pops", "Frames with a pop", n, "frames",
        f"Frames in which some joint jumps faster than {POP_DEG_PER_S:g}°/s, which is visible as a glitch.",
        "0", n == 0)
    return out


def _heading_deg(global_orient):
    f = Rotation.from_rotvec(global_orient).apply([0.0, 0.0, 1.0])
    return np.degrees(np.arctan2(f[:, 0], f[:, 2]))


def _angle_diff(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def _distance_to_polyline(points, poly):
    a, b = poly[:-1], poly[1:]
    ab = b - a
    t = np.clip(np.einsum("pnk,nk->pn", points[:, None] - a[None], ab) / np.maximum((ab**2).sum(1), 1e-12), 0, 1)
    closest = a[None] + t[..., None] * ab[None]
    return np.linalg.norm(points[:, None] - closest, axis=2).min(axis=1)


def _box_signed_distance(verts, ob, floor_y):
    """Signed distance (m) of every vertex to an upright box obstacle: negative inside. Shape (T, V)."""
    sx, sy, sz = ob["size"]
    c, s = np.cos(np.radians(ob.get("yaw_deg", 0.0))), np.sin(np.radians(ob.get("yaw_deg", 0.0)))
    dx = verts[..., 0] - ob["center"][0]
    dz = verts[..., 2] - ob["center"][1]
    local = np.stack([c * dx - s * dz, verts[..., 1] - (floor_y + sy / 2), s * dx + c * dz], axis=-1)
    d = np.abs(local) - np.array([sx, sy, sz]) / 2
    return np.linalg.norm(np.maximum(d, 0), axis=-1) + np.minimum(d.max(axis=-1), 0)


def metrics_table(metrics):
    """Markdown table of the metrics, for printing and for the reports."""
    rows = ["| | Measurement | Value | Target |", "|---|---|---|---|"]
    for m in metrics:
        mark = {True: "✅", False: "❌", None: ""}[m["ok"]]
        rows.append(f"| {mark} | {m['label']} | {m['value']:g} {m['unit']} | {m['target'] or ''} |")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("motion", type=Path, help="motion .npz, or an experiment folder with motion.npz and task.json")
    ap.add_argument("--task", help="task name or task .json (default: task.json next to the motion)")
    ap.add_argument("--out", type=Path, help="where to write the metrics JSON")
    args = ap.parse_args()

    motion_path = args.motion / "motion.npz" if args.motion.is_dir() else args.motion
    task = load_task(args.task or motion_path.parent / "task.json")
    metrics = evaluate(load_motion(motion_path), task, Body())
    out = args.out or motion_path.with_name(f"{motion_path.stem}.metrics.json")
    out.write_text(json.dumps({"task": task["name"], "metrics": metrics}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    passed = sum(m["ok"] is True for m in metrics)
    checked = sum(m["ok"] is not None for m in metrics)
    print(metrics_table(metrics))
    print(f"\n{passed} of {checked} targets met. Details and meanings: {out}")


if __name__ == "__main__":
    main()
