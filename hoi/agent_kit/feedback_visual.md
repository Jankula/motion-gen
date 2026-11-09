## Your tools

- **`$python evaluate.py [motion.npz] [task.json]`** measures the motion on the real body mesh and prints a table. It reports:
  - how deep the skin ever sinks into the floor, and how fast skin that touches the floor slides along it
  - how the hands touch the box: gaps, skin inside the box, contact area, sliding, whether they are on opposite sides
  - how the box behaves: whether it moves without being held, is dragged, tilts, jumps or is jerked
  - how it is put down: distance from the target, speed at touchdown, whether the hands stay until it stands
  - whether forearms pass through the trunk or legs, and whether the body and the box pass through each other
  - whether the person stays balanced with the weight of the box
  - the fastest joint rotation, to catch glitches

  Each line has a target, and the file `<motion name>.metrics.json` gives its exact meaning. It also writes `<motion name>.timeline.csv` with the contact and balance numbers for every frame, so you can find when something goes wrong. The defaults are `motion.npz` and `task.json`. Use it as often as you like; it takes about a minute.
- **`$python preview.py [motion.npz] [task.json] [--start S] [--duration D]`** renders two images into `preview/`:
  - `contact_sheet.png`: six cameras, one row each (the four follow cameras and the two close-ups of the hands), eight frames across a time window you choose (default 1.2 s starting at 2 s)
  - `overview_sheet.png`: the top and overview cameras at five moments across the whole clip

  Open the images to look at them. You can run `preview.py` at most $max_previews times in total, so choose the time windows deliberately, for example around the grip, the lift, the turn and the set-down. It takes about a minute.
- You may also check your motion numerically with your own code, for example with the forward kinematics in `SMPLX_INTERFACE.md`.
