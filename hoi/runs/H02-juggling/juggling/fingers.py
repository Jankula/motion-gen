"""Finger shapes for holding, catching and throwing balls of a given size.

Everything is solved for the left hand in the flat-hand rest pose of body_info.json (fingers along
+x, palm facing -y, thumb side +z), then mirrored.  A shape is the finger pose of SMPLX_INTERFACE.md:
the rotation of a joint is built from relaxed_pose + hand_pose, and here "absolute" means that sum.

A seat is the place of a ball's centre relative to the hand.  There are three: "one" for a single
ball, and "rear" and "front" for two balls lying one behind the other along the hand.

cup() closes each finger joint by joint, from the knuckle out, until the skin point on that bone
touches the ball: the same way a real finger closes around something.
"""
import numpy as np
from scipy.optimize import least_squares

from locomotion.rotations import DEG, from_rotvec
from manipulation.hand import NAMES, PALM, RELAXED, REST, SKIN, WRIST

FINGERS = ("index", "middle", "ring", "pinky")
THUMB = NAMES.index("left_thumb1")
_MIRROR = np.array([1.0, -1.0, -1.0])
_FLIP_X = np.array([-1.0, 1.0, 1.0])
PALM_NORMAL = np.array([0.0, -1.0, 0.0])    # out of the palm, in the hand's own frame
FINGER_DIR = np.array([1.0, 0.0, 0.0])      # towards the fingers, left hand
_REL = RELAXED["L"]


def _chain(i0, absolute):
    """World rotations and positions of the three joints of a finger; absolute (m, 3, 3)."""
    R = from_rotvec(absolute)
    W1 = R[:, 0]
    P1 = np.broadcast_to(REST[i0], (len(R), 3))
    P2 = P1 + W1 @ (REST[i0 + 1] - REST[i0])
    W2 = W1 @ R[:, 1]
    P3 = P2 + W2 @ (REST[i0 + 2] - REST[i0 + 1])
    W3 = W2 @ R[:, 2]
    return (P1, P2, P3), (W1, W2, W3)


def _skin(i0, absolute, name):
    """Position (m, 3) of a skin point of the finger starting at joint i0."""
    x, j = SKIN["left_" + name]
    P, W = _chain(i0, absolute)
    k = j - i0
    return P[k] + np.einsum("mij,j->mi", W[k], x - REST[j])


def _start(i0, spread, keep):
    """Absolute pose of a straight finger; keep = share of the relaxed side and twist rotations."""
    a = _REL[i0:i0 + 3] * np.array([keep, keep, 0.0])
    a[0, 1] += spread
    return a


def _close(a, i0, joint, points, C, want, lo, hi):
    """Bend one joint of a finger until the first of its skin points touches the sphere."""
    ang = np.linspace(lo, hi, 72)
    cand = np.repeat(a[None], len(ang), 0)
    cand[:, joint, 2] = -ang
    d = np.min([np.linalg.norm(_skin(i0, cand, p) - C, axis=-1) for p in points], axis=0)
    hit = np.nonzero(d <= want)[0]
    if len(hit) == 0:
        pick = int(np.argmin(d))
    elif hit[0] == 0:
        pick = 0
    else:
        i = int(hit[0])
        f = (d[i - 1] - want) / max(d[i - 1] - d[i], 1e-9)
        a[joint, 2] = -(ang[i - 1] + f * (ang[i] - ang[i - 1]))
        return
    a[joint, 2] = -ang[pick]


