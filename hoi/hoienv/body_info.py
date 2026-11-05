"""Write agent_kit/body_info.json: the walking body measurements plus the hands.

    python -m hoienv.body_info

The agent never sees the skin mesh, so for reaching and gripping it needs the finger joints and some
points on the skin of the hand. The numbers come from the SMPL-X model, so the file is git-ignored,
like the model itself.
"""
import json

import numpy as np
from smplx.joint_names import JOINT_NAMES

from walkenv.body import Body, _zero_motion
from walkenv.paths import BODY_INFO as WALKING_BODY_INFO

from .paths import BODY_INFO

FIRST_FINGER_JOINT = {"left": 25, "right": 40}
WRIST = {"left": 20, "right": 21}


def _round(v):
    return [round(float(x), 4) for x in v]


def hand_info(body, side, verts, joints):
    """Finger joints and skin points of one hand, in the flat-hand rest pose (palm facing -Y)."""
    first, wrist = FIRST_FINGER_JOINT[side], WRIST[side]
    mean = getattr(body.model, f"{side}_hand_mean").numpy().reshape(15, 3)
    owner = body.model.lbs_weights.numpy().argmax(axis=1)
    names = JOINT_NAMES
    finger_joints, skin = {}, {}
    for i in range(15):
        j = first + i
        finger_joints[names[j]] = {
            "rest": _round(joints[j]),
            "parent": names[int(body.parents[j])],
            "relaxed_pose": _round(mean[i]),
        }
        own = np.where(owner == j)[0]
        skin[f"{names[j]}_pad"] = {"rest": _round(verts[own[verts[own, 1].argmin()]]), "joint": names[j]}
        if i % 3 == 2:  # last bone of a finger: also its tip
            far = own[np.linalg.norm(verts[own] - joints[j], axis=1).argmax()]
            skin[f"{names[j][:-1]}_tip"] = {"rest": _round(verts[far]), "joint": names[j]}

    # Palm: skin of the wrist bone between the wrist and the knuckles.
    middle = joints[first + 3]
    palm = np.where(owner == wrist)[0]
    palm = palm[np.abs(verts[palm, 0]) > abs(joints[wrist, 0])]
    below = palm[verts[palm, 1] < joints[wrist, 1]]
    center = (joints[wrist] + middle) / 2
    closest = below[np.linalg.norm(verts[below][:, [0, 2]] - center[[0, 2]], axis=1).argmin()]
    skin[f"{side}_palm_center"] = {"rest": _round(verts[closest]), "joint": names[wrist]}
    heel = below[np.linalg.norm(verts[below][:, [0, 2]] - joints[wrist, [0, 2]], axis=1).argmin()]
    skin[f"{side}_palm_heel"] = {"rest": _round(verts[heel]), "joint": names[wrist]}
    above = palm[verts[palm, 1] >= joints[wrist, 1]]
    back = above[np.linalg.norm(verts[above][:, [0, 2]] - center[[0, 2]], axis=1).argmin()]
    return {
        "finger_joints": finger_joints,
        "skin_points": skin,
        "palm_thickness": round(float(verts[back, 1] - verts[closest, 1]), 4),
    }


def main():
    info = json.loads(WALKING_BODY_INFO.read_text(encoding="utf-8"))
    body = Body()
    motion = _zero_motion(1)
    for side in ("left", "right"):
        motion[f"{side}_hand_pose"][0] = -getattr(body.model, f"{side}_hand_mean").numpy().reshape(15, 3)
    verts, joints = body.forward(motion)
    info["hands"] = {
        "description": (
            "Hand skeleton and skin points in the flat-hand rest pose: fingers straight, palm facing -Y. Each finger joint "
            "has its rest position, its parent and relaxed_pose (see Hands in SMPLX_INTERFACE.md). Each skin point follows "
            "one joint: *_pad is the palm side of a finger bone, *_tip the end of a finger."
        ),
        **{side: hand_info(body, side, verts[0], joints[0]) for side in ("left", "right")},
    }
    BODY_INFO.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {BODY_INFO}")
    left = info["hands"]["left"]
    print({k: left["skin_points"][k]["rest"] for k in ("left_palm_center", "left_index_tip", "left_thumb_tip")},
          "palm thickness", left["palm_thickness"], info["hands"]["right"]["palm_thickness"])


if __name__ == "__main__":
    main()
