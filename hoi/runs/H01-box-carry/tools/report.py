"""Numerical summary of a generated motion: events, reach, joint ranges, balance.

    python tools/report.py [task.json]
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from locomotion import load_task  # noqa: E402
from locomotion.rotations import DEG, euler_xzy, from_rotvec, to_rotvec  # noqa: E402
from locomotion.skeleton import FLOOR, IDX, J, fk  # noqa: E402
from manipulation import generate_box_motion  # noqa: E402
from manipulation.rig import ARMS  # noqa: E402


def main():
    task = load_task(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "task.json"))
    m = generate_box_motion(task)
    rig = m["rig"]
    ev = rig.ev
    print("tempo %.2f  hold k=%d m=%d  width %.2f depth %.2f" % (rig.s.tempo, rig.hold["k"], rig.hold["m"],
                                                                rig.hold["width"], rig.hold["depth"]))
    print("events:", {k: round(v, 2) for k, v in ev.items()})
    print("drops:", {k: round(v, 3) for k, v in rig.post.scale.items()})
    print("steps:", [(s.side, round(s.t_lo, 2), round(s.t_hs, 2), np.round(s.xz, 2).tolist()) for s in rig.s.plan.steps])
    fps = m["fps"]
    t = np.arange(len(m["transl"])) / fps
    P0, R, pos, Rb, reach = rig.pose(t)
    W, P = fk(P0 - J[0], R)
    keys = ["down0", "contact", "lift0", "lift1", "walk2", "stop2", "low0", "touch", "away", "rise1"]
    print("%8s %6s %7s %7s %6s %6s %6s %6s %6s" % ("event", "t", "pelvisY", "shldY", "boxY", "elbL", "elbR", "knee", "reach"))
    for k in keys:
        i = min(int(ev[k] * fps), len(t) - 1)
        elb = [np.degrees(np.linalg.norm(to_rotvec(R[i, ARMS[s].elbow]))) for s in "LR"]
        kn = np.degrees(np.linalg.norm(to_rotvec(R[i, IDX["left_knee"]])))
        print("%8s %6.2f %7.3f %7.3f %6.3f %6.1f %6.1f %6.1f %6.3f" % (
            k, t[i], P0[i, 1] - FLOOR, P[i, IDX["left_shoulder"], 1] - FLOOR, pos[i, 1] - FLOOR, elb[0], elb[1], kn,
            0.5 * (reach["L"][0][i] + reach["R"][0][i])))
    a, b = int(ev["contact"] * fps), int(ev["touch"] * fps)
    for s in "LR":
        r = reach[s][0][a:b]
        print("reach %s in hold: min %.3f max %.3f at t=%.2f" % (s, r.min(), r.max(), t[a + int(np.argmax(r))]))
    for name in ("left_wrist", "right_wrist", "left_elbow", "right_elbow", "left_shoulder", "right_shoulder"):
        e = np.degrees(euler_xzy(R[a:b, IDX[name]]))
        print("%-15s x %6.1f..%6.1f  z %6.1f..%6.1f  y %6.1f..%6.1f" % (name, e[:, 0].min(), e[:, 0].max(),
              e[:, 1].min(), e[:, 1].max(), e[:, 2].min(), e[:, 2].max()))
    for name in ("left_ankle", "right_ankle", "left_knee", "right_knee", "left_hip", "right_hip", "spine1", "neck"):
        e = np.degrees(euler_xzy(R[:, IDX[name]]))
        print("%-15s x %6.1f..%6.1f  z %6.1f..%6.1f  y %6.1f..%6.1f" % (name, e[:, 0].min(), e[:, 0].max(),
              e[:, 1].min(), e[:, 1].max(), e[:, 2].min(), e[:, 2].max()))
    sh = rig.post.shift(t)
    print("shift range x %.3f..%.3f z %.3f..%.3f" % (sh[:, 0].min(), sh[:, 0].max(), sh[:, 1].min(), sh[:, 1].max()))


if __name__ == "__main__":
    main()
