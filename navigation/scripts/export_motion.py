"""Write the motion hand-off (motion/) for finished run folders.

    python scripts/export_motion.py runs/eval_procthor_long_v1/t01_breakfast_2927__agent__0
    python scripts/export_motion.py runs/eval_procthor_long_v1/*__agent__0
    python scripts/export_motion.py <run_dir> --episode episodes/procthor_long/t01_breakfast_2927.yaml --out /tmp/m

run_episode.py already does this at the end of every run; this is for runs made before, or
after changing the format. It needs no GPU and no Claude: it only reads state.json.

For each run folder it writes <run_dir>/motion/ (or --out):
  motion_script.json   subtasks, motion segments (walk, turn, step_back, open, close,
                       reach_grasp, put_down, use, sit_down, stand_up) and the object timeline
  walks/walk_NN.json   one task file per walk for the partner's walking code
                       (python make_motion.py walk_01.json walk_01.npz)
  route_motion.png     the map with the route coloured by subtask and every motion labelled
The episode file is found from summary.json (episode_path, or the episode id under episodes/).
"""

import argparse
import json
import sys
from pathlib import Path

from motiongen.motion_script import export


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("runs", nargs="+", help="run folders (with state.json)")
    parser.add_argument("--episode", help="the episode YAML, if it can't be found from summary.json")
    parser.add_argument("--out", help="output folder (one run only; default <run_dir>/motion)")
    args = parser.parse_args()
    if args.out and len(args.runs) > 1:
        sys.exit("--out works with one run folder only")

    failed = 0
    for run in args.runs:
        run = Path(run)
        if not (run / "state.json").exists():
            print(f"skip {run}: no state.json")
            continue
        try:
            out = export(run, args.episode, args.out)
        except Exception as error:  # noqa: BLE001 - report and go on with the other runs
            failed += 1
            print(f"FAIL {run}: {type(error).__name__}: {error}")
            continue
        script = json.loads((out / "motion_script.json").read_text())
        walks = sum(s["motion"] == "walk" for s in script["segments"])
        print(f"{run}: {len(script['subtasks'])} subtasks, {len(script['segments'])} segments, {walks} walks, "
              f"~{script['duration_est']:.0f} s of motion -> {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
