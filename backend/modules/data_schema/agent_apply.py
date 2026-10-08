from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_requirements import load_requirements_from_workspace
from backend.modules.data_schema.agent_completion import validate_agent_working_schema
from backend.modules.data_schema.agent_events import append_event
from backend.modules.data_schema.agent_requirement_scope import allowed_requirement_ids
from backend.modules.data_schema.agent_snapshots import create_snapshot, trim_snapshots
from backend.modules.data_schema.agent_validation import validate_data_schema
from backend.modules.data_schema.files import read_json, write_json
from backend.modules.data_schema.requirements_source import file_sha256, source_reference


def apply_run(
    module_root: Path,
    run_id: str,
    *,
    keep_last: int,
    requirements_max_bytes: int,
) -> dict[str, Any]:
    from backend.modules.data_schema.agent_runs import (
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
        semantic_review = run.get("semantic_review", {})
        if not isinstance(semantic_review, dict):
            semantic_review = {}
        review_status = str(semantic_review.get("status") or "")
        review_decision = str(semantic_review.get("decision") or "")
        review_kind = str(semantic_review.get("review_kind") or "")
        review_complete = semantic_review.get("coverage_complete") is True
        review_approved = (
            review_status in {"approved", "skipped"}
            and review_decision == "approve"
            and review_kind in {"combined", "correction_verification"}
            and review_complete
            and not semantic_review.get("blocking")
            and not semantic_review.get("correction_pending")
        )
        if run.get("apply_blocked") or not review_approved:
            raise ValueError(
                "Применение заблокировано: результат не прошёл завершённую "
                "смысловую проверку без обязательных замечаний."
            )
        root = run_root(module_root, run_id)
        _ensure_requirements_source_unchanged(
            module_root,
            run,
            max_bytes=requirements_max_bytes,
        )
        working = root / "working" / "data_schema"
        # Migrate previews created by older module versions at apply time too.
        # The external source is authoritative; the accepted data schema keeps
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
            raise ValueError("Preview data schema is invalid")

        snapshot = create_snapshot(module_root, run_id=run_id, reason="before_agent_apply")
        incoming = module_root.parent / f".data_schema_incoming_{run_id}"
        previous = module_root.parent / f".data_schema_previous_{run_id}"
        shutil.rmtree(incoming, ignore_errors=True)
        shutil.rmtree(previous, ignore_errors=True)
        shutil.copytree(working, incoming)
        try:
            module_root.rename(previous)
            incoming.rename(module_root)
            _copy_requirements_export(root, module_root, run_id)
            domain = run.get("config", {}).get("domain", {}) if isinstance(run.get("config"), dict) else {}
            final_validation = validate_data_schema(
                module_root,
                rebuild=True,
                known_requirement_ids=allowed_requirement_ids(root),
                logical_types=domain.get("logical_types"),
                cardinalities=domain.get("cardinalities"),
            )
            if not final_validation["valid"]:
                raise RuntimeError(
                    "Applied data schema failed final validation: "
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
            status="applied",
            phase="completed",
            snapshot_id=snapshot["snapshot_id"],
            requirements_data_export=f"exports/requirements_data/{run_id}.json",
        )
        append_event(
            module_root,
            run_id,
            event_type="applied",
            message="Пользователь применил предложенные изменения схемы данных",
            data={"snapshot_id": snapshot["snapshot_id"]},
        )
        clear_active_run(module_root, run_id)
        from backend.modules.data_schema.agent_runs import archive_and_remove_run
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
    source = run_path / "result" / "requirements_data_result.json"
    if not source.is_file():
        return
    target = module_root / "exports" / "requirements_data" / f"{run_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
