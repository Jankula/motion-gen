"""Write agent_kit/body_info.json: rest-pose measurements of the body the agent animates.

    python -m walkenv.body_info

Run once after placing the SMPL-X model files. The agent gets joint positions and a few foot
and head landmarks; it does not get the mesh, the skinning weights, or any code.
"""
import json
import re

import numpy as np

from .body import BODY_JOINT_NAMES, Body
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
    return info


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
