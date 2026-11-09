import json
import sys

import numpy as np
import pytest
import yaml
from PIL import Image

from motiongen import procthor
from motiongen.astar import plan, point_goal_mask
from motiongen.navigation import REPO_ROOT, new_state, walk_to
from motiongen.observe import agent_scene, assign_marks, load_view, mark_view, visible_ids
from motiongen.scene import Box, Scene

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from run_episode import audit_transcript  # noqa: E402

L_SHAPE = [{"id": "hall_1", "type": "hall", "polygon": [[0, 0], [6, 0], [6, 2], [3, 2], [3, 4], [0, 4]]}]
FRIDGE = {
    "id": "fridge_1", "label": "fridge", "color": "white",
    "center": [3.0, 0.4, 0.9], "size": [0.6, 0.6, 1.8],
    "openable": True, "open_box": {"center": [3.0, 2.0, 0.9], "size": [0.6, 4.0, 1.8]},
}
MILK = {"id": "milk_1", "label": "milk", "color": "white", "center": [3.0, 0.4, 0.5], "size": [0.1, 0.1, 0.2], "inside": "fridge_1"}
TABLE = Box("table_1", "table", "brown", (1.0, 1.0, 0.375), (0.6, 0.6, 0.75))


def write_scene(tmp_path, objects, rooms=None):
    data = {"name": "t", "room": {"x": [0, 6], "y": [0, 4], "height": 2.6}, "objects": objects}
    if rooms:
        data["rooms"] = rooms
    path = tmp_path / "scene.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_floor_polygon_blocks_the_missing_corner():
    scene = Scene("t", (0, 6), (0, 4), 2.6, [], rooms=L_SHAPE)
    assert scene.clearance_at(5.0, 3.0) == 0.0
    assert plan(scene, [1.0, 3.0], point_goal_mask(scene, 5.0, 3.0)) is None
    assert plan(scene, [1.0, 3.0], point_goal_mask(scene, 5.0, 1.0)) is not None
    assert scene.room_of(1.0, 1.0) == "hall_1"
    assert scene.room_of(5.0, 3.0) is None


def test_opened_door_takes_its_swept_footprint(tmp_path):
    path = write_scene(tmp_path, [FRIDGE])
    goal = lambda scene: point_goal_mask(scene, 5.0, 2.0)
    closed = Scene.load(path)
    assert plan(closed, [1.0, 2.0], goal(closed)) is not None
    opened = Scene.load(path, opened=["fridge_1"])
    assert opened.get("fridge_1").is_open
    assert plan(opened, [1.0, 2.0], goal(opened)) is None


def test_only_openable_objects_can_be_opened(tmp_path):
    path = write_scene(tmp_path, [FRIDGE, MILK])
    with pytest.raises(ValueError):
        Scene.load(path, opened=["milk_1"])


def test_contents_of_closed_containers_are_not_listed(tmp_path):
    path = write_scene(tmp_path, [FRIDGE, MILK])
    closed = Scene.load(path)
    assert "milk_1" not in closed.public_ids()
    assert [o["id"] for o in closed.graph()["objects"]] == ["fridge_1"]
    entry = closed.graph()["objects"][0]
    assert entry["openable"] and not entry["is_open"]
    opened = Scene.load(path, opened=["fridge_1"])
    milk = next(o for o in opened.graph()["objects"] if o["id"] == "milk_1")
    assert milk["inside"] == "fridge_1"


def test_explicit_support_wins_over_geometry():
    mug = Box("mug_1", "mug", "red", (1.0, 1.0, 0.8), (0.1, 0.1, 0.1), support="shelf_1")
    scene = Scene("t", (0, 6), (0, 4), 2.6, [TABLE, mug])
    assert scene.supported_by(mug) == "shelf_1"


def test_plain_scene_graph_is_unchanged():
    scene = Scene.load(REPO_ROOT / "scenes" / "s2_apartment.yaml")
    graph = scene.graph()
    assert set(graph) == {"room", "body", "objects"}
    assert set(graph["objects"][0]) == {"id", "label", "color", "center", "size", "blocks_body", "supported_by"}
    assert [o["id"] for o in scene.graph(visible={"sofa_1"})["objects"]] == ["sofa_1"]


