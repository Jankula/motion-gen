"""From the planned hands and balls to all joint rotations.

The balls and hands are fixed first (pattern.Scene).  The body is then built around them:

  feet     the standing foot never moves.  The free foot stays planted, peels off the floor heel
           first, is held up, and comes down toes first.
  balance  the wanted path of the centre of mass is written down: between the feet, over to the
           standing foot well before the free foot leaves, a slow sway, and back after the foot is
           down.  The pelvis is then shifted until the real centre of mass of the whole posed body
           (with the balls it is holding) follows that path.
  pelvis   its height comes from soft knees, a small give with every throw, and the reach of the legs.
  spine    the chest is steered in the world and shared out over the three spine joints.  It reacts
           to the arms: it turns and tips a little against the hand that throws.
  arms     analytic IK to the hand track of pattern.py.
  head     looks at the top of the arcs; the eyes follow more closely than the head.
"""
import numpy as np
from scipy.ndimage import gaussian_filter1d

from locomotion.rotations import (DEG, from_rotvec, mtv, mv, rot_between, rx, ry, rz, softplus, to_rotvec, tr)
from locomotion.skeleton import FLOOR, IDX, J, NJ, fk
from manipulation.arms import Arm
from manipulation.massmodel import BODY_MASS, body_com

from .curves import move, wobble
from .pattern import SIGN

SPINE = (("spine1", 0.30), ("spine2", 0.35), ("spine3", 0.35))
EYE = {"L": np.array([0.032, 0.058, 0.098]), "R": np.array([-0.032, 0.058, 0.098])}   # from the head joint


def chain_to_chest(P0, R):
    """World rotation and position of spine3."""
    W, P, prev = R[:, 0], P0, 0
    for name, _ in SPINE:
        j = IDX[name]
        P = P + mv(W, J[j] - J[prev])
        W = W @ R[:, j]
        prev = j
    return W, P


def slerp_to(Ra, Rb, w):
    return Ra @ from_rotvec(to_rotvec(tr(Ra) @ Rb) * w[:, None])


