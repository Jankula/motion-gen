# Juggle three balls, also on one foot: notes

## Summary

`make_motion.py` turns a task file into a clip of a person juggling three balls: they stand ready, start juggling, shift their weight, lift one foot, keep juggling on the other foot, catch all the balls, and only then put the foot down and stand still. Nothing is recorded or copied. Everything is computed from the task.

For `task.json`, all 48 targets of `evaluate.py` are met. The 11 extra tasks I wrote to vary everything the task may vary (ball size and weight, position, heading, standing foot, clip length, frame rate, minimum numbers) also meet all 48.

Meeting the targets does not prove that it looks real. I judged the look from still image sheets only, never from moving video, and the body's reactions are scripted rather than physically simulated. See [Known weaknesses](#known-weaknesses).

## What is here

| file | what it is |
|---|---|
| `make_motion.py` | `python make_motion.py <task.json> <out.npz>`. A task with balls goes to `juggling/`, a task with an object to `manipulation/`, a walking task to `locomotion/`. |
| `juggling/` | the new library for this task |
| `locomotion/`, `manipulation/` | the earlier libraries, byte-for-byte the same as in `previous/H01-box-carry/` |
| `motion.npz` | the motion for `task.json`. `check_format.py` prints `OK: 600 frames at 30 fps`. |
| `test_tasks/` | 11 juggling tasks (written by `tools/make_test_tasks.py`) and one walking task |
| `tools/` | checking tools, not needed to generate motion (listed at the end) |

**Speed.** `task.json` takes about 1 s of computing for a 20 s clip. Starting Python adds a few seconds: the whole command took 4 to 7 s in the test runs, with four running at once. **Determinism.** Two separate runs gave identical files.

## Terms used below

- **Joint rotation, pose**: the body is a skeleton; a pose is the rotation of every joint for one frame.
- **Forward kinematics (FK)** computes where the joints end up from their rotations. **Inverse kinematics (IK)** is the reverse: it finds rotations that put a hand or foot at a wanted place.
- **Reach**: distance from shoulder to wrist as a share of the arm's length. At 1.0 the arm is straight and cannot go further.
- **Centre of mass (COM)**: the average position of the body's mass. A person is balanced while it is above the area of the feet.
- **Cascade**: the classic three-ball pattern. The hands throw in turns and every ball crosses to the other hand.
- **Beat**: the time between two throws. **Dwell**: the time a ball stays in a hand. **Flight**: the time it spends in the air.
- **Seat**: the place of a ball's centre relative to the hand.
- **Free fall**: movement under gravity alone. Height over time is an exact parabola.
- **Jerk**: how fast acceleration changes. A **minimum-jerk path** is the smoothest path through given points. Smooth human arm movements are close to such paths.
- **Spline, knot**: a smooth curve made of pieces; a knot is a point where two pieces join.

## How it works

The order of work is: decide what happens when, plan the balls, fit the hands to the balls, then build the body around the hands.

### 1. What happens when (`juggling/schedule.py`)

A cascade follows a simple law: every ball is thrown again three beats after its last throw, so flight + dwell = 3 beats. I use a beat of 0.33 s, a dwell of 0.42 s and a flight of 0.57 s. Balls rise to about 1.58 m, roughly eye height.

The clip is fitted to the task. First come the minimum numbers plus a margin, then the spare time is shared out between the two-foot part (38 %) and the one-foot part. If a clip is too short, the rest at both ends is shortened first, then the beat gets faster, down to 0.29 s. A warning is printed if it still does not fit. Heavier balls are thrown a little slower.

For `task.json`:

| time | what happens |
|---|---|
| 0 – 1.0 s | stands with two balls in the right hand and one in the left, looking at the hands |
| 1.0 s | first throw, from the right hand |
| 5.06 – 6.56 s | the weight moves onto the left foot, while juggling |
| 6.81 s | the right heel starts to rise |
| 7.13 s | the toes leave the floor |
| 7.75 s | the foot is fully up |
| 16.04 s | last catch: 45 throws in all, 20 before the lift and 25 on one foot |
| 16.59 s | the foot starts down |
| 17.21 – 17.43 s | toes touch, then the foot goes flat |
| 18.31 s | the weight is back between the feet |
| to 20 s | stands still, holding the balls |

Throws are not perfectly regular. The tempo drifts slowly, and throw times, flight times and the points of release and catch vary by small random amounts, a little more on one foot. The random numbers come from fixed seeds, so the result is repeatable.

### 2. The balls come first (`schedule.Throw`)

Every flight is an exact free fall between a planned release point and a planned catch point. From those points and the flight time, the release velocity follows. The hands are made to fit the balls, never the reverse, so a ball in the air cannot steer or float. The evaluation measures 0 mm difference from a free fall.

### 3. Hands fitted to the balls (`juggling/pattern.py`)

- **Release.** The hand has the ball's position and velocity, and its acceleration is exactly −g. That is the physics of letting go: a ball leaves a hand at the moment the hand slows down faster than gravity slows the ball.
- **Catch.** The hand comes up under the ball and is already moving down, at 55 % of the ball's speed. The rest of the speed is taken up in the first few hundredths of a second, while the ball sinks 1.6 cm from the fingers into the palm.
- **In between.** With a ball, the hand scoops down and inwards to the bottom of a dip, then pushes up fast. Empty, it follows through upwards and swings out under the next ball.
- **Smoothness.** Only what the physics demands is fixed: the states at release and catch, and the heights of the dip and the top. All the rest is left to one minimum-jerk solve (`curves.min_jerk`).
- **Orientation.** The palm is up, tilted a little towards the middle. It tips forward during the throw, as a wrist flick does.

### 4. Fingers (`juggling/fingers.py`)

Finger shapes are solved for the ball size in the task, not stored:

- Each finger closes joint by joint until the skin on that bone touches the ball, then opens again until the fingertip is below the ball's equator. A juggler's hand is an open cup, not a fist.
- The thumb lies along the side of the ball. Its bone line stays one flesh thickness outside the ball.
- Two balls lie one behind the other. The front ball is laid down until it rests on the rear ball and on the fingers, so it neither floats nor sinks, whatever its size.

The fingers open at each release, stretch briefly and close at each catch. They move in a small wave, from index to little finger.

### 5. The body (`juggling/rig.py`, `juggling/stance.py`)

- **Feet.** The standing foot never moves. The free foot peels off heel first, turning about the ball of the foot, and comes down toes first, 1–2 cm from where it left.
- **Balance.** The wanted path of the COM is written down: between the feet, over the standing foot well before the heel rises, a slow sway, and back after the foot is down. The pelvis is then shifted until the COM of the whole posed body, with the balls it is holding, follows that path. The segment mass model comes from `manipulation/massmodel.py`.
- **Pattern.** It follows 90 % of the sideways weight shift, so the arms keep the same geometry on one foot.
- **Trunk and legs.** The knees stay soft and give a little with each throw. The chest turns and tips against the throwing arm, and the shoulders rise with the hands. The pelvis tips and turns with the lifted leg. Slow small movements run through everything, including the lifted foot.
- **Arms.** Analytic IK to the hand path. 68 % of the forearm's twist goes to the elbow joint and the rest to the wrist.
- **Head and eyes.** The head follows the top of the arcs, the eyes follow more closely. Looking down, the head stops at 24° and the eyes do the rest.

## What changed compared with the starting point (`previous/H01-box-carry`)

- **New:** the `juggling/` package, `test_tasks/`, `tools/`, and the choice of library in `make_motion.py`.
- **Reused as they are:** rotation helpers, FK, leg IK (`Leg.ik`), arm IK (`Arm.solve`), finger kinematics and the mass model.
- **Not reused:** the walking and footstep planning, because the feet do not walk here. The person stands in one place, so the feet and pelvis are simpler and written new.
- **Unchanged:** `locomotion/` and `manipulation/` were compared with the originals and are identical, so box and walking tasks behave as before.

## Main choices and why

