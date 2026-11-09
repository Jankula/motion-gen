"""Environment for the human-object interaction experiments. Reuses the walking package (body model,
cameras, renderer, session handling), which lives next to this folder."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "walking"))
