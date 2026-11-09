"""Symbolic interaction: what the person holds, opens, moves and switches on.

The world state lives in the episode state (state.json) next to the walked legs:
    held:     ids in the person's hands (at most HANDS)
    opened:   ids opened during the episode (the episode's own `opened` start open)
    closed:   ids from the episode's `opened` that were closed again
    placed:   {id: receptacle id} for everything put down
    placed_at: {id: [x, y]} where on a surface it was put (the edge nearest the person)
    revealed: ids seen by opening a container
    seen:     ids seen by looking around after a walk
    steps:    the subtasks the agent named with `mg step`, [{"id": n, "text": ...}]
    step:     the current subtask's id; walks, legs and actions are tagged with it
    events:   every walk and action in order, for scoring and the motion hand-off

Nothing here runs a simulator. Objects only change where they are and whether they are open;
the start renders stay as they were.
"""

import math

import numpy as np

from .astar import goal_mask
from .navigation import REPO_ROOT, end_heading
from .scene import Scene

HANDS = 2
# How far from an object's footprint the person can reach it, in metres. Walking to an
# object aims for REACH; acting allows a little more, as a smoothed route can end just short.
REACH = 1.0
REACH_SLACK = 0.15
# How far the person sees small things around them after walking somewhere, in metres.
SEE_DISTANCE = 3.5
# Things put on a surface go this far in from its edge nearest the person.
PLACE_INSET = 0.15
# How far the person may step back to make room for a door they open.
STEP_BACK = 1.2
# Receptacles that things go into rather than onto.
CONTAINER_LABELS = {
    "sink", "bowl", "pot", "pan", "mug", "cup", "garbage can", "laundry hamper", "box",
    "washing machine", "clothes dryer", "toaster",
}


def new_world():
    return {"held": [], "opened": [], "closed": [], "placed": {}, "placed_at": {}, "revealed": [], "seen": [],
            "steps": [], "step": None, "events": []}


def world(state):
    """The state's world part, added in place for states from before interaction existed."""
    for key, value in new_world().items():
        state.setdefault(key, value)
    return state


def open_ids(episode, state):
    world(state)
    start = [o for o in episode.get("opened", ()) if o not in state["closed"]]
    return sorted(set(start) | set(state["opened"]))


def _raw_objects(episode):
    import yaml

    data = yaml.safe_load((REPO_ROOT / episode["scene"]).read_text())
    return {o["id"]: o for o in data["objects"]}


def parent_of(obj_id, raw, state):
    """(parent id, "in" | "on") for where obj_id is now, or (None, None) on the floor or held."""
    if obj_id in state["placed"]:
        receptacle = state["placed"][obj_id]
        relation = "in" if is_container(raw[receptacle]) else "on"
        return receptacle, relation
    entry = raw[obj_id]
    if entry.get("inside"):
        return entry["inside"], "in"
    if entry.get("supported_by"):
        return entry["supported_by"], "on"
    return None, None


def is_container(entry):
    return entry.get("openable", False) or entry["label"] in CONTAINER_LABELS


def carried(state, raw):
    """Everything the person carries: held objects and whatever is in or on them."""
    out = set(state["held"])
    changed = True
    while changed:
        changed = False
        for obj_id in raw:
            if obj_id in out:
                continue
            parent, _ = parent_of(obj_id, raw, state)
            if parent in out:
                out.add(obj_id)
                changed = True
    return out


def moved_objects(episode, state, raw):
    """New positions for objects that were put down, or that rest on something that moved."""
    moved = {}
    cache = {}

    def center(obj_id, depth=0):
        if obj_id in cache:
            return cache[obj_id]
        entry = raw[obj_id]
        parent, relation = parent_of(obj_id, raw, state)
        result = entry["center"]
        if depth < 10 and parent is not None and (obj_id in state["placed"] or parent in moved):
            px, py, pz = center(parent, depth + 1)
            parent_size = raw[parent]["size"]
            if relation == "in":
                z = pz - parent_size[2] / 2 + entry["size"][2] / 2
            else:
                z = pz + parent_size[2] / 2 + entry["size"][2] / 2
            # The spot on a surface holds for furniture; on something that can be carried
            # (a plate), the thing travels with it, so it sits at its centre.
            if relation == "on" and obj_id in state.get("placed_at", {}) and not raw[parent].get("pickupable"):
                px, py = state["placed_at"][obj_id]
            result = [px, py, z]
            moved[obj_id] = {
                "center": result,
                "support": parent if relation == "on" else None,
                "inside": parent if relation == "in" else None,
            }
        cache[obj_id] = result
        return result

    # Resolve placed objects first, then anything that rests on a moved object.
    for obj_id in state["placed"]:
        center(obj_id)
    changed = True
    while changed:
        changed = False
        for obj_id in raw:
            if obj_id in moved:
                continue
            parent, _ = parent_of(obj_id, raw, state)
            if parent in moved:
                cache.pop(obj_id, None)
                center(obj_id)
                changed = obj_id in moved or changed
    return moved