def wrap_finger(name, C, r, spread, press=0.001, keep=0.6, limits=None, equator=0.004):
    """Absolute pose (3, 3) of a finger closed around a ball of radius r at C."""
    i0 = NAMES.index("left_%s1" % name)
    a = _start(i0, spread, keep)
    want = r - press
    lim = limits or ((-12.0, 80.0), (6.0, 95.0), (4.0, 70.0))
    _close(a, i0, 0, ["%s1_pad" % name], C, want, lim[0][0] * DEG, lim[0][1] * DEG)
    _close(a, i0, 1, ["%s2_pad" % name], C, want, lim[1][0] * DEG, lim[1][1] * DEG)
    _close(a, i0, 2, ["%s3_pad" % name, "%s_tip" % name], C, want, lim[2][0] * DEG, lim[2][1] * DEG)
    # an open cup: a ball lies in a hand, so the finger ends stay below the ball's equator.  (The
    # palm side is -y in this frame: "below" the ball means a larger y.)  Open the last joints until
    # the tip is there.
    for joint in (2, 1):
        floor_angle = lim[joint][0] * DEG
        while _skin(i0, a[None], "%s_tip" % name)[0, 1] < C[1] + equator and -a[joint, 2] > floor_angle:
            a[joint, 2] = min(a[joint, 2] + 2.0 * DEG, -floor_angle)
    return a


def wrap_thumb(C, r, flesh=0.0135, press=0.0, equator=0.006):
    """Absolute pose (3, 3) of the thumb lying along the side of a ball.

    A thumb is thick: the skin of its pad lies about 1.4 cm from the line of its bones.  So the bone
    line has to stay that far outside the ball (measured on the mesh with tools/seat_probe.py: a thumb
    fitted by its pad points alone went 2 cm through the ball), and only the end of the thumb
    reaches for the surface."""
    x0 = np.array([_REL[THUMB][0], _REL[THUMB][1], _REL[THUMB][2], _REL[THUMB + 1][0], _REL[THUMB + 2][0]])
    tip_x, tip_j = SKIN["left_thumb_tip"]

    def pose(x):
        a = _REL[THUMB:THUMB + 3].copy()
        a[0] = x[:3]
        a[1, 0] = x[3]
        a[2, 0] = x[4]
        return a

    def resid(x):
        a = pose(x)[None]
        (P1, P2, P3), (_, _, W3) = _chain(THUMB, a)
        end = P3[0] + W3[0] @ (tip_x - REST[tip_j])
        line = [P1[0] + f * (P2[0] - P1[0]) for f in (0.5, 1.0)]
        line += [P2[0] + f * (P3[0] - P2[0]) for f in (0.5, 1.0)]
        line += [P3[0] + f * (end - P3[0]) for f in (0.5, 0.8)]
        d = np.linalg.norm(np.array(line) - C, axis=-1)
        barrier = np.maximum(r + flesh - d, 0.0) / 0.0015
        reach = (np.linalg.norm(_skin(THUMB, a, "thumb3_pad")[0] - C) - (r - press)) / 0.008
        over = max(C[1] + equator - end[1], 0.0) / 0.002        # the thumb stays below the equator too
        return np.concatenate([barrier, [reach, over], 0.2 * (x - x0)])

    res = least_squares(resid, x0, max_nfev=60)
    return pose(res.x)


def rest_on_fingers(Cr, r, q, spreads):
    """Where a second ball comes to rest in front of the ball at Cr.

    It touches the rear ball, so it can only roll around it; it is laid down until it lies on the
    finger pads of a shallow tray.  This holds for any ball size: the ball can neither float
    above the fingers nor sink into them."""
    pads = []
    for f in FINGERS:
        i0 = NAMES.index("left_%s1" % f)
        a = _start(i0, spreads[f] * DEG, 0.6)
        a[:, 2] = -np.array(q["tray"])
        for n in ("%s1_pad", "%s2_pad", "%s3_pad", "%s_tip"):
            pads.append(_skin(i0, a[None], n % f)[0])
    pads = np.array(pads)
    rise = np.linspace(-10.0, 60.0, 141) * DEG
    C = Cr + (2.0 * r + q["two_space"]) * np.stack([np.cos(rise), -np.sin(rise), 0.0 * rise], -1)
    d = np.linalg.norm(C[:, None] - pads[None], axis=-1).min(1)
    # the skin at the bases of the fingers stands higher than the pad points, so the ball has to stay
    # clear of the pads by an amount that depends on its size (measured: tools/seat_by_radius.py two)
    table = np.array(q["tray_gap"])
    clearance = float(np.interp(r, table[:, 0], table[:, 1]))
    ok = np.nonzero(d >= r + clearance)[0]
    return C[ok[0]] if len(ok) else C[-1]


