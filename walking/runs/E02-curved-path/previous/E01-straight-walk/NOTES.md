# Walking motion for SMPL-X: notes

Files:

- `generate_motion.py` is the self-contained, deterministic generator. It uses numpy and scipy only, reads `body_info.json`, writes `motion.npz` and takes about 15 s.
- `analyze.py` is my own verification tool. It reloads `motion.npz` and runs the forward kinematics from `SMPLX_INTERFACE.md`. The generator does not need it.
- `motion.npz` is 180 frames at 30 fps with `transl`, `global_orient` and `body_pose`. Hands, jaw and eyes are left at zero, which is the relaxed default. `check_format.py` prints `OK`.

## The result in numbers

| quantity | value |
|---|---|
| speed / cadence / step length | 1.23 m/s, 113 steps/min (cycle 1.06 s with ±1.5 % slow wander), 0.65 m |
| stance / swing | 60 % / 40 %, about 10 % double support each step |
| step width / toe-out | 13.8 cm between heel centres (±4 mm scatter), 4.5° ± 1° |
| pelvis | vertical bob 3.6 cm (lowest just after heel strike, highest at mid-stance); lateral sway ±2.1 cm toward the stance leg; yaw ±4.5° (hip of the leading leg forward); obliquity ±3.5° (swing side drops); 2-4° forward tilt; forward speed ±5 % (fastest in double support) |
| knee | about 5° at heel strike, about 17° loading peak, 3-6° in terminal stance, about 31° at toe-off, about 62° peak in swing; never hyperextends |
| hip flexion / ankle | -14°...+34° / -22° (push-off)...+12° (dorsiflexion); toes extend up to 35° at push-off |
| trunk / head | thorax counter-rotates ±3.2° against the pelvis, leans 4° forward and ±1.2° toward the stance leg; the head is stabilised in space (±2.3° yaw, ±0.4° roll) and looks 5-8° down the path |
| arms | swing opposite to the legs (the left arm is most forward just after right heel strike); the hand travels about 17 cm behind to 26 cm in front of the pelvis; elbows flex about 10-35°, most just after the forward extreme; palms face the thighs, slightly turned back; collarbones drop 5° and protract/retract ±3° |

## Approach

I treated it as kinematic animation driven by one gait-phase clock, with hard contact constraints. The leg joint angles are computed rather than drawn: the feet are placed on the floor and the legs solved to reach them. Joint-angle "targets" come from what I know of normal adult gait curves (sagittal hip/knee/ankle, pelvis and trunk motion). No data was used.

1. **Phase clock.** Left heel strike is at phase 0 and right at 0.5. The cadence wanders slowly (±1.5 %, two incommensurate sinusoids), so no two steps last exactly the same time. The pelvis moves forward a fixed distance per gait cycle, so the gait geometry is identical every cycle and only the timing varies.

2. **Footprints.** Each heel strike puts the foot a fixed distance ahead of the pelvis (solved, see 5). Lateral and toe-out scatter are small and deterministic. From then on the foot is anchored to the floor.

3. **Stance foot (three rockers).**
   - *Heel rocker.* At contact the foot is pitched 19° toes-up and rolls without slipping on a 4.1 cm heel circle. I fitted that circle to the `heel_back` and `heel_bottom` landmarks. The plantarflexion is fastest right after contact and decelerates to a soft forefoot landing at 8 % of the cycle.
   - *Flat foot.* In the rest pose the soles sit exactly on the floor, so a flat foot is the rest foot orientation at rest height.
   - *Forefoot and toe rockers.* The heel rises by rotating the foot about the ball of the foot, which is the SMPL-X `*_foot` joint, while the toe joint counter-rotates so the toes stay flat. From 50 % of the cycle the toes also roll over the toe pad until toe-off at 60 %.
   - *How much the heel rises.* The heel-rise angle is a soft maximum of two terms. One is a heel-off profile starting at 31 % of the cycle. The other is the smallest rise that lets the knee bend at least a pre-swing minimum curve, rising to 31° at toe-off. The second term also guarantees the leg can always reach.