def scene_for(episode, state=None):
    """The scene as it is now: opened, moved and carried objects applied."""
    state = world(state if state is not None else {})
    raw = _raw_objects(episode)
    return Scene.load(
        REPO_ROOT / episode["scene"],
        hidden=episode.get("hidden_objects", ()),
        opened=open_ids(episode, state),
        body=episode.get("body"),
        moved=moved_objects(episode, state, raw),
        removed=carried(state, raw),
    )


def resolve(scene, state, ref):
    """An object id for ref: an id the person can see, or a visible object with that label.

    For a label, one within reach wins over the nearest one.
    """
    public = scene.public_ids()
    if ref in public:
        return ref
    label = ref.replace("_", " ")
    matches = [o for o in scene.objects if o.id in public and o.label == label]
    if not matches:
        return None
    x, y = state["position"]
    return min(matches, key=lambda o: (not reachable(scene, state, o.id), o.footprint_distance(x, y))).id


def containers(scene, obj_id):
    """The objects obj_id is in or on, nearest first."""
    chain = []
    current = scene.get(obj_id)
    for _ in range(10):
        parent = current.inside or current.support
        if parent is None or parent in chain:
            break
        chain.append(parent)
        current = scene.get(parent)
    return chain


def reach_goal(scene, target):
    """For an object in or on something (an egg on a deep counter), where it can be reached from.

    Returns None for anything else, which keeps the usual arrival band.
    """
    from .navigation import ARRIVE_MIN_DIST

    if target not in scene.public_ids():
        return None
    obj = scene.get(target)
    if obj.inside is not None and scene.get(obj.inside).openable:
        return reach_goal(scene, obj.inside) if (scene.get(obj.inside).inside or scene.get(obj.inside).support) \
            else goal_mask(scene, scene.get(obj.inside), ARRIVE_MIN_DIST, REACH)
    if obj.inside is None and obj.support is None:
        return None
    return goal_mask(scene, obj, ARRIVE_MIN_DIST, REACH, ignore=containers(scene, target))


def reachable(scene, state, obj_id):
    """Whether the person, where they stand, can reach obj_id with nothing tall in between.

    What it is in or on (the fridge an egg is in) doesn't block the reach, and anything
    inside an openable container (a fridge, a drawer) is in reach wherever the container is.
    """
    cell = scene.cell(*state["position"])
    obj = scene.get(obj_id)
    if obj.inside is not None and scene.get(obj.inside).openable:
        return reachable(scene, state, obj.inside)
    return bool(goal_mask(scene, obj, 0.0, REACH + REACH_SLACK, ignore=containers(scene, obj_id))[cell])


def declare_step(state, text):
    """Start a new subtask: what follows, until the next one, carries it out."""
    world(state)
    step_id = len(state["steps"]) + 1
    state["steps"].append({"id": step_id, "text": text})
    state["step"] = step_id
    state["events"].append({"action": "step", "id": step_id, "step": step_id, "text": text,
                            "position": [round(v, 3) for v in state["position"]]})
    return {"step": step_id, "text": text}


def _tag(entry, state):
    if state.get("step") is not None:
        entry["step"] = state["step"]
    return entry


def _record(state, action, **details):
    event = _tag({"action": action, **details, "position": [round(v, 3) for v in state["position"]]}, state)
    state["events"].append(event)
    if state["legs"]:
        state["legs"][-1].setdefault("actions", []).append({"action": action, **details})
    return event


def _fail(reason):
    return {"done": False, "reason": reason}


def _target(scene, state, ref, what="object"):
    obj_id = resolve(scene, state, ref)
    if obj_id is None:
        return None, _fail(f"no visible {what} {ref!r}")
    return obj_id, None


def contents(obj_id, raw, state, scene):
    """Ids directly or indirectly in or on obj_id (things inside things), as they are now."""
    present = {o.id for o in scene.objects}
    out = []
    frontier = [obj_id]
    while frontier:
        current = frontier.pop()
        for other in raw:
            if other in present and other not in out and parent_of(other, raw, state)[0] == current:
                out.append(other)
                frontier.append(other)
    return sorted(out)


