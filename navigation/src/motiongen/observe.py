"""Pre-rendered views of a scene, what they show, and copies with numbered object marks.

A view is a directory with rgb.png and objects.json:
    {"name": "top", "objects": [{"id": "sofa_1", "pixels": 5120, "bbox": [u0, v0, u1, v1],
                                 "centroid": [u, v]}, ...]}
ids.png (the instance-id render) sits beside them for debugging and isn't read here.
"""

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .navigation import REPO_ROOT
from .scene import WALL

# Objects covering fewer pixels than this are too small to make out, so they aren't listed.
MIN_PIXELS = 80
BADGE_FILL = (255, 230, 0, 215)
TEXT = (20, 20, 20, 255)
# Badge radius as a fraction of the image's shorter side, kept within these pixel sizes.
BADGE_SCALE = 0.013
MIN_BADGE_RADIUS = 6
MAX_BADGE_RADIUS = 10
# Spot cost weights: hiding the labelled object, hiding other listed objects, distance from it.
OWN_WEIGHT = 3.0
OTHER_WEIGHT = 1.0
DISTANCE_WEIGHT = 0.5


def load_view(directory):
    directory = Path(directory)
    data = json.loads((directory / "objects.json").read_text())
    ids_file = directory / "ids.png"
    return {
        "name": data.get("name", directory.name),
        "rgb": directory / "rgb.png",
        "ids": ids_file if ids_file.exists() else None,
        # index is the object's value in ids.png: its position in objects.json, plus one.
        "objects": [
            {**o, "index": i + 1} for i, o in enumerate(data["objects"]) if o["pixels"] >= MIN_PIXELS
        ],
    }


def visible_ids(views):
    return {o["id"] for view in views for o in view["objects"]}


def assign_marks(ids, existing=None):
    """One number per object, shared by every view.

    Numbers already given (existing) stay, so images marked earlier stay right; new ids get the
    next numbers, in id order.
    """
    marks = dict(existing or {})
    next_mark = max(marks.values(), default=0) + 1
    for object_id in sorted(ids):
        if object_id not in marks:
            marks[object_id] = next_mark
            next_mark += 1
    return marks


def badge_radius(width, height):
    return min(MAX_BADGE_RADIUS, max(MIN_BADGE_RADIUS, round(BADGE_SCALE * min(width, height))))


def object_masks(view, objects, width, height):
    """Each object's pixel mask, from ids.png, or its bounding box when there is none."""
    if view.get("ids") is not None:
        ids = np.asarray(Image.open(view["ids"]).convert("RGB")).astype(np.int32)
        index_image = ids[..., 0] + 256 * ids[..., 1]
        return [index_image == o["index"] for o in objects]
    masks = []
    for o in objects:
        mask = np.zeros((height, width), dtype=bool)
        u0, v0, u1, v1 = o["bbox"]
        mask[v0:v1 + 1, u0:u1 + 1] = True
        masks.append(mask)
    return masks


def candidate_spots(obj, r, width, height):
    """The object's centroid, then spots ringing its bounding box, nearest first."""
    u, v = obj["centroid"]
    u0, v0, u1, v1 = obj["bbox"]
    spots = [(u, v)]
    for ring in range(4):
        pad = r + 2 + ring * (2 * r + 2)
        spots += [
            (u, v0 - pad), (u, v1 + pad), (u0 - pad, v), (u1 + pad, v),
            (u0 - pad, v0 - pad), (u1 + pad, v0 - pad), (u0 - pad, v1 + pad), (u1 + pad, v1 + pad),
        ]
    return [(x, y) for x, y in spots if r <= x <= width - 1 - r and r <= y <= height - 1 - r]


def place_badges(objects, masks, width, height, r):
    """A badge centre per object that hides as little as possible of what's listed.

    A spot costs the fraction of the labelled object it hides, the share of the badge lying
    on other listed objects, and its distance from the object. Badges never overlap. A large
    object keeps its badge at its centroid; a small one gets it beside it.
    """
    any_object = np.zeros((height, width), dtype=bool)
    for mask in masks:
        any_object |= mask
    vs, us = np.mgrid[0:height, 0:width]
    diagonal = math.hypot(width, height)
    placed = []
    for obj, mask in zip(objects, masks):
        own_pixels = max(int(mask.sum()), 1)
        best, best_cost = None, math.inf
        for x, y in candidate_spots(obj, r, width, height):
            if any(math.dist((x, y), other) < 2 * r + 2 for other in placed):
                continue
            y0, y1, x0, x1 = int(y - r), int(y + r) + 1, int(x - r), int(x + r) + 1
            disk = (us[y0:y1, x0:x1] - x) ** 2 + (vs[y0:y1, x0:x1] - y) ** 2 <= r * r
            own = (mask[y0:y1, x0:x1] & disk).sum()
            other = ((any_object[y0:y1, x0:x1] & ~mask[y0:y1, x0:x1]) & disk).sum()
            cost = (
                OWN_WEIGHT * own / own_pixels
                + OTHER_WEIGHT * other / max(int(disk.sum()), 1)
                + DISTANCE_WEIGHT * math.dist((x, y), obj["centroid"]) / diagonal
            )
            if cost < best_cost:
                best, best_cost = (x, y), cost
        placed.append(best if best is not None else tuple(obj["centroid"]))
    return placed


