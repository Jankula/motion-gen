"""Juggling with the SMPL-X body.

Modules
  params     every tunable number
  curves     smooth paths and slow random wobble
  stance     where the feet stand
  schedule   the timeline of a clip and the list of throws (exact free falls)
  fingers    seats of the balls in the hand and finger shapes, solved for the ball size
  pattern    hand paths and orientations fitted to the balls; ball positions; finger timing
  rig        feet, balance, pelvis, chest, head and arms -> all joint rotations
  task       task file -> motion dict -> .npz
"""
from .task import generate_juggling_motion, save_juggling_motion

__all__ = ["generate_juggling_motion", "save_juggling_motion"]
