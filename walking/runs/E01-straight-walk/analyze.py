"""Numerical checks of motion.npz (my own verification tool; not needed to generate the motion).

Loads the motion exactly as stored, runs the forward kinematics from SMPLX_INTERFACE.md and
reports foot/floor contact, sliding, clearance, joint-angle curves, speed and limb distances.
"""
import sys

import numpy as np
from scipy.spatial.transform import Rotation as Rot

import generate_motion as gm

DEG = gm.DEG
J, FLOOR = gm.J, gm.FLOOR


def load(path="motion.npz"):
    d = np.load(path)
    T = len(d["transl"])
    bp = d["body_pose"].reshape(T, 21, 3).astype(float)
    R = np.zeros((T, 22, 3, 3))
    R[:, 0] = Rot.from_rotvec(d["global_orient"].astype(float)).as_matrix()
    R[:, 1:] = Rot.from_rotvec(bp.reshape(-1, 3)).as_matrix().reshape(T, 21, 3, 3)
    return d["transl"].astype(float), R, int(d["fps"])


def all_fk(transl, R):
    T = len(transl)
    W = np.zeros((T, 22, 3, 3))
    P = np.zeros((T, 22, 3))
    for f in range(T):
        w, p = gm.fk(transl[f], list(R[f]))
        W[f] = np.stack(w)
        P[f] = p
    return W, P


def sole_points(side):
    """Approximate sole/heel surface points in the rest pose: (foot-segment pts, toe pts)."""
    s = 1.0 if side == "L" else -1.0
    hx = abs(gm.LM["left_heel_bottom"][0])
    foot = []
    c = np.array([hx, FLOOR + gm.HEEL_R, gm.HEEL_Z])
    for beta in np.linspace(-95, 0, 12) * DEG:          # rounded back of the heel
        for dx in (-0.02, 0.0, 0.02):
            foot.append(c + np.array([dx, -gm.HEEL_R * np.cos(beta), gm.HEEL_R * np.sin(beta)]))
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
    toe.append(gm.LM["left_toe_tip"].copy())
    foot, toe = np.array(foot), np.array(toe)
    foot[:, 0] *= s
    toe[:, 0] *= s
    return foot, toe


