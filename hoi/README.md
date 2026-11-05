# Human-object interaction: can an AI agent animate a person handling an object?

An agent (Claude Code) gets a task in words, the SMPL-X body model's parameter interface and the body's measurements, including its hands. It writes a program that produces per-frame SMPL-X parameters together with the position of the object. This folder sets up each experiment, runs the agent, renders the result from eight cameras and measures it.

This is the sequel to the [walking experiments](../walking/README.md). It reuses their body model, cameras, renderer and session handling, and it starts from the code the agent wrote there.

**The results are documented in [report/](report/README.md). Start there.**

## Setup (once)

Follow the setup in [`../walking/README.md`](../walking/README.md) first: this folder uses the Python environment `../walking/.venv` and the SMPL-X model. Then, from this folder:

```powershell
..\walking\.venv\Scripts\activate
python -m hoienv.body_info     # writes agent_kit/body_info.json (body and hand measurements, given to the agent)
python -m hoienv.selftest      # checks the measuring tool: a correct hold passes, every fake is caught
python -m hoienv.selftest_juggling   # the same for juggling: a correct clip meets all targets, every fake is caught
```

## One experiment

Every experiment has an ID like `H01-box-carry`, used for its folder `runs/H01-box-carry/` and its report `report/experiments/H01-box-carry.md`.

```powershell
python -m hoienv.new_run H01-box-carry --task box-carry --from E04-narrow-passage   # create the workspace
# H02 is created the same way: python -m hoienv.new_run H02-juggling --task juggling --from H01-box-carry
python -m hoienv.launch H01-box-carry --model claude-opus-5-5   # run Claude Code headless in it; logs transcript.jsonl
python -m hoienv.render runs/H01-box-carry     # videos + contact sheets into runs/H01-box-carry/videos/
python -m hoienv.evaluate runs/H01-box-carry   # measurements into motion.metrics.json, motion.timeline.csv and, for juggling, motion.throws.csv
python -m hoienv.summary runs/H01-box-carry    # duration, turns, cost, tool use into run_summary.json
```

To try the finished program on the unseen task, from `runs/H01-box-carry/`:

```powershell
mkdir unseen; copy ..\..\tasks\box-carry-variant.json unseen\task.json
python make_motion.py unseen\task.json unseen\motion.npz
```

Then, from this folder, run `python -m hoienv.evaluate runs/H01-box-carry/unseen` and `python -m hoienv.render runs/H01-box-carry/unseen`.

If a session stops early because the account's usage limit was reached, continue the same session once the limit has reset: `python -m hoienv.launch <ID> --resume --reason "usage limit"`.

## Layout

```
agent_kit/     prompt templates and docs that new_run copies into each workspace
tasks/         task files: instruction, start pose, the object and where it has to go
runs/          one folder per experiment: everything the agent saw and produced, the session log, videos
report/        the documentation: setup, measurements, glossary, one page per experiment
hoienv/        measurements of hands, object, balls and balance, hand data, experiment creation and launch
```

## What is kept in git

Agent code, notes, motions, measurements and the key facts of each session (`run_summary.json`). Videos and pictures are kept locally only; re-create them with `python -m hoienv.render runs/<ID>`, so the links to them in the reports work on a local copy. Session logs (`transcript.jsonl`) are also kept locally only, because they contain `body_info.json`, which the agent reads. The SMPL-X model, and files derived from it such as `body_info.json`, are never committed.