- **Balls first, body last.** Free fall is the one thing a viewer cannot be fooled about, so it is exact by construction and everything else gives way to it.
- **The hand is planned on what the arm can reach.** The arm is short: the shoulder is 0.51 m from the wrist at full stretch. The hands move between about 1.0 and 1.3 m, and the forearm is near horizontal at the lowest point, which also keeps the elbow bent. Planning the hands lower made the arm lock straight, and the hand then lost the ball.
- **The hand does not match the ball's full speed at a catch.** Matching it fully would need a very deep dip. 55 % plus the sinking into the palm gives a catch that visibly gives way, with a speed jump of 1.13 m/s against a limit of 2.5.
- **`evaluate.py` used as a measuring tool for the hand.** I have only about 24 skin points per hand, but the evaluation measures on the real mesh, frame by frame. So I made calibration clips in which each frame tries another seat and finger shape, in real poses, and read the depth back (`tools/seat_by_radius.py`). This gave the seat rules in `params.py` for ball radii from 25 to 45 mm. Real poses matter, because skin also deforms with pose.
- **Ambiguities, and what I decided:**
  - *Which hand starts:* the right hand holds two balls and throws first, whichever foot the person stands on.
  - *Which hand ends with two balls:* this follows from the number of throws. In `task.json` it is the left.
  - *"Balls in the hands" at the end:* the hands stay in front of the body, palms up, as at the start. With hanging arms the balls would not lie on the hands.
  - *Spare time:* it goes into more juggling, not longer standing.
  - *Body mass:* 76 kg from the task. The balls count towards balance only while held.
  - *Starting point file:* `TASK.md` mentions `previous/H01-box-carry/task.json`, which does not exist. I tested the old box tasks with the files in `previous/H01-box-carry/test_tasks/`.
  - *Number of balls:* the code is built for three. Another number stops with a clear error.
  - Jaw left at zero.

## How I checked the result

### Final `evaluate.py` table (`task.json`, `motion.npz`)

48 of 48 targets met.

| | Measurement | Value | Target |
|---|---|---|---|
| ✅ | Deepest sinking into the floor | 2.62 mm | ≤ 10 mm |
| ✅ | Frames sinking more than 1 cm | 0 frames | 0 |
| ✅ | Frames with nothing on the floor | 0 frames | 0 |
| ✅ | Typical speed of floor-touching skin | 0.11 cm/s | ≤ 1 cm/s |
| ✅ | Speed of floor-touching skin, 95th percentile | 0.42 cm/s | ≤ 3 cm/s |
|  | Distance travelled by the pelvis | 0.6 m |  |
|  | Average speed | 0.03 m/s |  |
| ✅ | Start position error | 0 cm | ≤ 15 cm |
| ✅ | Start heading error | 0.02 ° | ≤ 15° |
| ✅ | Pelvis speed while standing at the start | 0.61 cm/s | ≤ 10 cm/s |
| ✅ | Pelvis speed while standing at the end | 0.29 cm/s | ≤ 10 cm/s |
| ✅ | Fastest joint rotation | 673.05 °/s | ≤ 800 °/s |
| ✅ | Frames with a pop | 0 frames | 0 |
| ✅ | Frames at the start without all balls in the hands | 0 frames | 0 |
| ✅ | Frames at the end without all balls in the hands | 0 frames | 0 |
| ✅ | Frames with more than two balls in one hand | 0 frames | 0 |
| ✅ | Narrowest contact between a hand and a held ball | 6.38 cm | ≥ 5 cm |
| ✅ | Ball-frames in which a held ball has no support from below | 0 frames | 0 |
| ✅ | Deepest hand skin inside a ball | 5.63 mm | ≤ 8 mm |
| ✅ | Largest gravity error of a flight | 0 % | ≤ 3 % |
| ✅ | Largest difference between a flight and a free fall | 0 mm | ≤ 3 mm |
| ✅ | Flights too short to be a throw | 0 flights | 0 |
| ✅ | Balls that are never caught | 0 flights | 0 |
| ✅ | Lowest throw | 35.84 cm | ≥ 20 cm |
| ✅ | Highest point of any ball | 1.63 m | ≤ 2.1 m |
| ✅ | Fastest ball | 2.96 m/s | ≤ 6 m/s |
| ✅ | Deepest two balls go into each other | 0 mm | ≤ 2 mm |
| ✅ | Deepest body skin (not hands) inside a ball | 0 mm | ≤ 8 mm |
| ✅ | Throws before the foot lifts | 20 throws | ≥ 9 |
| ✅ | Throws on one foot | 25 throws | ≥ 12 |
| ✅ | Throws of the least thrown ball | 15 throws | ≥ 7 |
| ✅ | Throws that come from the other hand than the throw before | 100 % | ≥ 95 % |
| ✅ | Throws caught by the other hand | 100 % | ≥ 95 % |
| ✅ | Longest time between two throws | 0.37 s | ≤ 0.6 s |
| ✅ | Largest jump in a ball's speed at the release | 0.8 m/s | ≤ 1.5 m/s |
| ✅ | Largest jump in a ball's speed at the catch | 1.13 m/s | ≤ 2.5 m/s |
| ✅ | Shortest time a ball stays in a hand | 0.43 s | ≥ 0.12 s |
| ✅ | Times the right foot leaves the floor | 1 times | 1 |
| ✅ | Frames the left (standing) foot is off the floor | 0 frames | 0 |
| ✅ | Time on one foot | 9.73 s | ≥ 5 s |
| ✅ | Typical height of the lifted foot | 13.24 cm | ≥ 10 cm |
| ✅ | Time from the last catch to the foot coming down | 1.03 s | ≥ 0.2 s |
| ✅ | All balls in the hands when the foot comes down | yes | yes |
| ✅ | Frames off balance on one foot | 0 frames | 0 |
|  | Worst balance margin on one foot | -2.3 cm |  |
| ✅ | Frames off balance on two feet | 0 frames | 0 |
| ✅ | Largest distance of the pelvis from where it starts | 15.45 cm | ≤ 20 cm |
| ✅ | Standing up at the end | 99.14 % of height | ≥ 96 % |
| ✅ | Deepest forearm or hand skin inside the trunk or legs | 0 mm | ≤ 15 mm |
| ✅ | Knees and elbows bending the wrong way | 0 ° | ≤ 5° |
| ✅ | Largest wrist rotation | 62.99 ° | ≤ 85° |
|  | Throws per second | 3.04 1/s |  |
|  | Typical time in the air | 0.57 s |  |
|  | Typical time in a hand | 0.5 s |  |
|  | Typical highest point of a throw | 1.58 m |  |
|  | Variation of the highest point | 1.98 cm |  |
|  | Variation of the time between throws | 19.58 ms |  |
|  | Sway of the centre of mass on one foot | 3.54 cm |  |

