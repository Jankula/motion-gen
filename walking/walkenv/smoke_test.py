"""Render a short, deliberately non-walking motion to check the pipeline and its conventions.

    python -m walkenv.smoke_test

Writes runs/_smoke/. What you should see (3 s):
  - arms lowered from the T-pose to the sides,
  - the LEFT knee lifting forward (near side in left.mp4, far side in right.mp4),
  - the RIGHT elbow bending, forearm forward,
  - the body gliding slowly forward along +Z; "front" shows the face throughout,
  - the feet on the floor at the start (not floating, not sunk in).
It is not a walk on purpose: nothing here should leak motion knowledge to the agent.
"""
import numpy as np

from .motion_format import OPTIONAL, REQUIRED
from .paths import RUNS_DIR
from .render import render

FPS = 30
FRAMES = 90
L_HIP, L_KNEE, L_SHOULDER, R_SHOULDER, R_ELBOW = 0, 3, 15, 16, 18  # indices into body_pose (joint index - 1)


def smoke_motion():
    s = np.linspace(0.0, 1.0, FRAMES)
    ramp = 0.5 - 0.5 * np.cos(np.pi * s)  # smooth 0 -> 1
    m = {key: np.zeros((FRAMES, *shape), np.float32) for key, shape in {**REQUIRED, **OPTIONAL}.items()}
    m["fps"] = FPS
    m["transl"][:, 2] = 0.3 * s * FRAMES / FPS
    m["body_pose"][:, L_SHOULDER, 2] = -np.radians(70) * ramp
    m["body_pose"][:, R_SHOULDER, 2] = np.radians(70) * ramp
    m["body_pose"][:, L_HIP, 0] = -np.radians(60) * ramp  # negative about +X: thigh swings forward (+Z)
    m["body_pose"][:, L_KNEE, 0] = np.radians(70) * ramp  # positive about +X: shank swings back
    m["body_pose"][:, R_ELBOW, 1] = np.radians(80) * ramp  # positive about +Y: right forearm swings forward
    return m


def main():
    out = RUNS_DIR / "_smoke"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "motion.npz"
    np.savez(path, **smoke_motion())
    for written in render(path, out / "videos", sheet_start=0.0, sheet_duration=3.0):
        print(written)


if __name__ == "__main__":
    main()
