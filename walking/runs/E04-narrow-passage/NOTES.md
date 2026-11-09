# Squeeze through a narrow gap: notes

## What is here

| file | what it is |
|---|---|
| `make_motion.py` | `python make_motion.py <task.json> <out.npz>` writes the motion for any task file. Deterministic (repeated runs give bit-identical files). |
| `locomotion/` | the reusable motion library that `make_motion.py` uses (described below) |
| `motion.npz` | the motion for `task.json` (330 frames). `check_format.py motion.npz task.json` prints `OK: 330 frames at 30 fps`. |
| `motion_turns.npz`, `motion_curved-path.npz`, `motion_straight-walk.npz` | the motions for the three earlier tasks in `tasks/` |
| `analyze.py` | checking tool (from the previous session): forward kinematics on a saved file, then foot contact, sliding, swing clearance, distances between the feet and legs, joint ranges and speeds, path |
| `tools/` | more checking tools, none needed to generate motion (list at the end) |
| `test_tasks/` | extra task files: the eight from the previous session and ten new ones with gaps |

**Speed.** Generating the 11 s clip takes about 2.2 s of computing (0.5–0.8 s for the tasks without obstacles, 3.7 s for a 14 s clip with two gaps). Starting Python and importing numpy and scipy adds about 3 s of wall-clock time.

## Final results (`evaluate.py`)

**This task** (`task.json`, `motion.npz`):

| | Measurement | Value | Target |
|---|---|---|---|
| ✅ | Deepest sinking into the floor | 4.05 mm | ≤ 10 mm |
| ✅ | Frames sinking more than 1 cm | 0 frames | 0 |
| ✅ | Frames with nothing on the floor | 0 frames | 0 |
| ✅ | Typical speed of floor-touching skin | 0.29 cm/s | ≤ 1 cm/s |
| ✅ | Speed of floor-touching skin, 95th percentile | 1.43 cm/s | ≤ 3 cm/s |
|  | Distance travelled by the pelvis | 8.44 m |  |
|  | Average speed | 0.77 m/s |  |
| ✅ | Average distance from the path | 1.7 cm | ≤ 15 cm |
| ✅ | Largest distance from the path | 4.32 cm | ≤ 15 cm |
| ✅ | Start position error | 2.12 cm | ≤ 15 cm |
| ✅ | Start heading error | 1 ° | ≤ 15° |
| ✅ | Closest approach to the left cabinet | 3.88 cm | > 0 cm |
| ✅ | Frames touching the left cabinet | 0 frames | 0 |
| ✅ | Closest approach to the right cabinet | 4.27 cm | > 0 cm |
| ✅ | Frames touching the right cabinet | 0 frames | 0 |
| ✅ | Fastest joint rotation | 452.01 °/s | ≤ 800 °/s |
| ✅ | Frames with a pop | 0 frames | 0 |

**Start, corner, stop, turn round** (`tasks/turns.json`, `motion_turns.npz`):

| | Measurement | Value | Target |
|---|---|---|---|
| ✅ | Deepest sinking into the floor | 4.12 mm | ≤ 10 mm |
| ✅ | Frames sinking more than 1 cm | 0 frames | 0 |
| ✅ | Frames with nothing on the floor | 0 frames | 0 |
| ✅ | Typical speed of floor-touching skin | 0.16 cm/s | ≤ 1 cm/s |
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
| ✅ | Fastest joint rotation | 445.02 °/s | ≤ 800 °/s |
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

The straight walk and the S-shaped path give exactly the same numbers as at the end of the previous session. The turns task changed slightly: typical skin speed 0.15 → 0.16 cm/s, fastest joint 465 → 445 °/s. The new rule that a swinging leg must be able to reach its foot (below) also applies to its turning steps on the spot, and lowers the pelvis a little there. All its other numbers are unchanged.

## What the person does in `task.json`

The gap between the cabinets is 0.40 m wide and 0.60 m deep (z = 4.0 to 4.6). The body is about 0.55 m wide seen from the front (arms included) and about 0.30 m deep from belly to back. Walking straight in, it went 7.7 cm into each cabinet (the first thing I measured). So the person must turn fully sideways.

