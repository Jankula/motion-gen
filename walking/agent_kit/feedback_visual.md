## Your tools

- **`$python evaluate.py [motion.npz] [task.json]`** measures the motion on the real body mesh and prints a table. It reports:
  - how deep the skin ever sinks into the floor, and whether there are frames with nothing on the floor
  - how fast skin that touches the floor slides along it
  - how far the pelvis strays from the path, and the start and end pose errors
  - how close the body comes to each obstacle (negative means inside it)
  - the fastest joint rotation, to catch glitches

  Each line has a target. The defaults are `motion.npz` and `task.json`. Use it as often as you like; it takes about half a minute.
- **`$python preview.py [motion.npz] [task.json] [--start S] [--duration D]`** renders two images into `preview/`:
  - `contact_sheet.png`: the four follow cameras, one row each, eight frames across a time window you choose (default 1.2 s starting at 2 s)
  - `overview_sheet.png`: the top and overview cameras at five moments across the whole clip

  Open the images to look at them. You can run `preview.py` at most $max_previews times in total, so choose the time windows deliberately, for example around turns, obstacles, starts and stops. It takes about a minute.
- You may also check your motion numerically with your own code, for example with the forward kinematics in `SMPLX_INTERFACE.md`.
