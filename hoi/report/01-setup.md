# How an experiment works

The experiments here use the same setup as the walking series, which is explained in full on the [walking setup page](../../walking/report/01-setup.md): what SMPL-X is, what the agent is, how a run goes from start to finish. This page explains only what is different when a person handles an object.

## What is new compared with walking

| | Walking experiments (E01–E04) | Object experiments (H01 onwards) |
|---|---|---|
| **What the agent controls** | Position, orientation and 22 joints of the body | The same, plus 30 finger joints, plus the position and orientation of the object for every frame |
| **What the agent knows about the body** | Joints of the body, feet, torso size | The same, plus the finger joints and points on the skin of the hands |
| **Cameras** | Six | Eight: the same six plus two close-ups of the hands |
| **Measurements** | Feet, path, obstacles, smoothness | The same, plus hands on the object, behaviour of the object, setting it down, arm and body collisions, balance with the extra weight. See [How results are measured](02-measurements.md). |
| **Previews** | 8 per experiment | 12 per experiment, because the hands need their own close looks |
| **Methods allowed** | The agent's own knowledge, numpy and scipy | The same, and explicitly any method it can build with them (inverse kinematics, optimisation, physical simulation), plus all earlier agent code |

## Who moves the object?

Nothing in the setup moves the box for the agent. There is no physics engine: the agent writes down where the box is in every frame, just as it writes down the body's joints. Gravity does not pull the box down, and nothing attaches it to the hands.

This has an important consequence. The agent could simply write down a box that follows the hands perfectly while the person moves as if it weighed nothing. A video of that would look wrong, but no program would stop it. This is why the measurements check that the box behaves like a real object and that the person's balance accounts for its weight.

## What the agent is and is not told

The agent is told what the person has to do, what the box weighs and what viewers will look for. It is **not** told how to lift: nothing in the prompt mentions bending the knees, keeping the back straight, carrying the box close to the body or slowing down. Whether it produces those things is part of what we want to find out.

The agent is also told that its program will be tried afterwards on a layout it has not seen, so that it writes a general program and not one that only works for one set of numbers. The unseen task is [`tasks/box-carry-variant.json`](../tasks/box-carry-variant.json). After the session, we copy it to `runs/<ID>/unseen/task.json`, run the agent's unchanged `make_motion.py` on it, and measure and render the result in that folder.

