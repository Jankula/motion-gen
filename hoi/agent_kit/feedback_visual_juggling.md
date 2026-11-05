## Your tools

- **`$python evaluate.py [motion.npz] [task.json]`** measures the motion on the real body mesh and prints a table. It works out by itself when each ball is held and when it flies, and it reports:
  - how deep the skin ever sinks into the floor, and how fast skin that touches the floor slides along it
  - how the balls lie in the hands: contact, support from below, skin inside a ball
  - how the balls fly: whether every flight is a true free fall, how high, whether balls pass through each other or the body
  - how they are thrown and caught: the pattern, the rhythm, and whether the hand moves with the ball
  - how the person stands on one foot: time, foot height, whether the centre of mass stays over the standing foot, and the order of the last catch and the foot coming down
  - whether forearms pass through the trunk or legs
  - the fastest joint rotation, to catch glitches

  Each line has a target, and the file `<motion name>.metrics.json` gives its exact meaning. It also writes `<motion name>.timeline.csv` with the contact and balance numbers for every frame, and `<motion name>.throws.csv` with one line per flight, so you can find which throw or catch goes wrong. The defaults are `motion.npz` and `task.json`. Use it as often as you like; it takes about a minute.
- **`$python preview.py [motion.npz] [task.json] [--start S] [--duration D]`** renders two images into `preview/`:
  - `contact_sheet.png`: six cameras, one row each (the four follow cameras and the two close-ups), eight frames across a time window you choose (default 1.2 s starting at 2 s)
  - `overview_sheet.png`: the top and overview cameras at five moments across the whole clip

  Open the images to look at them. You can run `preview.py` at most $max_previews times in total, so choose the time windows deliberately, for example around the first throws, a catch, the moment the foot lifts and the last catches. It takes about a minute.
- You may also check your motion numerically with your own code, for example with the forward kinematics in `SMPLX_INTERFACE.md`.
