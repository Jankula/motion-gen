# SMPL-X interface

## The body

SMPL-X is a parametric 3D human body: a skin mesh of 10,475 vertices driven by a skeleton of 55 joints. Here the body shape is fixed (a gender-neutral adult, measurements in `body_info.json`). You animate it by giving, for every frame, a translation and orientation of the whole body and a rotation for each joint. The skin follows the skeleton by linear blend skinning: each skin point moves with a weighted mix of the joints near it, plus small automatic corrective deformations.

## Coordinate frame

- Units: meters and radians.
- +Y points up. In the rest pose the body faces +Z. The body's own left side is +X.
- The floor is the horizontal plane `y = floor_y` (see `body_info.json`). With every parameter zero, the body stands in the rest pose with its soles exactly on the floor.

## Rest pose (all parameters zero)

Standing upright, legs straight and slightly apart, feet pointing forward (+Z), arms straight out to the sides at shoulder height (a T-pose), palms down, head looking forward. The hands are relaxed, with slightly curled fingers.

## Rotations

Every rotation is an axis-angle vector of 3 numbers: its direction is the rotation axis, its length is the angle in radians, and the positive direction follows the right-hand rule (thumb along the axis, fingers curl in the positive direction).

A joint's rotation is relative to its parent, in axes that coincide with the world axes above when the body is in the rest pose. Rotating a joint rotates its whole subtree (all its descendant joints and the skin attached to them) about that joint's position.

Forward kinematics, exactly as the renderer computes it. Joint `i` has rest position `J_i` (from `body_info.json`), parent `p(i)`, and rotation matrix `R_i` from its axis-angle vector. Joint 0 is the pelvis, whose rotation is `global_orient`.

```
world rotation:   W_0 = R_0
                  W_i = W_p(i) · R_i
world position:   P_0 = J_0 + transl
                  P_i = P_p(i) + W_p(i) · (J_i − J_p(i))
```

A skin point that moves only with joint `i` and has rest position `x` ends up at `P_i + W_i · (x − J_i)`.

## Joints you control

| `body_pose` row | joint | name | parent | notes |
|---|---|---|---|---|
| (`global_orient`) | 0 | pelvis | | root of the skeleton |
| 0 | 1 | left_hip | pelvis | |
| 1 | 2 | right_hip | pelvis | |
| 2 | 3 | spine1 | pelvis | lower back |
| 3 | 4 | left_knee | left_hip | |
| 4 | 5 | right_knee | right_hip | |
| 5 | 6 | spine2 | spine1 | middle back |
| 6 | 7 | left_ankle | left_knee | |
| 7 | 8 | right_ankle | right_knee | |
| 8 | 9 | spine3 | spine2 | upper back / chest |
| 9 | 10 | left_foot | left_ankle | ball of the foot; rotating it bends the toes |
| 10 | 11 | right_foot | right_ankle | ball of the foot; rotating it bends the toes |
| 11 | 12 | neck | spine3 | |
| 12 | 13 | left_collar | spine3 | collarbone |
| 13 | 14 | right_collar | spine3 | collarbone |
| 14 | 15 | head | neck | |
| 15 | 16 | left_shoulder | left_collar | |
| 16 | 17 | right_shoulder | right_collar | |
| 17 | 18 | left_elbow | left_shoulder | |
| 18 | 19 | right_elbow | right_shoulder | |
| 19 | 20 | left_wrist | left_elbow | |
| 20 | 21 | right_wrist | right_elbow | |

## Hands

The fingers are joints too: 15 per hand, in the order index 1-3, middle 1-3, pinky 1-3, ring 1-3, thumb 1-3 (1 = knuckle, 3 = last bone). You control them with `left_hand_pose` and `right_hand_pose`. `body_info.json` has everything about them under `hands`:

- `finger_joints`: for every finger joint its `rest` position, its `parent` and its `relaxed_pose`. The rest positions are those of a **flat hand**: fingers straight, palm facing -Y in the T-pose. Index 1, middle 1, pinky 1, ring 1 and thumb 1 hang from the wrist.
- `skin_points`: points on the skin of the hand, in the same flat-hand rest pose, each following one `joint`. `*_pad` is the palm side of a finger bone, `*_tip` the end of a finger, `*_palm_center` and `*_palm_heel` are on the palm.
- `palm_thickness`: the thickness of the hand at the palm.

Finger joints follow the same forward kinematics as the body, with one difference. The rotation of finger joint `i` is built from the **sum** of two axis-angle vectors:

```
R_i = rotation matrix of (relaxed_pose_i + hand_pose_i)
```

So a hand pose of zero is the relaxed, slightly curled hand, and `hand_pose_i = -relaxed_pose_i` is the flat hand. A skin point following joint `i` with rest position `x` ends up at `P_i + W_i · (x − J_i)`, as for the body.

You do not have the skin mesh itself: the skin points above and the measurements in `body_info.json` are what you have to work with. `evaluate.py` measures on the real skin.

## Motion file

`motion.npz`, written with `numpy.savez`. `T` is the number of frames.

| key | shape | required | meaning |
|---|---|---|---|
| `fps` | scalar int | yes | frames per second |
| `transl` | (T, 3) | yes | translation of the whole body in meters, applied after all rotations |
| `global_orient` | (T, 3) | yes | axis-angle rotation of the whole body about the pelvis joint |
| `body_pose` | (T, 21, 3) or (T, 63) | yes | axis-angle rotations of joints 1 to 21, in the row order of the table above |
| `left_hand_pose`, `right_hand_pose` | (T, 15, 3) or (T, 45) | no | finger joints, see Hands above. Zero is the relaxed hand. |
| `jaw_pose`, `leye_pose`, `reye_pose` | (T, 3) | no | jaw and eyeballs; zero is closed mouth, eyes forward |
| `object_transl` | (T, 3) | yes | position of the centre of the object in meters, in the same world coordinates as everything else (so an object of height `h` standing on the floor has y = `floor_y` + `h` / 2) |
| `object_orient` | (T, 3) | yes | axis-angle rotation of the object about its centre. Zero means its own x, y, z axes coincide with the world axes; its `size` is measured along those own axes. A rotation of `yaw_deg` about the vertical is `[0, radians(yaw_deg), 0]` |

Optional keys you leave out are zero for every frame. No other keys are allowed. The object moves only as you say: nothing pulls it down, and nothing attaches it to the hands.

```python
np.savez("motion.npz", fps=30, transl=transl, global_orient=global_orient, body_pose=body_pose,
         left_hand_pose=left_hand_pose, right_hand_pose=right_hand_pose,
         object_transl=object_transl, object_orient=object_orient)
```

Check a file with `python check_format.py motion.npz task.json`.