def step_back(scene, state, obj_id, opened_before):
    """Move the person to the nearest free spot after a door swung over where they stand."""
    x, y = state["position"]
    if scene.clearance_at(x, y) >= scene.body_radius:
        return True
    free = scene.clearance >= scene.body_radius
    ix, iy = np.nonzero(free)
    if len(ix) == 0:
        return False
    xs, ys = scene.xs[ix], scene.ys[iy]
    distance = np.hypot(xs - x, ys - y)
    best = int(np.argmin(distance))
    if distance[best] > STEP_BACK:
        return False
    new = [float(xs[best]), float(ys[best])]
    state["legs"].append({
        "target": f"{new[0]:.2f},{new[1]:.2f}", "intent": "stand", "kind": "step_back",
        "points": [list(state["position"]), new],
        "end_heading": end_heading(scene, obj_id, [list(state["position"]), new]),
        # Checked with the door still closed: the person steps back as it opens.
        "opened": opened_before, "actions": [],
    })
    _tag(state["legs"][-1], state)
    state["position"] = new
    return True


def act(episode, state, action, ref, receptacle_ref=None):
    """Do one action where the person stands. Returns a result dict; state changes only on success."""
    world(state)
    raw = _raw_objects(episode)
    scene = scene_for(episode, state)
    if action == "place":
        return _place(episode, state, scene, raw, ref, receptacle_ref)
    obj_id, error = _target(scene, state, ref)
    if error:
        return error
    obj = scene.get(obj_id)
    if action == "pick" and len(state["held"]) >= HANDS:
        return _fail(f"both hands are full ({', '.join(state['held'])}); put something down first")
    if not reachable(scene, state, obj_id):
        return _fail(f"{obj_id} is out of reach from here; walk to it first")

    if action in ("open", "close"):
        if not obj.openable:
            return _fail(f"{obj_id} can't be opened or closed")
        if (action == "open") == obj.is_open:
            return _fail(f"{obj_id} is already {'open' if obj.is_open else 'closed'}")
        if action == "open":
            opened_before = open_ids(episode, state)
            state["opened"].append(obj_id)
            if obj_id in state["closed"]:
                state["closed"].remove(obj_id)
            after = scene_for(episode, state)
            inside = [o for o in contents(obj_id, raw, state, after) if o in after.public_ids()]
            # Recorded on the leg that brought the person here, before any step back.
            _record(state, "open", object=obj_id, label=obj.label, contents=inside)
            if not step_back(after, state, obj_id, opened_before):
                state["opened"].remove(obj_id)
                state["events"].pop()
                if state["legs"]:
                    state["legs"][-1]["actions"].pop()
                return _fail(f"no room to open {obj_id} from here")
            state["revealed"] = sorted(set(state["revealed"]) | set(inside))
            return {"done": True, "opened": obj_id, "contents": [
                {"id": o, "label": after.get(o).label} for o in inside
            ], "position": [round(v, 2) for v in state["position"]]}
        if obj_id in state["opened"]:
            state["opened"].remove(obj_id)
        else:
            state["closed"].append(obj_id)
        _record(state, "close", object=obj_id, label=obj.label)
        return {"done": True, "closed": obj_id}

    if action == "pick":
        if not obj.pickupable:
            return _fail(f"{obj_id} can't be picked up")
        if len(state["held"]) >= HANDS:
            return _fail(f"both hands are full ({', '.join(state['held'])}); put something down first")
        state["held"].append(obj_id)
        state["placed"].pop(obj_id, None)
        _record(state, "pick", object=obj_id, label=obj.label)
        return {"done": True, "holding": list(state["held"])}

    if action == "use":
        if not obj.toggleable:
            return _fail(f"{obj_id} can't be switched on")
        if obj.openable and obj.is_open:
            return _fail(f"close {obj_id} before using it")
        inside = contents(obj_id, raw, state, scene)
        if obj.label == "faucet":
            # A faucet runs into the sink below it.
            sinks = [o for o in scene.objects if o.label == "sink" and o.footprint_distance(*obj.center[:2]) < 0.5]
            for sink in sinks:
                inside += contents(sink.id, raw, state, scene)
        _record(state, "use", object=obj_id, label=obj.label, contents=sorted(set(inside)))
        return {"done": True, "used": obj_id, "contents": sorted(set(inside))}

    return _fail(f"unknown action {action!r}")


