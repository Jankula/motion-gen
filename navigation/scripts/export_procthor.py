"""Export ProcTHOR houses and their renders into scenes/procthor. Needs a GPU with Vulkan.

    python scripts/export_procthor.py scene train 0
    python scripts/export_procthor.py views episodes/procthor/p1_sofa.yaml

Rendering defaults to CloudRendering (headless Vulkan, e.g. a T4). On WSL, `--platform linux64`
renders through the X display instead, which WSLg passes on to the Windows GPU.

`scene` writes scenes/procthor/<split>_<index>/scene.yaml and a top view of the house,
with every door and drawer closed, for writing episodes against. `views` renders one
episode's views (a top view, and four ego views at its start), with the episode's
`opened` objects open, and prints the `views:` list to paste into the episode.
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

from motiongen import procthor
from motiongen.navigation import REPO_ROOT

# The simulator helpers are shared with the render server (src/motiongen/thor_render.py).
from motiongen import thor_render  # noqa: E402
from motiongen.thor_render import (  # noqa: E402
    EGO_HORIZON, EGO_TURNS, FIELD_OF_VIEW, close_all, color_lookup, is_door, load_house, objects_by_id,
    save_view, set_openness, start_controller, top_view,
)


def export_scene(split, index):
    house = load_house(split, index)
    name = f"{split}_{index}"
    out = REPO_ROOT / "scenes" / "procthor" / name
    controller = start_controller(house)
    close_all(controller)
    by_thor_id = objects_by_id(controller)

    doors = [o for o in by_thor_id.values() if is_door(o)]
    furniture = [
        o for o in by_thor_id.values()
        if not is_door(o) and not procthor.is_folded_part(o) and o["objectType"] not in procthor.STRUCTURE_TYPES
    ]
    if not doors:
        print("warning: no door objects in the metadata, so walls have no doorways; check door object types")
    ids = procthor.make_ids(furniture)
    door_ids = {o["objectId"]: f"door_{i + 1}" for i, o in enumerate(sorted(doors, key=lambda o: o["objectId"]))}
    ours = {**ids, **door_ids}

    rgb, segmentation, camera = top_view(controller)
    colors = color_lookup(controller)
    object_color = {thor_id: color for color, thor_id in colors.items()}

    objects = []
    door_boxes = []
    for obj in doors:
        center, size = procthor.box_from_aabb(obj["axisAlignedBoundingBox"])
        door_boxes.append((center, size))
        # A doorway is a place to go, not an obstacle: a flat box on the floor never blocks the body.
        objects.append({
            "id": door_ids[obj["objectId"]], "label": "door", "color": "saddlebrown",
            "center": [center[0], center[1], 0.0], "size": [size[0], size[1], 0.0],
            "thor_id": obj["objectId"],
        })

    for obj in furniture:
        center, size = procthor.box_from_aabb(obj["axisAlignedBoundingBox"])
        if min(size) <= 0:
            continue
        seg_color = object_color.get(obj["objectId"])
        average = procthor.mean_color(rgb, segmentation, seg_color) if seg_color else None
        entry = {
            "id": ids[obj["objectId"]], "label": procthor.split_label(obj["objectType"]),
            "color": procthor.nearest_color(average) if average else "gray",
            "center": list(center), "size": list(size), "thor_id": obj["objectId"],
        }
        # What the person can do with it, for the interaction tools.
        for flag in sorted(procthor.interaction_flags(obj, by_thor_id.values())):
            entry[flag] = True
        parent = procthor.direct_parent(obj, {k: v for k, v in by_thor_id.items() if k in ids})
        if parent is not None:
            entry["inside" if procthor.is_inside(obj, parent) else "supported_by"] = ids[parent["objectId"]]
        if obj.get("openable") and set_openness(controller, obj["objectId"], 1.0):
            opened = objects_by_id(controller)[obj["objectId"]]
            swept = procthor.union_box((center, size), procthor.box_from_aabb(opened["axisAlignedBoundingBox"]))
            entry["openable"] = True
            entry["open_box"] = {"center": list(swept[0]), "size": list(swept[1])}
            set_openness(controller, obj["objectId"], 0.0)
        objects.append(entry)

    add_footprints(objects, segmentation, colors, camera)
    walls = procthor.wall_boxes(house, door_boxes)
    rooms = procthor.room_polygons(house)
    xs = [x for r in rooms for x, _ in r["polygon"]]
    ys = [y for r in rooms for _, y in r["polygon"]]
    scene = {
        "name": f"procthor_{name}",
        "source": {"dataset": "procthor-10k", "split": split, "index": index},
        "room": {
            "x": [min(xs), max(xs)], "y": [min(ys), max(ys)],
            "height": max(w["size"][2] for w in walls) if walls else 2.6,
        },
        "rooms": rooms,
        "objects": walls + objects,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "scene.yaml").write_text(yaml.safe_dump(scene, sort_keys=False, default_flow_style=None, width=160))
    save_view(out / "views" / "top", "top", rgb, segmentation, colors, ours, camera)
    controller.stop()
    print(f"wrote {out.relative_to(REPO_ROOT)}: {len(objects)} objects, {len(walls)} wall pieces, {len(rooms)} rooms")


def add_footprints(objects, segmentation, colors, camera):
    """Give large, partly filled boxes (L-shaped counters) their floor plan from the top view.

    The mask is the object's pixels plus those of whatever rests on it or hangs above it,
    which hide it from the top camera.
    """
    packed = (segmentation[..., 0].astype(np.int64) << 16) | (segmentation[..., 1].astype(np.int64) << 8) | segmentation[..., 2]
    pixels_of = {}
    for color, thor_id in colors.items():
        pixels_of.setdefault(thor_id, []).append((color[0] << 16) | (color[1] << 8) | color[2])
    by_id = {o["id"]: o for o in objects}
    for obj in objects:
        center, size = obj["center"], obj["size"]
        if obj["label"] == "door" or size[0] * size[1] < procthor.FOOTPRINT_MIN_AREA:
            continue
        top = center[2] + size[2] / 2

        def overlaps(other):
            return all(
                abs(other["center"][k] - center[k]) < (other["size"][k] + size[k]) / 2 for k in (0, 1)
            )

        covering = [obj] + [
            other for other in by_id.values()
            if other is not obj and (
                other.get("supported_by") == obj["id"] or other.get("inside") == obj["id"]
                or (overlaps(other) and other["center"][2] - other["size"][2] / 2 >= top - 0.05)
            )
        ]
        values = [v for other in covering for v in pixels_of.get(other["thor_id"], [])]
        if not values:
            continue
        rects = procthor.footprint_rects(np.isin(packed, values), camera, center, size)
        if rects:
            obj["footprint"] = rects


def export_views(episode_path):
    episode = yaml.safe_load(Path(episode_path).read_text())
    scene_path = REPO_ROOT / episode["scene"]
    scene = yaml.safe_load(scene_path.read_text())
    ours = {o["thor_id"]: o["id"] for o in scene["objects"] if "thor_id" in o}
    thor_of = {v: k for k, v in ours.items()}
    controller = start_controller(load_house(scene["source"]["split"], scene["source"]["index"]))
    close_all(controller)
    for object_id in episode.get("opened", ()):
        if not set_openness(controller, thor_of[object_id], 1.0):
            raise SystemExit(f"could not open {object_id}")

    view_root = scene_path.parent / "views"
    names = []
    rgb, segmentation, camera = top_view(controller)
    name = f"{episode['id']}_top"
    save_view(view_root / name, name, rgb, segmentation, color_lookup(controller), ours, camera)
    names.append(name)

    x, y = episode["start"]
    agent_y = controller.last_event.metadata["agent"]["position"]["y"]
    for turn_name, turn in EGO_TURNS.items():
        yaw = procthor.heading_to_unity_yaw(episode.get("heading", 0.0) + turn)
        event = controller.step(
            action="Teleport", position={"x": x, "y": agent_y, "z": y},
            rotation={"x": 0, "y": yaw, "z": 0}, horizon=EGO_HORIZON, standing=True, forceAction=True,
        )
        if not event.metadata["lastActionSuccess"]:
            raise SystemExit(f"teleport to the start failed: {event.metadata['errorMessage']}")
        camera = {"position": [x, y], "heading": episode.get("heading", 0.0) + turn,
                  "horizon": EGO_HORIZON, "field_of_view": FIELD_OF_VIEW}
        name = f"{episode['id']}_ego_{turn_name}"
        save_view(view_root / name, name, event.frame, event.instance_segmentation_frame,
                  color_lookup(controller), ours, camera)
        names.append(name)
    controller.stop()

    print("views:")
    for name in names:
        print(f"  - {(view_root / name).relative_to(REPO_ROOT)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["cloud", "linux64"], default="cloud")
    commands = parser.add_subparsers(dest="command", required=True)
    scene_parser = commands.add_parser("scene", help="export a house as a scene and a top view")
    scene_parser.add_argument("split", choices=["train", "val", "test"])
    scene_parser.add_argument("index", type=int)
    views_parser = commands.add_parser("views", help="render an episode's views")
    views_parser.add_argument("episode")
    args = parser.parse_args()
    thor_render.PLATFORM = args.platform
    if args.command == "scene":
        export_scene(args.split, args.index)
    else:
        export_views(args.episode)


if __name__ == "__main__":
    main()
