# The household-agent pipeline

How a task given in words becomes a walked, acted-out route, and how to run your own.

```
 ProcTHOR house ──export──▶ scene.yaml + top render          (once per house, GPU)
                                  │
 your task text + start ──▶ episode.yaml ──render──▶ views   (once per episode, GPU)
                                  │
                                  ▼
            agent (claude -p)  ◀── mg scene / step / goto / open / pick / place / use / submit ──▶  world state
                 ▲                                    │                                          (state.json)
                 └── new ego view after each walk ◀── render server (one AI2-THOR for the run, GPU)
                                  │
                                  ▼
            state.json · route.png · transcript · summary/score
            motion/: motion_script.json (subtasks → motion segments) · walks/walk_NN.json (partner tasks) · route_motion.png
```

Everything below runs on the VM in the `motion-gen` conda env (`source ~/miniconda3/bin/activate motion-gen`).
AI2-THOR and the GPU are needed for the two export steps and the re-rendering during agent runs; the agent loop,
the world model, scoring and the motion hand-off are plain Python.

---

## 1. Exporting a house (`scripts/export_procthor.py scene`)

`python scripts/export_procthor.py scene train 2927` loads ProcTHOR-10K house 2927 in AI2-THOR (headless,
`--platform cloud`), closes every door and drawer, and writes `scenes/procthor/train_2927/`:

