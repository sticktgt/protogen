from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any


class RequirementsSourceError(ValueError):
    """Raised when a requirements source path is invalid or unreadable."""


def load_requirements_from_workspace(
    *,
    module_root: Path,
    workspace_relative_path: str,
    max_bytes: int,
) -> tuple[dict[str, Any], Path, str]:
    source, normalized_path = resolve_workspace_file(
        module_root=module_root,
        workspace_relative_path=workspace_relative_path,
    )
    if not source.is_file():
        raise RequirementsSourceError(f"Файл требований не найден: {normalized_path}")
    if source.stat().st_size > max_bytes:
        raise RequirementsSourceError(
            f"Файл требований превышает допустимый размер {max_bytes} байт"
        )
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise RequirementsSourceError(
            f"Файл требований должен быть в кодировке UTF-8: {normalized_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RequirementsSourceError(
            f"Некорректный JSON в файле требований {normalized_path}: {exc}"
        ) from exc

    if not isinstance(data, dict) or not isinstance(data.get("requirements"), list):
        raise RequirementsSourceError(
            "Файл требований должен содержать JSON-объект с массивом requirements"
        )
    return data, source, normalized_path


def resolve_workspace_file(
    *,
    module_root: Path,
    workspace_relative_path: str,
) -> tuple[Path, str]:
    raw = str(workspace_relative_path or "").strip().replace("\\", "/")
    if not raw:
        raise RequirementsSourceError("Укажите относительный путь к файлу требований")

    relative = PurePosixPath(raw)
    if relative.is_absolute() or not relative.parts:
        raise RequirementsSourceError("Путь к требованиям должен быть относительным корню workspace")
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise RequirementsSourceError("Путь к требованиям не должен содержать . или ..")

    workspace_root = module_root.parent.resolve()
    candidate = (workspace_root / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise RequirementsSourceError("Файл требований должен находиться внутри workspace") from exc

    return candidate, relative.as_posix()
