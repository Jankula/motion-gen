# Walking along a curved path: notes

## What is here

| file | what it is |
|---|---|
| `make_motion.py` | `python make_motion.py <task.json> <out.npz>` writes the motion for any task file. Deterministic. |
| `locomotion/` | the reusable motion library that `make_motion.py` uses (described below) |
| `motion.npz` | the motion for `task.json` (S-shaped path, 300 frames). `check_format.py` prints `OK`. |
| `motion_straight-walk.npz` | the motion for `tasks/straight-walk.json` (180 frames), kept for reference |
| `analyze.py` | my own checking tool: forward kinematics on a saved file, foot contact, sliding, clearances, joint ranges, path and heading. It is not needed to generate motion. |
| `test_tasks/` | extra task files I wrote to test generality: a tight 180° arc of radius 1 m, a polyline, a 90° corner, and a start away from the origin facing +X |

**Speed.** A 10 s clip takes about 0.8 s of computing, or about 3.4 s of wall-clock time including Python start-up and the numpy/scipy imports. The previous code needed about 15 s for 6 s of motion.

## Final results (`evaluate.py`)

**S-shaped path** (`task.json`, `motion.npz`):

| | Measurement | Value | Target |
|---|---|---|---|
| ✅ | Deepest sinking into the floor | 2.64 mm | ≤ 10 mm |
| ✅ | Frames sinking more than 1 cm | 0 frames | 0 |
| ✅ | Frames with nothing on the floor | 0 frames | 0 |
| ✅ | Typical speed of floor-touching skin | 0.38 cm/s | ≤ 1 cm/s |
| ✅ | Speed of floor-touching skin, 95th percentile | 1.27 cm/s | ≤ 3 cm/s |
|  | Distance travelled by the pelvis | 11.55 m |  |
|  | Average speed | 1.16 m/s |  |
| ✅ | Average distance from the path | 1.86 cm | ≤ 15 cm |
| ✅ | Largest distance from the path | 4.62 cm | ≤ 15 cm |
| ✅ | Start position error | 0.9 cm | ≤ 15 cm |
| ✅ | Start heading error | 2.87 ° | ≤ 15° |
| ✅ | Fastest joint rotation | 449.19 °/s | ≤ 800 °/s |
| ✅ | Frames with a pop | 0 frames | 0 |

**Straight walk** (`tasks/straight-walk.json`, `motion_straight-walk.npz`):

| | Measurement | Value | Target |
|---|---|---|---|
| ✅ | Deepest sinking into the floor | 2.62 mm | ≤ 10 mm |
| ✅ | Frames sinking more than 1 cm | 0 frames | 0 |
| ✅ | Frames with nothing on the floor | 0 frames | 0 |
| ✅ | Typical speed of floor-touching skin | 0.4 cm/s | ≤ 1 cm/s |
| ✅ | Speed of floor-touching skin, 95th percentile | 1.29 cm/s | ≤ 3 cm/s |
|  | Distance travelled by the pelvis | 7.18 m |  |
|  | Average speed | 1.2 m/s |  |
| ✅ | Average distance from the path | 1.34 cm | ≤ 15 cm |
| ✅ | Largest distance from the path | 2.1 cm | ≤ 15 cm |
| ✅ | Start position error | 0.9 cm | ≤ 15 cm |
| ✅ | Start heading error | 2.87 ° | ≤ 15° |
| ✅ | Fastest joint rotation | 405.92 °/s | ≤ 800 °/s |
| ✅ | Frames with a pop | 0 frames | 0 |

For comparison, the previous experiment's straight walk scored 2.68 mm deepest sinking, 0.42 / 1.34 cm/s for the two skin-speed measures, a 2.68 cm largest path distance, a 1.24 cm start error and 419 °/s fastest rotation. The new straight walk is essentially the same motion.

## Terms used below

