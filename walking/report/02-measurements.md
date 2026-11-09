# How results are measured

Every motion is judged in two ways: **measurements** computed on the real body mesh, and **watching the videos**. The measurements catch the problems that numbers can catch reliably (feet sinking into the floor, sliding feet, leaving the path, walking into furniture, glitches). Watching catches what numbers cannot: whether the movement looks natural.

The measurements are computed by [`walkenv/evaluate.py`](../walkenv/evaluate.py). From E02 on, the agent can run the same tool on its own work. In the reports, each measurement appears in a table with a ✅ (target met), ❌ (target missed), or no mark (information only).

All measurements are made on the **skin** (the 10,475 mesh points), not on the skeleton. This matters: the skeleton can look fine while a heel goes through the floor.

## Ground contact

| Measurement | What it means | Target | Why this target |
|---|---|---|---|
| Deepest sinking into the floor | How far any point of the skin ever goes below the floor over the whole clip | ≤ 10 mm | A few millimetres are invisible; a centimetre starts to show as a foot sinking into the floor. |
| Frames sinking more than 1 cm | How many frames have some skin more than 1 cm below the floor | 0 | |
| Frames with nothing on the floor | Frames where no part of the body is within 2 cm of the floor | 0 | In walking, at least one foot is always on the ground (unlike running). A frame with both feet in the air means the body is floating. |

## Foot sliding

A foot that carries weight must stay where it is. In animation, feet that slide ("foot skating") are one of the most visible errors.

We take every point of the foot skin that touches the floor (within 5 mm) in two frames in a row, and measure how far it moved along the floor between them.

| Measurement | What it means | Target | Why |
|---|---|---|---|
| Typical speed of floor-touching skin | The median of those speeds | ≤ 1 cm/s | A planted foot should not move, so this should be close to zero. |
| Speed of floor-touching skin, 95th percentile | 95 % of floor-touching points move slower than this; it captures brief slips | ≤ 3 cm/s | Slight rolling of the heel and toes is natural and shows up here as small values. A foot that pivots on its ball while turning on the spot also raises this value legitimately. |

## Path, speed and poses

| Measurement | What it means | Target |
|---|---|---|
| Distance travelled by the pelvis | Length of the pelvis track seen from above, with the small side-to-side sway of each step smoothed out | information |
| Average speed | Distance travelled divided by the clip length, pauses included. Comfortable adult walking is about 1.2–1.4 m/s. | information |
| Average / largest distance from the path | How far the pelvis (seen from above) is from the marked path: on average, and at its worst moment | within the tolerance given in the task (0.15 m for smooth paths, 0.3 m where the path has sharp corners, which people round off) |
| Start / end position error | Distance between the pelvis and the required position in the first or last frame | ≤ 15 cm |
| Start / end heading error | Difference between the direction the pelvis faces and the required direction | ≤ 15° |
| Pelvis speed while standing | Fastest pelvis movement during the first or last 0.5 s, when the task says the person stands still | ≤ 10 cm/s (a standing person sways slightly) |

## Obstacles

Obstacles are boxes (cabinets, walls, furniture). For each one:

| Measurement | What it means | Target |
|---|---|---|
| Closest approach | Smallest distance between any point of the skin and the box over the whole clip. Negative means the body goes into the box. | > 0 cm |
| Frames touching | Frames in which some skin is inside the box | 0 |

## Smoothness

| Measurement | What it means | Target |
|---|---|---|
| Fastest joint rotation | The fastest any joint rotates between two frames, and which joint. In walking, the knee of the swinging leg is the fastest joint, at roughly 400–600 degrees per second. | ≤ 800 °/s |
| Frames with a pop | Frames where some joint rotates faster than 1,500 °/s, which shows up as a visible jump | 0 |

## What the measurements cannot tell

The measurements say nothing about whether the movement *looks* human. A motion can meet every target and still look robotic, so each report also includes what we see in the videos. We look in particular at:

- the walking rhythm and how the feet roll (heel first, then the whole foot, then pushing off with the toes);
- arm swing (opposite to the legs) and how the upper body moves with the steps;
- how starting, stopping and turning are done, including where the feet are placed;
- whether arms or legs pass through each other (not measured yet; see below);
- whether anything looks mechanical, too regular, or stiff.

**Known gap:** body parts passing through *each other* (for example a hand going through the thigh) are not measured automatically yet. We check this by eye.
