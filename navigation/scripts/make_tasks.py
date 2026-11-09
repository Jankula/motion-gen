"""Write the long-horizon task episodes into episodes/procthor_long/.

Each task names a house, an instruction, its hidden goals and a reference solution. For each,
this picks a start (the most open spot in the given room), checks that the reference solution
reaches every goal, and writes the episode. With --views it also renders the episode's views
(needs AI2-THOR) and adds them to the file.

    python scripts/make_tasks.py            # write and check
    python scripts/make_tasks.py --views    # also render views
"""

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

from motiongen import world
from motiongen.goals import score_goals
from motiongen.navigation import REPO_ROOT, new_state
from motiongen.scene import Scene, points_in_polygon

OUT = REPO_ROOT / "episodes" / "procthor_long"
SEATS = {"chair", "stool", "sofa", "arm chair"}
DISHES = ["bowl", "plate", "cup", "mug"]
# What eggs may be cooked and served in.
VESSELS = DISHES + ["pot", "pan"]


def seats_at(scene, table, within=0.6):
    """Seats beside a table, for "sit down there"."""
    t = scene.get(table)
    return [o.id for o in scene.objects if o.label in SEATS and o.footprint_distance(*t.center[:2]) <= within + max(t.size[:2]) / 2]


# Task families: (instruction, goals, reference) from per-house parameters.

def breakfast(p, scene):
    dish = p["dish"]
    eat_at = [p["table"], *seats_at(scene, p["table"])]
    goals = {
        "events": [
            {"id": "got_egg", "pick": "egg"},
            {"id": "cooked", "use": "microwave", "containing": "egg"},
            {"id": "ate", "goto": eat_at, "intent": "sit"},
        ],
        # Serving is checked by the end state (egg in a dish on the table): the dish may
        # already be on the table, with the egg put onto it there.
        "order": [["got_egg", "cooked"], ["cooked", "ate"]],
        "final": [{"in": ["egg", VESSELS]}, {"on": [VESSELS, p["table"]]}, {"closed": "fridge"},
                  {"closed": "microwave"}, {"holding": "nothing"}],
    }
    egg = p.get("egg_from", "fridge_1")
    get_egg = ([("goto", egg), ("open", egg), ("pick", "egg"), ("close", egg)] if egg.startswith("fridge")
               else [("goto", egg), ("pick", egg)])
    reference = get_egg + [
        ("goto", dish), ("pick", dish), ("place", "egg", dish),
        ("goto", "microwave_1"), ("open", "microwave_1"), ("place", dish, "microwave_1"), ("close", "microwave_1"),
        ("use", "microwave_1"), ("open", "microwave_1"), ("pick", dish), ("close", "microwave_1"),
        ("goto", p["table"]), ("place", dish, p["table"]), ("goto", p["seat"], "sit"),
    ]
    instruction = f"Make me scrambled eggs, serve them at {p['table_text']}, and sit down there to eat. Leave the kitchen tidy."
    return instruction, goals, reference


def coffee(p, scene):
    sofas = p["sofa"] if isinstance(p["sofa"], list) else [p["sofa"]]
    goals = {
        "events": [
            {"id": "got_cup", "pick": ["mug", "cup"]},
            {"id": "brewed", "use": "coffee machine", "containing": [["mug", "cup"]]},
            {"id": "sat", "goto": sofas, "intent": "sit"},
        ],
        "order": [["got_cup", "brewed"], ["brewed", "sat"]],
        "final": [{"near": [["mug", "cup"], sofas]}, {"at": sofas}],
    }
    cup = p["cup"]
    reference = [
        ("goto", cup), ("pick", cup), ("goto", "coffee_machine_1"), ("place", cup, "coffee_machine_1"),
        ("use", "coffee_machine_1"), ("pick", cup), ("goto", sofas[0], "sit"),
    ]
    return "Make me a cup of coffee, bring it to the sofa and sit down there with it.", goals, reference


