"""Print the obstacle clearances stored in evaluate.py's .metrics.json files (my own tool).

    python tools/clearances.py test_out/*.metrics.json"""
import json
import sys

for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    vals = ["%s %.2f cm" % (m["key"].split(":", 1)[1], m["value"]) for m in d["metrics"]
            if m["key"].startswith("clearance:")]
    vals += ["%s %s" % (m["key"], m["value"]) for m in d["metrics"]
             if m["key"] in ("contact_speed_p95", "max_joint_speed", "path_deviation_max",
                             "deepest_floor_penetration")]
    bad = [m["key"] for m in d["metrics"] if m.get("ok") is False]
    vals.append("FAILED: %s" % bad if bad else "all targets met")
    print("%-40s %s" % (path, ", ".join(vals)))
