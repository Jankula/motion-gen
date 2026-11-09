"""The motion hand-off: a run's walks and actions as motion segments, grouped into subtasks.

    build_script(episode, state)  -> (script, walk tasks)
    export(run_dir)               -> writes <run_dir>/motion/

The script (motion_script.json) lists, in order, every motion the person makes: walk, turn,
step_back, open, close, reach_grasp, put_down, use, sit_down, stand_up. Each carries where
it happens, what it acts on, which hand, a height, an estimated duration and a caption. The
segments are grouped into subtasks: the ones the agent named with `mg step`, or, where it named
none, one per walk with a templated text. An object timeline says which segment opens, picks up
or puts down what, so the motion side (and a later video) can re-time everything from its own
clip lengths.

Every walk also becomes a task file in the format of the partner's walking code
(Jankula/motion-gen, walking/tasks/*.json), runnable as `python make_motion.py walk_01.json out.npz`.
Its frame is y up with the floor as [x, z]; ours is z up with the floor as [x, y]. The mapping
[X, Z] = [x, -y], heading_partner = heading + 90 keeps both frames right-handed.
"""

import json
import math
from pathlib import Path

import numpy as np
import yaml

from . import world
from .navigation import REPO_ROOT, load_episode, new_state
from .path_check import path_length, sample_path

FPS = 30
# Duration estimates in seconds; the motion side has the final say.
WALK_SPEED = 1.2
CARRY_SPEED = 1.0
WALK_START = 0.8
WALK_STOP = 1.0
TURN_BASE = 0.6
TURN_PER_90 = 0.9
ACTION_SECONDS = {
    "open": 1.5, "close": 1.2, "reach_grasp": 1.2, "put_down": 1.2, "use": 1.0,
    "sit_down": 2.0, "stand_up": 1.6, "step_back": 1.2,
}
# Standing still added to the end of each partner clip, so a slow walk isn't cut off.
END_HOLD = 1.5
# Turns smaller than this (degrees) are left to the walk; an action needs a turn beyond ACTION_TURN.
MIN_TURN = 15.0
ACTION_TURN = 45.0
# Half the partner body's width with swinging arms (their E04 notes: 0.28 + 0.035 m). Where the
# clearance along the path is below it, their code turns the shoulders or side-steps.
PARTNER_HALF_WIDTH = 0.315
# Boxes within this distance of a path go into its partner task as obstacles.
OBSTACLE_RANGE = 1.0
# Narrow stretches closer together than this along the path count as one.
NARROW_MERGE = 0.3
SIMPLIFY_TOLERANCE = 0.03
PATH_TOLERANCE = 0.15
# Handles and switches: this high when the object allows it.
HANDLE_HEIGHT = 1.0
SEAT_HEIGHT = 0.46
MOTION_OF = {"pick": "reach_grasp", "place": "put_down", "open": "open", "close": "close", "use": "use"}
FRAME = {
    "ours": "metres; x, y on the floor, z up; heading in degrees counter-clockwise from +x",
    "partner": "[X, Z] = [x, -y], Y = z (up); heading_deg = heading + 90 (0 faces +Z, 90 faces +X)",
    "unity": "AI2-THOR position {x: x, y: z, z: y}; yaw = 90 - heading",
}


# --- frames -----------------------------------------------------------------------------------

def wrap(degrees):
    """An angle in (-180, 180]."""
    value = (degrees + 180.0) % 360.0 - 180.0
    return 180.0 if value == -180.0 else value


def to_partner(x, y):
    return [round(float(x), 3), round(float(-y), 3)]


def from_partner(px, pz):
    return [float(px), float(-pz)]


def heading_to_partner(heading):
    return round(wrap(heading + 90.0), 1)


def heading_from_partner(heading_deg):
    return wrap(heading_deg - 90.0)