def test_body_size_comes_from_the_episode(tmp_path):
    path = write_scene(tmp_path, [])
    scene = Scene.load(path, body={"radius": 0.3, "height": 1.8})
    assert scene.graph()["body"] == {"shape": "cylinder", "radius": 0.3, "height": 1.8}


def test_leg_records_intent_and_heading_toward_target():
    scene = Scene("t", (0, 6), (0, 4), 2.6, [TABLE])
    state = new_state({"start": [4.0, 1.0]})
    assert walk_to(scene, state, "table_1", "sit")["reached"]
    leg = state["legs"][0]
    assert leg["intent"] == "sit"
    # The table is in -x from wherever the person stops beside it.
    assert abs(leg["end_heading"]) > 90


def make_view(tmp_path, name, objects):
    directory = tmp_path / name
    directory.mkdir()
    Image.new("RGB", (60, 40), "white").save(directory / "rgb.png")
    (directory / "objects.json").write_text(json.dumps({"name": name, "objects": objects}))
    return directory


def test_views_list_marks_and_filter_small_objects(tmp_path):
    big = {"id": "table_1", "pixels": 500, "bbox": [0, 0, 20, 20], "centroid": [10, 10]}
    tiny = {"id": "mug_1", "pixels": 5, "bbox": [30, 5, 31, 6], "centroid": [30, 5]}
    view = load_view(make_view(tmp_path, "top", [big, tiny]))
    assert visible_ids([view]) == {"table_1"}
    marks = assign_marks({"table_1"})
    image = mark_view(view, marks)
    assert image.getpixel((10, 10)) != (255, 255, 255)


def test_agent_scene_lists_only_what_the_views_show(tmp_path):
    scene = Scene("t", (0, 6), (0, 4), 2.6, [TABLE, Box("sofa_1", "sofa", "gray", (4, 3, 0.4), (1, 1, 0.8))])
    view_dir = make_view(tmp_path, "ego", [{"id": "table_1", "pixels": 500, "bbox": [0, 0, 20, 20], "centroid": [10, 10]}])
    episode = {"start": [3, 2], "heading": 90, "views": [str(view_dir)]}
    result = agent_scene(scene, episode, tmp_path / "run")
    assert [o["id"] for o in result["objects"]] == ["table_1"]
    assert result["objects"][0]["mark"] == 1
    assert result["heading"] == 90
    assert (tmp_path / "run" / "views" / "ego.png").exists()


def tool_use(name, tool_input):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}})


def test_audit_allows_reading_only_the_view_images(tmp_path):
    lines = [
        tool_use("Bash", {"command": "mg goto sofa_1 --then sit"}),
        tool_use("Read", {"file_path": str(tmp_path / "views" / "top.png")}),
        tool_use("Read", {"file_path": str(tmp_path / "state.json")}),
        tool_use("Read", {"file_path": str(tmp_path / "views" / ".." / "state.json")}),
    ]
    calls, violations = audit_transcript(lines, tmp_path)
    assert calls == 4
    assert [v["input"]["file_path"] for v in violations] == [
        str(tmp_path / "state.json"), str(tmp_path / "views" / ".." / "state.json"),
    ]


def test_unity_conversions():
    assert procthor.to_ours({"x": 1.0, "y": 2.0, "z": 3.0}) == (1.0, 3.0, 2.0)
    assert procthor.split_label("CoffeeTable") == "coffee table"
    assert procthor.split_label("TVStand") == "tv stand"
    # Facing +x here is Unity yaw 90; facing +y here (Unity +z) is yaw 0.
    assert procthor.heading_to_unity_yaw(0) == 90
    assert procthor.heading_to_unity_yaw(90) == 0


def test_walls_are_cut_at_doors():
    corner = lambda x, z, y=0.0: {"x": x, "y": y, "z": z}
    wall = [corner(0, 2), corner(4, 2), corner(4, 2, 2.5), corner(0, 2, 2.5)]
    # Both rooms list the shared wall; it should come out once.
    house = {"walls": [{"polygon": wall}, {"polygon": list(reversed(wall))}]}
    door = ((2.0, 2.0, 1.0), (1.0, 0.1, 2.0))
    boxes = procthor.wall_boxes(house, [door])
    spans = sorted((b["center"][0] - b["size"][0] / 2, b["center"][0] + b["size"][0] / 2) for b in boxes)
    assert spans == [pytest.approx((0.0, 1.5)), pytest.approx((2.5, 4.0))]
    assert [b["id"] for b in boxes] == ["wall_1", "wall_2"]