| time | what happens |
|---|---|
| 0 – 2.5 s | walks along +Z at about 1.2 m/s (already walking at z = 0 when the clip starts) |
| 2.5 – 3.1 s | the last two walking steps get shorter (0.92 and 0.80 of a normal step) and the person slows down; the head is already turned towards the gap |
| 3.1 – 3.5 s | **entry step**: the right foot is put down in front, turned 60° to the left, about 15 cm before the gap; the trunk leads and the body begins to turn left over this foot |
| 3.65 – 4.07 s | the left foot comes round behind and is put down sideways; the body now faces +X (the left cabinet), turned 90° from the walking direction; it pauses for an instant (speed close to 0) |
| 4.2 – 7.1 s | **three side-step cycles**: the right foot steps about 0.3 m sideways towards +Z, the left foot closes up to 0.20 m from it. Knees are slightly soft, the trunk upright, the arms hang close, and the head turns about 60° to look where the body is going, a little downwards |
| 7.2 – 7.55 s | **exit step**: the right foot steps out past the gap, turned back to 35° from the walking direction, and the body turns back over it |
| 7.6 – 8.05 s | the left foot swings forward into the first walking step (0.42 m) |
| 8.1 – 11 s | walking resumes, with steps and arm swing growing back to normal; 1.2 m/s again by about 9.2 s; the pelvis is at z = 8.6 m (still walking, inside the 10 m path) when the clip ends |

## Terms used below

- **Gait cycle**, **stride**, **step**: a gait cycle runs from one heel strike of a foot to its next (about 1.06 s in steady walking). A stride is the distance covered in one cycle (1.30 m). A step is half of that, from one foot's touch-down to the other's.
- **Stance** and **swing**: the time a foot is on the floor or in the air. **Double support**: both feet on the floor.
- **Heel strike**, **toe off**: the moments a foot lands (normally heel first) and leaves the floor.
- **Plant**: one period during which a foot is on the floor. **Footstep plan**: the list of where and when each foot is put down.
- **Stance clock**: a number from 0 (touch-down) to 0.6 (toe off) that says how far a plant has progressed. It drives the rolling of the foot over heel, sole and toes, and the knee bend.
- **Centre of mass (COM)**: the average position of the body's mass, near the pelvis. **Centre of pressure (COP)**: the point on the floor through which the body's weight acts.
- **Inverted pendulum**: a simple balance model in which the body is a mass balanced on top of the COP, like a stick on a fingertip.
- **Forward kinematics (FK)** computes joint positions from joint rotations. **Inverse kinematics (IK)** is the reverse: it finds the leg joint rotations that put the foot at a given place.
- **Heading**: the direction someone faces on the floor. 0° faces +Z, and turning left increases it. A **heading offset** is an extra rotation added on top of the heading the path gives.
- **Side step / step-close**: moving sideways by stepping out with the leading foot and then bringing the trailing foot up to it.
- **Passage**: my name for a stretch of the path where obstacles leave too little room to walk through normally.
- **Hip rotation**: turning the thigh about its own long axis (internal = knee turns inwards, external = outwards). Comfortable ranges are roughly 35–40° each way.
- **PCHIP**: a smooth interpolating curve through given values that never overshoots them.

## How it works

The motion is computed, not drawn or copied; no motion data is used. The architecture is the previous session's: **first decide where and when every foot goes down (the footstep plan), then let a balance model work out how the body moves over those feet, then pose the legs and the upper body.** In the order `locomotion/` runs it:

