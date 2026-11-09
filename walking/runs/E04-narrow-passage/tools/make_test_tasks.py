"""Write extra passage test tasks into test_tasks/ (my own testing tool)."""
import json
import math
import os

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_tasks")


def pair(cx, cz, gap, yaw_deg=0.0, depth=0.6, width=1.0, label=""):
    """Two cabinets left and right of the point (cx, cz) on a path with heading yaw_deg."""
    h = math.radians(yaw_deg)
    nx, nz = math.cos(h), -math.sin(h)          # left normal of the heading
    off = 0.5 * gap + 0.5 * width
    out = []
    for name, s in (("left", 1.0), ("right", -1.0)):
        out.append({"label": "%s%s" % (label, name), "center": [round(cx + s * off * nx, 4), round(cz + s * off * nz, 4)],
                    "size": [width, 2.0, depth], "yaw_deg": yaw_deg})
    return out


def task(name, frames, start, end, path, obstacles):
    return {"name": name, "fps": 30, "frames": frames, "start": start, "end": end, "path": path,
            "obstacles": obstacles}


walking = {"state": "walking", "position": [0, 0], "heading_deg": 0}
straight10 = {"segments": [{"type": "straight", "length": 10}], "tolerance_m": 0.15}
tasks = [
    task("gap-offcenter", 330, walking, {"state": "walking"}, straight10, pair(0.08, 4.3, 0.42)),
    task("gap-wider", 300, walking, {"state": "walking"}, straight10, pair(0.0, 4.0, 0.50)),
    task("gap-055", 240, walking, {"state": "walking"}, straight10, pair(0.0, 4.0, 0.55)),
    task("gap-058", 240, walking, {"state": "walking"}, straight10, pair(0.0, 4.0, 0.58)),
    task("gap-060", 240, walking, {"state": "walking"}, straight10, pair(0.0, 4.0, 0.60)),
    task("gap-062", 240, walking, {"state": "walking"}, straight10, pair(0.0, 4.0, 0.62)),
    task("gap-early", 270, walking, {"state": "walking"}, straight10, pair(0.0, 1.6, 0.40)),
    task("gap-twice", 420, walking, {"state": "walking"}, {"segments": [{"type": "straight", "length": 12}], "tolerance_m": 0.15},
         pair(0.0, 3.5, 0.40, label="a ") + pair(0.0, 7.5, 0.42, label="b ")),
    task("gap-stand-stop", 420, {"state": "standing", "position": [0, 0], "heading_deg": 0},
         {"state": "standing", "position": [0, 6.0], "heading_deg": 0},
         {"points": [[0, 0], [0, 6.0]], "tolerance_m": 0.15}, pair(0.0, 3.0, 0.40)),
]
# a gap after a 30 degree bend, with cabinets turned to the path
r, turn = 3.0, 30.0
x_a = r * (1 - math.cos(math.radians(turn)))
z_a = 3.0 + r * math.sin(math.radians(turn))
d = 2.0
cx, cz = x_a + d * math.sin(math.radians(turn)), z_a + d * math.cos(math.radians(turn))
tasks.append(task("gap-after-bend", 330, walking, {"state": "walking"},
                  {"segments": [{"type": "straight", "length": 3.0}, {"type": "arc", "radius": r, "turn_deg": turn},
                                {"type": "straight", "length": 8.0}], "tolerance_m": 0.15},
                  pair(cx, cz, 0.40, yaw_deg=turn)))
os.makedirs(HERE, exist_ok=True)
for t in tasks:
    with open(os.path.join(HERE, t["name"] + ".json"), "w", encoding="utf-8") as fh:
        json.dump(t, fh, indent=1)
    print("wrote", t["name"])
