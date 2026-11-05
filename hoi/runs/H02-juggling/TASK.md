# Task: Juggle three balls, also on one foot

You are animating a 3D human body that juggles real balls. The body is the SMPL-X parametric model, and the only control you have over it is its parameters: a translation and an orientation for the whole body and a rotation for each joint and finger joint, for every frame. You also give the position of every ball for every frame. Your goal is motion that does what is asked below and looks as realistic as you can make it, ideally indistinguishable from a recording of a real person juggling real balls.

`SMPLX_INTERFACE.md` describes the parameters, the hands, the coordinate frame and the motion file format. `body_info.json` gives the body's measurements. Read both before you start.

## What the person does

One adult stands in one place, holding three small balls in their hands, ready to juggle. The person starts juggling the three balls in the air, in the classic three-ball pattern, throwing them from hand to hand. While they keep juggling without a break, they lift one foot off the floor and stand on the other foot, and they go on juggling like that. At the end, still on one foot, they catch all the balls, so that no ball is in the air any more. Only then do they put the foot down again and stand still on both feet, with the balls in their hands.

- **Clip:** 30 fps, exactly 600 frames (20 seconds).
- **Start:** standing still at position (x = 0, z = 0), heading 0° (facing +Z).
- **End:** standing still.
- **The balls:** 3 solid balls, each 6.5 cm across and weighing 120 g. A ball fits in one hand, and a hand can hold two of them.
- **Standing foot:** the person stands on the left foot.
- **At least:** 9 throws on both feet, 12 throws on one foot, and 5 seconds on one foot.

`task.json` holds the same task in machine-readable form. Positions are points on the floor, `[x, z]` in meters. The start position refers to the pelvis joint projected onto the floor. Headings are in degrees: 0 faces +Z, 90 faces +X, and turning left increases the heading. `balls` gives the number of balls, their radius and their mass. `juggle` gives the standing foot and the smallest numbers the result must reach. The mass of the body is about 76 kg.

## Starting point

`previous/H01-box-carry/` holds the code and notes of an earlier experiment, in which an earlier session of an AI agent solved "Pick up a box, carry it and put it down". That code can walk, stop and turn, bend down, hold and carry a box with both hands, compute arm and finger poses, and keep the body's centre of mass over the feet. It has never thrown or caught anything, and the person has never stood on one foot. Read its `NOTES.md` first. Reuse it, change it or replace parts of it, whatever gives the best result. Do not modify the files in `previous/`; build your own version in this directory.

## Deliverables (in this directory)

1. **`make_motion.py`**: running `C:/Projects/motion-gen/walking/.venv/Scripts/python.exe make_motion.py <task file> <output .npz>` writes the motion for that task. It must be self-contained (apart from your own modules in this directory) and deterministic.
2. **A reusable motion library** that `make_motion.py` uses, rather than one script per task. After this session, `make_motion.py` will also be run on a task file you have not seen: same kind of job, with other balls (other size and weight), another start position and heading, the other standing foot, another clip length and other minimum numbers. Do not hard-code these values. `make_motion.py` should also keep working for the earlier kinds of task, such as `previous/H01-box-carry/task.json`. Later experiments will start from your code and add other objects and actions, so general, well-structured code is part of the result.
3. **Speed:** generating a clip should take a few seconds, at most about 1 second of computing per second of motion.
4. **`motion.npz`**: the motion for `task.json`. `C:/Projects/motion-gen/walking/.venv/Scripts/python.exe check_format.py motion.npz task.json` must print `OK`.
5. **`NOTES.md`**, written for a reader who is not an animation specialist: what you built and how it works, what you changed compared with the starting point, the main choices you made and why, how you checked the result (include the final `evaluate.py` table), and the weaknesses you know of. Explain technical terms when you first use them.

## How the result is judged