1. **Lines** (`path.py`): the task path becomes a feet line (where footprints go) and a smoother body line (gives the pelvis heading).
2. **Obstacles** (`obstacles.py`, new): finds the passages on the feet line (next section).
3. **Footstep plan** (`plan.py`): behaviours append footsteps: `stand`, `wait`, `walk` (with corners as step turns, stopping, and now passages) and `turn` on the spot. The plan then derives each foot's plants and stance clocks, the heading program, and *envelopes*: smooth 0-to-1 curves that scale things in and out. Examples are the step size (gait oscillations fade in and out with it), the sideways envelope and the arms-still envelope.
4. **Balance** (`balance.py`): the COP runs under the planted feet; the COM follows from the linear inverted pendulum (in effect, the COP smoothed over about 0.3 s). Slowing down into the gap, the pause while turning sideways, the stop-and-go of side-stepping and the speeding up afterwards all come out of this one model.
5. **Body** (`body.py`, `legs.py`): pelvis position from the COM, pelvis height from the knee bend wanted in the weight-bearing legs, stance legs by IK on the rolling foot, swing legs either by joint-space walking splines or by a foot path in space plus IK.
6. **Upper body** (`upper_body.py`): spine, head and arms, set in world terms and spread over the joints.

### Finding gaps (`obstacles.py`)

Obstacles are upright boxes (centre, size, yaw). At every centimetre along the feet line, the code measures the free interval across the line: the distance to the nearest box on the left and on the right (sampled every 5 mm, up to 1.5 m out). Where the free width is less than the body seen from the front with swinging arms plus a margin (2 × (0.28 + 0.035) = 0.63 m), that stretch becomes a **passage**. It records where the narrow part starts and ends, its width and where its middle is. Then it chooses how to pass:

