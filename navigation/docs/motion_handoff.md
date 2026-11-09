# Motion hand-off: from household tasks to SMPL-X motion

This note is for the motion side (your `walking/` code). It describes what our household agent produces for
each run, how the walks can be fed to your `make_motion.py` as they are, and what else the tasks ask of the body.

## What produces it

Our agent gets an instruction ("Make me scrambled eggs, serve them at the kitchen table and sit down to eat") in
a ProcTHOR house. It breaks the task into subtasks and carries them out with tools: walk to an object, open,
pick up, put down, switch on, sit. A path planner makes every walk collision-free for a 0.25 m-radius cylinder.
At the end, the run is written out as a sequence of motions in `<run>/motion/`:

```
motion/
  motion_script.json    subtasks → motion segments, an object timeline, the frame transforms
  walks/walk_NN.json    one task file per walk, in your task format
  route_motion.png      the house from above, the route coloured by subtask, every motion labelled
```

## Running the walks with your code

Each `walks/walk_NN.json` is a task file like your `walking/tasks/*.json`. All of ours load with
`walkenv.tasks.load_task` and `describe`. From your E04 folder:

```bash
python make_motion.py <run>/motion/walks/walk_01.json walk_01.npz
```

What each file contains:
- **`start`**: standing, at the walk's first point, facing along the first piece of the path.
- **`end`**: standing, at the walk's last point, facing the object the person walked to. Your code stops and
  turns on the spot to this heading.
- **`path.points`**: the planned route simplified to its corners (within 3 cm), tolerance 0.15 m. The route
  keeps at least 0.25 m from any obstacle to the pelvis line.
- **`obstacles`**: every box within 1 m of the path that blocks the body. That includes furniture and walls
  (long thin boxes), and their top is the box height. Some big objects (L-shaped counters, a round dog bed)
  come as several boxes, one per rectangle they cover, labelled `fridge_1`, `counter_top_1 part 3`, and so on.
- **`frames`**: our estimate of the walk (1.2 m/s, 1.0 m/s when carrying, +0.8 s to start, +1.0 s to stop, plus
  the end turn) plus 1.5 s of standing, at 30 fps.
- **`instruction`**: written in your style, mentioning narrow stretches and what is carried.
- **`source`**: our episode and segment number, with `expected_seconds`. Your loader ignores it.

## Frames

| | up | floor | heading |
|---|---|---|---|
| ours | z | `[x, y]` | degrees counter-clockwise from +x |
| yours | Y | `[X, Z] = [x, -y]` | `heading_deg = heading + 90` (0 faces +Z, 90 faces +X) |
| AI2-THOR (the house renders) | y | position `{x: x, z: y}` | yaw `90 - heading` |

Both of our frames are right-handed, and turning left raises the heading in both. The walk files are already in
yours. `motion_script.json` is in ours, and its `frame` field repeats this table.

## The whole task: `motion_script.json`

`segments` is the full sequence. Each segment is one motion with an estimated duration (`duration_est`, and
`t_est` = [start, end] if everything ran back to back) and a text `caption`:

| motion | what the body does | the fields that drive it |
|---|---|---|
| `walk` | walk from `from` to `to` along `path`, stop facing `end_heading` | `partner_task` (the walk file), `carrying` (`{"right": "plate_1"}`), `narrow` (stretches where an obstacle is closer than 0.315 m: your shoulder or side mode), `rooms` crossed |
| `turn` | turn on the spot from `from_heading` to `to_heading` (`angle` > 0 is left) | `at` |
| `step_back` | short step(s) backwards, still facing the object, as a door swings open | `from`, `to` (0.3–1.2 m) |
| `open` / `close` | pull or push a door or drawer | `contact` [x, y, z] on the nearest side of the box at handle height (about 1 m, lower for low drawers), `hand` |
| `reach_grasp` | pick something up | `contact` = the object's centre, `height`, `hand` |
| `put_down` | put a held thing on or into something | `contact` (where it goes), `relation` (`on`/`in`), `into_held` (into a container held in the other hand), `hand` |
| `use` | press a switch or button | `contact`, `hand` |
| `sit_down` / `stand_up` | sit on a chair or sofa, and get up before the next walk | `seat` [x, y, height] (seat height is estimated, at most 0.46 m) |

