"""Render a motion into preview/contact_sheet.png and preview/overview_sheet.png.

    python preview.py                                   # motion.npz, task.json, window 1.2 s from 2.0 s
    python preview.py motion.npz task.json --start 3.5 --duration 2

contact_sheet.png: the four follow cameras and the two close-ups of the hands (rows) at eight moments across the window (columns).
overview_sheet.png: the top and overview cameras at five moments across the whole clip.
Allowed at most 12 times in total.
"""
import argparse
import subprocess
import sys
from pathlib import Path

PYTHON = r"C:/Projects/motion-gen/walking/.venv/Scripts/python.exe"
HOI_ROOT = r"C:/Projects/motion-gen/hoi"
MAX_PREVIEWS = 12
HERE = Path(__file__).resolve().parent
COUNTER = HERE / ".preview_count"

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("motion", nargs="?", default="motion.npz")
ap.add_argument("task", nargs="?", default="task.json")
ap.add_argument("--start", type=float, default=2.0, help="window start, seconds")
ap.add_argument("--duration", type=float, default=1.2, help="window length, seconds")
ap.add_argument("--cols", type=int, default=8, help="frames in the window")
args = ap.parse_args()

used = int(COUNTER.read_text()) if COUNTER.exists() else 0
if used >= MAX_PREVIEWS:
    sys.exit(f"No previews left (used {used} of {MAX_PREVIEWS}).")

cmd = [
    PYTHON, "-m", "hoienv.render", str((HERE / args.motion).resolve()), "--task", str((HERE / args.task).resolve()),
    "--out", str(HERE / "preview"), "--no-video",
    "--sheet-start", str(args.start), "--sheet-duration", str(args.duration), "--sheet-cols", str(args.cols),
]
if subprocess.run(cmd, cwd=HOI_ROOT).returncode != 0:
    sys.exit("Preview failed (this run was not counted).")
COUNTER.write_text(str(used + 1))
print(f"Wrote preview/contact_sheet.png and preview/overview_sheet.png. Previews left: {MAX_PREVIEWS - used - 1}")
