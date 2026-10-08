from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def write_json(path: Path, data: Any) -> None:
    _write_json_atomic(path, data, indent=2, separators=None)


def write_json_compact(path: Path, data: Any) -> None:
    _write_json_atomic(path, data, indent=None, separators=(",", ":"))


def _write_json_atomic(
    path: Path,
    data: Any,
    *,
    indent: int | None,
    separators: tuple[str, str] | None,
) -> None:
    """Write JSON through a temporary sibling file and atomically replace the target.

    Agent callbacks can run concurrently when the model requests several tools in one
    response. A normal ``open(path, 'w')`` briefly exposes an empty/partial JSON file
    to readers. ``os.replace`` keeps the previous complete file visible until the new
    complete file is ready.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=indent,
                separators=separators,
            )
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