def toast(p, scene):
    goals = {
        "events": [
            {"id": "got_bread", "pick": "bread"},
            {"id": "toasted", "use": "toaster", "containing": "bread"},
            {"id": "served", "place": ["bread", "plate"]},
        ],
        "order": [["got_bread", "toasted"], ["toasted", "served"]],
        "final": [{"on": ["bread", "plate"]}, {"on": ["plate", p["table"]]}, {"holding": "nothing"}],
    }
    reference = [("goto", p["bread"]), ("pick", p["bread"]), ("goto", "toaster_1"), ("place", p["bread"], "toaster_1"),
                 ("use", "toaster_1"), ("pick", p["bread"])] + p["serve"]
    return f"Make some toast and serve it on a plate at {p['table_text']}.", goals, reference


def salad(p, scene):
    goals = {
        "events": [{"id": "got_lettuce", "pick": "lettuce"}, {"id": "got_tomato", "pick": "tomato"}],
        "final": [{"in": ["lettuce", "bowl"]}, {"in": ["tomato", "bowl"]}, {"on": ["bowl", p["table"]]},
                  {"closed": "fridge"}, {"holding": "nothing"}],
    }
    return f"Make a salad of lettuce and tomato in a bowl and put it on {p['table_text']}.", goals, p["reference"]


def laundry(p, scene):
    goals = {
        "events": [
            {"id": "got_cloth", "pick": "cloth"},
            {"id": "washed", "use": "washing machine", "containing": "cloth"},
            {"id": "dried", "use": "clothes dryer", "containing": "cloth"},
        ],
        "order": [["got_cloth", "washed"], ["washed", "dried"]],
        "final": [{"in": ["cloth", "clothes dryer"]}, {"holding": "nothing"}],
    }
    reference = [
        ("goto", "cloth_1"), ("pick", "cloth_1"), ("goto", "washing_machine_1"), ("place", "cloth_1", "washing_machine_1"),
        ("use", "washing_machine_1"), ("pick", "cloth_1"), ("goto", "clothes_dryer_1"),
        ("place", "cloth_1", "clothes_dryer_1"), ("use", "clothes_dryer_1"),
    ]
    return "Do the laundry: wash the cloth that's lying in the bathroom, then dry it.", goals, reference


def clear_table(p, scene):
    final = [{"on": [d, "counter top"]} for d in p["dishes"]]
    final += [{"in": [f, "fridge"]} for f in p.get("food", [])]
    final += [{"off": [p["dishes"] + p.get("food", []), p["table"]]}, {"closed": "fridge"}, {"holding": "nothing"}]
    return p["instruction"], {"final": final}, p["reference"]


FAMILIES = {"breakfast": breakfast, "coffee": coffee, "toast": toast, "salad": salad,
            "laundry": laundry, "clear_table": clear_table}