def mark_view(view, marks):
    """The view's image with a numbered badge on or beside each marked object it shows.

    A badge beside its object is tied to the object's centroid by a thin line.
    """
    image = Image.open(view["rgb"]).convert("RGBA")
    width, height = image.size
    r = badge_radius(width, height)
    font = ImageFont.load_default(size=round(1.3 * r))
    shown = sorted((o for o in view["objects"] if o["id"] in marks), key=lambda o: marks[o["id"]])
    masks = object_masks(view, shown, width, height)
    spots = place_badges(shown, masks, width, height, r)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for obj, (x, y) in zip(shown, spots):
        u, v = obj["centroid"]
        if math.dist((u, v), (x, y)) > r:
            draw.line([u, v, x, y], fill=TEXT, width=1)
            draw.ellipse([u - 2, v - 2, u + 2, v + 2], fill=BADGE_FILL, outline=TEXT)
    for obj, (x, y) in zip(shown, spots):
        text = str(marks[obj["id"]])
        half = max(r, (draw.textlength(text, font=font) + 4) / 2)
        draw.rounded_rectangle([x - half, y - r, x + half, y + r], radius=r, fill=BADGE_FILL, outline=TEXT, width=1)
        draw.text((x, y), text, fill=TEXT, font=font, anchor="mm")
    return Image.alpha_composite(image, overlay).convert("RGB")


def agent_scene(scene, episode, run_dir, state=None):
    """What `mg scene` prints: the whole scene graph, or with views only what they show.

    With views, each listed object gets its mark number, and marked copies of the views
    are written to run_dir/views for the agent to look at. Objects the person found by
    opening something, seen up close after a walk, or put down, are listed too (without a mark); so is what they hold.
    The views are the episode's start views plus those rendered after each walk (state["views"]);
    mark numbers are kept in state["marks"] so they don't change as views are added.
    """
    extra = {"start": episode["start"]}
    if "heading" in episode:
        extra["heading"] = episode["heading"]
    if state is not None:
        extra["position"] = [round(v, 2) for v in state["position"]]
        if state.get("held"):
            from .world import held_entries
            extra["holding"] = held_entries(episode, state)
    if not episode.get("views"):
        return {**scene.graph(), **extra}

    views = [load_view(REPO_ROOT / path) for path in episode["views"]]
    if state is not None:
        views += [load_view(view["dir"]) for view in state.get("views", [])]
    public = scene.public_ids()
    shown = {i for i in visible_ids(views) if i in public and scene.get(i).label != WALL}
    marks = assign_marks(shown, state.get("marks") if state is not None else None)
    if state is not None:
        state["marks"] = marks
    marks = {i: marks[i] for i in shown}
    found = set()
    if state is not None:
        found = (set(state.get("revealed", ())) | set(state.get("seen", ())) | set(state.get("placed", {}))) & public
    graph = scene.graph(visible=shown | found)
    for entry in graph["objects"]:
        if entry["id"] in marks:
            entry["mark"] = marks[entry["id"]]
    image_dir = Path(run_dir) / "views"
    image_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for view in views:
        path = image_dir / f"{view['name']}.png"
        if not path.exists():
            mark_view(view, marks).save(path)
        images.append({"view": view["name"], "path": str(path)})
    return {**graph, "images": images, **extra}


def render_after_walk(episode, run_dir, state):
    """Render what the person sees after the walk just made, if a render server is running.

    Returns the marked image's path, or None without a server or when rendering failed (the
    failure is kept in state["render_errors"]). The view faces the walk's end heading, with the
    world as world.py has it: open doors open, carried things gone, put-down things moved.
    """
    from . import thor_render, world

    port = thor_render.server_port(run_dir)
    if port is None or not state["legs"]:
        return None
    leg = state["legs"][-1]
    heading = leg["end_heading"] if leg.get("end_heading") is not None else episode.get("heading", 0.0)
    raw = world._raw_objects(episode)
    name = f"walk_{len(state.get('views', [])) + 1:02d}"
    payload = {
        "name": name, "position": list(state["position"]), "heading": heading,
        "opened": world.open_ids(episode, state),
        "removed": sorted(world.carried(state, raw)),
        "moved": {k: v["center"] for k, v in world.moved_objects(episode, state, raw).items()},
    }
    try:
        reply = thor_render.request(port, payload)
    except (OSError, ValueError) as error:
        reply = {"error": f"{type(error).__name__}: {error}"}
    if "error" in reply:
        state.setdefault("render_errors", []).append({"name": name, "error": reply["error"]})
        return None
    state.setdefault("views", []).append({
        "name": name, "dir": reply["view"], "leg": len(state["legs"]) - 1,
        "seconds": reply.get("seconds"), "warnings": reply.get("warnings", []),
    })
    agent_scene(world.scene_for(episode, state), episode, run_dir, state)
    return str(Path(run_dir) / "views" / f"{name}.png")
