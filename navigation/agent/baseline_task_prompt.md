You direct a person through a house to carry out an instruction. It may describe a whole chore ("make breakfast") that you must break into steps yourself: what to fetch, where to take it, what to open, switch on and put away afterwards. A path planner handles the routes.

You make one plan and get no feedback. It runs like this: each step walks to the first of its candidate targets that has a collision-free route, then does the step's actions there, in order. If no candidate in a step has a route, or an action fails, execution stops and the task is reported as infeasible. Only go where the task needs you to go; where the person ends up counts. Leave things as a tidy person would: close what you opened, put things where they belong, and don't end holding anything the task doesn't need.

Actions, each on an object within reach of where the step ends (walk to the object itself; standing at one end of a long table doesn't reach the other end). An object is an id, or a label (with underscores, like "coffee_machine") for the nearest visible one, which is how to name something you expect inside a closed container:
- ["open", X] / ["close", X]: fridges, cabinets, drawers, microwaves.
- ["pick", X]: pick up something pickupable. The person has two hands; a container carries whatever is in it.
- ["place", X, Y]: put held X in or on receptacle Y (open Y first if it's closed), or into a container the person holds.
- ["use", X]: switch on a toggleable appliance (close a microwave first); it works on whatever is inside. A faucet runs into the sink below it.

The scene information may be incomplete or out of date. If the scene lists `images`, look at each one with Read before replying: they show the scene from the start position and from above, with each object's `mark` number drawn on it, and the object list then covers only what they show; things inside closed containers aren't listed. Read no other files.

Instruction: {instruction}

Scene:
{scene}

Reply with only a JSON object, in one of these forms. A target is an object id, a label or an "x,y" position; "then" is optional (sit, pick, place, open or stand). "step" says in a few words what the step does.
{{"steps": [{{"step": "get an egg from the fridge", "candidates": ["fridge_1"], "actions": [["open", "fridge_1"], ["pick", "egg"], ["close", "fridge_1"]]}}, {{"step": "sit down to eat", "candidates": ["chair_3"], "then": "sit"}}]}}
{{"infeasible": true, "reason": "why the instruction can't be carried out"}}
