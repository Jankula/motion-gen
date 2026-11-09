"""Carry out a task given only as text, a ProcTHOR house and a start position.

    python scripts/do_task.py --house 2927 --start 2.5,1.5 "Make me scrambled eggs and sit down to eat."

Everything else is automatic:
  1. exports the house (scenes/procthor/<split>_<index>/) if it hasn't been yet,
  2. moves the start to the nearest free floor if it isn't free,
  3. writes the episode (episodes/tasks/<id>.yaml) and renders its views,
  4. runs the agent, which plans the steps and walks and acts through the house; after every
     walk it gets a new ego view rendered from where the person stands (--no-rerender: start views only),
  5. prints the subtasks with their motion segments, the timings and where the run folder is.

The run folder holds state.json (legs and events), route.png, the transcript, summary.json and
motion/: motion_script.json (subtasks, motion segments, object timeline), walks/walk_NN.json (one
task file per walk for the partner's walking code) and route_motion.png. There is nothing to
score against, so success is null.
Needs AI2-THOR (GPU) for steps 1, 3 and the re-rendering, and the claude CLI for step 4.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from motiongen.navigation import REPO_ROOT
from motiongen.scene import Scene
from run_episode import run_episode

EPISODES = REPO_ROOT / "episodes" / "tasks"
# How far the start may be moved to reach free floor, in metres.
MAX_START_SHIFT = 1.5


def parse_house(text):
    """"2927", "train_2927" or "val_12" -> (split, index)."""
    match = re.fullmatch(r"(?:(train|val|test)_)?(\d+)", text)
    if not match:
        sys.exit(f"--house must look like 2927 or train_2927, not {text!r}")
    return match.group(1) or "train", int(match.group(2))


def export(*args):
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "export_procthor.py"), *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"export_procthor.py {' '.join(args)} failed:\n{result.stderr[-2000:]}")
    return result.stdout


def free_start(scene, x, y):
    """(x, y), or the nearest point the body fits, with how far it moved."""
    if scene.clearance_at(x, y) >= scene.body_radius:
        return [x, y], 0.0
    ix, iy = np.nonzero(scene.clearance >= scene.body_radius)
    if len(ix) == 0:
        sys.exit("the house has no free floor")
    distance = np.hypot(scene.xs[ix] - x, scene.ys[iy] - y)
    best = int(np.argmin(distance))
    if distance[best] > MAX_START_SHIFT:
        sys.exit(f"start ({x}, {y}) is {distance[best]:.1f} m from any free floor; pick a point inside a room")
    return [round(float(scene.xs[ix[best]]), 2), round(float(scene.ys[iy[best]]), 2)], float(distance[best])


def slug(text, words=4):
    return "_".join(re.findall(r"[a-z]+", text.lower())[:words]) or "task"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("instruction", help="the task, in plain words")
    parser.add_argument("--house", required=True, help="ProcTHOR house: 2927 or train_2927")
    parser.add_argument("--start", required=True, help="start position x,y in metres (scene frame)")
    parser.add_argument("--heading", type=float, default=0.0, help="start heading, degrees counter-clockwise from +x")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--condition", choices=["agent", "baseline"], default="agent")
    parser.add_argument("--no-rerender", action="store_true", help="no new ego views after walks")
    args = parser.parse_args()

    split, index = parse_house(args.house)
    scene_rel = f"scenes/procthor/{split}_{index}/scene.yaml"
    if not (REPO_ROOT / scene_rel).exists():
        print(f"exporting {split} house {index} ...", flush=True)
        export("scene", split, str(index))
    scene = Scene.load(REPO_ROOT / scene_rel)

    x, y = (float(v) for v in args.start.split(","))
    start, moved = free_start(scene, x, y)
    if moved:
        print(f"start ({x}, {y}) is not free floor; using {start} ({moved:.2f} m away)")
    print(f"start in {scene.room_of(*start) or 'no room'}", flush=True)

    episode_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{slug(args.instruction)}"
    episode = {
        "id": episode_id, "category": "task", "scene": scene_rel,
        "instruction": args.instruction, "start": start, "heading": args.heading,
        "max_walks": 20, "max_actions": 40,
    }
    EPISODES.mkdir(parents=True, exist_ok=True)
    path = EPISODES / f"{episode_id}.yaml"
    path.write_text(yaml.safe_dump(episode, sort_keys=False, default_flow_style=None, width=140))

    print("rendering views ...", flush=True)
    started = time.time()
    out = export("views", str(path))
    render_seconds = time.time() - started
    episode["views"] = [line.strip()[2:] for line in out.split("views:", 1)[1].splitlines() if line.strip()]
    path.write_text(yaml.safe_dump(episode, sort_keys=False, default_flow_style=None, width=140))

    print(f"running the {args.condition} ...", flush=True)
    run_dir = REPO_ROOT / "runs" / f"{episode_id}_{args.condition}"
    summary = run_episode(path, args.condition, args.model, run_dir, rerender=not args.no_rerender)

    state = json.loads((run_dir / "state.json").read_text())
    script_file = run_dir / "motion" / "motion_script.json"
    print()
    if script_file.exists():
        script = json.loads(script_file.read_text())
        segments = script["segments"]
        for subtask in script["subtasks"]:
            source = "" if subtask["source"] == "agent" else " (derived)"
            print(f"{subtask['id']}. {subtask['text']}{source}")
            for i in subtask["segments"]:
                seg = segments[i]
                print(f"     {i:2}  {seg['motion']:<11} {seg['duration_est']:5.1f} s  {seg['caption']}")
        print(f"estimated motion: {script['duration_est']:.0f} s in {len(segments)} segments, "
              f"{sum(s['motion'] == 'walk' for s in segments)} walk task files")
    else:
        print(f"no motion script: {summary.get('motion_export_error')}")
    failed = [e for e in state.get("events", []) if e["action"] == "goto" and not e.get("reached")]
    print(f"\nsubmitted: {state['submitted']}, reported infeasible: {state['infeasible']}"
          + (f" ({state['reason']})" if state["reason"] else ""))
    print(f"route: {summary['metrics']['route_length']} m, collision-free: {summary['metrics']['collision_free']}, "
          f"failed walks: {len(failed)}, audit clean: {summary['audit_clean']}")
    if summary.get("final_reply"):
        print(f"agent: {summary['final_reply']}")
    rerender = summary.get("rerender") or {}
    print(f"time: start views {render_seconds:.0f} s, run {summary['seconds']:.0f} s"
          + (f" (render server start {rerender['startup_seconds']} s, {rerender['renders']} walk views in "
             f"{rerender['render_seconds']} s)" if "renders" in rerender else "")
          + (f"; re-rendering off: {rerender['error']}" if "error" in rerender else ""))
    print(f"run folder: {run_dir}")
    print(f"motion hand-off: {run_dir / 'motion'}")


if __name__ == "__main__":
    main()
