"""Turn a ProcTHOR house and AI2-THOR metadata into this project's scene format.

Nothing here imports ai2thor, so it runs and is tested without a GPU.
scripts/export_procthor.py drives the simulator and calls these.

Unity is y-up and left-handed; scenes here are z-up and right-handed. Mapping
Unity (x, y, z) to (x, z, y) converts both, and a top view looks the same in either.
"""

import re
from collections import defaultdict

import numpy as np
from PIL import ImageColor

WALL_THICKNESS = 0.1
# Unity types that are part of the building, not furniture.
STRUCTURE_TYPES = {"Floor", "Wall", "Ceiling", "Window"}
DOOR_TYPES = {"Door", "Doorway", "Doorframe"}
# Appliances AI2-THOR can't switch on that a person can still run.
USABLE_TYPES = {"WashingMachine", "ClothesDryer"}
INTERACTION_FLAGS = ("pickupable", "receptacle", "toggleable")
CSS_COLORS = {name: ImageColor.getrgb(name) for name in ImageColor.colormap}


def to_ours(point):
    """A Unity {x, y, z} dict as an (x, y, z) tuple in the z-up frame."""
    return (point["x"], point["z"], point["y"])


def heading_to_unity_yaw(heading):
    """Our yaw (degrees counter-clockwise from +x) as Unity's y rotation (clockwise from +z)."""
    return (90.0 - heading) % 360.0


def box_from_aabb(aabb):
    """center and size tuples from an AI2-THOR axisAlignedBoundingBox."""
    center = to_ours(aabb["center"])
    sx, sy, sz = to_ours(aabb["size"])
    return tuple(round(v, 3) for v in center), tuple(round(abs(v), 3) for v in (sx, sy, sz))


def union_box(a, b):
    """The smallest box holding two (center, size) boxes."""
    lo = np.minimum(np.subtract(a[0], np.divide(a[1], 2)), np.subtract(b[0], np.divide(b[1], 2)))
    hi = np.maximum(np.add(a[0], np.divide(a[1], 2)), np.add(b[0], np.divide(b[1], 2)))
    return tuple(round(float(v), 3) for v in (lo + hi) / 2), tuple(round(float(v), 3) for v in hi - lo)


