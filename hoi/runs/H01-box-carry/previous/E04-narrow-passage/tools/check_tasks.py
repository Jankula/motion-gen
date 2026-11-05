"""Generate every task in the given files and print a one-line numerical summary for each.

    python tools/check_tasks.py task.json tasks/*.json test_tasks/*.json

Motions are written to test_out/.  Columns: compute time, fastest joint, smallest knee angle,
largest hip rotation, pelvis distance from the (rounded) path, closest approach of the two
soles and of the two shank axes, lowest sole point, 95th percentile of the floor-contact
point speed per foot, and end position / heading errors.  (My own checking tool.)"""
import io
import os
import sys
import time
from contextlib import redirect_stdout

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import analyze as A  # noqa: E402
from locomotion import generate_motion, load_task, save_motion  # noqa: E402
from locomotion.rotations import DEG, euler_xzy  # noqa: E402
from locomotion.skeleton import FLOOR, IDX, fk  # noqa: E402

for path in sys.argv[1:]:
    name = os.path.splitext(os.path.basename(path))[0]
    task = load_task(path)
    t0 = time.perf_counter()
    m = generate_motion(task)
    dt = time.perf_counter() - t0
    os.makedirs(os.path.join(HERE, "test_out"), exist_ok=True)
    out = os.path.join(HERE, "test_out", name + ".npz")
    save_motion(out, m)
    tr, R, fps = A.load(out)
    W, P = fk(tr, R)
    buf = io.StringIO()
    with redirect_stdout(buf):
        A.main(out, path)
    txt = buf.getvalue()
    sp = []
    for j in range(22):
        Rr = np.einsum("fji,fjk->fik", R[:-1, j], R[1:, j])
        ang = np.arccos(np.clip((np.trace(Rr, axis1=1, axis2=2) - 1) / 2, -1, 1))
        sp.append(ang.max() * fps / DEG)
    knee = min(euler_xzy(R[:, IDX[n]])[:, 0].min() / DEG for n in ("left_knee", "right_knee"))
    rot = max(np.abs(euler_xzy(R[:, IDX[n]])[:, 2]).max() / DEG for n in ("left_hip", "right_hip"))
    end = task.get("end", {})
    e_pos = ""
    if "position" in end:
        e_pos = "end err %.1f cm " % (np.linalg.norm(P[-1, 0, [0, 2]] - np.array(end["position"])) * 100)
    if "heading_deg" in end:
        f = W[-1, 0, :, 2]
        e_pos += "head err %.1f deg " % abs((np.degrees(np.arctan2(f[0], f[2])) - end["heading_deg"] + 180) % 360 - 180)
    dev = [l for l in txt.splitlines() if "path deviation" in l][0].split("path deviation")[1].strip()
    foot = [l for l in txt.splitlines() if "closest foot-foot" in l][0].split("points")[1].strip()
    shank = [l for l in txt.splitlines() if "shank-shank" in l][0].split("distance")[1].split(",")[0].strip()
    low = min(float(l.split("lowest sole point")[1].split("mm")[0]) for l in txt.splitlines() if "lowest sole" in l)
    slip = [l.split("p95")[1].split(",")[0].strip() for l in txt.splitlines() if "contact point speed" in l]
    print(f"{name:22s} {dt:4.2f}s | max joint {max(sp):4.0f} deg/s | knee min {knee:5.1f} | hip rot max {rot:4.1f} | "
          f"dev {dev} | feet {foot} | shank {shank} | lowest {low:.1f} mm | slip p95 {slip} | {e_pos}")