def test_empty_walls_are_open():
    corner = lambda x, z, y=0.0: {"x": x, "y": y, "z": z}
    shared = [corner(0, 2), corner(4, 2), corner(4, 2, 2.5), corner(0, 2, 2.5)]
    outer = [corner(0, 0), corner(4, 0), corner(4, 0, 2.5), corner(0, 0, 2.5)]
    # An open-plan connection: one room lists the shared wall as empty, so neither copy is built.
    house = {"walls": [{"polygon": shared, "empty": True}, {"polygon": list(reversed(shared))}, {"polygon": outer}]}
    boxes = procthor.wall_boxes(house, [])
    assert [b["center"][1] for b in boxes] == [0.0]


def test_view_objects_from_segmentation():
    segmentation = np.zeros((4, 6, 3), dtype=np.uint8)
    segmentation[1:3, 2:5] = (10, 20, 30)
    segmentation[0, 0] = (1, 2, 3)  # floor, which isn't exported
    objects, ids_image = procthor.view_objects(segmentation, {(10, 20, 30): "Mug|1", (1, 2, 3): "Floor|0"}, {"Mug|1": "mug_1"})
    assert objects == [{"id": "mug_1", "pixels": 6, "bbox": [2, 1, 4, 2], "centroid": [3.0, 1.5]}]
    assert ids_image[1, 2, 0] == 1 and ids_image[0, 0, 0] == 0


def test_parts_fold_into_their_object():
    assert procthor.whole_object_id("TVStand|7|0|0___1") == "TVStand|7|0|0"
    assert procthor.is_folded_part({"objectId": "TVStand|7|0|0___1"})
    assert not procthor.is_folded_part({"objectId": "TVStand|7|0|0"})
    assert not procthor.is_folded_part({"objectId": "Dresser|4|3___0", "openable": True})  # a drawer
    # A shelf's colour and the stand's colour both count as the stand.
    segmentation = np.zeros((2, 2, 3), dtype=np.uint8)
    segmentation[0, :] = (5, 5, 5)
    segmentation[1, 0] = (6, 6, 6)
    objects, _ = procthor.view_objects(segmentation, {(5, 5, 5): "TVStand|1", (6, 6, 6): "TVStand|1"}, {"TVStand|1": "tv_stand_1"})
    assert [(o["id"], o["pixels"]) for o in objects] == [("tv_stand_1", 3)]
    stand = {"objectId": "TVStand|1", "axisAlignedBoundingBox": {"size": {"x": 1, "y": 1, "z": 1}}}
    small = {"axisAlignedBoundingBox": {"size": {"x": 0.1, "y": 0.1, "z": 0.1}}}
    remote = {**small, "objectId": "Remote|1", "parentReceptacles": ["TVStand|1___0"]}
    assert procthor.direct_parent(remote, {"TVStand|1": stand}) is stand
    drawer = {"objectId": "Dresser|1___0", "axisAlignedBoundingBox": {"size": {"x": 0.5, "y": 0.2, "z": 0.5}}}
    pen = {**small, "objectId": "Pen|1", "parentReceptacles": ["Dresser|1___0"]}
    assert procthor.direct_parent(pen, {"Dresser|1___0": drawer}) is drawer


def test_direct_parent_ignores_smaller_receptacles():
    def thing(thor_id, size, parents=()):
        return {"objectId": thor_id, "parentReceptacles": list(parents),
                "axisAlignedBoundingBox": {"size": {"x": size, "y": size, "z": size}}}

    mug = thing("Mug|1", 0.1)
    counter = thing("CounterTop|1", 2.0, parents=["Mug|1"])
    assert procthor.direct_parent(counter, {"Mug|1": mug}) is None