def direction(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def turn_seconds(angle):
    return TURN_BASE + TURN_PER_90 * abs(angle) / 90.0


# --- geometry -----------------------------------------------------------------------------------

def simplify(points, tolerance):
    """Douglas-Peucker: the fewest points that stay within tolerance of the polyline."""
    points = np.asarray(points, dtype=float)
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    ab = b - a
    norm = np.linalg.norm(ab)
    rel = points - a
    if norm < 1e-9:
        distance = np.linalg.norm(rel, axis=1)
    else:
        distance = np.abs(ab[0] * rel[:, 1] - ab[1] * rel[:, 0]) / norm
    index = int(np.argmax(distance))
    if distance[index] <= tolerance:
        return np.array([a, b])
    left = simplify(points[:index + 1], tolerance)
    right = simplify(points[index:], tolerance)
    return np.concatenate([left[:-1], right])


def partner_path(scene, points):
    """The walk's polyline with only its real corners, still clear of obstacles."""
    tolerance = SIMPLIFY_TOLERANCE
    while tolerance >= 0.005:
        simple = simplify(points, tolerance)
        if all(scene.clearance_at(x, y) >= scene.body_radius - 0.02 for x, y in sample_path(simple)):
            return simple
        tolerance /= 2
    return np.asarray(points, dtype=float)


def first_heading(points):
    """Direction of the first piece of path longer than 5 cm."""
    for b in points[1:]:
        if math.dist(points[0], b) > 0.05:
            return direction(points[0], b)
    return direction(points[0], points[-1]) if len(points) > 1 else None


def last_heading(points):
    for a in points[-2::-1]:
        if math.dist(a, points[-1]) > 0.05:
            return direction(a, points[-1])
    return direction(points[0], points[-1]) if len(points) > 1 else None


def rect_distances(rect, samples):
    x0, y0, x1, y1 = rect
    dx = np.maximum(np.maximum(x0 - samples[:, 0], 0.0), samples[:, 0] - x1)
    dy = np.maximum(np.maximum(y0 - samples[:, 1], 0.0), samples[:, 1] - y1)
    return np.hypot(dx, dy)


def narrow_stretches(scene, points):
    """Stretches of the path where the free space is narrower than the partner's walking body."""
    samples = sample_path(points)
    along = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(samples, axis=0), axis=1))])
    clearance = np.array([scene.clearance_at(x, y) for x, y in samples])
    narrow = clearance < PARTNER_HALF_WIDTH
    runs = []
    start = None
    for i, flag in enumerate(np.append(narrow, False)):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            if runs and along[start] - along[runs[-1][1] - 1] < NARROW_MERGE:
                runs[-1][1] = i
            else:
                runs.append([start, i])
            start = None
    stretches = []
    for start, end in runs:
        lowest = start + int(np.argmin(clearance[start:end]))
        stretches.append({
            "from_m": round(float(along[start]), 2), "to_m": round(float(along[end - 1]), 2),
            "min_clearance": round(float(clearance[lowest]), 3),
            "at": [round(float(v), 2) for v in samples[lowest]],
        })
    return stretches


def rooms_along(scene, points):
    rooms = []
    for x, y in sample_path(points)[::5]:
        room = scene.room_of(x, y)
        if room and (not rooms or rooms[-1] != room):
            rooms.append(room)
    return rooms


def nearby_obstacles(scene, points):
    """Boxes that block the body within OBSTACLE_RANGE of the path, in the partner's format."""
    samples = sample_path(points)
    out = []
    for obj in scene.objects:
        if not obj.blocks_body(scene.body_height):
            continue
        for k, rect in enumerate(obj.rects):
            if rect_distances(rect, samples).min() > OBSTACLE_RANGE:
                continue
            x0, y0, x1, y1 = rect
            label = obj.id if len(obj.rects) == 1 else f"{obj.id} part {k + 1}"
            out.append({
                "label": label,
                "center": to_partner((x0 + x1) / 2, (y0 + y1) / 2),
                "size": [round(x1 - x0, 3), round(obj.z_range[1], 3), round(y1 - y0, 3)],
                "yaw_deg": 0,
            })
    return out


# --- words --------------------------------------------------------------------------------------

def room_name(room_id):
    if not room_id:
        return None
    return " ".join(part for part in room_id.split("_") if not part.isdigit())


def label_of(obj_id, raw):
    if obj_id in raw:
        return raw[obj_id]["label"]
    return None


def plural(label):
    if label.endswith(("s", "sh", "ch", "x")):
        return label + "es"
    if label.endswith("y") and label[-2:-1] not in "aeiou":
        return label[:-1] + "ies"
    return label + "s"


def counted(label, n):
    """"an egg", "2 eggs"."""
    if n == 1:
        return ("an " if label[0] in "aeiou" else "a ") + label
    return f"{n} {plural(label)}"


