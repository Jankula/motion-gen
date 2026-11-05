"""Task files with an object. On top of the walking task format (see walkenv/tasks.py):

  "object": {"label", "size": [extent along x, height, extent along z] in m, "mass_kg",
             "start": {"center": [x, z], "yaw_deg"}}      standing on the floor at the start
  "target": {"center": [x, z], "yaw_deg"}                 where it has to stand at the end

Or, for juggling:

  "balls": {"count", "radius" in m, "mass_kg"}
  "juggle": {"standing_foot": "left" or "right", "min_throws_two_feet", "min_throws_one_foot", "min_one_foot_s"}

"kit" names the variant of the agent's instructions (see new_run.py); without it the task is about a box.
"""
from pathlib import Path

from walkenv.tasks import _xz, describe as describe_walking, load_task as load_walking_task

from .paths import TASKS_DIR


def load_task(name_or_path):
    path = Path(name_or_path)
    return load_walking_task(path if path.suffix else TASKS_DIR / f"{name_or_path}.json")


def describe(task):
    """The task in plain words (markdown), used in the agent's TASK.md and in the reports."""
    if "balls" in task:
        return _describe_juggling(task)
    ob, target = task["object"], task["target"]
    sx, sy, sz = ob["size"]
    return "\n".join([
        describe_walking(task),
        f"- **The {ob['label']}:** a closed, rigid box with plain flat sides and no handles, {sx:g} m along its own x axis, "
        f"{sz:g} m along its own z axis and {sy:g} m tall. It weighs {ob['mass_kg']:g} kg. At the start it stands on the floor "
        f"centred at {_xz(ob['start']['center'])}, rotated {ob['start']['yaw_deg']:g}° about the vertical axis.",
        f"- **Where it goes:** on the floor, centred at {_xz(target['center'])}, rotated {target['yaw_deg']:g}° about the "
        "vertical axis (the box looks the same when turned by 180°, so that counts as the same). The spot is drawn on the "
        "floor in the videos.",
    ])


def _describe_juggling(task):
    balls, rules = task["balls"], task["juggle"]
    return "\n".join([
        describe_walking(task),
        f"- **The balls:** {balls['count']} solid balls, each {2 * balls['radius'] * 100:g} cm across and weighing {balls['mass_kg'] * 1000:g} g. "
        "A ball fits in one hand, and a hand can hold two of them.",
        f"- **Standing foot:** the person stands on the {rules['standing_foot']} foot.",
        f"- **At least:** {rules['min_throws_two_feet']} throws on both feet, {rules['min_throws_one_foot']} throws on one foot, "
        f"and {rules['min_one_foot_s']:g} seconds on one foot.",
    ])
