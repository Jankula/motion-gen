# Start, turn a corner, stop, turn around: notes

## What is here

| file | what it is |
|---|---|
| `make_motion.py` | `python make_motion.py <task.json> <out.npz>` writes the motion for any task file. Deterministic. |
| `locomotion/` | the reusable motion library that `make_motion.py` uses (described below) |
| `motion.npz` | the motion for `task.json` (360 frames). `check_format.py motion.npz task.json` prints `OK`. |
| `motion_straight-walk.npz`, `motion_curved-path.npz` | the motions for the two earlier tasks in `tasks/`, kept for reference |
| `analyze.py` | my checking tool: forward kinematics on a saved file, then foot contact, sliding, swing clearance, distance between the feet and legs, joint ranges and speeds, path, heading and stillness |
| `tools/check_tasks.py` | runs many task files and prints a one-line summary for each (writes motions to `test_out/`) |
| `tools/plan_report.py` | prints the footstep plan of a task and, with `--env`, the body state every 0.25 s |
| `test_tasks/` | extra task files for generality: the previous session's four, plus four new ones (a left corner with a stop, an already-walking person who stops and turns 90°, a zig-zag with two corners plus a stop and a 180° turn, and a start from standing into a curve that keeps going) |

None of the checking tools are needed to generate motion.

**Speed.** Generating the 12 s clip takes about 0.6 s of computing (0.5–0.8 s for every task file I tried). Starting Python and importing numpy/scipy adds about 3 s of wall-clock time.

## Final results (`evaluate.py`)

**This task** (`task.json`, `motion.npz`):

| | Measurement | Value | Target |
|---|---|---|---|
| ✅ | Deepest sinking into the floor | 4.12 mm | ≤ 10 mm |
| ✅ | Frames sinking more than 1 cm | 0 frames | 0 |
| ✅ | Frames with nothing on the floor | 0 frames | 0 |
| ✅ | Typical speed of floor-touching skin | 0.15 cm/s | ≤ 1 cm/s |
| ✅ | Speed of floor-touching skin, 95th percentile | 1.29 cm/s | ≤ 3 cm/s |
|  | Distance travelled by the pelvis | 5.63 m |  |
|  | Average speed | 0.47 m/s |  |
| ✅ | Average distance from the path | 2.93 cm | ≤ 30 cm |
| ✅ | Largest distance from the path | 12.03 cm | ≤ 30 cm |
| ✅ | Start position error | 0.58 cm | ≤ 15 cm |
| ✅ | Start heading error | 0 ° | ≤ 15° |
| ✅ | Pelvis speed while standing at the start | 3.28 cm/s | ≤ 10 cm/s |
| ✅ | End position error | 0.22 cm | ≤ 15 cm |
| ✅ | End heading error | 0 ° | ≤ 15° |
| ✅ | Pelvis speed while standing at the end | 1.73 cm/s | ≤ 10 cm/s |
| ✅ | Fastest joint rotation | 464.77 °/s | ≤ 800 °/s |
| ✅ | Frames with a pop | 0 frames | 0 |

**Straight walk** (`tasks/straight-walk.json`, `motion_straight-walk.npz`):

| | Measurement | Value | Target |
|---|---|---|---|
| ✅ | Deepest sinking into the floor | 2.75 mm | ≤ 10 mm |
| ✅ | Frames sinking more than 1 cm | 0 frames | 0 |
| ✅ | Frames with nothing on the floor | 0 frames | 0 |
| ✅ | Typical speed of floor-touching skin | 0.42 cm/s | ≤ 1 cm/s |
| ✅ | Speed of floor-touching skin, 95th percentile | 1.44 cm/s | ≤ 3 cm/s |
|  | Distance travelled by the pelvis | 7.16 m |  |
|  | Average speed | 1.2 m/s |  |
| ✅ | Average distance from the path | 1.45 cm | ≤ 15 cm |
| ✅ | Largest distance from the path | 2.48 cm | ≤ 15 cm |
| ✅ | Start position error | 1.37 cm | ≤ 15 cm |
| ✅ | Start heading error | 2.09 ° | ≤ 15° |
| ✅ | Fastest joint rotation | 467.6 °/s | ≤ 800 °/s |
| ✅ | Frames with a pop | 0 frames | 0 |

