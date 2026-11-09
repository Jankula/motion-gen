"""The motion hand-off (motion_script.py): subtasks, segments, hands, object timeline, partner tasks."""

import math

import numpy as np
import pytest
import yaml

from motiongen import world
from motiongen.goals import score_goals
from motiongen.motion_script import (
    build_script, from_partner, heading_from_partner, heading_to_partner, simplify, to_partner,
)
from motiongen.navigation import new_state
from motiongen.observe import assign_marks
from motiongen.path_check import sample_path
from motiongen.render_map import render_motion_route
from test_world import BREAKFAST, KITCHEN, run

PARTNER_TASK_KEYS = {"name", "title", "instruction", "fps", "frames", "start", "end", "path", "obstacles"}


@pytest.fixture
def episode(tmp_path):
    path = tmp_path / "kitchen.yaml"
    path.write_text(yaml.safe_dump(KITCHEN))
    return {"id": "k", "scene": str(path), "start": [2.0, 1.0], "instruction": "make breakfast"}


def breakfast_with_steps(episode):
    state = world.world(new_state(episode))
    world.declare_step(state, "get an egg from the fridge")
    run(episode, state, BREAKFAST[:4])
    world.declare_step(state, "cook the egg in a bowl")
    run(episode, state, BREAKFAST[4:15])
    world.declare_step(state, "eat at the table")
    run(episode, state, BREAKFAST[15:])
    return state


def test_frames_round_trip_and_stay_right_handed():
    assert from_partner(*to_partner(1.5, -2.25)) == pytest.approx([1.5, -2.25])
    for heading in (-170.0, -90.0, 0.0, 45.0, 90.0, 179.0):
        assert heading_from_partner(heading_to_partner(heading)) == pytest.approx(heading, abs=0.1)
        # The direction we face, mapped to [X, Z], is the one the partner's heading faces
        # (their walking/walkenv/tasks.py: heading_vector(deg) = [sin, cos]).
        ours = (math.cos(math.radians(heading)), math.sin(math.radians(heading)))
        theirs = math.radians(heading_to_partner(heading))
        assert to_partner(*ours) == pytest.approx([math.sin(theirs), math.cos(theirs)], abs=2e-3)
    # Facing +x is their 90 (+X); turning left raises the heading in both frames.
    assert heading_to_partner(0.0) == 90.0 and heading_to_partner(10.0) == 100.0


def test_simplify_keeps_only_the_corners():
    leg = [[x / 10, 0.0] for x in range(31)] + [[3.0, y / 10] for y in range(1, 21)]
    simple = simplify(leg, 0.03)
    assert simple.tolist() == [[0.0, 0.0], [3.0, 0.0], [3.0, 2.0]]


def test_breakfast_becomes_subtasks_of_motion_segments(episode):
    state = breakfast_with_steps(episode)
    script, tasks = build_script(episode, state)
    segments = script["segments"]

    assert [s["text"] for s in script["subtasks"]] == [
        "get an egg from the fridge", "cook the egg in a bowl", "eat at the table"]
    assert all(s["source"] == "agent" for s in script["subtasks"])
    covered = [i for s in script["subtasks"] for i in s["segments"]]
    assert covered == list(range(len(segments)))

    motions = [s["motion"] for s in segments if s["motion"] != "turn"]
    assert motions[:5] == ["walk", "open", "step_back", "reach_grasp", "close"]
    assert motions[-2:] == ["walk", "sit_down"]
    assert {"put_down", "use"} <= set(motions)
    # Each turn on the spot leaves the person facing where the next walk's task starts.
    for seg in segments:
        if seg["motion"] == "turn" and segments[seg["i"] + 1]["motion"] == "walk":
            task = tasks[segments[seg["i"] + 1]["partner_task"].split("/")[-1]]
            assert heading_to_partner(seg["to_heading"]) == pytest.approx(task["start"]["heading_deg"], abs=0.2)

    # Hands: the egg goes in the right hand, the bowl in the left, and the egg into the held bowl.
    pick_egg = next(s for s in segments if s["motion"] == "reach_grasp" and s["object"] == "egg_1")
    pick_bowl = next(s for s in segments if s["motion"] == "reach_grasp" and s["object"] == "bowl_1")
    egg_in_bowl = next(s for s in segments if s["motion"] == "put_down" and s["object"] == "egg_1")
    assert (pick_egg["hand"], pick_bowl["hand"], egg_in_bowl["hand"]) == ("right", "left", "right")
    assert egg_in_bowl.get("into_held")
    assert pick_egg["height"] == pytest.approx(0.8, abs=0.05)
    sit = segments[-1]
    assert sit["object"] == "chair_1" and sit["seat"][2] <= 0.8

    # Every attach is undone by a detach (the person ends holding nothing), in order.
    held = {}
    for change in script["objects"]:
        if change["change"] == "attach":
            held[change["object"]] = change["segment"]
        elif change["change"] == "detach":
            assert held.pop(change["object"]) < change["segment"]
    assert not held

    # Times add up and the walks carry what is held.
    assert segments[0]["t_est"][0] == 0 and segments[-1]["t_est"][1] == pytest.approx(script["duration_est"])
    walk_to_table = next(s for s in segments if s["motion"] == "walk" and s["target"] == "table_1")
    assert walk_to_table["carrying"] == {"right": "bowl_1"} and "carrying the bowl with an egg" in walk_to_table["caption"]


