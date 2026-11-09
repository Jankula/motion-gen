"""Render a motion as videos and contact sheets.

    python -m walkenv.render runs/E02-curved-path          # motion.npz + task.json there; writes videos/ there
    python -m walkenv.render motion.npz --task curved-path --out out_dir
    python -m walkenv.render runs/E02-curved-path --no-video   # only the two contact sheets (fast)

Views (see cameras.py): front, back, left, right follow the walker; top and overview show the whole
scene; for a task with an object, hands_left and hands_right are close-ups of the hands. The scene shows the marked path (teal line), start and end markers (grey and teal rings),
obstacles (translucent blue boxes, so they never hide the body), the pelvis trail so far (orange), and
for a task with an object the object itself (solid, cardboard coloured) and its target (teal outline), and
for a task with balls the balls (solid, one colour each, so that they can be followed).

Outputs:
  <view>.mp4            one video per view
  grid.mp4              all views in one video (3x2 grid, or 4x2 with the hand views)
  contact_sheet.png     follow views, frames across a short window (about one stride by default)
  overview_sheet.png    scene views, frames across the whole clip
"""
import argparse
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import pyvista as pv
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial.transform import Rotation

from .body import Body
from .cameras import FOLLOW_VIEWS, HAND_VIEWS, SCENE_VIEWS, VIEWS, CameraConfig, camera_path
from .motion_format import load_motion
from .tasks import load_task, scene_bounds

