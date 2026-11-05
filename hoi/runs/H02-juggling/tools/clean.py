"""Remove generated working files: scratch/, test_out/ and the Python caches of this directory.

    python tools/clean.py
"""
import glob
import os
import shutil

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for name in ("scratch", "test_out", "__pycache__", "juggling/__pycache__", "locomotion/__pycache__",
             "manipulation/__pycache__", "tools/__pycache__"):
    path = os.path.join(HERE, name)
    if os.path.isdir(path):
        shutil.rmtree(path)
print("left:", sorted(os.path.basename(p) for p in glob.glob(os.path.join(HERE, "*"))))