def test_each_walk_is_a_partner_task(episode):
    state = breakfast_with_steps(episode)
    script, tasks = build_script(episode, state)
    walks = [s for s in script["segments"] if s["motion"] == "walk"]
    assert len(tasks) == len(walks)
    for seg in walks:
        task = tasks[seg["partner_task"].split("/")[-1]]
        assert PARTNER_TASK_KEYS <= set(task)
        assert task["start"]["state"] == task["end"]["state"] == "standing"
        assert task["start"]["position"] == to_partner(*seg["from"])
        assert task["end"]["position"] == to_partner(*seg["to"])
        assert task["end"]["heading_deg"] == heading_to_partner(seg["end_heading"])
        assert task["frames"] >= seg["duration_est"] * task["fps"]
        # The simplified path stays within the tolerance of the walked one.
        points = np.array([from_partner(*p) for p in task["path"]["points"]])
        walked = np.asarray(seg["path"])
        gaps = [np.min(np.linalg.norm(walked - p, axis=1)) for p in sample_path(points)]
        assert max(gaps) <= task["path"]["tolerance_m"]
        for obstacle in task["obstacles"]:
            assert set(obstacle) == {"label", "center", "size", "yaw_deg"} and obstacle["size"][1] > 0


def test_without_steps_subtasks_are_derived_per_walk(episode):
    state = world.world(new_state(episode))
    run(episode, state, BREAKFAST)
    script, _ = build_script(episode, state)
    texts = [s["text"] for s in script["subtasks"]]
    assert texts[0] == "walk to the fridge, open the fridge, pick up the egg, close the fridge"
    assert texts[-1] == "walk to the chair, sit down on the chair"
    assert all(s["source"] == "derived" for s in script["subtasks"])


def test_mg_step_tags_what_follows_and_is_not_an_action(episode):
    state = world.world(new_state(episode))
    world.declare_step(state, "fetch the mug")
    run(episode, state, [("goto", "mug_1"), ("pick", "mug_1")])
    assert state["legs"][-1]["step"] == 1
    assert [e.get("step") for e in state["events"]] == [1, 1, 1]
    assert score_goals({**episode, "goals": {}}, state)["actions"] == 1


def test_a_navigation_run_without_events_still_gives_segments(episode):
    state = world.world(new_state(episode))
    run(episode, state, [("goto", "chair_1", "sit")])
    legs_only = {"position": state["position"], "legs": state["legs"], "attempts": state["attempts"],
                 "submitted": True, "infeasible": False, "reason": None}
    script, tasks = build_script(episode, legs_only)
    assert [s["motion"] for s in script["segments"] if s["motion"] != "turn"] == ["walk", "sit_down"]
    assert len(tasks) == 1


def test_motion_route_image_draws(episode):
    state = breakfast_with_steps(episode)
    script, _ = build_script(episode, state)
    image = render_motion_route(world.scene_for(episode), script)
    assert image.width > 500 and image.height > 400


def test_marks_keep_their_numbers_as_views_are_added():
    first = assign_marks({"sofa_1", "table_1"})
    assert first == {"sofa_1": 1, "table_1": 2}
    later = assign_marks({"apple_1", "table_1", "zebra_1"}, first)
    assert later == {"sofa_1": 1, "table_1": 2, "apple_1": 3, "zebra_1": 4}