def _place(episode, state, scene, raw, ref, receptacle_ref):
    held_or_carried = carried(state, raw)
    obj_id = ref if ref in held_or_carried else next(
        (o for o in state["held"] if raw[o]["label"] == ref.replace("_", " ")), None,
    )
    if obj_id is None:
        return _fail(f"not holding {ref!r}")
    # Into something in hand (cracking an egg into a held bowl) needs no reach.
    if receptacle_ref in held_or_carried:
        receptacle_id = receptacle_ref
        receptacle = raw[receptacle_id]
        label, openable, is_open = receptacle["label"], receptacle.get("openable", False), True
        if not receptacle.get("receptacle"):
            return _fail(f"{receptacle_id} can't hold things")
    else:
        receptacle_id, error = _target(scene, state, receptacle_ref, "receptacle")
        if error:
            return error
        box = scene.get(receptacle_id)
        label, openable, is_open = box.label, box.openable, box.is_open
        if not box.receptacle:
            return _fail(f"{receptacle_id} can't hold things")
        if not reachable(scene, state, receptacle_id):
            return _fail(f"{receptacle_id} is out of reach from here; walk to it first")
    if receptacle_id == obj_id:
        return _fail("can't put something into itself")
    if openable and not is_open:
        return _fail(f"open {receptacle_id} first")
    if obj_id in state["held"]:
        state["held"].remove(obj_id)
    state["placed"][obj_id] = receptacle_id
    relation = "in" if is_container(raw[receptacle_id]) else "on"
    state.setdefault("placed_at", {}).pop(obj_id, None)
    if relation == "on" and receptacle_id not in held_or_carried:
        state["placed_at"][obj_id] = surface_spot(scene.get(receptacle_id), state["position"])
    at = state["placed_at"].get(obj_id)
    _record(state, "place", object=obj_id, label=raw[obj_id]["label"], receptacle=receptacle_id,
            receptacle_label=label, relation=relation, **({"at": at} if at else {}))
    return {"done": True, "placed": obj_id, relation: receptacle_id, "holding": list(state["held"])}


def surface_spot(receptacle, position):
    """Where on a surface something is put: its nearest point to the person, inset from the edge."""
    x, y = position
    best = None
    for x0, y0, x1, y1 in receptacle.rects:
        inset_x = min(PLACE_INSET, (x1 - x0) / 2)
        inset_y = min(PLACE_INSET, (y1 - y0) / 2)
        spot = (min(max(x, x0 + inset_x), x1 - inset_x), min(max(y, y0 + inset_y), y1 - inset_y))
        if best is None or math.dist(spot, position) < math.dist(best, position):
            best = spot
    return [round(best[0], 3), round(best[1], 3)]


def held_entries(episode, state):
    raw = _raw_objects(episode)
    out = []
    for obj_id in state.get("held", []):
        entry = {"id": obj_id, "label": raw[obj_id]["label"]}
        inner = sorted(o for o in carried({**state, "held": [obj_id]}, raw) if o != obj_id)
        if inner:
            entry["carrying"] = inner
        out.append(entry)
    return out


def located(obj_id, raw, state):
    """The chain of receptacles obj_id is in or on, nearest first."""
    chain = []
    current = obj_id
    for _ in range(10):
        parent, relation = parent_of(current, raw, state)
        if parent is None:
            break
        chain.append((parent, relation))
        current = parent
    return chain


def distance(a, b):
    return math.dist(a, b)


def goto(episode, state, target, intent=None):
    """Walk to an object id, a label (nearest visible match) or an x,y position."""
    from .navigation import parse_target, walk_to

    world(state)
    scene = scene_for(episode, state)
    if parse_target(scene, target) is None:
        resolved = resolve(scene, state, target)
        if resolved is not None:
            target = resolved
    legs_before = len(state["legs"])
    result = walk_to(scene, state, target, intent, goal=reach_goal(scene, target))
    if len(state["legs"]) > legs_before:
        leg = state["legs"][-1]
        leg["opened"] = open_ids(episode, state)
        leg["actions"] = []
        _tag(leg, state)
    label = scene.get(target).label if target in scene.public_ids() else None
    state["events"].append(_tag({
        "action": "goto", "target": target, "label": label, "intent": intent,
        "reached": result["reached"], "position": [round(v, 3) for v in state["position"]],
    }, state))
    if result["reached"]:
        seen = look_around(scene, state)
        if seen:
            result["seen"] = seen
    return result


def look_around(scene, state):
    """Mark what the person can see from where they stand: objects within SEE_DISTANCE, not
    behind a wall or in a closed container. Returns the newly seen ones.

    The start renders miss small things (a tomato on a counter); a person walking into the
    kitchen would see them.
    """
    x, y = state["position"]
    walls = [o for o in scene.objects if o.label == "wall"]
    public = scene.public_ids()
    already = set(state.setdefault("seen", [])) | set(state["revealed"])
    new = []
    for obj in scene.objects:
        if obj.id not in public or obj.id in already or obj.label in ("wall", "door"):
            continue
        if obj.footprint_distance(x, y) > SEE_DISTANCE:
            continue
        cx, cy = obj.center[:2]
        t = np.linspace(0.0, 1.0, max(2, int(math.dist((x, y), (cx, cy)) / 0.05)))
        px, py = x + t * (cx - x), y + t * (cy - y)
        if any(w.covers(px, py).any() for w in walls):
            continue
        new.append(obj)
    state["seen"] = sorted(already - set(state["revealed"]) | {o.id for o in new})
    return [
        {"id": o.id, "label": o.label, **({"in": o.inside} if o.inside else {"on": o.support} if o.support else {})}
        for o in sorted(new, key=lambda o: o.id)
    ]
