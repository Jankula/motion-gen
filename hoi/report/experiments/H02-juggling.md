# H02: Juggling three balls, also on one foot

> **Summary.** A person stands in one place holding three balls, starts juggling, lifts one foot while juggling on without a break, catches all the balls while still on one foot, then puts the foot down and stands still. Starting from the code of H01, the agent built a new juggling library. Every ball flies in an exact free fall, 45 throws in a row, and the result meets **all 48 measurement targets**. On an **unseen task**, with bigger balls, the other foot and a longer clip, the finished program meets 47 of 48: one elbow moves 1 % too fast for an instant. The biggest gain over H01 is the hands: they now cup the balls, with fingers that open and close. The clear remaining weakness is that the juggling is too tidy, and all body reactions are scripted and not physically simulated. The session took 74 minutes and $11.33, less than H01 although the task is harder. The finished program makes a 20-second clip in about 2 seconds of computing.

| | |
|---|---|
| **Experiment ID** | `H02-juggling` (the same name is used for the folder and the videos) |
| **Date** | 2026-11-05 |
| **Task** | Juggle three balls on both feet, then on one foot, catch them all, put the foot down; 20 s ([`tasks/juggling.json`](../../tasks/juggling.json)) |
| **Agent** | Claude Code, model Claude Opus 5.5, headless |
| **Started from** | the code of [H01](H01-box-carry.md) |
| **Tools the agent had** | `evaluate.py` (used 21 times), `preview.py` (used 8 of 12 allowed) |
| **Session** | 74 min, 149 turns, $11.33, not interrupted |
| **Result** | 48/48 targets met, and 47/48 on the unseen task; about 2 s to compute the 20 s clip; hands much better than in H01; too tidy, not physically simulated |
| **Folder** | [`runs/H02-juggling/`](../../runs/H02-juggling/) |
| **Main video** | [`runs/H02-juggling/videos/grid.mp4`](../../runs/H02-juggling/videos/grid.mp4) |

## 1. Why this experiment

H01 showed that an agent can plan a whole sequence with an object, but also that its hands were the weak point: they pressed flat on the box and stayed there. Juggling attacks exactly that weakness, and it adds new difficulties:

- **Timing:** in H01 the hands touched the box twice, slowly. Here there are 40 or more throws and catches, and a hand that arrives 0.1 s late misses a ball moving at about 3 m/s.
- **Real physics in the air:** a ball in flight follows one exact curve. The hands, the balls and gravity all have to fit together.
- **Fast, precise arms:** the arms move all the time, much faster than in any earlier experiment, and the wrist and fingers matter.
- **Balance on one foot:** a person can only stand on one foot with the weight over that foot, and the weight has to get there before the foot leaves the floor.
- **Two tasks at once:** the arms must not notice when the legs change what they do.

## 2. The task

| | |
|---|---|
| **Balls** | three solid balls, 6.5 cm across, 120 g each. A ball fits in one hand, and a hand can hold two |
| **Clip** | 20 s (600 frames at 30 frames per second) |
| **Start** | standing at (0, 0), facing +Z, all three balls in the hands |
| **Standing foot** | left |
| **At least** | 9 throws on both feet, 12 throws on one foot, 5 s on one foot |
| **End** | all balls in the hands, standing still on both feet |

**The order matters.** The last ball is caught while the person is still on one foot, and only then does the foot come down.

The agent was told what the person has to do and what viewers will look for. It was **not** told how: nothing in the prompt says how high to throw, how long a ball stays in the hand, where the hands move, or how to shift the weight. It was told that the world's gravity is 9.81 m/s², and that its program would be tried on an unseen task.

The full prompt is in [`runs/H02-juggling/TASK.md`](../../runs/H02-juggling/TASK.md). The size and weight of the balls, the clip length, the left foot and the minimum numbers were our choices, because the original request left them open.

## 3. What the agent did

**The session.**

