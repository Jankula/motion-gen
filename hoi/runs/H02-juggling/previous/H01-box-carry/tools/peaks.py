"""When do the contact numbers peak, relative to the events of the script?

    python tools/peaks.py [name ...]     (names in test_out/; 'motion' = the main task)
"""
import csv
import glob
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from locomotion import load_task  # noqa: E402
from locomotion.body import calibrate  # noqa: E402
from locomotion.gait import make_params  # noqa: E402
from manipulation.script import compose  # noqa: E402
from manipulation.task import make_manipulation_params  # noqa: E402


def main():
    names = sys.argv[1:] or ["motion"] + [os.path.splitext(os.path.basename(f))[0]
                                          for f in sorted(glob.glob(os.path.join(ROOT, "test_tasks", "*.json")))]
    p = make_params()
    p["c_walk"], p["roll0"] = calibrate()
    q = make_manipulation_params()
    for name in names:
        task = os.path.join(ROOT, "task.json") if name == "motion" else os.path.join(ROOT, "test_tasks", name + ".json")
        tl = os.path.join(ROOT, "motion.timeline.csv") if name == "motion" else os.path.join(ROOT, "test_out", name + ".timeline.csv")
        s = compose(load_task(task), p, q)
        ev = s.ev
        rows = list(csv.DictReader(open(tl, encoding="utf-8")))
        t = np.array([float(r["time_s"]) for r in rows])
        print("%s: tempo %.2f k=%d m=%d" % (name, s.tempo, s.hold["k"], s.hold["m"]),
              {k: round(ev[k], 1) for k in ("stop1", "contact", "lift0", "lift1", "walk2", "stop2", "low0", "touch", "away", "rise1", "still")})
        for col in ("body_into_box_mm", "arm_into_body_mm"):
            v = np.array([float(r[col]) for r in rows])
            parts = []
            for a, b, lab in ((0, ev["contact"], "approach"), (ev["contact"], ev["lift0"], "grip"), (ev["lift0"], ev["lift1"], "lift"),
                              (ev["lift1"], ev["stop2"], "carry"), (ev["stop2"], ev["touch"], "lower"), (ev["touch"], 99, "after")):
                m = (t >= a) & (t < b)
                if m.any() and v[m].max() > 1.0:
                    i = int(np.argmax(np.where(m, v, -1)))
                    parts.append("%s %.0f@%.2f" % (lab, v[i], t[i]))
            print("   %-18s %s" % (col, parts))


if __name__ == "__main__":
    main()
