"""Find what is behind some evaluate.py numbers, on a saved motion file.

    python tools/diagnose.py [motion.npz] [task.json]

Hand skin points inside the box (which point, when); fastest joints; elbows and knees bending
backwards; forearm/leg closeness per time window from the timeline.
"""
import csv
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from locomotion.rotations import from_rotvec, to_rotvec, tr  # noqa: E402
from locomotion.skeleton import BODY, IDX, J, NAMES, fk  # noqa: E402


def hand_points(side, W, P, pose):
    """World positions of the skin points of a hand: dict name -> (T, 3)."""
    pre = "left" if side == "L" else "right"
    H = BODY["hands"][pre]
    names = list(H["finger_joints"].keys())
    wi = IDX[pre + "_wrist"]
    T = len(P)
    Wj, Pj = {}, {}
    for i, n in enumerate(names):
        fj = H["finger_joints"][n]
        par = fj["parent"]
        rest = np.array(fj["rest"])
        R = from_rotvec(np.array(fj["relaxed_pose"]) + pose[:, i])
        if par == pre + "_wrist":
            Wp, Pp, rp = W[:, wi], P[:, wi], J[wi]
        else:
            Wp, Pp, rp = Wj[par], Pj[par], np.array(H["finger_joints"][par]["rest"])
        Pj[n] = Pp + np.einsum("tij,j->ti", Wp, rest - rp)
        Wj[n] = Wp @ R
    out = {}
    for k, v in H["skin_points"].items():
        x = np.array(v["rest"])
        j = v["joint"]
        if j == pre + "_wrist":
            out[k] = P[:, wi] + np.einsum("tij,j->ti", W[:, wi], x - J[wi])
        else:
            out[k] = Pj[j] + np.einsum("tij,j->ti", Wj[j], x - np.array(H["finger_joints"][j]["rest"]))
    return out


def main():
    mpath = sys.argv[1] if len(sys.argv) > 1 else "motion.npz"
    tpath = sys.argv[2] if len(sys.argv) > 2 else "task.json"
    m = np.load(os.path.join(ROOT, mpath))
    task = json.load(open(os.path.join(ROOT, tpath)))
    fps = int(m["fps"])
    T = len(m["transl"])
    R = np.empty((T, 22, 3, 3))
    R[:, 0] = from_rotvec(m["global_orient"].astype(float))
    R[:, 1:] = from_rotvec(m["body_pose"].astype(float).reshape(T, 21, 3))
    W, P = fk(m["transl"].astype(float), R)
    size = np.array(task["object"]["size"], dtype=float)
    Rb = from_rotvec(m["object_orient"].astype(float))
    ob = m["object_transl"].astype(float)
    print("hand skin points inside the box (depth mm, time):")
    for side, key in (("L", "left_hand_pose"), ("R", "right_hand_pose")):
        pts = hand_points(side, W, P, m[key].astype(float).reshape(T, 15, 3))
        rows = []
        for k, x in pts.items():
            loc = np.einsum("tji,tj->ti", Rb, x - ob)
            depth = np.min(0.5 * size - np.abs(loc), axis=1)
            i = int(np.argmax(depth))
            rows.append((depth[i] * 1000.0, i / fps, k))
        rows.sort(reverse=True)
        print("  ", [(round(a, 1), round(b, 2), c.replace("left_", "").replace("right_", "")) for a, b, c in rows[:7]])
    print("fastest joints (deg/s, time):")
    dR = tr(R[:-1]) @ R[1:]
    sp = np.degrees(np.linalg.norm(to_rotvec(dR), axis=-1)) * fps
    top = np.argsort(sp.max(0))[::-1][:6]
    print("  ", [(NAMES[j], round(float(sp[:, j].max())), round(int(np.argmax(sp[:, j])) / fps, 2)) for j in top])
    print("elbow and knee rotation vectors, most backward (deg, time):")
    for name, ax, sg in (("left_elbow", 1, -1), ("right_elbow", 1, 1), ("left_knee", 0, 1), ("right_knee", 0, 1)):
        rv = np.degrees(to_rotvec(R[:, IDX[name]]))[:, ax] * sg
        i = int(np.argmin(rv))
        print("   %-12s %.1f at %.2f" % (name, rv[i], i / fps))
    for name, a, b, c in (("left elbow", "left_shoulder", "left_elbow", "left_wrist"),
                          ("right elbow", "right_shoulder", "right_elbow", "right_wrist"),
                          ("left knee", "left_hip", "left_knee", "left_ankle"),
                          ("right knee", "right_hip", "right_knee", "right_ankle")):
        u = P[:, IDX[b]] - P[:, IDX[a]]
        v = P[:, IDX[c]] - P[:, IDX[b]]
        ang = np.degrees(np.arccos(np.clip(np.sum(u * v, -1) / np.linalg.norm(u, axis=-1) / np.linalg.norm(v, axis=-1), -1, 1)))
        print("   %-12s bone angle min %.1f at %.2f, max %.1f" % (name, ang.min(), np.argmin(ang) / fps, ang.max()))
    from scipy.ndimage import gaussian_filter1d
    v = np.gradient(ob, 1.0 / fps, axis=0)
    a = np.linalg.norm(np.gradient(gaussian_filter1d(v, 2.5, axis=0, mode="nearest"), 1.0 / fps, axis=0), axis=1)
    top = [int(i) for i in np.argsort(a)[::-1][:1]]
    print("box acceleration: peak %.2f at %.2f; per second:" % (a.max(), top[0] / fps),
          [(i, round(float(a[i * fps:(i + 1) * fps].max()), 1)) for i in range(T // fps)])
    tl = os.path.join(ROOT, os.path.splitext(mpath)[0] + ".timeline.csv")
    if os.path.exists(tl):
        rows = list(csv.DictReader(open(tl, encoding="utf-8")))
        v = np.array([float(r["arm_into_body_mm"]) for r in rows])
        print("arm into body per second:", [(i, round(float(v[i * fps:(i + 1) * fps].max()), 1)) for i in range(T // fps)
                                            if v[i * fps:(i + 1) * fps].max() > 3])


if __name__ == "__main__":
    main()
