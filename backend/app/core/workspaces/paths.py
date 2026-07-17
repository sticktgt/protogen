from __future__ import annotations

import re
from pathlib import Path


def safe_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
    normalized = normalized.replace("..", "_").strip("_")
    return normalized or "item"


def relative_path(*parts: str) -> str:
    return "/".join(part.strip("/\\") for part in parts if part)


def ensure_inside(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
