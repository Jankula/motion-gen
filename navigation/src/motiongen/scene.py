"""Scene loading, occupancy grid, clearance field and scene-graph export."""

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import yaml
from scipy import ndimage

BODY_RADIUS = 0.25
BODY_HEIGHT = 1.7
RESOLUTION = 0.02
WALL = "wall"


@dataclass(frozen=True)
class Box:
    id: str
    label: str
    color: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    # Present in the world but missing from the scene graph, like a stale map.
    hidden: bool = False
    # What it rests on or is stored in, when the source data says so.
    support: str | None = None
    inside: str | None = None
    # Openable parts carry the box they fill when fully open: ((cx, cy, cz), (sx, sy, sz)).
    openable: bool = False
    open_box: tuple | None = None
    is_open: bool = False
    # What a person can do with it: pick it up, put things on or in it, switch it on.
    pickupable: bool = False
    receptacle: bool = False
    toggleable: bool = False
    # Where the box is only partly filled (an L-shaped counter), the rectangles
    # (x0, y0, x1, y1) it actually covers on the floor plan.
    footprint: tuple | None = None

    @property
    def z_range(self):
        return self.center[2] - self.size[2] / 2, self.center[2] + self.size[2] / 2

    @property
    def x_range(self):
        return self.center[0] - self.size[0] / 2, self.center[0] + self.size[0] / 2

    @property
    def y_range(self):
        return self.center[1] - self.size[1] / 2, self.center[1] + self.size[1] / 2

    @property
    def rects(self):
        """The floor-plan rectangles (x0, y0, x1, y1) the object covers."""
        if self.footprint:
            return self.footprint
        return ((self.x_range[0], self.y_range[0], self.x_range[1], self.y_range[1]),)

    def covers(self, gx, gy):
        """Mask of the grid points (arrays gx, gy) inside the object's footprint."""
        mask = np.zeros(np.shape(gx), dtype=bool)
        for x0, y0, x1, y1 in self.rects:
            mask |= (gx >= x0) & (gx <= x1) & (gy >= y0) & (gy <= y1)
        return mask

    def footprint_distance(self, x, y):
        return float(min(
            np.hypot(max(x0 - x, 0.0, x - x1), max(y0 - y, 0.0, y - y1)) for x0, y0, x1, y1 in self.rects
        ))

    def blocks_body(self, body_height=BODY_HEIGHT):
        return self.z_range[0] < body_height and self.z_range[1] > 0.0

    def opened(self):
        """This object with its open footprint, which includes the swept door or drawer."""
        center, size = self.open_box
        return replace(self, center=tuple(center), size=tuple(size), is_open=True, footprint=None)


def _box(data, hidden=False):
    open_box = data.get("open_box")
    return Box(
        data["id"], data["label"], data.get("color", "gray"),
        tuple(data["center"]), tuple(data["size"]), hidden=hidden,
        support=data.get("supported_by"), inside=data.get("inside"),
        openable=data.get("openable", False),
        open_box=(tuple(open_box["center"]), tuple(open_box["size"])) if open_box else None,
        pickupable=data.get("pickupable", False),
        receptacle=data.get("receptacle", False),
        toggleable=data.get("toggleable", False),
        footprint=tuple(tuple(r) for r in data["footprint"]) if data.get("footprint") else None,
    )


