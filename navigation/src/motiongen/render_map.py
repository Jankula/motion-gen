"""Top-down map and path overlay images with a metric grid."""

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont


PIXELS_PER_METER = 100
MARGIN = 50
CAPTION_PADDING = 12
CAPTION_LINE_HEIGHT = 22
GRID_MINOR = (232, 232, 232)
GRID_MAJOR = (190, 190, 190)
NO_GO = (250, 222, 222)
TEXT = (20, 20, 20)
START = (30, 110, 220)
PATH_OK = (20, 150, 70)
PATH_BAD = (210, 30, 30)


def _to_pixel(scene, x, y):
    u = MARGIN + (x - scene.room_x[0]) * PIXELS_PER_METER
    v = MARGIN + (scene.room_y[1] - y) * PIXELS_PER_METER
    return u, v


def _color(name):
    try:
        return ImageColor.getrgb(name)
    except ValueError:
        return (150, 150, 150)


def render_map(scene, start):
    width = int((scene.room_x[1] - scene.room_x[0]) * PIXELS_PER_METER) + 2 * MARGIN
    height = int((scene.room_y[1] - scene.room_y[0]) * PIXELS_PER_METER) + 2 * MARGIN
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=13)

    # Shade positions the body centre cannot occupy.
    no_go = scene.clearance[1:-1, 1:-1] < scene.body_radius
    shade = Image.fromarray((no_go.T[::-1] * 255).astype(np.uint8)).resize(
        (width - 2 * MARGIN, height - 2 * MARGIN), Image.NEAREST
    )
    image.paste(NO_GO, (MARGIN, MARGIN), shade)

    for meters in np.arange(scene.room_x[0], scene.room_x[1] + 0.01, 0.5):
        major = float(meters).is_integer()
        u, _ = _to_pixel(scene, meters, 0)
        draw.line([u, MARGIN, u, height - MARGIN], fill=GRID_MAJOR if major else GRID_MINOR)
        if major:
            draw.text((u, height - MARGIN + 6), f"{meters:g}", fill=TEXT, font=font, anchor="ma")
    for meters in np.arange(scene.room_y[0], scene.room_y[1] + 0.01, 0.5):
        major = float(meters).is_integer()
        _, v = _to_pixel(scene, 0, meters)
        draw.line([MARGIN, v, width - MARGIN, v], fill=GRID_MAJOR if major else GRID_MINOR)
        if major:
            draw.text((MARGIN - 6, v), f"{meters:g}", fill=TEXT, font=font, anchor="rm")

    draw.text((width / 2, height - 18), "x (m)", fill=TEXT, font=font, anchor="mm")
    draw.text((18, height / 2), "y (m)", fill=TEXT, font=font, anchor="mm")
    draw.rectangle([MARGIN, MARGIN, width - MARGIN, height - MARGIN], outline=TEXT, width=2)
    for room in scene.rooms:
        draw.polygon([_to_pixel(scene, x, y) for x, y in room["polygon"]], outline=TEXT, width=2)

    # Larger objects first, so things resting on a table stay visible.
    for obj in sorted(scene.objects, key=lambda o: -o.size[0] * o.size[1]):
        for x0, y0, x1, y1 in obj.rects:
            u0, v0 = _to_pixel(scene, x0, y1)
            u1, v1 = _to_pixel(scene, x1, y0)
            if obj.blocks_body(scene.body_height):
                draw.rectangle([u0, v0, u1, v1], fill=_color(obj.color), outline=None if obj.footprint else TEXT)
            else:
                draw.rectangle([u0, v0, u1, v1], outline=_color(obj.color), width=2)
    for obj in scene.objects:
        u, v = _to_pixel(scene, obj.center[0], obj.y_range[1])
        draw.text((u, v - 3), obj.id, fill=TEXT, font=font, anchor="md", stroke_width=2, stroke_fill="white")

    u, v = _to_pixel(scene, *start)
    r = scene.body_radius * PIXELS_PER_METER
    draw.ellipse([u - r, v - r, u + r, v + r], outline=START, width=3)
    draw.text((u, v), "start", fill=START, font=font, anchor="mm", stroke_width=2, stroke_fill="white")
    return image


