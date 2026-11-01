"""Render a motion as videos from the front, back, left and right of the walker.

    python -m walkenv.render runs/<run>                # reads runs/<run>/motion.npz, writes runs/<run>/videos/
    python -m walkenv.render motion.npz --out out_dir
    python -m walkenv.render runs/<run> --no-video     # only the contact sheet (fast)

Outputs: <view>.mp4 per view, grid.mp4 (all four views 2x2) and contact_sheet.png
(rows = views, columns = frames sampled across a short window, about one stride by default).
"""
import argparse
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import pyvista as pv
from PIL import Image, ImageDraw, ImageFont

from .body import Body
from .cameras import VIEWS, CameraConfig, camera_path, facing_direction
from .motion_format import load_motion

BODY_COLOR = "#d9a07a"
FLOOR_COLORS = np.array([[205, 205, 205], [160, 160, 160]], np.uint8)
SHADOW_COLOR = "#6e6e6e"
TILE = 0.5  # m; stated in the task prompt, so keep them in sync
BACKGROUND = ("#f5f7fa", "#b9c9da")  # bottom, top
GRID_LAYOUT = (("front", "back"), ("left", "right"))


def render(
    motion_path,
    out_dir,
    views=VIEWS,
    camera=None,
    size=(1280, 720),
    videos=True,
    grid=True,
    shadows=True,
    sheet_start=None,
    sheet_duration=1.2,
    sheet_cols=8,
    body=None,
):
    """Render videos and a contact sheet; returns the list of files written."""
    camera = camera or CameraConfig()
    body = body or Body()
    motion = load_motion(motion_path)
    fps = motion["fps"]
    verts, joints = body.forward(motion)
    num_frames = len(verts)
    width, height = size

    facing = facing_direction(motion["global_orient"])
    paths = {
        v: camera_path(v, joints[:, 0], facing, body.floor_y, fps, camera, width / height) for v in views
    }
    sheet_idx = _sheet_frames(num_frames, fps, sheet_start, sheet_duration, sheet_cols)
    frames_to_render = range(num_frames) if videos else sheet_idx

    pl, mesh, shadow = _build_scene(body, verts, joints[:, 0], size, camera, shadows)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    writers = {}
    if videos:
        for v in views:
            writers[v] = _video_writer(out_dir / f"{v}.mp4", fps)
        if grid and set(views) == set(VIEWS):
            writers["grid"] = _video_writer(out_dir / "grid.mp4", fps)
        written += [out_dir / f"{name}.mp4" for name in writers]

    font = _font(max(14, height // 36))
    sheet_tiles = {}
    try:
        for t in frames_to_render:
            _set_pose(mesh, shadow, verts[t], body)
            images = {}
            for v in views:
                position, focal = paths[v]
                pl.camera.position = position[t]
                pl.camera.focal_point = focal[t]
                pl.camera.up = (0.0, 1.0, 0.0)
                pl.renderer.ResetCameraClippingRange()
                pl.render()
                img = pl.screenshot(return_img=True)
                if t in sheet_idx:
                    sheet_tiles[(v, t)] = _crop_person(img, camera.mode)
                if v in writers:
                    img = _label(img, f"{v}   {t / fps:5.2f} s   frame {t}", font)
                    writers[v].append_data(img)
                images[v] = img
            if "grid" in writers:
                writers["grid"].append_data(_grid(images))
    finally:
        for w in writers.values():
            w.close()
        pl.close()

    sheet_path = out_dir / "contact_sheet.png"
    _contact_sheet(sheet_tiles, views, sheet_idx, fps).save(sheet_path)
    written.append(sheet_path)
    return written


def _build_scene(body, verts, pelvis, size, camera, shadows):
    pl = pv.Plotter(off_screen=True, window_size=list(size), lighting="none")
    pl.set_background(BACKGROUND[0], top=BACKGROUND[1])
    pl.camera.view_angle = camera.fov

    lo = pelvis[:, [0, 2]].min(axis=0)
    hi = pelvis[:, [0, 2]].max(axis=0)
    pl.add_mesh(
        _floor((lo + hi) / 2, (hi - lo).max() / 2 + 30.0, body.floor_y),
        scalars="rgb",
        rgb=True,
        ambient=0.35,
        diffuse=0.65,
        specular=0.0,
        show_scalar_bar=False,
    )

    mesh = pv.PolyData.from_regular_faces(verts[0].copy(), body.faces)
    pl.add_mesh(mesh, color=BODY_COLOR, interpolation="phong", ambient=0.25, diffuse=0.75, specular=0.15)
    shadow = None
    if shadows:
        # The body flattened straight down onto the floor: a planted foot touches its shadow, a lifted
        # one shows a gap. (VTK's shadow maps leave dark acne bands on a large floor.)
        shadow = pv.PolyData.from_regular_faces(verts[0].copy(), body.faces)
        pl.add_mesh(shadow, color=SHADOW_COLOR, lighting=False)
    _set_pose(mesh, shadow, verts[0], body)

    pl.add_light(pv.Light(position=(1.5, 6.0, 2.0), focal_point=(0, 0, 0), light_type="scene light", intensity=0.85))
    pl.add_light(pv.Light(light_type="headlight", intensity=0.35))
    pl.show(auto_close=False)  # pyvista skips render() calls until the plotter has been shown once
    return pl, mesh, shadow


def _set_pose(mesh, shadow, v, body):
    mesh.points = v
    mesh.point_data.active_normals = _vertex_normals(v, body.faces)
    if shadow is not None:
        flat = v.copy()
        flat[:, 1] = body.floor_y + 0.002  # just above the floor to avoid z-fighting
        shadow.points = flat


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
        path, fps=fps, codec="libx264", quality=8, macro_block_size=8, ffmpeg_params=["-preset", "veryfast"]
    )


def _font(size):
    return ImageFont.load_default(size=size)


def _label(img, text, font):
    im = Image.fromarray(img)
    ImageDraw.Draw(im).text((12, 8), text, fill=(20, 20, 20), font=font)
    return np.asarray(im)


def _half(img):
    return np.asarray(Image.fromarray(img).reduce(2))


def _grid(images):
    return np.vstack([np.hstack([_half(images[v]) for v in row]) for row in GRID_LAYOUT])


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
    th, tw = next(iter(tiles.values())).shape[:2]
    margin_left, margin_top = 90, 34
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
    ap.add_argument("motion", type=Path, help="motion .npz, or a run directory containing motion.npz")
    ap.add_argument("--out", type=Path, help="output directory (default: videos/ next to the motion)")
    ap.add_argument("--views", nargs="+", choices=VIEWS, default=list(VIEWS))
    ap.add_argument("--camera", choices=["track", "fixed"], default="track")
    ap.add_argument("--size", default="1280x720", help="WIDTHxHEIGHT of each view")
    ap.add_argument("--no-video", action="store_true", help="only write the contact sheet")
    ap.add_argument("--no-grid", action="store_true")
    ap.add_argument("--no-shadows", action="store_true")
    ap.add_argument("--sheet-start", type=float, help="contact sheet window start, seconds")
    ap.add_argument("--sheet-duration", type=float, default=1.2, help="contact sheet window length, seconds")
    ap.add_argument("--sheet-cols", type=int, default=8)
    args = ap.parse_args()

    motion = args.motion / "motion.npz" if args.motion.is_dir() else args.motion
    out = args.out or motion.parent / "videos"
    width, height = (int(x) for x in args.size.lower().split("x"))
    written = render(
        motion,
        out,
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