def split_label(object_type):
    """"CoffeeTable" -> "coffee table", "TVStand" -> "tv stand"."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", object_type)
    return spaced.lower()


def make_ids(objects):
    """Readable ids ("mug_1") for AI2-THOR objects, numbered per label in objectId order."""
    counts = defaultdict(int)
    ids = {}
    for obj in sorted(objects, key=lambda o: o["objectId"]):
        label = split_label(obj["objectType"]).replace(" ", "_")
        counts[label] += 1
        ids[obj["objectId"]] = f"{label}_{counts[label]}"
    return ids


def room_polygons(house):
    """Room floor polygons, with ids numbered per room type ("bedroom_2")."""
    counts = defaultdict(int)
    rooms = []
    for room in house["rooms"]:
        room_type = split_label(room["roomType"]).replace(" ", "_")
        counts[room_type] += 1
        rooms.append({
            "id": f"{room_type}_{counts[room_type]}",
            "type": room_type,
            "polygon": [[round(p["x"], 3), round(p["z"], 3)] for p in room["floorPolygon"]],
        })
    return rooms


def _wall_segments(house):
    """Each wall as (x0, y0, x1, y1, height), once even where two rooms share it.

    ProcTHOR marks an open-plan connection between two rooms with "empty": true; there is
    no wall there, so a segment any room lists as empty is left out.
    """
    segments, empty = {}, set()
    for wall in house["walls"]:
        ends = tuple(sorted({(round(p["x"], 3), round(p["z"], 3)) for p in wall["polygon"]}))
        if len(ends) != 2:
            continue
        if wall.get("empty"):
            empty.add(ends)
        height = max(p["y"] for p in wall["polygon"])
        segments[ends] = (*ends[0], *ends[1], height)
    return [segment for ends, segment in segments.items() if ends not in empty]


def _cut(start, end, gaps):
    """The parts of [start, end] outside every (lo, hi) gap."""
    pieces = [(start, end)]
    for lo, hi in gaps:
        pieces = [
            part
            for a, b in pieces
            for part in ((a, min(b, lo)), (max(a, hi), b))
            if part[1] - part[0] > 1e-3
        ]
    return pieces


def wall_boxes(house, doors):
    """Walls as thin boxes, cut open wherever a door's (center, size) footprint crosses them.

    Walls are axis-aligned in ProcTHOR; any that aren't are skipped.
    """
    boxes = []
    for x0, y0, x1, y1, height in _wall_segments(house):
        if abs(y0 - y1) < 1e-3:
            along, across, start, end = 0, y0, min(x0, x1), max(x0, x1)
        elif abs(x0 - x1) < 1e-3:
            along, across, start, end = 1, x0, min(y0, y1), max(y0, y1)
        else:
            continue
        gaps = [
            (c[along] - s[along] / 2, c[along] + s[along] / 2)
            for c, s in doors
            if abs(c[1 - along] - across) <= s[1 - along] / 2 + WALL_THICKNESS
        ]
        for a, b in _cut(start, end, gaps):
            mid = (a + b) / 2
            center = (mid, across) if along == 0 else (across, mid)
            size = (b - a, WALL_THICKNESS) if along == 0 else (WALL_THICKNESS, b - a)
            boxes.append({
                "label": "wall", "color": "dimgray",
                "center": [round(center[0], 3), round(center[1], 3), round(height / 2, 3)],
                "size": [round(size[0], 3), round(size[1], 3), round(height, 3)],
            })
    for index, box in enumerate(boxes):
        box["id"] = f"wall_{index + 1}"
    return boxes


def whole_object_id(thor_id):
    """The object a part belongs to ("TVStand|7|0|0___0" -> "TVStand|7|0|0")."""
    return thor_id.split("___")[0]


def is_folded_part(obj):
    """Whether obj is a part to fold into the object it belongs to.

    AI2-THOR lists some objects' parts as objects of their own, sometimes with another type:
    a TV stand's shelves are "TVStand|7|0|0___0" with type DiningTable, and a shelving unit
    lists each shelf. Those are folded into the whole object. Openable parts (a dresser's
    drawers) stay separate, since things are stored inside them.
    """
    return whole_object_id(obj["objectId"]) != obj["objectId"] and not obj.get("openable")


def interaction_flags(obj, objects):
    """Which of pickupable, receptacle and toggleable apply to obj.

    A folded part's receptacle flag passes to its object: a sink holds things in its basin,
    a shelving unit on its shelves.
    """
    flags = {flag for flag in INTERACTION_FLAGS if obj.get(flag)}
    if obj["objectType"] in USABLE_TYPES:
        flags.add("toggleable")
    for other in objects:
        if is_folded_part(other) and whole_object_id(other["objectId"]) == obj["objectId"] and other.get("receptacle"):
            flags.add("receptacle")
    return flags


def is_inside(obj, parent):
    """Whether obj is inside its parent receptacle rather than resting on top of it.

    Inside means an openable parent (a fridge, a drawer) with obj below its top: a cloth
    lying on a toilet's lid is on it, an egg on a fridge shelf is in it.
    """
    if not parent.get("openable"):
        return False
    obj_bottom = obj["axisAlignedBoundingBox"]["center"]["y"] - obj["axisAlignedBoundingBox"]["size"]["y"] / 2
    parent_top = parent["axisAlignedBoundingBox"]["center"]["y"] + parent["axisAlignedBoundingBox"]["size"]["y"] / 2
    return obj_bottom < parent_top - 0.05


def direct_parent(obj, by_thor_id):
    """The smallest receptacle obj is in or on, among the objects being exported.

    A receptacle that isn't exported (a folded part) counts as the object it belongs to.
    AI2-THOR sometimes lists a smaller object as a big one's receptacle (a counter "on" a mug,
    a table "on" a chair); a receptacle with a smaller footprint than obj is ignored.
    """
    def footprint(o):
        x, y, _ = to_ours(o["axisAlignedBoundingBox"]["size"])
        return x * y

    receptacles = {p if p in by_thor_id else whole_object_id(p) for p in obj.get("parentReceptacles") or ()}
    parents = [
        by_thor_id[p] for p in sorted(receptacles)
        if p in by_thor_id and footprint(by_thor_id[p]) >= footprint(obj)
    ]
    if not parents:
        return None
    return min(parents, key=lambda p: np.prod(to_ours(p["axisAlignedBoundingBox"]["size"])))


def nearest_color(rgb):
    """The CSS colour name closest to an (r, g, b) triple."""
    return min(CSS_COLORS, key=lambda name: sum((a - b) ** 2 for a, b in zip(CSS_COLORS[name], rgb)))


def view_objects(segmentation, color_to_thor_id, ours):
    """Per-object pixel statistics and an id image from an instance-segmentation frame.

    ours maps AI2-THOR objectIds to scene ids; other colours (walls, floor) are ignored.
    The id image stores index + 1 of each object in the returned list as red + 256 * green.
    """
    packed = (segmentation[..., 0].astype(np.int64) << 16) | (segmentation[..., 1].astype(np.int64) << 8) | segmentation[..., 2]
    ids_image = np.zeros(segmentation.shape, dtype=np.uint8)
    masks = {}
    for value in np.unique(packed):
        color = (int(value >> 16), int(value >> 8 & 255), int(value & 255))
        thor_id = color_to_thor_id.get(color)
        if thor_id not in ours:
            continue
        # Several colours can belong to one scene object (its parts).
        mask = packed == value
        masks[ours[thor_id]] = masks[ours[thor_id]] | mask if ours[thor_id] in masks else mask
    objects = []
    for object_id, mask in masks.items():
        vs, us = np.nonzero(mask)
        objects.append({
            "id": object_id,
            "pixels": int(mask.sum()),
            "bbox": [int(us.min()), int(vs.min()), int(us.max()), int(vs.max())],
            "centroid": [round(float(us.mean()), 1), round(float(vs.mean()), 1)],
        })
        index = len(objects)
        ids_image[mask, 0] = index & 255
        ids_image[mask, 1] = index >> 8
    return objects, ids_image


def mean_color(rgb, segmentation, color):
    """Mean RGB of rgb's pixels where segmentation has the given colour, or None."""
    mask = np.all(segmentation == np.array(color, dtype=segmentation.dtype), axis=-1)
    if not mask.any():
        return None
    return tuple(int(v) for v in rgb[mask].mean(axis=0))


