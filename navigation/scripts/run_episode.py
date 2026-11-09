"""Run one navigation episode on the signed-in Claude plan, then score it.

    python scripts/run_episode.py episodes/c1_red_mug.yaml --condition agent

Conditions:
    agent     Claude Code with `mg` tools, reacting to walk results.
    baseline  One Claude call that returns a plan, run with no further LLM calls.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from motiongen.metrics import score_episode
from motiongen import motion_script, thor_render, world
from motiongen.navigation import REPO_ROOT, load_episode, load_scene, new_state, route_points, walk_to
from motiongen.observe import agent_scene
from motiongen.path_check import check_path
from motiongen.render_map import render_overlay

ALLOWED_COMMAND = re.compile(
    r"^mg ((\w+ )?--help|scene|goto [\w.,-]+( --then (sit|pick|place|open|stand))?"
    r"|(open|close|pick|use) [\w.-]+|place [\w.-]+ [\w.-]+|step (\"[^\"$`\\\\]*\"|'[^']*')"
    r"|submit( --infeasible (\"[^\"]*\"|'[^']*'))?)\s*$"
)
# Long-horizon tasks (episodes with goals) get more turns and time.
TASK_MAX_TURNS = 80
TASK_TIMEOUT = 900


def allowed_read(block, run_dir):
    """Reading the marked view images that `mg scene` wrote is the only file access allowed."""
    if run_dir is None or block["name"] != "Read":
        return False
    path = Path(block["input"].get("file_path", "")).resolve()
    return path.is_relative_to(Path(run_dir).resolve() / "views")


def audit_transcript(lines, run_dir=None):
    """Return the tool-call count and every call outside what the agent may do."""
    violations = []
    tool_calls = 0
    for event in parse_events(lines):
        if event.get("type") != "assistant":
            continue
        for block in event["message"].get("content", []):
            if block.get("type") != "tool_use":
                continue
            tool_calls += 1
            command = block["input"].get("command", "")
            if block["name"] == "Bash" and ALLOWED_COMMAND.match(command):
                continue
            if allowed_read(block, run_dir):
                continue
            violations.append({"tool": block["name"], "input": block["input"]})
    return tool_calls, violations


def parse_events(lines):
    for line in lines:
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def result_event(lines):
    return next((e for e in parse_events(lines) if e.get("type") == "result"), {})


def claude_binary():
    """The claude CLI: on PATH, or the copy bundled with the VS Code extension."""
    found = shutil.which("claude")
    if found:
        return found
    bundled = sorted(Path.home().glob(".vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/claude"))
    if bundled:
        return str(bundled[-1])
    sys.exit("claude CLI not found: install it or put it on PATH")


def call_claude(prompt, cwd, env, model, timeout, tools, extra):
    command = [
        claude_binary(), "-p", prompt,
        "--model", model,
        "--output-format", "stream-json", "--verbose",
        "--tools", tools,
        "--setting-sources", "project",
        "--strict-mcp-config",
        "--no-session-persistence",
        *extra,
    ]
    try:
        result = subprocess.run(
            command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        return stdout.decode() if isinstance(stdout, bytes) else stdout, "timeout", None


def extract_json(text):
    """Parse the JSON object in a reply, tolerating a code fence or surrounding prose."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


def execute_task_plan(episode, plan):
    """Run a baseline plan for a long-horizon task: per step, walk then do its actions."""
    state = world.world(new_state(episode))
    state["submitted"] = True
    if plan.get("infeasible"):
        state["infeasible"] = True
        state["reason"] = plan.get("reason")
        return state
    for number, step in enumerate(plan["steps"], 1):
        if step.get("step"):
            world.declare_step(state, str(step["step"]))
        if step.get("candidates") and not any(
            world.goto(episode, state, target, step.get("then"))["reached"] for target in step["candidates"]
        ):
            state["infeasible"] = True
            state["reason"] = f"step {number}: no route to any of {step['candidates']}"
            return state
        for action in step.get("actions", []):
            result = world.act(episode, state, action[0], *action[1:3])
            if not result.get("done"):
                state["infeasible"] = True
                state["reason"] = f"step {number}: {action} failed: {result.get('reason')}"
                return state
    return state


def execute_plan(scene, episode, plan):
    """Run a baseline plan with no LLM in the loop: first reachable candidate per step."""
    if "goals" in episode:
        return execute_task_plan(episode, plan)
    state = new_state(episode)
    state["submitted"] = True
    if plan.get("infeasible"):
        state["infeasible"] = True
        state["reason"] = plan.get("reason")
        return state
    for step in plan["steps"]:
        if not any(walk_to(scene, state, target)["reached"] for target in step["candidates"]):
            state["infeasible"] = True
            state["reason"] = f"no route to any of {step['candidates']}"
            break
    return state


def read_permission(run_dir):
    # A leading // makes the rule an absolute path.
    return f"Read(/{Path(run_dir).resolve()}/views/**)"


def run_agent(episode, run_dir, env, model, timeout):
    """Claude Code with the mg tools. A render server, if one runs, is started by run_episode."""
    tools, allowed = "Bash", ["Bash(mg:*)"]
    if episode.get("views"):
        tools, allowed = "Bash,Read", allowed + [read_permission(run_dir)]
    max_turns = TASK_MAX_TURNS if "goals" in episode else 25
    stdout, stderr, exit_code = call_claude(
        f"Instruction: {episode['instruction']}", REPO_ROOT / "agent", env, model, timeout,
        tools=tools, extra=["--allowedTools", *allowed, "--max-turns", str(max_turns)],
    )
    state_file = run_dir / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else new_state(episode)
    return state, stdout, stderr, exit_code, None


