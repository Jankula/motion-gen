# How an experiment works

This page explains the setup shared by all experiments: what the AI agent is, what it receives, what it is allowed to do, how a run goes from start to finish, and how the results are shown. The individual experiment pages refer back here instead of repeating it.

## The body: SMPL-X

SMPL-X is a widely used 3D model of the human body from the Max Planck Institute for Intelligent Systems. It is a surface mesh of 10,475 points ("vertices") hung on a skeleton of 55 joints. You make the body move by rotating joints, and the skin follows the skeleton automatically, including small corrective bulges around bending joints.

In all our experiments:

- the body shape is fixed: the gender-neutral average adult, 1.72 m tall;
- the agent controls 22 joints (pelvis, spine, neck, head, collarbones, shoulders, elbows, wrists, hips, knees, ankles, toes) plus the position and orientation of the whole body, for every frame;
- fingers, face and eyes stay in their relaxed default pose unless the agent chooses to move them.

Everything the agent produces is therefore a table of numbers: for each frame, a position and 22 joint rotations. Everything else (the mesh, the videos, the measurements) is computed by us from that table.

## The agent

The agent is **Claude Code**, Anthropic's coding agent, running the model **Claude Opus 5.5**. It works "headless": we give it one starting instruction and it then works alone until it decides the job is done. It can read and write files in its experiment folder and run Python there. It cannot ask questions, browse the internet, or install software.

The agent does not output the motion directly. It writes a **program** that computes the motion. This turned out to be the natural way for it to work: walking is described by rules (how the feet are placed, how the legs swing, how the body balances), and a program can apply those rules to any number of frames and to new tasks.

## The rules, and why

| Rule | Why |
|---|---|
| Use only your own knowledge: no motion-capture recordings, motion datasets, pretrained motion models, or internet | The research question is what the model itself knows about human movement. Motion data would let it copy instead. |
| Python with only numpy and scipy (general maths libraries) | Prevents shortcuts through animation or robotics libraries. |
| Stay inside your experiment folder | Keeps experiments independent: an agent cannot look at other experiments' results. |
| Work autonomously, decide ambiguities yourself and write them down | Makes runs repeatable without a human in the loop. |

We check afterwards that the rules were followed: the full log of every session is kept (see below), and for E01 we confirmed that every file access and shell command stayed inside the folder.

## What the agent receives

Each experiment folder starts with only these files:

| File | What it is |
|---|---|
| `TASK.md` | The assignment: what the person should do, the deliverables, how the result will be judged, the tools and the rules. Generated from the task file, so every experiment uses the same wording. |
| `CLAUDE.md` (also as `AGENTS.md`) | The rules again, in the file the agent reads automatically at the start. |
| `SMPLX_INTERFACE.md` | How the body is controlled: coordinate system, how rotations work, how joints are connected, the file format. Comparable to a technical manual. It contains no information about how people move. |
| `body_info.json` | The body's measurements: where each joint is when standing, where the floor is, where the heels and toes are, how wide and deep the torso is. |
| `task.json` | The task in machine-readable form: path, obstacles, start and end poses, clip length. |
| `check_format.py` | Checks that a motion file has the right format and length. |
| `evaluate.py` | *(from E02 on)* Measures the motion on the real body mesh: floor contact, foot sliding, path following, obstacle collisions, glitches. See [the measurements page](02-measurements.md). Unlimited use. |
| `preview.py` | *(from E02 on)* Renders still images from all six cameras so the agent can look at its result. Limited to 8 uses per experiment. |
| `previous/<ID>/` | *(from E02 on)* The code and notes the agent wrote in the previous experiment. |
| `tasks/` | *(from E02 on)* The earlier tasks, which the new code must still handle. |

The prompt templates these files are generated from are in [`../agent_kit/`](../agent_kit/).

## Two ways of working: blind and with feedback

- **Blind** (E01): the agent never sees a rendering and has no measuring tool. Anything it checks, it checks with its own calculations. This shows what it can do from knowledge and reasoning alone.
- **With feedback** (E02 onwards): the agent has `evaluate.py` and `preview.py`. Since the goal from E02 on is the best possible motion, not a test of unaided knowledge, we give it the same tools a human animator would use. The tools say *whether* something is wrong (a foot slides, the body touches a cabinet), never *how* to move.

## Building on earlier experiments

From E02 on, the experiments form a chain. Each one starts from the code of the previous one (in `previous/`), gets a new, harder task, and must keep the earlier tasks working. The aim is to end with one general motion library that handles all tasks, not a separate program per task. The agent is asked to make its code fast (a few seconds to compute a clip) and to write its notes for a non-specialist reader.

