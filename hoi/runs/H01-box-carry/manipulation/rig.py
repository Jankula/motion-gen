"""From the script to all joint rotations: posture, box, arms, hands, head and balance.

The legs and the pelvis come from locomotion.Body.  On top of that:

  Posture   time programs that bend the body down and up, lean it back under the load, ...
            Each channel is a sum of smooth moves (zero speed and acceleration at both ends),
            so that overlapping moves of different channels give one flowing movement.
  box_pose  the box: on the floor, lifted, carried (it follows the body with a little
            smoothing and a reduced bob, as a load held in soft arms does), put down.
  arms      the hands are attached to the box by IK from the moment they touch it.  Before and
            after, the arms blend between the free arm swing and the IK solution.
  balance   the combined centre of mass of body and box is computed on the skeleton, and the
            pelvis is shifted so that it follows the balance model (over the feet when standing).

Rig.solve() iterates: how low the body goes follows from the reach of the arms at the box, the
pelvis shift from the balance, and a small correction of the box height from arms that would be
overstretched while the box moves.  That correction should stay small (a few cm): a large one
means the box and the body are out of step, and it is limited by reach_fix_max.
"""
import numpy as np
from scipy.ndimage import gaussian_filter1d

from locomotion.body import Body
from locomotion.path import hdir, lnorm
from locomotion.rotations import (DEG, from_rotvec, mv, rot_between, rx, ry, rz, smootherstep, smoothstep,
                                  to_rotvec, tr)
from locomotion.skeleton import FLOOR, IDX, J, fk

from .arms import Arm
from .hand import PALM, HandShapes
from .massmodel import BODY_MASS, total_com

DEFAULTS = dict(
    # --- how the box is gripped
    grip_low=0.46,         # palm centre at this share of the box height above its bottom ...
    grip_low_min=0.125,     # ... but at least this high (the fingers must clear the floor) [m]
    grip_low_max=0.20,     # ... and at most this [m]
    grip_near=0.36,        # palm centre at this share of the depth from the near face
    grip_finger=45.0 * DEG,  # fingers point this far down from the horizontal
    palm_gap=0.007,        # palm_center point this far off the face (the ball of the thumb touches)
    # --- how the box is carried
    carry_hand_y=0.95,    # height of the palm centres above the floor [m]
    carry_top_max=1.30,    # top of the box at most this high [m]
    carry_gap=0.015,       # between the belly and the near face of the box [m]
    belly=0.125,           # belly in front of the pelvis joint [m]
    box_follow=0.09,       # smoothing of the box's movement relative to the body [s]
    box_bob=0.75,          # share of the pelvis bob the box takes
    carry_tilt=-2.0 * DEG,  # box tilted so that its top is nearer to the body
    lean_back=2.5 * DEG,   # trunk leaning back under the load, plus ...
    lean_back_kg=0.30 * DEG,   # ... this much per kg
    carry_knee=4.0 * DEG,  # softer knees while walking under the load
    hitch=0.014,           # the legs give this much under a 10 kg load at the end of the lift [m]
    box_drift=0.004,       # the box drifts this much up and down, slowly [m]
    box_sway=1.0 * DEG,    # the box rolls and turns this much with the steps
    # --- bending down
    trunk_pitch=84.0 * DEG,  # thorax pitch at the bottom
    pelvis_share=0.47,     # share of the thorax pitch taken by the pelvis
    reach_bottom=0.925,     # shoulder-wrist distance at the bottom as a share of the arm's length
    lower_arc=0.045,        # on the way down the box passes this far further out, clear of the knees [m]
    final_height=0.04,     # the last bit of lowering the box, taken slowly [m] ...
    final_time=0.7,        # ... in this time [s]
    hand_off=0.075,        # hands come in from this far outside the face [m]
    reach_max=0.975,       # the box is lifted faster where the arms would be stretched beyond this ...
    reach_fix_max=0.15,    # ... but by at most this much [m]
    walk_shift=0.4,        # walking, the pelvis takes this share of the shift that balances the load
    crouch_fwd=0.05,       # centre of mass this far ahead of the middle of the feet at the bottom [m]
    # --- arms
    pole_low=(0.75, -0.42, -0.50),   # elbow direction in the thorax frame (left arm), bent down ...
    pole_carry=(0.38, -0.65, -0.50),  # ... and upright with the box: closer to the trunk
    collar_reach=12.0 * DEG,  # the shoulders come forward when the arms are in front of the body
    collar_up=3.0 * DEG,   # ... and rise a little under the load, but ...
    collar_down=7.0 * DEG,  # ... come down when reaching for the floor
)

