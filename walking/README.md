# Walking: can an AI agent animate a human body without motion data?

An agent (Claude Code) gets a task in words, the SMPL-X body model's parameter interface and the body's measurements. It writes a program that produces per-frame SMPL-X parameters, using only its own knowledge: no motion capture, no motion datasets, no pretrained motion models. This folder sets up each experiment, runs the agent, renders the result from six cameras and measures it.

**The results are documented in [report/](report/README.md). Start there.**

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

## One experiment

Every experiment has an ID like `E02-curved-path`, used for its folder `runs/E02-curved-path/` and its report `report/experiments/E02-curved-path.md`.

```powershell
python -m walkenv.new_run E02-curved-path --task curved-path --from E01-straight-walk   # create the workspace
python -m walkenv.launch E02-curved-path      # run Claude Code headless in it (about an hour); logs transcript.jsonl
python -m walkenv.render runs/E02-curved-path     # videos + contact sheets into runs/E02-curved-path/videos/
python -m walkenv.evaluate runs/E02-curved-path   # measurements into runs/E02-curved-path/motion.metrics.json
python -m walkenv.summary runs/E02-curved-path    # duration, turns, cost, tool use into run_summary.json
```

If a session stops early because the account's usage limit was reached, continue the same session once the limit has reset: `python -m walkenv.launch <ID> --resume --reason "usage limit"`.

Options of `new_run`: `--task` (a name in [tasks/](tasks/) or a path), `--from` (an earlier experiment whose code the agent starts from), `--feedback blind|visual` (whether the agent gets `evaluate.py` and `preview.py`), `--max-previews`. Options of `render`: `--camera fixed`, `--no-video` (contact sheets only), `--views`, `--size`, `--no-shadows`.

## Layout

```
agent_kit/     prompt templates and docs that new_run copies into each workspace
tasks/         task files: instruction, path, obstacles, start and end poses
models/        SMPL-X model files (git-ignored), or use the unzipped download at the repository root
runs/          one folder per experiment: everything the agent saw and produced, the session log, videos
report/        the documentation: setup, measurements, glossary, one page per experiment
walkenv/       body model, cameras, renderer, evaluator, experiment creation and launch
```

## What is kept in git

Agent code, notes, motions, measurements, session logs, `grid.mp4` and the contact sheets of every experiment. The single-view videos are kept locally only, because they are large; re-create them with `python -m walkenv.render runs/<ID>`. The SMPL-X model, and files derived from it, are never committed.
