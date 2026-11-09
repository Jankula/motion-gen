"""Symbolic interaction (world.py) and long-horizon goal scoring (goals.py), on a small kitchen."""

import pytest
import yaml

from motiongen import world
from motiongen.goals import score_goals
from motiongen.navigation import new_state


def box(id_, label, center, size, **flags):
    return {"id": id_, "label": label, "color": "gray", "center": list(center), "size": list(size), **flags}


KITCHEN = {
    "name": "kitchen",
    "room": {"x": [0.0, 8.0], "y": [0.0, 5.0], "height": 2.6},
    "objects": [
        box("fridge_1", "fridge", (0.5, 4.4, 0.9), (0.8, 0.8, 1.8), openable=True, receptacle=True,
            open_box={"center": [0.9, 3.9, 0.9], "size": [1.6, 1.8, 1.8]}),
        box("egg_1", "egg", (0.5, 4.4, 0.8), (0.05, 0.05, 0.06), pickupable=True, inside="fridge_1"),
        box("counter_1", "counter top", (4.0, 4.6, 0.45), (3.0, 0.8, 0.9), receptacle=True),
        box("microwave_1", "microwave", (4.5, 4.6, 1.05), (0.5, 0.4, 0.3), openable=True, receptacle=True,
            toggleable=True, supported_by="counter_1",
            open_box={"center": [4.5, 4.3, 1.05], "size": [0.5, 0.9, 0.3]}),
        box("bowl_1", "bowl", (3.2, 4.6, 0.95), (0.2, 0.2, 0.1), pickupable=True, receptacle=True,
            supported_by="counter_1"),
        box("mug_1", "mug", (3.6, 4.6, 0.95), (0.1, 0.1, 0.1), pickupable=True, receptacle=True,
            supported_by="counter_1"),
        box("cup_1", "cup", (3.8, 4.6, 0.95), (0.1, 0.1, 0.1), pickupable=True, receptacle=True,
            supported_by="counter_1"),
        box("table_1", "dining table", (6.5, 1.5, 0.4), (1.2, 0.8, 0.8), receptacle=True),
        box("chair_1", "chair", (6.5, 0.6, 0.4), (0.5, 0.5, 0.8), receptacle=True),
        box("sink_1", "sink", (2.2, 4.6, 0.45), (0.6, 0.6, 0.9), receptacle=True),
    ],
}


@pytest.fixture
def episode(tmp_path):
    path = tmp_path / "kitchen.yaml"
    path.write_text(yaml.safe_dump(KITCHEN))
    return {"id": "k", "scene": str(path), "start": [2.0, 1.0], "goals": {
        "events": [
            {"id": "got_egg", "pick": "egg"},
            {"id": "cooked", "use": "microwave", "containing": "egg"},
            {"id": "served", "place": ["bowl", "dining table"]},
            {"id": "ate", "goto": ["chair", "dining table"], "intent": "sit"},
        ],
        "order": [["got_egg", "cooked"], ["cooked", "served"], ["served", "ate"]],
        "final": [{"closed": "fridge"}, {"closed": "microwave"}, {"holding": "nothing"},
                  {"on": ["bowl", "dining table"]}],
    }}


def run(episode, state, steps):
    results = []
    for step in steps:
        if step[0] == "goto":
            results.append(world.goto(episode, state, step[1], step[2] if len(step) > 2 else None))
        else:
            results.append(world.act(episode, state, *step))
    return results


BREAKFAST = [
    ("goto", "fridge_1"), ("open", "fridge_1"), ("pick", "egg"), ("close", "fridge_1"),
    ("goto", "bowl_1"), ("pick", "bowl_1"), ("place", "egg_1", "bowl_1"),
    ("goto", "microwave_1"), ("open", "microwave_1"), ("place", "bowl_1", "microwave_1"),
    ("close", "microwave_1"), ("use", "microwave_1"), ("open", "microwave_1"), ("pick", "bowl_1"),
    ("close", "microwave_1"), ("goto", "table_1"), ("place", "bowl_1", "table_1"), ("goto", "chair_1", "sit"),
]


def test_breakfast_succeeds_and_hands_off_actions_per_leg(episode):
    state = world.world(new_state(episode))
    results = run(episode, state, BREAKFAST)
    assert all(r.get("reached", r.get("done")) for r in results), results
    state["submitted"] = True
    metrics = score_goals(episode, state)
    assert metrics["success"] and metrics["goal_fraction"] == 1.0
    # The use recorded the egg inside the bowl inside the microwave.
    use = next(e for e in state["events"] if e["action"] == "use")
    assert set(use["contents"]) == {"bowl_1", "egg_1"}
    # Each leg carries the actions done where it ends, for the motion side.
    # Here the fridge door swept over the person, who stepped back (a short "stand" leg).
    assert [a["action"] for a in state["legs"][0]["actions"]] == ["open"]
    assert state["legs"][1]["intent"] == "stand"
    assert [a["action"] for a in state["legs"][1]["actions"]] == ["pick", "close"]


