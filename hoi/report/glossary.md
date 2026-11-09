# Glossary

Terms specific to the object experiments, in plain words. Walking, animation and agent terms (step, stance, inverse kinematics, turn, session, ...) are explained in the [walking glossary](../../walking/report/glossary.md).

## Handling an object

| Term | Meaning |
|---|---|
| **HOI** | Human-object interaction: a person doing something with an object, as opposed to moving on their own. |
| **Grip / grasp** | How the hands hold the object: where they touch it and how the fingers are shaped around it. |
| **Contact** | Here: hand skin within 8 mm of the object's surface. |
| **Interpenetration** | One thing passing through another, for example fingers through the box. Small amounts are allowed because skin and clothes give way. |
| **Opposing grip** | Holding an object by pressing on two opposite sides. The force between the hands creates the friction that keeps it from falling. |
| **Squat lift** | Lifting with bent knees and a fairly upright back, so that the legs do the work. |
| **Stoop lift** | Lifting with fairly straight legs by bending at the waist. |
| **Touchdown** | The moment the object reaches the floor as it is set down. |
| **Release** | The moment the hands let go. |
| **Target** | The marked spot on the floor where the object has to end up. |

## Balance and weight

| Term | Meaning |
|---|---|
| **Centre of mass** | The point where all of a body's weight can be thought to act. A person standing still does not fall over as long as this point is above the area between the feet. |
| **Support outline** (support polygon) | The outline around everything touching the floor, seen from above. In these reports, the outline of the feet. |
| **Counterbalance** | Moving part of the body the other way to make up for a load: for example, leaning back while holding a box in front. |
| **Physics engine** | A program that simulates forces, gravity and collisions. We do not use one: the agent writes down all movement itself, which is why the measurements check that the box behaves like a real object. |

## Juggling

| Term | Meaning |
|---|---|
| **Cascade** | The classic three-ball pattern: the hands take turns, and every ball crosses from one hand to the other. |
| **Throw / release** | The moment a ball leaves the hand. The hand has already brought it up to speed. |
| **Catch** | The moment a hand takes a falling ball. A real hand gives way and moves down with the ball. |
| **Flight** | The time a ball spends in the air between two hands. |
| **Free fall** | How anything moves in the air when only gravity acts on it: in a straight line seen from above, and along a parabola up and down. Air resistance is too small to matter here. |
| **Parabola** | The curve of a free fall. It is fixed completely by where and how fast the ball leaves the hand. |
| **Dwell time** | How long a ball stays in a hand between a catch and the next throw. |
| **Standing foot** | The foot that stays on the floor while the other one is lifted. |
| **Weight shift** | Moving the body over the standing foot. It has to happen before the other foot leaves the floor, or the person falls over. |

## The hand in SMPL-X

| Term | Meaning |
|---|---|
| **Finger joints** | Each hand has 15: three for each finger, numbered from the knuckle (1) to the last bone (3). |
| **Relaxed hand** | What the hand looks like when the agent gives no finger rotation: slightly curled. SMPL-X adds this curl to whatever the agent asks for. |
| **Flat hand** | Fingers straight, palm down. Reached by cancelling the relaxed curl. |
| **Finger pad** | The soft palm side of a finger bone, which does the touching. |

## The experiment setup

| Term | Meaning |
|---|---|
| **Unseen task** | A task file the agent never saw, run through its finished program afterwards. It shows whether the program is general or only works for the numbers it was developed on. |
| **Timeline** | The file `motion.timeline.csv`, with contact and balance numbers for each frame, which shows *when* something goes wrong. |
| **Fake** | Here: a clip deliberately broken to test the measuring tool, for example a box that floats away from the hands. |
| **Reference clip** | A plain but correct juggling clip that we built to test the measuring tool. It has to meet every target. The agent never sees it. |
