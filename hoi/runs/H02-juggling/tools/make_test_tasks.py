"""Write test_tasks/*.json: juggling tasks that differ from task.json in everything the task may vary.

    python tools/make_test_tasks.py
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = json.load(open(os.path.join(HERE, "task.json"), encoding="utf-8"))


def task(name, frames=600, fps=30, pos=(0, 0), heading=0, radius=0.0325, mass=0.12, foot="left", two=9, one=12, one_s=5):
    t = dict(BASE)
    t.update(name=name, frames=frames, fps=fps, start={"state": "standing", "position": list(pos), "heading_deg": heading})
    t["balls"] = {"count": 3, "radius": radius, "mass_kg": mass}
    t["juggle"] = {"standing_foot": foot, "min_throws_two_feet": two, "min_throws_one_foot": one, "min_one_foot_s": one_s}
    return t


TASKS = [
    task("right-foot", foot="right"),
    task("moved-turned", pos=(1.5, -2.0), heading=90),
    task("right-foot-turned", pos=(-0.7, 0.9), heading=-135, foot="right"),
    task("big-heavy", radius=0.045, mass=0.30),
    task("small-light", radius=0.025, mass=0.06),
    task("tennis", radius=0.034, mass=0.058, foot="right", heading=30),
    task("short-clip", frames=450),
    task("very-short", frames=360, two=6, one=8, one_s=3),
    task("long-clip", frames=900, two=15, one=20, one_s=10),
    task("high-minimums", two=16, one=22, one_s=9),
    task("other-fps", frames=500, fps=25),
]

if __name__ == "__main__":
    out = os.path.join(HERE, "test_tasks")
    os.makedirs(out, exist_ok=True)
    for t in TASKS:
        with open(os.path.join(out, t["name"] + ".json"), "w", encoding="utf-8") as fh:
            json.dump(t, fh, indent=2)
    print("wrote", len(TASKS), "tasks to", out)
