from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    base_dir = Path(os.environ.get("ATLAS_WEAVE_DATA_DIR", ".atlas-weave"))
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir
