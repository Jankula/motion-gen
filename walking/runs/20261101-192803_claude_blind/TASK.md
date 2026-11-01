# Task: make a human walk

You are animating a 3D human body. The body is the SMPL-X parametric model, and the only control you have over it is its parameters: a translation and an orientation for the whole body and a rotation for each joint, for every frame. Your goal is a clip of a person walking that is as realistic as you can make it, ideally indistinguishable from a recording of a real person.

`SMPLX_INTERFACE.md` describes the parameters, the coordinate frame and the motion file format. `body_info.json` gives the body's measurements. Read both before you start.

## The clip

- 30 fps, exactly 180 frames (6 seconds).
- One adult walking forward in a straight line along +Z, on flat, level ground, at a natural self-selected pace.
- Steady walking: the person is already walking when the clip starts and is still walking when it ends.
- At frame 0 the pelvis is above the origin: the x and z of `transl` are near 0.
- The whole body is judged, not only the legs.

## Deliverables (in this directory)

1. `generate_motion.py`: a self-contained, deterministic script. Running `C:/Projects/motion-gen/walking/.venv/Scripts/python.exe generate_motion.py` writes `motion.npz`.
2. `motion.npz`: the motion. `C:/Projects/motion-gen/walking/.venv/Scripts/python.exe check_format.py motion.npz` must print `OK`.
3. `NOTES.md`: how you approached the problem, the main choices you made and why, how you checked the result, and the weaknesses you know of.

## How the result is judged

The motion is rendered as video from four cameras that follow the walker (front, back, left side, right side) over a checkerboard floor of 0.5 m tiles. People who know what human walking looks like watch it. Anything that gives away that this is not a real person counts against it, for example:

- feet that slide over the floor while bearing weight, sink into it, or hover above it
- body parts that pass through each other
- stiff, robotic or perfectly mechanical movement
- joints that bend the wrong way, or further than a real joint can
- body parts that move independently instead of as one coordinated body
- a walking speed that does not match what the legs are doing
- asymmetry or limping

This list is not exhaustive.

## Rules

- Use only your own knowledge and reasoning. Do not use motion-capture data, motion datasets, pretrained models or motion files of any kind, and do not search for them. No internet.
- Run Python as `C:/Projects/motion-gen/walking/.venv/Scripts/python.exe`. Use only the standard library, numpy and scipy. Do not install packages.
- Stay inside this directory: do not read or write anything outside it.
- You will not see the rendered result, and no renderer is available to you. You may check your motion numerically with your own code, for example using the forward kinematics in `SMPLX_INTERFACE.md`.
- Work autonomously until the deliverables are done. Nobody will answer questions. When something is ambiguous, decide and note the decision in `NOTES.md`.
