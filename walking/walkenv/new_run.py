"""Create an isolated workspace for one agent attempt and print how to launch the agent in it.

    python -m walkenv.new_run --agent claude --mode blind
    python -m walkenv.new_run --agent codex --mode visual --max-previews 5

The workspace (runs/<timestamp>_<agent>_<mode>/) contains only what the agent may see:
TASK.md, SMPLX_INTERFACE.md, body_info.json, check_format.py, CLAUDE.md / AGENTS.md
(the same rules, for Claude Code and Codex), and in visual mode preview.py.
"""
import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from string import Template

from .motion_format import TASK_FPS, TASK_FRAMES
from .paths import BODY_INFO, KIT_DIR, PYTHON, ROOT, RUNS_DIR

KICKOFF = (
    "Read TASK.md and SMPLX_INTERFACE.md, then complete the task. "
    "Work autonomously until every deliverable in TASK.md is done."
)


def create_run(agent, mode, max_previews, name=None):
    if not BODY_INFO.exists():
        raise SystemExit(f"{BODY_INFO} is missing; run `python -m walkenv.body_info` first.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run = RUNS_DIR / "_".join(filter(None, [stamp, agent, mode, name]))
    run.mkdir(parents=True)

    values = {
        "python": PYTHON.as_posix(),
        "fps": TASK_FPS,
        "frames": TASK_FRAMES,
        "seconds": f"{TASK_FRAMES / TASK_FPS:g}",
        "max_previews": max_previews,
        "walking_root": ROOT.as_posix(),
    }
    values["mode_rules"] = _fill(f"mode_{mode}.md", values).strip()
    task = _fill("TASK.md", values)
    rules = _fill("AGENT_RULES.md", values)

    (run / "TASK.md").write_text(task, encoding="utf-8")
    (run / "CLAUDE.md").write_text(rules, encoding="utf-8")
    (run / "AGENTS.md").write_text(rules, encoding="utf-8")
    shutil.copy(KIT_DIR / "SMPLX_INTERFACE.md", run / "SMPLX_INTERFACE.md")
    shutil.copy(BODY_INFO, run / "body_info.json")
    shutil.copy(Path(__file__).with_name("motion_format.py"), run / "check_format.py")
    if mode == "visual":
        (run / "preview.py").write_text(_fill("preview.py.tmpl", values), encoding="utf-8")

    meta = {"agent": agent, "mode": mode, "max_previews": max_previews, "created": stamp, "kickoff": KICKOFF}
    (run / "run.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return run


def _fill(template_name, values):
    return Template((KIT_DIR / template_name).read_text(encoding="utf-8")).substitute(values)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", default="agent", help="label for the run folder, e.g. claude or codex")
    ap.add_argument("--mode", choices=["blind", "visual"], default="blind")
    ap.add_argument("--max-previews", type=int, default=5, help="visual mode: preview renders allowed")
    ap.add_argument("--name", help="optional suffix for the run folder")
    args = ap.parse_args()

    run = create_run(args.agent, args.mode, args.max_previews, args.name)
    py = PYTHON.as_posix()
    print(f"""Created {run}

Kickoff prompt:
  {KICKOFF}

Launch from inside the workspace (cd "{run}"):
  Claude Code, interactive:  claude "{KICKOFF}"
  Claude Code, headless:     claude -p "{KICKOFF}" --permission-mode acceptEdits --allowedTools "Bash({py} *)" --output-format stream-json --verbose > transcript.jsonl
  Codex, interactive:        codex "{KICKOFF}"
  Codex, headless:           codex exec --full-auto "{KICKOFF}" > transcript.txt

When the agent is done, render the videos (from {ROOT}):
  python -m walkenv.render "{run.relative_to(ROOT).as_posix()}"
""")


if __name__ == "__main__":
    main()
