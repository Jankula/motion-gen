"""Generate the motion for a task file.

    python make_motion.py <task.json> <output.npz>

Deterministic; uses only numpy and scipy and the packages next to this file.  A task with balls goes
to juggling/, a task with an object to manipulation/, a walking task to locomotion/.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from juggling import generate_juggling_motion, save_juggling_motion  # noqa: E402
from locomotion import generate_motion, load_task, save_motion  # noqa: E402
from manipulation import generate_box_motion, save_box_motion  # noqa: E402


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip())
        return 2
    t0 = time.perf_counter()
    task = load_task(argv[1])
    if "balls" in task:
        motion = generate_juggling_motion(task)
        save_juggling_motion(argv[2], motion)
    elif "object" in task:
        motion = generate_box_motion(task)
        save_box_motion(argv[2], motion)
    else:
        motion = generate_motion(task)
        save_motion(argv[2], motion)
    n = len(motion["transl"])
    print("wrote %s: %d frames at %d fps (%.1f s of motion) in %.2f s"
          % (argv[2], n, motion["fps"], n / motion["fps"], time.perf_counter() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
