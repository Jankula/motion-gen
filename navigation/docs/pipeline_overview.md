# Pipeline overview

A short version to present from. Each section is roughly one slide. Details: [README_pipeline.md](README_pipeline.md).

---

## 1. The goal

**Input:** a sentence and a house, for example *"Make me scrambled eggs and sit down to eat"* in a ProcTHOR house.

**Output:** a plan a human body can act out. It is split into subtasks, every walk and hand action is placed in
the house, and the walks are already in the format the SMPL-X motion generator takes.

**End goal (later):** a video of an SMPL-X person doing the whole task in the house.

---

## 2. The pipeline in 4 steps

```
 1. HOUSE            2. TASK                 3. AGENT                     4. MOTION HAND-OFF
 ProcTHOR house  →   sentence + start   →    Claude plans and acts   →    subtasks + motion segments
 → boxes, rooms      → start images          with tools, step by step     + walk files for SMPL-X
 (AI2-THOR)          (AI2-THOR)              sees a new image per walk    (partner's code)
```

1. **House:** AI2-THOR loads a ProcTHOR house. We save every object as a labelled 3D box, plus the room
   outlines. This gives a simple, fast "symbolic world": no physics.
2. **Task:** the instruction and a start position. We render 5 images from the start (4 directions + from above).
3. **Agent:** Claude gets only the instruction and a small set of tools. It looks at the images, plans, and
   carries the task out step by step, checking each result.
4. **Motion hand-off:** the finished run is turned into a sequence of body motions, ready for motion generation.

---

## 3. What the agent sees and can do

**It sees:**
- images of the house with numbered badges on the objects;
- a list of only the objects visible in those images. Hidden things, such as eggs inside the fridge, must be
  found by opening;
- **new:** after every walk, a fresh image of what the person now sees, with opened doors and moved objects.

**It can do:**

| tool | meaning |
|---|---|
| `mg step "…"` | name the next subtask ("take eggs from the fridge") |
| `mg goto fridge --then open` | walk there; a path planner finds a collision-free route |
| `mg open / close / pick / place / use` | act on objects within reach; 2 hands |
| `mg submit` | done, or `--infeasible "why"` |

**Rules make it realistic:**
- 1 m reach and two hands;
- you must open before taking out, and close a microwave before using it;
- the person is a 0.25 m cylinder, so a route needs space.

---

## 4. Agent vs. baseline (the experiment)

- **Agent:** acts step by step, sees every result, and can react to surprises.
- **Baseline:** same model, same information, but it must write the **whole plan up front** in one answer. The
  plan is then executed blindly, and the first failure stops it.

So the comparison asks: *what does feedback while acting add?*

---

## 5. Results

**Long household tasks:** 19 tasks in 7 houses (breakfast, coffee, toast, salad, laundry, clearing the table, plus
2 impossible ones), 1 run each.

| | baseline | agent |
|---|---|---|
| tasks solved | **11 / 19** | **18 / 19** |
| mean fraction of goals reached | 0.70 | 0.99 |
| planning time per task (median) | ~21 s | ~51 s |

(Source: `runs/eval_procthor_long_v1.log`. The agent's one failure, t05 breakfast, was re-run afterwards and
succeeded; its saved runs now show 19/19.)

By category (baseline → agent):
- clear the table 0/2 → 2/2;
- salad 1/3 → 3/3;
- toast 1/3 → 3/3;
- coffee 2/3 → 3/3;
- breakfast 4/5 → 4/5;
- laundry 1/1 → 1/1;
- impossible tasks 2/2 → 2/2: both correctly reported them as impossible.

**Why the baseline fails:**
- something was out of reach from where it stopped;
- a small object wasn't visible at the start, so its plan named something that wasn't there;
- it left dishes behind.

The agent fixes all three by looking and reacting.

**Short navigation tasks** (10 tasks × 3 runs): both conditions solved all of them. These were too easy to
separate the two, which is why we built the long tasks. (That eval flagged tool-use violations in 4 episodes;
the long-task eval had none.)

---

## 6. Example run (the eggs task, with re-rendering)

`do_task.py --house 2927 --start 2.5,1.5 "Make me scrambled eggs and sit down to eat."`

**Subtasks the agent named itself:**
1. find eggs in the fridge
2. take eggs from the fridge
3. cook the eggs on the plate in the microwave
4. take the cooked eggs to the dining table and sit

**Numbers:**
- 31 tool calls, 5 walks (17.8 m), 15 actions;
- collision-free, and it used only the allowed tools;
- 98 s in total: render server start 11.5 s, 5 new images in 2.7 s;
- the result is 22 motion segments, about 48 s of estimated body motion.

**The agent explains its own limits:** "the microwave only switches on, so the eggs were heated whole, not
scrambled".

Good slides: `route.png` (the route), `motion/route_motion.png` (subtasks and motions on the map), and one
image from `views/` with badges.

---

## 7. The motion hand-off

From each run, `motion/` is written:
- **`motion_script.json`:**
  - subtasks → motion segments: walk, turn, step back, open, close, grasp, put down, switch on, sit down,
    stand up;
  - each segment has a position, hand, contact point, estimated duration and caption;
  - an object timeline says which segment picks up or puts down what. That is needed for the video later.
- **`walks/walk_NN.json`:** one file per walk in the partner's format (start, end, path, nearby obstacles).
  It feeds straight into their SMPL-X walking generator. All 226 walk files from the saved runs load correctly.
- **`route_motion.png`:** the whole plan drawn on the map.

---

## 8. What the body needs that doesn't exist yet

Counted from the 19 agent runs:
- 73 walks;
- 74 turns on the spot;
- 49 pick-ups and 46 put-downs;
- 19 opens and 19 closes;
- 13 switch-ons;
- 6 sit-downs.

The partner's generator can only walk so far. Missing, in order of need:
1. **turning before walking:** the median turn is 115°;
2. walking while carrying;
3. reaching and grasping: the median reach is 1.07 m, often too far, so a step or a lean is needed;
4. opening and closing doors;
5. sitting down and standing up.

---

## 9. Limits and next steps

**Limits:**
- symbolic world: no physics or grasp simulation, and objects are boxes;
- small evaluation: 1 run per long task, and the tasks were adjusted during development;
- images are re-rendered only after walks, not after every action.

**Next:**
- re-run the long-task eval with the new features (re-rendering and named subtasks);
- partner: the motions above;
- join the clips and render the final SMPL-X video in the house.