def points_in_polygon(x, y, polygon):
    """Even-odd test of points (arrays or scalars) against a polygon of [x, y] vertices."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    inside = np.zeros(np.broadcast(x, y).shape, dtype=bool)
    vertices = np.asarray(polygon, dtype=float)
    for (x0, y0), (x1, y1) in zip(vertices, np.roll(vertices, -1, axis=0)):
        if y0 == y1:
            continue
        crosses = (y0 > y) != (y1 > y)
        x_at = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
        inside ^= crosses & (x < x_at)
    return inside


class Scene:
    """Boxes in a rectangular room, rasterized for body-collision queries.

    Grid cells are indexed [ix, iy], with one ring of wall cells outside the room.
    With room polygons, everything outside them counts as wall too.
    """

    def __init__(
        self, name, room_x, room_y, room_height, objects, rooms=(),
        body_radius=BODY_RADIUS, body_height=BODY_HEIGHT,
    ):
        self.name = name
        self.room_x = tuple(room_x)
        self.room_y = tuple(room_y)
        self.room_height = room_height
        self.objects = list(objects)
        self.rooms = list(rooms)
        self.body_radius = body_radius
        self.body_height = body_height
        self.owners = [WALL] + [o.id for o in self.objects]
        self._build_grid()

    @classmethod
    def load(cls, path, hidden=(), opened=(), body=None, moved=None, removed=()):
        """A scene from YAML, with some objects opened, moved or taken away.

        moved maps an id to {"center": [x, y, z], "support": id | None, "inside": id | None};
        removed objects (being carried) are left out.
        """
        data = yaml.safe_load(Path(path).read_text())
        objects = [_box(o) for o in data["objects"] if o["id"] not in set(removed)]
        unknown = set(opened) - {o.id for o in objects if o.openable}
        if unknown:
            raise ValueError(f"cannot open {sorted(unknown)}: not openable objects in this scene")
        objects = [o.opened() if o.id in opened else o for o in objects]
        for index, obj in enumerate(objects):
            if moved and obj.id in moved:
                where = moved[obj.id]
                objects[index] = replace(
                    obj, center=tuple(where["center"]), support=where.get("support"), inside=where.get("inside"),
                    footprint=None,
                )
        objects += [_box(o, hidden=True) for o in hidden]
        room = data["room"]
        body = body or {}
        return cls(
            data["name"], room["x"], room["y"], room["height"], objects,
            rooms=data.get("rooms", ()),
            body_radius=body.get("radius", BODY_RADIUS),
            body_height=body.get("height", BODY_HEIGHT),
        )

    def _build_grid(self):
        nx = round((self.room_x[1] - self.room_x[0]) / RESOLUTION) + 2
        ny = round((self.room_y[1] - self.room_y[0]) / RESOLUTION) + 2
        xs = self.room_x[0] + (np.arange(nx) - 0.5) * RESOLUTION
        ys = self.room_y[0] + (np.arange(ny) - 0.5) * RESOLUTION
        self.xs, self.ys = xs, ys

        # Owner index per cell: -1 is free, 0 is wall, i + 1 is objects[i].
        owner = np.full((nx, ny), -1, dtype=np.int32)
        owner[[0, -1], :] = 0
        owner[:, [0, -1]] = 0
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        if self.rooms:
            floor = np.zeros((nx, ny), dtype=bool)
            for room in self.rooms:
                floor |= points_in_polygon(gx, gy, room["polygon"])
            owner[~floor] = 0
        for i, obj in enumerate(self.objects):
            if not obj.blocks_body(self.body_height):
                continue
            owner[obj.covers(gx, gy)] = i + 1
        self.owner = owner

        # Subtracting half a cell keeps distances to obstacle edges conservative.
        distance, nearest = ndimage.distance_transform_edt(
            owner == -1, sampling=RESOLUTION, return_indices=True
        )
        self.clearance = np.maximum(distance - RESOLUTION / 2, 0.0)
        self.nearest_owner = owner[nearest[0], nearest[1]]

    def cell(self, x, y):
        ix = int(np.clip(round((x - self.xs[0]) / RESOLUTION), 0, len(self.xs) - 1))
        iy = int(np.clip(round((y - self.ys[0]) / RESOLUTION), 0, len(self.ys) - 1))
        return ix, iy

    def in_room(self, x, y):
        return (
            self.room_x[0] <= x <= self.room_x[1]
            and self.room_y[0] <= y <= self.room_y[1]
        )

    def room_of(self, x, y):
        """The id of the room polygon containing (x, y), or None."""
        return next((r["id"] for r in self.rooms if points_in_polygon(x, y, r["polygon"])), None)

    def clearance_at(self, x, y):
        """Distance from (x, y) to the nearest obstacle; 0 inside one or outside the room."""
        if not self.in_room(x, y):
            return 0.0
        return float(self.clearance[self.cell(x, y)])

    def nearest_obstacle(self, x, y):
        if not self.in_room(x, y):
            return WALL
        owner = self.nearest_owner[self.cell(x, y)]
        return self.owners[owner]

    def get(self, object_id):
        return next(o for o in self.objects if o.id == object_id)

    def stored_away(self, obj):
        """True for objects inside a closed container, which can't be seen or reached.

        Only openable containers close; what's in a bowl or a toaster stays in view.
        """
        if obj.inside is None:
            return False
        container = self.get(obj.inside)
        return container.openable and not container.is_open

    def public_ids(self):
        return {o.id for o in self.objects if not o.hidden and not self.stored_away(o)}

    def supported_by(self, obj):
        """The object directly beneath obj, if obj rests on one."""
        if obj.support is not None:
            return obj.support
        for other in self.objects:
            if (
                other is not obj
                and abs(other.z_range[1] - obj.z_range[0]) < 0.01
                and other.x_range[0] <= obj.center[0] <= other.x_range[1]
                and other.y_range[0] <= obj.center[1] <= other.y_range[1]
            ):
                return other.id
        return None

    def _object_entry(self, obj):
        entry = {
            "id": obj.id,
            "label": obj.label,
            "color": obj.color,
            "center": obj.center,
            "size": obj.size,
            "blocks_body": obj.blocks_body(self.body_height),
            "supported_by": self.supported_by(obj),
        }
        # Optional fields appear only where they apply, so plain box scenes print as before.
        if self.rooms:
            entry["room"] = self.room_of(obj.center[0], obj.center[1])
        if obj.inside is not None:
            entry["inside"] = obj.inside
        if obj.openable:
            entry["openable"] = True
            entry["is_open"] = obj.is_open
        if obj.footprint:
            entry["footprint"] = [[round(v, 2) for v in r] for r in obj.footprint]
        return entry

    def graph(self, visible=None):
        """The scene as the agent sees it; visible, if given, limits which objects are listed."""
        graph = {
            "room": {"x": self.room_x, "y": self.room_y, "height": self.room_height},
            "body": {"shape": "cylinder", "radius": self.body_radius, "height": self.body_height},
        }
        if self.rooms:
            graph["rooms"] = self.rooms
        public = self.public_ids()
        graph["objects"] = [
            self._object_entry(o)
            for o in self.objects
            if o.id in public and (visible is None or o.id in visible)
        ]
        return graph
