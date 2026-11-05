"""Print the footstep plan of a task and, with --env, the body state every 0.25 s.

    python tools/plan_report.py task.json [--env]

(My own checking tool.)"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from locomotion import generate_motion, load_task  # noqa: E402
from locomotion.path import hdir, lnorm  # noqa: E402
from locomotion.rotations import DEG  # noqa: E402

task = load_task(sys.argv[1])
m = generate_motion(task)
b = m["body"]
p = b.p
print("c_walk %.4f roll0 %.3f deg" % (p["c_walk"], p["roll0"] / DEG))
plan = b.plan
for s in plan.steps:
    if -1.0 < s.t_hs < plan.duration + 0.5:
        P0, W0 = b.pelvis([s.t_hs])
        psi = b.psi([s.t_hs])[0]
        d = (s.xz - P0[0, [0, 2]]) @ hdir(psi)
        lat = (s.xz - P0[0, [0, 2]]) @ lnorm(psi)
        print("%s %-7s lo %6.3f hs %6.3f  heel ahead of pelvis %.3f lat %+.3f yaw %7.1f size %.2f alpha %.1f"
              % (s.side, s.kind, s.t_lo, s.t_hs, d, lat, s.yaw / DEG, s.size, s.alpha / DEG))
G = b.grid
t = G["t"]
sel = (t > 0) & (t < plan.duration)
v = np.gradient(G["com"], t, axis=0)
vf = np.sum(v * hdir(G["psi"]), -1)
vl = np.sum(v * lnorm(G["psi"]), -1)
print("COM fwd speed %.3f..%.3f, lateral %.3f..%.3f" % (vf[sel].min(), vf[sel].max(), vl[sel].min(), vl[sel].max()))
if "--env" in sys.argv:
    for tt in np.arange(0, plan.duration, 0.25):
        ph, g, e = b.envelopes(np.array([tt]))
        ll, lf = b.lean(np.array([tt]))
        c = b.com(np.array([tt]))[0]
        print("t %5.2f ph %5.2f g %4.2f e %4.2f psi %7.1f com (%6.3f %6.3f) lean lat %5.1f fwd %5.1f y %.3f"
              % (tt, ph[0], g[0], e[0], b.psi(np.array([tt]))[0] / DEG, c[0], c[1], ll[0] / DEG, lf[0] / DEG,
                 b.height(np.array([tt]))[0]))
