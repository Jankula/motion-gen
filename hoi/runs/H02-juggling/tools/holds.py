"""Where do hand skin and held balls disagree?  Reads <motion>.metrics.json and .timeline.csv.

    python tools/holds.py [motion name]
"""
import csv
import json
import sys

import numpy as np

name = sys.argv[1] if len(sys.argv) > 1 else "motion"
sys.stdout.reconfigure(encoding="utf-8")
m = json.load(open(name + ".metrics.json", encoding="utf-8"))
for x in m["metrics"]:
    if x["key"] in ("hand_depth_max", "frames_unsupported", "contact_width_min", "body_depth_max", "arm_into_body",
                    "gravity_error", "flight_fit_mm"):
        print(x["key"], x["value"], x["unit"], "|", x["meaning"])
rows = list(csv.DictReader(open(name + ".timeline.csv")))
t = np.array([float(r["time_s"]) for r in rows])
depth = np.array([float(r["hand_into_ball_mm"]) for r in rows])
print("hand into ball: median %.1f mm, 90%% %.1f mm, max %.1f at %.2f s" % (np.median(depth), np.percentile(depth, 90), depth.max(), t[int(np.argmax(depth))]))
over = depth > 8
print("frames over 8 mm:", int(over.sum()))
edges = np.nonzero(np.diff(np.concatenate([[0], over.astype(int), [0]])))[0]
print("stretches over 8 mm:", [(round(float(t[a]), 2), round(float(t[min(b, len(t) - 1)]), 2), round(float(depth[a:b].max()), 1)) for a, b in zip(edges[::2], edges[1::2])][:30])
gaps = np.array([[float(r["ball%d_gap_mm" % i]) for i in (1, 2, 3)] for r in rows])
air = np.array([float(r["balls_in_air"]) for r in rows])
print("balls in air at start/end:", air[:3], air[-3:])
print("first second: depth", depth[:6], "gaps", gaps[0])
print("last frames: depth", depth[-3:], "gaps", gaps[-1])
