from __future__ import annotations

import json
import os
from pathlib import Path

from .models import CandidateProfile


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_profile(path: str | Path) -> CandidateProfile:
    with Path(path).open(encoding="utf-8") as handle:
        return CandidateProfile.from_dict(json.load(handle))

