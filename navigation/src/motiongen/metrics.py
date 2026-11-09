"""Score a finished episode against its hidden success definition."""

from .astar import goal_mask
from .navigation import ARRIVE_MAX_DIST, ARRIVE_MIN_DIST, route_points
from .path_check import check_path


def _arrived(scene, position, accepted):
    cell = scene.cell(*position)
    return any(
        goal_mask(scene, scene.get(object_id), ARRIVE_MIN_DIST, ARRIVE_MAX_DIST)[cell]
        for object_id in accepted
    )


def stops_completed(scene, ends, stops):
    """How many stops were visited in order, as a subsequence of the leg endpoints."""
    completed = 0
    for end in ends:
        if completed < len(stops) and _arrived(scene, end, stops[completed]):
            completed += 1
    return completed


def score_episode(scene, episode, state):
    """Success means reporting infeasible on an impossible task, or doing every stop in order.

    The route must also be collision-free and finish at the last stop. Episodes with
    `goals` (long-horizon tasks), or with nothing to score against, go to goals.score_goals.
    """
    unscored = "stops" not in episode and not episode.get("expect_infeasible")
    if "goals" in episode or unscored:
        from .goals import score_goals
        return score_goals(episode, state)
    points = route_points(state)
    check = check_path(scene, points) if points else None
    collision_free = check["collision_free"] if check else True
    metrics = {
        "reported_infeasible": state["infeasible"],
        "collision_free": collision_free,
        "route_length": check["length"] if check else 0.0,
        "walk_attempts": len(state["attempts"]),
    }
    if episode.get("expect_infeasible"):
        return {**metrics, "success": state["infeasible"], "stops_completed": None}

    stops = episode["stops"]
    ends = [leg["points"][-1] for leg in state["legs"]]
    completed = stops_completed(scene, ends, stops)
    ends_at_last = bool(ends) and _arrived(scene, ends[-1], stops[-1])
    success = (
        not state["infeasible"] and collision_free
        and completed == len(stops) and ends_at_last
    )
    return {**metrics, "success": success, "stops_completed": f"{completed}/{len(stops)}"}
