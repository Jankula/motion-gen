"""The object: a closed rigid box, and how a person stands to take hold of it.

Conventions (see locomotion/path.py): floor coordinates are (x, z), a heading h faces
(sin h, cos h).  An object rotated by yaw about the vertical has its own z axis along heading
yaw and its own x axis along heading yaw + 90 deg.

A person facing the box along heading yaw + k * 90 deg (k = 0..3) holds it by the two faces on
their left and right.  The box stays fixed relative to the person while it is carried, so
k also fixes the heading needed to put it down in the target orientation.
"""
import math

import numpy as np

from locomotion.path import hdir
from locomotion.skeleton import FLOOR


class Box:
    def __init__(self, size, mass, start_xz, start_yaw, target_xz, target_yaw, label="box"):
        self.sx, self.h, self.sz = (float(v) for v in size)
        self.mass = float(mass)
        self.start_xz = np.asarray(start_xz, dtype=float)
        self.start_yaw = float(start_yaw)
        self.target_xz = np.asarray(target_xz, dtype=float)
        self.target_yaw = float(target_yaw)
        self.label = label

    @classmethod
    def from_task(cls, task):
        o = task["object"]
        tg = task["target"]
        return cls(o["size"], o.get("mass_kg", 10.0), o["start"]["center"],
                   math.radians(float(o["start"].get("yaw_deg", 0.0))),
                   tg["center"], math.radians(float(tg.get("yaw_deg", 0.0))), o.get("label", "box"))

    @property
    def y_floor(self):
        """Height of the centre of the box when it stands on the floor."""
        return FLOOR + 0.5 * self.h

    def extents(self, k):
        """(distance between the held faces, depth away from the person) for facing the box along
        heading yaw + k * 90 deg."""
        return (self.sx, self.sz) if k % 2 == 0 else (self.sz, self.sx)

    def stance_point(self, center, heading, depth, standoff):
        """Point on the floor to stand on (between the feet) to reach a box at center."""
        return np.asarray(center, dtype=float) - (0.5 * depth + standoff) * hdir(heading)