**S-shaped path** (`tasks/curved-path.json`, `motion_curved-path.npz`):

| | Measurement | Value | Target |
|---|---|---|---|
| ✅ | Deepest sinking into the floor | 2.81 mm | ≤ 10 mm |
| ✅ | Frames sinking more than 1 cm | 0 frames | 0 |
| ✅ | Frames with nothing on the floor | 0 frames | 0 |
| ✅ | Typical speed of floor-touching skin | 0.44 cm/s | ≤ 1 cm/s |
| ✅ | Speed of floor-touching skin, 95th percentile | 1.38 cm/s | ≤ 3 cm/s |
|  | Distance travelled by the pelvis | 11.29 m |  |
|  | Average speed | 1.13 m/s |  |
| ✅ | Average distance from the path | 1.83 cm | ≤ 15 cm |
| ✅ | Largest distance from the path | 4.92 cm | ≤ 15 cm |
| ✅ | Start position error | 1.34 cm | ≤ 15 cm |
| ✅ | Start heading error | 2.05 ° | ≤ 15° |
| ✅ | Fastest joint rotation | 471.44 °/s | ≤ 800 °/s |
| ✅ | Frames with a pop | 0 frames | 0 |

For comparison, the previous code scored 2.62–2.64 mm sinking, 0.38–0.40 / 1.27–1.29 cm/s skin speed, 2.1 / 4.6 cm largest path distance and 406 / 449 °/s fastest joint on the two earlier tasks, so walking quality is unchanged.

## What the person does in `task.json`

| time | what happens |
|---|---|
| 0 – 0.8 s | stands still (slight natural sway and breathing) |
| 0.8 – 1.1 s | shifts weight onto the left foot and starts to lean forward |
| 1.1 s | the right foot lifts for the first step (a short one, 0.54 of a normal step) |
| 1.5 – 3.7 s | four steps that grow to 0.9 of full length (about 1.0 m/s), then shorten again before the corner |
| 3.8 – 5.1 s | corner, taken as a *step turn*: the left foot is put down outside the corner, pointing 50° into the turn; the body swings round over it; the right foot steps into the new direction; the left foot pivots on its forefoot as it pushes off |
| 5.1 – 6.7 s | three steps along the second leg of the path, the last ones shorter (slowing down) |
| 7.3 – 7.8 s | closing step: the trailing left foot is brought up beside the right one; the body settles |
| 8.2 – 10.7 s | turns 180° to the left on the spot in six small steps of 60° (left, right, left, …); the head turns first |
| 10.7 – 12 s | stands still facing +X |

## Terms used below

- **Gait cycle**, **stride**, **step**: a gait cycle runs from one heel strike of a foot to its next (about 1.06 s in steady walking); a stride is the distance covered in it (1.30 m); a step is half of that, from one foot's touch-down to the other's.
- **Stance** and **swing**: the time a foot is on the floor or in the air. **Double support**: both feet on the floor.
- **Heel strike**, **toe off**: the moments a foot lands (normally heel first) and leaves the floor.
- **Rockers**: how the planted foot rolls, first over the rounded heel, then over the ankle with the foot flat, then over the ball of the foot and the toes.
- **Centre of mass (COM)**: the average position of the body's mass, near the pelvis. **Centre of pressure (COP)**: the point on the floor through which the body's weight acts; it lies under whichever part of the feet carries the weight.
- **Inverted pendulum**: a simple balance model in which the body is a mass balanced on top of the COP, like a stick balanced on a fingertip.
- **Forward kinematics (FK)**: computing joint positions from joint rotations. **Inverse kinematics (IK)**: the reverse, finding joint rotations that put the foot at a given place.
- **Spline**: a smooth curve through given points.
- **Heading**: the direction someone faces on the floor. 0° faces +Z, and turning left increases it.
- **Footstep plan**: the list of where and when each foot is put down.
- **Plant**: one period during which a foot is on the floor.
- **Step turn** and **spin turn**: the two ways people turn a corner while walking. In a step turn the outer foot is planted and the inner foot steps into the new direction. In a spin turn the body pivots over the inner foot and the outer foot crosses over. Step turns are the commoner and more stable kind.

