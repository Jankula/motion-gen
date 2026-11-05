"""Task file with an object -> motion."""
import numpy as np

from locomotion.body import calibrate
from locomotion.gait import make_params

from . import rig as rig_module
from . import script as script_module


def make_manipulation_params(overrides=None):
    q = dict(script_module.DEFAULTS)
    q.update(rig_module.DEFAULTS)
    if overrides:
        unknown = set(overrides) - set(q)
        if unknown:
            raise KeyError("unknown parameters: %s" % sorted(unknown))
        q.update(overrides)
    return q


def generate_box_motion(task, params=None, gait=None):
    """Motion dict for a pick-up, carry and put-down task (the Rig under 'rig' for inspection)."""
    fps = int(task.get("fps", 30))
    frames = int(task.get("frames", 300))
    p = make_params(gait)
    if p["c_walk"] is None or p["roll0"] is None:
        p["c_walk"], p["roll0"] = calibrate(gait)
    q = make_manipulation_params(params)
    script = script_module.compose(task, p, q)
    rig = rig_module.Rig(script, p, q, (-2.5, frames / fps + 2.5))
    rig.solve()
    motion = rig.generate(frames, fps)
    motion["rig"] = rig
    return motion


def save_box_motion(path, motion):
    arrays = {k: np.asarray(motion[k], dtype=np.float32)
              for k in ("transl", "global_orient", "body_pose", "left_hand_pose", "right_hand_pose",
                        "object_transl", "object_orient")}
    np.savez(path, fps=np.int64(motion["fps"]), **arrays)