class BallHand:
    """Seats and finger shapes for one ball size."""

    def __init__(self, radius, q):
        self.r = r = radius
        base = PALM["L"] + WRIST["L"]    # palm centre, flat-hand rest coordinates
        lift = np.array([0.0, -(r + q["seat_gap"]), 0.0])
        across = np.array([0.0, 0.0, q["seat_across"]])
        # measured with tools/seat_by_radius.py: a large ball runs into the bases of the fingers, so
        # it has to lie further back in the palm
        big = np.clip((r - q["seat_big_from"]) / (q["seat_big_to"] - q["seat_big_from"]), 0.0, 1.0)
        along = q["seat_along"] + big * (q["seat_along_big"] - q["seat_along"])
        C1 = base + lift + across + np.array([along, 0.0, 0.0])
        Cr = base + lift + across + np.array([q["rear_along"], 0.0, 0.0])
        spreads = dict(index=3.0, middle=0.0, ring=-2.0, pinky=-5.0)
        Cf = rest_on_fingers(Cr, r, q, spreads)
        self.centres = {"one": C1, "rear": Cr, "front": Cf}
        self.seat = {k: {"L": v - WRIST["L"], "R": (v - WRIST["L"]) * _FLIP_X} for k, v in self.centres.items()}
        # from the single seat to the front seat, for a hand held palm up with the fingers forward
        d = Cf - C1
        self.front_offset = np.array([0.0, -d[1], d[0]])

        one = _REL.copy()
        for f in FINGERS:
            i = NAMES.index("left_%s1" % f)
            one[i:i + 3] = wrap_finger(f, C1, r, spreads[f] * DEG, press=q["finger_press"])
        one[THUMB:THUMB + 3] = wrap_thumb(C1, r)

        two = _REL.copy()
        for f in FINGERS:
            i = NAMES.index("left_%s1" % f)
            # a shallow tray: the fingers lie under the front ball and do not curl over it
            two[i:i + 3] = wrap_finger(f, Cf, r, spreads[f] * DEG, press=q["finger_press"] - 0.003, limits=(
                (-12.0, 60.0), (6.0, q["two_wrap"] / DEG), (4.0, 0.6 * q["two_wrap"] / DEG)))
        two[THUMB:THUMB + 3] = wrap_thumb(Cr, r)

        # the hand before a catch: the same cup, opened; after a release: the fingers stretch
        ready = one.copy()
        flick = one.copy()
        for f in FINGERS:
            i = NAMES.index("left_%s1" % f)
            ready[i:i + 3, 2] = one[i:i + 3, 2] * np.array([0.72, 0.62, 0.62])
            ready[i, 1] = one[i, 1] * 1.5
            flick[i:i + 3, 2] = np.array([-6.0, -16.0, -10.0]) * DEG
            flick[i, 1] = one[i, 1] * 1.4
        ready[THUMB:THUMB + 3] = one[THUMB:THUMB + 3] + 0.28 * (_REL[THUMB:THUMB + 3] - one[THUMB:THUMB + 3])
        flick[THUMB:THUMB + 3] = one[THUMB:THUMB + 3] + 0.65 * (_REL[THUMB:THUMB + 3] - one[THUMB:THUMB + 3])

        self.shapes = {}
        for side, mirror in (("L", np.ones(3)), ("R", _MIRROR)):
            self.shapes[side] = {name: a * mirror - RELAXED[side]
                                 for name, a in (("one", one), ("two", two), ("ready", ready), ("flick", flick))}

    def offset(self, side, seat):
        """Ball centre relative to the wrist joint, in the frame of the hand."""
        return self.seat[seat][side]
