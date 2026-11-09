"""When do the worst moments of evaluated test tasks happen?

    python tools/when.py name [name ...]        (reads test_out/<name>.timeline.csv)

For each task: the stretches where forearm-in-body and hand-in-ball are high, with the plan's events.
"""
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from juggling.fingers import BallHand  # noqa: E402
from juggling.params import make_params  # noqa: E402
from juggling.schedule import Plan  # noqa: E402
from juggling.stance import Stance  # noqa: E402


def stretches(t, x, limit):
    over = x > limit
    e = np.nonzero(np.diff(np.concatenate([[0], over.astype(int), [0]])))[0]
    return [(round(float(t[a]), 2), round(float(t[min(b, len(t)) - 1]), 2), round(float(x[a:b].max()), 1)) for a, b in zip(e[::2], e[1::2])]


for name in sys.argv[1:]:
    rows = list(csv.DictReader(open("test_out/%s.timeline.csv" % name)))
    t = np.array([float(r["time_s"]) for r in rows])
    arm = np.array([float(r["arm_into_body_mm"]) for r in rows])
    hand = np.array([float(r["hand_into_ball_mm"]) for r in rows])
    task = json.load(open("test_tasks/%s.json" % name, encoding="utf-8"))
    q = make_params()
    p = Plan(task, q, Stance(q), BallHand(task["balls"]["radius"], q))
    print("==", name, {k: round(p.ev[k], 2) for k in ("first", "off", "up", "last", "down0", "touch")}, "beat %.3f throws %d" % (p.beat, p.n_throws))
    print("  arm in body >10:", stretches(t, arm, 10.0)[:12])
    print("  hand in ball >7:", stretches(t, hand, 7.0)[:12])
    print("  final hands:", [(s, [e.kind[0] + ("*" if e.seat != "one" else "") for e in p.events[s]][-3:]) for s in "LR"])
