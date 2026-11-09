# Task: $title

You are animating a 3D human body that handles a real object. The body is the SMPL-X parametric model, and the only control you have over it is its parameters: a translation and an orientation for the whole body and a rotation for each joint and finger joint, for every frame. You also give the position and orientation of the object for every frame. Your goal is motion that does what is asked below and looks as realistic as you can make it, ideally indistinguishable from a recording of a real person handling a real object.

`SMPLX_INTERFACE.md` describes the parameters, the hands, the coordinate frame and the motion file format. `body_info.json` gives the body's measurements. Read both before you start.

## What the person does

$description

`task.json` holds the same task in machine-readable form. Positions are points on the floor, `[x, z]` in meters. The start position refers to the pelvis joint projected onto the floor. Headings are in degrees: 0 faces +Z, 90 faces +X, and turning left increases the heading. The object's `size` is [extent along its own x axis, height, extent along its own z axis]; `center` is its centre seen from above; `yaw_deg` rotates it about the vertical axis. The mass of the body is about 76 kg.

$starting_point

## Deliverables (in this directory)

1. **`make_motion.py`**: running `$python make_motion.py <task file> <output .npz>` writes the motion for that task. It must be self-contained (apart from your own modules in this directory) and deterministic.
2. **A reusable motion library** that `make_motion.py` uses, rather than one script per task. After this session, `make_motion.py` will also be run on a task file you have not seen: same kind of job, with another box (other size, somewhat lighter or heavier), other positions and headings, and a target in another direction. Do not hard-code this layout. Later experiments will start from your code and add other objects and actions, so general, well-structured code is part of the result.
3. **Speed:** generating a clip should take a few seconds, at most about 1 second of computing per second of motion.
4. **`motion.npz`**: the motion for `task.json`. `$python check_format.py motion.npz task.json` must print `OK`.
5. **`NOTES.md`**, written for a reader who is not an animation specialist: what you built and how it works, what you changed compared with the starting point, the main choices you made and why, how you checked the result (include the final `evaluate.py` table), and the weaknesses you know of. Explain technical terms when you first use them.

## How the result is judged

The motion is rendered as video from eight cameras. Four follow the person (front, back, left side, right side), one looks straight down on the whole scene, one gives an overview of the whole scene, and two are close-ups of the hands, from the person's front left and front right. The floor is a checkerboard of 0.5 m tiles and the target spot is drawn on it. People who know what human movement looks like watch the videos. Anything that gives away that this is not a real person handling a real object counts against it, for example:

- a person who moves as if the box weighed nothing, or a box that behaves as if it weighed nothing
- a box that moves by itself, floats, jumps, sinks into the floor, is dragged, or is dropped
- hands that do not reach the box, slide over it, pass through it, or hold it in a way that could not really carry it
- fingers that stay in a resting pose while the hand is holding something
- body parts that pass through each other or through the box
- a person who would fall over: the box's weight counts for the balance too
- feet that slide over the floor while bearing weight, sink into it, or hover above it
- stiff, robotic or perfectly mechanical movement
- joints that bend the wrong way, or further than a real joint can
- body parts that move independently instead of as one coordinated body
- a speed that does not match what the legs are doing
- not doing what the task asks: leaving the box away from the target, or not ending up standing

This list is not exhaustive.

$feedback

## Rules

- You may use any method you can build here with numpy and scipy, such as inverse kinematics, optimisation or physical simulation, and you may reuse anything in `previous/`. Otherwise use only your own knowledge and reasoning: no motion-capture data, motion datasets, pretrained models or motion files from elsewhere, and do not search for them. No internet. (Code in `previous/` was written by an earlier agent session from its own knowledge.)
- Run Python as `$python`. Use only the standard library, numpy and scipy. Do not install packages.
- Stay inside this directory: do not read or write anything outside it.
- Work autonomously until the deliverables are done. Nobody will answer questions. When something is ambiguous, decide and note the decision in `NOTES.md`.
