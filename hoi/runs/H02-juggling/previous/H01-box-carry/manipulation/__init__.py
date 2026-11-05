"""Handling objects with the SMPL-X body, on top of the locomotion package.

Modules
  box        the object, and what a stance in front of it means
  route      routes on the floor (Dubins curves, turns on the spot) and the choice of grip side
  massmodel  segment masses: centre of mass of the body with a load
  arms       analytic arm IK
  hand       finger kinematics and grip shapes
  script     task -> footstep plan and event times
  rig        posture, box, arms, hands, head and balance -> all joint rotations
  task       task file -> motion dict -> .npz
"""
from .task import generate_box_motion, save_box_motion

__all__ = ["generate_box_motion", "save_box_motion"]