def add_caption(image, text):
    """Return image with text wrapped in a band above it."""
    font = ImageFont.load_default(size=16)
    measure = ImageDraw.Draw(image)
    lines = [""]
    for word in text.split():
        trial = f"{lines[-1]} {word}".strip()
        if measure.textlength(trial, font=font) <= image.width - 2 * CAPTION_PADDING:
            lines[-1] = trial
        else:
            lines.append(word)
    band = 2 * CAPTION_PADDING + CAPTION_LINE_HEIGHT * len(lines)
    captioned = Image.new("RGB", (image.width, image.height + band), "white")
    captioned.paste(image, (0, band))
    draw = ImageDraw.Draw(captioned)
    for index, line in enumerate(lines):
        draw.text((CAPTION_PADDING, CAPTION_PADDING + index * CAPTION_LINE_HEIGHT), line, fill=TEXT, font=font)
    return captioned


def render_overlay(scene, start, points, check, instruction=None):
    """Draw the route on the map. An empty route, as when nothing was walked, draws only the map."""
    image = render_map(scene, start)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=13)
    if points:
        pixels = [_to_pixel(scene, x, y) for x, y in points]
        color = PATH_OK if check["collision_free"] else PATH_BAD
        if len(pixels) > 1:
            draw.line(pixels, fill=color, width=4, joint="curve")
        u, v = pixels[-1]
        draw.ellipse([u - 5, v - 5, u + 5, v + 5], fill=color)
        draw.text((u + 8, v - 8), "end", fill=color, font=font, stroke_width=2, stroke_fill="white")
        if check["first_collision"]:
            u, v = _to_pixel(scene, check["first_collision"]["x"], check["first_collision"]["y"])
            draw.line([u - 9, v - 9, u + 9, v + 9], fill=(0, 0, 0), width=4)
            draw.line([u - 9, v + 9, u + 9, v - 9], fill=(0, 0, 0), width=4)
    return add_caption(image, instruction) if instruction else image


# Motion-labelled route (motion_script.json): one colour per subtask.
SUBTASK_COLORS = [
    (31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40), (148, 103, 189),
    (140, 86, 75), (227, 119, 194), (23, 190, 207), (188, 189, 34), (127, 127, 127),
]
STEP_BACK_COLOR = (120, 120, 120)
NARROW_COLOR = (20, 20, 20)
ACTION_WORDS = {
    "open": "open", "close": "close", "reach_grasp": "pick", "put_down": "put", "use": "switch on",
    "sit_down": "sit on", "stand_up": "stand up",
}
LEGEND_LINE_HEIGHT = 20


def subtask_color(number):
    return SUBTASK_COLORS[(number - 1) % len(SUBTASK_COLORS)]


def _action_text(seg):
    hand = {"right": " (R)", "left": " (L)"}.get(seg.get("hand"), "")
    if seg["motion"] == "put_down":
        where = "in" if seg.get("relation") == "in" else "on"
        return f"{seg['i']} put {seg['label']} {where} {seg['receptacle_label']}{hand}"
    if seg["motion"] == "stand_up":
        return f"{seg['i']} stand up"
    return f"{seg['i']} {ACTION_WORDS[seg['motion']]} {seg.get('label') or seg.get('object')}{hand}"


