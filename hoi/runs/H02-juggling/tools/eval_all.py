"""Generate and evaluate all test tasks into test_out/ and list the targets they miss.

    python tools/eval_all.py [name ...]        # default: all of test_tasks/
    python tools/eval_all.py --old             # the earlier box tasks and a walking task: do they still run?
"""
import concurrent.futures as cf
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = "C:/Projects/motion-gen/walking/.venv/Scripts/python.exe"
OUT = os.path.join(HERE, "test_out")


def run(path):
    name = os.path.splitext(os.path.basename(path))[0]
    npz = os.path.join(OUT, name + ".npz")
    t0 = time.perf_counter()
    r = subprocess.run([PY, "make_motion.py", path, npz], cwd=HERE, capture_output=True, text=True)
    gen = time.perf_counter() - t0
    if r.returncode != 0:
        return name, gen, None, "GENERATION FAILED\n" + r.stderr[-1500:]
    c = subprocess.run([PY, "check_format.py", npz, path], cwd=HERE, capture_output=True, text=True)
    if not c.stdout.startswith("OK"):
        return name, gen, None, "FORMAT: " + c.stdout
    e = subprocess.run([PY, "evaluate.py", os.path.relpath(npz, HERE), os.path.relpath(path, HERE)], cwd=HERE,
                       capture_output=True, text=True, encoding="utf-8")
    if e.returncode != 0:
        return name, gen, None, "EVALUATE FAILED\n" + (e.stderr or e.stdout)[-1500:]
    m = json.load(open(os.path.join(OUT, name + ".metrics.json"), encoding="utf-8"))["metrics"]
    bad = [x for x in m if x.get("ok") is False]
    total = sum(1 for x in m if x.get("target"))
    return name, gen, (total - len(bad), total), "; ".join("%s %s%s (%s)" % (x["label"], x["value"], x["unit"], x["target"]) for x in bad)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    args = sys.argv[1:]
    if args == ["--old"]:
        paths = sorted(glob.glob(os.path.join(HERE, "previous", "H01-box-carry", "test_tasks", "*.json")))[:4]
    elif args:
        paths = [os.path.join(HERE, "test_tasks", a + ".json") for a in args]
    else:
        paths = [p for p in sorted(glob.glob(os.path.join(HERE, "test_tasks", "*.json")))
                 if "balls" in json.load(open(p, encoding="utf-8"))]
    with cf.ThreadPoolExecutor(4) as pool:
        for name, gen, score, note in pool.map(run, paths):
            s = "%d/%d" % score if score else "--"
            print("%-20s %6.1f s  %-7s %s" % (name, gen, s, note or "all targets met"), flush=True)


if __name__ == "__main__":
    main()