class Rig:
    def __init__(self, plan, scene):
        self.plan, self.scene = plan, scene
        self.q = plan.q
        self.legs = plan.stance.legs
        self.arms = {s: Arm(s, twist_share=self.q["forearm_twist"]) for s in "LR"}
        self.stand, self.free = plan.stand, plan.free
        self.sg = plan.sign_stand
        self._feet()

    # ================================================================== feet
    def _feet(self):
        st = self.plan.stance
        self.Fy, self.ank, self.centre, self.mid = st.Fy, st.ankle, st.centre, st.mid
        lo = np.array(self.q["land_offset"])
        self.ank_land = self.ank[self.free] + np.array([SIGN[self.free] * lo[0], 0.0, lo[1]])

    def com_target(self, t):
        """Wanted path (n, 2) of the centre of mass on the floor."""
        q, plan = self.q, self.plan
        w = plan.weight_on_foot(t)
        two = self.mid + np.array([q["com_side"], q["com_fwd"]])
        one = self.centre[self.stand] + np.array([-self.sg * q["com_foot_in"], q["com_foot_fwd"]])
        c = (1.0 - w)[:, None] * two + w[:, None] * one
        amp = q["sway_two"] + (q["sway_one"] - q["sway_two"]) * self._up(t)
        end = 1.0 - 0.6 * move(t, plan.ev["back0"], plan.ev["back1"] + 0.5)
        sway = np.stack([wobble(t, 1, 0.08, 0.55), 1.2 * wobble(t, 2, 0.06, 0.45)], -1)
        return c + (amp * end)[:, None] * sway

    def _up(self, t):
        """1 while on one foot."""
        ev = self.plan.ev
        return move(t, ev["heel"], ev["off"] + 0.2) * (1.0 - move(t, ev["down0"] + 0.2, ev["flat"]))

    # ================================================================== the free foot
    def _foot_program(self, t):
        """Lift share w, foot pitch a (heel up, toes down) of the free foot."""
        q, ev = self.q, self.plan.ev
        w = move(t, ev["off"], ev["up"]) * (1.0 - move(t, ev["down0"], ev["touch"]))
        a = (q["heel_rise"] * move(t, ev["heel"], ev["off"] + 0.03)
             + (q["foot_drop"] - q["heel_rise"]) * move(t, ev["off"] + 0.03, ev["up"])
             + (q["land_pitch"] - q["foot_drop"]) * move(t, ev["down0"], ev["touch"] - 0.02)
             - q["land_pitch"] * move(t, ev["touch"], ev["flat"]))
        return w, a

    def _free_foot(self, t, P0, Wp):
        q, ev = self.q, self.plan.ev
        s = self.free
        leg = self.legs[s]
        w, a = self._foot_program(t)
        Fy = self.Fy[s]
        F = Fy @ rx(a)
        # on the floor the foot turns about the ball of the foot
        landed = move(t, 0.5 * (ev["up"] + ev["down0"]) - 0.01, 0.5 * (ev["up"] + ev["down0"]) + 0.01)
        ank0 = self.ank[s][None] + landed[:, None] * (self.ank_land - self.ank[s])[None]
        r = J[leg.toe] - J[leg.ankle]
        ball = ank0 + (Fy @ r)[None]
        floor_ank = ball - mv(F, r)
        # up: thigh and shank at the wanted angles below the hip
        hip = P0 + mv(Wp, leg.hip_off)
        th, kn = q["thigh_up"], q["knee_up"]
        thigh = np.linalg.norm(leg.a)
        shank = np.linalg.norm(leg.b)
        fwd = thigh * np.sin(th) + shank * np.sin(th - kn)
        dn = thigh * np.cos(th) + shank * np.cos(th - kn)
        droop = 0.012 * wobble(t, 31, 0.05, 0.2)
        up = hip + np.stack([0.02 * SIGN[s] * np.ones_like(t) + q["leg_wander"] * wobble(t, 32, 0.15, 0.6),
                             -dn + droop, fwd + q["leg_wander"] * wobble(t, 33, 0.12, 0.5)], -1)
        ank = (1.0 - w)[:, None] * floor_ank + w[:, None] * up
        toe = -a * (1.0 - w)
        return F, ank, toe

    # ================================================================== pelvis
    def _drop(self, t):
        q, plan = self.q, self.plan
        d = q["knee_drop"] + q["knee_drop_one"] * self._up(t)
        juggling = move(t, plan.ev["first"] - 0.3, plan.ev["first"]) * (1.0 - move(t, plan.ev["last"], plan.ev["last"] + 0.6))
        b = np.zeros_like(t)
        for th in plan.throws:
            b += np.exp(-((t - th.t_rel + 0.03) / 0.085) ** 2)
        d = d + q["bounce"] * juggling * b + 0.0012 * wobble(t, 3, 0.1, 0.4)
        # the legs take the landing of the free foot
        ev = plan.ev
        d = d + 0.008 * move(t, ev["touch"] - 0.05, ev["flat"]) * (1.0 - move(t, ev["flat"], ev["flat"] + 0.7))
        return d

    def pelvis_rot(self, t):
        q, plan = self.q, self.plan
        ev = plan.ev
        lift = move(t, ev["heel"], ev["up"]) * (1.0 - move(t, ev["down0"], ev["touch"] + 0.1))
        w = plan.weight_on_foot(t)
        tilt = q["pelvis_tilt"] - q["pelvis_back"] * lift + 0.25 * DEG * wobble(t, 4, 0.08, 0.3)
        # towards the standing foot the hip on that side rises, with the leg up the free side does
        roll = self.sg * (1.6 * DEG * w * (1.0 - lift) - q["hike"] * lift) + 0.25 * DEG * wobble(t, 5, 0.08, 0.3)
        yaw = self.sg * q["pelvis_turn"] * lift + 0.3 * DEG * wobble(t, 6, 0.06, 0.25)
        return ry(yaw) @ rx(tilt) @ rz(roll)

    def pelvis_pos(self, t, shift, Wp):
        """Pelvis joint position (n, 3); the height follows the reach of the legs on the floor."""
        q, plan = self.q, self.plan
        ev = plan.ev
        xz = shift
        y = (J[0, 1] - self._drop(t))
        dt = 1.0 / plan.fps
        limit = np.full(len(t), np.inf)
        for s in "LR":
            leg = self.legs[s]
            dmax = leg.distance_from_knee(leg.straight_knee + q["leg_soft"])
            hip = mv(Wp, leg.hip_off)
            if s == self.stand:
                ank = np.broadcast_to(self.ank[s], (len(t), 3))
                planted = np.ones(len(t), dtype=bool)
            else:
                P = np.stack([xz[:, 0], y, xz[:, 1]], -1)
                _, ank, _ = self._free_foot(t, P, Wp)
                planted = (t < ev["off"]) | (t > ev["touch"])
            h = (xz + hip[:, [0, 2]]) - ank[:, [0, 2]]
            reach = np.sqrt(np.maximum(dmax ** 2 - np.sum(h * h, -1), 0.04))
            lim = ank[:, 1] + reach - hip[:, 1]
            limit = np.where(planted, np.minimum(limit, lim), limit)
        over = softplus(y - limit, 0.003)
        over = gaussian_filter1d(np.where(np.isfinite(limit), over, 0.0), 0.05 / dt, mode="nearest")
        y = y - over
        return np.stack([xz[:, 0], y, xz[:, 1]], -1)

    # ================================================================== chest and head
    def _hand_lift(self, t):
        tr_ = self.scene.tracks
        d = (tr_["L"].pos(t)[:, 1] - tr_["R"].pos(t)[:, 1]) / 0.25
        return gaussian_filter1d(d, 0.045 * self.plan.fps, mode="nearest")

    def thorax_rot(self, t):
        q, plan = self.q, self.plan
        ev = plan.ev
        lift = self._up(t)
        w = plan.weight_on_foot(t)
        juggling = move(t, ev["first"] - 0.4, ev["first"] + 0.3) * (1.0 - move(t, ev["last"] - 0.1, ev["last"] + 0.6))
        d = self._hand_lift(t) * juggling
        breath = 0.5 * DEG * np.sin(2.0 * np.pi * t / 3.9 + 0.3)
        pitch = q["thorax_pitch"] + breath + 0.3 * DEG * wobble(t, 7, 0.08, 0.3)
        yaw = -q["thorax_yaw_amp"] * d + 0.5 * DEG * wobble(t, 8, 0.06, 0.25) + self.sg * 1.0 * DEG * lift
        roll = q["thorax_roll_amp"] * d - self.sg * q["lean_one"] * w + 0.3 * DEG * wobble(t, 9, 0.08, 0.3)
        return ry(yaw) @ rx(pitch) @ rz(roll)

    def focus(self, t):
        """The point the eyes are on (n, 3)."""
        q, plan = self.q, self.plan
        ev = plan.ev
        apexes = np.array([th.apex for th in plan.throws])
        top = float(np.mean(apexes)) - 0.04
        a = plan.anchor(t)
        z = q["z_throw"]
        # the eyes jump from one side of the arcs to the other, in time with the balls
        side = np.zeros_like(t)
        for th in plan.throws:
            s = 1.0 if th.dst == "L" else -1.0
            side += s * np.exp(-((t - 0.5 * (th.t_rel + th.t_catch) - 0.05) / 0.17) ** 2)
        x = a[:, 0] + q["gaze_side"] * side
        rest = np.array([0.0, FLOOR + q["y_throw"] + q["look_height"], z])
        hands = np.array([0.0, FLOOR + q["ready_y"] + 0.06, q["ready_z"]])
        up = move(t, ev["first"] - 0.55, ev["first"] + 0.10) * (1.0 - move(t, ev["last"] - 0.25, ev["last"] + 0.25))
        p = np.stack([x, np.full_like(t, top), np.full_like(t, z)], -1)
        low = hands[None] + a * np.array([1.0, 0.0, 0.0])
        ahead = np.array([0.0, FLOOR + 1.45, 2.4])
        w_ahead = move(t, ev["flat"], ev["flat"] + 1.2)
        low = low + (ahead - hands)[None] * w_ahead[:, None]
        start = rest[None] + (hands - rest)[None] * 0.55
        w_start = 1.0 - move(t, ev["first"] - 0.55, ev["first"] + 0.10)
        low = low * (1.0 - w_start)[:, None] + start * w_start[:, None]
        return low * (1.0 - up)[:, None] + p * up[:, None]

    def _head(self, t, P0, R):
        q = self.q
        W3, P3 = chain_to_chest(P0, R)
        f = self.focus(t)
        fh = gaussian_filter1d(f, 0.11 * self.plan.fps, axis=0, mode="nearest")
        neck = P3 + mv(W3, J[IDX["neck"]] - J[IDX["spine3"]])
        d = fh - (neck + np.array([0.0, 0.22, 0.09]))
        # looking down the eyes do most of the work: the head only goes so far
        flat = np.linalg.norm(d[:, [0, 2]], axis=-1)
        pitch = np.arctan2(d[:, 1], flat)
        lim = q["head_down_max"]
        d[:, 1] = flat * np.tan(np.where(pitch < 0.0, lim * np.tanh(pitch / lim), q["look_up_share"] * pitch))
        Wd = rot_between(np.broadcast_to(np.array([0.0, 0.0, 1.0]), d.shape), d)
        Wd = Wd @ rx(0.6 * DEG * wobble(t, 12, 0.1, 0.5)) @ ry(0.8 * DEG * wobble(t, 13, 0.1, 0.45))
        rv = to_rotvec(tr(W3) @ Wd)
        R[:, IDX["neck"]] = from_rotvec(rv * 0.5)
        R[:, IDX["head"]] = from_rotvec(rv * 0.5)

    def eyes(self, t, W, P):
        """leye_pose, reye_pose (n, 3): the eyes turn to the focus, within their range."""
        Wh, Ph = W[:, IDX["head"]], P[:, IDX["head"]]
        f = gaussian_filter1d(self.focus(t), 0.03 * self.plan.fps, axis=0, mode="nearest")
        out = {}
        for s in "LR":
            d = mtv(Wh, f - (Ph + mv(Wh, EYE[s])))
            rv = to_rotvec(rot_between(np.broadcast_to(np.array([0.0, 0.0, 1.0]), d.shape), d))
            a = np.linalg.norm(rv, axis=-1, keepdims=True)
            lim = 28.0 * DEG
            out[s] = rv * (lim * np.tanh(a / lim) / np.maximum(a, 1e-9))
        return out["L"], out["R"]

    # ================================================================== arms
    def _arms(self, t, P0, R):
        q = self.q
        W3, P3 = chain_to_chest(P0, R)
        reach = {}
        for s, arm in self.arms.items():
            sg = arm.sign
            tr_ = self.scene.tracks[s]
            H = tr_.pos(t)
            Wh = tr_.rot(t)
            wrist = tr_.wrist(t)
            up = gaussian_filter1d(H[:, 1] - (FLOOR + q["ready_y"] + self.plan.lift), 0.06 * self.plan.fps, mode="nearest") / 0.2
            Rcol = ry(np.full(len(t), -sg * q["collar_fwd"])) @ rz(sg * (q["collar_up"] + q["collar_follow"] * up))
            Wc = W3 @ Rcol
            Pc = P3 + mv(W3, J[arm.collar] - J[IDX["spine3"]])
            S = Pc + mv(Wc, J[arm.shoulder] - J[arm.collar])
            pole = mv(W3, np.array(q["pole"]) * np.array([sg, 1.0, 1.0]))
            Rs, Re, Rw, rq = arm.solve(S, Wc, wrist, Wh, pole)
            reach[s] = np.linalg.norm(wrist - S, axis=-1) / arm.reach
            R[:, arm.collar] = Rcol
            R[:, arm.shoulder] = Rs
            R[:, arm.elbow] = Re
            R[:, arm.wrist] = Rw
        return reach

    # ================================================================== whole pose
    def pose(self, t, shift):
        n = len(t)
        R = np.tile(np.eye(3), (n, NJ, 1, 1))
        Wp = self.pelvis_rot(t)
        P0 = self.pelvis_pos(t, shift, Wp)
        R[:, 0] = Wp
        for s, leg in self.legs.items():
            if s == self.stand:
                F = np.broadcast_to(self.Fy[s], (n, 3, 3))
                ank = np.broadcast_to(self.ank[s], (n, 3))
                toe = np.zeros(n)
            else:
                F, ank, toe = self._free_foot(t, P0, Wp)
            Rh, th, Ra, _ = leg.ik(P0, Wp, F, ank)
            R[:, leg.hip], R[:, leg.knee], R[:, leg.ankle], R[:, leg.toe] = Rh, rx(th), Ra, rx(toe)
        rv = to_rotvec(tr(Wp) @ self.thorax_rot(t))
        for name, f in SPINE:
            R[:, IDX[name]] = from_rotvec(rv * f)
        self._head(t, P0, R)
        self.reach = self._arms(t, P0, R)
        return P0, R

    def com(self, t, P0, R, balls, held):
        W, P = fk(P0 - J[0], R)
        c = body_com(W, P)
        m = self.plan.ball_mass
        load = np.einsum("tb,tbk->tk", held.astype(float), balls)
        count = held.sum(-1)
        return (BODY_MASS * c + m * load) / (BODY_MASS + m * count)[:, None], W, P

    def solve(self, t, passes=5):
        """Shift the pelvis until the centre of mass follows its path."""
        plan = self.plan
        sig = 0.07 * plan.fps
        balls = self.scene.balls(t)
        L, Rr = self.scene.held_by(t)
        held = L | Rr
        want = self.com_target(t)
        shift = want.copy()
        shift = shift + np.array([0.0, -0.02])
        for _ in range(passes):
            P0, R = self.pose(t, shift)
            c, _, _ = self.com(t, P0, R, balls, held)
            shift = shift + gaussian_filter1d(want - c[:, [0, 2]], sig, axis=0, mode="nearest")
        self.shift = shift
        return shift

    def generate(self, t, world_xz, heading):
        shift = self.solve(t)
        P0, R = self.pose(t, shift)
        W, P = fk(P0 - J[0], R)
        lo, re = self.eyes(t, W, P)
        balls = self.scene.balls(t)
        # the pattern and the body were planned around x = z = 0 at the pelvis' rest position: put
        # the pelvis of the first frame on the start position, turned to the start heading
        H = ry(heading)
        off = np.array([P0[0, 0], 0.0, P0[0, 2]])
        P0w = mv(H, P0 - off) + np.array([world_xz[0], 0.0, world_xz[1]])
        bw = np.einsum("ij,tbj->tbi", H, balls - off) + np.array([world_xz[0], 0.0, world_xz[1]])
        Rg = H @ R[:, 0]
        return dict(fps=self.plan.fps, transl=P0w - J[0], global_orient=to_rotvec(Rg),
                    body_pose=to_rotvec(R[:, 1:]),
                    left_hand_pose=self.scene.fingers(t, "L"), right_hand_pose=self.scene.fingers(t, "R"),
                    leye_pose=lo, reye_pose=re, balls_transl=bw)
