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

## Motion file

`motion.npz`, written with `numpy.savez`. `T` is the number of frames.

| key | shape | required | meaning |
|---|---|---|---|
| `fps` | scalar int | yes | frames per second |
| `transl` | (T, 3) | yes | translation of the whole body in meters, applied after all rotations |
| `global_orient` | (T, 3) | yes | axis-angle rotation of the whole body about the pelvis joint |
| `body_pose` | (T, 21, 3) or (T, 63) | yes | axis-angle rotations of joints 1 to 21, in the row order of the table above |
| `left_hand_pose`, `right_hand_pose` | (T, 15, 3) or (T, 45) | no | finger joints: index 1-3, middle 1-3, pinky 1-3, ring 1-3, thumb 1-3 (1 = knuckle). Zero is the relaxed hand. |
| `jaw_pose`, `leye_pose`, `reye_pose` | (T, 3) | no | jaw and eyeballs; zero is closed mouth, eyes forward |

Optional keys you leave out are zero for every frame. No other keys are allowed.

```python
np.savez("motion.npz", fps=30, transl=transl, global_orient=global_orient, body_pose=body_pose)
```

Check a file with `python check_format.py motion.npz`.
