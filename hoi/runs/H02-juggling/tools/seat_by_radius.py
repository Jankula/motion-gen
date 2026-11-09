"""How should the seat of a single ball change with the ball's size?  Measured on the real mesh.

A larger ball is flatter against the palm, so the bulges of the palm reach it sooner.  evaluate.py only
knows the radius from the task file, so this makes one clip and one task per radius.

    python tools/seat_by_radius.py write
    python tools/seat_by_radius.py eval
    python tools/seat_by_radius.py read
"""
import csv
import itertools
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from juggling import generate_juggling_motion  # noqa: E402
from juggling.fingers import BallHand  # noqa: E402
from juggling.params import make_params  # noqa: E402
from locomotion.rotations import from_rotvec  # noqa: E402
from locomotion.skeleton import IDX, fk  # noqa: E402

RADII = [0.025, 0.0325, 0.038, 0.045]
MODE = sys.argv[2] if len(sys.argv) > 2 else "one"
GRIDS = dict(one=dict(seat_along=[0.010, 0.020, 0.030, 0.040], seat_gap=[0.002, 0.005, 0.008, 0.012, 0.016],
                      finger_press=[-0.003, -0.001]),
             two=dict(tray_clear=[0.001, 0.004, 0.007, 0.010, 0.013, 0.016, 0.020], rear_along=[-0.012, -0.006, 0.000],
                      two_wrap=[0.35, 0.52, 0.79]))
GRID = GRIDS[MODE]
KEYS = list(GRID)


def write():
    os.makedirs("scratch", exist_ok=True)
    base = json.load(open("task.json", encoding="utf-8"))
    q0 = make_params()
    m = generate_juggling_motion(base)
    rig = m["rig"]
    plan = rig.plan
    ev = [e for e in plan.events["L"] if e.kind == "throw" and e.t > 3.0][0]
    frames = [0, int((ev.t - 0.13) * plan.fps), int(ev.t * plan.fps)] if MODE == "one" else [0]
    R = np.concatenate([from_rotvec(m["global_orient"])[:, None], from_rotvec(m["body_pose"])], 1)
    W, P = fk(m["transl"], R)
    wj = IDX["left_wrist"]
    combos = list(itertools.product(*[GRID[k] for k in KEYS]))
    grid = [(f,) + c for f in frames for c in combos]
    T = 600
    assert len(grid) <= T
    for r in RADII:
        out = {k: np.zeros((T,) + m[k].shape[1:]) for k in ("transl", "global_orient", "body_pose", "left_hand_pose", "right_hand_pose")}
        balls = np.zeros((T, 3, 3))
        balls[:, :] = [[-1.5, 1.5, 0.0], [-1.5, 1.0, 0.0], [-1.5, 0.5, 0.0]]
        cache = {}
        for i in range(T):
            row = grid[min(i, len(grid) - 1)]
            f, c = row[0], row[1:]
            for k in ("transl", "global_orient", "body_pose", "right_hand_pose"):
                out[k][i] = m[k][f]
            if c not in cache:
                over = dict(zip(KEYS, c))
                if "tray_clear" in over:      # one clearance for all sizes while measuring
                    over["tray_gap"] = ((0.0, over["tray_clear"]), (1.0, over.pop("tray_clear")))
                cache[c] = BallHand(r, {**q0, **over})
            h = cache[c]
            if MODE == "one":
                out["left_hand_pose"][i] = h.shapes["L"]["one"]
                balls[i, 0] = P[f, wj] + W[f, wj] @ h.offset("L", "one")
            else:
                out["left_hand_pose"][i] = h.shapes["L"]["two"]
                balls[i, 0] = P[f, wj] + W[f, wj] @ h.offset("L", "front")
                balls[i, 1] = P[f, wj] + W[f, wj] @ h.offset("L", "rear")
        name = "scratch/seatr_%03d" % round(r * 1000)
        np.savez(name + ".npz", fps=30, balls_transl=balls, **out)
        t = dict(base)
        t["balls"] = {"count": 3, "radius": r, "mass_kg": 0.12}
        json.dump(t, open(name + ".json", "w", encoding="utf-8"))
    np.save("scratch/seatr_grid.npy", np.array(grid + [grid[-1]] * (T - len(grid))))
    print("wrote", len(RADII), "clips of", len(grid), "configurations")


def read():
    grid = np.load("scratch/seatr_grid.npy")
    for r in RADII:
        name = "scratch/seatr_%03d" % round(r * 1000)
        rows = list(csv.DictReader(open(name + ".timeline.csv")))
        d = np.array([float(x["hand_into_ball_mm"]) for x in rows])
        g = np.array([float(x["ball1_gap_mm"]) for x in rows])
        combos = {}
        for i, row in enumerate(grid):
            combos.setdefault(tuple(row[1:]), []).append(i)
        if MODE == "two":
            g2 = np.array([float(x["ball2_gap_mm"]) for x in rows])
            print("r = %.1f mm: depth [mm] (front ball skin gap, rear ball skin gap); rows: tray_gap, columns: rear_along, at each wrap" % (r * 1000))
            for w in GRID["two_wrap"]:
                print("  wrap %.0f deg" % np.degrees(w))
                for tg in GRID["tray_clear"]:
                    line = []
                    for ra in GRID["rear_along"]:
                        i = combos[(tg, ra, w)][0]
                        line.append("%5.1f (%5.1f %5.1f)" % (d[i], g[i], g2[i]))
                    print("   %5.0f   " % (tg * 1000) + "  ".join(line))
            continue
        print("r = %.1f mm: worst depth over the poses [mm]; rows: gap, columns: along" % (r * 1000))
        print("   gap\\along " + " ".join("%5.0f" % (a * 1000) for a in GRID["seat_along"]))
        press = GRID["finger_press"][-1]
        for gap in GRID["seat_gap"]:
            line = [max(d[combos[(al, gap, press)]]) for al in GRID["seat_along"]]
            print("   %7.0f   " % (gap * 1000) + " ".join("%5.1f" % x for x in line))


def evaluate():
    """Run evaluate.py on all clips, a few at a time."""
    import concurrent.futures as cf
    import subprocess

    def one(r):
        name = "scratch/seatr_%03d" % round(r * 1000)
        subprocess.run([sys.executable, "evaluate.py", name + ".npz", name + ".json"], capture_output=True)

    with cf.ThreadPoolExecutor(3) as pool:
        list(pool.map(one, RADII))


if __name__ == "__main__":
    {"write": write, "read": read, "eval": evaluate}[sys.argv[1]]()