## How it works

The motion is computed, not drawn or copied. No motion data is used. The previous version moved the pelvis along the path at a set speed and put the feet where the pelvis was going. That cannot express standing, starting, stopping or stepping on the spot. The new version turns it around: **first decide where and when every foot goes down, then let a balance model work out how the body moves over those feet**, then pose the legs and the upper body. In the order `locomotion/` runs it:

### 1. Two lines on the floor (`path.py`, `task.py`)

The task path (a polyline or straight pieces and arcs) becomes two smooth curves:

- **Feet line.** It stays close to the drawn path: corners are rounded within 10 % of the tolerance (a 10 cm radius here), and it is smoothed only over 0.12 m. Footprints are placed along it.
- **Body line.** It is smoother (corners rounded within 35 % of the tolerance, a 36 cm radius here, and smoothed over 0.25 m). It only gives the direction the pelvis faces while walking.

Both are extended straight backwards and forwards so that walking can begin before the clip or continue after it. A small error in the old line builder was fixed: segment ends were snapped to the 5 mm sampling grid, so the 90° arc came out 0.5° short and the end of the path 2 cm off. The heading is now integrated exactly.

### 2. The footstep plan (`plan.py`)

A `PlanBuilder` strings behaviours together, each appending footsteps:

- **`stand(center, heading)`**: feet side by side, heels 17 cm apart, toes out 7°.
- **`wait(dt)`**: keep standing.
- **`walk(line, body_line, stop=…)`**: walk along the feet line, starting from standing and either stopping at the end of the path or walking on.
  - **Step lengths.** The normal step (0.65 m) is shortened in bends, by a speed factor of the turning rate measured 0.4 m ahead and 0.2 m behind, so the walker slows before a bend and speeds up only after it. Steps are also shortened over the first three steps from standing (0.60, 0.85, 0.97 of normal) and the last two before stopping (0.90, 0.70), then a closing step brings the trailing foot alongside.
  - **Timing.** The step period (0.53 s) lengthens in bends and in the first and last steps. The first swing takes 0.40 s, after 0.30 s of shifting weight onto the other foot. A slow ±1.5 % drift in cadence keeps steps from being identical.
  - **Corners.** A corner is a place where the line turns by at least 40° within half a metre and does most of its turning there; this tells a corner from a long, even bend. At each corner the plan makes a step turn: the step lengths before and after are scaled (within 0.65–1.25 of normal) so that the **outer foot lands exactly at the apex**, 4 cm further out than usual. The foot that steps first is chosen to make this work. The step after the apex is short (0.8 of normal), as the inner foot steps into the new direction.
  - **Lean.** In gentle bends the feet are shifted outwards so that the body can lean into the bend (as before). At corners this shift is switched off and the body is allowed to round the corner inside the footprints.
  - **Ending on the mark.** The step lengths of each stretch are scaled by one factor so that the feet arrive exactly at the next corner apex and at the end of the path. The stop then puts the centre of mass exactly on the end point.
- **`turn(angle)`**: turn on the spot with stepping turns.
  - Each foot turns at most 65° per step, so 180° takes 3 steps per foot (6 steps, 0.43 s each).
  - The inner foot (on the side of the turn) goes first.
  - A stepping foot is put down with its heel beside the planted foot's heel, across the mean of the two feet's headings. The heels stay clear while the toes open into a V.
  - The centre of the feet is pulled back to the starting point at every step, and the last step puts the feet side by side with their centre exactly there.
- **`finish()`**: turns the footsteps into a `Plan`.

From the footsteps, the plan derives for each foot its **plants**. Each plant has a **stance clock u(t)** with the meaning of the normal gait cycle:

| u | meaning |
|---|---|
| 0 | touch-down |
| 0.1 | the other foot leaves the floor |
| 0.5 | the other foot lands |
| 0.6 | toe off |
| 0.2 | a standing foot (flat) |

