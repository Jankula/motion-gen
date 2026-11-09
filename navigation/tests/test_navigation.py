import pytest
import numpy as np

from motiongen.astar import goal_mask, plan, point_goal_mask
from motiongen.metrics import score_episode
from motiongen.navigation import new_state, walk_to
from motiongen.path_check import check_path, path_length
from motiongen.render_map import render_overlay
from motiongen.scene import BODY_RADIUS, RESOLUTION, Box, Scene


def make_scene(*objects):
    return Scene("test", (0.0, 6.0), (0.0, 4.0), 2.6, objects)


TABLE = Box("table_1", "table", "brown", (3.0, 2.0, 0.375), (1.0, 1.0, 0.75))
OTHER_TABLE = Box("table_2", "table", "brown", (5.2, 2.0, 0.375), (0.6, 0.6, 0.75))
SPLIT_WALL = Box("wall_1", "wall", "gray", (1.5, 2.0, 1.0), (0.2, 4.0, 2.0))
HIDDEN_WALL = Box("wall_9", "wall", "gray", (1.5, 2.0, 1.0), (0.2, 4.0, 2.0), hidden=True)
EPISODE = {"start": [0.5, 2.0], "stops": [["table_1"]]}


def test_occupancy_matches_box():
    scene = make_scene(TABLE)
    assert scene.clearance_at(3.0, 2.0) == 0.0
    assert scene.nearest_obstacle(3.0, 2.0) == "table_1"
    assert scene.clearance_at(4.0, 2.0) == pytest.approx(0.5, abs=RESOLUTION)
    assert scene.clearance_at(1.0, 2.0) == pytest.approx(1.0, abs=RESOLUTION)


def test_clearance_includes_walls_and_outside_is_blocked():
    scene = make_scene()
    assert scene.clearance_at(0.3, 2.0) == pytest.approx(0.3, abs=RESOLUTION)
    assert scene.nearest_obstacle(0.3, 2.0) == "wall"
    assert scene.clearance_at(-1.0, 2.0) == 0.0
    assert scene.nearest_obstacle(-1.0, 2.0) == "wall"


def test_overhead_object_does_not_block_body():
    lamp = Box("lamp", "lamp", "gold", (3.0, 2.0, 2.2), (0.4, 0.4, 0.3))
    scene = make_scene(lamp)
    assert not lamp.blocks_body()
    assert scene.clearance_at(3.0, 2.0) > 1.0


def test_supported_by_relation():
    mug = Box("mug", "mug", "red", (3.0, 2.0, 0.8), (0.1, 0.1, 0.1))
    scene = make_scene(TABLE, mug)
    assert scene.supported_by(mug) == "table_1"
    assert scene.supported_by(TABLE) is None


def test_hidden_object_blocks_but_is_not_public():
    scene = make_scene(TABLE, HIDDEN_WALL)
    assert scene.clearance_at(1.5, 2.0) == 0.0
    assert "wall_9" not in scene.public_ids()
    assert "wall_9" not in [o["id"] for o in scene.graph()["objects"]]


def test_path_length():
    assert path_length([[0, 0], [3, 4], [3, 5]]) == pytest.approx(6.0)


def test_colliding_path_reports_first_contact():
    scene = make_scene(TABLE)
    result = check_path(scene, [[0.5, 2.0], [5.5, 2.0]])
    assert not result["collision_free"]
    assert result["first_collision"]["object"] == "table_1"
    assert result["first_collision"]["x"] == pytest.approx(2.5 - BODY_RADIUS, abs=2 * RESOLUTION)
    assert result["min_clearance"] < 0


def test_clear_path_reports_clearance():
    scene = make_scene(TABLE)
    result = check_path(scene, [[1.0, 0.75], [5.0, 0.75]])
    assert result["collision_free"]
    assert result["first_collision"] is None
    # The table's near edge and the wall are both 0.75 m from the centreline,
    # so the body surface passes 0.5 m from each.
    assert result["min_clearance"] == pytest.approx(0.5, abs=RESOLUTION)


