# H01: Walking to a box, picking it up, carrying it and setting it down

> **Summary.** A person has to walk to a 10 kg box on the floor, pick it up, carry it to a marked spot about 3 m away, set it down carefully and stand up. Starting from the walking program of E04, the agent built a new library for handling an object. The result meets **all 38 measurement targets**, and the finished program also meets all 38 on a **layout it never saw**, with a different box, start and target, in 5 seconds of computing. Without being told how to lift, the agent bent the knees and hips, kept the box close to the body and leaned back under the load. The sequence looks convincing from a normal distance. The clear weakness is **the grip**: the hands press flat on the two sides of the box with spread fingers, which is not how a person holds a 10 kg box. The session took 99 minutes of working time and $16.74. The first motion meeting all targets was ready after only 24 minutes, at about $4–5; the rest went into other layouts and polish.

| | |
|---|---|
| **Experiment ID** | `H01-box-carry` (the same name is used for the folder and the videos) |
| **Date** | 2026-11-04 |
| **Task** | Walk to a box, lift it, carry it about 3 m, set it down on a marked spot, stand up; 20 s ([`tasks/box-carry.json`](../../tasks/box-carry.json)) |
| **Agent** | Claude Code, model Claude Opus 5.5, headless |
| **Started from** | the code of [E04](../../../walking/report/experiments/E04-narrow-passage.md) |
| **Tools the agent had** | `evaluate.py` (used 23 times), `preview.py` (used 10 of 12 allowed) |
| **Session** | 99 min of working time in two parts (interrupted once by the account usage limit), 183 turns, $16.74 |
| **Result** | 38/38 targets met, and 38/38 on the unseen task; about 4 s to compute the 20 s clip; looks convincing overall, grip not realistic |
| **Folder** | [`runs/H01-box-carry/`](../../runs/H01-box-carry/) |
| **Main video** | [`runs/H01-box-carry/videos/grid.mp4`](../../runs/H01-box-carry/videos/grid.mp4) |

## 1. Why this experiment

In the walking experiments the person only had to move themselves. Handling an object adds three new difficulties at once:

- **Contact:** hands and box have to meet exactly, stay together for many seconds and part again, on a body whose hands the agent had never used.
- **Weight:** nothing in the setup makes the box heavy. The person must behave as if it were, in how they bend, lift, stand and walk.
- **A sequence of different actions:** walking, bending, lifting, carrying, lowering and standing up have to flow into each other in one clip.

The question is how good and how fast a fully agentic approach is on such a task: no recordings of real motion, no physics engine, only what the agent knows and the code it writes.

## 2. The task

The person starts standing at the origin. A box stands on the floor 3 m ahead. A marked spot on the floor lies 3 m to the side of the box and 1 m further on, and the box has to end up there, turned by 90°.

| | |
|---|---|
| **Box** | 40 cm wide, 30 cm high, 30 cm deep, 10 kg |
| **Clip** | 20 s (600 frames at 30 frames per second) |
| **Start** | standing at (0, 0), facing the box |
| **End** | the box on the marked spot, hands off it, the person standing upright |

The agent was told what the person has to do, what the box weighs and what viewers will look for. It was **not** told how to lift: nothing in the prompt mentions bending the knees, keeping the box close or slowing down. It was told that its program would be tried afterwards on a layout it had not seen.

The full prompt is in [`runs/H01-box-carry/TASK.md`](../../runs/H01-box-carry/TASK.md). What is different from the walking experiments is explained on [How an experiment works](../01-setup.md).

## 3. What the agent did

**The session.** Working time is counted without the break caused by the usage limit:

| Working time | What happened |
|---|---|
| 0–6 min | Read the task, the manual and E04's code and notes. Built a dummy clip to see how the measuring tool reports results. |
| 6–13 min | Planned the work and copied the walking library into its folder. |
| 13–17 min | Wrote the first version of the whole new `manipulation/` library (1,300 lines in its final form) and `make_motion.py` in one go. |
| **17 min** | **First complete motion: 32 of 38 targets.** The hands were 27 mm inside the box and slid 12.5 cm over it. |
| 17–24 min | First preview and fixes: where the hands sit, a neck glitch of 989 °/s when looking straight down. |
| **24 min** | **First motion meeting all 38 targets**, at a cost of about $4–5. |
| 24–27 min | Looked at the carry and the set-down, and wrote its own test layouts. |
| 27–66 min | Worked through its test layouts and found bugs that the main task could not show (see below). Reworked the hand shape. **Interrupted** by the usage limit at 15:28. |
| 66–99 min | Resumed at 21:17. First checked that the regenerated motion was bit-identical to the saved one. Smoothed the box's acceleration (from 4.4 to 3.4 m/s²), found and fixed a hidden problem in the lowering, and wrote its notes. |

