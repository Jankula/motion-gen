"""Are two motion files identical?

    python tools/compare.py a.npz b.npz
"""
import sys

import numpy as np

a, b = np.load(sys.argv[1]), np.load(sys.argv[2])
same = set(a.files) == set(b.files)
worst = 0.0
for k in a.files:
    if k in b.files:
        worst = max(worst, float(np.abs(a[k].astype(float) - b[k].astype(float)).max()))
print("same keys: %s, largest difference: %g, bit-identical: %s"
      % (same, worst, same and all(np.array_equal(a[k], b[k]) for k in a.files)))
