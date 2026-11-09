"""Are two motion files identical?   python tools/compare.py a.npz b.npz"""
import sys

import numpy as np

a, b = np.load(sys.argv[1]), np.load(sys.argv[2])
same = sorted(a.files) == sorted(b.files) and all(np.array_equal(a[k], b[k]) for k in a.files)
print("identical" if same else "DIFFERENT")
sys.exit(0 if same else 1)
