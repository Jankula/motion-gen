"""Copy a motion with every frame outside the time windows moved 50 m away along +x, so that
evaluate.py reports obstacle clearances for those windows only (my own checking tool).

    python tools/window.py motion.npz probe/win_entry.npz 2.5 4.2 [t0 t1 ...]"""
import sys

import numpy as np

src, dst = sys.argv[1], sys.argv[2]
win = [float(x) for x in sys.argv[3:]]
d = dict(np.load(src))
fps = int(d["fps"])
t = np.arange(len(d["transl"])) / fps
keep = np.zeros(len(t), dtype=bool)
for a, b in zip(win[::2], win[1::2]):
    keep |= (t >= a) & (t <= b)
tr = d["transl"].copy()
tr[~keep, 0] += 50.0
d["transl"] = tr
np.savez(dst, **d)
print("wrote %s: %d of %d frames kept" % (dst, keep.sum(), len(t)))
