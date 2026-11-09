"""Own numeric checks of a generated juggling motion, without the (slower) evaluate.py.

    python tools/diagnose.py [task.json]

Prints where the hands really end up compared with the plan, arm reach, joint speeds and ranges,
hand speed and acceleration, and the distance between balls.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from juggling import generate_juggling_motion  # noqa: E402
from locomotion.rotations import DEG, from_rotvec, to_rotvec, tr  # noqa: E402
from locomotion.skeleton import FLOOR, IDX, NAMES, fk  # noqa: E402


def main():
    task = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "task.json", encoding="utf-8"))
    m = generate_juggling_motion(task)
    rig = m["rig"]
    plan, scene = rig.plan, rig.scene
    t = np.arange(plan.frames) / plan.fps
    ev = plan.ev
    print("beat %.3f dwell %.3f flight %.3f throws %d" % (plan.beat, plan.dwell, plan.flight, plan.n_throws))
    print({k: round(v, 2) for k, v in ev.items()})
    print("apex %.3f..%.3f above floor" % (min(th.apex for th in plan.throws) - FLOOR, max(th.apex for th in plan.throws) - FLOOR))
    v = np.array([np.linalg.norm(th.v_rel) for th in plan.throws])
    print("release speed %.2f..%.2f, vy %.2f" % (v.min(), v.max(), np.mean([th.v_rel[1] for th in plan.throws])))
    for s in "LR":
        print(s, "reach max %.3f min %.3f" % (rig.reach[s].max(), rig.reach[s].min()), "at", t[int(np.argmax(rig.reach[s]))])

    R = np.concatenate([from_rotvec(m["global_orient"])[:, None], from_rotvec(m["body_pose"])], 1)
    W, P = fk(m["transl"], R)
    for s, name in (("L", "left_wrist"), ("R", "right_wrist")):
        tr_ = scene.tracks[s]
        want = tr_.wrist(t)
        err = np.linalg.norm((P[:, IDX[name]] - P[0, 0] + np.array([0, P[0, 0, 1], 0])) - want + np.array([rig_off(rig, t)[0], 0, rig_off(rig, t)[1]]), axis=-1)
        print(s, "wrist error vs plan: max %.4f  median %.4f" % (err.max(), np.median(err)))
        H = tr_.pos(t)
        vel = tr_.pos(t, 1)
        acc = tr_.pos(t, 2)
        print(s, "hand y %.3f..%.3f  x %.3f..%.3f  z %.3f..%.3f  speed max %.2f  acc max %.1f"
              % (H[:, 1].min() - FLOOR, H[:, 1].max() - FLOOR, H[:, 0].min(), H[:, 0].max(), H[:, 2].min(), H[:, 2].max(),
                 np.linalg.norm(vel, axis=-1).max(), np.linalg.norm(acc, axis=-1).max()))

    # does a hand ever leave its lane?  (a path bug that no target of evaluate.py shows: after the
    # last catch a hand once swung 27 cm across the body and back)
    anchor = plan.anchor(t)
    for s, sg in (("L", 1.0), ("R", -1.0)):
        side = sg * (scene.tracks[s].pos(t)[:, 0] - anchor[:, 0])
        i = int(np.argmin(side))
        j = int(np.argmax(side))
        print(s, "hand sideways from the pattern centre: %.3f (t=%.2f) .. %.3f (t=%.2f)" % (side[i], t[i], side[j], t[j]))

    # joint speed
    Rl = R
    d = to_rotvec(tr(Rl[:-1]) @ Rl[1:])
    sp = np.linalg.norm(d, axis=-1) * plan.fps / DEG
    worst = np.argsort(sp.max(0))[::-1][:6]
    print("fastest joints:", [(NAMES[j], round(float(sp[:, j].max())), round(float(t[int(np.argmax(sp[:, j]))]), 2)) for j in worst])
    for name in ("left_wrist", "right_wrist", "left_elbow", "right_elbow", "left_shoulder", "right_shoulder"):
        a = np.linalg.norm(to_rotvec(R[:, IDX[name]]), axis=-1) / DEG
        print("%-15s angle %.0f..%.0f" % (name, a.min(), a.max()))

    b = m["balls_transl"]
    n = b.shape[1]
    dmin = min(np.linalg.norm(b[:, i] - b[:, j], axis=-1).min() for i in range(n) for j in range(i))
    print("smallest ball distance %.4f (touching at %.4f)" % (dmin, 2 * plan.radius))


def rig_off(rig, t):
    P0, _ = rig.pose(t[:1], rig.shift[:1])
    return P0[0, 0], P0[0, 2]


if __name__ == "__main__":
    main()