def thing(obj_id, raw, sim=None):
    """"the bowl", or "the bowl with 2 eggs" when it carries something."""
    text = f"the {label_of(obj_id, raw) or obj_id}"
    if sim is not None:
        inner = [label_of(o, raw) for o in world.carried({**sim, "held": [obj_id]}, raw) if o != obj_id]
        if inner:
            text += " with " + " and ".join(counted(label, inner.count(label)) for label in sorted(set(inner)))
    return text


def carrying_words(hands, raw, sim):
    held = [(hand, obj) for hand, obj in hands.items() if obj]
    if not held:
        return ""
    if len(held) == 2 and held[0][1] == held[1][1]:
        return f" carrying {thing(held[0][1], raw, sim)} with both hands"
    return " carrying " + " and ".join(f"{thing(obj, raw, sim)} in the {hand} hand" for hand, obj in held)


def route_words(rooms):
    names = [room_name(r) for r in rooms]
    if len(names) >= 2:
        return f" from the {names[0]} into the {names[-1]}"
    if names:
        return f" in the {names[0]}"
    return ""


# --- replay -------------------------------------------------------------------------------------

def _apply(sim, event, final_placed_at, last_place):
    """Change the replayed world state the way world.act did for this event."""
    action, obj = event["action"], event.get("object")
    if action == "open":
        if obj in sim["closed"]:
            sim["closed"].remove(obj)
        if obj not in sim["opened"]:
            sim["opened"].append(obj)
    elif action == "close":
        if obj in sim["opened"]:
            sim["opened"].remove(obj)
        elif obj not in sim["closed"]:
            sim["closed"].append(obj)
    elif action == "pick":
        sim["held"].append(obj)
        sim["placed"].pop(obj, None)
    elif action == "place":
        if obj in sim["held"]:
            sim["held"].remove(obj)
        sim["placed"][obj] = event["receptacle"]
        sim["placed_at"].pop(obj, None)
        at = event.get("at")
        # Runs from before events recorded the spot: the state's final spot fits the last placement.
        if at is None and last_place.get(obj) is event:
            at = final_placed_at.get(obj)
        if at is not None and event.get("relation", "on") == "on":
            sim["placed_at"][obj] = at


def _box_now(obj_id, raw, moved):
    entry = raw[obj_id]
    center = moved[obj_id]["center"] if obj_id in moved else entry["center"]
    return np.asarray(center, dtype=float), np.asarray(entry["size"], dtype=float)


def _handle_point(center, size, position):
    """Where a hand meets a box: its nearest side to the person, at handle height if it can."""
    x = min(max(position[0], center[0] - size[0] / 2), center[0] + size[0] / 2)
    y = min(max(position[1], center[1] - size[1] / 2), center[1] + size[1] / 2)
    z0, z1 = center[2] - size[2] / 2, center[2] + size[2] / 2
    z = min(max(HANDLE_HEIGHT, z0 + 0.15 * size[2]), z1 - 0.15 * size[2])
    return [round(float(x), 3), round(float(y), 3), round(float(z), 3)]


def _events(state):
    """The event log; navigation-only runs (legs, no events) get one goto per leg."""
    if state.get("events"):
        return state["events"]
    return [{"action": "goto", "target": leg["target"], "intent": leg.get("intent"), "reached": True}
            for leg in state.get("legs", [])]