def test_contents_are_hidden_until_opened(episode):
    state = world.world(new_state(episode))
    run(episode, state, [("goto", "fridge_1")])
    assert world.act(episode, state, "pick", "egg_1")["done"] is False
    opened = world.act(episode, state, "open", "fridge_1")
    assert [c["id"] for c in opened["contents"]] == ["egg_1"]
    # Opening swung the door over the person, who stepped back to free floor.
    scene = world.scene_for(episode, state)
    assert scene.clearance_at(*state["position"]) >= scene.body_radius
    assert world.act(episode, state, "pick", "egg_1")["done"]


def test_reach_and_hands_are_limited(episode):
    state = world.world(new_state(episode))
    assert "out of reach" in world.act(episode, state, "pick", "mug_1")["reason"]
    run(episode, state, [("goto", "mug_1"), ("pick", "mug_1"), ("pick", "bowl_1")])
    assert "hands are full" in world.act(episode, state, "pick", "cup_1")["reason"]
    assert world.act(episode, state, "place", "mug_1", "counter_1")["done"]
    assert world.act(episode, state, "pick", "mug_1")["done"]


def test_rules_for_open_place_and_use(episode):
    state = world.world(new_state(episode))
    run(episode, state, [("goto", "bowl_1"), ("pick", "bowl_1"), ("goto", "microwave_1")])
    assert "open microwave_1 first" in world.act(episode, state, "place", "bowl_1", "microwave_1")["reason"]
    assert "can't be picked up" in world.act(episode, state, "pick", "counter_1")["reason"]
    run(episode, state, [("open", "microwave_1")])
    assert "close microwave_1" in world.act(episode, state, "use", "microwave_1")["reason"]


def test_carried_contents_move_with_their_container(episode):
    state = world.world(new_state(episode))
    run(episode, state, [
        ("goto", "fridge_1"), ("open", "fridge_1"), ("pick", "egg_1"), ("goto", "bowl_1"), ("pick", "bowl_1"),
        ("place", "egg_1", "bowl_1"), ("goto", "table_1"), ("place", "bowl_1", "table_1"),
    ])
    scene = world.scene_for(episode, state)
    bowl, egg = scene.get("bowl_1"), scene.get("egg_1")
    assert bowl.support == "table_1" and egg.inside == "bowl_1"
    assert egg.center[:2] == pytest.approx(bowl.center[:2])
    assert bowl.z_range[0] == pytest.approx(scene.get("table_1").z_range[1])


def test_partial_run_scores_a_fraction_and_names_what_failed(episode):
    state = world.world(new_state(episode))
    run(episode, state, BREAKFAST[:3] + [("goto", "bowl_1"), ("pick", "bowl_1"), ("goto", "table_1"),
                                         ("place", "bowl_1", "table_1")])
    state["submitted"] = True
    metrics = score_goals(episode, state)
    assert not metrics["success"]
    assert metrics["events_missing"] == ["cooked", "ate"]
    assert {"closed": "fridge"} in metrics["final_failed"]
    assert 0 < metrics["goal_fraction"] < 1


def test_order_violation_is_reported(episode):
    episode["goals"]["order"] = [["served", "got_egg"]]
    state = world.world(new_state(episode))
    run(episode, state, BREAKFAST)
    assert score_goals(episode, state)["order_violations"] == [["served", "got_egg"]]


def test_a_task_without_goals_is_unscored(episode):
    del episode["goals"]
    state = world.world(new_state(episode))
    run(episode, state, [("goto", "bowl_1"), ("pick", "bowl_1")])
    metrics = score_goals(episode, state)
    assert metrics["success"] is None and metrics["actions"] == 1 and metrics["collision_free"]


def test_walking_somewhere_reveals_small_things_nearby(episode):
    state = world.world(new_state(episode))
    result = world.goto(episode, state, "bowl_1")
    seen = {o["id"] for o in result["seen"]}
    assert {"bowl_1", "mug_1", "cup_1", "counter_1"} <= seen
    assert "egg_1" not in seen  # inside the closed fridge
    assert "table_1" not in seen  # too far away
    assert "mug_1" in state["seen"]


def test_things_on_a_carried_plate_travel_with_it(tmp_path):
    kitchen = {**KITCHEN, "objects": KITCHEN["objects"] + [
        box("plate_1", "plate", (4.6, 4.5, 0.91), (0.25, 0.25, 0.02), pickupable=True, receptacle=True,
            supported_by="counter_1"),
    ]}
    path = tmp_path / "kitchen.yaml"
    path.write_text(yaml.safe_dump(kitchen))
    episode = {"id": "k", "scene": str(path), "start": [2.0, 1.0]}
    state = world.world(new_state(episode))
    run(episode, state, [
        ("goto", "mug_1"), ("pick", "mug_1"), ("goto", "plate_1"), ("place", "mug_1", "plate_1"),
        ("pick", "plate_1"), ("goto", "table_1"), ("place", "plate_1", "table_1"),
    ])
    scene = world.scene_for(episode, state)
    plate, mug = scene.get("plate_1"), scene.get("mug_1")
    assert plate.support == "table_1" and mug.support == "plate_1"
    assert mug.center[:2] == pytest.approx(plate.center[:2])
    assert mug.z_range[0] == pytest.approx(plate.z_range[1])