- **Gait cycle**: one full cycle of walking, from one left-heel contact to the next (about 1.06 s here). The **gait phase** counts gait cycles: left heel strike at 0, right heel strike at 0.5, the next left heel strike at 1.
- **Stride**: the distance covered in one gait cycle (two steps). **Cadence**: steps per minute.
- **Stance**: the part of the cycle in which a foot is on the floor (60 % here). **Swing**: the part in which it is in the air (40 %).
- **Heel strike** and **toe-off**: the moments a foot touches down and leaves the floor.
- **Rockers**: the three ways the stance foot rolls. First over the rounded heel, then the shin rotates over the flat foot, then the foot rolls over the ball of the foot and the toes.
- **Forward kinematics (FK)**: computing where every joint is from the joint rotations. **Inverse kinematics (IK)**: the reverse, finding joint rotations that put the foot at a given place.
- **Spline**: a smooth curve through given points. A *clamped cubic spline* also matches given slopes (velocities) at its ends.
- **Walking line**: the smooth curve on the floor that the pelvis actually follows (see below).
- **Heading**: the direction someone faces on the floor. 0° faces +Z, and turning left increases it.

## How it works

The motion is computed, not drawn. Leg joint angles come from foot placements plus IK, and the target curves come from what I know of normal adult walking. No motion data is used. The pipeline, in the order `locomotion/walker.py` runs it:

1. **Walking line** (`path.py`). The task path (straight pieces and arcs, or a polyline) is sampled every 5 mm.
   - It is extended 8 m straight backwards (the person is already walking) and 30 m straight forwards.
   - It is then smoothed with a Gaussian of 0.30 m along its length. Where a straight piece meets an arc, the curvature of the marked path jumps from 0 to 0.5 /m. A walker cannot start turning at full rate instantly, so after smoothing the turning rate builds up and dies away over about a metre. The smoothed line stays within about 2 cm of the marked path.
   - Polylines are first turned into straight pieces joined by arcs (fillets), each as large as the path tolerance allows.

2. **Speed along the line and the gait clock** (`gait.py`, `Clock`).
   - People slow down in bends. The speed factor is `1 / (1 + 0.16 k + 0.06 k^2)`, where k is the absolute curvature (1/m), smoothed over 0.6 m and looked up 0.4 m ahead, so the person slows before reaching the bend. Of the slow-down, 40 % comes from a lower cadence and 60 % from shorter strides.
   - In the 2 m bends the speed drops from 1.23 m/s to 1.12 m/s (stride 1.30 m becomes about 1.24 m).
   - The clock integrates the gait phase and the distance S along the line over time. The integration includes the slow ±1.5 % cadence drift of the previous experiment, so no two steps are identical. S at t = 0 is set so that the pelvis is exactly at the start of the path in the first frame.

3. **Pelvis track** (`Walker.pelvis`). Position: the walking line point at distance S, plus a ±2.1 cm sideways sway toward the stance leg, plus a ±4 mm forward-speed ripple. Orientation:
   - Yaw: the line's heading plus a ±4.5° gait oscillation (the hip of the leading leg forward).
   - Forward tilt: 3° ± 1°.
   - Side tilt: ±3.5° of normal pelvic drop, plus half the lean into the bend (point 4).

4. **Footprints** (`Walker.footprints`). At each heel strike the foot is put on the line a fixed distance ahead of the pelvis (0.233 m, solved; see point 6), half a step width (6.8 cm) to the side.
   - **Foot direction.** The foot points along the line's heading 12 cm beyond the footprint plus 4.5° toe-out, so in a bend each foot turns 30–35° from one of its footprints to the next.
   - **Lean and outward shift (new).** To be pulled round a bend, the body's centre of mass must sit on the inner side of the feet, so the whole body leans in. The physically required lean is atan(v²·k/g), about 3.9° here. I use 85 % of it, which is 3.3°, never more than 7°. The feet land outwards of the pelvis line by pelvis height × tan(lean), at most 5.5 cm. In the bends the inner foot lands almost under the pelvis line and the outer foot 12 cm out.
   - **Stride lengths.** Because the feet are on curved lines of different radius, the inner foot's strides shrink to 1.21 m and the outer foot's grow to 1.29 m, as in real curved walking.

5. **Stance foot and leg** (`legs.py`; mostly unchanged from the previous experiment).
   - The foot rolls over a 4.1 cm heel circle, lies flat, and then rises about the ball of the foot while the toes stay on the floor; late in stance it rolls over the toe pad.
   - The heel-rise angle is a soft maximum of two terms: a prescribed heel-off profile, and the rise the knee needs to bend at least a minimum pre-swing curve.
   - New: that second term is now solved in closed form. The squared hip-to-ankle distance is `K + A cos(a) + B sin(a)` in the heel-rise angle a, so the angle comes from an arccos. The previous code nested root-finding inside root-finding.
   - The leg is then solved by analytic two-bone IK on the actual SMPL-X bones. The knee only flexes, and it points over the foot. A planted foot therefore cannot slide.