ARMS = {"L": Arm("L"), "R": Arm("R")}
UP = np.array([0.0, 1.0, 0.0])


def move(t, ta, tb, ease=smootherstep):
    return ease((np.asarray(t, dtype=float) - ta) / max(tb - ta, 1e-6))


class Posture:
    """Time programs read by locomotion.Body and upper_body."""

    CHANNELS = ("drop", "tilt", "thorax_pitch", "thorax_yaw", "thorax_roll", "pelvis_yaw",
                "pelvis_roll", "load", "soft", "arm_out", "hitch")

    def __init__(self, t_a, t_b):
        self.tg = np.arange(t_a, t_b, 1.0 / 120.0)
        self.moves = {c: [] for c in self.CHANNELS}
        self.scale = {}
        self.ch = {}
        self.shift_t = np.array([t_a, t_b])
        self.shift_xz = np.zeros((2, 2))
        self.crouch_ref = 0.1
        self.rebuild()

    def add(self, chan, ta, tb, amp, tag=None, ease=smootherstep):
        self.moves[chan].append((ta, tb, amp, tag, ease))

    def rebuild(self):
        for c in self.CHANNELS:
            v = np.zeros(len(self.tg))
            for ta, tb, amp, tag, ease in self.moves[c]:
                v += amp * self.scale.get(tag, 1.0) * move(self.tg, ta, tb, ease)
            self.ch[c] = v
        self.crouch_ref = max(0.05, float(self.ch["drop"].max()))

    def _get(self, c, t):
        return np.interp(t, self.tg, self.ch[c])

    def drop(self, t):
        return self._get("drop", t) + self._get("hitch", t)

    def hitch(self, t):
        return self._get("hitch", t)

    def tilt(self, t):
        return self._get("tilt", t)

    def thorax_pitch(self, t):
        return self._get("thorax_pitch", t)

    def thorax_yaw(self, t):
        return self._get("thorax_yaw", t)

    def thorax_roll(self, t):
        return self._get("thorax_roll", t)

    def pelvis_yaw(self, t):
        return self._get("pelvis_yaw", t)

    def pelvis_roll(self, t):
        return self._get("pelvis_roll", t)

    def loaded(self, t):
        return self._get("load", t)

    def soft_knee(self, t):
        return self._get("soft", t)

    def arm_out(self, t):
        return self._get("arm_out", t)

    def shift(self, t, upright_only=False):
        """Horizontal shift (n, 2) of the pelvis that keeps the centre of mass where it belongs.
        While the pelvis height is solved (upright_only) the part due to bending is left out."""
        s = np.stack([np.interp(t, self.shift_t, self.shift_xz[:, k]) for k in (0, 1)], -1)
        if upright_only:
            s = s * (1.0 - smoothstep(self.drop(t) / (0.3 * self.crouch_ref)))[:, None]
        return s


def slerp_to(Ra, Rb, w):
    """Rotation a share w (n,) of the way from Ra to Rb."""
    return Ra @ from_rotvec(to_rotvec(tr(Ra) @ Rb) * w[:, None])