Every action segment also has `at` (where the person stands) and `reach` (horizontal distance from `at` to
`contact`). The person stands still between segments, so the end pose of one segment is the start of the next.

The segments are grouped into **`subtasks`**, the steps the agent named itself ("get an egg from the fridge").
In older runs, without named steps, they are grouped per walk with a templated text.

The **`objects`** timeline says which segment changes which object:
- `open`, `close`, and `switched_on` (with what's inside);
- `attach` (picked up, into which hand);
- `detach` (put down: into or onto what, and its new centre).

It refers to segment numbers rather than times, so it stays right when your clips are longer or shorter than our
estimates. It is what a final video needs to move objects with the hands.

## Putting one run together

1. Run `make_motion.py` on every `walks/walk_NN.json`.
2. Between walks, the person stands. For each `turn` or action segment in between, either hold the standing pose
   for `duration_est`, or generate the motion once your code can do it.
3. Joins: a walk clip ends standing at its `to`, facing `end_heading`. The next walk clip starts standing at its
   own `from`, which is the same point unless a `step_back` moved the person in between. It faces along its path;
   the `turn` segment in between covers the difference.
4. Re-time the script from your clip lengths. The object timeline follows the segment numbers.

## What the tasks ask for that your code can't do yet

Roughly in order of how often it comes up. Counts are from the agent's 19 recorded long tasks: 73 walks,
74 turns on the spot, 49 pick-ups, 46 put-downs, 19 opens, 19 closes, 13 switch-ons, 6 sit-downs and 3 step-backs.

1. **Turning on the spot before walking off.** Almost every walk starts facing the object of the previous
   action, away from the path: the median turn is 115°, and 44 of the 74 are over 90°. Today this is a separate `turn` segment, because a standing start
   facing away from the path isn't supported. Your end-of-walk turn already does the same movement.
2. **Walking while carrying** (one hand or both). The arms can't swing; `carrying` names the hand and the object.
3. **Reaching and grasping at a height** (0.1–1.8 m), and putting down. `contact` is the hand target.
   Most reaches are long: the median `reach` from the pelvis is 1.07 m, and 126 of 146 are over 0.7 m.
   - Our planner stops the person 0.25–0.7 m from an object's edge, and things on deep counters sit up to
     0.6 m further in.
   - Anything inside an open fridge counts as reachable from where the fridge is.
   - So the body needs a step closer or a lean. We could add a short `step` segment to a closer free spot
     before such actions, if that suits you better.
4. **Opening and closing** a fridge door, cabinet, drawer or microwave, with a step back when the door swings
   towards the person.
5. **Sitting down and standing up.**
6. **Clip length:** `frames` is our guess. Reporting the length you need, or a `"frames": "auto"`, would let us
   re-time instead of guessing.

## Example (house 2927, "make scrambled eggs", first segments)

```json
{"i": 0, "motion": "turn", "at": [3.83, 10.59], "from_heading": 0.0, "to_heading": -104.0, "angle": -104.0,
 "duration_est": 1.64, "caption": "a person turns on the spot 104 degrees to the right to set off", "subtask": 1}
{"i": 1, "motion": "walk", "target": "fridge_1", "from": [3.83, 10.59], "to": [4.93, 6.41], "length": 5.87,
 "end_heading": 28.5, "carrying": {}, "rooms": ["bedroom_1", "living_room_1", "kitchen_1"], "narrow": [],
 "duration_est": 7.5, "partner_task": "walks/walk_01.json",
 "caption": "a person walks from the bedroom into the kitchen to the fridge", "subtask": 1}
{"i": 2, "motion": "open", "object": "fridge_1", "hand": "right", "contact": [5.578, 6.665, 1.0], "height": 1.0,
 "at": [4.93, 6.41], "duration_est": 1.5, "caption": "a person opens the fridge with the right hand", "subtask": 1}
```

The code is `src/motiongen/motion_script.py`. `python scripts/export_motion.py <run>` regenerates `motion/` for any
run folder without a GPU or Claude.