TASKS = [
    # Breakfast: an egg (usually in the fridge) cooked in the microwave in a bowl or on a plate.
    dict(id="t01_breakfast_2927", family="breakfast", house=2927, start_room="bedroom_1",
         dish="bowl_2", table="dining_table_2", table_text="the kitchen table", seat="chair_3"),
    dict(id="t02_breakfast_1078", family="breakfast", house=1078, start_room="bedroom_2",
         dish="bowl_1", table="dining_table_1", table_text="the dining table", seat="dining_table_1"),
    dict(id="t03_breakfast_2957", family="breakfast", house=2957, start_room="bedroom_3",
         dish="bowl_1", table="dining_table_1", table_text="the kitchen table", seat="dining_table_1"),
    dict(id="t04_breakfast_239", family="breakfast", house=239, start_room="bedroom_1",
         dish="plate_1", table="dining_table_2", table_text="the kitchen table", seat="dining_table_2"),
    dict(id="t05_breakfast_811", family="breakfast", house=811, start_room="bedroom_3",
         dish="plate_1", table="dining_table_1", table_text="the kitchen table", seat="dining_table_1"),
    # Coffee: a mug or cup through the coffee machine, then to the sofa.
    dict(id="t06_coffee_1078", family="coffee", house=1078, start_room="bedroom_1", cup="cup_1", sofa="sofa_1"),
    dict(id="t07_coffee_737", family="coffee", house=737, start_room="bedroom_3", cup="cup_1", sofa=["sofa_1", "sofa_2"]),
    dict(id="t08_coffee_239", family="coffee", house=239, start_room="bedroom_1", cup="cup_1", sofa="sofa_1"),
    # Toast: bread through the toaster, onto a plate, at a table.
    dict(id="t09_toast_2927", family="toast", house=2927, start_room="living_room_1", bread="bread_1",
         table="dining_table_2", table_text="the kitchen table",
         serve=[("goto", "plate_1"), ("pick", "plate_1"), ("place", "bread_1", "plate_1"),
                ("goto", "dining_table_2"), ("place", "plate_1", "dining_table_2")]),
    dict(id="t10_toast_2957", family="toast", house=2957, start_room="living_room_2", bread="bread_1",
         table="dining_table_1", table_text="the kitchen table",
         serve=[("goto", "plate_1"), ("place", "bread_1", "plate_1")]),
    dict(id="t11_toast_737", family="toast", house=737, start_room="bedroom_1", bread="bread_1",
         table="dining_table_3", table_text="the table where the only plate in the house is",
         serve=[("goto", "plate_1"), ("place", "bread_1", "plate_1")]),
    # Salad: lettuce and tomato into a bowl, onto a table. Two hands for three things.
    dict(id="t12_salad_2927", family="salad", house=2927, start_room="bedroom_1",
         table="dining_table_2", table_text="the kitchen table",
         reference=[("goto", "lettuce_1"), ("pick", "lettuce_1"), ("goto", "tomato_2"), ("pick", "tomato_2"),
                    ("goto", "bowl_2"), ("place", "lettuce_1", "bowl_2"), ("place", "tomato_2", "bowl_2")]),
    dict(id="t13_salad_1078", family="salad", house=1078, start_room="bedroom_1",
         table="dining_table_1", table_text="the dining table",
         reference=[("goto", "bowl_1"), ("pick", "bowl_1"), ("goto", "lettuce_1"), ("pick", "lettuce_1"),
                    ("place", "lettuce_1", "bowl_1"), ("goto", "tomato_1"), ("pick", "tomato_1"),
                    ("place", "tomato_1", "bowl_1"), ("goto", "dining_table_1"), ("place", "bowl_1", "dining_table_1")]),
    dict(id="t14_salad_2957", family="salad", house=2957, start_room="bedroom_1",
         table="dining_table_2", table_text="the dining table in the living room",
         reference=[("goto", "tomato_2"), ("pick", "tomato_2"), ("goto", "lettuce_1"), ("pick", "lettuce_1"),
                    ("place", "lettuce_1", "bowl_1"), ("place", "tomato_2", "bowl_1"), ("pick", "bowl_1"),
                    ("goto", "dining_table_2"), ("place", "bowl_1", "dining_table_2")]),
    # Laundry: the only house with a washing machine and a dryer.
    dict(id="t15_laundry_811", family="laundry", house=811, start_room="kitchen_1"),
    # Clearing a table: more things than two hands, so several trips or stacking.
    dict(id="t16_clear_table_2957", family="clear_table", house=2957, start_room="bedroom_2",
         table="dining_table_1", dishes=["bowl_1", "plate_1", "cup_1"], food=["lettuce_1", "potato_3"],
         instruction="Clear the kitchen table: dishes go on the counter, food goes in the fridge.",
         reference=[("goto", "cup_1"), ("pick", "cup_1"), ("goto", "bowl_1"), ("place", "cup_1", "bowl_1"),
                    ("pick", "bowl_1"), ("goto", "plate_1"), ("pick", "plate_1"),
                    ("goto", "counter_top_1"), ("place", "bowl_1", "counter_top_1"), ("place", "plate_1", "counter_top_1"),
                    ("goto", "lettuce_1"), ("pick", "lettuce_1"), ("goto", "potato_3"), ("pick", "potato_3"),
                    ("goto", "fridge_1"), ("open", "fridge_1"), ("place", "lettuce_1", "fridge_1"),
                    ("place", "potato_3", "fridge_1"), ("close", "fridge_1")]),
    dict(id="t17_clear_table_2927", family="clear_table", house=2927, start_room="living_room_1",
         table="dining_table_2", dishes=["bowl_2", "cup_1", "cup_2"],
         instruction="Clear the dishes off the kitchen table and put them on the kitchen counter.",
         reference=[("goto", "cup_1"), ("pick", "cup_1"), ("goto", "cup_2"), ("pick", "cup_2"),
                    ("goto", "bowl_2"), ("place", "cup_1", "bowl_2"), ("place", "cup_2", "bowl_2"), ("pick", "bowl_2"),
                    ("goto", "counter_top_1"), ("place", "bowl_2", "counter_top_1")]),
    # Infeasible: the appliance the task needs isn't in the house.
    dict(id="t18_coffee_no_machine_2957", family="coffee", house=2957, start_room="bedroom_1",
         cup="cup_2", sofa="sofa_1", infeasible=True),
    dict(id="t19_toast_no_toaster_1078", family="toast", house=1078, start_room="bedroom_2", bread="bread_1",
         table="dining_table_1", table_text="the dining table", serve=[], infeasible=True),
]


