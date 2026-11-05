"""Task files: what the person should do, and the scene they do it in.

A task is a JSON file in tasks/. Conventions (the same ones the agent is told):
  - positions are points on the floor, [x, z] in meters, and refer to the pelvis joint projected onto the floor
  - headings are in degrees: 0 faces +Z, 90 faces +X; turning left increases the heading
  - "path" is either {"segments": [...]} (straight pieces and arcs, starting from the start pose) or
    {"points": [[x, z], ...]} (a polyline with corners)
  - obstacles are upright boxes standing on the floor
  - tasks with an object (see the hoi folder) also have "object" (what is moved and where it starts)
    and "target" (where it has to end up); both give a "center" [x, z] and a "yaw_deg"
"""
import json
from pathlib import Path

import numpy as np

from .paths import TASKS_DIR


def load_task(name_or_path):
    """Load a task by name (tasks/<name>.json) or by path; adds "path_points" (N, 2) or None."""
    path = Path(name_or_path)
    if not path.suffix:
        path = TASKS_DIR / f"{name_or_path}.json"
    task = json.loads(path.read_text(encoding="utf-8"))
    task["path_points"] = path_points(task)
    return task


def heading_vector(deg):
    """Unit [x, z] vector a person with this heading faces."""
    r = np.radians(deg)
    return np.array([np.sin(r), np.cos(r)])


def left_vector(deg):
    """Unit [x, z] vector pointing to the person's left."""
    r = np.radians(deg)
    return np.array([np.cos(r), -np.sin(r)])


def path_points(task, step=0.05):
    spec = task.get("path")
    if not spec:
        return None
    if "points" in spec:
        return np.asarray(spec["points"], float)
    pos = np.asarray(task["start"]["position"], float)
    heading = float(task["start"]["heading_deg"])
    points = [pos]
    for seg in spec["segments"]:
        if seg["type"] == "straight":
            n = max(1, int(np.ceil(seg["length"] / step)))
            points += [pos + heading_vector(heading) * seg["length"] * i / n for i in range(1, n + 1)]
        elif seg["type"] == "arc":
            radius, turn = seg["radius"], seg["turn_deg"]
            sign = np.sign(turn)
            center = pos + sign * radius * left_vector(heading)
            n = max(1, int(np.ceil(radius * np.radians(abs(turn)) / step)))
            points += [center - sign * radius * left_vector(heading + turn * i / n) for i in range(1, n + 1)]
            heading += turn
        else:
            raise ValueError(f"unknown path segment type {seg['type']!r}")
        pos = points[-1]
    return np.array(points)


def scene_bounds(task, extra_points=None):
    """[xmin, zmin], [xmax, zmax] covering the path, the obstacles, the start/end and extra_points."""
    pts = [np.asarray(task["start"]["position"], float)[None]]
    if task.get("path_points") is not None:
        pts.append(task["path_points"])
    if "position" in task.get("end", {}):
        pts.append(np.asarray(task["end"]["position"], float)[None])
    for ob in task.get("obstacles", []):
        pts.append(box_corners_xz(ob))
    if "object" in task:
        pts.append(box_corners_xz({**task["object"]["start"], "size": task["object"]["size"]}))
        pts.append(box_corners_xz({**task["target"], "size": task["object"]["size"]}))
    if extra_points is not None:
        pts.append(np.asarray(extra_points)[:, :2])
    pts = np.concatenate(pts)
    return pts.min(axis=0), pts.max(axis=0)


def box_corners_xz(ob):
    sx, _, sz = ob["size"]
    c, s = np.cos(np.radians(ob.get("yaw_deg", 0.0))), np.sin(np.radians(ob.get("yaw_deg", 0.0)))
    local = np.array([[sx, sz], [sx, -sz], [-sx, sz], [-sx, -sz]]) / 2
    rot = np.array([[c, s], [-s, c]])  # yaw about +Y applied to [x, z]
    return np.asarray(ob["center"], float) + local @ rot.T


def describe(task):
    """The task in plain words (markdown), used in the agent's TASK.md and in the reports."""
    fps, frames = task["fps"], task["frames"]
    start, end = task["start"], task.get("end", {})
    lines = [
        task["instruction"],
        "",
        f"- **Clip:** {fps} fps, exactly {frames} frames ({frames / fps:g} seconds).",
        f"- **Start:** {_state(start['state'])} at position {_xz(start['position'])}, "
        f"heading {start['heading_deg']:g}° ({_heading_words(start['heading_deg'])}).",
    ]
    if end:
        where = f" at position {_xz(end['position'])}" if "position" in end else ""
        facing = f", heading {end['heading_deg']:g}° ({_heading_words(end['heading_deg'])})" if "heading_deg" in end else ""
        state = "still walking when the clip ends" if end["state"] == "walking" else "standing still"
        lines.append(f"- **End:** {state}{where}{facing}.")
    spec = task.get("path")
    if spec:
        if "segments" in spec:
            parts = []
            for seg in spec["segments"]:
                if seg["type"] == "straight":
                    parts.append(f"{seg['length']:g} m straight")
                else:
                    side = "left" if seg["turn_deg"] > 0 else "right"
                    parts.append(f"a {abs(seg['turn_deg']):g}° bend to the {side} (radius {seg['radius']:g} m)")
            route = ", then ".join(parts)
        else:
            route = "the polyline " + " → ".join(_xz(p) for p in spec["points"])
        lines.append(
            f"- **Path:** from the start pose, {route}. The pelvis should stay within "
            f"{spec['tolerance_m']:g} m of the path (it is drawn on the floor in the videos)."
        )
    for ob in task.get("obstacles", []):
        sx, sy, sz = ob["size"]
        lines.append(
            f"- **Obstacle \"{ob['label']}\":** an upright box {sx:g} m along x, {sz:g} m along z and {sy:g} m tall, "
            f"centred at {_xz(ob['center'])}, rotated {ob.get('yaw_deg', 0):g}°. "
            f"It spans x {ob['center'][0] - sx / 2:g} to {ob['center'][0] + sx / 2:g} and "
            f"z {ob['center'][1] - sz / 2:g} to {ob['center'][1] + sz / 2:g} (before rotation)."
        )
    return "\n".join(lines)


def _state(state):
    return {"walking": "already walking", "standing": "standing still"}[state]


def _xz(p):
    return f"(x = {p[0]:g}, z = {p[1]:g})"


def _heading_words(deg):
    v = heading_vector(deg)
    names = {(0, 1): "facing +Z", (1, 0): "facing +X", (0, -1): "facing -Z", (-1, 0): "facing -X"}
    return names.get((int(round(v[0])), int(round(v[1]))), f"facing x {v[0]:+.2f}, z {v[1]:+.2f}")