When a foot lifts after standing, u runs from 0.2 to 0.6 over the 0.3 s of unloading. This one clock drives the foot rockers, the heel rise before lift-off, the target knee bend and where the weight sits under the foot, for walking, starting, stopping and turning alike. The size of the push-off (heel rise, toe roll, knee bend before lift-off) scales with the length of the coming step. The plan also provides:
- the **heading program**: along the body line while walking; while turning on the spot, a smooth curve that turns mostly while a foot is in the air;
- the **gait phase**;
- a **step-size envelope** (1 for a normal step, 0 when standing), which scales every gait oscillation so that pelvis rotation, arm swing and so on fade in when starting and out when stopping.

### 3. Balance: from the feet to the body's path (`balance.py`)

- **Centre of pressure.** Under each planted foot it runs from the heel to the toes during stance. When both feet are down, the weight moves smoothly from one to the other over the double support (or over 0.3 s when shifting weight from standing). While standing, a slow sway of a few millimetres is added.
- **Centre of mass.** It comes from the *linear inverted pendulum*: the body's horizontal acceleration is proportional to how far the COM is from the COP (x'' = (g / 0.95 m)·(x − p)). Solved over the whole clip so that the body never falls over, the COM path is simply the COP path smoothed over about 0.3 s.

This one model produces several behaviours with nothing tuned for them separately:
- the side-to-side sway of walking (±2–2.5 cm);
- the slight surge and slowing within each step;
- the weight shift and forward "fall" that start a walk;
- the braking at a stop;
- the rounding of corners inside the footprints;
- the small weight shifts of stepping on the spot.

The sustained part of the COM acceleration (smoothed over 0.22 s) gives the **lean**: into bends and corners (up to 7°), and a forward trunk lean when speeding up.

### 4. Pelvis (`body.py`)

- **Position.** The pelvis follows the COM. While walking it is 3.9 cm ahead of it; this offset and a −1.0° static pelvic tilt are solved once by Newton iteration so that the leg geometry hands over smoothly from one leg to the other, as before.
- **Orientation.**
  - Heading: from the plan, plus the walking rotation of ±4.5° that brings the leading hip forward.
  - Forward tilt: 1° when standing, 3° walking.
  - Pelvic drop: ±3.5°.
  - Lean into bends: half of the body lean.
  - Every oscillation is scaled by the step size.
- **Height.** For every weight-bearing leg, the pelvis height that gives its target knee bend is computed in closed form. Targets: 4° when standing, the normal 5–17° loading curve after a walking heel strike, and less after small steps. The highest smooth curve that never exceeds the lowest of these is then fitted. New: the requirement at each touch-down is also applied to the neighbouring samples. Without this the fitted curve could overshoot between two samples just as a leg takes the weight, and the knee snapped straight at heel strike.

### 5. Legs (`legs.py`, `body.py`)

- **Stance.** Foot rockers plus analytic two-bone IK, as before, so a planted foot cannot slide. New: **forefoot pivot**. When the body has turned over a planted foot (at a corner), the foot turns on the ball of the foot towards the body's heading during the heel rise before toe off: 75 % of the misalignment beyond 8°, at most 30°. Real feet do this in step turns. Without it the leg was twisted and over-stretched at push-off (ankle at 75° and joints at over 1300 °/s in early versions).
- **Walking swing.** Joint-space splines between toe off and the next heel strike, as before. Their swing knee peak scales with step length: 61° for a full step, about 45° for the short first step. Big re-orientations of the foot (at corners) happen mostly in mid-swing, when the foot is up. Two guards were added:
  - *Toe clearance.* The lowest point of the sole, including the toe segment, is checked over the swing. Where it would come within 1.4 cm of the floor in mid-swing (or touch it in early swing), a smooth bump of extra knee and hip flexion is added.
  - *Foot clearance.* Where the swinging foot would pass within 3.5 cm of the planted foot (tight turns), a smooth bump of hip abduction swings it wider.
