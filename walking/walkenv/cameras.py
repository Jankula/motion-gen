"""Camera placement for the four fixed viewpoints.

Views are defined relative to the direction the body faces (not the direction it moves), so
"front" always shows the face even if a motion drifts sideways or walks backwards.
"""
from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation

UP = np.array([0.0, 1.0, 0.0])
VIEWS = ("front", "back", "left", "right")  # left/right = the subject's own left/right side


@dataclass
class CameraConfig:
    mode: str = "track"  # "track": follow the walker; "fixed": static camera that sees the whole path
    distance: float = 4.5  # m, camera to subject (track mode, and minimum for fixed mode)
    height: float = 1.1  # m above the floor
    look_height: float = 0.9  # m above the floor, the point the camera aims at
    fov: float = 30.0  # vertical field of view, degrees
    smooth_seconds: float = 1.0  # track mode: window that removes step-to-step sway from the camera path


def facing_direction(global_orient):
    """Average horizontal facing direction (unit vector in XZ) over the clip."""
    forward = Rotation.from_rotvec(global_orient).apply([0.0, 0.0, 1.0])  # rest pose faces +Z
    forward[:, 1] = 0.0
    mean = forward.mean(axis=0)
    norm = np.linalg.norm(mean)
    return mean / norm if norm > 1e-6 else np.array([0.0, 0.0, 1.0])


def view_direction(view, facing):
    """Unit vector from the subject towards the camera."""
    left = np.cross(UP, facing)  # rest pose: facing +Z, left is +X
    return {"front": facing, "back": -facing, "left": left, "right": -left}[view]


def camera_path(view, pelvis, facing, floor_y, fps, cfg, aspect):
    """Per-frame camera positions and focal points, each (T, 3)."""
    ground = pelvis.copy()
    ground[:, 1] = 0.0
    offset = view_direction(view, facing)

    if cfg.mode == "track":
        targets = _moving_average(ground, max(1, round(cfg.smooth_seconds * fps)))
        distance = cfg.distance
    elif cfg.mode == "fixed":
        center = 0.5 * (ground.min(axis=0) + ground.max(axis=0))
        rel = ground - center
        depth = np.abs(rel @ offset).max()  # extent towards/away from the camera
        lateral = np.abs(rel @ np.cross(UP, offset)).max()  # extent across the image
        half_hfov = np.arctan(np.tan(np.radians(cfg.fov) / 2) * aspect)
        distance = max(depth + cfg.distance, (lateral + 1.0) / np.tan(half_hfov))
        targets = np.repeat(center[None], len(ground), axis=0)
    else:
        raise ValueError(f"unknown camera mode {cfg.mode!r}")

    focal = targets + UP * (floor_y + cfg.look_height)
    position = targets + offset * distance + UP * (floor_y + cfg.height)
    return position, focal


def _moving_average(x, window):
    pad = window // 2
    padded = np.pad(x, ((pad, window - 1 - pad), (0, 0)), mode="edge")
    kernel = np.ones(window) / window
    return np.stack([np.convolve(padded[:, i], kernel, mode="valid") for i in range(x.shape[1])], axis=1)
