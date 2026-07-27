from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_requirements import load_requirements_from_workspace
from backend.modules.ui_schema.agent_completion import validate_agent_working_schema
from backend.modules.ui_schema.agent_snapshots import create_snapshot, trim_snapshots
from backend.modules.ui_schema.agent_validation import validate_ui_schema
from backend.modules.ui_schema.files import read_json, write_json
from backend.modules.ui_schema.requirements_source import file_sha256, source_reference


def apply_run(
    module_root: Path,
    run_id: str,
    *,
    keep_last: int = 10,
    requirements_max_bytes: int = 10 * 1024 * 1024,
) -> dict[str, Any]:
    from backend.modules.ui_schema.agent_runs import (
        PROCESS_LOCK,
        clear_active_run,
        get_run,
        run_root,
        update_run,
    )

    with PROCESS_LOCK:
        run = get_run(module_root, run_id)
        if run.get("status") != "preview_ready":
            raise ValueError("Only a preview-ready run can be applied")
        root = run_root(module_root, run_id)
        requirements_data = read_json(root / "input" / "requirements.json", {"requirements": []})
        _ensure_requirements_source_unchanged(
            module_root,
            run,
            max_bytes=requirements_max_bytes,
        )
        working = root / "working" / "ui_schema"
        # Migrate previews created by older module versions at apply time too.
        # The external source is authoritative; the accepted UI schema keeps
        # only its reference and never a copied requirements payload.
        write_json(
            working / "requirements_source.json",
            source_reference(
                str(run.get("requirements_source_path") or ""),
                sha256=str(run.get("requirements_source_sha256") or "") or None,
            ),
        )
        (working / "requirements.json").unlink(missing_ok=True)
        update_run(module_root, run_id, status="applying", phase="applying")
        validation = validate_agent_working_schema(root)
        if not validation["valid"]:
            update_run(
                module_root,
                run_id,
                status="failed",
                phase="validating",
                validation_errors=validation["errors"],
                validation_warnings=validation.get("warnings", []),
            )
            raise ValueError("Preview UI schema is invalid")

        snapshot = create_snapshot(module_root, run_id=run_id, reason="before_agent_apply")
        incoming = module_root.parent / f".ui_schema_incoming_{run_id}"
        previous = module_root.parent / f".ui_schema_previous_{run_id}"
        shutil.rmtree(incoming, ignore_errors=True)
        shutil.rmtree(previous, ignore_errors=True)
        shutil.copytree(working, incoming)
        try:
            module_root.rename(previous)
            incoming.rename(module_root)
            _copy_requirements_export(root, module_root, run_id)
            final_validation = validate_ui_schema(
                module_root,
                rebuild=True,
                requirements_data=requirements_data,
            )
            if not final_validation["valid"]:
                raise RuntimeError(
                    "Applied UI schema failed final validation: "
                    + "; ".join(final_validation["errors"])
                )
        except Exception:
            shutil.rmtree(module_root, ignore_errors=True)
            if previous.exists():
                previous.rename(module_root)
            update_run(module_root, run_id, status="failed", phase="applying")
            raise
        finally:
            shutil.rmtree(previous, ignore_errors=True)
            shutil.rmtree(incoming, ignore_errors=True)

        trim_snapshots(module_root, keep_last=keep_last)
        run = update_run(
            module_root,
            run_id,
            status="completed",
            phase="completed",
            snapshot_id=snapshot["snapshot_id"],
            requirements_ui_export=f"exports/requirements_ui/{run_id}.json",
        )
        clear_active_run(module_root, run_id)
        from backend.modules.ui_schema.agent_runs import archive_and_remove_run
        return archive_and_remove_run(module_root, run_id, run=run)


def _ensure_requirements_source_unchanged(
    module_root: Path,
    run: dict[str, Any],
    *,
    max_bytes: int,
) -> None:
    source_path = str(run.get("requirements_source_path") or "")
    _, source_file, _ = load_requirements_from_workspace(
        module_root=module_root,
        workspace_relative_path=source_path,
        max_bytes=max_bytes,
    )
    expected = str(run.get("requirements_source_sha256") or "")
    current = file_sha256(source_file)
    if expected and current != expected:
        raise ValueError(
            "Файл требований изменился после запуска синхронизации. "
            "Перегенерируйте результат на актуальной версии требований перед применением."
        )


def _copy_requirements_export(run_path: Path, module_root: Path, run_id: str) -> None:
    source = run_path / "result" / "requirements_ui_result.json"
    if not source.is_file():
        return
    target = module_root / "exports" / "requirements_ui" / f"{run_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
