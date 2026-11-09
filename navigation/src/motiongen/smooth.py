"""Round off grid-planned routes with an elastic band, keeping them collision-free."""

import numpy as np

from .path_check import check_path
from .scene import RESOLUTION

SAMPLE_STRIDE = 5
ITERATIONS = 800
TENSION = 0.5
REPULSION = 0.01
# Clearance beyond the body radius that routes try to keep.
DESIRED_MARGIN = 0.2


def smooth_path(scene, points):
    """Relax interior points under tension and obstacle repulsion, with endpoints fixed.

    Tension straightens the route; repulsion pushes it out of the desired clearance
    margin. A point never moves to where the body would touch an obstacle.
    Returns the input unchanged if the result somehow fails the collision check.
    """
    if len(points) < 3:
        return points
    indices = list(range(0, len(points) - 1, SAMPLE_STRIDE)) + [len(points) - 1]
    path = np.asarray([points[i] for i in indices], dtype=float)
    if len(path) < 3:
        return points

    radius = scene.body_radius
    desired = radius + DESIRED_MARGIN
    grad_x, grad_y = np.gradient(scene.clearance, RESOLUTION)

    def cells(xy):
        ix = np.clip(np.rint((xy[:, 0] - scene.xs[0]) / RESOLUTION).astype(int), 0, len(scene.xs) - 1)
        iy = np.clip(np.rint((xy[:, 1] - scene.ys[0]) / RESOLUTION).astype(int), 0, len(scene.ys) - 1)
        return ix, iy

    floor = radius + RESOLUTION
    for _ in range(ITERATIONS):
        current = path[1:-1]
        ix, iy = cells(current)
        margin = np.clip(desired - scene.clearance[ix, iy], 0.0, None)
        push = np.stack([grad_x[ix, iy], grad_y[ix, iy]], axis=1)
        strength = REPULSION * margin / DESIRED_MARGIN
        candidate = current + TENSION * ((path[:-2] + path[2:]) / 2 - current) + strength[:, None] * push
        accepted = scene.clearance[cells(candidate)] >= floor
        path[1:-1][accepted] = candidate[accepted]

    result = path.tolist()
    return result if check_path(scene, result)["collision_free"] else points
