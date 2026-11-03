"""Motion file format for the walking task.

numpy only: this file is copied into every agent workspace as check_format.py.

Usage: python check_format.py motion.npz [task.json]
"""
import json
import sys

import numpy as np

TASK_FPS = 30
TASK_FRAMES = 180

# key -> per-frame shape. Flat variants ((63,) for body_pose, (45,) for hands) are also accepted.
REQUIRED = {
    "transl": (3,),
    "global_orient": (3,),
    "body_pose": (21, 3),
}
OPTIONAL = {
    "left_hand_pose": (15, 3),
    "right_hand_pose": (15, 3),
    "jaw_pose": (3,),
    "leye_pose": (3,),
    "reye_pose": (3,),
}


class MotionFormatError(ValueError):
    pass


def load_motion(path, expect_fps=None, expect_frames=None):
    """Load and validate a motion file.

    Returns a dict with "fps" (int) and float32 arrays for every key in REQUIRED and
    OPTIONAL, shaped (T, *shape); optional keys that are absent are filled with zeros.
    Raises MotionFormatError listing every problem found.
    """
    errors = []
    try:
        data = np.load(path, allow_pickle=False)
    except Exception as e:  # noqa: BLE001 - report any load failure as a format error
        raise MotionFormatError(f"cannot read {path}: {e}") from e

    if "fps" not in data.files:
        errors.append("missing key 'fps'")
        fps = None
    else:
        fps_arr = _read(data, "fps", errors)
        ok = fps_arr is not None and fps_arr.size == 1 and np.issubdtype(fps_arr.dtype, np.number)
        value = fps_arr.item() if ok else None
        if not ok or not np.isfinite(value) or value != int(value):
            errors.append(f"'fps' must be a single integer, got {fps_arr!r}")
            fps = None
        else:
            fps = int(value)
            if not 10 <= fps <= 120:
                errors.append(f"'fps' must be between 10 and 120, got {fps}")
            if expect_fps is not None and fps != expect_fps:
                errors.append(f"'fps' must be {expect_fps} for this task, got {fps}")

    out = {"fps": fps}
    num_frames = None
    for key, shape in {**REQUIRED, **OPTIONAL}.items():
        if key not in data.files:
            if key in REQUIRED:
                errors.append(f"missing key '{key}'")
            continue
        arr = _read(data, key, errors)
        if arr is None:
            continue
        if not np.issubdtype(arr.dtype, np.number):
            errors.append(f"'{key}' must be numeric, got dtype {arr.dtype}")
            continue
        flat = int(np.prod(shape))
        if arr.ndim == 2 and arr.shape[1] == flat:
            arr = arr.reshape(len(arr), *shape)
        if arr.shape[1:] != shape:
            errors.append(f"'{key}' must have shape (T, {', '.join(map(str, shape))}), got {arr.shape}")
            continue
        if not np.isfinite(arr).all():
            errors.append(f"'{key}' contains NaN or inf")
            continue
        if num_frames is None:
            num_frames = len(arr)
        elif len(arr) != num_frames:
            errors.append(f"'{key}' has {len(arr)} frames, other keys have {num_frames}")
            continue
        out[key] = arr.astype(np.float32)

    if num_frames is not None:
        if num_frames < 2:
            errors.append(f"need at least 2 frames, got {num_frames}")
        if expect_frames is not None and num_frames != expect_frames:
            errors.append(f"must have exactly {expect_frames} frames for this task, got {num_frames}")

    unknown = sorted(set(data.files) - {"fps"} - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        errors.append(f"unknown keys {unknown}; allowed: fps, {', '.join([*REQUIRED, *OPTIONAL])}")

    if errors:
        raise MotionFormatError(f"{path}:\n  - " + "\n  - ".join(errors))

    for key, shape in OPTIONAL.items():
        out.setdefault(key, np.zeros((num_frames, *shape), np.float32))
    return out


def _read(data, key, errors):
    try:
        return np.asarray(data[key])
    except ValueError as e:  # e.g. object arrays, which need pickle
        errors.append(f"'{key}' cannot be read without pickle ({e}); save plain numeric arrays")
        return None


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__.strip().splitlines()[-1])
        return 2
    fps, frames = TASK_FPS, TASK_FRAMES
    if len(argv) == 3:  # the task file says how long the clip must be
        with open(argv[2], encoding="utf-8") as f:
            task = json.load(f)
        fps, frames = task["fps"], task["frames"]
    try:
        m = load_motion(argv[1], expect_fps=fps, expect_frames=frames)
    except MotionFormatError as e:
        print(f"INVALID {e}")
        return 1
    print(f"OK: {len(m['transl'])} frames at {m['fps']} fps")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
