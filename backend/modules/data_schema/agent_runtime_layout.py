from __future__ import annotations

import json
import shutil
from pathlib import Path

from backend.modules.data_schema.agent_paths import (
    RUN_ID_PATTERN,
    run_root,
    runtime_root,
)

_LAYOUT_VERSION = 2


def ensure_runtime_layout(module_root: Path) -> None:
    """Migrate legacy split run storage to one directory per run.

    Canonical layout:
      runs/<run_id>/run.json
      runs/<run_id>/diagnostics/attempt_<n>.zip

    Active runs keep their input/base/working/reference/result files in the same
    run directory. Terminal runs retain only the compact run record and ZIPs.
    """
    root = runtime_root(module_root)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "layout.json"
    if _layout_version(marker) >= _LAYOUT_VERSION:
        return

    _migrate_completed_records(module_root, root / "completed_runs")
    _migrate_diagnostics(module_root, root / "diagnostics")
    _remove_empty(root / "completed_runs")
    _remove_empty(root / "diagnostics")
    marker.write_text(
        json.dumps({"version": _LAYOUT_VERSION}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def compact_terminal_run_directory(
    module_root: Path,
    run_id: str,
    run: dict[str, object],
) -> None:
    """Remove heavy files while retaining the compact record and diagnostics."""
    root = run_root(module_root, run_id)
    diagnostics = root / "diagnostics"
    for child in list(root.iterdir()):
        if child == diagnostics:
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    diagnostics.mkdir(parents=True, exist_ok=True)
    (root / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _migrate_completed_records(module_root: Path, legacy_root: Path) -> None:
    if not legacy_root.is_dir():
        return
    for source in sorted(legacy_root.glob("run_*.json")):
        run_id = source.stem
        if not RUN_ID_PATTERN.fullmatch(run_id):
            continue
        target = run_root(module_root, run_id) / "run.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        source.unlink(missing_ok=True)


def _migrate_diagnostics(module_root: Path, legacy_root: Path) -> None:
    if not legacy_root.is_dir():
        return
    for source_dir in sorted(path for path in legacy_root.iterdir() if path.is_dir()):
        run_id = source_dir.name
        if not RUN_ID_PATTERN.fullmatch(run_id):
            continue
        target_dir = run_root(module_root, run_id) / "diagnostics"
        target_dir.mkdir(parents=True, exist_ok=True)
        for source in sorted(source_dir.glob("attempt_*.zip")):
            target = target_dir / source.name
            if not target.exists():
                shutil.copy2(source, target)
            source.unlink(missing_ok=True)
        _remove_empty(source_dir)


def _layout_version(marker: Path) -> int:
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
        return int(value.get("version", 0)) if isinstance(value, dict) else 0
    except (OSError, ValueError, TypeError):
        return 0


def _remove_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass
