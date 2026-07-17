from __future__ import annotations

from backend.app.state import AppState
from backend.modules.demo_hello.files import read_json, write_json


def message_file(state: AppState, workspace_id: str):
    config = state.config.read_module_runtime_config("demo_hello")
    folder = config.get("workspace_folder", "demo_hello")
    filename = config.get("files", {}).get("message", "message.json")
    return state.workspaces.get_workspace_path(workspace_id) / folder / filename


def read_message(state: AppState, workspace_id: str) -> dict:
    return read_json(message_file(state, workspace_id), {"message": "", "updated_by": ""})


def save_message(state: AppState, workspace_id: str, username: str, message: str) -> dict:
    data = {"message": message, "updated_by": username}
    write_json(message_file(state, workspace_id), data)
    return data
