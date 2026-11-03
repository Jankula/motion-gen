"""Generate and evaluate several task files, then print a one-line summary of each from the
evaluate.py metrics (my own checking tool).

    python tools/eval_all.py test_tasks/gap-*.json

Motions go to test_out/<name>.npz, metrics to test_out/<name>.metrics.json."""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
paths = []
for a in sys.argv[1:]:
    paths += sorted(glob.glob(a)) or [a]
os.makedirs(os.path.join(HERE, "test_out"), exist_ok=True)
for path in paths:
    name = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join("test_out", name + ".npz")
    gen = subprocess.run([PY, "make_motion.py", path, out], cwd=HERE, capture_output=True, text=True)
    msg = (gen.stdout.strip().splitlines() or [""])[-1]
    warn = " ".join(l for l in gen.stderr.splitlines() if "warning" in l)
    subprocess.run([PY, "evaluate.py", out, path], cwd=HERE, capture_output=True)
    with open(os.path.join(HERE, "test_out", name + ".metrics.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    vals = ["%s %.1f" % (m["key"].split(":", 1)[1], m["value"]) for m in d["metrics"]
            if m["key"].startswith("clearance:")]
    keys = ("contact_speed_p95", "max_joint_speed", "path_deviation_max", "end_position_error")
    vals += ["%s %s" % (m["key"], m["value"]) for m in d["metrics"] if m["key"] in keys]
    bad = [m["key"] for m in d["metrics"] if m.get("ok") is False]
    print("%-18s %s | %s | %s %s" % (name, msg.split(" in ")[-1], ", ".join(vals),
                                     ("FAILED %s" % bad) if bad else "all targets met", warn))
