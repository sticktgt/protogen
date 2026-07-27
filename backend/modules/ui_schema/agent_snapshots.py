from __future__ import annotations

import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.modules.ui_schema.agent_paths import history_root, initial_snapshot_path, now_iso
from backend.modules.ui_schema.agent_validation import validate_ui_schema
from backend.modules.ui_schema.files import read_json, write_json


def ensure_initial_snapshot(module_root: Path) -> None:
    path = initial_snapshot_path(module_root)
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    create_zip(module_root, path)


def create_snapshot(module_root: Path, *, run_id: str | None, reason: str) -> dict[str, Any]:
    snapshot_id = f"snapshot_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    target = history_root(module_root) / snapshot_id
    target.mkdir(parents=True, exist_ok=True)
    create_zip(module_root, target / "ui_schema.zip")
    metadata = {
        "snapshot_id": snapshot_id,
        "created_at": now_iso(),
        "reason": reason,
        "run_id": run_id,
    }
    write_json(target / "metadata.json", metadata)
    return metadata


def latest_snapshot(module_root: Path) -> dict[str, Any] | None:
    root = history_root(module_root)
    if not root.is_dir():
        return None
    snapshots: list[dict[str, Any]] = []
    for item in root.iterdir():
        if item.is_dir() and (item / "metadata.json").is_file() and (item / "ui_schema.zip").is_file():
            metadata = read_json(item / "metadata.json", {})
            metadata["path"] = item
            snapshots.append(metadata)
    if not snapshots:
        return None
    snapshots.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return snapshots[0]


def restore_latest_snapshot(module_root: Path) -> dict[str, Any]:
    from backend.modules.ui_schema.agent_runs import PROCESS_LOCK, ensure_schema_writable

    with PROCESS_LOCK:
        ensure_schema_writable(module_root)
        snapshot = latest_snapshot(module_root)
        if not snapshot:
            raise FileNotFoundError("No UI schema snapshots are available")
        create_snapshot(module_root, run_id=None, reason="before_snapshot_restore")
        incoming = module_root.parent / f".ui_schema_restore_{uuid4().hex[:8]}"
        previous = module_root.parent / f".ui_schema_restore_previous_{uuid4().hex[:8]}"
        shutil.rmtree(incoming, ignore_errors=True)
        extract_zip(Path(snapshot["path"]) / "ui_schema.zip", incoming)
        validation = validate_ui_schema(incoming, rebuild=True)
        if not validation["valid"]:
            shutil.rmtree(incoming, ignore_errors=True)
            raise ValueError("Snapshot is invalid: " + "; ".join(validation["errors"]))
        try:
            module_root.rename(previous)
            incoming.rename(module_root)
            if not validate_ui_schema(module_root, rebuild=True)["valid"]:
                raise RuntimeError("Restored UI schema is invalid")
        except Exception:
            shutil.rmtree(module_root, ignore_errors=True)
            if previous.exists():
                previous.rename(module_root)
            raise
        finally:
            shutil.rmtree(previous, ignore_errors=True)
            shutil.rmtree(incoming, ignore_errors=True)
        return {key: value for key, value in snapshot.items() if key != "path"}


def trim_snapshots(module_root: Path, *, keep_last: int) -> None:
    if keep_last <= 0:
        return
    root = history_root(module_root)
    if not root.is_dir():
        return
    entries = sorted((path for path in root.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True)
    for path in entries[keep_last:]:
        shutil.rmtree(path, ignore_errors=True)


def create_zip(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
    os.replace(temporary, destination)


def extract_zip(source: Path, destination: Path) -> None:
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "r") as archive:
        archive.extractall(destination)
