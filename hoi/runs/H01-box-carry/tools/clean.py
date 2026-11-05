"""Remove generated working files: scratch/, test_out/ and Python caches (not previous/).

    python tools/clean.py
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in ("scratch", "test_out", "__pycache__", os.path.join("locomotion", "__pycache__"),
          os.path.join("manipulation", "__pycache__"), os.path.join("tools", "__pycache__")):
    path = os.path.join(ROOT, d)
    if os.path.isdir(path):
        shutil.rmtree(path)
        print("removed", d)
