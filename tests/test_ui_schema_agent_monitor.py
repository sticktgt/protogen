from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if "backend.app.state" not in sys.modules:
    app_package = types.ModuleType("backend.app")
    app_package.__path__ = []
    state_module = types.ModuleType("backend.app.state")
    state_module.AppState = type("AppState", (), {})
    sys.modules["backend.app"] = app_package
    sys.modules["backend.app.state"] = state_module

from backend.modules.ui_schema.agent_monitor import (
    AgentRunCancellation,
    AgentRunStopped,
    _check_run,
)
from backend.modules.ui_schema.agent_paths import run_root
from backend.modules.ui_schema.files import write_json


def test_completed_operation_is_not_discarded_only_because_duration_elapsed(
    tmp_path: Path,
) -> None:
    module_root = tmp_path / "modules" / "ui_schema"
    module_root.mkdir(parents=True)
    run_id = "run_20260806_120000_1234abcd"
    root = run_root(module_root, run_id)
    root.mkdir(parents=True)
    write_json(root / "run.json", {"status": "running"})
    write_json(root / "metrics.json", {"started_at": "2000-01-01T00:00:00+00:00"})
    limits = {"max_duration_seconds": 1}

    _check_run(
        module_root,
        run_id_value=run_id,
        limits=limits,
        enforce_duration=False,
    )

    with pytest.raises(AgentRunStopped, match="максимальный срок"):
        _check_run(module_root, run_id_value=run_id, limits=limits)


def test_duration_defer_does_not_ignore_user_cancellation(tmp_path: Path) -> None:
    module_root = tmp_path / "modules" / "ui_schema"
    module_root.mkdir(parents=True)
    run_id = "run_20260806_120000_1234abce"
    root = run_root(module_root, run_id)
    root.mkdir(parents=True)
    write_json(root / "run.json", {"status": "cancelling"})
    write_json(root / "metrics.json", {"started_at": "2000-01-01T00:00:00+00:00"})

    with pytest.raises(AgentRunCancellation):
        _check_run(
            module_root,
            run_id_value=run_id,
            limits={"max_duration_seconds": 1},
            enforce_duration=False,
        )
