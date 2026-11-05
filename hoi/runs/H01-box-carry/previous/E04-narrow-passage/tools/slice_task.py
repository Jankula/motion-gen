"""Write a copy of a task whose obstacles are cut into slices, to find where the body comes
closest to them with evaluate.py (which reports one clearance per obstacle).

    python tools/slice_task.py task.json probe/zslices.json --axis z --n 6
    python tools/slice_task.py task.json probe/yslices.json --axis y --n 5

--axis z: slices along the box's own z extent; --axis y: boxes of increasing height (each
reports the closest approach of skin below its top).  (My own checking tool.)"""
import argparse
import json
import os

ap = argparse.ArgumentParser()
ap.add_argument("task")
ap.add_argument("out")
ap.add_argument("--axis", default="z")
ap.add_argument("--n", type=int, default=6)
a = ap.parse_args()
with open(a.task, encoding="utf-8") as fh:
    t = json.load(fh)
obs = []
for ob in t.get("obstacles", []):
    sx, h, sz = ob["size"]
    for k in range(a.n):
        o = dict(ob)
        if a.axis == "z":
            # slice k of the box along its own z axis (yaw 0 assumed for the offset)
            o["center"] = [ob["center"][0], ob["center"][1] - 0.5 * sz + (k + 0.5) * sz / a.n]
            o["size"] = [sx, h, sz / a.n]
        else:
            o["size"] = [sx, h * (k + 1) / a.n, sz]
        o["label"] = "%s/%s%d" % (ob.get("label", "box"), a.axis, k)
        obs.append(o)
t["obstacles"] = obs
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
with open(a.out, "w", encoding="utf-8") as fh:
    json.dump(t, fh, indent=1)
print("wrote %s with %d obstacles" % (a.out, len(obs)))