- **Small steps on the spot.** The foot moves along a path in space: the ankle follows a smooth curve that leaves and arrives with the planted foot's own velocity, the foot turns smoothly to its new heading, and the path is lifted so that the sole clears the floor by 4.5 cm in mid-swing. It is also pushed away from the other foot if needed. The leg follows by IK.

### 6. Upper body (`upper_body.py`)

As before, the thorax and head orientations are set in the world and spread over the spine and neck joints. New:
- The thorax faces where the pelvis will face 0.2 s later.
- The head turns towards where it will face 0.55 s later, taking 75 % of that direction relative to the thorax. This gives the natural order (eyes and head, then trunk, then pelvis and feet) for bends, corners and turns on the spot alike.
- Arm swing, thorax counter-rotation and head bob scale with the step size.
- When standing, the arms hang relaxed (elbows bent 12°), the chest moves slightly with breathing, and the head drifts slowly.

All stages are vectorised over frames with numpy.

## What changed compared with the starting point (`previous/E02-curved-path`)

- **New architecture.** Footstep plan → balance model → body, instead of pelvis track → footprints. New modules: `plan.py` (behaviours, plants, stance clocks, heading program, envelopes) and `balance.py` (centre of pressure, inverted pendulum). `walker.py` became `body.py`; the old gait clock was removed.
- **New behaviours.** Standing, starting from standing, stopping, step turns at corners and turning on the spot. Walking that is already under way is handled by starting 6 m before the start position and shifting time so that the pelvis passes the start position at t = 0.
- **Stance clock per plant** instead of one global gait phase. Push-off size, loading response and landing pitch are per step.
- **Pelvis path from the balance model** instead of a prescribed sway and speed ripple. On straight walking the result matches the old one: heel strike 0.235 m ahead of the pelvis, ±2.5 cm sway.
- **Kept and reused:** the gait curves, foot rockers and IK, the closed-form heel rise and pelvis height, the swing splines, the bend slow-down and lean, and the arm and head detail.
- **Fixed:** the line-building error (corner arcs a little short), and the pelvis height overshooting between samples at touch-down.

## Main choices and why

- **Feet first, body from balance.** Starting, stopping and turning are defined by what the feet do; a person's body then moves the way the balance of a body over those feet requires. With a single physical model the transitions are consistent with no special cases. For example, the body begins to drift forward half a second before the first foot lifts, as in a real gait initiation.
- **Step turn at the corner, outer foot at the apex.** A 90° corner within ±0.3 m cannot be taken by spreading the turn over many steps; the body must turn about 45° per step. The first attempt placed feet along a smoothed line and ended up with the outer foot inside the corner and legs crossing. Planting the outer foot outside the corner, with the steps around it shorter, makes the turn work with plausible joint ranges (hip rotation at most 38°).
- **The pelvis rounds the corner** about 12 cm inside the drawn corner (tolerance 30 cm). Cutting corners like this is what real walkers do.
- **Six steps for the 180° turn.** With four steps of 90° the hips needed 54° of external rotation and the feet came within millimetres of each other. Six steps of 60° keep the hips within about 38°, at 0.43 s per step (2.5 s in total).
- **Ambiguities, and what I decided:**
  - Standing "for a moment" at the start: 0.8 s, then 0.3 s of weight shift.
  - Pace: the normal steady pace is still 1.23 m/s, but on this short path (3 m to the corner, starting from standing) the person never reaches it. They peak at about 1.0 m/s, slow to about 0.6 m/s at the corner and average about 0.85 m/s while walking, which I think is what a real person does over such a short course.
  - Which foot steps first: the one that makes the corner a step turn (the right foot here).
  - Which way to turn round: a 180° turn could go either way; the planner turns towards the side of the foot that was put down last, so that foot steps first (left here).
  - End pose: the pelvis ends on the end point; the feet end side by side but staggered by about 8 cm, as people rarely stop with feet perfectly aligned.
  - Hands, jaw and eyes are left at zero (relaxed hand, closed mouth, eyes forward).

## How I checked the result

