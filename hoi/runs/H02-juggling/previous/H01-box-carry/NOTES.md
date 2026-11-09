# Pick up a box, carry it and put it down: notes

## Summary

`make_motion.py` turns a task file into 20 seconds of motion: a person walks to a box, bends down, takes hold of it, lifts it, carries it to the marked spot, sets it down, lets go, stands up and steps back. Nothing is recorded or copied; everything is computed from the task.

For `task.json` all 38 targets of `evaluate.py` are met. On 12 extra tasks I wrote to test other boxes and layouts, 8 meet every target. Of the other 4, two miss one target by less than 1 mm, one has an arm pressing into a thigh, and one is a deliberately extreme box (details under [How I checked the result](#how-i-checked-the-result)).

The main visible weakness is the grip: the hands press flat on the two sides of the box, with no fingers under it (see [Known weaknesses](#known-weaknesses)).

## What is here

| file | what it is |
|---|---|
| `make_motion.py` | `python make_motion.py <task.json> <out.npz>` writes the motion. A task with an object goes to `manipulation/`, a walking task to `locomotion/`. |
| `locomotion/` | the walking library from the starting point, with a few additions (listed below) |
| `manipulation/` | the new library for handling objects |
| `motion.npz` | the motion for `task.json`. `check_format.py` prints `OK: 600 frames at 30 fps`. |
| `test_tasks/` | 12 extra task files (written by `tools/make_test_tasks.py`) |
| `tools/` | checking tools, not needed to generate motion (listed at the end) |

**Speed.** Generating `task.json` takes about 3–4 s of computing, plus about 3 s to start Python, for a 20 s clip. The slowest test task took 6.4 s of computing. **Determinism.** Repeated runs give bit-identical files.

## Terms used below

- **Joint rotation, pose**: the body is a skeleton; a pose is the rotation of every joint for one frame.
- **Forward kinematics (FK)** computes where the joints end up from their rotations. **Inverse kinematics (IK)** is the reverse: it finds rotations that put a hand or foot at a wanted place.
- **Centre of mass (COM)**: the average position of the body's mass. A person stays balanced while the COM is above the area of the feet. **Centre of pressure (COP)**: the point on the floor through which the weight acts.
- **Inverted pendulum**: a simple balance model in which the body is a mass balanced on the COP, like a stick on a fingertip.
- **Footstep plan**: the list of where and when each foot is put down. **Stance**: how the feet stand. **Stride**: the distance of two steps.
- **Heading**: the direction someone faces on the floor. 0° faces +Z, and turning left increases it.
- **Dubins curve**: the shortest path between two positions-with-headings when turning is limited to a given radius. It is made of an arc, a straight piece and an arc.
- **Pole direction**: the direction an elbow points. Hand and shoulder alone leave the elbow free to swing around the line between them.
- **Pelvis tilt, thorax pitch**: how far the pelvis and the chest are tipped forward.
- **Tempo**: a factor on the duration of the handling phases (0.9 = 10 % quicker).

## How it works

The order of work is: decide what happens when, then work out the legs and pelvis, then the box, then fit the arms to the box, then correct the balance and repeat.

### 1. What happens when (`manipulation/script.py`, `route.py`, `box.py`)

**Which side of the box.** A person facing a box holds it by the faces on the left and right. There are four sides to walk up to, and two sides to stand on at the target, because a box turned by 180° looks the same. `choose_holds` prices all eight combinations by the walking time of both routes, by how awkward the grip is (very wide, very narrow, deeper than wide), and by how far the person would have to walk around the box. The box stays fixed relative to the body while it is carried, so the choice of side also fixes which way the person must face at the target.

**Routes.** `plan_route` compares Dubins curves, Dubins curves after a turn on the spot, and "turn, walk straight, turn". It picks the fastest. Routes through the box cost a lot. After every turn on the spot the rest is planned again, because turning moves the feet a little. Within 30 cm of the target the person just takes two small steps.

**Timing.** The events (`stop1`, `contact`, `lift0`, ... see the top of `script.py`) depend on the weight of the box. The job is fitted to the clip in stages: first a tempo down to 0.88 with everything in it, then dropping the final step back, then a tempo down to 0.72, then walking up to 20 % faster, and as a last resort a tempo of 0.62. Lifting and lowering have minimum durations that the tempo cannot shorten, because a rushed lift looks as if the box were light.

For `task.json` (tempo 0.94):

| time | what happens |
|---|---|
| 0 – 0.75 s | stands still |
| 0.75 – 4.25 s | walks 2.6 m to the box, looks down at it during the last steps, stops with the feet wide apart and the left foot 5 cm ahead |
| 4.5 – 5.75 s | bends down: the trunk leads, the hips go back; the fingers open; the palms reach the box at 5.64 s |
| 5.75 – 6.43 s | takes hold, then braces: the hips start to rise and the arms straighten while the box stays on the floor |
| 6.43 – 7.8 s | lifts: the box comes off the floor gently and rises with the legs, the trunk extends and ends leaning back |
| 7.8 – 8.2 s | the legs give a little under the load, then push back up |
| 8.2 – 13.0 s | carries the box along a curve, with shorter and slower steps than before |
| 13.3 – 15.1 s | lowers: the box goes out and down with the trunk; the last 4 cm take 0.7 s |
| 15.1 – 15.7 s | holds the standing box, the fingers relax, the hands move away |
| 15.8 – 17.05 s | stands up, the arms passing outside the thighs |
| 17.2 – 19.0 s | two small steps back out of the wide stance |
| 19 – 20 s | stands still |

### 2. Legs and pelvis (`locomotion/`)

Unchanged in principle: the footstep plan gives the COP, the inverted pendulum gives the COM, and the pelvis and legs follow. The new part is a **posture program** (`Posture` in `rig.py`) that the body reads. It has channels such as how far the pelvis drops, pelvis tilt, thorax pitch and load. Each channel is a sum of smooth moves that start and stop at zero speed. Because the moves of different channels overlap in time, the body moves as one flowing movement rather than one joint after another.

### 3. The box (`Rig.box_pose`)

The box stands on the floor until the lift, ends exactly on the target, and in between follows the pelvis with some smoothing. So it does not copy every small movement of the body: it takes 75 % of the pelvis bob, rolls and turns by about 1° with the steps, and drifts by a few millimetres, as a load in soft arms does. It turns with the chest, which leads the pelvis in a turn. While being lowered it passes 4.5 cm further out than its final position, to clear the knees.

### 4. Arms and hands (`arms.py`, `hand.py`, `Rig._arms`)

- **Grip.** The palm centre is 46 % of the box height above its bottom and 36 % of the depth from the near face, with the fingers pointing 45° down. The two hands differ slightly on purpose.
- **Arms.** From the moment the hands touch the box they are attached to it by IK, so they cannot slide. Before and after, the arm blends between its free walking swing and the IK solution, while the target rides up and down with the body so that the arm is not pulled straight.
- **Elbows.** The pole direction depends on the posture and on the box. Bent down, the elbows point out, but stay in for a narrow box. Upright, they stay near the trunk, but go out with a wide box so that the forearm does not cut across the corner of the box. An elbow never goes straighter than 6°. Forearm twist is shared between the elbow and wrist joints.
- **Fingers.** `HandShapes` solves three shapes numerically on the finger skeleton: relaxed, open, and a grip with every finger seated on the flat face and the thumb lying on it. The right hand mirrors the left. The fingers open on the way down, close at contact, and open again on release.
- **Head.** The head turns towards the box or the spot on the floor. This is computed from the body's own heading, because a plain compass direction is undefined when looking straight down (this caused a 989 °/s neck glitch).

### 5. Balance and fitting (`Rig.solve`, `massmodel.py`)

The skeleton carries a segment mass model (usual anthropometric shares, from general knowledge) that gives the true COM of body and box. Three passes then fit:

- how low the body goes, so that the arms reach the box at 92.5 % of their length;
- a pelvis shift, so that the combined COM is over the feet when standing. At the bottom it is 5 cm ahead of the middle of the feet;
- a small correction of the box height where the arms would otherwise be overstretched during lifting or lowering.

## What changed compared with the starting point (`previous/E04-narrow-passage`)

- **New:** the whole `manipulation/` package, `make_motion.py` choosing between the two libraries, and the tools in `tools/` that concern objects.
- **`locomotion/plan.py`:** `walk()` and `turn()` accept a final stance (width, toes, stagger), there is a new `reposition()` behaviour for small steps in any direction, and a plan can carry a posture program.
- **`locomotion/body.py`:** the pelvis reads the posture program, and knees are softer under a load.
- **`locomotion/upper_body.py`:** the trunk reads the posture program, and its walking oscillation is calmer under a load.
- **`locomotion/gait.py`:** arms hang 4° further out (`arm_abd_extra`), because the evaluation here showed the hands of the old arm swing up to 3.5 cm inside the thighs. This also changes plain walking tasks. I only re-checked that such a task still generates and passes the format check; I did not re-run the earlier walking evaluations.
- **Kept unchanged:** the gait, stops, turns and narrow-gap code, and the balance model.

## Main choices and why

- **Bend at hips and knees together.** A pure squat cannot reach the box: my first attempt ended with the pelvis at 0.33 m, nearly sitting on the heels. Shoulders must come down to about 0.64 m to reach the hands, so the trunk has to tip well forward. The result has the pelvis at 0.45 m and a trunk lean of 60°, which is how most people lift something from the floor, rather than the ideal textbook lift.
- **Hands on the side faces, box close to the belly.** The box has no handles, and `evaluate.py` looks for hands on opposite sides. The box touches or nearly touches the belly while carried, because that is how a load is really held.
- **The trunk moves with the box when lowering.** The box has to go out from the body and down, and the arms can only follow if the trunk goes too. Getting this right reduced the height correction from about 19 cm to under 2 cm.
- **Balance is only fully enforced when standing.** Walking, the pelvis takes 40 % of the shift that would balance the load. When it took all of it, the leading foot was out of reach at each touchdown, and the pelvis dipped 10 cm within two frames. Real people carrying something also let the load run a little ahead of them.
- **Hands stand 7 mm off the face at the palm point.** The skin of the ball of the thumb bulges past the palm point that `body_info.json` gives. I found this because `evaluate.py` reported 14 mm inside the box while my own skin points reported under 5 mm.
- **Ambiguities, and what I decided:**
  - *"Next to the box"*: the person ends facing the box, a step back from it, about 0.4 m from it.
  - *Clip longer than the job*: the phases are slowed by up to 12 % and the rest is spent standing.
  - *Body mass*: `task.json` says 76 kg and `evaluate.py` uses 75 kg; I used 76 kg. The difference does not matter.
  - Jaw and eyes are left at zero.

## How I checked the result

### Final `evaluate.py` table (`task.json`, `motion.npz`)

38 of 38 targets met.

| | Measurement | Value | Target |
|---|---|---|---|
| ✅ | Deepest sinking into the floor | 6.84 mm | ≤ 10 mm |
| ✅ | Frames sinking more than 1 cm | 0 frames | 0 |
| ✅ | Frames with nothing on the floor | 0 frames | 0 |
| ✅ | Typical speed of floor-touching skin | 0.12 cm/s | ≤ 1 cm/s |
| ✅ | Speed of floor-touching skin, 95th percentile | 1.03 cm/s | ≤ 3 cm/s |
|  | Distance travelled by the pelvis | 6.96 m |  |
|  | Average speed | 0.35 m/s |  |
| ✅ | Start position error | 0.64 cm | ≤ 15 cm |
| ✅ | Start heading error | 0 ° | ≤ 15° |
| ✅ | Pelvis speed while standing at the start | 4.11 cm/s | ≤ 10 cm/s |
| ✅ | Pelvis speed while standing at the end | 0.61 cm/s | ≤ 10 cm/s |
| ✅ | Fastest joint rotation | 603.53 °/s | ≤ 800 °/s |
| ✅ | Frames with a pop | 0 frames | 0 |
| ✅ | The box starts where the task says | 0.03 mm | ≤ 5 mm |
| ✅ | Hands on the box before it moves | 1 s | ≥ 0.15 s |
| ✅ | Frames the box moves without both hands on it | 0 frames | 0 |
| ✅ | Largest gap between a hand and the box while carrying | 0 mm | ≤ 10 mm |
| ✅ | Deepest hand skin inside the box | 8.41 mm | ≤ 10 mm |
| ✅ | Fewest hand skin points touching the box | 378 points | ≥ 40 |
| ✅ | Hands sliding over the box while carrying | 0.61 cm | ≤ 2 cm |
| ✅ | How opposite the two hands are | 147.87 ° | ≥ 120° |
| ✅ | Highest the bottom of the box gets | 80.62 cm | ≥ 20 cm |
| ✅ | Frames the box slides along the floor | 0 frames | 0 |
| ✅ | Deepest the box goes into the floor | 0 mm | ≤ 3 mm |
| ✅ | Largest tilt of the box while carrying | 2.82 ° | ≤ 15° |
| ✅ | Fastest the box moves | 1.14 m/s | ≤ 2 m/s |
| ✅ | Strongest acceleration of the box | 3.36 m/s² | ≤ 5 m/s² |
| ✅ | Distance from the marked spot | 0 cm | ≤ 10 cm |
| ✅ | Final rotation error of the box | 0 ° | ≤ 15° |
| ✅ | The box stands on the floor at the end | 0.03 mm | ≤ 3 mm |
| ✅ | Final tilt of the box | 0 ° | ≤ 1° |
| ✅ | Speed at touchdown | 0.1 m/s | ≤ 0.15 m/s |
| ✅ | Hands stay on the box after it lands | 0.73 s | ≥ 0.1 s |
| ✅ | Hands off the box at the end | 57.07 cm | ≥ 5 cm |
| ✅ | Standing up at the end | 99.84 % of height | ≥ 96 % |
| ✅ | Deepest body skin (not hands) inside the box | 7.45 mm | ≤ 15 mm |
| ✅ | Deepest forearm or hand skin inside the trunk or legs | 2.27 mm | ≤ 15 mm |
| ✅ | Knees and elbows bending the wrong way | 0 ° | ≤ 5° |
| ✅ | Largest wrist rotation | 41.79 ° | ≤ 85° |
| ✅ | Frames off balance with both feet down | 0 frames | 0 |
|  | Worst balance margin | -0.9 cm |  |
|  | Lowest pelvis height | 0.45 m |  |
|  | Trunk lean at the grip | 59.63 ° |  |
|  | Walking speed without the box | 0.87 m/s |  |
|  | Trunk lean without the box | -1.15 ° |  |
|  | Walking speed with the box | 0.79 m/s |  |
|  | Trunk lean with the box | -4.12 ° |  |
|  | Box centre in front of the chest while carrying | 28.75 cm |  |
|  | Height of the box centre while carrying | 0.95 m |  |

### Other boxes and layouts (`tools/eval_all.py`)

Each task was generated and evaluated with the final code. Sizes are `[x, height, z]`.

| task | box | what it tests | failed targets |
|---|---|---|---|
| `close-target` | 0.4 × 0.3 × 0.3, 10 kg | target 1.2 m away, turned 30° | none |
| `tall-box` | 0.35 × 0.5 × 0.3, 9 kg | tall box, target to the left, −90° | none |
| `target-behind` | 0.4 × 0.3 × 0.3, 14 kg | target behind the person: turn with the box | none |
| `target-right` | 0.3 × 0.4 × 0.3, 8 kg | box turned 90°, target to the side | none |
| `tiny-move` | 0.4 × 0.3 × 0.3, 10 kg | target 22 cm away | none |
| `typical-a` | 0.5 × 0.35 × 0.3, 12 kg | box slightly off to the side and turned, target behind left | none |
| `typical-b` | 0.35 × 0.3 × 0.35, 7 kg | start not facing the box exactly | none |
| `typical-c` | 0.45 × 0.25 × 0.35, 8 kg | start elsewhere, heading 90° | none |
| `far-target` | 0.45 × 0.3 × 0.35, 12 kg | target 5.6 m from the box | body in box 15.62 mm (≤ 15) |
| `left-rotated` | 0.5 × 0.25 × 0.35, 6 kg | held along its 0.5 m side, so it is deep | body in box 15.77 mm (≤ 15) |
| `small-light` | 0.3 × 0.2 × 0.25, 4 kg | small, low box | arm in leg 23.19 mm (≤ 15) |
| `wide-heavy` | 0.6 × 0.3 × 0.4, 15 kg | deliberately extreme, tempo down to 0.62 | hand in box 18.22 mm (≤ 10), hand sliding 3.13 cm (≤ 2), box acceleration 5.44 m/s² (≤ 5), body in box 41.1 mm (≤ 15) |

The test tasks were written by me, so they show what I thought of, and they were also used to tune the code. They are not an independent test. Of them, I only looked at rendered images of a stretch of `target-behind`; the others were only measured.

### Rendered previews

I used 10 of the 12 allowed: 9 on `motion.npz` and 1 on `target-behind` for turning with the box. `tools/zoom.py` enlarged the hands.

| phase of `motion.npz` | last seen |
|---|---|
| lift (5.8–8.7 s) and carry (8.4–13 s) | on the final file |
| lowering (12.9–15.9 s) | one small change later: undoing a 5 mm test of the carry gap |
| approach (0.8–4.6 s) | before the last route and lowering changes, which leave this phase's walking the same |
| release, standing up, step back (16.4–19.8 s) | before the elbow, route and lowering changes, and those moved this phase about 0.2 s earlier in the clip; its numbers were checked with `evaluate.py`, but I did not look at it again |

### Bugs the checks found

These are worth knowing about, because `task.json` alone showed none of the first three:

- **Box spinning.** The box's yaw could differ by a full turn from the body's heading, so it spun round while being lifted or put down.
- **Missing the box.** A heading error under 3.4° skipped the turn but kept walking along the wrong heading, leaving the person 7 cm off-centre. The layout of `task.json` has exactly zero error, so it could not show this.
- **Routes that never arrived.** After that fix, one route kept turning on the spot and never walked, and the height correction then threw the box around at 32 m/s. Straight walks now aim exactly at the target, the correction is limited to 15 cm, and a warning is printed if a route ends away from its stance.
- **Hidden lowering problem.** All targets were met while the height correction was silently bending the box's path by 19 cm. I only saw this because limiting the correction made the numbers worse.

## Known weaknesses

- **The grip is the weakest part visually.** The hands press flat on the side faces, and a real 10 kg box would more likely be held with fingers under it. Fingers cannot get under a box standing on the floor without tilting it or sliding the hands. I did not build that. Physically, the carry relies on friction and on the box resting against the belly.
- **Hand skin is close to its limit.** It goes 8.4 mm into the box against a target of 10 mm, because of the bulge of the ball of the thumb. Moving the hands out further would leave a gap at the fingers.
- **Effort is shown only through timing and posture.** There is no breathing harder, no shoulder strain, and no adjusting of the grip while walking.
- **The bottom of the bend is fairly deep** (pelvis 0.45 m, knees about 118°, hips strongly flexed). It looks plausible in the previews, but a person might stand a little closer or round the back more.
- **Unusual boxes:**
  - Deep boxes (0.35 m or more) reach about 16 mm of body in the box while lifting or lowering.
  - Narrow low boxes press a forearm into a thigh.
  - Very wide and heavy boxes fail several targets. At a tempo of 0.62 they also look rushed.
- **The box cannot be turned in the hands.** The person must walk to the matching heading, which makes some layouts slow. `close-target` spends about 6.5 s on a 1.2 m move, turning, walking and turning again.
- **Routes only avoid the box itself.** Other obstacles in a task are ignored. The carry route does not check that the walking line stays clear of anything.
- **Small steps are plain.** `reposition()` steps are simple foot paths, not real backward walking.
- **Everything is fitted to this body.** Belly depth, stand-off from the box and the arm reach are measured values for this one body shape, as in the earlier work.
- **Inherited from the starting point.** The gait curves are hand-tuned, heel strike is a deliberate velocity jump, and the balance model treats the body as a point mass at constant height.

## Extending the library

- **Another object or action:** `script.py` is the place to write a new sequence. Add events, append footsteps to the plan, and add moves to the `Posture` in `Rig._posture_moves`. `box_pose` and `Rig._grip` are the parts specific to a box.
- **Other grips:** a grip is a contact point and a hand rotation per hand in the object's own frame (`Rig._grip`), plus a finger shape (`HandShapes`).
- **Parameters:** `script.DEFAULTS` and `rig.DEFAULTS`, overridden with `generate_box_motion(task, params={...})`. Gait parameters are in `locomotion/gait.py` and go in through `gait={...}`.
- **Inspecting a run:** `generate_box_motion` returns the `Rig` under `motion["rig"]`.
- **Watch `fix_y`:** if the correction of the box height (`Rig.fix_y`) grows beyond a few centimetres, the box and body are out of step.

Tools in `tools/`:

| tool | what it does |
|---|---|
| `eval_all.py` | generates and evaluates all test tasks into `test_out/` and lists failed targets |
| `make_test_tasks.py` | writes `test_tasks/` |
| `report.py` | event times, reach, joint ranges of a generated motion |
| `peaks.py` | when the body-in-box and arm-in-body numbers peak, by phase |
| `diagnose.py` | hand skin points inside the box, fastest joints, backward joints, box acceleration |
| `near_box.py` | which joints are closest to the box at a given moment |
| `meanings.py` | failed metrics with their meanings, and timeline peaks |
| `compare.py` | checks whether two motion files are identical |
| `zoom.py` | enlarges part of a preview image (from the earlier session) |
| `clean.py` | removes generated working files (`test_out/`, Python caches) |
