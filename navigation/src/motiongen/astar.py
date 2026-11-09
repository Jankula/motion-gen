"""Baseline A* planner over the grid of collision-free body positions."""

import heapq
import math

import numpy as np

from .scene import RESOLUTION
from .smooth import DESIRED_MARGIN, smooth_path

LINE_OF_SIGHT_HEIGHT = 1.5
CLEARANCE_WEIGHT = 3.0
NEIGHBORS = [
    (dx, dy, math.hypot(dx, dy))
    for dx in (-1, 0, 1)
    for dy in (-1, 0, 1)
    if dx or dy
]


def goal_mask(scene, target, min_dist, max_dist, ignore=()):
    """Cells in the [min_dist, max_dist] band of the target, with nothing tall in between.

    The line-of-sight test stops a target counting as reached from behind a wall. The sight
    line runs to the nearest point of the target's footprint and on to its centre: a box can
    poke through a wall (a toilet's bounding box into the next room), and then only the second
    part crosses the wall. Objects in ignore (the fridge an egg is in) don't block the view.
    """
    gx, gy = np.meshgrid(scene.xs, scene.ys, indexing="ij")
    distance = np.full(gx.shape, np.inf)
    nearest_x = np.zeros(gx.shape)
    nearest_y = np.zeros(gx.shape)
    for x0, y0, x1, y1 in target.rects:
        rx, ry = np.clip(gx, x0, x1), np.clip(gy, y0, y1)
        d = np.hypot(gx - rx, gy - ry)
        closer = d < distance
        distance[closer] = d[closer]
        nearest_x[closer] = rx[closer]
        nearest_y[closer] = ry[closer]
    mask = (distance >= min_dist) & (distance <= max_dist)

    # From the boxes, not scene.owner, where a later object can overwrite a wall's cells.
    tall = np.zeros_like(mask)
    walls = np.zeros_like(mask)
    skip = {target.id, *ignore}
    for obj in scene.objects:
        if obj.id in skip or not obj.blocks_body(scene.body_height) or obj.z_range[1] < LINE_OF_SIGHT_HEIGHT:
            continue
        footprint = obj.covers(gx, gy)
        tall |= footprint
        if obj.label == "wall":
            walls |= footprint
    cells = np.argwhere(mask)
    if len(cells) == 0:
        return mask
    x = scene.xs[cells[:, 0]]
    y = scene.ys[cells[:, 1]]
    nearest_x = nearest_x[cells[:, 0], cells[:, 1]]
    nearest_y = nearest_y[cells[:, 0], cells[:, 1]]
    center_x = sum(target.x_range) / 2
    center_y = sum(target.y_range) / 2

    def crosses(occupied, x0, y0, x1, y1):
        length = float(np.max(np.hypot(x1 - x0, y1 - y0)))
        t = np.linspace(0.0, 1.0, int(np.ceil(length / RESOLUTION)) + 2)[:, None]
        ix = np.clip(np.rint((x0 + t * (x1 - x0) - scene.xs[0]) / RESOLUTION).astype(int), 0, len(scene.xs) - 1)
        iy = np.clip(np.rint((y0 + t * (y1 - y0) - scene.ys[0]) / RESOLUTION).astype(int), 0, len(scene.ys) - 1)
        return occupied[ix, iy].any(axis=0)

    blocked = crosses(tall, x, y, nearest_x, nearest_y) | crosses(walls, nearest_x, nearest_y, center_x, center_y)
    mask[cells[blocked, 0], cells[blocked, 1]] = False
    return mask


def point_goal_mask(scene, x, y, radius=0.1):
    gx, gy = np.meshgrid(scene.xs, scene.ys, indexing="ij")
    return np.hypot(gx - x, gy - y) <= radius


def plan(scene, start, goal):
    """Shortest collision-free path from start to any goal-mask cell, or None if unreachable."""
    free = scene.clearance >= scene.body_radius
    goal = goal & free
    if not goal.any():
        return None
    goal_cells = np.argwhere(goal)
    # Distance to the goal cells' bounding rectangle is an admissible heuristic.
    gx0, gy0 = goal_cells.min(axis=0)
    gx1, gy1 = goal_cells.max(axis=0)

    def heuristic(cell):
        dx = max(gx0 - cell[0], 0, cell[0] - gx1)
        dy = max(gy0 - cell[1], 0, cell[1] - gy1)
        return math.hypot(dx, dy)

    start_cell = scene.cell(*start)
    if not free[start_cell]:
        return None
    # Soft cost for passing close to obstacles, which leaves room to round corners.
    # Narrow gaps stay passable. Costs only rise, so the heuristic stays admissible.
    desired = scene.body_radius + DESIRED_MARGIN
    penalty = (np.clip(desired - scene.clearance, 0.0, None) / DESIRED_MARGIN).tolist()
    best = {start_cell: 0.0}
    parent = {}
    queue = [(heuristic(start_cell), start_cell)]
    while queue:
        _, cell = heapq.heappop(queue)
        if goal[cell]:
            cells = [cell]
            while cells[-1] in parent:
                cells.append(parent[cells[-1]])
            points = [[float(start[0]), float(start[1])]]
            points += [[float(scene.xs[i]), float(scene.ys[j])] for i, j in reversed(cells[:-1])]
            return smooth_path(scene, points)
        for dx, dy, step in NEIGHBORS:
            nxt = (cell[0] + dx, cell[1] + dy)
            if not (0 <= nxt[0] < free.shape[0] and 0 <= nxt[1] < free.shape[1]):
                continue
            if not free[nxt]:
                continue
            cost = best[cell] + step * (1.0 + CLEARANCE_WEIGHT * penalty[nxt[0]][nxt[1]])
            if cost < best.get(nxt, math.inf):
                best[nxt] = cost
                parent[nxt] = cell
                heapq.heappush(queue, (cost + heuristic(nxt), nxt))
    return None
