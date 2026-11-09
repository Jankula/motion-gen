# The pipeline, step by step

How one sentence turns into a walked, acted-out plan and into input for the SMPL-X motion code. Every stage
says what goes in, what comes out, which code does it and where the files land. The examples are real outputs
of task **t01** in house 2927 ("Make me scrambled eggs, serve them at the kitchen table, and sit down there to
eat. Leave the kitchen tidy."), from `runs/eval_procthor_long_v1/t01_breakfast_2927__agent__0`.

How to run it: [../README.md](../README.md). Every field in full: [pipeline.md](pipeline.md). For the SMPL-X
side: [motion_handoff.md](motion_handoff.md).

```
 ┌─────────────────────────── once per house (GPU) ────────────────────────────┐
 │ ProcTHOR-10K house ──AI2-THOR──▶ scene.yaml (rooms, boxes) + top image        │
 └──────────────────────────────────────────────────────────────────────────────┘
 ┌─────────────────────────── once per task (GPU) ─────────────────────────────┐
 │ instruction + start ──▶ episode.yaml ──AI2-THOR──▶ 5 start images             │
 └──────────────────────────────────────────────────────────────────────────────┘
 ┌─────────────────────────── the run ─────────────────────────────────────────┐
 │ claude -p (agent/CLAUDE.md)                                                   │
 │    │  mg scene / step / goto / open / pick / place / use / submit             │
 │    ▼                                                                          │
 │ symbolic world (world.py) ──▶ state.json        path planner (navigation.py)  │
 │    │ after each walk                                                          │
 │    ▼                                                                          │
 │ render server (one AI2-THOR, GPU) ──▶ new ego image ──▶ back to the agent      │
 └──────────────────────────────────────────────────────────────────────────────┘
 ┌─────────────────────────── after the run (no GPU) ──────────────────────────┐
 │ summary.json (audit, score) · route.png                                      │
 │ motion/: motion_script.json · walks/walk_NN.json · route_motion.png           │
 └──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼   partner: make_motion.py walk_NN.json → SMPL-X clip
```

Coordinates throughout are **z up**: the floor is `[x, y]` in metres, and heading is in degrees
counter-clockwise from +x.

---

## Stage 1: the house (`scripts/export_procthor.py scene`, once per house)

**In:** a ProcTHOR-10K index (here `train 2927`). **Needs:** GPU (AI2-THOR, headless `--platform cloud`).

AI2-THOR loads the house and closes every door and drawer. Then every object is read out as an axis-aligned box.

**Out:** `scenes/procthor/train_2927/`
- `scene.yaml`: the house as everything after this stage sees it. An object looks like this:
  ```yaml
  - id: fridge_1          # label + number, stable for this house
    label: fridge
    color: darkslategray
    center: [6.119, 7.055, 0.941]   # metres, z up
    size: [1.082, 0.779, 1.883]
    thor_id: Fridge|6|1   # AI2-THOR's id, used only for rendering
    receptacle: true
    openable: true
    open_box: ...         # space it fills when open, including the door swing
  - id: egg_1
    label: egg
    center: [6.462, 7.242, 0.741]
    size: [0.053, 0.053, 0.074]
    pickupable: true
    inside: fridge_1      # or supported_by: <surface>
  ```
  It also holds:
  - rooms as floor polygons (`kitchen_1`, `bedroom_1`, …);
  - walls as thin boxes, cut open at doorways;
  - `footprint` rectangles for big hollow shapes such as L-shaped counters.
- `views/top/`: an image from above (`rgb.png`), plus which object each pixel shows (`ids.png`, `objects.json`).

**Free floor:** `scene.py` builds a 2 cm grid of how far each point is from the nearest obstacle. The person is
a cylinder (radius 0.25 m, height 1.7 m), and it may stand wherever that distance is ≥ 0.25 m. Things lower
than the body's reach (a rug) or hanging above it don't block.

The world has no physics. "Open", "held" and "on the plate" are only facts in the state.

---

## Stage 2: the episode (`episodes/.../<id>.yaml`, once per task)

**In:** instruction, house, start. `do_task.py` writes it for you to `episodes/tasks/<time>_<words>.yaml`.
The 19 eval tasks are in `episodes/procthor_long/`.

```yaml
id: t01_breakfast_2927
scene: scenes/procthor/train_2927/scene.yaml
instruction: Make me scrambled eggs, serve them at the kitchen table, and sit down there to eat. Leave the kitchen tidy.
start: [3.83, 10.59]
heading: 0
max_walks: 20
max_actions: 40
views: [...]          # the five start images, filled in by the views export
goals: {...}          # only in eval tasks, for scoring (stage 6); do_task episodes have none
```

**Start images** (`export_procthor.py views`, GPU, ~15–20 s): from the start position, one top view and four
first-person views (front, left, back, right, 90° apart, at eye height). They are saved in
`scenes/procthor/train_2927/views/<episode>_{top,ego_front,ego_left,ego_back,ego_right}/`. Each holds
`rgb.png`, `ids.png` (per-pixel object), `objects.json` and `camera.json`. The id image tells which objects are
visible; that controls what the agent is allowed to know.

---

## Stage 3: the agent run (`scripts/run_episode.py`)

### How Claude is started
- `claude -p "Instruction: <instruction>"`, model `sonnet` by default.
- Working directory is `agent/`, so **`agent/CLAUDE.md` is its entire task description**: the tools, the rules,
  the method.
- Allowed: only `Bash(mg:*)`, and `Read` on `<run>/views/**` (its own images). No MCP, no saved session, no API key.
- Limits:
  - tasks with goals: 900 s and 80 turns;
  - `do_task` tasks: 300 s and 25 turns;
  - walks and actions: from the episode (20 and 40).
- Environment: `MG_EPISODE` and `MG_RUN_DIR` tell every `mg` call which episode and run folder to use.
- Before Claude starts, the **render server** starts (stage 4; about 11 s).

### What the agent knows at the start: `mg scene`
`mg scene` (`observe.py`) prints JSON:
- the room bounds, `rooms` (polygons), `body`, `start`, the current `position`, and `holding`;
- `objects`: **only those visible in the images** (≥ 80 pixels in some view), plus what it found later. One line
  per object:
  ```json
  {"id":"fridge_1","label":"fridge","color":"darkslategray","center":[6.119,7.055,0.941],"size":[1.082,0.779,1.883],
   "blocks_body":true,"supported_by":null,"room":"kitchen_1","openable":true,"is_open":false,"mark":45}
  ```
  `mark` is the number of the badge drawn on that object in the images.
- `images`: paths to marked copies of the views in `<run>/views/`. The agent opens these with Read and sees the
  house, with numbered badges on objects.

Not shown: things inside closed containers (the eggs in the fridge), and objects too small to see from the start.

### What it does: the t01 transcript, shortened
```
mg scene                                  → objects, rooms, images
Read views/t01_breakfast_2927_top.png      (+ the ego images)
mg goto fridge_1 --then open              → {"reached":true,"position":[4.93,6.41],"leg_length":5.87,
                                             "seen":[dog_bed_1, fridge_1, garbage_bag_1, stool_1],"attempts_left":19}
mg open fridge_1                          → {"done":true,"contents":[egg_1, egg_2, egg_3, potato_1, tomato_1]}
mg pick egg_1 ; mg pick egg_2             → {"holding":["egg_1","egg_2"]}
mg close fridge_1
mg goto plate_1 --then place              → reached, 7.49 m, seen: bread, coffee machine, counter top, …
mg place egg_1 plate_1 ; mg place egg_2 plate_1 ; mg pick plate_1
mg goto microwave_1 --then open           → already there (0 m)
mg open microwave_1 ; mg place plate_1 microwave_1 ; mg close microwave_1
mg use microwave_1                        → {"used":"microwave_1","contents":["egg_1","egg_2","plate_1"]}
mg open microwave_1 ; mg pick plate_1 ; mg close microwave_1
mg goto dining_table_2 --then place ; mg place plate_1 dining_table_2
mg goto chair_8 --then sit
mg submit                                 → {"submitted":true}
```
New runs also have `mg step "…"` lines that name each part of the plan, and every `goto` result gets an `"image"`.
The agent ends with one sentence on what happened.

### What each tool does (`cli.py` → `world.py`)
Every `mg` call:
1. loads `state.json`;
2. rebuilds the scene with the current state (open doors take floor space, held things are gone from it);
3. acts;
4. saves `state.json` again.

| command | rules |
|---|---|
| `mg step "text"` | Starts a new subtask; everything after it is tagged with its number. Not counted as an action. |
| `mg goto <id\|label\|x,y> [--then intent]` | A* path on the free-floor grid, smoothed. It stops 0.2–0.7 m from the object, or within 1 m reach of something resting on it. Then it **looks around**: objects within 3.5 m in line of sight (not through walls, not in closed containers) become known and are returned as `seen`. A failed route leaves the person where they are and uses up one attempt. |
| `mg open` / `close` | Openable things within reach. Opening reveals the contents. If the door swings over the person, they step back (a short extra leg). |
| `mg pick` | Pickupable, within reach (1.0 m, 1.15 m when acting), with a free hand (2 hands). The contents come along. |
| `mg place <held> <target>` | Target within reach and open, or a container in the other hand. On a surface, it goes on the edge nearest the person. |
| `mg use` | Toggleable, closed if openable. Records what is inside (that is what "cooked" means). |
| `mg submit [--infeasible "why"]` | Ends the run. |

A label such as `egg` instead of an id picks the nearest visible match.

---

## Stage 4: a new image after every walk (`src/motiongen/thor_render.py`, `observe.py`)

One AI2-THOR process stays open for the whole run. It talks to `mg` over a local port, written in
`<run>/render.port`.

After each successful `mg goto`:
1. `mg` sends the server the current world: position, heading (facing the target), what is open, what is held
   (hidden), and what was moved (new positions).
2. The server makes the simulator match. It opens doors, removes carried objects, and teleports placed ones.
   Then it renders one first-person view, in about 0.4 s.
3. The raw view goes to `<run>/renders/walk_NN/`, and a marked copy to `<run>/views/walk_NN.png`.
   `goto` returns that path as `image`.
4. From now on `mg scene` counts this view like the start views. Its objects are listed, with badges. A badge
   number never changes during a run (`state["marks"]`); new objects get the next free numbers.

If there is no GPU, or with `--no-rerender`, the agent works from the start images only. Server log:
`<run>/render_server.log`.

---

## Stage 5: the result (`runs/<run>/`)

When Claude finishes, `run_episode.py` writes:

| file | contents |
|---|---|
| `transcript.jsonl` | the full session: every message, tool call and result |
| `state.json` | the world at the end, and its history (below) |
| `summary.json` | time, tool calls, tokens, audit, score, final reply, re-render timings |
| `route.png` | floor plan with the walked route |
| `views/`, `renders/` | images the agent saw, raw renders |
| `stderr.txt`, `render_server.log` | logs |

**`state.json`:**
- `legs`: one per walk. This is the original hand-off format:
  ```json
  {"target": "fridge_1", "intent": "open", "points": [[3.83, 10.59], [3.80, 10.49], ...],
   "end_heading": 28.5, "opened": [], "step": 1,
   "actions": [{"action": "open", "object": "fridge_1", "contents": ["egg_1", ...]},
               {"action": "pick", "object": "egg_1"}, ...]}
  ```
  `points` are about every 10 cm, `end_heading` faces the target, and `actions` happen at the leg's end.
- `events`: every walk and action in order, with the position and subtask.
- `steps`: the named subtasks.
- The final world: `held`, `opened`, `placed` and `placed_at`, `revealed`, `seen`, `views`, `marks`.

**Audit:** the transcript is checked so that every tool call was an allowed `mg` command or a Read of its own
images. Anything else counts as a violation (`audit_clean: false`).

---

## Stage 6: scoring (`goals.py`, `metrics.py`), only for episodes with goals

Goals in t01:
- **events that must happen:** pick an egg; use the microwave with an egg inside; go to the table or a chair
  with intent sit;
- **order:** pick, then cook, then sit;
- **final facts:** egg in a bowl or plate; that dish on `dining_table_2`; fridge and microwave closed; holding
  nothing.

`success` needs all of these, with no collision and not reported infeasible. `goal_fraction` gives the partial
score. Tasks from `do_task.py` have no goals, so `success` is `null`; route length and collisions are still reported.

**Baseline** (`--condition baseline`): same model, same scene JSON and images, but a single call that must
return the whole plan as JSON. The plan is then carried out blindly with the same world rules, and the first
failure stops it. It shows how much the agent gains from feedback. In eval v1: agent 18/19 (19/19 after re-running t05), baseline 11/19.

---

## Stage 7: the motion hand-off (`src/motiongen/motion_script.py`, no GPU)

At the end of every run, `state.json` is turned into `runs/<run>/motion/`. For older runs:
`python scripts/export_motion.py <run>`.

### `motion_script.json`
- **`subtasks`**: named by the agent with `mg step`, or derived one per walk:
  ```json
  {"id": 1, "text": "walk to the fridge, open the fridge, pick up 2 eggs, close the fridge",
   "source": "derived", "segments": [0, 1, 2, 3, 4, 5]}
  ```
- **`segments`**: the whole task as a list of single body motions. Each has an estimated duration, start and end
  time (`t_est`) and a caption:
  ```json
  {"i": 0, "motion": "turn", "at": [3.83, 10.59], "from_heading": 0.0, "to_heading": -104.0, "duration_est": 1.64,
   "caption": "a person turns on the spot 104 degrees to the right to set off", "subtask": 1}
  {"i": 1, "motion": "walk", "target": "fridge_1", "from": [3.83, 10.59], "to": [4.93, 6.41], "length": 5.87,
   "end_heading": 28.5, "carrying": {}, "rooms": ["bedroom_1", "living_room_1", "kitchen_1"], "narrow": [],
   "partner_task": "walks/walk_01.json", "caption": "a person walks from the bedroom into the kitchen to the fridge"}
  {"i": 2, "motion": "open", "object": "fridge_1", "hand": "right", "contact": [5.578, 6.665, 1.0], "height": 1.0,
   "at": [4.93, 6.41], "revealed": ["egg_1", "egg_2", "egg_3", "potato_1", "tomato_1"], "caption": "a person opens the fridge with the right hand"}
  ```
  Motion types: `walk`, `turn`, `step_back`, `open`, `close`, `reach_grasp`, `put_down`, `use`, `sit_down`,
  `stand_up`. How they are made:
  - **turns** are added before a walk when its direction differs from the facing by more than 15°, and before
    an action whose object is more than 45° to the side;
  - **hands:** right first, then left; putting something down frees its hand;
  - **`contact`** is where the hand goes: the object's centre for a pick, the handle side at about 1 m for doors;
  - **`narrow`** marks stretches where an obstacle is closer than 0.315 m;
  - **timings** are estimates: 1.2 m/s walking, 1.0 m/s carrying, 1.5 s to open, and so on.
- **`objects`**: what happens to objects, tied to segment numbers, not times:
  ```json
  {"segment": 2, "object": "fridge_1", "change": "open"}
  {"segment": 3, "object": "egg_1", "change": "attach", "hand": "right"}
  {"segment": 4, "object": "egg_2", "change": "attach", "hand": "left"}
  ```
- **`frame`**: the coordinate conversions, and `house`, so a later video can load the same scene.

### `walks/walk_NN.json`: input for the partner's walking code
One file per walk segment, in their task format (Jankula/motion-gen `walking/tasks/`), already converted to their
frame (**Y up, `[X, Z] = [x, -y]`, heading + 90°**):
```json
{"name": "t01-breakfast-2927-walk-01", "title": "Walk to the fridge",
 "instruction": "One adult stands still for a moment, then walks along the marked path from the bedroom into the kitchen, 5.9 m, to the fridge. At the end ... turn on the spot about 21 degrees to the left to face the fridge ...",
 "fps": 30, "frames": 270,
 "start": {"state": "standing", "position": [3.83, -10.59], "heading_deg": -14.0},
 "end":   {"state": "standing", "position": [4.93, -6.41], "heading_deg": 118.5},
 "path": {"points": [[3.83, -10.59], [3.098, -7.659], [3.08, -7.458], ...], "tolerance_m": 0.15},
 "obstacles": [{"label": "wall_5", "center": [5.603, -7.47], "size": [3.735, 3.205, 0.1], "yaw_deg": 0}, ...],
 "source": {"episode": "t01_breakfast_2927", "segment": 1, "expected_seconds": 7.5}}
```
- `path.points`: the route reduced to its corners (within 3 cm).
- `obstacles`: walls and furniture within 1 m of the path.
- `frames`: our time estimate plus 1.5 s.

The partner runs `python make_motion.py walk_01.json walk_01.npz`, which gives one SMPL-X clip. All 226 walk
files from the saved runs load with their loader.

### `route_motion.png`
The floor plan with each walk coloured by subtask and numbered. It also shows turns as arcs, narrow stretches
dashed, step-backs in grey, a label at every action, and a legend of subtasks.

---

## What's next (not built yet)
- **Actions:** the partner's code only walks for now. Turning before walking, carrying, reaching, opening and
  sitting are listed as requests in [motion_handoff.md](motion_handoff.md). Until then, those segments are standing holds.
- **Final video:**
  1. generate a clip per walk;
  2. re-time the script with the real clip lengths;
  3. join the clips with the action segments in between;
  4. move the objects using the object timeline;
  5. render the SMPL-X body in the house.

## Where the code is

| file | role |
|---|---|
| `scripts/do_task.py` | one task from text: episode → start images → run → printout |
| `scripts/run_episode.py` | starts Claude (or the baseline) and the render server; writes the run folder; audit, score, motion export |
| `scripts/run_eval.py` | agent vs. baseline over a folder of episodes |
| `scripts/export_procthor.py` | stage 1 (house) and stage 2 (start images) |
| `scripts/export_motion.py` | stage 7 for existing runs |
| `scripts/make_tasks.py`, `find_houses.py` | building the eval tasks, finding suitable houses |
| `agent/CLAUDE.md` | the agent's instructions; `agent/baseline_*.md` for the baseline |
| `src/motiongen/scene.py` | boxes, rooms, free-floor grid |
| `src/motiongen/navigation.py`, `path_check.py` | path planning, collision checks |
| `src/motiongen/world.py` | world state and action rules |
| `src/motiongen/cli.py` | the `mg` commands |
| `src/motiongen/observe.py` | what `mg scene` shows, badges, images after walks |
| `src/motiongen/thor_render.py` | AI2-THOR helpers and the render server |
| `src/motiongen/goals.py`, `metrics.py` | scoring |
| `src/motiongen/motion_script.py`, `render_map.py` | motion hand-off, maps |
