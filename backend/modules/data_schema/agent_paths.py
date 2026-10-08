from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

RUN_ID_PATTERN = re.compile(r"^run_[0-9]{8}_[0-9]{6}_[a-f0-9]{8}$")
ACTIVE_STATUSES = {"running", "cancelling", "preview_ready", "applying", "failed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_root(module_root: Path) -> Path:
    return module_root.parent / ".protoarchitect" / "data_schema_agent"


def active_run_path(module_root: Path) -> Path:
    return runtime_root(module_root) / "active_run.json"


def runs_root(module_root: Path) -> Path:
    return runtime_root(module_root) / "runs"


def run_root(module_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    return runs_root(module_root) / run_id


def run_file(module_root: Path, run_id: str) -> Path:
    return run_root(module_root, run_id) / "run.json"


def history_root(module_root: Path) -> Path:
    return runtime_root(module_root) / "history"


def completed_run_file(module_root: Path, run_id: str) -> Path:
    """Return the canonical compact record path for a terminal run."""
    return run_file(module_root, run_id)


def legacy_completed_run_file(module_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    return runtime_root(module_root) / "completed_runs" / f"{run_id}.json"


def legacy_diagnostics_root(module_root: Path) -> Path:
    return runtime_root(module_root) / "diagnostics"


def initial_snapshot_path(module_root: Path) -> Path:
    return runtime_root(module_root) / "initial" / "data_schema.zip"


def validate_run_id(run_id: str) -> None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("Invalid run_id")