The agent's session is also kept apart from everything else. It only has its own folder, and since H02 it also runs with Claude Code's project memory switched off, so that it cannot see notes kept about this project. In H02 itself the memory was still on: see [what went wrong in the setup](experiments/H02-juggling.md#5-problems-and-limitations).

## Why the agent needs hand data

In the walking experiments the agent never needed the skin of the hands. Now it does, and the agent never sees the skin mesh, only numbers we give it. So we extended `body_info.json` with:

- the position of every finger joint in a flat hand, and how the joints are connected;
- how much each finger is curled when the hand is relaxed. SMPL-X adds this curl on top of whatever the agent asks for, so without this number the agent could not compute where its fingertips are;
- points on the skin: the palm, the pad of each finger bone and each fingertip;
- the thickness of the hand.

We checked this against the real model: computing the finger joints with the formula and numbers we give the agent lands within 0.1 mm of the model's own result.

## The extra files in an experiment folder

| File | What it is |
|---|---|
| `motion.timeline.csv` | Written by the measuring tool next to the motion: the contact and balance numbers for every frame, so that the agent, or we, can see when something goes wrong and not only that it did. |
| `motion.throws.csv` | Juggling only: one line for every flight of a ball, with its hands, times, height and fit. |
| `SMPLX_INTERFACE.md` | The manual, now with a section on the hands and two more entries in the motion file. |

Everything else is as in the [walking setup](../../walking/report/01-setup.md#what-the-agent-receives). The prompt templates are in [`../agent_kit/`](../agent_kit/).

## Checking the measuring tool

The measurements are only useful if they catch what they claim to catch. Before any agent used them, `python -m hoienv.selftest` built a crude clip of a correct hold and six fakes, and confirmed that the correct hold passes and each fake is caught:

| Fake | Caught by |
|---|---|
| The box floats away from the hands | box moving without hands, gap between hand and box |
| The person stands 30 cm too far back | box moving without hands, gap between hand and box |
| The box is dropped from 30 cm | speed at touchdown, box moving without hands |
| The box is dragged along the floor | box sliding on the floor, box never lifted |
| The hands are inside the box | hand skin inside the box |
| The box teleports | fastest box speed, strongest acceleration |

The same check exists for juggling, in `python -m hoienv.selftest_juggling`. It has to do more, because the measurements have to recognise a real throw. So it builds a plain but complete juggling clip: arms from inverse kinematics, the weight moved over one foot, 45 throws, balls in exact free fall. That clip meets all 48 targets, which also proves that the targets can be reached. It looks stiff, and it is not an example of good motion. The agent never sees it. Then the clip is broken on purpose:

| Fake | Caught by |
|---|---|
| A ball flies in a straight line | gravity error, difference from a free fall |
| Gravity is too weak | gravity error |
| A ball jumps in the air | difference from a free fall, fastest ball |
| A catch is missed and the ball falls to the floor | ball never caught, balls not in the hands at the end |
| The balls hang under the hands | balls not in the hands at the start |
| A ball flies through the chest | body skin inside a ball |
| Two balls are in the same place | balls inside each other |
| The balls balance on the fingertips | narrowest contact |
| The hand hardly moves, and the ball shoots out of it | speed jump at the release |
| The hand does not give way at the catch | speed jump at the catch |
| The foot is never lifted | times the foot leaves the floor, time on one foot |
| The foot touches down in between | times the foot leaves the floor |
| The weight does not move over the standing foot | off balance on one foot |
| The foot comes down before the last catch | order of the last catch and the foot |
| The person stands on the wrong foot | standing foot off the floor |

Whether the hands alternate and whether throws cross are tested on hand-made lists of throws.

## Changes to the shared walking code

The object experiments needed a few additions to [`../../walking/walkenv/`](../../walking/walkenv/): the motion file format accepts the object's position and rotation, the renderer draws the object and its target, and the cameras include the two hand views. For juggling, the motion file also accepts the positions of several balls, and the renderer draws them. The walking experiments are not affected: re-measuring E04 with the changed code gives exactly the same numbers as before. The same holds for the box: after the juggling changes, H01 measures exactly as before, and its instructions are unchanged.

## Where everything is

The rule is the same as in the walking series. An experiment ID such as `H01-box-carry` names:

- its report page: `report/experiments/H01-box-carry.md`
- its folder, with everything the agent saw and produced: `runs/H01-box-carry/`
- its videos: `runs/H01-box-carry/videos/` (start with `grid.mp4`, which shows all eight cameras at once)

Experiment IDs here start with H, for human-object interaction.

## The videos

| View | What it shows |
|---|---|
| `front`, `back`, `left`, `right` | Follow the person at 4.5 m distance. "Left" and "right" are the person's own left and right. |
| `top`, `overview` | The whole scene, from straight above and from the side at an angle. |
| `hands_left`, `hands_right` | Close-ups that look at the point between the wrists from 2 m away, from the person's front left and front right, slightly from above. |
| `grid.mp4` | All eight in one video. Top row: overview, front, left, hands from the left. Bottom row: top, back, right, hands from the right. |
| `contact_sheet.png` | Follow and hand cameras at eight moments in a chosen short time window. |
| `overview_sheet.png` | The two scene cameras at five moments across the clip. |

In the videos the box is solid and cardboard coloured, and the spot where it has to go is a teal outline on the floor. Balls are red, yellow and blue, so that each one can be followed, and the close-ups aim 25 cm higher, to show them in the air. The orange line on the floor is the track of the pelvis so far, and the grey ring marks the starting position.