### Other juggling tasks (`tools/eval_all.py`)

All were generated and evaluated with the final code, and all meet 48 of 48.

| task | what it tests |
|---|---|
| `right-foot` | standing on the right foot |
| `moved-turned` | start at (1.5, −2), heading 90° |
| `right-foot-turned` | right foot, start at (−0.7, 0.9), heading −135° |
| `big-heavy` | balls of radius 45 mm, 300 g |
| `small-light` | balls of radius 25 mm, 60 g |
| `tennis` | radius 34 mm, 58 g, right foot, heading 30° |
| `short-clip` | 15 s |
| `very-short` | 12 s, minimums 6 / 8 throws, 3 s |
| `long-clip` | 30 s, minimums 15 / 20 throws, 10 s |
| `high-minimums` | 20 s, minimums 16 / 22 throws, 9 s |
| `other-fps` | 25 frames per second |

These tasks were written by me and used to tune the code, so they are not an independent test. Of them I only read the numbers; I looked at rendered images of `task.json` only.

### Earlier kinds of task

- **Box tasks.** I re-ran 4 of the 12 box tasks in `previous/H01-box-carry/test_tasks/`. `close-target` meets all 38 targets. `far-target`, `left-rotated` and `small-light` each miss one target, with exactly the values listed in the earlier notes (15.62 mm, 15.77 mm, 23.19 mm). Those are inherited weaknesses. The box code is unchanged.
- **Walking.** `test_tasks/walk.json` generates and passes the format check. I did not evaluate it further.

### Rendered previews

I used 8 of the 12 allowed. No change to the motion was made after the last five.

| window | what I saw | version |
|---|---|---|
| 3.0 – 3.7 s | it reads as juggling; locked knees, chest too still | early, later improved |
| 6.5 – 8.0 s | foot lift right, but a crouching stance and a pelvis too far out | early, repeated below |
| 15.2 – 17.6 s | right order of events, but the head dropped to the chest | early, repeated below |
| 0.55 – 1.65 s | two-ball hold and first throw | final settings |
| 4.16 – 4.40 s | a catch and a throw frame by frame | final settings |
| 15.7 – 18.7 s | last catches, foot down, standing still | final settings |
| 11.0 – 12.2 s | steady juggling on one foot | final settings |
| 6.6 – 7.9 s | foot lift | final settings |

### Bugs the checks found

These are worth knowing about, because the first one met every target on `task.json`:

