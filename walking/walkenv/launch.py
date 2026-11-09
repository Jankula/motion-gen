"""Run the agent (Claude Code, headless) in an experiment folder and record the session.

    python -m walkenv.launch E02-curved-path
    python -m walkenv.launch E02-curved-path --model claude-opus-5-5
    python -m walkenv.launch E03-turns --resume --reason "account usage limit reached"

Writes into the experiment folder: transcript.jsonl (every message and tool call), stderr.txt, and
run_summary.json when the agent stops. Environment variables starting with CLAUDE are removed so
that, when this is started from inside another Claude Code session, the agent still runs as an
independent session. The agent may edit files in its folder, run the project's Python and create
folders; nothing else.

--resume continues the same agent session (same conversation, same context) after an interruption
from outside, such as a usage limit. The transcript is appended to, and run.json records the
interruption and its reason.
"""
import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime

from .paths import PYTHON, RUNS_DIR
from .summary import summarize, summary_table

RESUME_MESSAGE = (
    "Your session was interrupted from outside (not by anything you did) and is now resumed. "
    "Continue where you left off and complete every deliverable in TASK.md."
)


def launch(exp_id, model=None, resume=False, reason=None, runs_dir=RUNS_DIR):
    run = runs_dir / exp_id
    meta_path = run / "run.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    claude = shutil.which("claude")
    if claude is None:
        raise SystemExit("the `claude` command (Claude Code) is not on PATH")

    if resume:
        session_id = _session_id(run / "transcript.jsonl")
        prompt = RESUME_MESSAGE
        meta.setdefault("resumed", []).append(
            {"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "session_id": session_id, "reason": reason}
        )
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    else:
        prompt = meta["kickoff"]
    cmd = [
        claude, "-p", prompt,
        "--permission-mode", "acceptEdits",
        "--allowedTools", f"Bash({PYTHON.as_posix()} *)", "Bash(mkdir *)",
        "--output-format", "stream-json", "--verbose",
    ]
    if resume:
        cmd += ["--resume", session_id]
    if model:
        cmd += ["--model", model]
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"  # the agent must not see notes kept about this project
    mode = "a" if resume else "w"
    with open(run / "transcript.jsonl", mode, encoding="utf-8") as out, open(run / "stderr.txt", mode, encoding="utf-8") as err:
        code = subprocess.run(cmd, cwd=run, env=env, stdout=out, stderr=err).returncode
    print(f"agent exited with code {code}")
    return summarize(run)


def _session_id(transcript):
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict) and ev.get("session_id"):
            return ev["session_id"]
    raise SystemExit(f"no session id found in {transcript}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment")
    ap.add_argument("--model", help="model for the agent (default: Claude Code's default)")
    ap.add_argument("--resume", action="store_true", help="continue the recorded session after an interruption")
    ap.add_argument("--reason", help="why the session was interrupted (recorded in run.json)")
    args = ap.parse_args()
    print(summary_table(launch(args.experiment, args.model, args.resume, args.reason)))


if __name__ == "__main__":
    main()