def open_spot(scene, room):
    """The point in room farthest from any obstacle."""
    polygon = next(r["polygon"] for r in scene.rooms if r["id"] == room)
    gx, gy = np.meshgrid(scene.xs, scene.ys, indexing="ij")
    clearance = np.where(points_in_polygon(gx, gy, polygon), scene.clearance, 0.0)
    ix, iy = np.unravel_index(np.argmax(clearance), clearance.shape)
    return [round(float(scene.xs[ix]), 2), round(float(scene.ys[iy]), 2)]


def run_reference(episode, steps):
    state = world.world(new_state(episode))
    for step in steps:
        if step[0] == "goto":
            result = world.goto(episode, state, step[1], step[2] if len(step) > 2 else None)
            ok = result["reached"]
        else:
            result = world.act(episode, state, *step)
            ok = result.get("done")
        if not ok:
            return state, f"{step}: {result.get('reason')}"
    state["submitted"] = True
    return state, None


def build(task):
    scene_path = f"scenes/procthor/train_{task['house']}/scene.yaml"
    scene = Scene.load(REPO_ROOT / scene_path)
    instruction, goals, reference = FAMILIES[task["family"]](task, scene)
    episode = {
        "id": task["id"], "category": "infeasible" if task.get("infeasible") else task["family"],
        "scene": scene_path, "instruction": instruction,
        "start": open_spot(scene, task["start_room"]), "heading": 0,
        "max_walks": 20, "max_actions": 40,
    }
    if task.get("infeasible"):
        episode["expect_infeasible"] = True
    else:
        episode["goals"] = goals
        episode["reference"] = [list(step) for step in reference]
    return episode


def check(episode):
    if episode.get("expect_infeasible"):
        return "infeasible (not run)"
    state, error = run_reference(episode, episode["reference"])
    if error:
        return f"FAIL reference stopped at {error}"
    metrics = score_goals(episode, state)
    if not metrics["success"]:
        return f"FAIL {metrics}"
    return f"ok: {len(state['legs'])} legs, {metrics['actions']} actions, {metrics['route_length']} m"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--views", action="store_true", help="render views with AI2-THOR")
    parser.add_argument("--only", nargs="*", help="task ids to build")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    failed = False
    for task in TASKS:
        if args.only and task["id"] not in args.only:
            continue
        episode = build(task)
        result = check(episode)
        print(f"{episode['id']:30} {result}")
        if result.startswith("FAIL"):
            failed = True
            continue
        path = OUT / f"{episode['id']}.yaml"
        if not args.views and path.exists():
            # Keep views rendered earlier; the start and the scene are unchanged.
            old = yaml.safe_load(path.read_text())
            if old.get("views") and old.get("start") == episode["start"]:
                episode["views"] = old["views"]
        path.write_text(yaml.safe_dump(episode, sort_keys=False, default_flow_style=None, width=140))
        if args.views:
            out = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "export_procthor.py"), "views", str(path)],
                capture_output=True, text=True,
            ).stdout
            if "views:" not in out:
                print(f"  views FAILED for {episode['id']}")
                failed = True
                continue
            episode["views"] = [line.strip()[2:] for line in out.split("views:", 1)[1].splitlines() if line.strip()]
            path.write_text(yaml.safe_dump(episode, sort_keys=False, default_flow_style=None, width=140))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