class _Builder:
    def __init__(self, episode, state, raw):
        self.episode, self.state, self.raw = episode, state, raw
        self.segments, self.objects, self.tasks = [], [], {}
        self.position = list(episode["start"])
        self.facing = float(episode.get("heading", 0.0))
        self.hands = {"right": None, "left": None}
        self.seated_on = None
        self.group = 0
        self.sim = world.world(new_state(episode))
        self._scenes = {}

    def scene(self):
        key = json.dumps([world.open_ids(self.episode, self.sim), self.sim["placed"], self.sim["placed_at"],
                          self.sim["held"]], sort_keys=True)
        if key not in self._scenes:
            self._scenes = {key: world.scene_for(self.episode, self.sim)}
        return self._scenes[key]

    def add(self, motion, step, **fields):
        seg = {"i": len(self.segments), "motion": motion, "group": self.group, "step": step, **fields}
        self.segments.append(seg)
        return seg

    def stand_up(self, step):
        if self.seated_on is not None:
            self.add("stand_up", step, object=self.seated_on, at=self._at(),
                     duration_est=ACTION_SECONDS["stand_up"],
                     caption=f"a person stands up from {thing(self.seated_on, self.raw)}")
            self.seated_on = None

    def _at(self):
        return [round(v, 3) for v in self.position]

    def turn_to(self, heading, step, why=None):
        angle = wrap(heading - self.facing)
        if abs(angle) >= MIN_TURN:
            side = "left" if angle > 0 else "right"
            self.add("turn", step, at=self._at(), from_heading=round(self.facing, 1), to_heading=round(heading, 1),
                     angle=round(angle, 1), duration_est=round(turn_seconds(angle), 2),
                     caption=f"a person turns on the spot {abs(angle):.0f} degrees to the {side}"
                             + (f" {why}" if why else ""))
        self.facing = heading

    # walking ------------------------------------------------------------------------------------
    def walk(self, leg, event):
        step = event.get("step", leg.get("step"))
        points = [list(p) for p in leg["points"]]
        length = path_length(points)
        target = leg["target"]
        end = leg.get("end_heading")
        self.group += 1
        self.stand_up(step)
        if length < 0.05:
            # Already there: at most a turn to face the target.
            if end is not None:
                before = len(self.segments)
                self.turn_to(end, step, f"to face {thing(target, self.raw)}" if target in self.raw else None)
                if len(self.segments) > before:
                    self.segments[-1].update(target=target, label=label_of(target, self.raw))
            self.position = points[-1]
            self.sit_if_asked(leg, step)
            return
        scene = self.scene()
        simple = partner_path(scene, points)
        start_heading = first_heading(simple.tolist())
        self.turn_to(start_heading, step, "to set off")
        last = last_heading(simple.tolist())
        end = last if end is None else end
        end_turn = wrap(end - last)
        carrying = [o for o in self.hands.values() if o]
        speed = CARRY_SPEED if carrying else WALK_SPEED
        duration = WALK_START + length / speed + WALK_STOP + (turn_seconds(end_turn) if abs(end_turn) > 3 else 0)
        rooms = rooms_along(scene, points)
        narrow = narrow_stretches(scene, points)
        where = f" to {thing(target, self.raw)}" if target in self.raw else " to a spot"
        caption = f"a person walks{route_words(rooms)}{where}{carrying_words(self.hands, self.raw, self.sim)}"
        seg = self.add(
            "walk", step, target=target, label=label_of(target, self.raw), intent=leg.get("intent"),
            **{"from": [round(v, 3) for v in points[0]], "to": [round(v, 3) for v in points[-1]]},
            length=round(length, 2), end_heading=round(end, 1),
            carrying={hand: obj for hand, obj in self.hands.items() if obj},
            rooms=rooms, narrow=narrow, path=[[round(x, 3), round(y, 3)] for x, y in points],
            duration_est=round(duration, 2), caption=caption,
        )
        name = f"walk_{sum(s['motion'] == 'walk' for s in self.segments):02d}.json"
        seg["partner_task"] = f"walks/{name}"
        self.tasks[name] = self.partner_task(seg, scene, simple, start_heading, end, last)
        self.position, self.facing = points[-1], end
        self.sit_if_asked(leg, step)

    def sit_if_asked(self, leg, step):
        """`goto --then sit`: sit down on the target, also when the person was already beside it."""
        target = leg["target"]
        if leg.get("intent") == "sit" and target in self.raw:
            center, size = _box_now(target, self.raw, world.moved_objects(self.episode, self.sim, self.raw))
            seat = [round(float(center[0]), 3), round(float(center[1]), 3),
                    round(float(min(center[2] + size[2] / 2, SEAT_HEIGHT)), 3)]
            self.add("sit_down", step, object=target, label=label_of(target, self.raw), seat=seat, at=self._at(),
                     duration_est=ACTION_SECONDS["sit_down"], caption=f"a person sits down on {thing(target, self.raw)}")
            self.seated_on = target

    def step_back(self, leg, event):
        points = [list(p) for p in leg["points"]]
        self.add("step_back", event.get("step"), object=event["object"], label=label_of(event["object"], self.raw),
                 path=[[round(x, 3), round(y, 3)] for x, y in points],
                 **{"from": [round(v, 3) for v in points[0]], "to": [round(v, 3) for v in points[-1]]},
                 facing=round(self.facing, 1), duration_est=ACTION_SECONDS["step_back"],
                 caption=f"a person steps back to make room for {thing(event['object'], self.raw)} as it opens")
        self.position = points[-1]

    def partner_task(self, seg, scene, simple, start_heading, end, last):
        label = seg["label"] or "the marked spot"
        target = f"the {label}" if seg["label"] else label
        turn = wrap(end - last)
        parts = [
            f"One adult stands still for a moment, then walks along the marked path{route_words(seg['rooms'])}, "
            f"{seg['length']:.1f} m, to {target}.",
        ]
        if seg["carrying"]:
            parts.append(f"They are{carrying_words(self.hands, self.raw, self.sim)}.")
        for stretch in seg["narrow"]:
            parts.append(
                f"Between {stretch['from_m']:.1f} m and {stretch['to_m']:.1f} m along the path the nearest furniture "
                f"or wall is only {stretch['min_clearance']:.2f} m from the path.")
        if abs(turn) > 3:
            side = "left" if turn > 0 else "right"
            parts.append(f"At the end of the path they stop, turn on the spot about {abs(turn):.0f} degrees to the "
                         f"{side} to face {target}, and stand still until the clip ends.")
        else:
            parts.append(f"At the end of the path they stop facing {target} and stand still until the clip ends.")
        parts.append("The obstacles are the furniture and walls near the path, which must not be touched.")
        frames = math.ceil((seg["duration_est"] + END_HOLD) * FPS)
        return {
            "name": f"{self.episode['id']}-{Path(seg['partner_task']).stem}".replace("_", "-"),
            "title": f"Walk to {target}",
            "instruction": " ".join(parts),
            "fps": FPS,
            "frames": frames,
            "start": {"state": "standing", "position": to_partner(*seg["from"]),
                      "heading_deg": heading_to_partner(start_heading)},
            "end": {"state": "standing", "position": to_partner(*seg["to"]), "heading_deg": heading_to_partner(end)},
            "path": {"points": [to_partner(x, y) for x, y in simple], "tolerance_m": PATH_TOLERANCE},
            "obstacles": nearby_obstacles(scene, simple),
            "source": {"episode": self.episode["id"], "segment": seg["i"], "expected_seconds": seg["duration_est"]},
        }

    # actions ------------------------------------------------------------------------------------
    def free_hand(self):
        return next((h for h in ("right", "left") if self.hands[h] is None), None)

    def hand_holding(self, obj_id):
        """The hand holding obj_id, or the container it's in or on."""
        for hand, held in self.hands.items():
            if held and (held == obj_id or obj_id in world.carried({**self.sim, "held": [held]}, self.raw)):
                return hand
        return None

    def act(self, event, final_placed_at, last_place):
        action, obj = event["action"], event["object"]
        motion = MOTION_OF[action]
        step = event.get("step")
        moved = world.moved_objects(self.episode, self.sim, self.raw)
        fields = {"object": obj, "label": label_of(obj, self.raw)}
        if action == "place":
            receptacle = event["receptacle"]
            relation = event.get("relation", "on")
            hand = self.hand_holding(obj)
            fields.update(receptacle=receptacle, receptacle_label=label_of(receptacle, self.raw), relation=relation)
            if self.hand_holding(receptacle):
                # Into something in hand: in front of the body, at waist height.
                ahead = math.radians(self.facing)
                contact = [self.position[0] + 0.35 * math.cos(ahead), self.position[1] + 0.35 * math.sin(ahead), 1.0]
                fields["into_held"] = True
            else:
                center, size = _box_now(receptacle, self.raw, moved)
                top = center[2] + size[2] / 2
                at = event.get("at") or (final_placed_at.get(obj) if last_place.get(obj) is event else None)
                if relation == "on" and at is not None:
                    contact = [at[0], at[1], top]
                elif relation == "in" and self.raw[receptacle].get("openable"):
                    contact = list(center)
                else:
                    contact = [center[0], center[1], top]
            words = f"puts {thing(obj, self.raw, self.sim)} {'into' if relation == 'in' else 'on'} " \
                    f"{thing(receptacle, self.raw)}"
        elif action == "pick":
            hand = self.free_hand()
            center, _ = _box_now(obj, self.raw, moved)
            contact = list(center)
            words = f"picks up {thing(obj, self.raw, self.sim)}"
        else:
            hand = self.free_hand()
            if hand is None:
                hand, fields["hands_full"] = "right", True
            center, size = _box_now(obj, self.raw, moved)
            contact = _handle_point(center, size, self.position)
            verb = {"open": "opens", "close": "closes", "use": "switches on"}[action]
            words = f"{verb} {thing(obj, self.raw)}"
            if action == "use" and event.get("contents"):
                fields["contents"] = event["contents"]
            if action == "open" and event.get("contents"):
                fields["revealed"] = event["contents"]
        contact = [round(float(v), 3) for v in contact]
        if not fields.get("into_held"):
            bearing = direction(self.position, contact)
            if abs(wrap(bearing - self.facing)) > ACTION_TURN:
                self.turn_to(bearing, step, f"towards {thing(obj if action != 'place' else event['receptacle'], self.raw)}")
        # Horizontal distance from where the person stands; beyond about 0.7 m a body needs a step
        # or a lean (world.py lets anything in an open fridge be reached from where the fridge is).
        reach = round(math.dist(self.position, contact[:2]), 2)
        seg = self.add(motion, step, **fields, hand=hand, contact=contact, height=contact[2], reach=reach,
                       at=self._at(),
                       seated=self.seated_on is not None or None,
                       duration_est=ACTION_SECONDS[motion],
                       caption=f"a person {words}" + (f" with the {hand} hand" if hand else ""))
        if seg["seated"] is None:
            del seg["seated"]

        # The object timeline, then the hands and the replayed world.
        if action in ("open", "close"):
            self.objects.append({"segment": seg["i"], "object": obj, "change": action})
        elif action == "use":
            self.objects.append({"segment": seg["i"], "object": obj, "change": "switched_on",
                                 "contents": event.get("contents", [])})
        elif action == "pick":
            self.objects.append({"segment": seg["i"], "object": obj, "change": "attach", "hand": hand})
            if hand:
                self.hands[hand] = obj
        _apply(self.sim, event, final_placed_at, last_place)
        if action == "place":
            moved_after = world.moved_objects(self.episode, self.sim, self.raw)
            center, _ = _box_now(obj, self.raw, moved_after)
            self.objects.append({"segment": seg["i"], "object": obj, "change": "detach", "hand": hand,
                                 "to": event["receptacle"], "relation": event.get("relation", "on"),
                                 "center": [round(float(v), 3) for v in center]})
            for h, held in self.hands.items():
                if held == obj:
                    self.hands[h] = None