def main(path="motion.npz"):
    transl, R, fps = load(path)
    T = len(transl)
    W, P = all_fk(transl, R)
    t = np.arange(T) / fps
    print(f"frames {T} fps {fps}; transl[0] = {np.round(transl[0], 4)}")

    # ---------------- global progression
    pel = P[:, 0]
    vz = np.gradient(pel[:, 2], 1 / fps)
    print(f"pelvis: mean speed {(pel[-1, 2] - pel[0, 2]) / t[-1]:.3f} m/s, "
          f"vz range {vz.min():.3f}..{vz.max():.3f}, "
          f"y range {pel[:, 1].min():.4f}..{pel[:, 1].max():.4f} (p2p {np.ptp(pel[:, 1]) * 100:.1f} cm), "
          f"x range {pel[:, 0].min():.3f}..{pel[:, 0].max():.3f}")

    # ---------------- feet
    for side in ("L", "R"):
        sd = gm.SIDES[side]
        fpts, tpts = sole_points(side)
        ia, it = sd["ankle"], sd["toe"]
        fw = np.einsum("fij,nj->fni", W[:, ia], fpts - J[ia]) + P[:, ia][:, None]
        tw = np.einsum("fij,nj->fni", W[:, it], tpts - J[it]) + P[:, it][:, None]
        allp = np.concatenate([fw, tw], 1)
        h = allp[..., 1] - FLOOR
        minh = h.min(1)
        print(f"\n[{side}] lowest sole point: min {minh.min() * 1000:.1f} mm, "
              f"frames below -2 mm: {(minh < -0.002).sum()}, below -5 mm: {(minh < -0.005).sum()}")
        # sliding: horizontal motion of points that stay on the floor (< 2 mm) in two frames
        on = h < 0.002
        both = on[1:] & on[:-1]
        disp = np.linalg.norm((allp[1:] - allp[:-1])[..., [0, 2]], axis=-1)
        sl = np.where(both, disp, 0.0)
        print(f"[{side}] max horizontal motion of a floor-contact point between frames: "
              f"{sl.max() * 1000:.2f} mm (=> {sl.max() * fps:.3f} m/s)")
        # swing clearance (frames where no point is in contact)
        contact = minh < 0.004
        print(f"[{side}] contact frames {contact.sum()} / {T}")
        heel_h = fw[:, :36, 1].min(1) - FLOOR
        toe_h = tw[..., 1].min(1) - FLOOR
        line = " ".join(f"{x * 100:4.1f}" for x in minh[:40])
        print(f"[{side}] min sole height (cm), first 40 frames:\n  {line}")
        line = " ".join(f"{x * 100:4.1f}" for x in toe_h[:40])
        print(f"[{side}] toe height (cm):\n  {line}")
        line = " ".join(f"{x * 100:4.1f}" for x in heel_h[:40])
        print(f"[{side}] heel height (cm):\n  {line}")

    # ---------------- joint angles
    def ang(j):
        return np.array([gm.euler(R[f, j]) for f in range(T)]) / DEG

    print("\nper-frame sagittal angles (deg) for the first 36 frames")
    for side in ("L", "R"):
        sd = gm.SIDES[side]
        hip, knee, ank, toe = ang(sd["hip"]), ang(sd["knee"]), ang(sd["ankle"]), ang(sd["toe"])
        print(f"[{side}] hip flex : " + " ".join(f"{-x:5.1f}" for x in hip[:36, 0]))
        print(f"[{side}] hip add  : " + " ".join(f"{x * (-sd['sign']):5.1f}" for x in hip[:36, 1]))
        print(f"[{side}] hip rot  : " + " ".join(f"{x * sd['sign']:5.1f}" for x in hip[:36, 2]))
        print(f"[{side}] knee     : " + " ".join(f"{x:5.1f}" for x in knee[:36, 0]))
        print(f"[{side}] knee other: max |z|,|y| {np.abs(knee[:, 1]).max():.2f} {np.abs(knee[:, 2]).max():.2f}")
        print(f"[{side}] ank dors : " + " ".join(f"{-x:5.1f}" for x in ank[:36, 0]))
        print(f"[{side}] ank inv  : " + " ".join(f"{x:5.1f}" for x in ank[:36, 1]))
        print(f"[{side}] toe ext  : " + " ".join(f"{-x:5.1f}" for x in toe[:36, 0]))
        print(f"[{side}] ranges: hip flex {(-hip[:, 0]).min():.1f}..{(-hip[:, 0]).max():.1f}, "
              f"knee {knee[:, 0].min():.1f}..{knee[:, 0].max():.1f}, "
              f"ankle {(-ank[:, 0]).min():.1f}..{(-ank[:, 0]).max():.1f}")

    # ---------------- smoothness: max angular acceleration per joint
    print("\nmax joint angular speed / acceleration (deg/s, deg/s^2)")
    for j in range(22):
        rv = np.array([Rot.from_matrix(R[f, j]).as_rotvec() for f in range(T)])
        v = np.linalg.norm(np.diff(rv, axis=0), axis=1) * fps / DEG
        a = np.linalg.norm(np.diff(rv, 2, axis=0), axis=1) * fps * fps / DEG
        print(f"  {gm.NAMES[j]:15s} {v.max():7.1f} {a.max():9.1f}")

    # ---------------- limb clearances
    def seg_dist(p1, p2, q1, q2):
        # min distance between segments p1p2 and q1q2 (sampled)
        s = np.linspace(0, 1, 21)
        A = p1[None] + s[:, None] * (p2 - p1)[None]
        B = q1[None] + s[:, None] * (q2 - q1)[None]
        return np.min(np.linalg.norm(A[:, None] - B[None], axis=-1))

    I = gm.IDX
    knee_d = [seg_dist(P[f, I["left_knee"]], P[f, I["left_ankle"]], P[f, I["right_knee"]], P[f, I["right_ankle"]]) for f in range(T)]
    thigh_d = [seg_dist(P[f, I["left_hip"]], P[f, I["left_knee"]], P[f, I["right_hip"]], P[f, I["right_knee"]]) for f in range(T)]
    print(f"\nmin shank-shank axis distance {min(knee_d) * 100:.1f} cm; thigh-thigh {min(thigh_d) * 100:.1f} cm")
    ank_dx = np.abs(P[:, I["left_ankle"], 0] - P[:, I["right_ankle"], 0])
    print(f"ankle lateral separation min {ank_dx.min() * 100:.1f} cm (at frame {ank_dx.argmin()})")

    # arms vs body (in pelvis frame): wrist and elbow lateral distance from the body midline
    for side in ("left", "right"):
        loc = np.einsum("fji,fj->fi", W[:, 0], P[:, I[side + "_wrist"]] - P[:, 0])
        loce = np.einsum("fji,fj->fi", W[:, 0], P[:, I[side + "_elbow"]] - P[:, 0])
        print(f"{side} wrist in pelvis frame: |x| {np.abs(loc[:, 0]).min():.3f}..{np.abs(loc[:, 0]).max():.3f}, "
              f"y {loc[:, 1].min():.3f}..{loc[:, 1].max():.3f}, z {loc[:, 2].min():.3f}..{loc[:, 2].max():.3f}; "
              f"elbow |x| min {np.abs(loce[:, 0]).min():.3f}")

    # head stability
    hd = P[:, I["head"]]
    print(f"head y p2p {np.ptp(hd[:, 1]) * 100:.1f} cm, x p2p {np.ptp(hd[:, 0]) * 100:.1f} cm")
    return P, W, R


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "motion.npz")
