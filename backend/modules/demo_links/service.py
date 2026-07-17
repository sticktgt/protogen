from __future__ import annotations

import json

from backend.app.state import AppState


def read_hello_summary(state: AppState, workspace_id: str) -> dict:
    config = state.config.read_module_runtime_config("demo_links")
    relative_file = config.get("reads_external_demo_file", "demo_hello/message.json")
    target = state.workspaces.get_workspace_path(workspace_id) / relative_file
    if not target.exists():
        return {"exists": False, "message": None}
    with target.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return {"exists": True, "message": data.get("message"), "source": relative_file}
