from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

_READ_RETRIES = 3
_READ_RETRY_DELAY_SECONDS = 0.01


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    last_error: json.JSONDecodeError | None = None
    for attempt in range(_READ_RETRIES):
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError as exc:
            last_error = exc
            if attempt + 1 < _READ_RETRIES:
                time.sleep(_READ_RETRY_DELAY_SECONDS)
    assert last_error is not None
    raise last_error


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    target_mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, target_mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