## How one experiment runs, step by step

1. **Task file.** We describe the task in a JSON file in [`../tasks/`](../tasks/), with a plain-language instruction plus the precise path, obstacles and start and end poses.
2. **Create the folder.** `python -m walkenv.new_run E02-curved-path --task curved-path --from E01-straight-walk` creates `runs/E02-curved-path/` with the files listed above.
3. **Run the agent.** `python -m walkenv.launch E02-curved-path` starts Claude Code in that folder with a one-line kickoff ("Read TASK.md and SMPLX_INTERFACE.md, then complete the task..."). The full session is recorded in `transcript.jsonl`.
4. **The agent delivers** `make_motion.py` (its program), its library code, `motion.npz` (the motion for this task) and `NOTES.md` (its own account of what it did).
5. **Render.** `python -m walkenv.render runs/E02-curved-path` produces the videos and images in `runs/E02-curved-path/videos/`.
6. **Measure.** `python -m walkenv.evaluate runs/E02-curved-path` writes `motion.metrics.json`.
7. **Session facts.** `python -m walkenv.summary runs/E02-curved-path` extracts duration, cost and tool use from the transcript into `run_summary.json`.
8. **Report.** We watch the videos, read the agent's notes and code, and write `report/experiments/E02-curved-path.md`.

**Interruptions.** The agent runs on a Claude subscription, which limits how much can be used in a 5-hour window. If a session hits that limit, it stops in the middle of its work. Such a session is not restarted from scratch. It is resumed with `python -m walkenv.launch <ID> --resume --reason "..."`, which continues the *same* conversation, so the agent keeps everything it had read, planned and written, and is told that it was interrupted from outside. The transcript then holds both parts, `run.json` records when and why the session was resumed, and the experiment page says so. Durations and costs in the reports count working time only, without the waiting time between the parts.

**Permissions during a run.** The agent may create and edit files in its folder, run the project's Python, and create folders. Any other shell command is refused automatically; the agent sees the refusal and works around it.

## Where everything is: one name for everything

Every experiment has an ID such as **`E02-curved-path`** (number, then a short name for the task). The same ID is used for:

| What | Where |
|---|---|
| The report page | `report/experiments/E02-curved-path.md` |
| The experiment folder (everything the agent saw and produced) | `runs/E02-curved-path/` |
| The videos and images | `runs/E02-curved-path/videos/` |
| The measurements | `runs/E02-curved-path/motion.metrics.json` |
| The session log and facts | `runs/E02-curved-path/transcript.jsonl`, `run_summary.json` |

One experiment is always exactly one agent session. If a task is attempted again, it gets a new ID.

## The videos

Each motion is rendered from six cameras:

| View | What it shows |
|---|---|
| **front**, **back**, **left**, **right** | Cameras that follow the person at 4.5 m distance and turn with them, so "front" always shows the face, even during turns. "Left" and "right" mean the person's own left and right. |
| **top** | The whole scene seen from straight above. Best for judging the path. |
| **overview** | The whole scene from an elevated corner. The easiest view for a first impression. |

What is drawn:

- **Floor:** a checkerboard of 0.5 m tiles. A foot that slides while standing is easy to spot against the tiles.
- **Path:** a teal line. The start position is a grey ring and the required end position a teal ring; a short line on a ring shows the required facing direction.
- **Trail:** an orange line showing where the pelvis has actually been so far.
- **Obstacles:** translucent blue boxes, so they never hide the body.
- **Shadow:** a grey shadow straight below the body. A foot on the floor touches its shadow; a lifted foot shows a gap.

Files in `videos/`:

| File | Content |
|---|---|
| `grid.mp4` | **All six views in one video.** Start here. Top row: overview, front, left. Bottom row: top, back, right. |
| `front.mp4` … `overview.mp4` | Each view on its own at full size. These are kept on the local machine only (large), and can be re-created with the render command. |
| `contact_sheet.png` | Still frames from the four follow cameras across about one second (roughly one stride), for close inspection. |
| `overview_sheet.png` | The top and overview cameras at five moments spread over the whole clip. |

## The machine

Everything runs on a laptop: Intel Core i5-8250U, 8 GB RAM, no usable GPU, Windows 11. Rendering a 10-second clip from six cameras takes about 3–4 minutes. Measuring takes about 30 seconds.

## Reproducing everything

Setup is described in [`../README.md`](../README.md). In short: create the Python environment, place the SMPL-X model files, run `python -m walkenv.body_info` once, then follow the steps above.
