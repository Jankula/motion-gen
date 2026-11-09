# EXX: <title>

> **Summary.** Two to four sentences a supervisor can read on their own: what was tried, what came out, and the one most important finding.

| | |
|---|---|
| **Experiment ID** | `EXX-name` (the same name is used for the folder and the videos) |
| **Date** | YYYY-MM-DD |
| **Task** | short description, with a link to the task file in `tasks/` |
| **Agent** | Claude Code, model, headless |
| **Started from** | scratch, or the code of experiment `EYY` |
| **Tools the agent had** | blind, or `evaluate.py` + `preview.py` (N previews) |
| **Session** | duration, number of turns, cost |
| **Result** | one line, for example "all N measurement targets met; looks natural except ..." |
| **Folder** | link to `runs/EXX-name/` |
| **Main video** | link to `runs/EXX-name/videos/grid.mp4` |

## 1. Why this experiment

What question it answers, and how it follows from the previous experiment.

## 2. The task

What the person has to do, in plain words, plus the exact specification (path, obstacles, start and end, clip length). Say what makes it harder than before.

## 3. What the agent did

An account of the session in plain language: how it approached the problem, what it built, what went wrong along the way and how it fixed it. Based on the agent's `NOTES.md`, its code and the transcript. Explain any technical term on first use, or link to the [glossary](../glossary.md).

## 4. Results

### Videos and images

Links to `grid.mp4`, the per-view videos, `contact_sheet.png` and `overview_sheet.png`, with one or two images embedded.

### Measurements

The table from `motion.metrics.json`, followed by a short reading of it: what is good, and what each ❌ means in practice. Include the earlier tasks the code must still handle.

### What we see in the videos

An honest visual assessment: what looks natural, what does not, at which moments (give times or frame numbers).

## 5. Problems and limitations

What is wrong or missing, both what we saw and what the agent itself reported.

## 6. Conclusion and next step

What we learned, and what the next experiment changes because of it.

## Files in the experiment folder

| File | Content |
|---|---|
| `TASK.md`, `CLAUDE.md` | exactly what the agent was told |
| `make_motion.py`, library folder | the agent's code |
| `NOTES.md` | the agent's own account |
| `motion.npz` | the motion (SMPL-X parameters per frame) |
| `motion.metrics.json` | the measurements |
| `transcript.jsonl`, `run_summary.json` | the full session log, and its key facts |
| `videos/` | rendered videos and images |
