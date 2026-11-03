# Teaching an AI agent to animate human walking: experiment report

*Last updated: 2026-11-03*

## What this project is about

We test whether an AI agent can make a 3D human body move realistically, using only what it knows, with no recordings of real human motion. The agent is a large language model that writes and runs its own code (Claude Code with Claude Opus 5.5). The body is SMPL-X, a standard 3D human body model used in computer vision and graphics research.

For each experiment, we describe a task in words (for example "walk along this S-shaped path" or "squeeze sideways through a narrow gap"). The agent then writes a program that computes the body's pose for every frame. We turn the result into videos from six cameras and measure it on the body's surface: do the feet slide or sink into the floor, does the person stay on the path, do they walk into furniture.

The goal is a fast, general program that produces high-quality human movement for a task given in words. The experiments build on each other: each one starts from the code of the previous one and adds a harder skill.

## How to read this report

1. **This page** gives the overview and the list of experiments.
2. **[How an experiment works](01-setup.md)** explains the setup once: what the agent receives, its rules, the steps of a run, and what the videos show.
3. **[How results are measured](02-measurements.md)** explains every measurement and its target.
4. **[Glossary](glossary.md)** explains walking and animation terms (stance, swing, cadence, inverse kinematics, ...).
5. **One page per experiment** in [`experiments/`](experiments/), all with the same structure: summary, task, what the agent did, results with videos and measurements, problems, conclusion.

**One name for everything.** Each experiment has an ID such as `E02-curved-path`, and that ID is the name of:

- its report page: `report/experiments/E02-curved-path.md`
- its folder, with everything the agent saw and produced: `runs/E02-curved-path/`
- its videos: `runs/E02-curved-path/videos/` (start with `grid.mp4`, which shows all six cameras at once)

## Experiments

| ID | Date | Task | Started from | Agent had | Result | Session | Report | Main video |
|---|---|---|---|---|---|---|---|---|
| E01 | 2026-11-01 | Straight walk, 6 s | scratch | no feedback (blind) | Natural walk at 1.23 m/s; feet neither slide nor sink; 11/11 targets met | 61 min, $12.71 | [E01](experiments/E01-straight-walk.md) | [grid.mp4](../runs/E01-straight-walk/videos/grid.mp4) |
| E02 | 2026-11-01 | S-shaped path, 10 s | E01 | measuring + preview tools | Follows any smooth path: slows, leans and looks into bends; 11/11 targets on both tasks; 4 s to compute 10 s | 38 min, $6.52 | [E02](experiments/E02-curved-path.md) | [grid.mp4](../runs/E02-curved-path/videos/grid.mp4) |
| E03 | 2026-11-02 | Start from standing, turn a 90° corner, stop, turn around on the spot, 12 s | E02 | measuring + preview tools | Redesigned around planned footsteps plus a balance model: start, step turn at the corner, precise stop (2 mm), six-step turn on the spot; 15/15 targets, earlier tasks still 11/11 | 69 min (interrupted once by the usage limit, resumed), $27.87 | [E03](experiments/E03-turns.md) | [grid.mp4](../runs/E03-turns/videos/grid.mp4) |
| E04 | 2026-11-02 / 03 | Squeeze sideways through a 0.40 m gap between two cabinets, 11 s | E03 | measuring + preview tools | Finds narrow gaps, turns sideways and side-steps through with 3.9 / 4.3 cm to spare; second technique (shoulder turn) for wider gaps; 15/15 targets, all earlier tasks still pass | 58 min (interrupted twice by the usage limit, resumed), $35.21 | [E04](experiments/E04-narrow-passage.md) | [grid.mp4](../runs/E04-narrow-passage/videos/grid.mp4) |

## The plan, and why in this order

| Step | New skill | Why it is harder than before |
|---|---|---|
| E01 straight walk | walking at all | baseline |
| E02 curved path | changing direction while walking | the body has to lean and turn into the bend, and the inner and outer feet travel different distances. E01's code assumes one fixed direction everywhere. |
| E03 turns, start, stop | starting from standing, a sharp corner, stopping, turning on the spot | the movement is no longer a repeating cycle: every step is different, and turning on the spot needs small pivoting steps. |
| E04 narrow passage | turning the body sideways and side-stepping through a gap narrower than the shoulders | a completely different way of moving, plus obstacles that must not be touched. |

After E04, the plan is a combined scene (for example a room with furniture and an instruction like "walk from the door around the table to the sofa"), to test whether the accumulated program can follow a new instruction quickly.

## Where we are after E04

The planned series is complete. The program written by the agent (in [`runs/E04-narrow-passage/`](../runs/E04-narrow-passage/)) produces, from a task file and in a few seconds:

- straight walking
- walking along smooth curves
- sharp corners
- starting and stopping
- turning on the spot
- squeezing through narrow gaps

All four tasks meet all measurement targets on the real body. No motion data was used at any point. Everything comes from the model's own knowledge of how people move, plus physics (balance) and geometry.

What the measurements cannot say is whether the motion *looks* human in every detail. Each experiment page lists the moments to check in the videos, and the next step is for people to watch them.

**Time and cost of the series** (one agent session per experiment; costs at list price):

| Experiment | Working time | Cost | Interruptions |
|---|---|---|---|
| E01 | 61 min | $12.71 | none |
| E02 | 38 min | $6.52 | none |
| E03 | 69 min | $27.87 | 1 (account usage limit) |
| E04 | 58 min | $35.21 | 2 (account usage limit) |
| **Total** | **3 h 46 min** | **$82.31** | |

Two practical lessons:

- **Harder tasks cost more,** because the agent works longer and every step re-reads an ever-longer conversation.
- **Interruptions are expensive when resumed many hours later,** because the whole conversation has to be loaded again at full price. In E04 a 4-minute final part cost $18.80. For future series it is better to run experiments at a time when the account's 5-hour usage window is fresh.

## Main findings so far

- **E04:** an entirely new way of moving (turning sideways and side-stepping through a gap narrower than the shoulders) fitted into E03's footstep-plus-balance design as new kinds of footsteps; balance, legs and upper body worked unchanged. The agent also worked around the limits of its tools. It could only measure the whole clip at once, so it made its own time-window and sliced-obstacle measurements to find where the body came closest, then centred the body in the gap to within millimetres.
- **E03:** to start, stop and turn sharp corners, the agent changed the program's architecture instead of patching it. It now plans every footstep first, then computes how the body moves over the feet with a simple balance model (the inverted pendulum). That single physical rule produces the forward lean before the first step, braking at the stop, corner cutting and side-to-side sway without separate tuning. This is the same split used in robotics and footstep-based animation, arrived at from first principles. The cost was high ($27.87), largely because of a long session of fixing the corner and the turn on the spot.
- **E02:** starting from E01's code and given tools to measure and look at its result, the agent generalised straight walking to any smooth path in half the time and cost. It built in physically motivated turning behaviour (slowing down, leaning into the bend, looking ahead, head turning before trunk and hips), turned the code into a reusable library, and made it about 20 times faster. Quality is unchanged: all targets met on the new and the old task. It also found the next limit by testing on its own: sharp 90° corners need a pivot or step turn.
- **E01:** with no data and no way to see its result, the agent wrote a walking program from first principles: footprints pinned to the floor, legs computed to reach them, hip height solved from how a knee bends. Measured on the real body, the result is clean: feet slide less than 0.5 cm/s and sink at most 2.7 mm. It took one hour and $12.71; most of that time was spent thinking and fine-tuning, while the finished program generates the clip in about 15 seconds.