**What the person does** (from the agent's plan):

| Time | What happens |
|---|---|
| 0–0.75 s | stands still |
| 0.75–4.25 s | walks 2.6 m to the box, looks down at it during the last steps, and stops with the feet wide apart and the left foot 5 cm ahead |
| 4.5–5.75 s | bends down: the trunk leads, the hips go back, the fingers open; the palms reach the box at 5.64 s |
| 5.75–6.43 s | takes hold and braces: the hips start to rise and the arms straighten while the box stays on the floor |
| 6.43–7.8 s | lifts: the box comes off the floor gently and rises with the legs, and the trunk straightens and ends up leaning back |
| 7.8–8.2 s | the legs give a little under the load, then push back up |
| 8.2–13 s | carries the box along a curve, with shorter and slower steps |
| 13.3–15.1 s | lowers: the box goes out and down with the trunk, and the last 4 cm take 0.7 s |
| 15.1–15.7 s | holds the box as it stands on the floor, the fingers relax, the hands move away |
| 15.8–17.05 s | stands up, with the arms passing outside the thighs |
| 17.2–19 s | takes two small steps back out of the wide stance |
| 19–20 s | stands still |

**How the program works**, in plain words (the agent's full account is in [`NOTES.md`](../../runs/H01-box-carry/NOTES.md)). The order of work is: decide what happens when, compute the legs and pelvis, compute the box, fit the arms to the box, then correct the balance and repeat.

1. **What happens when.** The program decides which side of the box to approach. There are four sides to walk up to and two ways to stand at the target, and it prices all eight combinations by walking time and how awkward the grip is. It then plans the two walking routes and fits the timing to the clip. Lifting and lowering have minimum durations, because a rushed lift looks as if the box were light. The durations also depend on the box's weight.
2. **Legs and pelvis.** The footstep and balance method from E03 is unchanged. New is a *posture program*: smooth, overlapping moves for pelvis height, pelvis tilt and chest tilt, so that the body moves in one flowing movement and not one joint after another.
3. **The box.** It stands still until the lift and ends exactly on the target. In between it follows the body with some smoothing, so it does not copy every small bounce. It takes 75 % of the up-and-down of the pelvis and rolls by about 1° with the steps, as a load in soft arms would.
4. **Arms and hands.** From the moment the hands touch the box, they are attached to it by [inverse kinematics](../../../walking/report/glossary.md), so they cannot slide. The fingers have three computed shapes: relaxed, open, and lying on the flat face of the box.
5. **Balance.** The agent gave the skeleton a mass for each body part and computes the centre of mass of body and box together. The pelvis is shifted so that this point stays over the feet when standing. While walking, only 40 % of that shift is applied: applying all of it put the leading foot out of reach and made the pelvis dip suddenly.

**Bugs found only by testing other layouts.** These are the reason for most of the time after minute 27:

- **Box spinning:** the box's rotation could differ from the body's by a full turn, so it spun round while being lifted.
- **Missing the box:** a small heading error skipped the turn but kept the wrong direction, leaving the person 7 cm off-centre. The main task has exactly zero error, so it could not show this.
- **Routes that never arrived:** one route kept turning on the spot and never walked, and a correction then threw the box around at 32 m/s.
- **A hidden problem in the lowering:** all targets were met while a correction was silently bending the box's path by 19 cm. The agent only noticed this when limiting the correction made the numbers worse. This is a good reminder that passing all targets does not prove the method underneath is sound.

## 4. Results

### Videos and images

- **Main video:** [`videos/grid.mp4`](../../runs/H01-box-carry/videos/grid.mp4), all eight cameras at once
- **Single views:** `front`, `back`, `left`, `right`, `top`, `overview`, `hands_left`, `hands_right` (`.mp4`, in the same folder, kept locally)
- **Close-ups of each phase:** [bending and taking hold](../../runs/H01-box-carry/videos/contact_sheet_grip.png), [lifting](../../runs/H01-box-carry/videos/contact_sheet_lift.png), [carrying](../../runs/H01-box-carry/videos/contact_sheet_carry.png), [setting down](../../runs/H01-box-carry/videos/contact_sheet_setdown.png), [standing up](../../runs/H01-box-carry/videos/contact_sheet_stand.png)
- **Whole scene:** [`overview_sheet.png`](../../runs/H01-box-carry/videos/overview_sheet.png)
- **Unseen task:** [`unseen/videos/grid.mp4`](../../runs/H01-box-carry/unseen/videos/grid.mp4), [whole scene](../../runs/H01-box-carry/unseen/videos/overview_sheet.png), [turning with the box](../../runs/H01-box-carry/unseen/videos/contact_sheet_turn.png)

The lift, from 6.3 to 8.3 s:

![The lift, seen from six cameras at eight moments](../../runs/H01-box-carry/videos/contact_sheet_lift.png)

### Measurements

All 38 targets are met on the task, and all 38 on the unseen task. We measured both ourselves; the numbers do not come from the agent's notes. The meaning of each measurement is explained on [How results are measured](../02-measurements.md).

**The unseen task.** After the session we ran the agent's finished program, unchanged, on [`tasks/box-carry-variant.json`](../../tasks/box-carry-variant.json), which it never saw. The box is smaller (36 × 26 × 34 cm) and lighter (8 kg), and it is turned by 30°. The person starts in a different place and walks in a different direction, and the clip has 660 frames. The target lies about 100° away from the walking direction, so the person has to turn sharply with the box in their hands, which the main task does not require.

| | Measurement | H01 task | Unseen task | Target |
|---|---|---|---|---|
| | **Feet and path** | | | |
| ✅ | Deepest sinking into the floor | 6.84 mm | 8.09 mm | ≤ 10 mm |
| ✅ | Frames sinking more than 1 cm | 0 | 0 | 0 |
| ✅ | Frames with nothing on the floor | 0 | 0 | 0 |
| ✅ | Typical speed of floor-touching skin | 0.12 cm/s | 0.12 cm/s | ≤ 1 cm/s |
| ✅ | Speed of floor-touching skin, 95th percentile | 1.03 cm/s | 0.78 cm/s | ≤ 3 cm/s |
| | Distance travelled by the pelvis | 6.96 m | 7.35 m | |
| ✅ | Start position error | 0.64 cm | 0.73 cm | ≤ 15 cm |
| ✅ | Start heading error | 0° | 0° | ≤ 15° |
| ✅ | Pelvis speed while standing at the start | 4.11 cm/s | 5.24 cm/s | ≤ 10 cm/s |
| ✅ | Pelvis speed while standing at the end | 0.61 cm/s | 0.43 cm/s | ≤ 10 cm/s |
| ✅ | Fastest joint rotation | 604 °/s | 760 °/s | ≤ 800 °/s |
| ✅ | Frames with a pop | 0 | 0 | 0 |
| | **Grip** | | | |
| ✅ | The box starts where the task says | 0.03 mm | 0.03 mm | ≤ 5 mm |
| ✅ | Hands on the box before it moves | 1.0 s | 0.9 s | ≥ 0.15 s |
| ✅ | Frames the box moves without both hands on it | 0 | 0 | 0 |
| ✅ | Largest gap between a hand and the box while carrying | 0 mm | 0 mm | ≤ 10 mm |
| ✅ | Deepest hand skin inside the box | 8.41 mm | 8.53 mm | ≤ 10 mm |
| ✅ | Fewest hand skin points touching the box | 378 | 380 | ≥ 40 |
| ✅ | Hands sliding over the box while carrying | 0.61 cm | 0.59 cm | ≤ 2 cm |
| ✅ | How opposite the two hands are | 147.9° | 148.6° | ≥ 120° |
| | **The box in the air** | | | |
| ✅ | Highest the bottom of the box gets | 80.6 cm | 82.4 cm | ≥ 20 cm |
| ✅ | Frames the box slides along the floor | 0 | 0 | 0 |
| ✅ | Deepest the box goes into the floor | 0 mm | 0 mm | ≤ 3 mm |
| ✅ | Largest tilt of the box while carrying | 2.82° | 2.70° | ≤ 15° |
| ✅ | Fastest the box moves | 1.14 m/s | 1.21 m/s | ≤ 2 m/s |
| ✅ | Strongest acceleration of the box | 3.36 m/s² | 3.67 m/s² | ≤ 5 m/s² |
| | **Putting it down** | | | |
| ✅ | Distance from the marked spot | 0 cm | 0 cm | ≤ 10 cm |
| ✅ | Final rotation error of the box | 0° | 0° | ≤ 15° |
| ✅ | The box stands on the floor at the end | 0.03 mm | 0.03 mm | ≤ 3 mm |
| ✅ | Final tilt of the box | 0° | 0° | ≤ 1° |
| ✅ | Speed at touchdown | 0.10 m/s | 0.09 m/s | ≤ 0.15 m/s |
| ✅ | Hands stay on the box after it lands | 0.73 s | 0.70 s | ≥ 0.1 s |
| ✅ | Hands off the box at the end | 57.1 cm | 49.8 cm | ≥ 5 cm |
| ✅ | Standing up at the end | 99.8 % | 99.7 % | ≥ 96 % |
| | **Body and balance** | | | |
| ✅ | Deepest body skin (not hands) inside the box | 7.45 mm | 7.96 mm | ≤ 15 mm |
| ✅ | Deepest forearm or hand skin inside the trunk or legs | 2.27 mm | 0 mm | ≤ 15 mm |
| ✅ | Knees and elbows bending the wrong way | 0° | 0° | ≤ 5° |
| ✅ | Largest wrist rotation | 41.8° | 42.6° | ≤ 85° |
| ✅ | Frames off balance with both feet down | 0 | 0 | 0 |
| | Worst balance margin (negative means always inside the feet) | −0.9 cm | −0.17 cm | |

**How the weight shows** (no targets; these describe the behaviour):

| Measurement | H01 task | Unseen task |
|---|---|---|
| Lowest pelvis height (standing is 0.95 m) | 0.45 m | 0.42 m |
| Trunk lean at the grip | 59.6° | 59.7° |
| Walking speed without the box | 0.87 m/s | 0.91 m/s |
| Walking speed with the box | 0.79 m/s | 0.95 m/s |
| Trunk lean without the box | −1.2° | −1.0° |
| Trunk lean with the box (negative means leaning back) | −4.1° | −3.7° |
| Box centre in front of the chest while carrying | 28.8 cm | 30.7 cm |
| Height of the box centre while carrying | 0.95 m | 0.94 m |

**How to read these numbers:**

- **The unseen task is the most important result.** The program was not fitted to one layout. It found the box, chose a side, made a sharp turn with the box and hit the target exactly. This is one test only, though, and its box is similar to the original.
- **Some margins are small.** Hand skin goes 8.4 mm into the box against a limit of 10 mm, and the fastest joint on the unseen task reaches 760 °/s against a limit of 800 °/s.
- **Leaning back under the load appears in both tasks,** by about 3° more than when walking without the box. It emerged from the balance calculation.
- **Slowing down under load is not reliable.** The person slows by 9 % on the main task, but on the unseen task walks slightly *faster* with the box than without it. Walking speed is set by how much time the clip leaves, not by the weight.

**Other boxes and layouts.** The agent also wrote 12 test tasks of its own. We ran them again with the final program and our measuring tool:

| Task | Box (width × height × depth) | What it tests | Failed targets |
|---|---|---|---|
| `close-target` | 40 × 30 × 30 cm, 10 kg | target 1.2 m away, turned 30° | none |
| `tall-box` | 35 × 50 × 30 cm, 9 kg | tall box, target to the left | none |
| `target-behind` | 40 × 30 × 30 cm, 14 kg | target behind the person: turn with the box | none |
| `target-right` | 30 × 40 × 30 cm, 8 kg | box turned 90°, target to the side | none |
| `tiny-move` | 40 × 30 × 30 cm, 10 kg | target 22 cm away | none |
| `typical-a` | 50 × 35 × 30 cm, 12 kg | box off to the side and turned, target behind on the left | none |
| `typical-b` | 35 × 30 × 35 cm, 7 kg | start not facing the box exactly | none |
| `typical-c` | 45 × 25 × 35 cm, 8 kg | another start, with heading 90° | none |
| `far-target` | 45 × 30 × 35 cm, 12 kg | target 5.6 m from the box | body in box 15.6 mm (limit 15) |
| `left-rotated` | 50 × 25 × 35 cm, 6 kg | held along its 50 cm side, so it is deep | body in box 15.8 mm (limit 15) |
| `small-light` | 30 × 20 × 25 cm, 4 kg | small, low box | arm in leg 23.2 mm (limit 15) |
| `wide-heavy` | 60 × 30 × 40 cm, 15 kg | deliberately extreme | hand in box 18.2 mm, hand sliding 3.1 cm, box acceleration 5.4 m/s², body in box 41.1 mm |

So 8 of the 12 meet every target. These tasks are not an independent test, because the agent used them to tune its code, but they show where the limits are: deep boxes, small low boxes, and very wide, heavy ones.

**Earlier tasks still work.** The agent widened the arm swing by 4° to stop the hands going into the thighs, which also changes plain walking, and it did not measure the effect. We did: with the final code, the straight walk (11/11), the curved path (11/11), the turns (15/15) and the narrow passage (15/15) all still meet every target.

**Speed.** With the program finished, the 20-second clip takes 3.8 s to compute, or about 7 s including starting Python. The unseen 22-second clip takes 5 s, or about 8.5 s in total. Repeated runs give identical files.

### What we see in the videos

This assessment comes from still images, not from watching the videos: 40 moments of the clip and 8 of the unseen task, from six cameras each. Stills cannot show timing and flow, so people still need to watch [`grid.mp4`](../../runs/H01-box-carry/videos/grid.mp4).

**What looks natural:**

- **The whole sequence reads clearly.** At every moment it is obvious what the person is doing. The stills show no break between walking, bending, lifting, carrying and setting down, and the measurements find no pops.
- **Bending down (4.6–5.6 s):** the hips go back while the trunk tips forward and the head follows the box, as in a real person.
- **The lift (6.4–7.8 s):** the box leaves the floor gently, the legs do the work and the trunk rises with the load. The small give in the legs at about 8 s suggests weight.
- **Carrying (8.2–13 s):** the box stays close to the belly and level (it tilts by less than 3°), and the slight lean back is visible from the side.
- **Setting down (13.3–15.1 s):** this is the best phase. The box slows clearly near the floor, lands squarely inside the teal outline, and the hands stay on it for a moment before letting go. It reads as careful.
- **Turning with the box** (unseen task, 10–13.5 s): the grip stays steady and the feet step round the turn plausibly.

**What does not look right:**

- **The grip (5.6–15.4 s) is the main flaw.** The hands lie flat on the two sides of the box, low down, with the fingers spread and straight, and they stay that way for 10 seconds. The box looks pinned between two open palms and not held. A person would curl their fingers under the bottom edge or hold it diagonally by the corners. See the hand cameras in the [carry sheet](../../runs/H01-box-carry/videos/contact_sheet_carry.png).
- **The fold at the bottom (5.6–6.4 s and 14.4–15.8 s) is deep.** The person both squats (pelvis at 0.45 m) and tips forward (60°), with the head low and the neck bent sharply. It is plausible, but more folded than a real person would need to be for a 30 cm box. It follows from the grip: the palms have to reach a point 14 cm above the floor.
- **Arms during the carry:** in the stills they keep almost the same shape from step to step. Whether this looks stiff needs checking in the video.
- **Letting go (16–16.5 s):** the arms spread out wide to pass outside the thighs, which looks a little theatrical. The agent did not look at this phase again after its last changes.
- **Effort:** apart from the small give after the lift, nothing shows strain: no change of grip while walking, no pause before the lift to prepare.
- **The walk is slower than normal even before the box:** 0.87 m/s against about 1.2 m/s in the walking experiments, so the difference between walking with and without the box is hardly visible.

## 5. Problems and limitations

- **The grip is not physically convincing.** Held like this, the box stays up only through friction. With a friction of about 0.5, each hand would have to press with about 100 N (the force needed to hold up a 10 kg weight) for about ten seconds. The hands also sit about 4 cm behind the centre of the box, so a real box would tend to tip forward out of them.
- **Our own measurements contributed to this.** The agent chose side faces partly because `evaluate.py` checks that the hands are on opposite sides. No measurement rewards support from below, so nothing pushed it towards a better grip. A motion can pass all 38 targets and still have this flaw.
- **There is no physics.** The agent writes down the position of the box. The measurements check that it behaves plausibly; no simulation proves it.
- **The agent developed against the measuring tool.** It ran it 23 times, so the 38/38 on the main task says less than the 38/38 on the unseen task, and that was only one layout with a similar box.
- **Weight is mostly in the timing and posture.** Lifting and lowering are slower for heavier boxes, but nothing else in the program depends on weight in a physically meaningful way.
- **The box cannot be turned in the hands.** The person must walk to the matching direction, which makes some layouts slow: a 1.2 m move takes about 6.5 s.
- **Obstacles are ignored.** Routes only avoid the box itself.
- **Fitted to this body.** Belly depth, distance from the box and arm reach are measured values for this one body shape.
- **Time and cost of the interruption.** The second part cost $7.34 for 33 minutes, including reading the whole conversation in again.

## 6. Conclusion and next step

**How good?** Clearly better than we expected for a first attempt at contact. A full pick-up-and-carry sequence works from a task file, the numbers are clean, and the program handled a layout it had never seen. Without being told, the agent reproduced the main features of real lifting: bent knees, a trunk that leads, the load close to the body and a lean back against it. What is missing is the fine detail of the hands, and that is exactly the detail a viewer looks at in an object-handling clip.

**How fast?**

| Step | Time | Cost |
|---|---|---|
| First motion meeting all targets on this one task | 24 min | about $4–5 |
| Finished, general program with notes | 99 min | $16.74 |
| Running the finished program on a new layout | about 8 s | no agent needed |

The pattern from the walking series holds: building a new skill takes the agent about an hour or more, and using it afterwards takes seconds. H01 took the longest of all experiments so far, but cost less than E03 or E04, even though it had to build far more new code. That may be because it wrote most of the library in one go at the start.

**Next step.** The next experiment is [H02: juggling](H02-juggling.md), a much harder test of the hands, with a measurement for support from below. Still open from this experiment is a real grip on the box: a measurement that rewards support from below, fingers curled under the box, and a person who tilts the box slightly to get them there, as people do. Getting the hands right matters for every later task with objects. A different object (a pan or a cup held in one hand) would then show how much of `manipulation/` carries over. It would also help if people watched `grid.mp4`, to confirm or correct the judgement above.

## Files in the experiment folder

| File | Content |
|---|---|
| [`TASK.md`](../../runs/H01-box-carry/TASK.md), [`CLAUDE.md`](../../runs/H01-box-carry/CLAUDE.md), [`SMPLX_INTERFACE.md`](../../runs/H01-box-carry/SMPLX_INTERFACE.md) | exactly what the agent was told |
| [`make_motion.py`](../../runs/H01-box-carry/make_motion.py), [`manipulation/`](../../runs/H01-box-carry/manipulation/), [`locomotion/`](../../runs/H01-box-carry/locomotion/) | the agent's program: the new library for objects, and the walking library with a few additions |
| [`tools/`](../../runs/H01-box-carry/tools/) | the agent's own checking tools |
| [`test_tasks/`](../../runs/H01-box-carry/test_tasks/) | its 12 extra test tasks |
| [`NOTES.md`](../../runs/H01-box-carry/NOTES.md) | the agent's own account |
| `motion.npz` | the motion: SMPL-X parameters and box position for each frame |
| [`motion.metrics.json`](../../runs/H01-box-carry/motion.metrics.json), [`motion.timeline.csv`](../../runs/H01-box-carry/motion.timeline.csv) | the measurements, and the frame-by-frame contact and balance numbers |
| `unseen/` | the unseen task: task file, motion, measurements and videos, made by us after the session |
| `previous/E04-narrow-passage/` | the starting code it was given |
| `transcript.jsonl`, [`run_summary.json`](../../runs/H01-box-carry/run_summary.json), [`run.json`](../../runs/H01-box-carry/run.json) | the full session log (both parts), its key facts, and the record of the interruption |
| `videos/` | rendered videos and images, including the close-ups of each phase, `contact_sheet_*.png` |
