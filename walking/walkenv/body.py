"""SMPL-X body: turns per-frame parameters into mesh vertices and joint positions."""
import numpy as np
import smplx
import torch
from smplx.joint_names import JOINT_NAMES

from .motion_format import OPTIONAL, REQUIRED
from .paths import MODELS_DIR

NUM_SKELETON_JOINTS = 55  # smplx also returns extra landmark "joints" after these
BODY_JOINT_NAMES = JOINT_NAMES[:22]  # pelvis + the 21 joints in body_pose


class Body:
    """Neutral SMPL-X body with betas = 0 (the fixed body the agent animates)."""

    def __init__(self, model_dir=MODELS_DIR, gender="neutral"):
        model_file = model_dir / "smplx" / f"SMPLX_{gender.upper()}.npz"
        if not model_file.exists():
            raise FileNotFoundError(
                f"SMPL-X model not found at {model_file}. See models/README.md for how to get it."
            )
        self.model = smplx.create(
            str(model_dir),
            model_type="smplx",
            gender=gender,
            ext="npz",
            use_pca=False,  # hand poses are full axis-angle, like the body
            flat_hand_mean=False,  # zero hand pose = relaxed, slightly curled hand
            num_betas=10,
            num_expression_coeffs=10,
        ).eval()
        self.faces = np.asarray(self.model.faces, dtype=np.int64)
        self.parents = self.model.parents.numpy().copy()
        rest_verts, rest_joints = self.forward(_zero_motion(1))
        self.rest_vertices = rest_verts[0]
        self.rest_joints = rest_joints[0]
        self.floor_y = float(self.rest_vertices[:, 1].min())

    @torch.no_grad()
    def forward(self, motion, chunk=32):
        """Returns vertices (T, V, 3) and skeleton joints (T, 55, 3) as float32 arrays."""
        num_frames = len(motion["transl"])
        verts, joints = [], []
        for start in range(0, num_frames, chunk):
            sl = slice(start, min(start + chunk, num_frames))
            n = sl.stop - sl.start
            params = {
                key: torch.from_numpy(np.ascontiguousarray(motion[key][sl])).reshape(n, -1).float()
                for key in [*REQUIRED, *OPTIONAL]
            }
            out = self.model(
                betas=torch.zeros(n, 10),
                expression=torch.zeros(n, 10),
                return_verts=True,
                **params,
            )
            verts.append(out.vertices.numpy())
            joints.append(out.joints[:, :NUM_SKELETON_JOINTS].numpy())
        return np.concatenate(verts), np.concatenate(joints)


def _zero_motion(num_frames):
    motion = {key: np.zeros((num_frames, *shape), np.float32) for key, shape in {**REQUIRED, **OPTIONAL}.items()}
    motion["fps"] = 30
    return motion