4. **Leg IK.** This is an analytic two-bone solve on the actual (slightly bent, slightly asymmetric) SMPL-X leg bones. The knee is a pure flexion about its local x axis. The remaining twist about the hip-ankle line points the knee's flexion axis along the foot's lateral axis, so the knee tracks over the foot. The ankle takes the remaining rotation. A weight-bearing foot therefore cannot slide.

5. **Pelvis height is solved, not guessed.**
   - For the leading stance leg (the one from its heel strike to the opposite heel strike), I solve the pelvis height that gives a normal stance-knee curve: 5° at contact, a 17.5° loading peak, 5° in terminal stance.
   - The near-straight knee makes this requirement very sensitive and V-shaped at each heel strike. I therefore fit the highest smooth periodic curve (harmonics up to 8) that never exceeds the requirement (constrained least squares, SLSQP). A slightly lower pelvis only adds a little knee flexion; a higher one would over-stretch the leg.
   - The heel-strike distance (0.231 m, the same for both feet) and a small static pelvic obliquity are solved by Newton iteration so that the requirement is continuous when the leading leg changes.

6. **Swing in joint space.** Each leg channel (hip 3 angles, knee, ankle 3 angles, toe) is a clamped cubic spline over the swing.
   - **Start:** the stance leg's angles and velocities at toe-off, so the C1 join is seamless.
   - **Via points:** normal swing kinematics. The knee peaks at about 61° at 30 % of swing and is 55° at mid-swing. Hip flexion peaks late and retracts 4° into contact. The ankle keeps plantarflexing briefly after push-off, then dorsiflexes to neutral. The toes relax.
   - **End:** the exact heel-strike pose with a "rigid-leg approach" velocity. The knee is momentarily still, the foot holds its pitch, and the hip retracts so the heel moves forward over the floor at 0.3 m/s. The heel then comes down at about 0.45 m/s, which is an impact-like contact rather than a float-in or a skid.

7. **Upper body.** The thorax orientation is specified in world space (counter-rotation, lean, small pitch bob) and distributed over spine1/2/3 (30/35/35 %). Head orientation is also specified in world space and distributed over neck and head (55/45 %), so the head stays steady while trunk and pelvis move.
   - **Arms:** the shoulder rotation aligns the rest shoulder-to-wrist line, which is what the mesh arm actually is, with a hang direction: 11° out from vertical, swinging ±16° plus a small second harmonic, plus the trunk lean, since arms hang with gravity. A 14° humeral internal rotation keeps the palms facing the thighs.
   - **Elbows and wrists:** elbow flexion is phase-lagged; wrist flexion lags further, like a passive pendulum.
   - **Variation:** arm amplitude varies ±6 % over time (different phase per arm) and the head drifts ±1.5° slowly, so nothing repeats perfectly.

### Problems found and fixed along the way (all by numerical checks)

- **Toe-off reach.** A 1.38 m stride made toe-off unreachable: even a straight leg could not reach the trailing forefoot. I moved toe-off to 60 %, added the toe rocker and shortened the stride to 1.30 m. A body with this leg length (hip joint 0.86 m above the floor) walks naturally at about 1.2-1.3 m/s.
- **Swing blow-ups.** Matching the stance-side knee velocity at heel strike made the swing splines go wild, because a near-straight knee has a huge geometric knee velocity. I replaced that with the rigid-leg approach, and also accounted for the leg being swung sideways by the pelvic obliquity rate.
- **Arm asymmetry.** The SMPL-X rest skeleton is not symmetric. The left elbow joint sits 3 cm below the shoulder-to-wrist line, and the right shoulder joint is 1.2 cm closer to the midline. The first arm version therefore hung the left arm 4° into the body. Aligning the shoulder-to-wrist line instead fixed it, and the right arm gets 1.2° more abduction so the hands mirror each other.
- **Leg asymmetry.** The legs differ too. The left knee is 3.1° bent in the rest skeleton and the right only 0.2°; the right hip is 1.1 cm lower and the right leg 0.9 cm shorter. Equal joint angles therefore need about 3 mm more pelvis height on the right. Putting the whole fix into foot placement would have needed 9 cm different step lengths (a limp). Putting it all into pelvic tilt would have needed 1.8°. I split it: ±1.1° stance-knee offsets plus a static pelvic obliquity of -0.7°. Both are below anything a viewer can see, and steps, timing, foot placement and swing are fully symmetric.