def render_motion_route(scene, script):
    """The map with the route coloured by subtask and every motion labelled where it happens.

    Walks are coloured lines with their segment number; stretches narrower than the partner's
    walking body are dashed dark; step-backs are grey; turns are arcs; actions are listed in
    boxes at the spot where the person stands. A legend below names the subtasks.
    """
    image = render_map(scene, script["start"]["position"])
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=13)
    bold = ImageFont.load_default(size=14)

    for seg in script["segments"]:
        color = subtask_color(seg["subtask"])
        if seg["motion"] in ("walk", "step_back"):
            pixels = [_to_pixel(scene, x, y) for x, y in seg["path"]]
            line_color = STEP_BACK_COLOR if seg["motion"] == "step_back" else color
            if len(pixels) > 1:
                draw.line(pixels, fill=line_color, width=5 if seg["motion"] == "walk" else 3, joint="curve")
            for stretch in seg.get("narrow", []):
                _dash_along(draw, scene, seg["path"], stretch["from_m"], stretch["to_m"])
    # Numbers and glyphs on top of all lines.
    labels = {}
    for seg in script["segments"]:
        color = subtask_color(seg["subtask"])
        if seg["motion"] == "walk":
            u, v = _to_pixel(scene, *_point_at_fraction(seg["path"], 0.5))
            draw.ellipse([u - 10, v - 10, u + 10, v + 10], fill="white", outline=color, width=3)
            draw.text((u, v), str(seg["i"]), fill=TEXT, font=font, anchor="mm")
        elif seg["motion"] == "turn":
            u, v = _to_pixel(scene, *seg["at"])
            h0, h1 = seg["from_heading"], seg["from_heading"] + seg["angle"]
            r = 16
            draw.arc([u - r, v - r, u + r, v + r], -max(h0, h1), -min(h0, h1), fill=color, width=3)
            tip = np.radians(h1)
            tu, tv = u + r * np.cos(tip), v - r * np.sin(tip)
            draw.ellipse([tu - 4, tv - 4, tu + 4, tv + 4], fill=color)
        elif seg["motion"] != "step_back":
            key = tuple(round(c, 1) for c in seg["at"])
            labels.setdefault(key, []).append((_action_text(seg), color))
    boxes = []
    for (x, y), lines in labels.items():
        u, v = _to_pixel(scene, x, y)
        draw.ellipse([u - 5, v - 5, u + 5, v + 5], fill=lines[0][1], outline=TEXT)
        width = max(draw.textlength(text, font=font) for text, _ in lines) + 10
        height = 16 * len(lines) + 6
        u0, v0 = _label_spot(u, v, width, height, boxes, image.width, image.height)
        boxes.append((u0, v0, u0 + width, v0 + height))
        if not (u0 <= u <= u0 + width and v0 <= v <= v0 + height):
            nearest = (min(max(u, u0), u0 + width), min(max(v, v0), v0 + height))
            draw.line([u, v, *nearest], fill=TEXT, width=1)
        draw.rectangle([u0, v0, u0 + width, v0 + height], fill=(255, 255, 255), outline=TEXT)
        for k, (text, color) in enumerate(lines):
            draw.text((u0 + 5, v0 + 3 + 16 * k), text, fill=color, font=font)

    # Legend: one line per subtask, then the instruction above everything.
    legend = [(f"{s['id']}. {s['text']}" + (" (derived)" if s["source"] == "derived" else ""),
               subtask_color(s["id"])) for s in script["subtasks"]]
    legend.append(("grey: step back   dark dashes: narrower than the walking body   arcs: turns on the spot",
                   STEP_BACK_COLOR))
    band = 2 * CAPTION_PADDING + LEGEND_LINE_HEIGHT * len(legend)
    out = Image.new("RGB", (image.width, image.height + band), "white")
    out.paste(image, (0, 0))
    draw = ImageDraw.Draw(out)
    for k, (text, color) in enumerate(legend):
        y = image.height + CAPTION_PADDING + k * LEGEND_LINE_HEIGHT
        draw.rectangle([CAPTION_PADDING, y + 3, CAPTION_PADDING + 14, y + 15], fill=color)
        draw.text((CAPTION_PADDING + 22, y), text, fill=TEXT, font=bold)
    caption = script.get("instruction")
    return add_caption(out, caption) if caption else out


def _label_spot(u, v, width, height, boxes, image_width, image_height):
    """A top-left corner for a label box near (u, v), inside the image and clear of other boxes."""
    candidates = []
    for shift in range(0, 400, 20):
        for du, dv in ((12, -height / 2 + shift), (-12 - width, -height / 2 + shift),
                       (12, -height / 2 - shift), (-12 - width, -height / 2 - shift)):
            candidates.append((u + du, v + dv))
    for u0, v0 in candidates:
        if u0 < 2 or v0 < 2 or u0 + width > image_width - 2 or v0 + height > image_height - 2:
            continue
        if all(u0 > b[2] + 4 or u0 + width < b[0] - 4 or v0 > b[3] + 4 or v0 + height < b[1] - 4 for b in boxes):
            return u0, v0
    return min(max(u + 12, 2), image_width - width - 2), min(max(v - height / 2, 2), image_height - height - 2)


def _cumulative(points):
    points = np.asarray(points, dtype=float)
    return points, np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))])


def _point_at(points, along, distance):
    distance = min(max(distance, 0.0), along[-1])
    i = int(np.searchsorted(along, distance, side="right")) - 1
    i = min(max(i, 0), len(points) - 2)
    span = along[i + 1] - along[i]
    t = 0.0 if span == 0 else (distance - along[i]) / span
    return points[i] + t * (points[i + 1] - points[i])


def _point_at_fraction(path, fraction):
    points, along = _cumulative(path)
    if len(points) == 1:
        return points[0]
    return _point_at(points, along, fraction * along[-1])


def _dash_along(draw, scene, path, start, end, dash=0.1):
    points, along = _cumulative(path)
    if len(points) < 2:
        return
    d = start
    while d < end:
        a = _point_at(points, along, d)
        b = _point_at(points, along, min(d + dash, end))
        draw.line([_to_pixel(scene, *a), _to_pixel(scene, *b)], fill=NARROW_COLOR, width=3)
        d += 2 * dash
