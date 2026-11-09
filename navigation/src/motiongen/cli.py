"""`mg`: the agent's tools. Output never includes the episode's success definition.

Requires MG_EPISODE (episode YAML) and MG_RUN_DIR (where state is written).
"""

import argparse
import json
import os
import sys
from pathlib import Path

from . import world
from .navigation import INTENTS, load_episode, new_state
from .observe import agent_scene, render_after_walk

# Defaults; an episode can raise them with max_walks / max_actions.
MAX_WALK_ATTEMPTS = 8
MAX_ACTIONS = 40
ACTIONS = ("open", "close", "pick", "use")


def read_state(run_dir, episode):
    state_file = run_dir / "state.json"
    if state_file.exists():
        return world.world(json.loads(state_file.read_text()))
    return world.world(new_state(episode))


def write_state(run_dir, state):
    (run_dir / "state.json").write_text(json.dumps(state, indent=2))


def fail(message):
    print(json.dumps({"error": message}))
    return 1


def scene_json(data):
    """Compact JSON with one list item per line.

    Indented JSON for a furnished house runs past 30 KB, more than the agent's Bash tool
    shows; the agent would then see the room bounds but not the objects.
    """
    def compact(value):
        return json.dumps(value, separators=(",", ":"))

    lines = []
    for key, value in data.items():
        if isinstance(value, list) and value:
            items = ",\n".join(f"  {compact(item)}" for item in value)
            lines.append(f"{compact(key)}:[\n{items}\n]")
        else:
            lines.append(f"{compact(key)}:{compact(value)}")
    return "{\n" + ",\n".join(lines) + "\n}"


def cmd_scene(scene, episode, run_dir, state, args):
    print(scene_json(agent_scene(scene, episode, run_dir, state)))
    write_state(run_dir, state)  # keeps the mark numbers
    return 0


def walk_limit(episode):
    return episode.get("max_walks", MAX_WALK_ATTEMPTS)


def cmd_goto(scene, episode, run_dir, state, args):
    if state["submitted"]:
        return fail("episode already submitted")
    limit = walk_limit(episode)
    if len(state["attempts"]) >= limit:
        return fail(f"limit of {limit} walk attempts reached; run `mg submit`")
    result = world.goto(episode, state, args.target, args.then)
    if result["reached"] and episode.get("views"):
        image = render_after_walk(episode, run_dir, state)
        if image:
            result["image"] = image
    write_state(run_dir, state)
    print(json.dumps({**result, "attempts_left": limit - len(state["attempts"])}))
    return 0


def cmd_action(scene, episode, run_dir, state, args):
    if state["submitted"]:
        return fail("episode already submitted")
    limit = episode.get("max_actions", MAX_ACTIONS)
    done = sum(1 for e in state["events"] if e["action"] not in ("goto", "step"))
    if done >= limit:
        return fail(f"limit of {limit} actions reached; run `mg submit`")
    result = world.act(episode, state, args.command, args.object, getattr(args, "receptacle", None))
    write_state(run_dir, state)
    print(json.dumps(result))
    return 0


def cmd_step(scene, episode, run_dir, state, args):
    if state["submitted"]:
        return fail("episode already submitted")
    text = " ".join(args.text).strip()
    if not text:
        return fail("say what the step is, e.g. mg step \"get an egg from the fridge\"")
    result = world.declare_step(state, text)
    write_state(run_dir, state)
    print(json.dumps(result))
    return 0


def cmd_submit(scene, episode, run_dir, state, args):
    if state["submitted"]:
        return fail("episode already submitted")
    state["submitted"] = True
    state["infeasible"] = args.infeasible is not None
    state["reason"] = args.infeasible
    write_state(run_dir, state)
    print(json.dumps({"submitted": True, "infeasible": state["infeasible"]}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mg")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("scene", help="print the scene graph as JSON")
    goto_parser = commands.add_parser("goto", help="walk to an object id or an x,y position")
    goto_parser.add_argument("target")
    goto_parser.add_argument("--then", choices=INTENTS, help="what the person does on arrival")
    for action in ACTIONS:
        action_parser = commands.add_parser(action, help=f"{action} an object within reach")
        action_parser.add_argument("object", help="object id, or a label for the nearest visible one")
    place_parser = commands.add_parser("place", help="put a held object in or on a receptacle")
    place_parser.add_argument("object")
    place_parser.add_argument("receptacle")
    step_parser = commands.add_parser("step", help="name the next part of the plan")
    step_parser.add_argument("text", nargs="+", help='what it does, e.g. "get an egg from the fridge"')
    submit_parser = commands.add_parser("submit", help="end the episode")
    submit_parser.add_argument("--infeasible", metavar="REASON", help="report the task as impossible")
    args = parser.parse_args(argv)

    try:
        episode_path = os.environ["MG_EPISODE"]
        run_dir = Path(os.environ["MG_RUN_DIR"])
    except KeyError as error:
        return fail(f"{error.args[0]} is not set")
    run_dir.mkdir(parents=True, exist_ok=True)
    episode = load_episode(episode_path)
    state = read_state(run_dir, episode)
    scene = world.scene_for(episode, state)
    handlers = {"scene": cmd_scene, "goto": cmd_goto, "step": cmd_step, "submit": cmd_submit}
    handler = handlers.get(args.command, cmd_action)
    return handler(scene, episode, run_dir, state, args)


if __name__ == "__main__":
    sys.exit(main())