def test_direct_parent_is_the_smallest_receptacle():
    def thing(thor_id, size):
        return {"objectId": thor_id, "axisAlignedBoundingBox": {"size": {"x": size, "y": size, "z": size}}}

    counter, cabinet = thing("Counter|1", 2.0), thing("Cabinet|1", 0.5)
    mug = {**thing("Mug|1", 0.1), "parentReceptacles": ["Counter|1", "Cabinet|1", "Floor|0"]}
    assert procthor.direct_parent(mug, {"Counter|1": counter, "Cabinet|1": cabinet}) is cabinet


def test_badges_avoid_small_objects_and_each_other():
    from motiongen.observe import place_badges

    r = 7
    width, height = 200, 150
    big = {"centroid": [60, 60], "bbox": [20, 20, 100, 100]}
    mug = {"centroid": [150, 60], "bbox": [146, 56, 154, 64]}
    near = {"centroid": [152, 62], "bbox": [150, 60, 154, 64]}
    objects = [big, mug, near]
    masks = []
    for o in objects:
        mask = np.zeros((height, width), dtype=bool)
        u0, v0, u1, v1 = o["bbox"]
        mask[v0:v1 + 1, u0:u1 + 1] = True
        masks.append(mask)
    spots = place_badges(objects, masks, width, height, r)
    assert spots[0] == (60, 60)  # a large object keeps its badge on it
    for spot, (o, mask) in zip(spots[1:], zip(objects[1:], masks[1:])):
        x, y = spot
        assert not mask[int(y), int(x)]  # a small one gets it beside it
    pairs = [(a, b) for i, a in enumerate(spots) for b in spots[i + 1:]]
    assert all(np.hypot(a[0] - b[0], a[1] - b[1]) >= 2 * r for a, b in pairs)


def test_interaction_flags_include_folded_receptacles():
    sink = {"objectId": "Sink|1", "objectType": "Sink"}
    basin = {"objectId": "Sink|1___0", "objectType": "SinkBasin", "receptacle": True}
    washer = {"objectId": "WashingMachine|1", "objectType": "WashingMachine", "receptacle": True}
    objects = [sink, basin, washer]
    assert procthor.interaction_flags(sink, objects) == {"receptacle"}
    assert procthor.interaction_flags(washer, objects) == {"receptacle", "toggleable"}


def test_footprint_rects_follow_an_l_shape():
    # 20 px per metre, a 10 m square view centred on (5, 5).
    camera = {"orthographicSize": 5.0, "position": {"x": 5.0, "y": 3.0, "z": 5.0}}
    mask = np.zeros((200, 200), dtype=bool)
    to_world, _ = procthor.top_pixel_to_world(camera, 200, 200)
    vs, us = np.mgrid[0:200, 0:200]
    x, y = to_world(us, vs)
    # An L: the 2 m square at (5, 5) minus its +x, +y quarter.
    mask[(x > 4) & (x < 6) & (y > 4) & (y < 6) & ~((x > 5) & (y > 5))] = True
    rects = procthor.footprint_rects(mask, camera, (5.0, 5.0), (2.0, 2.0))
    area = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rects)
    assert area == pytest.approx(3.0, abs=0.15)
    inside = lambda px, py: any(x0 <= px <= x1 and y0 <= py <= y1 for x0, y0, x1, y1 in rects)
    assert inside(4.5, 4.5) and inside(5.5, 4.5) and inside(4.5, 5.5)
    assert not inside(5.6, 5.6)
    # A full box needs no footprint.
    full = (x > 4) & (x < 6) & (y > 4) & (y < 6)
    assert procthor.footprint_rects(full, camera, (5.0, 5.0), (2.0, 2.0)) is None


def test_resting_on_an_openable_parent_is_on_not_in():
    def aabb(cy, sy):
        return {"axisAlignedBoundingBox": {"center": {"x": 0, "y": cy, "z": 0}, "size": {"x": 1, "y": sy, "z": 1}}}

    toilet = {**aabb(0.475, 0.95), "openable": True}
    assert not procthor.is_inside(aabb(0.97, 0.05), toilet)  # a cloth on the lid
    assert procthor.is_inside(aabb(0.5, 0.1), toilet)
    assert not procthor.is_inside(aabb(0.5, 0.1), {**aabb(0.475, 0.95), "openable": False})
