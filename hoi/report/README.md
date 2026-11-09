# Teaching an AI agent to animate a person handling objects: experiment report

*Last updated: 2026-11-05*

## What this project is about

This is the sequel to the [walking experiments](../../walking/report/README.md). There, an AI agent learned to make a 3D human body walk, turn and squeeze through a gap, using only what it knows and no recordings of real motion. Here, the same kind of agent has to make the person **do something with an object**: pick it up, carry it and put it down.

The agent is a large language model that writes and runs its own code (Claude Code with Claude Opus 5.5). The body is SMPL-X, a standard 3D human body model used in computer vision and graphics research. For each experiment, we describe a task in words. The agent writes a program that computes the body's pose and the object's position for every frame. We turn the result into videos from eight cameras and measure it on the body's surface: do the hands really touch the object, does it behave like a real object, does the person keep their balance with the extra weight.

The question is **how good and how fast a fully agentic approach is** on human-object interaction, with any method the agent can build itself.

## How to read this report

1. **This page** gives the overview and the list of experiments.
2. **[How an experiment works](01-setup.md)** explains what is different from the walking experiments.
3. **[How results are measured](02-measurements.md)** explains every measurement and its target.
4. **[Glossary](glossary.md)** explains the terms for handling objects. Walking terms are in the [walking glossary](../../walking/report/glossary.md).
5. **One page per experiment** in [`experiments/`](experiments/), all with the same structure: summary, task, what the agent did, results with videos and measurements, problems, conclusion.

**One name for everything.** Each experiment has an ID such as `H01-box-carry`, and that ID is the name of:

- its report page: `report/experiments/H01-box-carry.md`
- its folder, with everything the agent saw and produced: `runs/H01-box-carry/`
- its videos: `runs/H01-box-carry/videos/` (start with `grid.mp4`, which shows all eight cameras at once)

## Experiments

| ID | Date | Task | Started from | Agent had | Result | Session | Report | Main video |
|---|---|---|---|---|---|---|---|---|
| H01 | 2026-11-04 | Walk to a 10 kg box, pick it up, carry it about 3 m, set it down carefully on a marked spot, stand up; 20 s | E04 | measuring + preview tools | Convincing sequence; bends knees and hips and leans back without being told; 38/38 targets, also 38/38 on an unseen layout; 4 s to compute. Weak point: flat, unrealistic grip | 99 min (interrupted once by the usage limit, resumed), $16.74 | [H01](experiments/H01-box-carry.md) | [grid.mp4](../runs/H01-box-carry/videos/grid.mp4) |
| H02 | 2026-11-05 | Juggle three balls, go on juggling on one foot, catch them all, put the foot down; 20 s | H01 | measuring + preview tools | 45 throws without a drop, exact free fall, 9.7 s on one foot, hands that cup the balls; 48/48 targets, 47/48 on an unseen task; 2 s to compute. Weak point: too tidy, reactions scripted | 74 min, $11.33 | [H02](experiments/H02-juggling.md) | [grid.mp4](../runs/H02-juggling/videos/grid.mp4) |

## Results so far

![Juggling on one foot in H02, seen from six cameras at eight moments](../runs/H02-juggling/videos/contact_sheet_onefoot.png)

**How good.** Both experiments work from a task file, without any recorded motion, and both finished programs handle tasks they never saw.

| | H01 box | H02 juggling |
|---|---|---|
| Targets met | 38 of 38 | 48 of 48 |
| Targets met on the unseen task | 38 of 38 | 47 of 48 (one elbow 1 % too fast for an instant) |
| The agent's own test tasks | 8 of 12 meet every target | 11 of 11 meet every target |
| Convincing | the whole sequence, from a normal distance | the pattern, the hands, the order of events |
| Main weakness | flat hands with spread fingers | too tidy, with scripted reactions and no physics |

Both judgements come from still images. People still need to watch the videos, and for juggling, which depends on rhythm, that matters most.

**How fast.**

| Step | H01 box | H02 juggling |
|---|---|---|
| First motion meeting all targets on the one task | 24 min, about $4–5 | 32 min, about $4 |
| Finished, general program with notes | 99 min, $16.74 | 74 min, $11.33 |
| Running the finished program on a new task | about 8 s, no agent needed | about 6 s, no agent needed |

Costs are at list price, for one agent session. Working time does not count the break caused by the account's usage limit in H01.

**What we learned.**

- **Earlier code carries over.** The walking method from E03 and E04 needed only small additions for H01, and H02 reused H01's arm and finger kinematics. The harder task took less time and money, though one run each proves little.
- **One program now does everything so far.** The final `make_motion.py` still meets every target on the walking tasks and the box tasks.
- **The agent knows how people move.** Without being told, it bent the knees to lift, leaned back against a load, moved the weight before lifting a foot, and let the hand give way at a catch.
- **Order of work matters.** In H02 the agent computed the exact flights first and made the hands fit them, so the physics of the balls is exact by construction.
- **An independent test matters.** All of the agent's test tasks in H02 passed, and the unseen task still found a miss.
- **Passing all targets is not proof of quality.** H01's grip passed everything and looked wrong, and in both experiments a target-passing motion hid a real bug. Measurements catch faking, but people have to judge what looks real.
- **Measurements shape the result.** H01's flat grip and H02's open cup both follow partly from what our checks rewarded.

## What comes next

First, people should watch [`H02 grid.mp4`](../runs/H02-juggling/videos/grid.mp4) and [`H01 grid.mp4`](../runs/H01-box-carry/videos/grid.mp4), to confirm or correct the judgements on the experiment pages.

The next experiment could be a **new kind of object handling**, such as a pan held in one hand, which tests generality and moves towards the kitchen task. This is our recommendation. Other open directions are a **more alive juggler**, with real reactions, small errors and recoveries, and a **real grip on the box**, with fingers curled under it.