- **A hand swinging across the body.** After its last catch, each hand swung 27 cm inwards and back out, between path points only 6 cm apart. The minimum-jerk solve carried the curve of the fast last swing into a long, slack path. On `task.json` no target failed. It only showed on other tasks, as a forearm in the trunk, and I first explained that wrongly, as a problem of the two-ball seat. Printing the path showed the real cause. `tools/diagnose.py` now checks that hands stay in their lane.
- **Arm out of reach.** The first plan needed reach up to 1.3. The hand could not follow, the ball parted from it, and the evaluation counted false short flights.
- **Planned bottom not the real bottom.** With free speed at the dip, the path overshot it by about 6 cm and nearly straightened the arm, which caused a fast elbow (828 °/s). The dip and top now have zero vertical speed.
- **A thumb through the ball.** A thumb fitted by its pad points went 2 cm into the ball, because the pad lies about 1.4 cm from the bone line.
- **Fingers over the top.** Fully wrapped fingers lifted the average contact above the ball's centre, so the ball counted as hanging from the hand. This led to the open cup.
- **Sizes other than 32.5 mm.** A seat tuned for one radius gave 12 mm of skin in a large ball, and a small ball floated with no contact.

## Known weaknesses

- **I never saw it move.** The previews are still sheets. Rhythm and fluency are judged from frames and numbers, so a viewer may notice things I could not.
- **No real physics.** Balance is placed, not simulated: the COM follows a written path, and nothing computes forces. The reactions of the chest and knees to the throws are scripted to look right, not caused by the arms. Balance margin on one foot is 2.3 cm at the worst moment.
- **Very tidy juggling.** Variation is small and random. There are no near-misses, recoveries or corrections after a poor throw, and the pattern shows almost no reaction to the foot lifting, which real jugglers would probably show a little.
- **The one-foot sway does not interact with the pattern.** The hands do not respond to the body's sway. The pattern follows the large weight shift, but its slow drift is independent of the sway.
- **The hold of two balls is simple.** A ball moving between seats slides along a planned path rather than rolling. The second ball of the final catch lands on the fingers in the same way as any other catch, which is probably easier than it should look.
- **Fingers blend between four solved shapes.** The ball does not roll along the fingers at release; it leaves from its seat.
- **Hand fit is measured for this one body.** The seat rules were measured on the left hand, in three poses for one ball and in one pose for two balls, for radii from 25 to 45 mm. Outside that range they are held at the end values and untested. Hand depth is 5.6 mm against a limit of 8 mm.
- **Eye positions are estimates.** The position of the eyes on the head is my own estimate, not data. I looked at the gaze only in the image sheets.
- **Very tight tasks.** The shortest clip tested is 12 s. If a clip cannot fit the minimum numbers even at the fastest beat, a warning is printed and the result will be poor.
- **Three balls only.**

## Extending the library

- **Another pattern:** `Plan._throws` decides who throws to whom and when. `pattern.py` only needs a sorted list of throw and catch events per hand, so other throw orders need few changes there.
- **Other objects in the hands:** `BallHand` gives seats and finger shapes. The rest asks it only for offsets and shapes.
- **Other standing actions:** `rig.py` works from the hand paths, a COM path and a free-foot program. Replacing `com_target` and `_foot_program` gives other balance tasks.
- **Parameters:** every number is in `juggling/params.py`, and `generate_juggling_motion(task, params={...})` overrides them.
- **Inspecting a run:** `generate_juggling_motion` returns the `Rig` under `motion["rig"]`, with the plan, hand paths and arm reach.
- **Watch reach:** keep `rig.reach` below about 0.97. Above that the elbow speed jumps and the hand starts to lose the ball.

Tools in `tools/`:

| tool | what it does |
|---|---|
| `eval_all.py` | generates and evaluates the test tasks into `test_out/` and lists missed targets; `--old` runs four earlier box tasks |
| `make_test_tasks.py` | writes the juggling tasks in `test_tasks/` |
| `diagnose.py` | timing, reach, hand paths and lanes, joint speeds and ranges, ball distances |
| `when.py` | when the worst moments of evaluated test tasks happen |
| `holds.py` | when hand skin goes into a ball, from `evaluate.py` output |
| `seat_by_radius.py` | calibration clips for the seats on the real mesh (`one` or `two` balls) |
| `compare.py` | checks whether two motion files are identical |
| `clean.py` | removes generated working files (`scratch/`, `test_out/`, Python caches) |
