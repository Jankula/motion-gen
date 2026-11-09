"""Where the feet stand.  Both the plan (how far the weight travels) and the rig use this one object.

Everything is in the person's own frame: x = z = 0 stands for the pelvis joint at rest.
"""
import numpy as np

from locomotion.legs import Leg
from locomotion.rotations import ry
from locomotion.skeleton import J, LM

SIGN = {"L": 1.0, "R": -1.0}


class Stance:
    def __init__(self, q):
        self.origin = J[0, [0, 2]].copy()
        self.legs = {s: Leg(s) for s in "LR"}
        self.Fy, self.ankle, self.centre = {}, {}, {}
        for s, sg in SIGN.items():
            pre = "left_" if s == "L" else "right_"
            leg = self.legs[s]
            self.Fy[s] = ry(sg * q["toe_out"])
            a = J[leg.ankle].copy()
            a[0] += sg * q["stance_extra"] - self.origin[0]
            a[2] -= self.origin[1]
            self.ankle[s] = a
            heel, toe = LM[pre + "heel_back"], LM[pre + "toe_tip"]
            outer, inner = LM[pre + "sole_outer_edge"], LM[pre + "sole_inner_edge"]
            c = np.array([0.5 * (outer[0] + inner[0]), 0.0, 0.5 * (heel[2] + toe[2])]) - J[leg.ankle] * np.array([1.0, 0.0, 1.0])
            self.centre[s] = (a + self.Fy[s] @ c)[[0, 2]]
        self.mid = 0.5 * (self.centre["L"] + self.centre["R"])

    def travel(self, side):
        """How far the weight moves sideways to get over the foot of that side."""
        return float(abs(self.centre[side][0] - self.mid[0]))