def _subtasks(segments, state, raw):
    """Group segments: by the agent's steps where it named them, else one group per walk."""
    texts = {s["id"]: s["text"] for s in state.get("steps", [])}
    keys = []
    for seg in segments:
        key = ("agent", seg["step"]) if seg.get("step") in texts else ("derived", seg["group"])
        if not keys or keys[-1] != key:
            keys.append(key)
        seg["_key"] = key
    order = list(dict.fromkeys(keys))
    subtasks = []
    for number, key in enumerate(order, 1):
        members = [s for s in segments if s["_key"] == key]
        if key[0] == "agent":
            text = texts[key[1]]
        else:
            text = derived_text(members, raw)
        subtasks.append({"id": number, "text": text, "source": key[0], "segments": [s["i"] for s in members]})
        for s in members:
            s["subtask"] = number
    for seg in segments:
        del seg["_key"], seg["group"], seg["step"]
    return subtasks


def derived_text(members, raw):
    """"walk to the fridge, open the fridge, pick up 2 eggs, close the fridge"."""
    words = []  # [(key, phrase with {n}), count]
    for seg in members:
        label = seg.get("label")
        motion = seg["motion"]
        if motion == "walk":
            phrase = f"walk to the {label}" if label else "walk to a spot"
        elif motion == "turn" and label:
            phrase = f"turn to the {label}"
        elif motion == "reach_grasp":
            phrase = "pick up {thing}"
        elif motion == "put_down":
            phrase = f"put {{thing}} {'into' if seg['relation'] == 'in' else 'on'} the {seg['receptacle_label']}"
        elif motion in ("open", "close"):
            phrase = f"{motion} the {label}"
        elif motion == "use":
            phrase = f"switch on the {label}"
        elif motion == "sit_down":
            phrase = f"sit down on the {label}"
        else:
            continue
        key = (phrase, label)
        if words and words[-1][0] == key and "{thing}" in phrase:
            words[-1][1] += 1
        else:
            words.append([key, 1])
    out = []
    for (phrase, label), n in words:
        out.append(phrase.replace("{thing}", f"the {label}" if n == 1 else counted(label, n)))
    return ", ".join(out) or members[0]["motion"].replace("_", " ")


