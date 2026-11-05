"""Create the workspace for one experiment and print how to start the agent in it.

    python -m hoienv.new_run H01-box-carry --task box-carry --from E04-narrow-passage
    python -m hoienv.new_run H02-juggling --task juggling --from H01-box-carry

One experiment = one agent session = one folder runs/<ID>/ = one report report/experiments/<ID>.md.
Works like walkenv/new_run.py. The differences: --from also finds the walking experiments, the agent
always has the measuring and preview tools, and body_info.json includes the hands.

A task with "kit": "juggling" uses the variants of the instructions in agent_kit/ with that name
(TASK_juggling.md, ...) where they exist. starting_point_previous_<ID>.md, if it exists, describes what
the code of that earlier experiment can do.
"""
import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from string import Template

from walkenv import motion_format
from walkenv.new_run import _copy_agent_files

from .paths import BODY_INFO, KIT_DIR, PYTHON, ROOT, RUNS_DIR, TASKS_DIR, WALKING_RUNS
from .tasks import describe, load_task

KICKOFF = (
    "Read TASK.md and SMPLX_INTERFACE.md, then complete the task. "
    "Work autonomously until every deliverable in TASK.md is done."
)


def create_run(exp_id, task_ref, source, max_previews):
    if not re.fullmatch(r"H\d{2}[a-z]?-[a-z0-9-]+", exp_id):
        raise SystemExit(f"experiment IDs look like H01-box-carry, got {exp_id!r}")
    run = RUNS_DIR / exp_id
    if run.exists():
        raise SystemExit(f"{run} already exists; every experiment gets a new ID")
    if not BODY_INFO.exists():
        raise SystemExit(f"{BODY_INFO} is missing; run `python -m hoienv.body_info` first.")
    task_path = Path(task_ref) if Path(task_ref).suffix else TASKS_DIR / f"{task_ref}.json"
    task = load_task(task_path)
    src = next((d / source for d in (RUNS_DIR, WALKING_RUNS) if (d / source).is_dir()), None)
    if src is None:
        raise SystemExit(f"no experiment folder {source}")

    values = {
        "python": PYTHON.as_posix(),
        "hoi_root": ROOT.as_posix(),
        "max_previews": max_previews,
        "title": task["title"],
        "description": describe(task),
        "prev_exp": source,
        "prev_title": json.loads((src / "task.json").read_text(encoding="utf-8"))["title"],
    }
    def variant(stem):
        specific = f"{stem}_{task.get('kit')}.md"
        return specific if (KIT_DIR / specific).exists() else f"{stem}.md"

    starting = f"starting_point_previous_{source}.md"
    values["starting_point"] = _fill(starting if (KIT_DIR / starting).exists() else "starting_point_previous.md", values).strip()
    values["feedback"] = _fill(variant("feedback_visual"), values).strip()
    values["object_section"] = _fill(variant("object_section"), values).strip()

    run.mkdir(parents=True)
    _copy_agent_files(src, run / "previous" / source)
    shutil.copy(task_path, run / "task.json")
    (run / "TASK.md").write_text(_fill(variant("TASK"), values), encoding="utf-8")
    rules = _fill("AGENT_RULES.md", values)
    (run / "CLAUDE.md").write_text(rules, encoding="utf-8")
    (run / "AGENTS.md").write_text(rules, encoding="utf-8")
    (run / "SMPLX_INTERFACE.md").write_text(_fill("SMPLX_INTERFACE.md", values), encoding="utf-8")
    shutil.copy(BODY_INFO, run / "body_info.json")
    shutil.copy(motion_format.__file__, run / "check_format.py")
    (run / "preview.py").write_text(_fill("preview.py.tmpl", values), encoding="utf-8")
    (run / "evaluate.py").write_text(_fill("evaluate.py.tmpl", values), encoding="utf-8")

    meta = {
        "experiment": exp_id,
        "task": task["name"],
        "started_from": source,
        "feedback": "visual",
        "max_previews": max_previews,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "kickoff": KICKOFF,
    }
    (run / "run.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return run


def _fill(template_name, values):
    return Template((KIT_DIR / template_name).read_text(encoding="utf-8")).substitute(values)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment", help="experiment ID, e.g. H01-box-carry")
    ap.add_argument("--task", required=True, help="task name (tasks/<name>.json) or path to a task file")
    ap.add_argument("--from", dest="source", required=True, help="experiment whose code the agent starts from")
    ap.add_argument("--max-previews", type=int, default=12)
    args = ap.parse_args()

    run = create_run(args.experiment, args.task, args.source, args.max_previews)
    print(f"""Created {run}

Start the agent (headless, everything recorded in the folder):
  python -m hoienv.launch {args.experiment}

When it is done:
  python -m hoienv.render runs/{args.experiment}      # videos and contact sheets into runs/{args.experiment}/videos/
  python -m hoienv.evaluate runs/{args.experiment}    # measurements into runs/{args.experiment}/motion.metrics.json
  python -m hoienv.summary runs/{args.experiment}     # duration, turns, cost, tool use into run_summary.json
""")


if __name__ == "__main__":
    main()
