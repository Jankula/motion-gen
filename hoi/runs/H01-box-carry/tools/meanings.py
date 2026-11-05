"""Print failed metrics with their meanings, and when the timeline peaks.

    python tools/meanings.py [motion name] [--all]
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
name = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "motion"
m = json.load(open(os.path.join(ROOT, name + ".metrics.json"), encoding="utf-8"))
for e in m["metrics"]:
    if "--all" in sys.argv or e.get("ok") is False:
        print("[%s] %s = %s %s (target %s)\n    %s" % (e["key"], e["label"], e["value"], e["unit"], e["target"], e["meaning"]))
rows = list(csv.DictReader(open(os.path.join(ROOT, name + ".timeline.csv"), encoding="utf-8")))
for col in ("body_into_box_mm", "arm_into_body_mm", "balance_outside_feet_cm", "box_speed_m_s"):
    v = [float(r[col]) for r in rows]
    i = max(range(len(v)), key=lambda k: v[k])
    pos = [float(rows[k]["time_s"]) for k in range(len(v)) if v[k] > 0.5 * v[i]] if v[i] > 0 else []
    print("%-26s peak %.2f at t=%.2f; above half of it: %s" % (col, v[i], float(rows[i]["time_s"]),
          (min(pos), max(pos), len(pos)) if pos else "-"))