The motion is rendered as video from eight cameras. Four follow the person (front, back, left side, right side), one looks straight down on the whole scene, one gives an overview of the whole scene, and two are close-ups of the hands and the balls, from the person's front left and front right. The floor is a checkerboard of 0.5 m tiles. The balls have three different colours, so a viewer can follow each one. People who know what human movement looks like watch the videos. Anything that gives away that this is not a real person juggling real balls counts against it, for example:

- a ball that does not fly like a real ball: it floats, steers, changes speed or jumps in the air
- a ball that shoots out of a hand that is hardly moving, or stops dead in a hand that does not give way
- a ball that appears in a hand before it has arrived there, or that a hand does not really reach
- a ball that sticks to a hand, hangs under it, lies on the back of it or balances on a fingertip
- fingers that stay in a resting pose while the hand is throwing and catching
- balls that pass through each other, or through the hands, the arms or the body
- a pattern that stops, stumbles or changes when the foot lifts or comes down
- a person who would fall over: on one foot, the weight has to be over that foot, and it has to get there before the foot leaves the floor
- a body that stands like a statue while only the arms move
- a person who never looks at the balls
- feet that slide over the floor while bearing weight, sink into it, or hover above it
- stiff, robotic or perfectly mechanical movement, in the arms as much as in the rest of the body
- joints that bend the wrong way, or further than a real joint can
- not doing what the task asks: dropping a ball, putting the foot down before all the balls are caught, or not ending up standing still on both feet with the balls in the hands

This list is not exhaustive.

## Your tools

- **`C:/Projects/motion-gen/walking/.venv/Scripts/python.exe evaluate.py [motion.npz] [task.json]`** measures the motion on the real body mesh and prints a table. It works out by itself when each ball is held and when it flies, and it reports:
  - how deep the skin ever sinks into the floor, and how fast skin that touches the floor slides along it
  - how the balls lie in the hands: contact, support from below, skin inside a ball
  - how the balls fly: whether every flight is a true free fall, how high, whether balls pass through each other or the body
  - how they are thrown and caught: the pattern, the rhythm, and whether the hand moves with the ball
  - how the person stands on one foot: time, foot height, whether the centre of mass stays over the standing foot, and the order of the last catch and the foot coming down
  - whether forearms pass through the trunk or legs
  - the fastest joint rotation, to catch glitches

  Each line has a target, and the file `<motion name>.metrics.json` gives its exact meaning. It also writes `<motion name>.timeline.csv` with the contact and balance numbers for every frame, and `<motion name>.throws.csv` with one line per flight, so you can find which throw or catch goes wrong. The defaults are `motion.npz` and `task.json`. Use it as often as you like; it takes about a minute.
- **`C:/Projects/motion-gen/walking/.venv/Scripts/python.exe preview.py [motion.npz] [task.json] [--start S] [--duration D]`** renders two images into `preview/`:
  - `contact_sheet.png`: six cameras, one row each (the four follow cameras and the two close-ups), eight frames across a time window you choose (default 1.2 s starting at 2 s)
  - `overview_sheet.png`: the top and overview cameras at five moments across the whole clip

  Open the images to look at them. You can run `preview.py` at most 12 times in total, so choose the time windows deliberately, for example around the first throws, a catch, the moment the foot lifts and the last catches. It takes about a minute.
- You may also check your motion numerically with your own code, for example with the forward kinematics in `SMPLX_INTERFACE.md`.

## Rules

- You may use any method you can build here with numpy and scipy, such as inverse kinematics, optimisation or physical simulation, and you may reuse anything in `previous/`. Otherwise use only your own knowledge and reasoning: no motion-capture data, motion datasets, pretrained models or motion files from elsewhere, and do not search for them. No internet. (Code in `previous/` was written by an earlier agent session from its own knowledge.)
- Run Python as `C:/Projects/motion-gen/walking/.venv/Scripts/python.exe`. Use only the standard library, numpy and scipy. Do not install packages.
- Stay inside this directory: do not read or write anything outside it.
- Work autonomously until the deliverables are done. Nobody will answer questions. When something is ambiguous, decide and note the decision in `NOTES.md`.
