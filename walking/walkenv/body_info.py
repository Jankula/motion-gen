"""Write agent_kit/body_info.json: rest-pose measurements of the body the agent animates.

    python -m walkenv.body_info

Run once after placing the SMPL-X model files. The agent gets joint positions and a few foot
and head landmarks; it does not get the mesh, the skinning weights, or any code.
"""
import json
import re

import numpy as np

from .body import BODY_JOINT_NAMES, Body, _zero_motion
from .paths import BODY_INFO


def body_info(body):
    v, j = body.rest_vertices, body.rest_joints
    info = {
        "description": "SMPL-X neutral body, betas = 0, rest pose (all parameters zero). Meters; +Y up, "
        "the body faces +Z, the body's left is +X.",
        "floor_y": round(body.floor_y, 4),
        "standing_height": round(float(v[:, 1].max() - v[:, 1].min()), 4),
        "joints": {name: _r(j[i]) for i, name in enumerate(BODY_JOINT_NAMES)},
        "parents": {
            name: (BODY_JOINT_NAMES[body.parents[i]] if i > 0 else None) for i, name in enumerate(BODY_JOINT_NAMES)
        },
        "landmarks": {"head_top": _r(v[v[:, 1].argmax()])},
    }
    for side, sign in (("left", 1.0), ("right", -1.0)):
        ankle = j[BODY_JOINT_NAMES.index(f"{side}_ankle")]
        foot = v[(v[:, 0] * sign > 0) & (v[:, 1] < ankle[1])]  # everything below this ankle
        sole = foot[foot[:, 1] < body.floor_y + 0.015]  # the part touching the floor when standing
        info["landmarks"][f"{side}_heel_back"] = _r(foot[foot[:, 2].argmin()])
        info["landmarks"][f"{side}_heel_bottom"] = _r(sole[sole[:, 2].argmin()])
        info["landmarks"][f"{side}_toe_tip"] = _r(foot[foot[:, 2].argmax()])
        info["landmarks"][f"{side}_sole_outer_edge"] = _r(sole[(sole[:, 0] * sign).argmax()])
        info["landmarks"][f"{side}_sole_inner_edge"] = _r(sole[(sole[:, 0] * sign).argmin()])
    info["dimensions_arms_down"] = _dimensions(body)
    return info


def _dimensions(body):
    """Torso width and depth with the arms lowered to the sides (arm vertices excluded)."""
    m = _zero_motion(1)
    m["body_pose"][0, BODY_JOINT_NAMES.index("left_shoulder") - 1, 2] = -np.radians(70)
    m["body_pose"][0, BODY_JOINT_NAMES.index("right_shoulder") - 1, 2] = np.radians(70)
    v, j = (a[0] for a in body.forward(m))
    arm_joints = [BODY_JOINT_NAMES.index(f"{s}_{p}") for s in ("left", "right") for p in ("shoulder", "elbow", "wrist")]
    arm_joints += list(range(25, 55))  # fingers
    torso = v[~np.isin(body.model.lbs_weights.numpy().argmax(axis=1), arm_joints)]
    shoulder_y, pelvis_y, neck_y = j[16, 1], j[0, 1], j[12, 1]

    def extent(lo, hi, axis):
        p = torso[(torso[:, 1] > lo) & (torso[:, 1] < hi)]
        return round(float(p[:, axis].max() - p[:, axis].min()), 3)

    return {
        "note": "Measured on the skin with the arms hanging at the sides; the arms themselves are excluded.",
        "torso_width_at_shoulders": extent(shoulder_y - 0.12, shoulder_y + 0.05, 0),
        "hip_width": extent(pelvis_y - 0.15, pelvis_y + 0.05, 0),
        "max_torso_depth_front_to_back": extent(pelvis_y - 0.2, neck_y, 2),
    }


def _r(p):
    return [round(float(x), 4) for x in np.asarray(p)]


def main():
    info = body_info(Body())
    text = json.dumps(info, indent=2)
    text = re.sub(r"\[\s+([^\[\]]*?)\s+\]", lambda m: "[" + " ".join(m.group(1).split()) + "]", text)  # [x, y, z] on one line
    BODY_INFO.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {BODY_INFO}")
    print(f"floor_y = {info['floor_y']}, standing height = {info['standing_height']} m")


if __name__ == "__main__":
    main()
