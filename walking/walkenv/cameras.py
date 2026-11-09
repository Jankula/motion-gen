"""Camera placement.

Two kinds of views:
  - follow views (front, back, left, right) move with the walker and are defined relative to the
    direction the body faces, smoothed over about a second: "front" always shows the face, also
    while the person turns. left/right are the subject's own left/right side.
  - scene views (top, overview) are fixed and show the whole scene: path, obstacles and the walker.
  - hand views (hands_left, hands_right) are close-ups for tasks with an object. They look at the
    point between the two wrists from slightly above, from the person's front left and front right.
"""
from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation

UP = np.array([0.0, 1.0, 0.0])
FOLLOW_VIEWS = ("front", "back", "left", "right")
SCENE_VIEWS = ("top", "overview")
VIEWS = FOLLOW_VIEWS + SCENE_VIEWS
HAND_VIEWS = ("hands_left", "hands_right")


@dataclass
class CameraConfig:
    mode: str = "track"  # follow views: "track" follows the walker; "fixed" is static and sees the whole path
    distance: float = 4.5  # m, camera to subject (track mode, and minimum for fixed mode)
    height: float = 1.1  # m above the floor
    look_height: float = 0.9  # m above the floor, the point the camera aims at
    fov: float = 30.0  # vertical field of view of the follow views, degrees
    scene_fov: float = 40.0  # vertical field of view of the scene views, degrees
    smooth_seconds: float = 1.0  # track mode: window that removes step-to-step sway from the camera path
    hand_distance: float = 2.0  # m, hand views: camera to the point between the wrists
    hand_elevation: float = 30.0  # degrees above the horizontal, hand views
    hand_side: float = 50.0  # degrees from straight in front of the person, hand views
    hand_smooth_seconds: float = 0.5  # hand views: window that removes the arm swing from the camera path


def heading_angles(global_orient):
    """Per-frame horizontal facing angle in radians (0 = +Z, pi/2 = +X), unwrapped so turns are continuous."""
    forward = Rotation.from_rotvec(global_orient).apply([0.0, 0.0, 1.0])  # rest pose faces +Z
    return np.unwrap(np.arctan2(forward[:, 0], forward[:, 2]))


def camera_path(view, pelvis, global_orient, floor_y, fps, cfg, aspect, bounds, hands=None):
    """Per-frame camera positions and focal points, each (T, 3), and the camera's up vector.

    hands: (T, 3) point between the wrists; needed for the hand views.
    """
    if view in SCENE_VIEWS:
        return _scene_camera(view, global_orient, floor_y, cfg, aspect, bounds, len(pelvis))
    if view in HAND_VIEWS:
        return _hand_camera(view, hands, global_orient, fps, cfg)
    ground = pelvis.copy()
    ground[:, 1] = 0.0
    angles = heading_angles(global_orient)

    if cfg.mode == "track":
        window = max(1, round(cfg.smooth_seconds * fps))
        targets = moving_average(ground, window)
        angles = moving_average(angles[:, None], window)[:, 0]
        offset = _view_direction(view, angles)
        distance = cfg.distance
    elif cfg.mode == "fixed":
        mean = np.arctan2(np.sin(angles).mean(), np.cos(angles).mean())
        offset = _view_direction(view, np.full(len(ground), mean))
        center = 0.5 * (ground.min(axis=0) + ground.max(axis=0))
        rel = ground - center
        depth = np.abs(rel @ offset[0]).max()  # extent towards/away from the camera
        lateral = np.abs(rel @ np.cross(UP, offset[0])).max()  # extent across the image
        half_hfov = np.arctan(np.tan(np.radians(cfg.fov) / 2) * aspect)
        distance = max(depth + cfg.distance, (lateral + 1.0) / np.tan(half_hfov))
        targets = np.repeat(center[None], len(ground), axis=0)
    else:
        raise ValueError(f"unknown camera mode {cfg.mode!r}")

    focal = targets + UP * (floor_y + cfg.look_height)
    position = targets + offset * distance + UP * (floor_y + cfg.height)
    return position, focal, UP


