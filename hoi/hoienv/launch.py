"""Run the agent (Claude Code, headless) in an experiment folder and record the session.

    python -m hoienv.launch H01-box-carry --model claude-opus-5-5
    python -m hoienv.launch H01-box-carry --resume --reason "account usage limit reached"

Same as walkenv/launch.py, for the experiments in hoi/runs/.
"""
import argparse

from walkenv.launch import launch
from walkenv.summary import summary_table

from .paths import RUNS_DIR


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment")
    ap.add_argument("--model", help="model for the agent (default: Claude Code's default)")
    ap.add_argument("--resume", action="store_true", help="continue the recorded session after an interruption")
    ap.add_argument("--reason", help="why the session was interrupted (recorded in run.json)")
    args = ap.parse_args()
    print(summary_table(launch(args.experiment, args.model, args.resume, args.reason, runs_dir=RUNS_DIR)))


if __name__ == "__main__":
    main()
