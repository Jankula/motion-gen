"""Sweep the body cylinder along a polyline and report collisions and clearance."""

import numpy as np

from .scene import RESOLUTION


def sample_path(points):
    """Points along the polyline, no more than one grid cell apart."""
    points = np.asarray(points, dtype=float)
    samples = [points[:1]]
    for a, b in zip(points[:-1], points[1:]):
        steps = max(int(np.ceil(np.linalg.norm(b - a) / RESOLUTION)), 1)
        t = np.arange(1, steps + 1)[:, None] / steps
        samples.append(a + t * (b - a))
    return np.concatenate(samples)


def path_length(points):
    points = np.asarray(points, dtype=float)
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def check_path(scene, points):
    """Check a path of [x, y] points, including its first point.

    min_clearance is measured from the body surface, so it is negative on collision.
    """
    first_collision = None
    min_clearance = np.inf
    for x, y in sample_path(points):
        clearance = scene.clearance_at(x, y) - scene.body_radius
        min_clearance = min(min_clearance, clearance)
        if clearance < 0 and first_collision is None:
            first_collision = {
                "x": round(float(x), 3),
                "y": round(float(y), 3),
                "object": scene.nearest_obstacle(x, y),
            }
    return {
        "collision_free": first_collision is None,
        "first_collision": first_collision,
        "min_clearance": round(float(min_clearance), 3),
        "length": round(path_length(points), 3),
    }