# Objects whose box covers at least this much floor are checked against the top view.
FOOTPRINT_MIN_AREA = 0.5
# ... and get a footprint when the top view shows them filling less than this share of it.
FOOTPRINT_MAX_FILL = 0.8
FOOTPRINT_CELL = 0.05


def top_pixel_to_world(camera, width, height):
    """Functions from top-view pixel (u, v) to world (x, y) and back, for the orthographic camera."""
    half = camera["orthographicSize"]
    per_metre = height / (2 * half)
    cx, cy = camera["position"]["x"], camera["position"]["z"]

    def to_world(u, v):
        return cx + (np.asarray(u) + 0.5 - width / 2) / per_metre, cy + (height / 2 - np.asarray(v) - 0.5) / per_metre

    def to_pixel(x, y):
        return (np.asarray(x) - cx) * per_metre + width / 2 - 0.5, height / 2 - (np.asarray(y) - cy) * per_metre - 0.5

    return to_world, to_pixel


def footprint_rects(mask, camera, center, size, cell=FOOTPRINT_CELL):
    """The rectangles (x0, y0, x1, y1) of a box's floor plan that a top-view mask covers.

    mask marks the object's pixels (and whatever rests on it, which hides it from above).
    Returns None when the object fills most of its box anyway.
    """
    height, width = mask.shape
    to_world, to_pixel = top_pixel_to_world(camera, width, height)
    x0, y0 = center[0] - size[0] / 2, center[1] - size[1] / 2
    nx, ny = max(1, int(np.ceil(size[0] / cell))), max(1, int(np.ceil(size[1] / cell)))
    filled = np.zeros((nx, ny), dtype=bool)
    for i in range(nx):
        for j in range(ny):
            # Sample a 3x3 grid of points in the cell.
            xs = x0 + (i + np.array([0.2, 0.5, 0.8])) * cell
            ys = y0 + (j + np.array([0.2, 0.5, 0.8])) * cell
            gx, gy = np.meshgrid(xs, ys)
            u, v = to_pixel(gx, gy)
            u = np.clip(np.rint(u).astype(int), 0, width - 1)
            v = np.clip(np.rint(v).astype(int), 0, height - 1)
            filled[i, j] = mask[v, u].mean() >= 0.3
    # Close one-cell seams (legs, gaps between parts).
    from scipy import ndimage

    filled = ndimage.binary_closing(filled, iterations=1, border_value=0) | filled
    if not filled.any() or filled.mean() >= FOOTPRINT_MAX_FILL:
        return None
    # Runs along x per row of cells, merged with identical runs in the rows above.
    rects, open_runs = [], {}
    for j in range(ny + 1):
        runs = set()
        if j < ny:
            i = 0
            while i < nx:
                if filled[i, j]:
                    start = i
                    while i < nx and filled[i, j]:
                        i += 1
                    runs.add((start, i))
                else:
                    i += 1
        for run in list(open_runs):
            if run not in runs:
                rects.append((run, open_runs.pop(run), j))
        for run in runs:
            open_runs.setdefault(run, j)
    return [
        [round(x0 + a * cell, 3), round(y0 + j0 * cell, 3), round(x0 + b * cell, 3), round(y0 + j1 * cell, 3)]
        for (a, b), j0, j1 in sorted(rects, key=lambda r: (r[1], r[0]))
    ]
