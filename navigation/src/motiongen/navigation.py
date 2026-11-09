"""Episode loading and the walk-to primitive shared by the agent and the baseline.

Each walked leg in the state is the hand-off to motion generation:
    {"target": str, "intent": str | None, "points": [[x, y], ...], "end_heading": float}
in the scene's frame (metres, z up). end_heading is the yaw in degrees, counter-clockwise
from +x, that faces the target object; for a position target it is the last walking direction.
"""

import math
from pathlib import Path

import yaml

from .astar import goal_mask, plan, point_goal_mask
from .path_check import path_length
from .scene import Scene

REPO_ROOT = Path(__file__).resolve().parents[2]
ARRIVE_MIN_DIST = 0.2
ARRIVE_MAX_DIST = 0.7
INTENTS = ("sit", "pick", "place", "open", "stand")


def load_episode(path):
    return yaml.safe_load(Path(path).read_text())


def load_scene(episode):
    return Scene.load(
        REPO_ROOT / episode["scene"],
        hidden=episode.get("hidden_objects", ()),
        opened=episode.get("opened", ()),
        body=episode.get("body"),
    )


def new_state(episode):
    return {
        "position": list(episode["start"]),
        "legs": [],
        "attempts": [],
        "submitted": False,
        "infeasible": False,
        "reason": None,
    }


def parse_target(scene, text):
    """Return a goal mask for an object id or an "x,y" string, or None if it isn't known."""
    if text in scene.public_ids():
        return goal_mask(scene, scene.get(text), ARRIVE_MIN_DIST, ARRIVE_MAX_DIST)
    try:
        x, y = (float(value) for value in text.split(","))
    except ValueError:
        return None
    return point_goal_mask(scene, x, y)


def end_heading(scene, target, points):
    """Yaw in degrees facing the target object, or along the last step for a position target."""
    x, y = points[-1]
    if target in scene.public_ids():
        obj = scene.get(target)
        dx, dy = obj.center[0] - x, obj.center[1] - y
    elif len(points) > 1:
        dx, dy = x - points[-2][0], y - points[-2][1]
    else:
        return None
    return round(math.degrees(math.atan2(dy, dx)), 1)


def walk_to(scene, state, target, intent=None, goal=None):
    """Walk from the current position to target, updating state. The body stays put on failure.

    intent says what the person does on arrival; navigation records it but ignores it.
    goal, if given, is the goal mask to use instead of the usual one for target.
    """
    state["attempts"].append(target)
    if goal is None:
        goal = parse_target(scene, target)
    if goal is None:
        return {"reached": False, "reason": f"unknown target {target!r}"}
    points = plan(scene, state["position"], goal)
    if points is None:
        return {"reached": False, "reason": "no collision-free route"}
    state["legs"].append({
        "target": target, "intent": intent, "points": points,
        "end_heading": end_heading(scene, target, points),
    })
    state["position"] = points[-1]
    return {
        "reached": True,
        "position": [round(value, 2) for value in points[-1]],
        "leg_length": round(path_length(points), 2),
    }


def route_points(state):
    """The whole walked route as one polyline."""
    points = []
    for leg in state["legs"]:
        points.extend(leg["points"] if not points else leg["points"][1:])
    return points