6. **Pelvis height** (`Walker._solve_height`).
   - **Required height.** For the leading stance leg, the target knee curve (5° at contact, 17.5° loading peak, 5° late in stance) fixes the hip-to-ankle distance. The pelvis height that gives it is computed in closed form at 120 samples per second.
   - **Smooth fit.** The highest smooth curve that never exceeds this requirement is then fitted by *asymmetric least squares*: a smoothing fit that strongly penalises any sample where the curve would be too high. A lower pelvis only adds a little knee bend; a higher one would over-stretch the leg.
   - **Calibration.** The skeleton's legs differ slightly. The heel-strike distance and a small static pelvic tilt (-1.0°) are therefore solved once for straight walking (Newton iteration) so that the requirement is continuous when the leading leg changes.

7. **Swing leg** (`Walker.swing_splines`; as before). Each joint channel is a clamped cubic spline in joint space.
   - **Start:** it leaves toe-off with the stance leg's own joint velocities.
   - **Middle:** it passes via-points from normal swing kinematics (about 61° peak knee flexion, a late hip-flexion peak).
   - **End:** it arrives at the next footprint with a "rigid-leg approach": the heel moves forward 0.3 m/s over the floor, then comes down.
   - In bends the hip's rotation and side-to-side channels carry the foot from its old direction to the new one during the swing.

8. **Upper body** (`upper_body.py`). Thorax and head orientation are specified in the world and spread over the three spine joints and the neck/head, as before. New for bends:
   - **Thorax:** faces the line's heading 25 cm ahead (about 7° into the bend) and leans fully into the bend.
   - **Head:** turns toward the point on the line 1.6 m ahead, taking 70 % of that direction relative to the thorax (the eyes would do the rest), and leans 60 % as much as the trunk. The head therefore starts turning about half a second before the body and leads the path heading by up to about 20° in the bends. When the path switches from left to right, the head swings over first.
   - **Arms:** they swing exactly as on a straight line, because in a bend the effective gravity (gravity plus the outward pull) tilts with the body lean.

All stages are vectorised over frames with numpy, which is where the speed comes from.

## What changed compared with the starting point (`previous/E01-straight-walk`)

- **Structure.** The one script has become a package: skeleton/FK, batched rotations, path, gait clock, legs, walker, upper body, task I/O. `make_motion.py` takes any task file.
- **Paths.** The pelvis follows an arbitrary smoothed line instead of the +Z axis. Footprints, foot directions, pelvis yaw, thorax and head are all taken from the line. The task path may be segments or a polyline.
- **Turning behaviour** (all new): slowing down before and in bends, the lean into the bend with outward foot placement, the foot turning a little more on each step, the thorax leading and the head looking ahead.
- **Speed.** Closed-form required pelvis height and heel rise, a sparse asymmetric-least-squares fit instead of SLSQP (a constrained optimiser) on a Fourier series, and a batched clock, IK and upper body. Together this is about 20 times faster per second of motion.
- **Pelvis height** is no longer assumed periodic. It is fitted over the whole clip, so it adapts to the stride changes in bends and to future non-steady tasks.
- **Start position.** The pelvis *joint* (not `transl`) is placed at the start position. In the previous experiment `transl` was zeroed, which left the joint 1.24 cm off.
- **Kept unchanged:** all gait curves and amplitudes, foot rockers, IK, swing splines, arm and head detail.

## Main choices and why

- **Smoothing the marked path (σ = 0.3 m)** rather than following its curvature jumps. A real walker's rate of turning changes smoothly. The cost is 2–4 cm of deviation, against a 15 cm tolerance.
- **Physically motivated lean, at 85 % strength.** The lean and the outward foot placement follow from the centripetal force a body needs to go round a curve, so their size scales correctly with speed and radius. I used slightly less than the full physical value, because a real foot can also push sideways within its sole.
- **Turning distributed over every step**, with the planted foot fixed and the hip rotating over it. This is how people negotiate gentle bends, as opposed to the pivot or step turns used at sharp corners.
- **Look-ahead in distance rather than time** for the head and thorax. It gives the anticipation people show automatically (head first, then trunk, then pelvis) and needs no special handling at the start or end of bends.
- **Ambiguities.**
  - "Natural pace" means 1.23 m/s on straights, as before, slowing to about 1.12 m/s in the 2 m bends.
  - The start pose is the pelvis joint at (0, 0) on the path at frame 0. Its sideways sway puts it 0.9 cm off at that moment, and its heading includes the normal ±4.5° pelvis rotation (2.9° at frame 0).
  - The person reaches about 11.8 m of the 13.8 m path, so they never reach its end.
  - Hands, jaw and eyes are left at zero (relaxed hand, closed mouth, eyes forward).