class Rig:
    def __init__(self, script, p, q, window):
        self.s = script
        self.p, self.q = p, q
        self.ev = script.ev
        self.box = script.box
        self.hold = script.hold
        self.dur = script.plan.duration
        self.fix_t = np.array([window[0], window[1]])
        self.fix_y = np.zeros(2)     # extra height of the box where the arms would overstretch
        self.post = Posture(window[0], window[1])
        self._carry_height()
        self._posture_moves()
        script.plan.posture = self.post
        self.body = Body(script.plan, window)
        self.shapes = {s: HandShapes(s, gap=q["palm_gap"]) for s in ("L", "R")}
        self._grip()
        self._anchor_tables()
        fr = np.arange(0.0, min(self.ev["t0"], 0.5), 1.0 / 30.0)
        self.ref_com = self._free_reference(fr)

    # ================================================================== posture
    def _posture_moves(self):
        q, ev, post = self.q, self.ev, self.post
        m = self.box.mass
        f = self.s.tempo
        lean = q["lean_back"] + q["lean_back_kg"] * m
        th = q["trunk_pitch"]
        tau = q["pelvis_share"] * th
        a, b = ev["down0"], ev["bottom"]
        post.scale.update(pick=0.30, place=0.30)
        post.add("drop", a + 0.10 * f, b, 1.0, "pick")
        post.add("tilt", a + 0.02 * f, b - 0.08 * f, tau)
        post.add("thorax_pitch", a - 0.12 * f, b - 0.14 * f, th)
        # bracing: the hips start to rise and the arms straighten before the box moves
        c, d, e = ev["load0"], ev["lift0"], ev["lift1"]
        post.add("drop", c, d + 0.2 * f, -0.03, "pick")
        post.add("drop", d + 0.06 * f, e, -0.97, "pick", _lift_ease)
        post.add("tilt", d - 0.05 * f, e + 0.05 * f, -tau)
        post.add("thorax_pitch", d, e + 0.12 * f, -th - lean)
        # settling the load: the legs give a little as the box arrives, then push it back up
        hitch = q["hitch"] * min(1.5, m / 10.0)
        post.add("hitch", e - 0.10 * f, e + 0.16 * f, hitch)
        post.add("hitch", e + 0.12 * f, e + 0.42 * f, -hitch)
        post.add("load", c + 0.1 * f, d + 0.12 * f, 1.0)
        post.add("soft", d, e, q["carry_knee"])
        # put down
        g, h = ev["low0"], ev["touch"]
        post.add("drop", g, h, 1.0, "place", self._lower_ease)
        # (the trunk has to go forward with the box, or the arms cannot follow it out and down)
        post.add("tilt", g - 0.10 * f, h - 0.55 * f, tau)
        post.add("thorax_pitch", g - 0.15 * f, h - 0.60 * f, th + lean)
        post.add("load", h - 0.20 * f, h + 0.10 * f, -1.0)
        post.add("soft", g, h, -q["carry_knee"])
        r0, r1 = ev["rise0"], ev["rise1"]
        post.add("drop", r0, r1, -1.0, "place")
        post.add("tilt", r0 - 0.02 * f, r1 + 0.05 * f, -tau)
        post.add("thorax_pitch", r0 + 0.05 * f, r1 + 0.20 * f, -th)
        # the free arms pass outside the thighs while standing up
        post.add("arm_out", ev["away"], r0 + 0.45 * f, 10.0 * DEG)
        post.add("arm_out", r0 + 0.6 * f, r1 + 0.2 * f, -10.0 * DEG)
        # small asymmetries: nobody bends exactly straight
        post.add("thorax_yaw", a, b, 2.5 * DEG)
        post.add("thorax_roll", a, b, -1.5 * DEG)
        post.add("thorax_yaw", d, e, -2.5 * DEG)
        post.add("thorax_roll", d, e, 1.5 * DEG)
        post.add("thorax_yaw", g, h, -2.0 * DEG)
        post.add("thorax_roll", g, h, 1.2 * DEG)
        post.add("thorax_yaw", r0, r1, 2.0 * DEG)
        post.add("thorax_roll", r0, r1, -1.2 * DEG)
        post.rebuild()

    # ================================================================== the grip
    def _grip(self):
        """Palm contact points and hand rotations in the box's own frame."""
        q, box, hold = self.q, self.box, self.hold
        W, D, H = hold["width"], hold["depth"], box.h
        self.rel = box.start_yaw - hold["h_pick"]
        Rrel = ry(self.rel).T
        low = self.grip_low
        self.grip = {}
        phi = q["grip_finger"]
        for side, sg, dz, dy, dphi in (("L", 1.0, 0.012, 0.006, 2.0 * DEG), ("R", -1.0, -0.004, 0.0, -2.0 * DEG)):
            c = np.array([sg * 0.5 * W, -0.5 * H + low + dy, -0.5 * D + q["grip_near"] * D + dz])
            n = np.array([-sg, 0.0, 0.0])                 # palm normal, into the box
            fdir = np.array([0.0, -np.sin(phi + dphi), np.cos(phi + dphi)])
            thumb = sg * np.cross(n, fdir)
            rest_x = sg * fdir                            # the rest x axis points to the fingers (L)
            Wh = np.stack([rest_x, -n, thumb], -1)
            self.grip[side] = dict(c=Rrel @ c, W=Rrel @ Wh)

    def _carry_height(self):
        """Height of the box while carried, how far in front of the pelvis, and its tilt."""
        q = self.q
        H, D = self.box.h, self.hold["depth"]
        self.grip_low = float(np.clip(q["grip_low"] * H, q["grip_low_min"], q["grip_low_max"]))
        y_hand = min(q["carry_hand_y"], q["carry_top_max"] - (H - self.grip_low))
        self.y_carry = FLOOR + y_hand + 0.5 * H - self.grip_low
        self.fwd_carry = q["belly"] + q["carry_gap"] + 0.5 * D
        self.tilt_carry = q["carry_tilt"]

    def _lower_ease(self, s):
        """Lowering profile (s = 0..1 from low0 to touch): most of the way in one movement, then
        the last centimetres to the floor slowly, whatever the tempo."""
        s = np.clip(s, 0.0, 1.0)
        T = self.ev["touch"] - self.ev["low0"]
        a = self.q["final_height"] / max(self.y_carry - self.box.y_floor, 0.1)
        s_tail = 1.0 - self.q["final_time"] / T
        return (1.0 - a) * smootherstep(s / (s_tail + 0.3 * (1.0 - s_tail))) + a * smootherstep((s - s_tail) / (1.0 - s_tail))

    def lower_progress(self, t):
        return move(t, self.ev["low0"], self.ev["touch"], self._lower_ease)

    def w_arm(self, t, side):
        """Share of the IK solution in the arm pose."""
        ev = self.ev
        f = self.s.tempo
        lag = 0.05 if side == "R" else 0.0
        up = move(t, ev["down0"] + 0.05 * f + lag, ev["contact"] - 0.28 * f + lag)
        dn = move(t, ev["away"] + 0.05 * f + lag, ev["rise1"] - 0.30 * f + lag)
        return up * (1.0 - dn)

    def hand_offset(self, t, side):
        """How far the palm is outside the face of the box."""
        ev, q = self.ev, self.q
        f = self.s.tempo
        lag = 0.04 if side == "R" else 0.0
        come = 1.0 - move(t, ev["contact"] - 0.38 * f + lag, ev["contact"] + lag)
        leave = (move(t, ev["open0"] + 0.12 * f + lag, ev["away"] + 0.2 * f + lag)
                 + 0.7 * move(t, ev["away"] + 0.1 * f, ev["rise0"] + 0.5 * f))
        return q["hand_off"] * (come + leave)

    def hand_ride(self, t):
        """Before the hands touch the box and after they leave it the target of the arm moves
        up and down with the body, so the arms are not pulled straight."""
        post, ev = self.post, self.ev
        d = post.drop(t)
        return np.where(t < ev["contact"], np.maximum(post.scale["pick"] - d, 0.0),
                        np.where(t > ev["away"], np.maximum(post.scale["place"] - d, 0.0), 0.0))

    def fingers(self, t, side):
        """hand_pose (n, 15, 3)."""
        ev = self.ev
        f = self.s.tempo
        sh = self.shapes[side]
        lag = 0.04 if side == "R" else 0.0
        w_open = (move(t, ev["down0"] + 0.25 * f + lag, ev["contact"] - 0.15 * f + lag)
                  * (1.0 - move(t, ev["away"] + 0.15 * f + lag, ev["rise1"] - 0.2 * f + lag)))
        w_grip = (move(t, ev["contact"] - 0.14 * f + lag, ev["contact"] + 0.14 * f + lag)
                  * (1.0 - move(t, ev["open0"] + lag, ev["open0"] + 0.22 * f + lag)))
        a = w_open[:, None, None]
        b = w_grip[:, None, None]
        return (1.0 - b) * (a * sh.open + (1.0 - a) * sh.relaxed) + b * sh.grip

    # ================================================================== the box
    def _anchor_tables(self):
        b, q = self.body, self.q
        tg = self.post.tg
        dt = tg[1] - tg[0]
        sig = q["box_follow"] / dt
        self.A_t = tg
        # the box follows the upright pelvis (and the trunk when it leans into a start)
        psi = b.psi(tg)
        _, g, _ = b.envelopes(tg)
        _, lean_fwd = b.lean(tg)
        base = (b.com(tg) + self.post.shift(tg, upright_only=True)
                + (self.p["c_walk"] * np.minimum(g, 1.0) + 0.1 * np.maximum(lean_fwd, 0.0))[:, None] * hdir(psi))
        self.A_xz = gaussian_filter1d(base, sig, axis=0, mode="nearest")
        # it turns with the thorax, which leads the pelvis
        self.A_psi = gaussian_filter1d(b.psi(tg + self.p["thorax_lead_t"]), 1.3 * sig, mode="nearest")
        y = b.height(tg)
        self.y_ref = float(np.median(y[(tg > 0.0) & (tg < self.ev["t0"])]))
        self.A_y = gaussian_filter1d(y, 0.5 * sig, mode="nearest")

    def box_pose(self, t):
        """Box centre (n, 3) and rotation (n, 3, 3) at times t."""
        ev, q, box = self.ev, self.q, self.box
        t = np.asarray(t, dtype=float)
        xz = np.stack([np.interp(t, self.A_t, self.A_xz[:, k]) for k in (0, 1)], -1)
        psi = np.interp(t, self.A_t, self.A_psi)
        y = np.interp(t, self.A_t, self.A_y)
        anchor = xz + self.fwd_carry * hdir(psi)
        # (a held load is never perfectly still: slow small drifts of height and tilt)
        ya = (self.y_carry + q["box_bob"] * (y - self.y_ref) - self.post.hitch(t)
              + q["box_drift"] * np.sin(2.0 * np.pi * t / 3.3 + 0.8))
        yaw_a = psi + self.rel
        # lift: straight up first, towards the body afterwards
        lv = move(t, ev["lift0"], ev["lift1"], _lift_ease)
        lh = move(t, ev["lift0"] + 0.18 * (ev["lift1"] - ev["lift0"]), ev["lift1"])
        # put down: forwards first, the last part straight down
        pv = self.lower_progress(t)
        ph = move(t, ev["low0"] - 0.1, ev["low0"] + 0.55 * (ev["touch"] - ev["low0"]))
        xz_lift = (1.0 - lh)[:, None] * box.start_xz + lh[:, None] * anchor
        xz_all = (1.0 - ph)[:, None] * xz_lift + ph[:, None] * box.target_xz
        arc = q["lower_arc"] * np.sin(np.pi * np.clip((t - ev["low0"] + 0.1) / (ev["touch"] - ev["low0"] - 0.1), 0.0, 1.0)) ** 2
        xz_all = xz_all + arc[:, None] * hdir(psi)
        y_all = (1.0 - lv) * box.y_floor + lv * ya
        y_all = (1.0 - pv) * y_all + pv * box.y_floor + np.interp(t, self.fix_t, self.fix_y)
        # the same orientations as the task's, on the body's continuous heading scale
        yaw_0 = float(np.interp(ev["lift0"], self.A_t, self.A_psi)) + self.rel
        yaw_0 = box.start_yaw + np.round((yaw_0 - box.start_yaw) / (2.0 * np.pi)) * 2.0 * np.pi
        yaw_1 = float(np.interp(ev["low0"], self.A_t, self.A_psi)) + self.rel
        yaw_1 = box.target_yaw + np.round((yaw_1 - box.target_yaw) / np.pi) * np.pi
        yaw_all = (1.0 - lh) * yaw_0 + lh * yaw_a
        yaw_all = (1.0 - ph) * yaw_all + ph * yaw_1
        heading = yaw_all - self.rel
        held = lv * (1.0 - pv)
        tilt = (self.tilt_carry + 0.7 * DEG * np.sin(2.0 * np.pi * t / 4.3 + 2.0)) * held
        ph_g = self.s.plan.phase(t)
        sway = q["box_sway"] * held * np.minimum(self.s.plan.size_env(t), 1.0)
        Rb = (ry(heading) @ rx(tilt) @ rz(sway * np.sin(2 * np.pi * (ph_g + 0.08)))
              @ ry(self.rel + 0.8 * sway * np.cos(2 * np.pi * (ph_g + 0.05))))
        pos = np.stack([xz_all[:, 0], y_all, xz_all[:, 1]], -1)
        return pos, Rb

    # ================================================================== pose of a set of frames
    def pose(self, t):
        t = np.asarray(t, dtype=float)
        P0, R = self.body.pose_rotations(t)
        pos, Rb = self.box_pose(t)
        reach = self._arms(t, P0, R, pos, Rb)
        self._gaze(t, P0, R)
        return P0, R, pos, Rb, reach

    def _arms(self, t, P0, R, pos, Rb):
        q = self.q
        W3, P3 = _chain_to(P0, R, IDX["spine3"])
        reach = {}
        for side, arm in ARMS.items():
            sg = arm.sign
            w = self.w_arm(t, side)
            g = self.grip[side]
            Wh = Rb @ g["W"]
            C = pos + mv(Rb, g["c"])
            off = self.hand_offset(t, side)
            out = Wh[:, :, 1]
            C = C + (off + q["palm_gap"])[:, None] * out + (0.3 * off + self.hand_ride(t))[:, None] * UP
            wrist = C - mv(Wh, PALM[side])
            prot = (q["collar_reach"] * w)
            low = np.clip(self.post.drop(t) / self.post.crouch_ref, 0.0, 1.0)
            Rcol = R[:, arm.collar] @ ry(-sg * prot) @ rz(sg * (q["collar_up"] - (q["collar_up"] + q["collar_down"]) * low) * w)
            Wc = W3 @ Rcol
            Pc = P3 + mv(W3, J[arm.collar] - J[IDX["spine3"]])
            S = Pc + mv(Wc, J[arm.shoulder] - J[arm.collar])
            # Bent down, the elbows stay in for a narrow box (the forearms pass inside the knees).
            # Upright, they go out with a wide box: an elbow inside the plane of the held face
            # would take the forearm across the near corner of the box.
            width = self.hold["width"]
            p_low = np.array(q["pole_low"]) * np.array([np.clip((width - 0.2) / 0.2, 0.25, 1.0), 1.0, 1.0])
            p_up = np.array(q["pole_carry"]) * np.array([np.clip(1.0 + 6.5 * (width - 0.4), 1.0, 2.2), 1.0, 1.0])
            pl = (low[:, None] * p_low + (1.0 - low)[:, None] * p_up) * np.array([sg, 1.0, 1.0])
            pole = mv(W3, pl)
            Rs, Re, Rw, reach_q = arm.solve(S, Wc, wrist, Wh, pole)
            reach[side] = (np.linalg.norm(wrist - S, axis=-1) / arm.reach, reach_q)
            R[:, arm.collar] = Rcol
            R[:, arm.shoulder] = slerp_to(R[:, arm.shoulder], Rs, w)
            R[:, arm.elbow] = slerp_to(R[:, arm.elbow], Re, w)
            R[:, arm.wrist] = slerp_to(R[:, arm.wrist], Rw, w)
        return reach

    def _gaze_program(self, t):
        """Point looked at (n, 3) and how much the head turns to it (n,)."""
        ev = self.ev
        box = self.box
        f = self.s.tempo
        y_top = FLOOR + box.h
        p1 = np.array([box.start_xz[0], y_top, box.start_xz[1]])
        p2 = np.array([box.target_xz[0], FLOOR + 0.2 * box.h, box.target_xz[1]])
        w1 = (move(t, ev["stop1"] - 1.5, ev["stop1"] - 0.5) * 0.9
              * (1.0 - 0.75 * move(t, ev["lift0"] + 0.1 * f, ev["lift1"] - 0.1 * f))
              * (1.0 - move(t, ev["lift1"] - 0.2 * f, ev["walk2"])))
        w2 = (move(t, ev["stop2"] - 1.3, ev["stop2"] - 0.2) * 0.95
              * (1.0 - move(t, ev["rise0"] + 0.5 * f, ev["rise1"] + 0.1 * f)))
        pt = np.where((t < 0.5 * (ev["walk2"] + ev["stop2"]))[:, None], p1[None], p2[None])
        return pt, np.maximum(w1, w2)

    def _gaze(self, t, P0, R):
        pt, w = self._gaze_program(t)
        W3, P3 = _chain_to(P0, R, IDX["spine3"])
        Wn = W3 @ R[:, IDX["neck"]]
        Pn = P3 + mv(W3, J[IDX["neck"]] - J[IDX["spine3"]])
        Wh = Wn @ R[:, IDX["head"]]
        Ph = Pn + mv(Wn, J[IDX["head"]] - J[IDX["neck"]])
        eye = Ph + mv(Wh, np.array([0.0, 0.08, 0.09]))
        # the wanted head rotation, from the body's own heading (well defined when looking
        # straight down); the eyes do the last part of looking down
        Hh = ry(self.body.psi(t))
        d = np.einsum("nji,nj->ni", Hh, pt - eye)
        d[:, 1] *= 0.8
        Wd = Hh @ rot_between(np.broadcast_to(np.array([0.0, 0.0, 1.0]), d.shape), d)
        Wb = slerp_to(Wh, Wd, w)
        rv = to_rotvec(tr(W3) @ Wb)
        ang = np.linalg.norm(rv, axis=-1, keepdims=True)
        lim = 70.0 * DEG
        rv = rv * (lim * np.tanh(ang / lim) / np.maximum(ang, 1e-9))
        R[:, IDX["neck"]] = from_rotvec(rv * 0.55)
        R[:, IDX["head"]] = from_rotvec(rv * 0.45)

    # ================================================================== balance
    def _com(self, t, P0, R, pos):
        W, P = fk(P0 - J[0], R)
        m = self.box.mass * self.post.loaded(t)
        return total_com(W, P, pos, m), W, P

    def _free_reference(self, t):
        """Where the real centre of mass sits relative to the balance model's when standing
        freely, in the heading frame (forward, left)."""
        P0, R, pos, _, _ = self.pose(t)
        c, _, _ = self._com(t, P0, R, pos)
        d = c[:, [0, 2]] - self.body.com(t)
        psi = self.body.psi(t)
        return np.array([np.mean(np.sum(d * hdir(psi), -1)), np.mean(np.sum(d * lnorm(psi), -1))])

    def solve(self, passes=3):
        """Fit how low the body goes to the reach of the arms, and the pelvis shift to the balance."""
        ev, q, post, body = self.ev, self.q, self.post, self.body
        n = int(round(self.dur * 15)) + 1
        tf = np.linspace(0.0, self.dur, n)
        active = move(tf, ev["down0"] - 0.6, ev["down0"] + 0.1) * (1.0 - move(tf, ev["rise0"] + 0.2, ev["rise1"] + 0.2))
        moving = (move(tf, ev["lift0"], ev["lift0"] + 0.3) * (1.0 - move(tf, ev["lift1"] - 0.2, ev["lift1"] + 0.2))
                  + move(tf, ev["low0"] - 0.2, ev["low0"] + 0.2) * (1.0 - move(tf, ev["touch"] - 0.4, ev["touch"] - 0.1)))
        keys = (("pick", ev["contact"] + 0.05), ("place", ev["touch"]))
        for it in range(passes):
            for _ in range(3):
                tk = np.array([k[1] for k in keys])
                _, _, _, _, reach = self.pose(tk)
                r = 0.5 * (reach["L"][0] + reach["R"][0])
                for i, (tag, _) in enumerate(keys):
                    post.scale[tag] = float(np.clip(post.scale[tag] + 0.9 * (r[i] - q["reach_bottom"]) * ARMS["L"].reach,
                                                    0.0, 0.62))
                post.rebuild()
                self._reset()
            P0, R, pos, _, reach = self.pose(tf)
            c, _, _ = self._com(tf, P0, R, pos)
            psi = body.psi(tf)
            over = np.maximum(reach["L"][0], reach["R"][0]) - q["reach_max"]
            over = np.maximum(over, 0.0) * ARMS["L"].reach * moving
            self.fix_t = tf
            self.fix_y = (self.fix_y if len(self.fix_y) == len(tf) else np.zeros(len(tf)))
            self.fix_y = np.minimum(self.fix_y + 1.5 * gaussian_filter1d(over, 0.10 * 15, mode="nearest"),
                                    q["reach_fix_max"]) * moving
            # bent down the mass goes a little forward; walking, the load runs a little ahead of
            # the balance model (the pelvis cannot stay behind it: the leading foot would be out
            # of reach), standing it is fully balanced
            bent = smoothstep(post.drop(tf) / (0.15 * post.crouch_ref))
            standing = np.maximum(bent, 1.0 - body.envelopes(tf)[2])
            lead = (1.0 - q["walk_shift"]) * self.box.mass * self.fwd_carry / (BODY_MASS + self.box.mass)
            fwd = (self.ref_com[0] + q["crouch_fwd"] * smoothstep(post.drop(tf) / post.crouch_ref)
                   + lead * (1.0 - standing) * post.loaded(tf))
            want = body.com(tf) + fwd[:, None] * hdir(psi) + self.ref_com[1] * lnorm(psi)
            err = (c[:, [0, 2]] - want) * active[:, None]
            # standing: the error is removed closely; walking: only its slow part, the step by
            # step movement of the centre of mass belongs to the gait
            err = (standing[:, None] * gaussian_filter1d(err, 0.10 * 15, axis=0, mode="nearest")
                   + (1.0 - standing)[:, None] * gaussian_filter1d(err, 0.5 * 15, axis=0, mode="nearest"))
            old = np.stack([np.interp(tf, post.shift_t, post.shift_xz[:, k]) for k in (0, 1)], -1)
            post.shift_t = tf
            post.shift_xz = old - err
            self._reset()
            self._anchor_tables()
        body._solve_height()
        self._anchor_tables()

    def _reset(self):
        """Forget the swing paths: they depend on the pelvis, which has changed."""
        self.body._swing_cache = {}

    # ================================================================== output
    def generate(self, n_frames, fps):
        t = np.arange(n_frames) / float(fps)
        P0, R, pos, Rb, _ = self.pose(t)
        return dict(fps=int(fps), transl=P0 - J[0], global_orient=to_rotvec(R[:, 0]),
                    body_pose=to_rotvec(R[:, 1:]),
                    left_hand_pose=self.fingers(t, "L"), right_hand_pose=self.fingers(t, "R"),
                    object_transl=pos, object_orient=to_rotvec(Rb))


def _chain_to(P0, R, joint):
    """World rotation and position of a joint on the spine (pelvis -> spine1 -> spine2 -> spine3)."""
    chain = [IDX["spine1"], IDX["spine2"], IDX["spine3"]]
    W = R[:, 0]
    P = P0
    prev = 0
    for j in chain:
        P = P + mv(W, J[j] - J[prev])
        W = W @ R[:, j]
        prev = j
        if j == joint:
            break
    return W, P


def _lift_ease(s):
    """Lift profile: the box comes off the floor gently, then moves with the legs."""
    return smootherstep(np.clip(s, 0.0, 1.0) ** 1.15)


