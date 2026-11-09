"""Procedural locomotion for the SMPL-X body.

Modules
  skeleton    body data (joints, parents, landmarks) and forward kinematics
  rotations   batched rotation helpers
  path        the walking line: task path -> smooth arc-length parametrised curve
  gait        gait parameters, normal-gait target curves, the gait clock
  legs        foot rockers and analytic leg IK
  walker      footprints, pelvis trajectory and height, stance/swing legs, whole clip
  upper_body  spine, head (gaze) and arms
  task        task file -> motion dict -> .npz
"""
from .path import WalkLine
from .task import generate_motion, load_task, save_motion
from .walker import Walker

__all__ = ["WalkLine", "Walker", "generate_motion", "load_task", "save_motion"]
