"""Score a long-horizon task: events that must happen, their order, and the end state.

An episode's `goals`:
    events:  [{id, pick: X} | {id, place: [X, Y]} | {id, open: X} | {id, close: X}
              | {id, use: X, containing: Z or [Z, ...]} (all of the Zs; a Z that is a list means
                any of it) | {id, goto: X, intent: I}]
    order:   [[event id, event id], ...]   the first must happen before the second
    final:   [{in: [X, Y]} | {on: [X, Y]} | {off: [X, Y]} (nothing matching X in or on Y)
              | {near: [X, Y], within: m} (X held by a person beside Y, or put down near it)
              | {closed: X} | {open: X} | {holding: nothing | X} | {at: X}]
X, Y, Z are object ids or labels ("egg", "dining table"), or lists of them for any of several;
a label matches any object with it.
"""

from .astar import goal_mask
from .navigation import ARRIVE_MAX_DIST, ARRIVE_MIN_DIST
from .path_check import check_path
from .scene import Scene
from . import world

# How close "near" means, in metres from the place's footprint.
NEAR = 1.5


def _as_list(value):
    return list(value) if isinstance(value, (list, tuple)) else [value]


def matches(ref, obj_id, raw):
    """Whether ref (an id or a label, or a list of them for any of several) names obj_id."""
    if obj_id is None:
        return False
    if isinstance(ref, (list, tuple)):
        return any(matches(r, obj_id, raw) for r in ref)
    if ref == obj_id:
        return True
    label = raw[obj_id]["label"] if obj_id in raw else None
    return label is not None and label == str(ref).replace("_", " ")


def event_times(goal, events, raw):
    """Indices in the event log where the event goal happened."""
    times = []
    for index, event in enumerate(events):
        action = event["action"]
        if "pick" in goal:
            ok = action == "pick" and matches(goal["pick"], event["object"], raw)
        elif "place" in goal:
            thing, receptacle = goal["place"]
            ok = (action == "place" and matches(thing, event["object"], raw)
                  and matches(receptacle, event["receptacle"], raw))
        elif "open" in goal or "close" in goal:
            kind = "open" if "open" in goal else "close"
            ok = action == kind and matches(goal[kind], event["object"], raw)
        elif "use" in goal:
            ok = action == "use" and matches(goal["use"], event["object"], raw) and all(
                any(matches(z, c, raw) for c in event.get("contents", ()))
                for z in _as_list(goal.get("containing", []))
            )
        elif "goto" in goal:
            ok = (action == "goto" and event.get("reached")
                  and matches(goal["goto"], event["target"], raw)
                  and ("intent" not in goal or event.get("intent") == goal["intent"]))
        else:
            raise ValueError(f"unknown event goal {goal}")
        if ok:
            times.append(index)
    return times


def final_holds(fact, episode, state, raw, scene):
    if "in" in fact or "on" in fact or "off" in fact:
        # Through stacking too: a cup in a bowl on the counter is on the counter.
        thing, receptacle = fact.get("in") or fact.get("on") or fact["off"]
        found = any(
            matches(thing, obj_id, raw)
            and any(matches(receptacle, parent, raw) for parent, _ in world.located(obj_id, raw, state))
            for obj_id in raw
        )
        return not found if "off" in fact else found
    if "near" in fact:
        thing, place = fact["near"]
        within = fact.get("within", NEAR)
        carried = world.carried(state, raw)
        places = [o for o in scene.objects if matches(place, o.id, raw)]
        for obj_id in raw:
            if not matches(thing, obj_id, raw):
                continue
            x, y = state["position"] if obj_id in carried else scene.get(obj_id).center[:2]
            if any(p.footprint_distance(x, y) <= within for p in places):
                return True
        return False
    if "closed" in fact or "open" in fact:
        opened = set(world.open_ids(episode, state))
        ref = fact.get("closed", fact.get("open"))
        targets = [o for o in raw if raw[o].get("openable") and matches(ref, o, raw)]
        if "closed" in fact:
            return all(o not in opened for o in targets)
        return any(o in opened for o in targets)
    if "holding" in fact:
        if fact["holding"] in (None, "nothing"):
            return not state["held"]
        return any(matches(fact["holding"], o, raw) for o in state["held"])
    if "at" in fact:
        cell = scene.cell(*state["position"])
        return any(
            goal_mask(scene, obj, ARRIVE_MIN_DIST, ARRIVE_MAX_DIST)[cell]
            for obj in scene.objects
            if obj.id in scene.public_ids() and matches(fact["at"], obj.id, raw)
        )
    raise ValueError(f"unknown final fact {fact}")


def route_check(episode, state):
    """Collision check and length of every leg, against the doors open while it was walked."""
    scenes = {}
    collision_free, length = True, 0.0
    for leg in state["legs"]:
        if len(leg["points"]) < 2:
            continue
        opened = tuple(leg.get("opened", world.open_ids(episode, {})))
        if opened not in scenes:
            scenes[opened] = Scene.load(
                world.REPO_ROOT / episode["scene"], hidden=episode.get("hidden_objects", ()),
                opened=opened, body=episode.get("body"),
            )
        check = check_path(scenes[opened], leg["points"])
        collision_free &= check["collision_free"]
        length += check["length"]
    return collision_free, round(length, 3)


def score_goals(episode, state):
    world.world(state)
    raw = world._raw_objects(episode)
    collision_free, length = route_check(episode, state)
    metrics = {
        "reported_infeasible": state["infeasible"],
        "collision_free": collision_free,
        "route_length": length,
        "walk_attempts": len(state["attempts"]),
        "actions": sum(1 for e in state["events"] if e["action"] not in ("goto", "step")),
    }
    if episode.get("expect_infeasible"):
        return {**metrics, "success": state["infeasible"], "goal_fraction": None}
    if "goals" not in episode:
        # A task given only as an instruction: nothing to score against.
        return {**metrics, "success": None, "goal_fraction": None}

    goals = episode["goals"]
    times = {g["id"]: event_times(g, state["events"], raw) for g in goals.get("events", [])}
    events_met = [name for name, t in times.items() if t]
    order_met, order_violations = [], []
    for before, after in goals.get("order", []):
        if times.get(before) and times.get(after):
            if min(times[before]) < max(times[after]):
                order_met.append([before, after])
            else:
                order_violations.append([before, after])
    final_scene = world.scene_for(episode, state)
    finals = [final_holds(f, episode, state, raw, final_scene) for f in goals.get("final", [])]

    total = len(times) + len(goals.get("order", [])) + len(finals)
    met = len(events_met) + len(order_met) + sum(finals)
    success = (
        not state["infeasible"] and collision_free and len(events_met) == len(times)
        and len(order_met) == len(goals.get("order", [])) and all(finals)
    )
    return {
        **metrics,
        "success": success,
        "goal_fraction": round(met / total, 3) if total else 1.0,
        "events_missing": [name for name, t in times.items() if not t],
        "order_violations": order_violations,
        "final_failed": [f for f, ok in zip(goals.get("final", []), finals) if not ok],
    }