def _hand_camera(view, hands, global_orient, fps, cfg):
    window = max(1, round(cfg.hand_smooth_seconds * fps))
    focal = moving_average(hands, window)
    side = np.radians(cfg.hand_side) * (1 if view == "hands_left" else -1)  # the person's left is a larger heading
    angles = moving_average(heading_angles(global_orient)[:, None], 2 * window)[:, 0] + side
    elevation = np.radians(cfg.hand_elevation)
    direction = np.stack(
        [np.cos(elevation) * np.sin(angles), np.full_like(angles, np.sin(elevation)), np.cos(elevation) * np.cos(angles)],
        axis=1,
    )
    return focal + cfg.hand_distance * direction, focal, UP


def _view_direction(view, angles):
    """Unit vectors (T, 3) from the subject towards the camera."""
    facing = np.stack([np.sin(angles), np.zeros_like(angles), np.cos(angles)], axis=1)
    left = np.stack([facing[:, 2], np.zeros_like(angles), -facing[:, 0]], axis=1)  # cross(UP, facing)
    return {"front": facing, "back": -facing, "left": left, "right": -left}[view]


def _scene_camera(view, global_orient, floor_y, cfg, aspect, bounds, num_frames):
    """Fixed camera seeing the whole scene, with the scene's long axis across the image width.

    top: straight down; the walker's starting direction points to the image right (or up, for scenes
    that are wider than long). overview: from the side and slightly behind the start, 35 degrees down.
    """
    lo, hi = (np.asarray(b, float) for b in bounds)
    center = (lo + hi) / 2
    start = heading_angles(global_orient[:1])[0]
    fwd = np.array([np.sin(start), np.cos(start)])  # [x, z]
    walker_right = np.array([-fwd[1], fwd[0]])
    long_axis = np.array([1.0, 0.0]) if hi[0] - lo[0] >= hi[1] - lo[1] else np.array([0.0, 1.0])
    if long_axis @ fwd < 0:
        long_axis = -long_axis
    corners = np.array([[lo[0], lo[1]], [lo[0], hi[1]], [hi[0], lo[1]], [hi[0], hi[1]]]) - center
    tan_v = np.tan(np.radians(cfg.scene_fov) / 2)
    tan_h = tan_v * aspect

    if view == "top":
        right = long_axis  # image right
        up2 = np.array([right[1], -right[0]])  # image up when looking straight down
        h = max((np.abs(corners @ right).max() + 1.5) / tan_h, (np.abs(corners @ up2).max() + 1.5) / tan_v)
        focal = np.array([center[0], floor_y, center[1]])
        position = focal + UP * h
        up = np.array([up2[0], 0.0, up2[1]])
    else:
        side = np.array([long_axis[1], -long_axis[0]])
        if side @ walker_right < 0:
            side = -side
        horizontal = side - 0.5 * fwd
        horizontal /= np.linalg.norm(horizontal)
        across = np.array([horizontal[1], -horizontal[0]])  # image right, roughly
        elevation = np.radians(35)
        depth = np.abs(corners @ horizontal).max()
        d = max((np.abs(corners @ across).max() + 1.0) / tan_h, (depth * np.sin(elevation) + 1.2) / tan_v)
        d += 0.5 * depth * np.cos(elevation)  # the near edge of the scene is closer than the centre
        focal = np.array([center[0], floor_y + 0.5, center[1]])
        position = focal + d * (np.cos(elevation) * np.array([horizontal[0], 0.0, horizontal[1]]) + np.sin(elevation) * UP)
        up = UP
    return np.repeat(position[None], num_frames, axis=0), np.repeat(focal[None], num_frames, axis=0), up


def moving_average(x, window):
    """Centered moving average along axis 0, with edge padding. x: (T, D)."""
    pad = window // 2
    padded = np.pad(x, ((pad, window - 1 - pad), (0, 0)), mode="edge")
    kernel = np.ones(window) / window
    return np.stack([np.convolve(padded[:, i], kernel, mode="valid") for i in range(x.shape[1])], axis=1)