def build_script(episode, state):
    """The motion script for a finished run, and its partner walk tasks {file name: task}."""
    raw = world._raw_objects(episode)
    events = _events(state)
    legs = state.get("legs", [])
    final_placed_at = state.get("placed_at", {})
    last_place = {}
    for event in events:
        if event["action"] == "place":
            last_place[event["object"]] = event
    builder = _Builder(episode, state, raw)
    pointer = 0
    for index, event in enumerate(events):
        action = event["action"]
        if action == "goto":
            if event.get("reached") and pointer < len(legs):
                builder.walk(legs[pointer], event)
                pointer += 1
        elif action in MOTION_OF:
            builder.act(event, final_placed_at, last_place)
            if action == "open" and pointer < len(legs):
                # world.step_back added a leg if the door swung over the person.
                walks_left = sum(1 for e in events[index + 1:] if e["action"] == "goto" and e.get("reached"))
                leg = legs[pointer]
                if leg.get("kind") == "step_back" or len(legs) - pointer > walks_left:
                    builder.step_back(leg, event)
                    pointer += 1

    segments = builder.segments
    subtasks = _subtasks(segments, state, raw)
    clock = 0.0
    for seg in segments:
        seg["t_est"] = [round(clock, 2), round(clock + seg["duration_est"], 2)]
        clock += seg["duration_est"]
    source = yaml.safe_load((REPO_ROOT / episode["scene"]).read_text()).get("source", {})
    script = {
        "episode": episode["id"],
        "instruction": episode.get("instruction"),
        "house": {**({"split": source["split"], "index": source["index"]} if "split" in source else {}),
                  "scene": episode["scene"]},
        "start": {"position": list(episode["start"]), "heading": float(episode.get("heading", 0.0))},
        "frame": FRAME,
        "fps": FPS,
        "duration_est": round(clock, 2),
        "subtasks": subtasks,
        "segments": segments,
        "objects": builder.objects,
        "submitted": state.get("submitted"),
        "infeasible": state.get("infeasible"),
    }
    return script, builder.tasks