- **`scene.yaml`**: the house as our planner and agent see it.
  - `room`: the bounding box; `rooms`: one floor polygon per room (`kitchen_1`, `bedroom_2`, … numbered per type).
    Anything outside the polygons counts as wall.
  - `objects`: every object as an axis-aligned box: `id` (`fridge_1`), `label`, a CSS `color` name, `center` and
    `size` in metres. Coordinates are **z-up**: Unity `(x, y, z)` becomes `(x, z, y)`.
    Optional fields:
    - `supported_by` / `inside`: what it rests on or is stored in. `inside` only for openable containers and
      only below their top: an egg in the fridge is `inside`, a cloth on the toilet lid is `supported_by`.
    - `openable` and `open_box`: the box it fills when fully open, including the door swing.
    - `pickupable`, `receptacle`, `toggleable`: what a person can do with it. Washing machines and dryers are
      marked toggleable even though AI2-THOR can't switch them.
    - `footprint`: for large objects whose box is mostly empty (L- or U-shaped counters, toilets), the
      rectangles they really cover, measured from the top render.
    - `thor_id`: the AI2-THOR objectId, used when rendering.
  - Walls are thin boxes cut open at doorways. Open-plan connections (ProcTHOR `"empty"` walls) have no wall.
    Doors are flat boxes on the floor (a place to go to, never an obstacle).
  - Object parts that AI2-THOR lists separately (TV-stand shelves typed as "DiningTable", shelving-unit shelves,
    sink basins) are folded into their object; openable parts (a dresser's drawers) stay separate.
- **`views/top/`**: an orthographic 1600×1200 render from above (`rgb.png`), the instance-id image (`ids.png`),
  which object each id is with its pixel count and bounding box (`objects.json`), and the camera (`camera.json`).

To find houses with what a task needs: `python scripts/find_houses.py --limit 3000` (house JSON only, no simulator).
ProcTHOR has **no stove, oven or dishwasher**, and in the houses checked so far all sinks are in bathrooms.
Cooking means microwave, toaster, coffee machine or kettle.

## 2. The episode (`episodes/<dir>/<id>.yaml`)

One task in one house:

| field | meaning |
|---|---|
| `id`, `category` | name; category groups results in the eval |
| `scene` | path to a `scene.yaml` |
| `instruction` | the only thing the agent is told about the task |
| `start`, `heading` | start position `[x, y]` in metres; heading in degrees counter-clockwise from +x |
| `views` | rendered views (filled in by the views export) |
| `max_walks`, `max_actions` | budgets (defaults 8 walks, 40 actions) |
| `opened` | objects open at the start (their door swing blocks floor) |
| `hidden_objects` | boxes that block the body but aren't listed or rendered (a stale map) |
| `goals` / `stops` / `expect_infeasible` | how to score, see section 6; all optional |
| `reference` | a known solution as a list of steps (only used by `make_tasks.py` to check the goals) |

## 3. What the agent sees (`mg scene`, `src/motiongen/observe.py`)

`python scripts/export_procthor.py views <episode.yaml>` renders `<id>_top` and four first-person views from the
start (`ego_front/left/back/right`, 90° apart).

When the agent runs `mg scene`:
1. Objects covering at least 80 pixels in some view are visible. Small things (a mug on a far counter) usually aren't.
2. Each visible object gets a number (`mark`). Copies of the views with numbered badges are written to
   `<run_dir>/views/`. Badges sit on large objects and beside small ones (with a leader line), placed to hide as
   little as possible.
3. The JSON lists the visible objects, plus anything found since (seen after a walk, found by opening something,
   or put down), plus `rooms`, `body` (cylinder radius 0.25 m, height 1.7 m), `start`, current `position` and
   `holding`. It's printed compactly, one object per line, to stay under the Bash tool's 30 KB display limit.

**After each walk, a new view.** During an agent run, `run_episode.py` keeps one AI2-THOR open for the episode
(`src/motiongen/thor_render.py`, the render server). After every successful `mg goto` it is brought in line
with the world state (open doors open, carried things hidden, put-down things moved) and renders one ego view
from where the person stands, facing the target. The marked copy is `<run_dir>/views/walk_NN.png` and the
`goto` result gives its path as `image`. From then on `mg scene` counts it like the start views: objects it
shows are listed, with marks. Mark numbers never change during a run (`state["marks"]`); objects seen for the
first time get the next free number.
- Cost: about 11 s to start the server (once per run, before the agent starts) and about 0.3–0.5 s per view.
  A `goto` takes 3–5 s in all, mostly rebuilding the scene. Plus the agent's time to look at each image.
- Raw renders go to `<run_dir>/renders/walk_NN/` (outside `views/`, so their `objects.json` isn't readable to
  the agent). The server log is `render_server.log`.
- Without a GPU, or with `--no-rerender`, the run goes on with the start views only.

## 4. The agent and its tools (`agent/CLAUDE.md`, `src/motiongen/cli.py`, `world.py`)

`scripts/run_episode.py` starts `claude -p "Instruction: …"` with `agent/` as its working directory, so
`agent/CLAUDE.md` is its system prompt. It may only run `mg …` commands and Read its own view images; the
transcript is audited afterwards. Each `mg` call reads `MG_EPISODE` / `MG_RUN_DIR`, rebuilds the scene from the
current world state, acts, and saves `state.json`.

| command | what happens |
|---|---|
| `mg step "<text>"` | Names the next part of the plan ("get an egg from the fridge"). The walks and actions after it, until the next `mg step`, are tagged with it; they become one subtask in the motion hand-off (section 9). Doesn't count as an action. |
| `mg goto <id \| label \| x,y> [--then sit\|…]` | A* on a 2 cm grid, smoothed. Stops 0.2–0.7 m from an object, or within reach (1 m) of an object resting on or in something. Then the person **looks around**: anything within 3.5 m in line of sight (not through walls, not in a closed container) becomes visible and is returned as `seen`. With the render server running, also returns the new ego view as `image` (section 3). |
| `mg open / close <obj>` | Openable objects. Opening lists the contents. If the door swings over the person, they step back to the nearest free spot (a short leg with intent `stand`). |
| `mg pick <obj>` | Pickupable, within reach, free hand (2 hands). Whatever is in or on it comes along. |
| `mg place <held> <receptacle>` | Within reach, open if openable; or into a held container (an egg into a held bowl). On a surface it goes at the edge nearest the person; into a container at its centre. |
| `mg use <obj>` | Toggleable, closed if openable. Records everything in or on it (an egg in a bowl in the microwave). A faucet also counts the sink below it. |
| `mg submit [--infeasible "reason"]` | Ends the episode. |

Reach is 1.0 m (1.15 m when acting, as a smoothed route can end just short). Anything inside an openable container
is in reach wherever the container is. A label instead of an id picks the nearest visible match, preferring one in reach.

Nothing is simulated physically: objects change where they are (`placed`, `placed_at`, `held`) and whether
they're open; the planner sees open doors and carried objects at once. Only the views rendered after walks
show these changes; the start images stay as they were.

## 4b. The baseline: one plan, no feedback (`run_episode.py --condition baseline`)

The baseline is the comparison for the agent. It answers the question: **how much does acting step by step,
and seeing what happens, add over planning everything up front?** It uses the same model, the same scene
information and the same world rules; the only difference is that it gets no feedback.

How a baseline run works (`run_baseline` and `execute_plan` in `scripts/run_episode.py`):

1. **One prompt.** The baseline gets a single `claude -p` call. The prompt template is `agent/baseline_task_prompt.md`
   (long tasks; `agent/baseline_prompt.md` for the original navigation episodes). It contains the instruction, the
   rules of the actions (reach, two hands, open before placing inside, close a microwave before using it) and the
   **same scene JSON** that `mg scene` would print at the start (visible objects with marks, rooms, body, start).
   It may Read the same marked view images (up to 10 turns, only for reading them). It has no `mg` tools.
2. **One plan.** It must reply with a JSON plan and nothing else:
   ```json
   {"steps": [
     {"step": "get an egg", "candidates": ["fridge_1"], "actions": [["open", "fridge_1"], ["pick", "egg"], ["close", "fridge_1"]]},
     {"step": "put it on a plate", "candidates": ["plate_1"], "actions": [["pick", "plate_1"], ["place", "egg", "plate_1"]]},
     {"step": "sit down to eat", "candidates": ["chair_3", "dining_table_2"], "then": "sit"}]}
   ```
   or `{"infeasible": true, "reason": "..."}`. Each step lists walk targets in order of preference (ids, labels or
   `x,y`), an optional `then` intent, and actions to do on arrival. Labels let it name things it can't see yet
   ("pick egg" before the fridge has been opened). The optional `step` text plays the part of the agent's
   `mg step`: it becomes the subtask's name in the motion hand-off.
3. **Executed blindly** (`execute_task_plan`, with no model in the loop; no views are rendered after walks): for each step the person walks to the
   first candidate that has a route, using the same `world.goto`, then does the step's actions with the same
   `world.act`. The **first failure stops everything**: an unreachable step, or any action that fails (out of reach,
   hands full, nothing visible by that label). The run is then recorded as reported infeasible, with the failing
   step as the reason. A reply that isn't a usable plan counts as a failed run (`plan_error` in the summary).
4. **Scored identically**, with the same goals on the same `state.json`.

What the baseline can't do, and the agent can:
- **React.** If an action fails, it can't try something else. The agent reads each result and changes its plan.
- **Learn while acting.** It plans before any walk, so it never gets the `seen` lists (small things noticed up
  close) or the contents revealed by opening a container. It can only guess, by label, what's there.
- **Check the state.** It can't run `mg scene` again to see where things are now.

What the baseline is good for: when it succeeds, the task was solvable from the start information alone; when
the agent succeeds where the baseline fails, it's because of something learned or fixed along the way. In the
first long-task eval (`runs/eval_procthor_long_v1`, one run each) the baseline solved 11 of 19 tasks and the agent
18 of 19 (19 of 19 after re-running t05). The baseline's failures were mostly a step it couldn't do as planned:
- something out of reach from where the step ended, as when it tried to pick from the far end of a table;
- something too small to see at the start, so the label it named matched nothing;
- in the clear-table tasks, dishes left behind.

The baseline runs through the same audit as the agent; the only tool it may use is Read on its view images.

## 5. Outputs (`runs/<run>/`)

- **`state.json`**: the result.
  - `legs`: the walked route, one leg per walk:
    ```json
    {"target": "fridge_1", "intent": "open", "points": [[2.5, 1.5], [2.52, 1.60], ...],
     "end_heading": 28.5, "opened": [],
     "actions": [{"action": "open", "object": "fridge_1", "label": "fridge", "contents": ["egg_1", ...]},
                 {"action": "pick", "object": "egg_1", "label": "egg"}, ...]}
    ```
    `points` are about 10 cm apart in metres (scene frame, z-up); `end_heading` faces the target;
    `opened` is what stood open while it was walked; `actions` are done where the leg ends, in order.
    `target`, `intent`, `points` and `end_heading` are the original leg format; `actions` and `opened` were
    added. The motion hand-off (`motion/`, section 9) is built from the legs and events.
  - `events`: every walk and action in order, with the position, for scoring. Each carries `step`, the subtask
    it belongs to, when the agent named one; `{"action": "step", "id": 2, "text": ...}` events mark the starts.
  - `steps`: the subtasks named with `mg step`.
  - The final world: `held`, `opened`, `closed`, `placed`, `placed_at`, `revealed`, `seen`.
  - `views` (the walk renders, with how long each took), `marks` (object id → badge number), `render_errors`.
- **`route.png`**: the floor plan with the route.
- **`motion/`**: the motion hand-off, written at the end of every run (section 9).
- **`transcript.jsonl`**: the agent's full session. **`summary.json`**: metrics, audit, the agent's last reply,
  `episode_path`, and `rerender` (server start-up seconds, number of walk views, seconds spent rendering).
- **`views/`** (marked images the agent saw), **`renders/`** (raw walk renders), **`render_server.log`**.

## 6. Scoring (`src/motiongen/metrics.py`, `goals.py`)

An episode is scored by whichever of these it has:

- **nothing** (a task given only as text): no score. `success` is `null`; route length, collisions and action
  count are still reported.
- **`goals`** (long tasks). Labels match any object with that label; a list means any of them:
  ```yaml
  goals:
    events:                       # must happen (checked against the event log)
      - {id: got_egg, pick: egg}
      - {id: cooked,  use: microwave, containing: egg}     # containing: all of these; [[a, b]] = a or b
      - {id: ate,     goto: [dining_table_2, chair_3], intent: sit}
      #   also: {place: [X, Y]}, {open: X}, {close: X}
    order: [[got_egg, cooked], [cooked, ate]]             # first must happen before second
    final:                        # must hold at the end; in/on/off follow stacking (cup in bowl on counter)
      - {in: [egg, [bowl, plate, pot, pan]]}
      - {on: [[bowl, plate, pot, pan], dining_table_2]}
      - {closed: fridge}
      - {holding: nothing}
      #   also: {off: [X, Y]}, {near: [X, Y], within: 1.5}, {open: X}, {at: X}
  ```
  Reported: `success` (all events, all orderings, all final facts, no collision, not reported infeasible),
  `goal_fraction`, `events_missing`, `order_violations`, `final_failed`.
- **`stops`** (the original navigation episodes): each walk must arrive at the stops in order.
- **`expect_infeasible: true`**: success means reporting it infeasible.

Collisions are checked leg by leg against the doors open at the time.

## 7. Running your own task

### a. Just the text: `scripts/do_task.py`
```bash
python scripts/do_task.py --house 2927 --start 2.5,1.5 "Make me a coffee and bring it to the bedroom desk."
#   options: --heading 90  --model sonnet  --condition baseline  --no-rerender
```
It exports the house if needed, moves the start to free floor if it isn't (up to 1.5 m), writes
`episodes/tasks/<time>_<words>.yaml`, renders the views, runs the agent (with a new view after each walk), and
prints the subtasks with their motion segments, the timings (start views, run, render server, walk views) and
where `motion/` is. Unscored. To pick a start, open `scenes/procthor/train_<n>/views/top/rgb.png` or draw the map:
```python
from motiongen.scene import Scene; from motiongen.render_map import render_map
render_map(Scene.load("scenes/procthor/train_2927/scene.yaml"), [2.5, 1.5]).save("map.png")   # grid in metres
```

### b. Your own episode, with a score
1. Export the house (section 1) and look at `scene.yaml` for the ids you need.
2. Write `episodes/mine/<id>.yaml` with the fields of section 2 and `goals` from section 6.
   Check the start is free floor: `Scene.load(...).clearance_at(x, y) >= 0.25`.
3. `python scripts/export_procthor.py views episodes/mine/<id>.yaml` and paste the printed `views:` list in.
4. `python scripts/run_episode.py episodes/mine/<id>.yaml --condition agent` (or `baseline`).

To check your goals before spending a run, script a solution and score it:
```python
from motiongen import world; from motiongen.goals import score_goals
from motiongen.navigation import load_episode, new_state
ep = load_episode("episodes/mine/x.yaml"); st = world.world(new_state(ep))
world.goto(ep, st, "fridge_1"); world.act(ep, st, "open", "fridge_1"); ...   # one call per step
print(score_goals(ep, st))
```

### c. Many tasks: `scripts/make_tasks.py`
Add an entry to `TASKS` (house, family, start room, ids) or a new family function, then
`python scripts/make_tasks.py --views`. It picks the most open spot in the start room, checks your reference
solution against the goals, renders the views and writes `episodes/procthor_long/`.

### d. Comparing agent and baseline
```bash
python scripts/run_eval.py --name mine_v1 --episodes episodes/mine --repeats 3
```
Resumable; stops cleanly on a failed Claude call (a usage limit) so a re-run continues. Success per episode and
category, mean goal fraction, audit violations; per-run folders under `runs/eval_mine_v1/`. `--no-rerender` gives
the agent only the start views, for comparing with the re-rendered runs.

Both conditions run on every episode; section 4b explains the baseline. To run it on one episode:
`python scripts/run_episode.py <episode.yaml> --condition baseline`, or `do_task.py ... --condition baseline`.

---

## 8. Known limits

- Views are re-rendered only after walks, facing the target; not after opening, picking or stepping back.
  Up-close seeing is still also a 3.5 m radius rule (`seen`), which catches things too small for the renders.
- Runs before the re-rendering and `mg step` (`eval_procthor_long_v1`) have neither; their motion scripts use
  derived subtasks.
- Interaction is symbolic: no grasps, no physics, no object states beyond place/open/used.
- AABB boxes: tilted or curved things are approximated by boxes (or footprint rectangles for big ones).
- Results so far (`runs/eval_procthor_long_v1`): agent 18/19 (19/19 after re-running t05), baseline 11/19, one run each, on tasks that were
  adjusted after seeing earlier failures.

---

## 9. The motion hand-off (`motion/`, `src/motiongen/motion_script.py`)

At the end of every run, `run_episode.py` turns `state.json` into the input for motion generation, in
`<run_dir>/motion/`. For runs made earlier: `python scripts/export_motion.py <run_dir> [...]` (no GPU, no Claude).

```
motion/
  motion_script.json    the task as subtasks → motion segments, plus an object timeline
  walks/walk_NN.json    one task file per walk, in the format of the partner's walking code
  route_motion.png      the map: route coloured by subtask, every motion labelled where it happens
```

**Subtasks.** The agent names them with `mg step "..."` (the baseline with a `step` text per plan step). Where a
run has none, each walk and the actions after it form one subtask with a templated text ("walk to the fridge,
open the fridge, pick up 2 eggs, close the fridge"), marked `"source": "derived"`.

**Segments**, in order, each one motion:

| motion | from | fields besides `i`, `subtask`, `duration_est`, `t_est`, `caption` |
|---|---|---|
| `walk` | a leg | `target`, `from`, `to`, `path` (the leg's points), `length`, `end_heading`, `carrying` (`{hand: id}`), `rooms` crossed, `narrow` stretches, `partner_task` |
| `turn` | heading change on the spot | `at`, `from_heading`, `to_heading`, `angle` (+ = left) |
| `step_back` | the leg `world.step_back` adds when a door swings over the person | `object`, `from`, `to`, `path`, `facing` |
| `open`, `close`, `use` | the actions | `object`, `hand`, `contact` [x, y, z] (nearest side of the box at handle height, about 1 m), `height`, `at` |
| `reach_grasp` | `pick` | `object`, `hand`, `contact` (object centre), `height` |
| `put_down` | `place` | `object`, `receptacle`, `relation` (`in`/`on`), `hand`, `contact` (where it goes), `into_held` (into a container in the other hand) |
| `sit_down` / `stand_up` | `goto --then sit` / the next walk | `object`, `seat` [x, y, height] |

- **Turns** are added wherever the person must turn on the spot: before a walk, to face along its first piece
  (more than 15°), and before an action whose object is more than 45° to the side.
- **Hands:** the first free hand is right, then left; putting something down frees its hand; a container's
  contents travel in its hand. Opening with both hands full is marked `hands_full`.
- **`narrow`:** stretches where the nearest obstacle is closer than 0.315 m to the path, half the partner body's
  width with swinging arms. Their code turns the shoulders or side-steps there. Our planner only guarantees 0.25 m.
- **Timing** is our estimate (walk 1.2 m/s, 1.0 m/s carrying, plus 0.8 s to start and 1.0 s to stop; turn
  0.6 s + 0.9 s per 90°; open 1.5 s, close, pick and put 1.2 s, use 1.0 s, sit 2.0 s). `t_est` adds them up.
  The motion side has the final say: the object timeline refers to segment numbers, not times.

**Object timeline** (`objects`): `open` / `close` / `switched_on` (with contents) / `attach` (picked up, with the
hand) / `detach` (put down: where to, `in`/`on`, and its new centre), each with the segment where it happens.
Everything a later video needs to move the objects with the hands.

**Frames.** Ours: z up, floor `[x, y]`, heading counter-clockwise from +x. The partner's: y up, floor `[X, Z] =
[x, -y]`, heading 0 facing +Z and 90 facing +X, so `heading_deg = heading + 90`. Both stay right-handed, and turning
left raises the heading in both. AI2-THOR: position `{x: x, y: z, z: y}`, yaw `90 - heading`. All three are written in
the script's `frame`.

**Walk task files** (`walks/walk_NN.json`, one per `walk` segment) follow the partner's task format
(Jankula/motion-gen, `walking/tasks/*.json`) and load with their `walkenv.tasks.load_task`:
- standing start at the leg's first point, facing along the first piece of path; standing end at its last
  point, facing the target (their code turns on the spot at the end);
- `path.points`: the leg simplified to its corners (Douglas–Peucker, 3 cm, kept clear of obstacles), tolerance 0.15 m;
- `obstacles`: every box that blocks the body within 1 m of the path (furniture, walls; footprint objects as
  one box per rectangle), standing on the floor with their top as height;
- `frames`: the estimated duration plus 1.5 s of standing, at 30 fps;
- an `instruction` in their style, and `source` (our episode and segment).

`docs/motion_handoff.md` is written for the partner: the files, how to run the walks with their code, what the
segments ask of the motion side, and what their code can't do yet.
