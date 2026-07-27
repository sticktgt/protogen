from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.workspace_migration import remove_obsolete_requirements_copy


def init_workspace(
    *,
    config: Any,
    username: str,
    workspace_id: str,
    workspace: Any,
    workspace_path: Path,
    module: Any,
    module_path: Path,
) -> None:
    """Finish initialization of a clean UI Schema workspace.

    Static init files remain the source of the empty schema. The hook removes the
    legacy local requirements copy that can still be present in installations
    updated by overlay ZIP archives.
    """
    module_path.mkdir(parents=True, exist_ok=True)
    (module_path / "pages").mkdir(parents=True, exist_ok=True)
    (module_path / "mappings").mkdir(parents=True, exist_ok=True)
    remove_obsolete_requirements_copy(module_path)