- **`evaluate.py`** on all three task files: all targets met (tables above).
- **`analyze.py`** on `motion.npz`:
  - no sole point more than 1.5 mm below the floor;
  - planted feet: contact-point speed median 0.0 cm/s, 95th percentile 0.6–0.8 cm/s;
  - the two soles never closer than 4.4 cm, the shank axes never closer than 8 cm;
  - knees 4–66°, except that the right knee reaches full extension (−0.2°, which is straight for this skeleton) for a moment in the last turning step;
  - hip rotation within ±38°, ankle 16° plantarflexion to 24° dorsiflexion;
  - fastest joint 465 °/s.
- **`tools/check_tasks.py`** over the 11 task files (the three above plus `test_tasks/`): everything generates in 0.5–0.8 s, with fastest joints 460–675 °/s, no sinking beyond 1.6 mm, soles at least 2.9 cm apart, and stops ending within 0.6 cm and 0° of the requested pose. The previous session's 90° corner test, which failed with the old code, now works (step turn). That task's path is shorter than its 10 s clip, so the walker continues straight past its end, as before.
- **Rendered previews**, 5 of the 8 allowed:
  - the corner (3.4–5.2 s): this showed the feet passing too close right after the corner, which led to the foot-clearance guard;
  - the start (0.8–2.6 s);
  - the stop and turn (6.6–10.8 s);
  - a closer look at the turning steps (8.4–10.6 s);
  - the stop with the final parameters (6.2–8.4 s).

  They show natural standing, a forward lean into the first step, steps growing and shrinking, the head turning into the corner and into the turn first, compact turning steps without crossing, and in the top view the pelvis track on the drawn path.
- **Numbers that drove the design changes** (all found with `analyze.py` before the final version): feet nearly touching after the corner, a 63° ankle and over-stretched leg at the corner push-off, heels colliding in the turn, toes dipping 5 mm into the floor at early swing, and the knee snapping straight at heel strike.
- **Determinism.** Repeated runs give bit-identical files.

## Known weaknesses

- **Corner details.** In the step turn, the outer foot lands toed-in about 35° relative to the still forward-facing pelvis, and the inner foot lands toed-out about 38° relative to the pelvis. These are large but brief hip rotations. The forefoot pivot makes the contact skin move a little (that is where the remaining 95th-percentile sliding comes from). Corners closer together than about 2 m force short steps between them.
- **Turning on the spot.**
  - The six steps are regular in timing and size, which is slightly mechanical.
  - The arms hang still during the turn; real arms swing a little with the body's rotation.
  - The final stance is staggered by about 8 cm.
- **Balance model.**
  - The body is treated as a point mass at constant height. Vertical motion and the fine timing of the weight shift (for example the backward and sideways push of the centre of pressure that real people make just before the first step) are not modelled.
  - The forward speed varies by about ±0.15 m/s within each step. That is realistic, but larger than the old ±0.05 m/s, and push-off is a little stronger (ankle plantarflexion up to 27° instead of 20° in steady walking).
- **Timing is not planned against the clip length.** The plan does not stretch or compress itself to fit the clip. If a task's walk plus turn takes longer than the clip, a warning is printed and the motion is simply cut. Here the person stands for 1.3 s at the end.
- **Inherited.** The gait curves are hand-tuned from memory of typical gait. Heel strike is a deliberate velocity discontinuity. Self-contact is checked only between feet and leg axes, not on the skin. There is no obstacle avoidance (a warning is printed).

## Extending the library

- New tasks that combine standing, walking along a path, stopping and turning on the spot need only a task file. `task.py` composes `PlanBuilder.stand / wait / walk / turn`.
- New behaviours (a side-step, a step over an obstacle, a detour) should be written as new `PlanBuilder` methods that append footsteps. Everything after the plan (balance, plants, stance clocks, pelvis height, legs, upper body) works on any footstep sequence. The footstep `kind` chooses the swing style: `walk` for joint-space walking swings, `shuffle` for foot-path swings.
- Obstacles could be handled by bending the feet line around them, or by a planner that places footsteps directly.
- Parameters are in `gait.DEFAULTS` and can be overridden with `generate_motion(task, params={...})`. Set the environment variable `LOCO_DEBUG=1` to print how steps are distributed between corners.
