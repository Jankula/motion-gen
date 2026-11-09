The object has two more keys, both required:

| key | shape | meaning |
|---|---|---|
| `object_transl` | (T, 3) | position of the centre of the object in meters, in the same world coordinates as everything else (so an object of height `h` standing on the floor has y = `floor_y` + `h` / 2) |
| `object_orient` | (T, 3) | axis-angle rotation of the object about its centre. Zero means its own x, y, z axes coincide with the world axes; its `size` is measured along those own axes. A rotation of `yaw_deg` about the vertical is `[0, radians(yaw_deg), 0]` |

The object moves only as you say: nothing pulls it down, and nothing attaches it to the hands.

```python
np.savez("motion.npz", fps=30, transl=transl, global_orient=global_orient, body_pose=body_pose,
         left_hand_pose=left_hand_pose, right_hand_pose=right_hand_pose,
         object_transl=object_transl, object_orient=object_orient)
```
