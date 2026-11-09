The balls have one more key, which is required:

| key | shape | meaning |
|---|---|---|
| `balls_transl` | (T, N, 3) | position of the centre of each of the N balls in meters, in the same world coordinates as everything else |

The balls move only as you say: nothing pulls them down, and nothing attaches them to the hands. Gravity in this world is 9.81 m/s².

```python
np.savez("motion.npz", fps=30, transl=transl, global_orient=global_orient, body_pose=body_pose,
         left_hand_pose=left_hand_pose, right_hand_pose=right_hand_pose, balls_transl=balls_transl)
```