| Working time | What happened |
|---|---|
| 0–13 min | Read the task, the manual and H01's code and notes, and planned the work. |
| 13–17 min | Wrote the first version of the whole `juggling/` library (1,400 lines in its final form) in one go. |
| **18.5 min** | **First complete motion: 32 of 48 targets**, at a cost of about $2. |
| 18–22 min | Fixed the hand paths. The arm could not reach them at first, so the ball parted from the hand. **46 of 48.** |
| 23–31 min | The last two targets were about how a ball lies in a hand. The agent has only about 24 skin points per hand, so it built test clips in which every frame tries another ball position, and read the answer from `evaluate.py` (see below). |
| **32 min** | **First motion meeting all 48 targets**, at a cost of about $4. |
| 32–36 min | Looked at the foot lift and the ending, and corrected the stance and the head. |
| 36–62 min | Wrote 11 test tasks and made the program work on all of them. Found a bug that no target on the main task showed. |
| 62–74 min | Looked at the final motion in five previews, and wrote its notes. |

**What the person does** (from the agent's plan):

| Time | What happens |
|---|---|
| 0–1 s | stands with two balls in the right hand and one in the left, looking at the hands |
| 1 s | first throw, from the right hand |
| 5.06–6.56 s | the weight moves onto the left foot, while juggling |
| 6.81–7.75 s | the right heel rises, the toes leave the floor at 7.13 s, and the foot comes fully up |
| 7.75–16 s | juggles on one foot |
| 16.04 s | last catch: 45 throws in all, 20 before the lift and 25 on one foot |
| 16.59–17.43 s | the foot comes down, toes first |
| 18.31 s | the weight is back between the feet |
| to 20 s | stands still, holding the balls in front of the body |

**How the program works**, in plain words (the agent's full account is in [`NOTES.md`](../../runs/H02-juggling/NOTES.md)). The agent's main decision was **balls first, body last**: free fall is the one thing a viewer cannot be fooled about, so it is made exact, and everything else gives way to it.

1. **What happens when.** In this pattern every ball is thrown again three beats after its last throw. The agent uses a beat of 0.33 s, a time in the hand of 0.42 s and a time in the air of 0.57 s. Throw times and heights vary slightly, a little more on one foot, so the pattern is not perfectly mechanical.
2. **The balls.** Every flight is computed as an exact free fall between a planned release point and a planned catch point.
3. **The hands fit the balls.** At the release the hand has the ball's position and speed, and it then slows down faster than gravity slows the ball, which is how a ball really leaves a hand. At the catch the hand is already moving down at 55 % of the ball's speed. Between these moments the hand follows the smoothest possible path.
4. **Fingers.** Finger shapes are computed for the size of the ball, not stored. The fingers close until they touch the ball, then open again until the fingertips are below the ball's middle: an open cup. They open at each release and close at each catch, in a small wave from the index to the little finger.
5. **The body.** The path of the centre of mass is written down first: over the standing foot well before the heel rises, then a slow sway. The pelvis is then moved so that the real centre of mass follows this path. The knees give a little with each throw, the chest turns against the throwing arm, and the head and eyes follow the balls. These reactions are scripted to look right. They are not caused by any physics.

**A clever use of the measuring tool.** The agent cannot see the skin of the hand, only about 24 points on it. To find out where a ball sits in a real hand, it made test clips in which each frame tried another position and finger shape, ran `evaluate.py` on them, and read back how deep the skin went. This is allowed, and it turned the measuring tool into a way of seeing the skin.

**Bugs it found:**

- **A hand swinging across the body:** after its last catch, each hand swung 27 cm inwards and back out. On the main task this met every target. It only showed on other tasks, and the agent first explained it wrongly before finding the real cause. It now has a check for this.
- **Arm out of reach:** the first plan needed the arm to be 1.3 times its real length.
- **A thumb through the ball**, by 2 cm, and **an elbow that became too fast** when a planned path overshot its lowest point.
- **Fingers over the top:** fingers wrapped fully round the ball lifted the average contact above the ball's centre, so `evaluate.py` counted the ball as hanging from the hand. This is what led to the open cup (see section 5).

## 4. Results

### Videos and images

- **Main video:** [`videos/grid.mp4`](../../runs/H02-juggling/videos/grid.mp4), all eight cameras at once
- **Single views:** `front`, `back`, `left`, `right`, `top`, `overview`, `hands_left`, `hands_right` (`.mp4`, in the same folder, kept locally)
- **Close-ups of each phase:** [start and first throws](../../runs/H02-juggling/videos/contact_sheet_start.png), [one catch, frame by frame](../../runs/H02-juggling/videos/contact_sheet_catch.png), [the foot lift](../../runs/H02-juggling/videos/contact_sheet_lift.png), [juggling on one foot](../../runs/H02-juggling/videos/contact_sheet_onefoot.png), [the end](../../runs/H02-juggling/videos/contact_sheet_end.png)
- **Unseen task:** [`unseen/videos/grid.mp4`](../../runs/H02-juggling/unseen/videos/grid.mp4), [the foot lift](../../runs/H02-juggling/unseen/videos/contact_sheet_lift.png)

Juggling on one foot, from 11.0 to 11.9 s:

![Juggling on one foot, seen from six cameras at eight moments](../../runs/H02-juggling/videos/contact_sheet_onefoot.png)

### Measurements

All 48 targets are met on the task, and 47 of 48 on the unseen task. We measured both ourselves; the numbers do not come from the agent's notes. The meaning of each measurement is explained on [How results are measured](../02-measurements.md#juggling).

**The unseen task.** After the session we ran the agent's finished program, unchanged, on [`tasks/juggling-variant.json`](../../tasks/juggling-variant.json), which it never saw. The balls are bigger and heavier (8 cm, 150 g), the person starts in another place facing 40° away, stands on the **right** foot, the clip lasts 24 s, and the minimum numbers are higher (12 throws, 15 throws, 7 s).

| | Measurement | H02 task | Unseen task | Target |
|---|---|---|---|---|
| | **Feet and stillness** | | | |
| ✅ | Deepest sinking into the floor | 2.62 mm | 2.07 mm | ≤ 10 mm |
| ✅ | Frames sinking more than 1 cm | 0 | 0 | 0 |
| ✅ | Frames with nothing on the floor | 0 | 0 | 0 |
| ✅ | Typical speed of floor-touching skin | 0.11 cm/s | 0.11 cm/s | ≤ 1 cm/s |
| ✅ | Speed of floor-touching skin, 95th percentile | 0.42 cm/s | 0.39 cm/s | ≤ 3 cm/s |
| ✅ | Start position error | 0 cm | 0 cm | ≤ 15 cm |
| ✅ | Start heading error | 0.02° | 0.02° | ≤ 15° |
| ✅ | Pelvis speed while standing at the start | 0.61 cm/s | 0.61 cm/s | ≤ 10 cm/s |
| ✅ | Pelvis speed while standing at the end | 0.29 cm/s | 0.48 cm/s | ≤ 10 cm/s |
| ✅ / ❌ | Fastest joint rotation | 673 °/s | **809 °/s** | ≤ 800 °/s |
| ✅ | Frames with a pop | 0 | 0 | 0 |
| | **Holding the balls** | | | |
| ✅ | Frames at the start without all balls in the hands | 0 | 0 | 0 |
| ✅ | Frames at the end without all balls in the hands | 0 | 0 | 0 |
| ✅ | Frames with more than two balls in one hand | 0 | 0 | 0 |
| ✅ | Narrowest contact between a hand and a held ball | 6.38 cm | 5.58 cm | ≥ 5 cm |
| ✅ | Ball-frames in which a held ball has no support from below | 0 | 0 | 0 |
| ✅ | Deepest hand skin inside a ball | 5.63 mm | 6.53 mm | ≤ 8 mm |
| | **The balls in the air** | | | |
| ✅ | Largest gravity error of a flight | 0 % | 0 % | ≤ 3 % |
| ✅ | Largest difference between a flight and a free fall | 0 mm | 0 mm | ≤ 3 mm |
| ✅ | Flights too short to be a throw | 0 | 0 | 0 |
| ✅ | Balls that are never caught | 0 | 0 | 0 |
| ✅ | Lowest throw | 35.8 cm | 35.1 cm | ≥ 20 cm |
| ✅ | Highest point of any ball | 1.63 m | 1.65 m | ≤ 2.1 m |
| ✅ | Fastest ball | 2.96 m/s | 2.98 m/s | ≤ 6 m/s |
| ✅ | Deepest two balls go into each other | 0 mm | 0 mm | ≤ 2 mm |
| ✅ | Deepest body skin (not hands) inside a ball | 0 mm | 0 mm | ≤ 8 mm |
| | **Throwing and catching** | | | |
| ✅ | Throws before the foot lifts | 20 | 24 | ≥ 9 (unseen ≥ 12) |
| ✅ | Throws on one foot | 25 | 33 | ≥ 12 (unseen ≥ 15) |
| ✅ | Throws of the least thrown ball | 15 | 19 | ≥ 7 (unseen ≥ 9) |
| ✅ | Throws from the other hand than the throw before | 100 % | 100 % | ≥ 95 % |
| ✅ | Throws caught by the other hand | 100 % | 100 % | ≥ 95 % |
| ✅ | Longest time between two throws | 0.37 s | 0.37 s | ≤ 0.6 s |
| ✅ | Largest jump in a ball's speed at the release | 0.80 m/s | 0.75 m/s | ≤ 1.5 m/s |
| ✅ | Largest jump in a ball's speed at the catch | 1.13 m/s | 1.11 m/s | ≤ 2.5 m/s |
| ✅ | Shortest time a ball stays in a hand | 0.43 s | 0.43 s | ≥ 0.12 s |
| | **Standing on one foot** | | | |
| ✅ | Times the foot leaves the floor | 1 | 1 | 1 |
| ✅ | Frames the standing foot is off the floor | 0 | 0 | 0 |
| ✅ | Time on one foot | 9.73 s | 12.3 s | ≥ 5 s (unseen ≥ 7 s) |
| ✅ | Typical height of the lifted foot | 13.2 cm | 13.4 cm | ≥ 10 cm |
| ✅ | Time from the last catch to the foot coming down | 1.03 s | 1.03 s | ≥ 0.2 s |
| ✅ | All balls in the hands when the foot comes down | yes | yes | yes |
| ✅ | Frames off balance on one foot | 0 | 0 | 0 |
| | Worst balance margin on one foot (negative means always inside the foot) | −2.3 cm | −2.5 cm | |
| ✅ | Frames off balance on two feet | 0 | 0 | 0 |
| ✅ | Largest distance of the pelvis from where it starts | 15.5 cm | 15.2 cm | ≤ 20 cm |
| ✅ | Standing up at the end | 99.1 % | 99.1 % | ≥ 96 % |
| | **Body** | | | |
| ✅ | Deepest forearm or hand skin inside the trunk or legs | 0 mm | 0 mm | ≤ 15 mm |
| ✅ | Knees and elbows bending the wrong way | 0° | 0° | ≤ 5° |
| ✅ | Largest wrist rotation | 63.0° | 62.9° | ≤ 85° |

**How the juggling looks** (no targets):

| Measurement | H02 task | Unseen task |
|---|---|---|
| Throws per second | 3.04 | 3.0 |
| Typical time in the air | 0.57 s | 0.57 s |
| Typical time in a hand | 0.50 s | 0.50 s |
| Typical highest point of a throw | 1.58 m | 1.60 m |
| Variation of the highest point | 2.0 cm | 1.9 cm |
| Variation of the time between throws | 20 ms | 22 ms |
| Sway of the centre of mass on one foot | 3.5 cm | 3.6 cm |

**How to read these numbers:**

- **The one miss is small.** On the unseen task the left elbow reaches 809 °/s for an instant at 17.2 s, 1 % over the limit, and the measurements find no pop. Still, it is a real miss on a task the agent had not seen, while all of its own test tasks passed, which is why an independent test matters.
- **The free fall is exact because it is constructed.** A difference of 0 mm does not show skill in the air. It shows that the agent chose the right order: compute the balls, then make the hands fit.
- **The catch is soft.** The ball's speed jumps by about 1.1 m/s at a catch, where a hand that stood still would give about 3 m/s.
- **The numbers look like juggling.** Three throws a second and about half a second in the air are in the range of relaxed three-ball juggling, as far as we know without measured data to compare with.

**Other tasks.** We ran these ourselves with the final program:

| Tasks | Result |
|---|---|
| The agent's 11 juggling test tasks (right foot, other headings, balls of 5–9 cm, clips of 12–30 s, 25 frames per second) | all 48/48. Not an independent test, because the agent tuned its code on them |
| Box: the H01 task and its unseen variant | 38/38 on both. The agent's library for the box is unchanged |
| Walking: straight walk, curved path, turns, narrow passage | 11/11, 11/11, 15/15, 15/15 |

So one `make_motion.py` now handles walking, carrying a box and juggling.

**Speed.** With the program finished, the 20-second clip takes 1.6 s to compute, or about 5 s including starting Python. The unseen 24-second clip takes 1.9 s, or about 6 s in total. Repeated runs give identical files.

### What we see in the videos

This assessment comes from still images, not from watching the videos: 40 moments of the clip and 8 of the unseen task, from six cameras each. Stills cannot show rhythm and flow, and for juggling these matter more than for any earlier task. People need to watch [`grid.mp4`](../../runs/H02-juggling/videos/grid.mp4). The agent also never saw the motion move, only still images.

**What looks natural:**

- **It reads as juggling at once.** From the front and the sides, the balls form the familiar crossing pattern in front of the face.
- **The hands are far better than in H01.** They cup the ball, the fingers curl round it and open at the release. See the [frame-by-frame catch](../../runs/H02-juggling/videos/contact_sheet_catch.png).
- **The catch (3.1–3.27 s):** the hand comes up under the ball and goes down with it.
- **Two balls in one hand (0.7–1 s and from 16.3 s):** they lie side by side in the hand, which looks plausible.
- **The weight moves first (5.8–6.8 s),** and only then does the heel rise and the foot peel off the floor. That is the right order.
- **The body is not a statue.** The shoulders tilt and the chest turns with the throws, which is clearest from behind.
- **The ending (15.4–18.6 s)** happens in the right order and reads clearly: last catches on one foot, foot down, weight back, standing still.

**What does not look right, or needs checking:**

- **The hands move more than they need to.** After a throw, the empty hand rises to chest height (the wrist reaches 1.21 m, and travels 26 cm up and down) with the fingers tilted up by up to 39°. In the front view this looks more like a gesture than a relaxed follow-through, for example at 3.0–3.1 s, 6.4 s and 11.0 s.
- **The weight shift is large.** The pelvis moves 15 cm, and our plain test clip stayed in balance with 9.5 cm. From the front and from behind the person visibly leans to the side at 6.4–7.4 s.
- **The one-foot pose looks held.** The knee is raised higher than needed and the pose hardly changes for almost 10 seconds. It looks posed, not like someone keeping their balance.
- **Very tidy.** Heights vary by 2 cm and the rhythm by 20 ms, and nothing ever goes slightly wrong. There are no recoveries, and the pattern does not react to the foot lifting. A real person would show some of this. The agent says the same.
- **To check in the video:** whether the rhythm feels alive, whether the head really follows the balls, and whether balls moving 10 cm per frame look smooth at 30 frames per second.

## 5. Problems and limitations

- **There is no physics.** The balls obey gravity exactly, but the body's balance is a written path and its reactions to the throws are scripted. Nothing computes forces. A throw does not actually push the body.
- **The measurement shaped the fingers.** Our "support from below" check counted fully wrapped fingers as a ball hanging from the hand, and the agent moved to an open cup. That suits juggling, but the check would be wrong for holding a ball firmly, and it needs changing before a task like that.
- **The agent developed against the measuring tool,** 21 times, so the 48/48 says less than the unseen result.
- **Three balls only.** Any other number stops with a clear error. Ball sizes were calibrated for 5–9 cm across, for this one body.
- **Two balls in a hand are simple.** A ball moving between its places slides along a planned path and does not roll.

**Things that went wrong in the setup.** None of them changes the result, but they belong in the record:

- **Our notes reached the agent.** Claude Code gave the agent's session the two-line index of our private project notes, one line of which said that H02 was prepared. The agent did not open the notes themselves, which the audit confirms. The index contained nothing about the unseen task or how to solve the task. This is fixed: sessions now run with this memory switched off, tested before use.
- **A wrong path in the prompt.** `TASK.md` pointed to `previous/H01-box-carry/task.json`, which does not exist in the agent's folder. The agent noticed, used the box tasks in `test_tasks/` instead and said so. The template is fixed.
- **One forbidden action.** Once, in the middle of its work and without any explanation, the agent tried to write a file called `scratch_placeholder_do_not_use.txt` outside its folder, in the project root. The permissions blocked it, nothing was written, and the agent reported it itself in its final message. Otherwise it read and wrote only inside its folder, and used only numpy and scipy.

## 6. Conclusion and next step

**How good?** Better than we expected. A person juggles 45 throws without a drop, stands on one foot for almost 10 seconds, and ends correctly, from a task file and without any recorded motion. The finished program handled bigger balls and the other foot on a task it never saw, with one small miss. The hands, the main flaw of H01, are now convincing in still images. What is missing is life: small errors, recoveries, and a body that really reacts.

**How fast?**

| Step | Time | Cost |
|---|---|---|
| First complete motion | 18.5 min | about $2 |
| First motion meeting all targets on this one task | 32 min | about $4 |
| Finished, general program with notes | 74 min | $11.33 |
| Running the finished program on a new task | about 6 s | no agent needed |

| | H01 box | H02 juggling |
|---|---|---|
| First motion meeting all targets | 24 min | 32 min |
| Finished | 99 min | 74 min |
| Cost | $16.74 | $11.33 |
| Interrupted | once | no |

The harder task took less time and money. This is one run each, so it proves little, but there are likely reasons: H02 reused H01's arm and finger kinematics and its mass model, it needed no route planning, and it was not interrupted.

**Next step.** First, people should watch `grid.mp4`, because this is the first experiment where the judgement depends mostly on movement. After that, the next experiment could be either a **more alive juggler** (a real reaction of the body to each throw, small errors and recoveries) or a **new kind of object handling**, such as a pan held in one hand, which moves towards the kitchen task. The second tests generality, and that is the project's main goal, so it is our recommendation.

## Files in the experiment folder

| File | Content |
|---|---|
| [`TASK.md`](../../runs/H02-juggling/TASK.md), [`CLAUDE.md`](../../runs/H02-juggling/CLAUDE.md), [`SMPLX_INTERFACE.md`](../../runs/H02-juggling/SMPLX_INTERFACE.md) | exactly what the agent was told |
| [`make_motion.py`](../../runs/H02-juggling/make_motion.py), [`juggling/`](../../runs/H02-juggling/juggling/), [`manipulation/`](../../runs/H02-juggling/manipulation/), [`locomotion/`](../../runs/H02-juggling/locomotion/) | the agent's program: the new juggling library, and the box and walking libraries, unchanged |
| [`tools/`](../../runs/H02-juggling/tools/) | the agent's own checking tools |
| [`test_tasks/`](../../runs/H02-juggling/test_tasks/) | its 11 extra juggling tasks and one walking task |
| [`NOTES.md`](../../runs/H02-juggling/NOTES.md) | the agent's own account |
| `motion.npz` | the motion: SMPL-X parameters and ball positions for each frame |
| [`motion.metrics.json`](../../runs/H02-juggling/motion.metrics.json), [`motion.timeline.csv`](../../runs/H02-juggling/motion.timeline.csv), [`motion.throws.csv`](../../runs/H02-juggling/motion.throws.csv) | the measurements, the frame-by-frame numbers, and one line for every flight |
| `unseen/` | the unseen task: task file, motion, measurements and videos, made by us after the session |
| `previous/H01-box-carry/` | the starting code it was given |
| `transcript.jsonl`, [`run_summary.json`](../../runs/H02-juggling/run_summary.json), [`run.json`](../../runs/H02-juggling/run.json) | the full session log, its key facts, and how it was started |
| `videos/` | rendered videos and images, including the close-ups of each phase, `contact_sheet_*.png` |
