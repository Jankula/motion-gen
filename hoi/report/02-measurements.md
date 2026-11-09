# How results are measured

This page covers the box experiments first, then [juggling](#juggling). As in the walking series, every motion is judged in two ways: **measurements** on the real body mesh, and **watching the videos**. The measurements are computed by [`hoienv/evaluate.py`](../hoienv/evaluate.py), and the agent can run the same tool on its own work. In the reports, each measurement appears with a ✅ (target met), ❌ (target missed), or no mark (information only).

All the [walking measurements](../../walking/report/02-measurements.md) still apply: sinking into the floor, foot sliding, standing still at start and end, and joint speed. The ones below are added for handling an object.

Most of them exist to catch one specific way of faking the interaction. Because nothing in the setup forces the box to behave like a real object (see [the setup page](01-setup.md#who-moves-the-object)), the measurements have to do that job.

## How the phases are found

The tool does not ask the agent when the box was picked up. It finds out from the box itself:

- the **carry** starts in the first frame in which the box is more than 3 mm or 1° from its starting pose;
- the carry ends in the last frame in which the box is more than 3 mm or 1° from its final pose;
- **touchdown** is the first frame after which the bottom of the box stays within 5 mm of the floor.

## Grip

A hand counts as "touching" where its skin is within 8 mm of the box surface, and it can no longer be holding the box if it is more than 1.5 cm away.

| Measurement | What it means | Target | What it catches |
|---|---|---|---|
| The box starts where the task says | Distance of the box in the first frame from its required position | ≤ 5 mm | A box placed wherever is convenient |
| Hands on the box before it moves | How long both hands touch the box before it starts moving | ≥ 0.15 s | A box that jumps up the instant a hand arrives. People take hold first, then lift. |
| Frames the box moves without both hands on it | Frames with a moving box and a hand more than 1.5 cm away | 0 | A box that moves by itself |
| Largest gap between a hand and the box while carrying | The worse hand at its worst moment | ≤ 10 mm | Hands that hover next to the box |
| Deepest hand skin inside the box | How far hand skin goes into the box at any time | ≤ 10 mm | Fingers passing through the box. A few millimetres are allowed because skin is soft. |
| Fewest hand skin points touching the box | While carrying, the smallest number of skin points of a hand within 8 mm of the box | ≥ 40 | A box touched with one fingertip. We measured the reference on the real mesh: a flat hand on a flat surface gives 41 points, or 86 when pressed in by 4 mm; a single fingertip gives at most 28. |
| Hands sliding over the box while carrying | How far the touching skin moves over the box surface | ≤ 2 cm | Hands that are not really holding on |
| How opposite the two hands are | The angle at the box's centre between the two hands, at its smallest; 180° means exactly opposite | ≥ 120° | Hands resting on top of the box or on the same side, which could not carry it |

## The box in the air

| Measurement | What it means | Target | What it catches |
|---|---|---|---|
| Highest the bottom of the box gets | Largest height of its lowest corner | ≥ 20 cm | A box that is not really picked up |
| Frames the box slides along the floor | Frames in which it stands on the floor but moves sideways | 0 | Dragging |
| Deepest the box goes into the floor | Lowest corner below the floor | ≤ 3 mm | Sinking |
| Largest tilt of the box while carrying | How far its top leans from horizontal | ≤ 15° | A box held at an odd angle |
| Fastest the box moves | Its highest speed | ≤ 2 m/s | Jumps |
| Strongest acceleration of the box | Largest change of speed, smoothed over 0.17 s | ≤ 5 m/s² | A heavy box that is jerked around as if it weighed nothing. At 10 kg, 5 m/s² takes a 50 N push on top of its weight. |

## Putting it down

| Measurement | What it means | Target | What it catches |
|---|---|---|---|
| Distance from the marked spot | Final position of the box against the target, seen from above | ≤ 10 cm | Missing the spot |
| Final rotation error of the box | Final rotation against the marked one; turned by 180° counts as the same | ≤ 15° | |
| The box stands on the floor at the end | Height of its lowest corner in the last frame | ≤ 3 mm | A box left floating |
| Final tilt of the box | How far it leans | ≤ 1° | A box left leaning |
| Speed at touchdown | Downward speed in the last 0.1 s before it reaches the floor | ≤ 0.15 m/s | Dropping. A fall from just 10 cm would be 1.4 m/s. This measurement is the "carefully" of the task. |
| Hands stay on the box after it lands | Time from touchdown to the first hand leaving | ≥ 0.1 s | Letting go too early |
| Hands off the box at the end | Distance from the box to the closer hand in the last frame | ≥ 5 cm | Never letting go |
| Standing up at the end | Head height in the last frame, as a share of its height in a straight stance | ≥ 96 % | Staying bent down |

## Body

| Measurement | What it means | Target | What it catches |
|---|---|---|---|
| Deepest body skin (not hands) inside the box | How far torso, arms, legs or feet ever go into the box | ≤ 15 mm | A box carried through the chest, or feet walking through it. A little is allowed for soft tissue. |
| Deepest forearm or hand skin inside the trunk or legs | How far forearms and hands go into the body | ≤ 15 mm | Arms passing through the body. This check did not exist in the walking experiments, and carrying something close to the body makes it matter. |
| Knees and elbows bending the wrong way | How far a knee or elbow ever bends backwards | ≤ 5° | Broken joints from solving the arm or leg position |
| Largest wrist rotation | Total rotation of a wrist | ≤ 85° | Wrists twisted beyond what a real wrist can do |

The forearm check works like this: for every skin point of a forearm or hand, it finds the nearest skin point of the trunk or legs and checks which side of that skin it is on. It is an approximation, and it is the only one of these measurements that does not come directly from an exact distance to a surface.

## Balance

This is the measurement that gives the box real weight. A person who bends over and lifts 10 kg far from the body would fall forward, so the box's weight has to change how the person stands.

We compute the **centre of mass** of the whole body from the volume of the mesh (76 kg at the density of water) and add the box while it is held. We then look down from above and check whether that combined point lies inside the outline of the feet on the floor. Only frames in which both feet are down and the body moves slowly count: during walking, the centre of mass legitimately leaves the feet with every step.

| Measurement | What it means | Target |
|---|---|---|
| Frames off balance with both feet down | Frames in which the point is more than 3 cm outside the outline of the feet | 0 |
| Worst balance margin | The largest distance outside the outline in those frames; negative means it always stayed inside | information |

This is a simplification: real balance also depends on the forces of acceleration. It is meant to catch clear errors, not to replace a physical simulation.

## How the weight shows

These numbers have no target. They describe how the person handles the load and whether the weight changes anything, and they are the first thing to compare with what a real person would do.

| Measurement | What it means |
|---|---|
| Lowest pelvis height | How far the person goes down. Standing is 0.95 m. A low pelvis means bent knees. |
| Trunk lean at the grip | Forward lean of the trunk (pelvis to neck) when the lift begins. A large lean with a high pelvis means lifting by bending the back. |
| Walking speed without / with the box | Typical speed on the way to the box, and while carrying it |
| Trunk lean without / with the box | Typical lean while walking. Negative means leaning back against the load. |
| Box centre in front of the chest while carrying | How far from the body the box is held |
| Height of the box centre while carrying | How high it is carried |

## Juggling

From H02 on, a task can have balls instead of a box. All the walking measurements still apply, and the ones below replace the box measurements. They are computed by [`hoienv/juggling.py`](../hoienv/juggling.py). As with the box, nothing in the setup moves a ball, so a ball could float, change speed in the air or appear in a hand. These measurements are what stops that.

### How throws and catches are found

The tool does not ask the agent when a ball is thrown. It finds out from the motion itself:

- a ball is **held** while skin on the palm side of a hand stays within 1.5 cm of it for at least 0.1 s. The back of the hand does not count;
- everything between two holds is a **flight**;
- every flight is compared with a **free fall**: a ball in the air moves in a straight line seen from above, and up and down along a parabola set by gravity. The tool fits this curve to the flight;
- the exact moments of the **release** and the **catch** are the first and last frames that lie on this curve.

The measuring tool also writes `motion.throws.csv`, with one line for every flight, so that a single bad throw can be found.

### Holding the balls

| Measurement | What it means | Target | What it catches |
|---|---|---|---|
| Frames at the start / at the end without all balls in the hands | During the first and last 0.5 s | 0 | Balls that are not held at the start or the end |
| Frames with more than two balls in one hand | | 0 | One hand holding everything |
| Narrowest contact between a hand and a held ball | Width of the palm-side skin within 8 mm of the ball, at its smallest | ≥ 5 cm | A ball balancing on a fingertip |
| Ball-frames in which a held ball has no support from below | The touching skin must lie below the ball's centre on average | 0 | A ball that sticks to a hand or hangs under it. This is the lesson of H01, where no measurement asked for support from below. |
| Deepest hand skin inside a ball | | ≤ 8 mm | Fingers passing through a ball |

**How the contact target was calibrated.** We first planned to count touching skin points, as for the box. Measured on the real mesh, that turned out to be useless: a ball on one fingertip gives 43–57 points, as many as a ball in the palm (44), because the mesh is very fine at the fingertips. The *width* of the contact separates them clearly: a ball in the palm or on the fingers gives 5.9–7 cm, a ball on a fingertip 3.8–4.4 cm.

### The balls in the air

| Measurement | What it means | Target | What it catches |
|---|---|---|---|
| Largest gravity error of a flight | The gravity that fits the flight, against the real 9.81 m/s² | ≤ 3 % | Balls that float or fall too fast |
| Largest difference between a flight and a free fall | Average distance from the best curve with real gravity, for the worst flight | ≤ 3 mm | Balls that steer, slow down, hang or jump in the air |
| Flights too short to be a throw | Flights under 0.17 s | 0 | Balls hopping out of a hand and back |
| Balls that are never caught | Flights that do not end in a hand | 0 | Dropped balls |
| Lowest throw | Rise above the height of the release | ≥ 20 cm | Balls passed from hand to hand and not thrown |
| Highest point of any ball | Above the floor | ≤ 2.1 m | Balls leaving the picture |
| Fastest ball | | ≤ 6 m/s | Jumps |
| Deepest two balls go into each other | | ≤ 2 mm | Balls passing through each other, in the air or in a hand |
| Deepest body skin (not hands) inside a ball | | ≤ 8 mm | Balls flying through the arms, chest or head |

### Throwing and catching

| Measurement | What it means | Target | What it catches |
|---|---|---|---|
| Throws before the foot lifts / on one foot | | set by the task (9 / 12) | Too little juggling |
| Throws of the least thrown ball | | a third of the two numbers above | A ball that does not take part |
| Throws from the other hand than the throw before | | ≥ 95 % | One hand doing everything |
| Throws caught by the other hand | | ≥ 95 % | Not the classic pattern |
| Longest time between two throws | | ≤ 0.6 s | A pattern that stops, for example when the foot lifts |
| Largest jump in a ball's speed at the release | Speed just before and just after it leaves the hand | ≤ 1.5 m/s | A ball shooting out of a hand that is hardly moving. The hand has to bring the ball up to speed. |
| Largest jump in a ball's speed at the catch | Speed just before and just after it is caught | ≤ 2.5 m/s | A hand that stands still and stops the ball dead, which would be a jump of about 3 m/s. A real hand gives way and goes down with the ball. |
| Shortest time a ball stays in a hand | From catch to next throw | ≥ 0.12 s | A ball that bounces off the hand |

### Standing on one foot

| Measurement | What it means | Target | What it catches |
|---|---|---|---|
| Times the foot leaves the floor | | 1 | A foot that touches down in between |
| Frames the standing foot is off the floor | | 0 | Standing on the wrong foot, or hopping |
| Time on one foot | | set by the task (5 s) | Too short |
| Typical height of the lifted foot | Height of its lowest skin | ≥ 10 cm | A foot that only hovers |
| Time from the last catch to the foot coming down | | ≥ 0.2 s | The wrong order: the task says catch first, then put the foot down |
| All balls in the hands when the foot comes down | | yes | Juggling on after the foot is down |
| Frames off balance on one foot | The centre of mass more than 2 cm outside the outline of the standing foot, seen from above | 0 | A person who would fall over. The weight has to be over the foot before the foot lifts. |
| Frames off balance on two feet | As for the box, more than 3 cm outside the outline of the feet | 0 | |
| Largest distance of the pelvis from where it starts | | ≤ 20 cm | Walking away. The person stays in one place. |
| Standing up at the end | Head height against a straight stance | ≥ 96 % | |

The weight of the balls is left out of the balance: together they weigh about 0.5 % of the body and move the centre of mass by about 2 mm.

The checks for arms inside the body, joints bending the wrong way and wrist rotation are the same as for the box.

### How the juggling looks

These numbers have no target. They describe the juggling and are the first thing to compare with a real person: throws per second, time in the air, time in a hand, height of the throws, how much the height and the rhythm vary, and how much the centre of mass sways on one foot. Variation of exactly 0 is a warning sign, because no person is that regular.

## What the measurements cannot tell

As in the walking series, numbers cannot say whether the movement looks natural. In particular, they cannot judge whether the effort looks right, whether the timing of the lift feels heavy, whether the fingers look as if they are gripping, or whether juggling looks relaxed and alive. H01 showed this clearly: its grip met every target and still looked wrong. Each experiment page lists the moments to check in the videos.
