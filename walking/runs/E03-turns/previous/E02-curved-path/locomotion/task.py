"""Task files -> motion.

A task (see task.json) gives fps, number of frames, the start pose, the end state and a path
(segments or a polyline).  Supported now: start and end state "walking" (steady walking that is
already under way when the clip starts and continues after it ends).
"""
import json
import sys

import numpy as np

from .path import WalkLine
from .walker import Walker
from .gait import make_params


def load_task(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def generate_motion(task, params=None):
    """Return a dict with fps, transl, global_orient and body_pose for the task."""
    fps = int(task.get("fps", 30))
    frames = int(task.get("frames", 300))
    for key in ("start", "end"):
        state = task.get(key, {}).get("state", "walking")
        if state != "walking":
            print("warning: %s state %r is not supported yet; generating steady walking"
                  % (key, state), file=sys.stderr)
    if task.get("obstacles"):
        print("warning: obstacles are not avoided by the walker itself; the path is followed",
              file=sys.stderr)
    p = make_params(params)
    line = WalkLine.from_task(task, sigma=p["line_sigma"])
    walker = Walker(line, params, duration=frames / fps)
    motion = walker.generate(frames, fps)
    motion["walker"] = walker
    return motion


def save_motion(path, motion):
    np.savez(path, fps=np.int64(motion["fps"]),
             transl=np.asarray(motion["transl"], dtype=np.float32),
             global_orient=np.asarray(motion["global_orient"], dtype=np.float32),
             body_pose=np.asarray(motion["body_pose"], dtype=np.float32))
