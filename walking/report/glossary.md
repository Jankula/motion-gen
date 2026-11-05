# Glossary

Terms used in the reports and in the agents' notes, in plain words.

## Walking

| Term | Meaning |
|---|---|
| **Step** | Moving one foot forward, from one heel touching the ground to the other heel touching the ground. |
| **Stride** / **gait cycle** | Two steps: from one heel touching the ground until the *same* heel touches it again. Walking repeats this cycle. |
| **Step length** / **stride length** | The distance covered by one step or one stride. For this body, about 0.65 m and 1.3 m in normal walking. |
| **Cadence** | Steps per minute. Comfortable adult walking is roughly 100–120 steps per minute. |
| **Stance phase** | The part of the cycle when a foot is on the ground carrying weight, about 60 % of the cycle. |
| **Swing phase** | The part of the cycle when a foot is in the air moving forward, about 40 %. |
| **Double support** | The short moments when both feet are on the ground, at the hand-over from one leg to the other. Walking always has them; running does not. |
| **Heel strike** | The moment the heel of the forward foot touches the ground. Marks the start of the stance phase. |
| **Toe-off** | The moment the toes leave the ground. Marks the start of the swing phase. |
| **Foot roll** ("rockers") | How the foot rolls over the ground during stance: first over the rounded heel, then flat, then over the ball of the foot and the toes as the heel lifts. |
| **Pelvis sway, tilt and rotation** | The small movements of the hips during walking: side to side (towards the standing leg), up and down (highest when the body passes over the standing leg), tilting (the hip of the swinging leg drops a little), and turning (the hip of the forward leg comes forward). |
| **Arm swing** | Arms swing opposite to the legs: the left arm forward when the right leg is forward. This balances the twisting of the body. |
| **Spin turn / step turn** | Two ways of turning a corner while walking: turning on the standing foot, or stepping out in the new direction. |
| **Side-stepping / sidling** | Moving sideways, with the body turned, as when passing through a gap narrower than the shoulders. |

## Animation and the body model

| Term | Meaning |
|---|---|
| **SMPL-X** | The 3D human body model we use: a skin mesh on a skeleton of joints. See [How an experiment works](01-setup.md#the-body-smpl-x). |
| **Mesh / vertices** | The surface of the body, made of 10,475 points (vertices) connected into triangles. |
| **Joint rotation** | How much a joint (knee, hip, ...) is turned, relative to the body part it hangs from. The motion file stores one rotation per joint per frame. |
| **Axis-angle** | The way rotations are written in the motion file: a direction to rotate about, and how far. |
| **Forward kinematics** | Computing where every body part ends up from the joint rotations ("if the hip turns this much and the knee this much, where is the foot?"). |
| **Inverse kinematics (IK)** | The reverse: computing the joint rotations needed to put a body part at a chosen place ("which hip and knee angles put the foot exactly here?"). Used to keep planted feet exactly in place. |
| **Foot skating / foot sliding** | The common animation error where a foot that should be planted slides over the floor. |
| **Interpenetration** | Body parts passing through each other or through objects. |
| **Frame / fps** | One still image of the motion; we use 30 frames per second (fps). |
| **Heading** | The horizontal direction the body faces. 0° means facing the +Z direction of the scene, 90° means facing +X. Turning left increases the heading. |
| **Contact sheet** | A single image with many still frames side by side, used to inspect a motion without playing the video. |

## Ways of generating motion (used in the proposals)

| Term | Meaning |
|---|---|
| **Pretrained motion model** | A neural network trained on large amounts of motion capture that generates new movement from a text description and/or constraints, in seconds or less. Examples: Kimodo, ARDY, MotionBricks, DART, HY-Motion. |
| **Motion capture (mocap)** | Recording real people's movement with cameras or body sensors. Datasets of such recordings (AMASS, TRUMANS, ParaHome, ...) are used to train models or to search for suitable clips. |
| **Keyframe** | A pose the body must have at a given moment. Animators set a few keyframes and fill in the movement between them. |
| **In-betweening** | Generating the movement between keyframes. |
| **Semantic keyframe** | A keyframe described by what it means ("right hand at the cupboard handle, looking at it") rather than by joint angles; a pose solver turns it into a full pose. |
| **Retargeting / body conversion** | Transferring motion from one body or skeleton (for example NVIDIA's SOMA) to another (our SMPL-X). Done badly, it causes visible errors ("artifacts"). |
| **Motion matching** | A game-industry technique: every few frames, the clip in a motion database that best continues the current movement and fits the goal is searched and played. |
| **Inertialization** | A technique for switching from one motion to another without a visible jump, in milliseconds. |
| **Layering** | Combining motions by body part, for example legs from walking and arms from carrying. |
| **Diffusion model** | A kind of generative network that creates data (here, motion) by gradually removing noise. Most current motion models are of this kind. |
| **Autoregressive generation** | Generating motion piece by piece, each piece continuing from the previous one; this allows long and real-time motion. |
| **Distillation** | Training a small, fast model to reproduce what a slower system (here, our engine plus data) produces. |
| **Director / action script** | In the proposed design, the agent writes a short list of actions (walk to, reach, place, ...) with targets and timing, which a motion engine carries out, instead of writing motion code itself. |
| **GPU / VRAM** | A graphics processor, used both for drawing images and for running neural networks; VRAM is its memory. The NVIDIA L4 has 24 GB. |

## The experiment setup

| Term | Meaning |
|---|---|
| **Agent** | An AI model that works on a task by itself: it plans, writes code, runs it, looks at the results and corrects itself, over many steps. Here: Claude Code with the Claude Opus 5.5 model. |
| **Session** | One run of the agent from the kickoff instruction until it stops. One experiment is one session. |
| **Turn** | One round trip in a session: the model decides what to do, a tool (for example running Python) does it, and the result comes back. |
| **Headless** | Running the agent without a person typing to it: it gets one instruction at the start and works alone. |
| **Transcript** | The complete record of a session: everything the agent wrote, every command it ran and every result it saw (`transcript.jsonl`). |
| **Task file** | The JSON file describing a task: instruction, path, obstacles, start and end poses ([`../tasks/`](../tasks/)). |
| **Blind / with feedback** | Whether the agent can see renderings of its result and measure it (see [How an experiment works](01-setup.md#two-ways-of-working-blind-and-with-feedback)). |