def test_astar_routes_around_obstacle_to_goal_band():
    wall = Box("wall_1", "wall", "gray", (1.5, 1.5, 1.0), (0.2, 3.0, 2.0))
    scene = make_scene(TABLE, wall)
    points = plan(scene, [0.5, 1.0], goal_mask(scene, TABLE, 0.2, 0.7))
    assert points is not None
    assert check_path(scene, points)["collision_free"]
    assert 0.2 <= TABLE.footprint_distance(*points[-1]) <= 0.7
    assert max(y for _, y in points) > 3.0  # had to go over the wall


def test_astar_returns_none_when_blocked():
    scene = make_scene(TABLE, SPLIT_WALL)
    assert plan(scene, [0.5, 2.0], goal_mask(scene, TABLE, 0.2, 0.7)) is None


def test_astar_to_point():
    scene = make_scene(TABLE)
    points = plan(scene, [0.5, 2.0], point_goal_mask(scene, 1.5, 1.0))
    assert points[-1] == pytest.approx([1.5, 1.0], abs=0.11)


def test_walk_to_updates_position_and_chains_legs():
    scene = make_scene(TABLE, OTHER_TABLE)
    state = new_state(EPISODE)
    assert walk_to(scene, state, "table_1")["reached"]
    first_end = state["position"]
    assert walk_to(scene, state, "table_2")["reached"]
    assert state["legs"][1]["points"][0] == first_end


def test_walk_to_failure_leaves_body_in_place():
    scene = make_scene(TABLE, SPLIT_WALL)
    state = new_state(EPISODE)
    result = walk_to(scene, state, "table_1")
    assert not result["reached"]
    assert state["position"] == EPISODE["start"]
    assert state["legs"] == []
    assert state["attempts"] == ["table_1"]


def test_walk_to_rejects_unknown_and_hidden_targets():
    scene = make_scene(TABLE, HIDDEN_WALL)
    state = new_state(EPISODE)
    assert "unknown" in walk_to(scene, state, "nonsense")["reason"]
    assert "unknown" in walk_to(scene, state, "wall_9")["reason"]


def walked(scene, *targets):
    state = new_state(EPISODE)
    for target in targets:
        walk_to(scene, state, target)
    state["submitted"] = True
    return state


def test_score_success_on_correct_stop():
    scene = make_scene(TABLE, OTHER_TABLE)
    metrics = score_episode(scene, EPISODE, walked(scene, "table_1"))
    assert metrics["success"]
    assert metrics["stops_completed"] == "1/1"
    # A* stops on entering the band, 0.7 m from the table edge at x=2.5.
    assert metrics["route_length"] == pytest.approx(1.3, abs=2 * RESOLUTION)


def test_score_wrong_target_fails():
    scene = make_scene(TABLE, OTHER_TABLE)
    episode = {**EPISODE, "stops": [["table_2"]]}
    metrics = score_episode(scene, episode, walked(scene, "table_1"))
    assert not metrics["success"]
    assert metrics["stops_completed"] == "0/1"


def test_score_requires_stop_order():
    scene = make_scene(TABLE, OTHER_TABLE)
    episode = {**EPISODE, "stops": [["table_1"], ["table_2"]]}
    assert score_episode(scene, episode, walked(scene, "table_1", "table_2"))["success"]
    assert not score_episode(scene, episode, walked(scene, "table_2", "table_1"))["success"]


def test_score_must_finish_at_last_stop():
    scene = make_scene(TABLE, OTHER_TABLE)
    metrics = score_episode(scene, EPISODE, walked(scene, "table_1", "table_2"))
    assert metrics["stops_completed"] == "1/1"
    assert not metrics["success"]


def test_score_infeasible_only_succeeds_when_expected():
    scene = make_scene(TABLE)
    state = walked(scene)
    state["infeasible"] = True
    assert score_episode(scene, {**EPISODE, "stops": None, "expect_infeasible": True}, state)["success"]
    assert not score_episode(scene, EPISODE, state)["success"]
    assert not score_episode(scene, {"start": [0.5, 2.0], "expect_infeasible": True}, walked(scene))["success"]


