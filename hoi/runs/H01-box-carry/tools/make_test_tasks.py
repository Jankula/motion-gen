"""Write the extra test tasks into test_tasks/: other boxes, weights, layouts and directions."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = dict(name="", title="Pick up a box, carry it and put it down", instruction="", fps=30, frames=600)

CASES = {
    # name: start position, heading, box size, mass, box centre, box yaw, target centre, target yaw
    "left-rotated": ([1.0, -1.0], 30, [0.5, 0.25, 0.35], 6, [-1.0, 2.5], 35, [-3.0, 0.0], -20),
    "target-behind": ([0, 0], 0, [0.4, 0.3, 0.3], 14, [0, 3.0], 0, [0.5, 0.0], 0),
    "target-right": ([0, 0], 0, [0.3, 0.4, 0.3], 8, [0.5, 2.5], 90, [-2.5, 3.5], 0),
    "small-light": ([0, 0], 0, [0.3, 0.2, 0.25], 4, [0, 2.5], 0, [2.0, 1.0], 45),
    "far-target": ([0, 0], 0, [0.45, 0.3, 0.35], 12, [0, 3.5], 0, [5.0, 6.0], 180),
    "close-target": ([0, 0], 0, [0.4, 0.3, 0.3], 10, [0, 3.0], 0, [1.2, 3.2], 30),
    "wide-heavy": ([0, 0], 20, [0.6, 0.3, 0.4], 15, [1.0, 4.0], -30, [-2.0, 2.0], 120),
    "tall-box": ([0, 0], 0, [0.35, 0.5, 0.3], 9, [0, 3.0], 0, [-2.5, 4.5], -90),
    "tiny-move": ([0, 0], 0, [0.4, 0.3, 0.3], 10, [0, 3.0], 0, [0.2, 3.1], 0),
    "typical-a": ([0, 0], 10, [0.5, 0.35, 0.3], 12, [0.5, 3.0], 15, [-3.0, 2.0], 0),
    "typical-b": ([0, 0], -10, [0.35, 0.3, 0.35], 7, [-0.5, 3.2], -10, [2.5, 1.5], 30),
    "typical-c": ([1, 1], 90, [0.45, 0.25, 0.35], 8, [4.0, 1.0], 90, [2.0, 3.5], 45),
}


def main():
    os.makedirs(os.path.join(ROOT, "test_tasks"), exist_ok=True)
    for name, (pos, head, size, mass, c0, y0, c1, y1) in CASES.items():
        t = dict(BASE, name=name)
        t["start"] = {"state": "standing", "position": pos, "heading_deg": head}
        t["end"] = {"state": "standing"}
        t["object"] = {"label": "box", "size": size, "mass_kg": mass, "start": {"center": c0, "yaw_deg": y0}}
        t["target"] = {"center": c1, "yaw_deg": y1}
        with open(os.path.join(ROOT, "test_tasks", name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(t, fh, indent=2)


if __name__ == "__main__":
    main()
