"""Numerical checks of a motion file (my own verification tool; not needed to generate motion).

    python analyze.py motion.npz task.json [--verbose]

Runs the forward kinematics from SMPLX_INTERFACE.md on the stored file and reports foot/floor
contact (sampled sole points), sliding, swing clearance, joint ranges and speeds, distances
between the feet and legs, pelvis path deviation, heading, speed and stillness.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from locomotion.legs import HEEL_R, HEEL_Z  # noqa: E402
from locomotion.path import WalkLine  # noqa: E402
from locomotion.rotations import DEG, euler_xzy, from_rotvec  # noqa: E402
from locomotion.skeleton import FLOOR, IDX, J, LM, NAMES, fk  # noqa: E402
from locomotion.task import load_task  # noqa: E402


def load(path):
    d = np.load(path)
    T = len(d["transl"])
    R = np.zeros((T, 22, 3, 3))
    R[:, 0] = from_rotvec(d["global_orient"].astype(float))
    R[:, 1:] = from_rotvec(d["body_pose"].reshape(T, 21, 3).astype(float))
    return d["transl"].astype(float), R, int(d["fps"])


def sole_points(side):
    """Approximate sole/heel surface points in the rest pose: (foot-segment pts, toe pts)."""
    s = 1.0 if side == "L" else -1.0
    hx = abs(LM["left_heel_bottom"][0])
    foot = []
    c = np.array([hx, FLOOR + HEEL_R, HEEL_Z])
    for beta in np.linspace(-95, 0, 12) * DEG:          # rounded back of the heel
        for dx in (-0.02, 0.0, 0.02):
            foot.append(c + np.array([dx, -HEEL_R * np.cos(beta), HEEL_R * np.sin(beta)]))
    for z in np.linspace(-0.08, 0.058, 8):               # flat sole of the rear/mid foot
        w = (z + 0.08) / 0.138
        x0, x1 = 0.075 + (0.066 - 0.075) * w, 0.122 + (0.160 - 0.122) * w
        for x in np.linspace(x0, x1, 4):
            foot.append(np.array([x, FLOOR, z]))
    toe = []
    for z in (0.07, 0.09, 0.11, 0.125):
        w = (z - 0.07) / 0.055
        x0, x1 = 0.068 + 0.01 * w, 0.155 - 0.025 * w
        for x in np.linspace(x0, x1, 4):
            toe.append(np.array([x, FLOOR + 0.001, z]))
    toe.append(LM["left_toe_tip"].copy())
    foot, toe = np.array(foot), np.array(toe)
    foot[:, 0] *= s
    toe[:, 0] *= s
    return foot, toe


def seg_dist(p1, p2, q1, q2):
    s = np.linspace(0, 1, 15)
    A = p1[:, None] + s[None, :, None] * (p2 - p1)[:, None]
    B = q1[:, None] + s[None, :, None] * (q2 - q1)[:, None]
    return np.min(np.linalg.norm(A[:, :, None] - B[:, None, :], axis=-1), axis=(1, 2))


def main(path, task_path, verbose=False):
    transl, R, fps = load(path)
    T = len(transl)
    W, P = fk(transl, R)
    task = load_task(task_path)
    print(f"{path}: {T} frames at {fps} fps")

    # ---------------- path
    raw = WalkLine.from_task(task, sigma=0.0)
    pel = P[:, 0, [0, 2]]
    sm = (raw.s > -0.5) & (raw.s < raw.s_end + 0.01)
    pts = raw.xz[sm]
    dist = np.min(np.linalg.norm(pel[:, None] - pts[None, ::2], axis=-1), axis=1)
    print(f"pelvis start ({pel[0, 0]:.3f}, {pel[0, 1]:.3f}) end ({pel[-1, 0]:.3f}, {pel[-1, 1]:.3f}); "
          f"path deviation mean {dist.mean() * 100:.1f} cm, max {dist.max() * 100:.1f} cm (frame {dist.argmax()})")
    fwd = W[:, 0, :, 2]
    yaw = np.unwrap(np.arctan2(fwd[:, 0], fwd[:, 2]))
    print(f"pelvis yaw start {yaw[0] / DEG:.1f} end {yaw[-1] / DEG:.1f} deg")
    vel = np.gradient(pel, 1 / fps, axis=0)
    spd = np.linalg.norm(vel, axis=1)
    k = int(fps)
    sm_spd = np.convolve(spd, np.ones(k) / k, mode="valid")
    print(f"speed (1 s average): {sm_spd.min():.2f}..{sm_spd.max():.2f} m/s, mean {spd.mean():.2f}; "
          f"max speed first/last 0.5 s: {spd[:fps // 2].max() * 100:.1f} / {spd[-fps // 2:].max() * 100:.1f} cm/s")
    if verbose:
        print("  per 0.5 s: " + " ".join(f"{x:.2f}" for x in spd[::fps // 2]))

    # ---------------- feet
    feet_world = {}
    for side in ("L", "R"):
        pre = "left_" if side == "L" else "right_"
        fpts, tpts = sole_points(side)
        ia, it = IDX[pre + "ankle"], IDX[pre + "foot"]
        fw = np.einsum("fij,nj->fni", W[:, ia], fpts - J[ia]) + P[:, ia][:, None]
        tw = np.einsum("fij,nj->fni", W[:, it], tpts - J[it]) + P[:, it][:, None]
        allp = np.concatenate([fw, tw], 1)
        feet_world[side] = allp
        h = allp[..., 1] - FLOOR
        minh = h.min(1)
        on = h < 0.002
        both = on[1:] & on[:-1]
        disp = np.linalg.norm((allp[1:] - allp[:-1])[..., [0, 2]], axis=-1)
        sl = np.where(both, disp, 0.0)
        contact = minh < 0.004
        runs, cur = [], []
        for f in range(T):
            if not contact[f]:
                cur.append(minh[f])
            elif cur:
                n = len(cur)
                mid = cur[int(0.2 * n):max(int(0.8 * n), int(0.2 * n) + 1)]
                runs.append(min(mid))
                cur = []
        clr = " ".join(f"{x * 100:.1f}" for x in runs)
        fs = int(np.unravel_index(np.argmax(sl), sl.shape)[0])
        csp = disp[both] * fps * 100
        print(f"[{side}] contact point speed median {np.median(csp):.2f} cm/s, p95 {np.percentile(csp, 95):.2f}, "
              f"frames with >3 cm/s: {np.unique(np.nonzero(np.where(both, disp * fps * 100, 0) > 3)[0]).tolist()[:40]}")
        print(f"[{side}] lowest sole point {minh.min() * 1000:.1f} mm; max floor-point slip "
              f"{sl.max() * 1000:.2f} mm/frame (frame {fs}); contact frames {contact.sum()}/{T}; "
              f"swing min clearance (cm): {clr}")
    # distance between the two feet (sampled sole points, horizontal)
    dL, dR = feet_world["L"], feet_world["R"]
    dd = np.min(np.linalg.norm(dL[:, :, None, :] - dR[:, None, :, :], axis=-1), axis=(1, 2))
    print(f"closest foot-foot sole points {dd.min() * 100:.1f} cm (frame {dd.argmin()})")

    # ---------------- joint angles
    for side in ("L", "R"):
        pre = "left_" if side == "L" else "right_"
        sg = 1.0 if side == "L" else -1.0
        hip = euler_xzy(R[:, IDX[pre + "hip"]]) / DEG
        knee = euler_xzy(R[:, IDX[pre + "knee"]]) / DEG
        ank = euler_xzy(R[:, IDX[pre + "ankle"]]) / DEG
        toe = euler_xzy(R[:, IDX[pre + "foot"]]) / DEG
        print(f"[{side}] hip flex {(-hip[:, 0]).min():.1f}..{(-hip[:, 0]).max():.1f}, "
              f"abd {(sg * hip[:, 1]).min():.1f}..{(sg * hip[:, 1]).max():.1f}, "
              f"int.rot {(-sg * hip[:, 2]).min():.1f}..{(-sg * hip[:, 2]).max():.1f}; "
              f"knee {knee[:, 0].min():.1f}..{knee[:, 0].max():.1f}; "
              f"ankle dorsi {(-ank[:, 0]).min():.1f}..{(-ank[:, 0]).max():.1f}, "
              f"inv {(sg * ank[:, 1]).min():.1f}..{(sg * ank[:, 1]).max():.1f}, "
              f"rot {(sg * ank[:, 2]).min():.1f}..{(sg * ank[:, 2]).max():.1f}; "
              f"toe ext {(-toe[:, 0]).min():.1f}..{(-toe[:, 0]).max():.1f}")

    # ---------------- angular speed
    sp = []
    for j in range(22):
        Rr = np.einsum("fji,fjk->fik", R[:-1, j], R[1:, j])
        ang = np.arccos(np.clip((np.trace(Rr, axis1=1, axis2=2) - 1) / 2, -1, 1))
        sp.append((ang.max() * fps / DEG, NAMES[j], int(ang.argmax())))
    sp.sort(reverse=True)
    print("fastest joints (deg/s): " + ", ".join(f"{n} {v:.0f} @{f}" for v, n, f in sp[:5]))

    # ---------------- leg clearances
    I = IDX
    shank = seg_dist(P[:, I["left_knee"]], P[:, I["left_ankle"]], P[:, I["right_knee"]], P[:, I["right_ankle"]])
    thigh = seg_dist(P[:, I["left_hip"]], P[:, I["left_knee"]], P[:, I["right_hip"]], P[:, I["right_knee"]])
    ank = np.linalg.norm(P[:, I["left_ankle"]] - P[:, I["right_ankle"]], axis=1)
    print(f"min shank-shank axis distance {shank.min() * 100:.1f} cm (frame {shank.argmin()}), "
          f"thigh-thigh {thigh.min() * 100:.1f} cm, ankle-ankle {ank.min() * 100:.1f} cm (frame {ank.argmin()})")
    for side in ("left", "right"):
        loc = np.einsum("fji,fj->fi", W[:, 0], P[:, I[side + "_wrist"]] - P[:, 0])
        print(f"{side} wrist in pelvis frame: |x| {np.abs(loc[:, 0]).min():.3f}..{np.abs(loc[:, 0]).max():.3f}, "
              f"z {loc[:, 2].min():.3f}..{loc[:, 2].max():.3f}")
    hd = P[:, I["head"]]
    print(f"pelvis height {P[:, 0, 1].min() - FLOOR:.3f}..{P[:, 0, 1].max() - FLOOR:.3f} m; "
          f"head height p2p {np.ptp(hd[:, 1]) * 100:.1f} cm")
    return P, W, R


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "motion.npz", args[1] if len(args) > 1 else "task.json",
         "--verbose" in sys.argv)
