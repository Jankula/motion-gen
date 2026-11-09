"""Generate and evaluate all test tasks (a few at a time) and print the failed targets.

    python tools/eval_all.py [name ...]

Motions and reports go to test_out/.
"""
import glob
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

PY = sys.executable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = "test_out"
INFO = ("lowest_pelvis", "speed_carrying", "balance_worst", "max_joint_speed", "touchdown_speed", "body_depth_max",
        "hand_depth_max", "arm_depth_max")


def run(task):
    name = os.path.splitext(os.path.basename(task))[0]
    motion = os.path.join(OUT, name + ".npz")
    g = subprocess.run([PY, "make_motion.py", task, motion], cwd=ROOT, capture_output=True, text=True)
    if g.returncode:
        return name, "GENERATION FAILED\n" + g.stderr[-1500:]
    gen = g.stdout.strip().splitlines()
    e = subprocess.run([PY, "evaluate.py", motion, task], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    try:
        m = json.load(open(os.path.join(ROOT, OUT, name + ".metrics.json"), encoding="utf-8"))["metrics"]
    except OSError:
        return name, "EVALUATION FAILED\n" + e.stderr[-1500:]
    bad = ["%s=%s%s (%s)" % (x["key"], x["value"], x["unit"], x["target"]) for x in m if x["ok"] is False]
    n_ok = sum(1 for x in m if x["ok"] is True)
    info = {x["key"]: x["value"] for x in m if x["key"] in INFO}
    return name, "%d ok, %d failed: %s\n    %s\n    %s" % (n_ok, len(bad), bad, info, " | ".join(gen))


def main():
    os.makedirs(os.path.join(ROOT, OUT), exist_ok=True)
    tasks = sorted(glob.glob("test_tasks/*.json", root_dir=ROOT))
    if len(sys.argv) > 1:
        tasks = [t for t in tasks if os.path.splitext(os.path.basename(t))[0] in sys.argv[1:]]
    with ThreadPoolExecutor(3) as ex:
        for name, res in ex.map(run, tasks):
            print("%-16s %s" % (name, res), flush=True)


if __name__ == "__main__":
    main()