def find_episode(episode_id):
    """The episode file with this id, searched under episodes/."""
    for path in sorted((REPO_ROOT / "episodes").rglob("*.yaml")):
        if path.stem == episode_id:
            return path
    for path in sorted((REPO_ROOT / "episodes").rglob("*.yaml")):
        try:
            if yaml.safe_load(path.read_text()).get("id") == episode_id:
                return path
        except (yaml.YAMLError, AttributeError):
            continue
    return None


def export(run_dir, episode_path=None, out_dir=None):
    """Write motion_script.json, walks/*.json and route_motion.png for a run folder."""
    from .render_map import render_motion_route

    run_dir = Path(run_dir)
    state = json.loads((run_dir / "state.json").read_text())
    if episode_path is None:
        summary = json.loads((run_dir / "summary.json").read_text())
        episode_path = summary.get("episode_path") or find_episode(summary["episode"])
        if episode_path is None:
            raise FileNotFoundError(f"no episode file for {summary['episode']}; pass it explicitly")
    episode = load_episode(episode_path)
    script, tasks = build_script(episode, state)
    out = Path(out_dir) if out_dir else run_dir / "motion"
    walks = out / "walks"
    walks.mkdir(parents=True, exist_ok=True)
    for old in walks.glob("walk_*.json"):
        old.unlink()
    for name, task in tasks.items():
        (walks / name).write_text(json.dumps(task, indent=2))
    (out / "motion_script.json").write_text(json.dumps(script, indent=1))
    render_motion_route(world.scene_for(episode), script).save(out / "route_motion.png")
    return out