- **Shoulder mode** (gaps of about 0.58–0.63 m): keep walking, hold the arms still and close to the body, and turn the shoulders just enough. Seen from above, the shoulders and arms are taken as a block (half-width 0.25 m, half-thickness 0.07 m) and the chest as a point 0.15 m in front. Turned by an angle β, the body then reaches max(0.25 cos β + 0.07 sin β, 0.15 sin β + 0.10 cos β) across the gap, plus 2.5 cm of walking sway. The smallest β up to 45° that fits with the margin is used; the thorax takes 65 % of it and the pelvis 35 %.
- **Side mode** (narrower gaps; the task's 0.40 m gap): turn fully sideways and side-step through.
- Gaps narrower than the body's depth, gaps whose middle is further from the path than its tolerance, and paths that run straight through a box are reported as warnings.

These body dimensions were calibrated with `evaluate.py` on test gaps, because the mesh itself is not available to my code.

### Passing sideways (`plan.py`: `walk`, `_passage_layout`, `_passage_steps`)

`walk()` is now split into **stretches**: from the start (standing) or from the exit of a passage, to the entry of the next passage, to the stop, or to the end of the clip. Each stretch distributes its steps between its anchors as before: corner apexes, the stop, and now the passage entry, where the leading foot must land exactly at the entry point. The last steps before a passage are shortened (0.92, 0.80, and 0.62 for the entry step) and slowed. The first steps after it are shortened too (0.65, 0.82, 0.94), so the walker speeds up again gradually.

The passage itself, in coordinates along the line (s) and across it (n), with the body facing the left of the path (the right foot leads):

- **Sideways stances.** The feet alternate between a narrow stance (their pressure points 0.20 m apart) and a wide one (one side step further). The narrow stances are centred from 0.15 m before the narrow part to 0.17 m after it, in equal side steps of at most 0.32 m. Here that is three steps of 0.30 m, from s = 3.86 to 4.77, with small deliberate variations in length (±5 %) and timing (±4 %). Every sideways foot stands so that its pressure point is on one line across the gap. That line is 8.5 mm in front of the gap's middle, which centres the body: the belly reaches 0.13 m in front of the pelvis and the buttocks 0.165 m behind it.
- **Entry (E1, E2).** E1 is the leading foot's last walking step, put down turned 60° towards the facing side. E2: the trailing foot comes round behind and is put down sideways.
- **Side steps** (0.38 s swing, 0.12 s double support): leading foot out, trailing foot in.
- **Exit (X1, X2).** X1: the leading foot steps out by 0.20 m, turned back to 35° from the line. X2: the trailing foot swings forward into the first walking step.
- **Heading.** A heading offset turns the body: 30° when E1 lands, 86–90° from E2 until X1 lifts, 62° when X1 lands, 10° when X2 lands, then 0. These values were chosen so that neither hip has to twist more than about 35°. The thorax faces where the pelvis will face 0.2 s later, so the shoulders turn first.

New footstep attributes describe how a foot leaves and lands, so that the rest of the pipeline handles side steps without special cases:

- **kind** `side` (a foot-path swing, like the turning steps);
- **lift style** `flat` (picked up nearly flat, with a 1° heel rise) or `walk` (heel rise and push-off over the toes);
- **land style** `flat` or `heel`;
- **lift height** (3 cm for side steps, 5 cm for X2).

The stance clock of a plant follows these styles, so a sideways foot stays flat and the centre of pressure stays mid-foot. It does not roll from heel to toe across the body's direction of travel.

### Legs in side steps (`body.py`)

- **Side-step foot path.** The foot is lifted before it moves sideways and has stopped moving before it is put down: for the first and last 12 % of the swing there is no horizontal motion. Without this, the sole skimmed the floor while moving, which counts as sliding. A foot leaving with a push-off (E2, X2) keeps its toe-off velocity instead. The foot's pitch is released during the first half of the swing, level in the middle, and set to the landing angle over the last 45 %.
- **Reach.** The pelvis height used to be solved only from the weight-bearing legs. Right after the trailing foot lifted, the pelvis rose while still moving away, and that foot was briefly out of reach: the knee locked straight. A second pass now also requires the pelvis to be low enough for every foot-path swing leg to reach its foot at 98.5 % of its length. While side-stepping, the stance knees are also bent 8° more. Knees now stay between 5° and 66°.
- **Pivots.** Before, a foot whose body had turned over it (as at corners) pivoted on the ball of the foot before toe off. In and out of a passage that made the skin slide at up to 14 cm/s. There the footholds and heading program are now planned so that the hips can absorb up to 35° of twist, and feet pivot only beyond that (in practice not at all).
- **First step after the passage (X2).** It is a foot-path swing that lands on the heel. A joint-space walking swing starting from a foot that points sideways swept the toes over the floor (a 13 cm slip in one frame, toes 1 cm into the floor). X2 leaves with a heel rise: a foot lifted flat could not reach, because the body has moved 0.3 m past it by then.

### Upper body (`upper_body.py`)

- **Gaze.** The head looks along the direction of travel: the heading offset is taken back out of the gaze direction. Sideways, the head turns about 60° relative to the thorax, with a soft limit at 65° neck rotation, and looks 5° further down.
- **Posture.** In a gap the trunk is held upright (less forward lean), the arms hang closer (abduction × 0.55) and the elbows bend 8° more.
- **Shoulder mode.** The thorax gets its own extra rotation, and arm swing is cut by 85 %.

## What changed compared with the starting point (`previous/E03-turns`)

- **New:** `obstacles.py` (boxes, the free-width scan, passages, choice of mode), `Passage`, stretches in `walk()`, the passage layout and its steps, heading offsets, the sideways, still-arms and thorax-offset envelopes, the shoulder-turn behaviour, and footstep lift and land styles.
- **Legs:** the side-step foot path; the swing-reach requirement on the pelvis height (it also protects turning steps on the spot); passage-specific pivot limits; softer knees while side-stepping; no swing-side pelvic drop while sideways.
- **Upper body:** gaze along the direction of travel, a soft neck-rotation limit, posture changes in gaps.
- **Kept unchanged:** everything else, including the walking gait, corners, starts, stops and turns on the spot (turning steps only gained the reach rule). The earlier tasks give the same or nearly the same numbers as before.

## Main choices and why

- **Fully sideways with step-close side steps.** With 0.40 m between the cabinets and a 0.30 m deep body, there is only 5 cm to spare on each side, and only when fully sideways; at 60° turned the body is already about 0.40 m wide. People squeezing through such a gap turn their shoulders square to it and shuffle sideways, leading with one side and looking where they go. Crossing the legs over (walking sideways) would be less stable and takes more room in front and behind.
- **Turn on the leading foot, turn back on it.** In: the leading foot's last walking step lands already turned in, the body turns over it, and the trailing foot comes round behind. Out: the leading foot steps out turned forward, the body turns over it, and the trailing foot swings through into walking. These are the step turns of the corner code, applied to the body's orientation rather than to the path.
- **Margins measured, not guessed.** I cannot see the mesh, so I measured with `evaluate.py`. I moved every frame outside a time window 50 m away and evaluated only the entry, sideways or exit window. I also cut the cabinets into slices 10 cm deep or 20 cm high, so each slice reports its own clearance. This showed that the sideways phase sets the limit (belly in front, buttocks behind, at hip height), so the body was centred there. The entry and exit had 8–11 cm to spare, which let me shorten the sideways stretch. When I shortened it too much, the trailing hand at the exit came within 1.4 cm, so it was lengthened again.
- **No pivoting feet in the passage.** A pivoting foot slides, and the evaluation (and viewers) see it. Planning the foot angles and the heading program so that the hips absorb the twist (at most about 35° of hip rotation) avoids it.
- **Ambiguities, and what I decided:**
  - Which way to face: either works for a symmetric gap. The default is to face the left of the path (`squeeze_turn = "L"`), here the left cabinet, leading with the right foot.
  - How fast: the approach slows from 1.2 m/s to a brief pause, side-stepping averages about 0.3 m/s, and walking speed is regained about 1 s after the exit. The whole passage takes about 5 s, so the person ends at z = 8.6 m, inside the 10 m path.
  - Hands, jaw and eyes are left at zero (relaxed hands, closed mouth, eyes forward).

## How I checked the result

- **`evaluate.py`** on all four required tasks: all targets met (tables above).
- **Windows and slices** (`tools/window.py`, `tools/slice_task.py`), final clearances in cm (left / right cabinet):

  | window | clearance |
  |---|---|
  | walking in and turning sideways (2.5–4.15 s) | 6.7 / 5.8 |
  | sideways (4.15–7.15 s) | 3.9 / 4.3 (sets the minimum) |
  | turning back and walking out (7.15–9 s) | 4.3 / 10.3 |
- **`analyze.py`:**
  - no sampled sole point more than 0.6 mm below the floor (`evaluate.py`, on the full skin, finds at most 4 mm);
  - planted feet: contact-point speed median 0.0 cm/s, 95th percentile 1.5 / 0.4 cm/s;
  - knees 5–66°, hip rotation within ±37°, ankles −31° to +27°;
  - soles at least 4.4 cm apart;
  - fastest joint 452 °/s.

  It also drove the fixes: sliding at 14 cm/s from pivots and from side steps landing while still moving; a toe 1 cm into the floor and a 13 cm slip at the first step out; knees locking straight (out of reach) as the trailing foot lifted; knee speeds up to 756 °/s in too-quick side steps.
- **Rendered previews**, 6 of the 8 allowed:
  1. the entry (2.7–4.5 s);
  2. an early version of the exit;
  3. one side-step cycle (4.5–5.55 s);
  4. a close look at the turn into the gap (3.1–4.3 s);
  5. the shoulder-turn mode on a 0.60 m test gap;
  6. the final exit (7.1–8.5 s).

  I enlarged parts of the images with `tools/zoom.py`, a small PNG reader written with zlib and numpy. They show a natural slow-down, the turn led by the head and trunk, the trailing leg coming round behind without crossing badly, a relaxed upright sideways stance looking towards the way out, regular but not identical side steps with soft knees, and a clean turn back into walking with the arm swing growing again.
- **Generality** (`tools/eval_all.py`): ten new gap tasks, all with every `evaluate.py` target met. Clearances (cm, left / right):

  | gap task | clearance |
  |---|---|
  | 0.40 m gap at 1.6 m, right after the start | 3.8 / 4.3 |
  | 0.42 m gap 8 cm off the path | 4.9 / 5.2 |
  | gap after a 30° bend, cabinets turned | 3.7 / 3.8 |
  | two gaps in a row | 3.7 / 4.3 and 4.7 / 5.3 |
  | standing start, gap, stop at 6 m | 3.8 / 4.3, end error 0.2 cm |
  | 0.50 and 0.55 m gaps (sideways) | 7.9 / 9.3 and 9.9 / 11.8 |
  | 0.58 and 0.60 m gaps (shoulder turn of 44° and 39°) | 4.2 / 9.7 and 5.2 / 10.6 |
  | 0.62 m gap (arms held still) | 7.1 / 8.2 |

  The eight older test tasks (corners, stops, turns) behave as before.
- **Determinism:** two runs give identical files.

## Known weaknesses

- **Side-stepping.**
  - The rhythm is regular apart from small variations, and the body almost stops during each closing step. That is physically consistent (it comes from the balance model) but may look slightly mechanical.
  - The arms hang still. A real person might brush a hand along a cabinet, hold the arms in front, or move them slightly with the steps.
- **Turning in and out.**
  - The body turns 60° in about 0.5 s on the entry and exit steps, and the hips twist up to about 35°.
  - When the right foot leaves its turned exit position, its toes skim the floor for one frame.
  - The trailing foot coming round (E2) lifts and lands on a foot path. It is smooth but simpler than a real swing.
- **Clearance model.**
  - The body dimensions for passages (half-width 0.28 m with swinging arms, 0.25 m with still arms, depth 0.30 m) and the centring offset were calibrated on this body with `evaluate.py`. A different body shape would need new values.
  - The planner does not check the finished motion against the obstacles itself; the margins (3.5 cm) are fixed.
  - In shoulder mode the clearance comes out uneven (closer on the left), and the walker does not slow down, which real people usually do.
- **Obstacles in general.** Only gaps across the path are handled. Paths running into a box, boxes beside the path that leave room on one side only, and low boxes that could be stepped over are reported but not avoided. An off-centre gap is centred only within the path tolerance.
- **Timing is not planned against the clip length.** If a task's actions take longer than the clip, a warning is printed and the motion is cut.
- **Inherited.** The gait curves are hand-tuned from memory of typical gait, and heel strike is a deliberate velocity discontinuity. Self-contact is checked only between feet and leg axes, not on the skin. The balance model treats the body as a point mass at constant height.

## Extending the library

- New tasks with gaps need only a task file: `task.py` passes the passages found by `obstacles.find_passages` to `walk()`. To force a mode or a side, edit or construct `Passage` objects (`mode="side"` or `"shoulder"`, `turn="L"` or `"R"`, `beta`) and pass them to `PlanBuilder.walk(..., passages=[...])`.
- Other ways of passing an obstacle (a detour, a step over a low box) can be written like `_passage_layout` / `_passage_steps`: a stretch ends at an anchor, the behaviour appends footsteps with suitable kind, lift and land styles, heading offsets and envelopes, and a new stretch resumes walking. Everything after the plan (balance, stance clocks, pelvis height with reach, legs, upper body) works on any footstep sequence.
- Parameters are in `gait.DEFAULTS` (new groups: body dimensions and gap margin, shoulder turn, squeeze/side steps, entry/exit, approach/resume). Override them with `generate_motion(task, params={...})`. Set the environment variable `LOCO_DEBUG=1` to print how steps are distributed and the passage layout.
- Checking tools in `tools/` (none needed to generate motion):

  | tool | what it does |
  |---|---|
  | `check_tasks.py` | quick numerical summary of many tasks |
  | `eval_all.py` | generate and run `evaluate.py` on many tasks |
  | `plan_report.py` | footstep plan and body state |
  | `joints.py` | leg joint angles frame by frame |
  | `window.py` | evaluate a time window only |
  | `slice_task.py` | cut obstacles into slices |
  | `clearances.py` | summarise metrics files |
  | `zoom.py` | enlarge part of a preview image |
  | `make_test_tasks.py` | writes the gap test tasks |