## How I checked the result

- **`evaluate.py`** on both task files: tables above, 11 of 11 targets each.
- **`analyze.py`** (forward kinematics on the saved file, sampled sole points):
  - no sole point below the floor;
  - floor-contact points move at most 1.1 mm per frame;
  - mid-swing toe clearance 1.8–2.9 cm on every step in the bends (1.8–2.1 cm on the straight);
  - shank axes never closer than 10.9 cm, ankles never closer than 12.4 cm;
  - peak joint speed 449 °/s (right ankle at push-off in the bend);
  - pelvis yaw within -8.6° to +5.9° of the path heading.

  I also printed path heading against pelvis, thorax and head yaw over time to confirm the order: head first, then thorax, then pelvis.
- **Rendered previews**, 4 of the 8 allowed: the first bend (2.0–3.2 s), the switch from left to right bend (3.5–4.9 s), the entry into the first bend (0.6–2.2 s) and the exit into the final straight (5.6–7.2 s). They showed:
  - natural-looking walking, with the body turning with the path and the head turning into each bend first;
  - no visible sliding, crossing feet or interpenetration;
  - in the top view, the pelvis track lying on the drawn path.

  I made no changes as a result of the previews.
- **Straight walk regression.** The new code reproduces the previous straight walk: same joint ranges within about 1°, the same speed and the same contact quality.
- **Determinism.** Repeated runs give bit-identical files.
- **Generality** (`test_tasks/`):
  - The tight radius-1 m half circle, the polyline with 56° and 45° corners, and the start facing +X all run without problems: no sliding (≤ 2.1 mm per frame), no pops, all joint speeds ≤ 600 °/s, path deviation ≤ 7.6 cm.
  - The 90° corner does not work (see weaknesses). Its 8 m path is also shorter than 10 s of walking; beyond the end the walker simply continues straight.

## Known weaknesses

- **Sharp corners.** For a polyline corner that must be rounded tighter than about 0.5 m to stay within the tolerance (for example a 90° corner), the body has to turn about 60° over a single planted foot. The ankle then twists unrealistically and the foot slides for a frame or two (seen in `test_tasks/corner90.json`). Real people use dedicated step or pivot turns there; that needs a new mechanism. The lean, foot shift and slow-down are limited so that tighter curves degrade gracefully rather than explode.
- **The lean model is simple.** One lean angle drives the foot shift, pelvis roll (50 %), thorax (100 %) and head (60 %). Real walkers also change their timing in bends; for example, the inner leg spends longer on the ground. That is not modelled.
- **Arms and gaze in bends.** The arms swing identically on straights and in bends, and the head simply tracks a fixed look-ahead point. A real person's gaze jumps ahead in quick eye-and-head movements (saccades) rather than tracking continuously.
- **The new code adds no new variability.** Steps vary only through the slow cadence drift, small foot-placement scatter and the changes the bends bring. The hands stay in the default relaxed pose, and there is no breathing.
- **Inherited from E01:**
  - all curves are hand-tuned from memory of typical gait;
  - the slight skeleton asymmetry is absorbed by a small static pelvic tilt and ±1.1° knee offsets;
  - heel strike is a deliberate velocity discontinuity (an impact);
  - self-contact is checked only with joint-axis distances, not on the skin.
- **Not supported yet:** starting from standing, stopping, and avoiding obstacles. `generate_motion` warns and walks steadily along the path when a task asks for them.

## Extending the library

- **New paths** need only a task file (`segments` or `points`).
- **Gait parameters** are in `gait.DEFAULTS` and can be overridden with `generate_motion(task, params={...})`.
- **Speed changes along the path** go through the speed field in `Walker._speed_field`. Starting and stopping would add a time-dependent factor there plus dedicated first and last steps.
- **The pelvis-height fit** is already non-periodic, so it will follow such changes.
