"""Procedural locomotion for the SMPL-X body.

Modules
  skeleton    body data (joints, parents, landmarks) and forward kinematics
  rotations   batched rotation helpers
  path        the walking line: task path -> smooth arc-length parametrised curve
  gait        gait parameters and normal-gait target curves
  plan        footstep plans: behaviours (stand, walk, stop, turn on the spot, squeeze through
              a gap) -> footsteps, plants with stance clocks, heading program, envelopes
  obstacles   upright boxes; narrow gaps on the walking line -> passages (sideways or with a
              shoulder turn)
  balance     centre of pressure and the inverted-pendulum centre of mass
  legs        foot rockers and analytic leg IK
  body        pelvis, pelvis height, stance and swing legs, whole clip
  upper_body  spine, head (gaze) and arms
  task        task file -> plan -> motion dict -> .npz
"""
from .body import Body, calibrate
from .path import WalkLine
from .obstacles import Box, find_passages
from .plan import Passage, Plan, PlanBuilder
from .task import build_plan, generate_motion, load_task, save_motion

__all__ = ["Body", "Box", "Passage", "Plan", "PlanBuilder", "WalkLine", "build_plan", "calibrate",
           "find_passages", "generate_motion", "load_task", "save_motion"]
