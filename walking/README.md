# Walking: can an agent make a human walk?

An agent (Claude Code, Codex, ...) gets the SMPL-X body model's parameter interface and is asked to produce a realistic walk using only its own knowledge: no motion-capture data, no motion datasets, no pretrained motion models. It writes a script that outputs per-frame SMPL-X parameters. This folder renders the result as video from four cameras (front, back, left, right).

## Setup (once)

```powershell
cd walking
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Get the SMPL-X model as described in [models/README.md](models/README.md). Then:

```powershell
python -m walkenv.body_info     # writes agent_kit/body_info.json (the body's measurements, given to the agent)
python -m walkenv.smoke_test    # renders runs/_smoke/; check it matches the list in walkenv/smoke_test.py
```

## One attempt

```powershell
python -m walkenv.new_run --agent claude --mode blind
```

This creates `runs/<timestamp>_claude_blind/` and prints the commands to launch Claude Code or Codex inside it, interactively or headless. When the agent finishes:

```powershell
python -m walkenv.render runs/<timestamp>_claude_blind
```

The output in `runs/<run>/videos/` is `front.mp4`, `back.mp4`, `left.mp4`, `right.mp4`, `grid.mp4` (all four views at once) and `contact_sheet.png` (frames across about one stride, one row per view). Useful flags: `--camera fixed` for static cameras that see the whole path instead of following the walker, `--no-shadows`, `--size 1920x1080`.

## Modes

- **blind**: the agent never sees a render. This measures prior knowledge plus reasoning: the agent can still check its motion numerically, for example by writing its own forward kinematics.
- **visual**: the agent also gets `preview.py`, which renders a contact sheet it can look at, limited to `--max-previews` uses. This measures whether it can improve from visual feedback.

## What the agent sees

The workspace contains only what is copied from [agent_kit/](agent_kit/):

| file | content |
|---|---|
| `TASK.md` | the task, the deliverables, how the result is judged, the rules |
| `CLAUDE.md`, `AGENTS.md` | the rules again, auto-loaded by Claude Code and Codex respectively |
| `SMPLX_INTERFACE.md` | coordinate frame, rotation convention, forward kinematics, joint table, file format |
| `body_info.json` | rest-pose joint positions, floor height, foot and head landmarks |
| `check_format.py` | validates `motion.npz` (a copy of `walkenv/motion_format.py`) |
| `preview.py` | visual mode only |

The prompt states *what* is judged (foot sliding, ground contact, interpenetration, robotic motion, coordination, speed vs. leg motion, symmetry) and gives no gait knowledge: no joint-angle curves, cadence or step length. Isolation is by instruction only: the agent is told not to read outside its workspace, but nothing enforces it.

## Layout

```
agent_kit/     prompt templates and docs copied into each workspace
models/        SMPL-X model files (git-ignored)
runs/          one folder per attempt; videos/ and preview/ are git-ignored
walkenv/       body model wrapper, cameras, renderer, run creation
```