## Ambiguities and decisions

- **"Natural self-selected pace"**: 1.23 m/s at 113 steps/min, the stride that fits this body's legs (see above).
- **"Pelvis above the origin at frame 0"**: the x and z of `transl` are exactly 0 at frame 0 (the whole motion is shifted). The height is whatever the gait needs (`transl` y is about -0.026 at frame 0).
- **Starting phase**: the clip starts mid-gait with the left foot in early stance and the right just after toe-off, so the person is already walking. The phase at the end is arbitrary; walking continues past it.
- **Optional keys**: hands, jaw and eyes are omitted (zero is the relaxed hand / closed mouth / eyes forward).
- **Sign conventions** were derived from the interface and checked with FK. For example, +x rotation flexes the knee and moves the thigh backward, +y yaws toward the body's left, +z raises the left side of the pelvis.

## How I checked it (`analyze.py`, on the saved file)

- **FK as specified.** Forward kinematics follows the formula in `SMPLX_INTERFACE.md`, applied to the stored float32 axis-angles.
- **Floor contact.** I don't have the mesh, so I sampled the sole: the heel circle, rear/mid-foot sole points at floor level from the sole-edge landmarks, toe-pad points and the toe-tip landmark. Each is attached to its joint (ankle or toe). Results:
  - lowest point over all frames: 0.0 mm, never below the floor;
  - floor-contact points move at most 1.2 mm per frame, which is the rolling heel and not sliding;
  - minimum swing clearance 1.6-1.9 cm on every step (normal minimum toe clearance is about 1-2 cm);
  - the heel is about 1-2 cm up one frame before contact.
- **Leg reach.** The IK is never out of reach (q < 1) and the knee never hyperextends (minimum 2.3°).
- **Joint ranges and speeds.** Ranges are listed above. Peak knee speed is about 400°/s, in early swing, which is normal for walking. There are no frame-to-frame jumps; I scanned all joints' angular speed and acceleration.
- **Symmetry.** Left/right ranges match to within about 1-2°. Step lengths are 0.650 m every step and step times 0.52-0.54 s.
- **Clearances (approximate).** These use joint positions and assumed body widths:
  - hands are 20-27 cm from the body midline when beside the hips (hip half-width is roughly 18 cm);
  - elbows are 17-21 cm from the thorax axis;
  - swing and stance ankles stay ≥ 9.9 cm apart, shank axes ≥ 12 cm.
- **Posture.** An ASCII stick-figure plot (side and front) to sanity-check posture and coordination.
- **Determinism.** Two runs give bit-identical `motion.npz`.

## Known weaknesses

- **No mesh.** Foot/floor contact relies on landmarks plus a fitted heel circle and assumed sole points. The real mesh may hover or sink by a few millimetres, especially during the heel rocker, at push-off where skinning around the toe joint blends, and on the sole edges. Inversion is not modelled; the foot stays flat mediolaterally, with about 4° of ankle inversion coming from the skeleton's leg geometry.
- **Self-contact checked only roughly.** Contact was checked with joint distances and assumed body widths, not the skin. With this body the inner thighs and the armpit/upper arm may touch the torso slightly, as any SMPL-X body does in these poses.
- **Heel strike.** The knee flexes quickly right after contact (about 250°/s for 2 frames). The smooth pelvis curve cannot follow the sharp kinematic corner at contact. Contact is also a deliberate velocity discontinuity (an impact), which might read as slightly "stompy".
- **Regularity.** The motion is deterministic and nearly periodic. Variability is limited to slow cadence wander, arm amplitude, a small head drift and foot-placement scatter. Step length is constant. There are no gaze shifts, breathing or finger motion; the hands stay in the default relaxed pose for the whole clip.
- **Hand-tuned curves.** All gait curves and amplitudes are from memory of typical adult gait and tuned by numbers, not by eye. Style details may not match any particular person: arm swing amplitude, the 4° forward lean, a 13.8 cm step width that is on the wide side of normal (chosen to keep the thighs and ankles clear).
- **Skeleton asymmetry.** The -0.7° pelvic obliquity offset and ±1.1° knee offsets are a compromise; a viewer should not perceive them.
