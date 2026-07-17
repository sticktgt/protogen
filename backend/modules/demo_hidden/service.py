from __future__ import annotations

from backend.app.state import AppState
from backend.modules.demo_hidden.files import read_json, write_json


def note_file(state: AppState, workspace_id: str):
    config = state.config.read_module_runtime_config("demo_hidden")
    folder = config.get("workspace_folder", "demo_hidden")
    filename = config.get("notes_file", "notes.json")
    return state.workspaces.get_workspace_path(workspace_id) / folder / filename


def read_status(state: AppState, workspace_id: str) -> dict:
    data = read_json(note_file(state, workspace_id), {"note": ""})
    return {
        "module": "demo_hidden",
        "workspace_id": workspace_id,
        "note": data.get("note", ""),
        "source": "This page is registered but not shown in the left module menu.",
    }


def save_note(state: AppState, workspace_id: str, note: str) -> dict:
    data = {"note": note}
    write_json(note_file(state, workspace_id), data)
    return data
