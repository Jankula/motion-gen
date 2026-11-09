"""Compare the agent and the one-call baseline over every episode. Safe to re-run: it resumes.

    python scripts/run_eval.py --name first --repeats 3
    python scripts/run_eval.py --name procthor_v1 --episodes episodes/procthor
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from motiongen.navigation import REPO_ROOT
from run_episode import run_episode

CONDITIONS = ["baseline", "agent"]


def load_finished(run_dir):
    summary_file = run_dir / "summary.json"
    if not summary_file.exists():
        return None
    summary = json.loads(summary_file.read_text())
    return summary if summary["exit_code"] == 0 else None


def tally(summaries, key):
    groups = defaultdict(lambda: {"baseline": [0, 0], "agent": [0, 0]})
    for summary in summaries:
        counts = groups[summary[key]][summary["condition"]]
        counts[0] += summary["metrics"]["success"]
        counts[1] += 1
    return groups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--episodes", default="episodes", help="directory of episode YAML files")
    parser.add_argument("--no-rerender", action="store_true", help="agent sees only the start views")
    args = parser.parse_args()

    eval_dir = REPO_ROOT / "runs" / f"eval_{args.name}"
    summaries = []
    stopped = None
    for episode_path in sorted((REPO_ROOT / args.episodes).glob("*.yaml")):
        for repeat in range(args.repeats):
            for condition in CONDITIONS:
                run_dir = eval_dir / f"{episode_path.stem}__{condition}__{repeat}"
                summary = load_finished(run_dir)
                if summary is None:
                    summary = run_episode(episode_path, condition, args.model, run_dir,
                                          rerender=not args.no_rerender)
                    print(
                        f"{episode_path.stem} {condition} {repeat}: "
                        f"success={summary['metrics']['success']} exit={summary['exit_code']}",
                        flush=True,
                    )
                # A failed Claude call (a usage limit, say) is not a result. Stop so a re-run resumes here.
                if summary["exit_code"] != 0:
                    stopped = f"{run_dir.name}: exit {summary['exit_code']}"
                    break
                summaries.append(summary)
            if stopped:
                break
        if stopped:
            break

    (eval_dir / "results.json").write_text(json.dumps(summaries, indent=2))
    for key in ("episode", "category"):
        print(f"\nSuccess by {key} (baseline, agent)")
        for name, counts in sorted(tally(summaries, key).items()):
            print(f"  {name:28} {counts['baseline'][0]}/{counts['baseline'][1]}   {counts['agent'][0]}/{counts['agent'][1]}")
    fractions = defaultdict(list)
    for summary in summaries:
        if summary["metrics"].get("goal_fraction") is not None:
            fractions[summary["condition"]].append(summary["metrics"]["goal_fraction"])
    if fractions:
        print("\nMean goal fraction on long-horizon tasks (baseline, agent)")
        mean = lambda values: f"{sum(values) / len(values):.2f}" if values else "-"
        print(f"  {'all':28} {mean(fractions['baseline'])}   {mean(fractions['agent'])}")
    dirty = [s["episode"] for s in summaries if not s["audit_clean"]]
    print(f"\nRuns: {len(summaries)}. Audit violations: {dirty or 'none'}.")
    if stopped:
        raise SystemExit(f"Stopped early at {stopped}. Re-run to resume.")


if __name__ == "__main__":
    main()
