"""Task file with balls -> motion."""
import math

import numpy as np

from .fingers import BallHand
from .params import make_params
from .pattern import Scene
from .rig import Rig
from .schedule import Plan
from .stance import Stance

KEYS = ("transl", "global_orient", "body_pose", "left_hand_pose", "right_hand_pose", "leye_pose", "reye_pose",
        "balls_transl")


def generate_juggling_motion(task, params=None):
    """Motion dict for a juggling task.  The Rig is returned under 'rig' for inspection."""
    q = make_params(params)
    hand = BallHand(float(task["balls"]["radius"]), q)
    plan = Plan(task, q, Stance(q), hand)
    scene = Scene(plan, hand)
    rig = Rig(plan, scene)
    start = task.get("start", {})
    t = np.arange(plan.frames) / float(plan.fps)
    motion = rig.generate(t, start.get("position", [0.0, 0.0]), math.radians(float(start.get("heading_deg", 0.0))))
    motion["rig"] = rig
    return motion


def save_juggling_motion(path, motion):
    arrays = {k: np.asarray(motion[k], dtype=np.float32) for k in KEYS}
    np.savez(path, fps=np.int64(motion["fps"]), **arrays)