BODY_COLOR = "#d9a07a"
FLOOR_COLORS = np.array([[205, 205, 205], [160, 160, 160]], np.uint8)
SHADOW_COLOR = "#6e6e6e"
PATH_COLOR = "#1f9e89"
TRAIL_COLOR = "#e07b24"
OBSTACLE_COLOR = "#4f7cac"
OBJECT_COLOR = "#c49a6c"
OBJECT_EDGE_COLOR = "#7a5a36"
BALL_COLORS = ("#d1343f", "#f2b705", "#1f6fd1", "#37a24b", "#8e44ad")
TILE = 0.5  # m; stated in the task prompt, so keep them in sync
BACKGROUND = ("#f5f7fa", "#b9c9da")  # bottom, top
GRID_LAYOUTS = {
    frozenset(VIEWS): (("overview", "front", "left"), ("top", "back", "right")),
    frozenset(FOLLOW_VIEWS): (("front", "back"), ("left", "right")),
    frozenset(VIEWS + HAND_VIEWS): (("overview", "front", "left", "hands_left"), ("top", "back", "right", "hands_right")),
}
VIEW_TITLES = {
    "top": "top (whole scene)",
    "overview": "overview (whole scene)",
    "hands_left": "hands, from front left",
    "hands_right": "hands, from front right",
}
BOX_EDGES = [(0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (2, 6), (3, 7)]


def render(
    motion_path,
    out_dir,
    task=None,
    views=None,
    camera=None,
    size=(1280, 720),
    videos=True,
    grid=True,
    shadows=True,
    sheet_start=None,
    sheet_duration=1.2,
    sheet_cols=8,
    overview_cols=5,
    body=None,
):
    """Render videos and contact sheets; returns the list of files written. task: a loaded task or None.

    views: the views to render; by default all of them (the hand views only for a task with an object).
    """
    camera = camera or CameraConfig()
    body = body or Body()
    task = task or {"start": {}, "path_points": None}
    ball_count = task["balls"]["count"] if "balls" in task else None
    motion = load_motion(motion_path, expect_object="object" in task, expect_balls=ball_count)
    views = tuple(views or default_views(task))
    fps = motion["fps"]
    verts, joints = body.forward(motion)
    num_frames = len(verts)
    width, height = size
    pelvis = joints[:, 0]

    bounds = _bounds(task, pelvis)
    hands = joints[:, [20, 21]].mean(axis=1)  # the two wrists
    if "balls" in task:
        hands = hands + [0.0, 0.25, 0.0]  # the close-ups also have to show the balls in the air
    paths = {
        v: camera_path(v, pelvis, motion["global_orient"], body.floor_y, fps, camera, width / height, bounds, hands)
        for v in views
    }
    follow = [v for v in views if v in FOLLOW_VIEWS + HAND_VIEWS]
    scene = [v for v in views if v in SCENE_VIEWS]
    sheet_idx = _sheet_frames(num_frames, fps, sheet_start, sheet_duration, sheet_cols) if follow else []
    overview_idx = _sheet_frames(num_frames, fps, 0.0, (num_frames - 1) / fps, overview_cols) if scene else []
    frames_to_render = range(num_frames) if videos else sorted(set(sheet_idx) | set(overview_idx))

    pl, body_mesh, shadow, trail = _build_scene(body, verts, pelvis, task, bounds, size, camera, shadows)
    box = _add_object(pl, task, motion, body.floor_y, shadows) if "object" in task else None
    balls = _add_balls(pl, task, shadows) if "balls" in task else None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written, writers = [], {}
    if videos:
        for v in views:
            writers[v] = _video_writer(out_dir / f"{v}.mp4", fps)
        layout = GRID_LAYOUTS.get(frozenset(views))
        if grid and layout:
            writers["grid"] = _video_writer(out_dir / "grid.mp4", fps)
        written += [out_dir / f"{name}.mp4" for name in writers]

    font = _font(max(14, height // 36))
    tiles = {}
    try:
        for t in frames_to_render:
            _set_pose(body_mesh, shadow, trail, verts[t], body.faces, pelvis, t, body.floor_y)
            if box:
                _set_object(box, t, body.floor_y)
            if balls:
                _set_balls(balls, motion["balls_transl"][t], body.floor_y)
            images = {}
            for v in views:
                needed = v in writers or (t in sheet_idx and v in follow) or (t in overview_idx and v in scene)
                if not needed:
                    continue
                position, focal, up = paths[v]
                pl.camera.position = position[t]
                pl.camera.focal_point = focal[t]
                pl.camera.up = up
                pl.camera.view_angle = camera.scene_fov if v in SCENE_VIEWS else camera.fov
                pl.renderer.ResetCameraClippingRange()
                pl.render()
                img = pl.screenshot(return_img=True)
                if t in sheet_idx and v in follow:
                    tiles[(v, t)] = _crop_person(img, camera.mode)
                if t in overview_idx and v in scene:
                    tiles[(v, t)] = np.asarray(Image.fromarray(img).reduce(3))
                if v in writers:
                    img = _label(img, f"{VIEW_TITLES.get(v, v)}   {t / fps:5.2f} s   frame {t}", font)
                    writers[v].append_data(img)
                images[v] = img
            if "grid" in writers:
                writers["grid"].append_data(_grid(images, GRID_LAYOUTS[frozenset(views)]))
    finally:
        for w in writers.values():
            w.close()
        pl.close()

    for name, rows, idx in (("contact_sheet", follow, sheet_idx), ("overview_sheet", scene, overview_idx)):
        if rows:
            path = out_dir / f"{name}.png"
            _contact_sheet(tiles, rows, idx, fps).save(path)
            written.append(path)
    return written


def default_views(task):
    return VIEWS + HAND_VIEWS if "object" in task or "balls" in task else VIEWS


def _bounds(task, pelvis):
    if task.get("path_points") is None and not task.get("obstacles") and "object" not in task:
        lo, hi = pelvis[:, [0, 2]].min(axis=0), pelvis[:, [0, 2]].max(axis=0)
    else:
        lo, hi = scene_bounds(task, pelvis[:, [0, 2]])
    center, half = (lo + hi) / 2, np.maximum((hi - lo) / 2, 1.5)  # at least 3 m x 3 m
    return center - half, center + half


def _build_scene(body, verts, pelvis, task, bounds, size, camera, shadows):
    pl = pv.Plotter(off_screen=True, window_size=list(size), lighting="none")
    pl.set_background(BACKGROUND[0], top=BACKGROUND[1])
    pl.enable_depth_peeling()  # correct look of the translucent obstacles
    fy = body.floor_y
    lo, hi = bounds
    pl.add_mesh(
        _floor((lo + hi) / 2, (hi - lo).max() / 2 + 30.0, fy),
        scalars="rgb",
        rgb=True,
        ambient=0.35,
        diffuse=0.65,
        specular=0.0,
        show_scalar_bar=False,
    )

    if task.get("path_points") is not None:
        pts = task["path_points"]
        pl.add_mesh(pv.lines_from_points(np.c_[pts[:, 0], np.full(len(pts), fy + 0.004), pts[:, 1]]),
                    color=PATH_COLOR, line_width=5, lighting=False)
    for which, color in (("start", "#8a8a8a"), ("end", PATH_COLOR)):
        spec = task.get(which, {})
        if "position" in spec:
            x, z = spec["position"]
            pl.add_mesh(pv.Disc(center=(x, fy + 0.003, z), inner=0.22, outer=0.28, normal=(0, 1, 0), c_res=48),
                        color=color, lighting=False)
            if "heading_deg" in spec:
                r = np.radians(spec["heading_deg"])
                tip = (x + 0.45 * np.sin(r), fy + 0.003, z + 0.45 * np.cos(r))
                pl.add_mesh(pv.Line((x, fy + 0.003, z), tip), color=color, line_width=5, lighting=False)
    for ob in task.get("obstacles", []):
        sx, sy, sz = ob["size"]
        center = (ob["center"][0], fy + sy / 2, ob["center"][1])
        box = pv.Cube(center=center, x_length=sx, y_length=sy, z_length=sz).rotate_y(ob.get("yaw_deg", 0.0), point=center)
        pl.add_mesh(box, color=OBSTACLE_COLOR, opacity=0.35, specular=0.0)
        pl.add_mesh(box.extract_feature_edges(), color="#2b4a6b", line_width=2, lighting=False)

    trail = pv.lines_from_points(np.c_[pelvis[:, 0], np.full(len(pelvis), fy + 0.006), pelvis[:, 2]])
    pl.add_mesh(trail, color=TRAIL_COLOR, line_width=3, lighting=False)

    body_mesh = pv.PolyData.from_regular_faces(verts[0].copy(), body.faces)
    pl.add_mesh(body_mesh, color=BODY_COLOR, interpolation="phong", ambient=0.25, diffuse=0.75, specular=0.15)
    shadow = None
    if shadows:
        # The body flattened straight down onto the floor: a planted foot touches its shadow, a lifted
        # one shows a gap. (VTK's shadow maps leave dark acne bands on a large floor.)
        shadow = pv.PolyData.from_regular_faces(verts[0].copy(), body.faces)
        pl.add_mesh(shadow, color=SHADOW_COLOR, lighting=False)
    _set_pose(body_mesh, shadow, trail, verts[0], body.faces, pelvis, 0, fy)

    pl.add_light(pv.Light(position=(1.5, 6.0, 2.0), focal_point=(0, 0, 0), light_type="scene light", intensity=0.85))
    pl.add_light(pv.Light(light_type="headlight", intensity=0.35))
    pl.show(auto_close=False)  # pyvista skips render() calls until the plotter has been shown once
    return pl, body_mesh, shadow, trail


def _set_pose(body_mesh, shadow, trail, v, faces, pelvis, t, floor_y):
    body_mesh.points = v
    body_mesh.point_data.active_normals = _vertex_normals(v, faces)
    if shadow is not None:
        flat = v.copy()
        flat[:, 1] = floor_y + 0.002  # just above the floor to avoid z-fighting
        shadow.points = flat
    so_far = pelvis[np.minimum(np.arange(len(pelvis)), t)]  # points after t collapse onto the current one
    trail.points = np.c_[so_far[:, 0], np.full(len(so_far), floor_y + 0.006), so_far[:, 2]]


def _add_object(pl, task, motion, floor_y, shadows):
    """Add the moving box, its shadow and the outline of its target; returns what _set_object needs."""
    half = np.array(task["object"]["size"], float) / 2  # x, height, z
    corners = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]) * half
    cube = pv.Cube(x_length=2 * half[0], y_length=2 * half[1], z_length=2 * half[2], clean=False)
    cube.point_data.clear()  # the stored normals would not follow the box
    pl.add_mesh(cube, color=OBJECT_COLOR, interpolation="flat", ambient=0.3, diffuse=0.7, specular=0.05)
    edges = pv.PolyData(corners.copy(), lines=np.array([[2, a, b] for a, b in BOX_EDGES]).ravel())
    pl.add_mesh(edges, color=OBJECT_EDGE_COLOR, line_width=3, lighting=False)
    shadow = None
    if shadows:
        shadow = cube.copy()
        pl.add_mesh(shadow, color=SHADOW_COLOR, lighting=False)

    tgt = task["target"]
    r = np.radians(tgt.get("yaw_deg", 0.0))
    rot = np.array([[np.cos(r), np.sin(r)], [-np.sin(r), np.cos(r)]])  # yaw about +Y applied to [x, z]
    outline = (np.array([[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]) * half[[0, 2]]) @ rot.T + np.asarray(tgt["center"], float)
    pl.add_mesh(pv.lines_from_points(np.c_[outline[:, 0], np.full(5, floor_y + 0.004), outline[:, 1]]),
                color=PATH_COLOR, line_width=5, lighting=False)
    return {
        "mesh": cube, "rest": np.array(cube.points), "edges": edges, "corners": corners, "shadow": shadow,
        "position": motion["object_transl"], "rotation": Rotation.from_rotvec(motion["object_orient"]).as_matrix(),
    }


def _set_object(box, t, floor_y):
    position, rotation = box["position"][t], box["rotation"][t]
    box["mesh"].points = box["rest"] @ rotation.T + position
    box["edges"].points = box["corners"] @ rotation.T + position
    if box["shadow"] is not None:
        flat = box["rest"] @ rotation.T + position
        flat[:, 1] = floor_y + 0.002
        box["shadow"].points = flat


def _add_balls(pl, task, shadows):
    """Add one sphere and one round shadow per ball; returns their actors, which _set_balls moves."""
    radius = task["balls"]["radius"]
    actors = []
    for i in range(task["balls"]["count"]):
        color = BALL_COLORS[i % len(BALL_COLORS)]
        ball = pl.add_mesh(pv.Sphere(radius=radius, theta_resolution=40, phi_resolution=40), color=color,
                           interpolation="phong", ambient=0.3, diffuse=0.7, specular=0.25)
        shadow = None
        if shadows:
            disc = pv.Disc(center=(0, 0, 0), inner=0.0, outer=radius, normal=(0, 1, 0), c_res=32)
            shadow = pl.add_mesh(disc, color=SHADOW_COLOR, lighting=False)
        actors.append((ball, shadow))
    return actors


def _set_balls(balls, centers, floor_y):
    for (ball, shadow), (x, y, z) in zip(balls, centers.tolist()):
        ball.position = (x, y, z)
        if shadow is not None:
            shadow.position = (x, floor_y + 0.003, z)


def _floor(center_xz, half_size, floor_y):
    """Checkerboard floor with tiles aligned to the world grid (so it reveals foot sliding)."""
    n = 2 * int(np.ceil(half_size / TILE))
    cx, cz = np.round(np.asarray(center_xz) / TILE) * TILE
    plane = pv.Plane(
        center=(cx, floor_y, cz), direction=(0, 1, 0), i_size=n * TILE, j_size=n * TILE, i_resolution=n, j_resolution=n
    )
    c = plane.cell_centers().points
    parity = (np.floor(c[:, 0] / TILE) + np.floor(c[:, 2] / TILE)).astype(int) % 2
    plane.cell_data["rgb"] = FLOOR_COLORS[parity]
    return plane


def _vertex_normals(v, f):
    face_n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    n = np.zeros_like(v)
    for k in range(3):
        np.add.at(n, f[:, k], face_n)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _video_writer(path, fps):
    return imageio.get_writer(
        path, fps=fps, codec="libx264", quality=7, macro_block_size=8, ffmpeg_params=["-preset", "veryfast"]
    )


def _font(size):
    return ImageFont.load_default(size=size)


def _label(img, text, font):
    im = Image.fromarray(img)
    ImageDraw.Draw(im).text((12, 8), text, fill=(20, 20, 20), font=font)
    return np.asarray(im)


def _half(img):
    return np.asarray(Image.fromarray(img).reduce(2))


def _grid(images, layout):
    return np.vstack([np.hstack([_half(images[v]) for v in row]) for row in layout])


def _sheet_frames(num_frames, fps, start, duration, cols):
    if start is None:
        start = min(2.0, (num_frames - 1) / fps / 3)
    end = min(start + duration, (num_frames - 1) / fps)
    idx = np.round(np.linspace(start, end, cols) * fps).astype(int)
    return sorted(set(np.clip(idx, 0, num_frames - 1).tolist()))


def _crop_person(img, mode):
    """In track mode the walker stays centred, so crop to a portrait tile around them."""
    if mode != "track":
        return _half(img)
    h, w = img.shape[:2]
    cw = int(h * 0.6)
    x0 = (w - cw) // 2
    return _half(img[:, x0 : x0 + cw])


def _contact_sheet(tiles, views, frames, fps):
    th, tw = tiles[(views[0], frames[0])].shape[:2]
    margin_left, margin_top = 100, 34
    sheet = Image.new("RGB", (margin_left + tw * len(frames), margin_top + th * len(views)), "white")
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    for col, t in enumerate(frames):
        draw.text((margin_left + col * tw + 8, 8), f"{t / fps:.2f}s (#{t})", fill="black", font=font)
    for row, v in enumerate(views):
        draw.text((8, margin_top + row * th + th // 2 - 10), v, fill="black", font=font)
        for col, t in enumerate(frames):
            sheet.paste(Image.fromarray(tiles[(v, t)]), (margin_left + col * tw, margin_top + row * th))
    return sheet


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("motion", type=Path, help="motion .npz, or an experiment folder containing motion.npz")
    ap.add_argument("--task", help="task name or .json (default: task.json next to the motion, if any)")
    ap.add_argument("--out", type=Path, help="output directory (default: videos/ next to the motion)")
    ap.add_argument("--views", nargs="+", choices=VIEWS + HAND_VIEWS, help="default: all views for this task")
    ap.add_argument("--camera", choices=["track", "fixed"], default="track", help="follow views only")
    ap.add_argument("--size", default="1280x720", help="WIDTHxHEIGHT of each view")
    ap.add_argument("--no-video", action="store_true", help="only write the contact sheets")
    ap.add_argument("--no-grid", action="store_true")
    ap.add_argument("--no-shadows", action="store_true")
    ap.add_argument("--sheet-start", type=float, help="contact sheet window start, seconds")
    ap.add_argument("--sheet-duration", type=float, default=1.2, help="contact sheet window length, seconds")
    ap.add_argument("--sheet-cols", type=int, default=8)
    args = ap.parse_args()

    motion = args.motion / "motion.npz" if args.motion.is_dir() else args.motion
    task_ref = args.task or (motion.parent / "task.json" if (motion.parent / "task.json").exists() else None)
    width, height = (int(x) for x in args.size.lower().split("x"))
    written = render(
        motion,
        args.out or motion.parent / "videos",
        task=load_task(task_ref) if task_ref else None,
        views=args.views,
        camera=CameraConfig(mode=args.camera),
        size=(width, height),
        videos=not args.no_video,
        grid=not args.no_grid,
        shadows=not args.no_shadows,
        sheet_start=args.sheet_start,
        sheet_duration=args.sheet_duration,
        sheet_cols=args.sheet_cols,
    )
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
