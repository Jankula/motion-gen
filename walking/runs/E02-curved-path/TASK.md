# Task: Walk along an S-shaped path

You are animating a 3D human body. The body is the SMPL-X parametric model, and the only control you have over it is its parameters: a translation and an orientation for the whole body and a rotation for each joint, for every frame. Your goal is motion that does what is asked below and looks as realistic as you can make it, ideally indistinguishable from a recording of a real person.

`SMPLX_INTERFACE.md` describes the parameters, the coordinate frame and the motion file format. `body_info.json` gives the body's measurements. Read both before you start.

## What the person does

One adult walks along the marked S-shaped path at a natural, self-selected pace: first a bend to the left, then a bend to the right, then straight on. The person is already walking when the clip starts and is still walking when it ends (they do not reach the end of the marked path). The body should turn with the path the way a real walker's does, not slide around the bends.

- **Clip:** 30 fps, exactly 300 frames (10 seconds).
- **Start:** already walking at position (x = 0, z = 0), heading 0° (facing +Z).
- **End:** still walking when the clip ends.
- **Path:** from the start pose, 1.5 m straight, then a 90° bend to the left (radius 2 m), then a 90° bend to the right (radius 2 m), then 6 m straight. The pelvis should stay within 0.15 m of the path (it is drawn on the floor in the videos).

`task.json` holds the same task in machine-readable form. Positions are points on the floor, `[x, z]` in meters, and refer to the pelvis joint projected onto the floor. Headings are in degrees: 0 faces +Z, 90 faces +X, and turning left increases the heading. A path is given either as `segments` (straight pieces and arcs, starting from the start pose; a positive `turn_deg` bends left) or as `points` (a polyline with corners). Obstacles are upright boxes standing on the floor: `size` is [extent along x, height, extent along z] before rotation, and `yaw_deg` rotates the box about the vertical axis.

## Starting point

`previous/E01-straight-walk/` holds the code and notes of the previous experiment, in which an earlier session of an AI agent solved an earlier task: "Walk in a straight line". Read its `NOTES.md` first. Reuse it, change it or replace parts of it, whatever gives the best result. Do not modify the files in `previous/`; build your own version in this directory.

The earlier tasks are in `tasks/`: `straight-walk.json`. Your `make_motion.py` must still produce good motion for them, so check each with `evaluate.py` too.

## Deliverables (in this directory)

1. **`make_motion.py`**: running `C:/Projects/motion-gen/walking/.venv/Scripts/python.exe make_motion.py <task file> <output .npz>` writes the motion for that task. It must be self-contained (apart from your own modules in this directory) and deterministic. It must work for `task.json` and for every task file in `tasks/`.
2. **A reusable motion library** (for example a `locomotion/` package) that `make_motion.py` uses, rather than one script per task. Later experiments will start from your code and give it new tasks: other paths, turns, obstacles, starting and stopping. General, well-structured code is part of the result.
3. **Speed:** generating a clip should take a few seconds, at most about 1 second of computing per second of motion.
4. **`motion.npz`**: the motion for `task.json`. `C:/Projects/motion-gen/walking/.venv/Scripts/python.exe check_format.py motion.npz task.json` must print `OK`.
5. **`NOTES.md`**, written for a reader who is not an animation specialist: what you built and how it works, what you changed compared with the starting point, the main choices you made and why, how you checked the result (include the final `evaluate.py` table for every task), and the weaknesses you know of. Explain technical terms when you first use them.

## How the result is judged

The motion is rendered as video from six cameras. Four follow the person (front, back, left side, right side), one looks straight down on the whole scene, and one gives an overview of the whole scene. The floor is a checkerboard of 0.5 m tiles, the path is drawn on it, and obstacles are shown as translucent boxes. People who know what human movement looks like watch the videos. Anything that gives away that this is not a real person counts against it, for example:

- feet that slide over the floor while bearing weight, sink into it, or hover above it
- body parts that pass through each other or through obstacles
- stiff, robotic or perfectly mechanical movement
- joints that bend the wrong way, or further than a real joint can
- body parts that move independently instead of as one coordinated body
- a speed that does not match what the legs are doing
- asymmetry or limping
- starting, stopping and turning that do not look the way people do them (when the task contains them)
- not doing what the task asks: leaving the path, missing the start or end pose, touching obstacles

This list is not exhaustive.

## Your tools

- **`C:/Projects/motion-gen/walking/.venv/Scripts/python.exe evaluate.py [motion.npz] [task.json]`** measures the motion on the real body mesh and prints a table. It reports:
  - how deep the skin ever sinks into the floor, and whether there are frames with nothing on the floor
  - how fast skin that touches the floor slides along it
  - how far the pelvis strays from the path, and the start and end pose errors
  - how close the body comes to each obstacle (negative means inside it)
  - the fastest joint rotation, to catch glitches

  Each line has a target. The defaults are `motion.npz` and `task.json`. Use it as often as you like; it takes about half a minute.
- **`C:/Projects/motion-gen/walking/.venv/Scripts/python.exe preview.py [motion.npz] [task.json] [--start S] [--duration D]`** renders two images into `preview/`:
  - `contact_sheet.png`: the four follow cameras, one row each, eight frames across a time window you choose (default 1.2 s starting at 2 s)
  - `overview_sheet.png`: the top and overview cameras at five moments across the whole clip

  Open the images to look at them. You can run `preview.py` at most 8 times in total, so choose the time windows deliberately, for example around turns, obstacles, starts and stops. It takes about a minute.
- You may also check your motion numerically with your own code, for example with the forward kinematics in `SMPLX_INTERFACE.md`.

## Rules

- Use only your own knowledge and reasoning. Do not use motion-capture data, motion datasets, pretrained models or motion files of any kind, and do not search for them. No internet. (Code in `previous/` was written by an earlier agent session from its own knowledge; you may use it.)
- Run Python as `C:/Projects/motion-gen/walking/.venv/Scripts/python.exe`. Use only the standard library, numpy and scipy. Do not install packages.
- Stay inside this directory: do not read or write anything outside it.
- Work autonomously until the deliverables are done. Nobody will answer questions. When something is ambiguous, decide and note the decision in `NOTES.md`.