def run_baseline(episode, scene, run_dir, env, model, timeout):
    prompt_file = "baseline_task_prompt.md" if "goals" in episode else "baseline_prompt.md"
    template = (REPO_ROOT / "agent" / prompt_file).read_text()
    prompt = template.format(
        instruction=episode["instruction"],
        scene=json.dumps(agent_scene(scene, episode, run_dir)),
    )
    # Looking at the views is part of reading the input, not feedback, so the baseline may too.
    tools, extra = "", []
    if episode.get("views"):
        tools, extra = "Read", ["--allowedTools", read_permission(run_dir), "--max-turns", "10"]
    stdout, stderr, exit_code = call_claude(prompt, run_dir, env, model, timeout, tools=tools, extra=extra)
    reply = result_event(stdout.splitlines()).get("result", "")
    try:
        plan = extract_json(reply)
        (run_dir / "plan.json").write_text(json.dumps(plan, indent=2))
        state = execute_plan(scene, episode, plan)
        return state, stdout, stderr, exit_code, None
    except (ValueError, KeyError, TypeError) as error:
        return new_state(episode), stdout, stderr, exit_code, f"unusable plan: {error}"


def start_rerender(episode_path, episode, run_dir):
    """Start the render server for new ego views after each walk; returns (process, info)."""
    started = time.time()
    process, detail = thor_render.start_server(episode_path, run_dir)
    if process is None:
        print(f"warning: no re-rendering: {detail}", file=sys.stderr)
        return None, {"error": detail}
    return process, {"startup_seconds": round(time.time() - started, 1)}


def run_episode(episode_path, condition, model, run_dir, timeout=300, rerender=True):
    """Run one episode and score it.

    rerender: for the agent on an episode with views, keep a simulator open (thor_render) and
    give the agent a new ego view after every walk. Needs the GPU; without one the run goes on
    with the start views only.
    """
    episode_path = Path(episode_path).resolve()
    episode = load_episode(episode_path)
    scene = load_scene(episode)
    if "goals" in episode:
        timeout = max(timeout, TASK_TIMEOUT)
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    mg = shutil.which("mg", path=str(Path(sys.executable).parent))
    if mg is None:
        sys.exit("mg not found next to this Python; use the motion-gen environment")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["PATH"] = f"{Path(mg).parent}{os.pathsep}{env['PATH']}"
    env["MG_EPISODE"] = str(episode_path)
    env["MG_RUN_DIR"] = str(run_dir)

    started = time.time()
    render_info, server = None, None
    if condition == "agent" and rerender and episode.get("views"):
        server, render_info = start_rerender(episode_path, episode, run_dir)
    if condition == "agent":
        try:
            state, stdout, stderr, exit_code, plan_error = run_agent(episode, run_dir, env, model, timeout)
        finally:
            if server is not None:
                thor_render.stop_server(server, run_dir)
    else:
        state, stdout, stderr, exit_code, plan_error = run_baseline(
            episode, scene, run_dir, env, model, timeout
        )
    (run_dir / "transcript.jsonl").write_text(stdout)
    (run_dir / "stderr.txt").write_text(stderr)
    (run_dir / "state.json").write_text(json.dumps(state, indent=2))

    lines = stdout.splitlines()
    tool_calls, violations = audit_transcript(lines, run_dir)
    metrics = score_episode(scene, episode, state)
    # An agent that never submitted did not finish, whatever its position.
    if not state["submitted"] and metrics["success"] is not None:
        metrics["success"] = False

    usage = result_event(lines).get("usage", {})
    if render_info is not None and "error" not in render_info:
        views = state.get("views", [])
        render_info.update(renders=len(views), render_seconds=round(sum(v.get("seconds") or 0 for v in views), 1),
                           errors=len(state.get("render_errors", [])))
    summary = {
        "episode": episode["id"],
        "episode_path": str(episode_path),
        "category": episode.get("category", "task"),
        "condition": condition,
        "model": model,
        "exit_code": exit_code,
        "seconds": round(time.time() - started, 1),
        "submitted": state["submitted"],
        "plan_error": plan_error,
        "tool_calls": tool_calls,
        "output_tokens": usage.get("output_tokens"),
        "audit_clean": not violations,
        "violations": violations,
        "reason": state["reason"],
        "attempts": state["attempts"],
        "final_reply": result_event(lines).get("result"),
        "metrics": metrics,
    }
    if render_info is not None:
        summary["rerender"] = render_info
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    points = route_points(state)
    check = check_path(scene, points) if points else None
    render_overlay(scene, episode["start"], points, check, episode["instruction"]).save(run_dir / "route.png")
    # The motion hand-off: subtasks, motion segments and the partner's walk tasks, in motion/.
    try:
        motion_script.export(run_dir, episode_path)
    except Exception as error:  # noqa: BLE001 - a run's result must not be lost to an export bug
        summary["motion_export_error"] = f"{type(error).__name__}: {error}"
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("episode")
    parser.add_argument("--condition", choices=["agent", "baseline"], default="agent")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-rerender", action="store_true",
                        help="don't render new ego views after each walk (the agent sees only the start views)")
    args = parser.parse_args()

    name = Path(args.episode).stem
    run_dir = REPO_ROOT / "runs" / f"{name}_{args.condition}_{time.strftime('%Y%m%d_%H%M%S')}"
    summary = run_episode(args.episode, args.condition, args.model, run_dir, args.timeout,
                          rerender=not args.no_rerender)
    print(json.dumps(summary, indent=2))
    print(f"Run folder: {run_dir}")


if __name__ == "__main__":
    main()
