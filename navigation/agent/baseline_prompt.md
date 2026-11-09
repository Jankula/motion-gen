You direct a person walking through a 3D scene to carry out an instruction. They are modelled as an upright cylinder and start at a fixed position. A path planner handles the routes; you decide where to go.

You make one plan and get no feedback. It runs like this: each step lists candidate targets in order of preference. The person walks to the first candidate that has a collision-free route and moves on to the next step. If no candidate in a step has a route, execution stops and the task is reported as infeasible. Only go where the instruction needs you to go; where the person ends up counts.

The scene information may be incomplete or out of date. If the scene lists `images`, look at each one with Read before replying: they show the scene from the start position and from above, with each object's `mark` number drawn on it, and the object list then covers only what they show. Read no other files.

Instruction: {instruction}

Scene:
{scene}

Reply with only a JSON object, in one of these forms. A target is an object id or an "x,y" position.
{{"steps": [{{"candidates": ["first_choice", "fallback"]}}, {{"candidates": ["next_step_target"]}}]}}
{{"infeasible": true, "reason": "why the instruction can't be carried out"}}
