# SMPL-X model files

The model is free for research but licence-restricted, so it is not in this repository.

1. Register at https://smpl-x.is.tue.mpg.de and accept the licence.
2. On the Download page, get **SMPL-X v1.1 (NPZ+PKL)**.
3. Put it where `walkenv` looks, in this order:
   - the folder in the `WALKENV_MODELS` environment variable, if set
   - `walking/models/smplx/SMPLX_NEUTRAL.npz` (this folder)
   - `models_smplx_v1_1/models/smplx/SMPLX_NEUTRAL.npz` at the repository root, i.e. the download unzipped in place (shared with other projects in the repo)

Only the neutral `.npz` is used. Both locations are git-ignored.
