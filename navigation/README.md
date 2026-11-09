# motion-gen: how to run it

A household agent (Claude) gets a task in words, such as "Make me scrambled eggs and sit down to eat", in a
ProcTHOR house. It plans the steps, walks and acts through the house, and writes the result as motion input for
the SMPL-X walking code. How it works inside: [docs/README_pipeline.md](docs/README_pipeline.md).

## 1. Every new terminal

```bash
source ~/miniconda3/bin/activate      # makes `conda` available (or run `~/miniconda3/bin/conda init bash` once)
conda activate motion-gen
cd ~/motion-gen
```

You need:
- the GPU VM, for AI2-THOR renders;
- the `claude` CLI, logged in. It is found on PATH or inside the VS Code extension.

## 2. Run one task: `scripts/do_task.py`

```bash
python scripts/do_task.py --house 2927 --start 2.5,1.5 "Make me scrambled eggs and sit down to eat."
```

| option | meaning |
|---|---|
| `--house` | ProcTHOR house index (`2927` or `train_2927`); exported on first use |
| `--start x,y` | start position in metres; moved to the nearest free floor if needed |
| `--heading` | start heading in degrees, counter-clockwise from +x (default 0) |
| `--model` | `sonnet` (default), `opus`, … |
| `--condition` | `agent` (default; acts step by step with feedback) or `baseline` (one plan, no feedback) |
| `--no-rerender` | no new image after each walk; the agent sees only the start images |

It takes about 1–2 minutes. It prints the subtasks with their motion segments, the timings, and the run folder.

**Choosing a start:** look at the house from above in `scenes/procthor/train_2927/views/top/rgb.png`. Exported
houses so far: 0, 3, 4, 10, 17, 20, 239, 737, 811, 1078, 2927, 2957.

### Where the files land

| path | what |
|---|---|
| `episodes/tasks/<time>_<words>.yaml` | the episode: instruction, house, start, limits, list of start images |
| `scenes/procthor/train_<n>/views/<episode>_*/` | the five start images (front, left, right, back, top) |
| `runs/<episode>_agent/` | the run folder |
| … `transcript.jsonl` | everything the model said and every tool call and result |
| … `state.json` | walks (legs), actions, events, what is held, images seen |
| … `summary.json` | time, tool calls, tokens, audit, route metrics, final reply |
| … `route.png` | map with the walked route |
| … `views/`, `renders/` | images the model looked at (with numbered badges), raw renders after walks |
| … `motion/motion_script.json` | subtasks → motion segments (walk, turn, open, pick, …) and object timeline |
| … `motion/walks/walk_NN.json` | one input file per walk for the partner's `make_motion.py` |
| … `motion/route_motion.png` | map coloured by subtask with every motion labelled |

## 3. Other commands

```bash
# one existing episode (scored, if the episode has goals)
python scripts/run_episode.py episodes/procthor_long/t01_breakfast_2927.yaml --condition agent

# agent vs. baseline over a folder of episodes (resumable); results in runs/eval_<name>/
python scripts/run_eval.py --name procthor_long_v2 --episodes episodes/procthor_long --repeats 1

# rebuild motion/ for runs made earlier (no GPU, no Claude)
python scripts/export_motion.py runs/eval_procthor_long_v1/t01_breakfast_2927__agent__0

# export a house, or render the start images for an episode you wrote yourself
python scripts/export_procthor.py scene train 2927
python scripts/export_procthor.py views episodes/mine/x.yaml

# tests (no GPU)
python -m pytest tests
```

## 4. More

- [docs/README_pipeline.md](docs/README_pipeline.md): the pipeline in one page.
- [docs/pipeline.md](docs/pipeline.md): full reference (episode fields, scoring, writing your own tasks).
- [docs/motion_handoff.md](docs/motion_handoff.md): the motion files, written for the SMPL-X side.