def test_score_collision_fails_route():
    scene = make_scene(TABLE, Box("box", "box", "gray", (1.2, 2.0, 0.5), (0.4, 0.4, 1.0)))
    state = new_state(EPISODE)
    state["legs"] = [{"target": "table_1", "points": [[0.5, 2.0], [2.0, 2.0]]}]
    metrics = score_episode(scene, EPISODE, state)
    assert not metrics["collision_free"]
    assert not metrics["success"]


def test_target_behind_wall_is_not_reached_through_it():
    desk = Box("desk", "desk", "brown", (3.0, 1.0, 0.375), (1.0, 0.6, 0.75))
    wall = Box("wall_1", "wall", "gray", (3.0, 1.5, 1.25), (6.0, 0.2, 2.5))
    scene = make_scene(desk, wall)
    state = {**new_state({"start": [3.0, 2.5]})}
    # Beyond the wall, the desk is under 0.7 m away but out of reach.
    result = walk_to(scene, state, "desk")
    assert not result["reached"]


def test_target_poking_through_wall_is_not_reached_from_the_other_side():
    # The toilet's box reaches 0.1 m past the wall (y 1.4 to 1.6) into the room the person is in.
    toilet = Box("toilet", "toilet", "white", (3.0, 1.1, 0.4), (0.6, 1.0, 0.8))
    wall = Box("wall_1", "wall", "gray", (3.0, 1.5, 1.25), (6.0, 0.1, 2.5))
    scene = make_scene(toilet, wall)
    assert not goal_mask(scene, toilet, 0.2, 0.7)[scene.cell(3.0, 2.0)]
    assert goal_mask(scene, toilet, 0.2, 0.7)[scene.cell(3.0, 0.4)]


def test_low_object_does_not_block_reaching_over_it():
    chair = Box("chair", "chair", "tan", (3.0, 2.8, 0.4), (0.4, 0.2, 0.8))
    scene = make_scene(TABLE, chair)
    assert goal_mask(scene, TABLE, 0.2, 0.7)[scene.cell(3.0, 3.1)]


def max_turn_degrees(points):
    points = np.asarray(points)
    headings = np.arctan2(*np.diff(points, axis=0).T[::-1])
    turns = np.abs(np.angle(np.exp(1j * np.diff(headings))))
    return np.degrees(turns.max())


def test_route_around_obstacle_is_smooth_and_collision_free():
    wall = Box("wall_1", "wall", "gray", (2.0, 1.5, 1.0), (0.2, 3.0, 2.0))
    scene = make_scene(TABLE, wall)
    points = plan(scene, [0.8, 1.0], goal_mask(scene, TABLE, 0.2, 0.7))
    assert check_path(scene, points)["collision_free"]
    assert max_turn_degrees(points) < 15
    assert points[0] == [0.8, 1.0]
    assert 0.2 <= TABLE.footprint_distance(*points[-1]) <= 0.7


def test_route_still_passes_narrow_gap():
    lower = Box("wall_1", "wall", "gray", (2.0, 1.0, 1.0), (0.2, 2.0, 2.0))
    upper = Box("wall_2", "wall", "gray", (2.0, 3.35, 1.0), (0.2, 1.3, 2.0))
    scene = make_scene(lower, upper)
    points = plan(scene, [1.0, 1.0], point_goal_mask(scene, 3.0, 1.0))
    assert points is not None
    assert check_path(scene, points)["collision_free"]


def test_overlay_caption_adds_band_and_handles_empty_route():
    scene = make_scene(TABLE)
    plain = render_overlay(scene, [0.5, 2.0], [], None)
    short = render_overlay(scene, [0.5, 2.0], [], None, "Walk to the table.")
    long = render_overlay(scene, [0.5, 2.0], [], None, "Walk to the table. " * 30)
    assert short.width == plain.width
    assert plain.height < short.height < long.height


def test_scene_json_is_compact_and_valid():
    import json
    from motiongen.cli import scene_json
    data = {"room": {"x": [0, 1]}, "objects": [{"id": "a", "size": [1, 2]}, {"id": "b"}], "rooms": []}
    text = scene_json(data)
    assert json.loads(text) == data
    assert text.count("\n") == 7  # one line per object
