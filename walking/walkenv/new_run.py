"""Create the workspace for one experiment and print how to start the agent in it.

    python -m walkenv.new_run E02-curved-path --task curved-path --from E01-straight-walk
    python -m walkenv.new_run E09-blind-retry --task straight-walk --feedback blind

One experiment = one agent session = one folder runs/<ID>/ = one report report/experiments/<ID>.md.
The folder starts with only what the agent may see:
  TASK.md, CLAUDE.md / AGENTS.md    the assignment and the rules (CLAUDE.md for Claude Code, AGENTS.md for Codex)
  SMPLX_INTERFACE.md, body_info.json  how the body is controlled, and its measurements
  task.json                         the task, machine-readable
  check_format.py                   validates a motion file
  evaluate.py, preview.py           measuring and preview tools (feedback "visual" only)
  previous/<ID>/                    the agent-written code and notes of the experiment given by --from
  tasks/                            the earlier tasks of that chain, which must keep working
"""
import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from string import Template

from .paths import BODY_INFO, KIT_DIR, PYTHON, ROOT, RUNS_DIR, TASKS_DIR
from .tasks import describe, load_task

KICKOFF = (
    "Read TASK.md and SMPLX_INTERFACE.md, then complete the task. "
    "Work autonomously until every deliverable in TASK.md is done."
)
# Files we put into (or the run adds to) an experiment folder. Everything else in it was written by the agent.
HARNESS_FILES = {
    "TASK.md", "CLAUDE.md", "AGENTS.md", "SMPLX_INTERFACE.md", "body_info.json", "check_format.py", "preview.py",
    "evaluate.py", "run.json", "run_summary.json", "transcript.jsonl", "stderr.txt", "task.json", "tasks",
    "previous", "videos", "preview", "__pycache__", ".preview_count", "unseen",
}


def create_run(exp_id, task_ref, source=None, feedback="visual", max_previews=8):
    if not re.fullmatch(r"E\d{2}[a-z]?-[a-z0-9-]+", exp_id):
        raise SystemExit(f"experiment IDs look like E02-curved-path, got {exp_id!r}")
    run = RUNS_DIR / exp_id
    if run.exists():
        raise SystemExit(f"{run} already exists; every experiment gets a new ID")
    if not BODY_INFO.exists():
        raise SystemExit(f"{BODY_INFO} is missing; run `python -m walkenv.body_info` first.")
    task_path = Path(task_ref) if Path(task_ref).suffix else TASKS_DIR / f"{task_ref}.json"
    task = load_task(task_path)

    values = {
        "python": PYTHON.as_posix(),
        "walking_root": ROOT.as_posix(),
        "max_previews": max_previews,
        "title": task["title"],
        "description": describe(task),
        "and_earlier": "",
    }
    run.mkdir(parents=True)
    shutil.copy(task_path, run / "task.json")
    if source:
        src = RUNS_DIR / source
        if not src.is_dir():
            raise SystemExit(f"no experiment folder {src}")
        _copy_agent_files(src, run / "previous" / source)
        earlier = _copy_earlier_tasks(src, run / "tasks", task["name"])
        values.update(
            prev_exp=source,
            prev_title=json.loads((src / "task.json").read_text(encoding="utf-8"))["title"],
            earlier_list=", ".join(f"`{name}.json`" for name in earlier),
            and_earlier=" and for every task file in `tasks/`" if earlier else "",
        )
        values["starting_point"] = _fill("starting_point_previous.md", values).strip()
    else:
        values["starting_point"] = _fill("starting_point_scratch.md", values).strip()
    values["feedback"] = _fill(f"feedback_{feedback}.md", values).strip()

    (run / "TASK.md").write_text(_fill("TASK.md", values), encoding="utf-8")
    rules = _fill("AGENT_RULES.md", values)
    (run / "CLAUDE.md").write_text(rules, encoding="utf-8")
    (run / "AGENTS.md").write_text(rules, encoding="utf-8")
    shutil.copy(KIT_DIR / "SMPLX_INTERFACE.md", run / "SMPLX_INTERFACE.md")
    shutil.copy(BODY_INFO, run / "body_info.json")
    shutil.copy(Path(__file__).with_name("motion_format.py"), run / "check_format.py")
    if feedback == "visual":
        (run / "preview.py").write_text(_fill("preview.py.tmpl", values), encoding="utf-8")
        (run / "evaluate.py").write_text(_fill("evaluate.py.tmpl", values), encoding="utf-8")

    meta = {
        "experiment": exp_id,
        "task": task["name"],
        "started_from": source,
        "feedback": feedback,
        "max_previews": max_previews if feedback == "visual" else 0,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "kickoff": KICKOFF,
    }
    (run / "run.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return run


def _copy_agent_files(src, dst):
    dst.mkdir(parents=True)
    for item in src.iterdir():
        if item.name in HARNESS_FILES or item.suffix == ".npz" or item.name.endswith((".metrics.json", ".timeline.csv", ".throws.csv")):
            continue
        if item.is_dir():
            shutil.copytree(item, dst / item.name, ignore=shutil.ignore_patterns("__pycache__", "*.npz"))
        else:
            shutil.copy(item, dst / item.name)


def _copy_earlier_tasks(src, dst, current_name):
    """The source experiment's own task plus the tasks it had to keep working."""
    files = [src / "task.json"] + sorted((src / "tasks").glob("*.json") if (src / "tasks").is_dir() else [])
    names = []
    for f in files:
        name = json.loads(f.read_text(encoding="utf-8"))["name"]
        if name != current_name and name not in names:
            dst.mkdir(exist_ok=True)
            shutil.copy(f, dst / f"{name}.json")
            names.append(name)
    return names


def _fill(template_name, values):
    return Template((KIT_DIR / template_name).read_text(encoding="utf-8")).substitute(values)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment", help="experiment ID, e.g. E02-curved-path")
    ap.add_argument("--task", required=True, help="task name (tasks/<name>.json) or path to a task file")
    ap.add_argument("--from", dest="source", help="experiment whose code the agent starts from")
    ap.add_argument("--feedback", choices=["blind", "visual"], default="visual",
                    help="blind: no tools to see or measure the result; visual: evaluate.py and preview.py")
    ap.add_argument("--max-previews", type=int, default=8)
    args = ap.parse_args()

    run = create_run(args.experiment, args.task, args.source, args.feedback, args.max_previews)
    print(f"""Created {run}

Start the agent (headless, everything recorded in the folder):
  python -m walkenv.launch {args.experiment}

Or interactively, from inside the folder:
  claude "{KICKOFF}"
  codex "{KICKOFF}"

When it is done:
  python -m walkenv.render runs/{args.experiment}      # videos and contact sheets into runs/{args.experiment}/videos/
  python -m walkenv.evaluate runs/{args.experiment}    # measurements into runs/{args.experiment}/motion.metrics.json
""")


if __name__ == "__main__":
    main()
