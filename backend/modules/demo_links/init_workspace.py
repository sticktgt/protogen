from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def init_workspace(
    *,
    username: str,
    workspace_id: str,
    workspace: dict[str, Any],
    module_path: Path,
    **_kwargs: Any,
) -> None:
    data = {
        "created_by": username,
        "workspace_id": workspace_id,
        "workspace_name": workspace.get("name", ""),
        "note": "This file was created by a module Python init hook."
    }
    target = module_path / "init_hook_result.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
