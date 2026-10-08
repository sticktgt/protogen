from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_addition_removal import remove_run_additions
from backend.modules.data_schema.agent_completion import validate_agent_working_schema
from backend.modules.data_schema.agent_schema_io import (
    write_dictionaries,
    write_relations,
    write_schema_core,
)
from backend.modules.data_schema.agent_schema_patch import (
    patch_dictionaries,
    patch_relations,
    patch_schema_core,
)
from backend.modules.data_schema.agent_semantic_correction_models import (
    SemanticCorrectionPlanPayload,
)
from backend.modules.data_schema.agent_traceability_patch import patch_requirement_results
from backend.modules.data_schema.files import write_json


def apply_semantic_correction_plan(
    *,
    run_path: Path,
    plan: SemanticCorrectionPlanPayload,
    correction_round: int = 1,
) -> dict[str, Any]:
    """Apply an LLM-selected plan as one technical transaction.

    Backend executes the explicit operations without choosing semantic targets or
    interpreting requirements. An invalid plan is rolled back so the run keeps the
    previous valid working schema and reports the technical correction failure.
    """
    working_root = run_path / "working" / "data_schema"
    result_root = run_path / "result"
    report_path = result_root / "agent_report.json"

    with tempfile.TemporaryDirectory(
        dir=run_path,
        prefix=".semantic-correction-backup-",
    ) as temporary:
        backup_root = Path(temporary)
        backup_working = backup_root / "data_schema"
        shutil.copytree(working_root, backup_working)
        backup_report = backup_root / "agent_report.json"
        report_existed = report_path.is_file()
        if report_existed:
            shutil.copy2(report_path, backup_report)

        operations: list[dict[str, Any]] = []
        try:
            _apply_operations(
                run_path=run_path,
                plan=plan,
                operations=operations,
            )
            validation = validate_agent_working_schema(run_path)
            if not validation.get("valid"):
                raise ValueError(
                    "correction plan produced an invalid schema: "
                    + "; ".join(str(item) for item in validation.get("errors", [])[:20])
                )
        except (ValueError, TypeError, KeyError) as exc:
            _restore_snapshot(
                working_root=working_root,
                backup_working=backup_working,
                report_path=report_path,
                backup_report=backup_report,
                report_existed=report_existed,
            )
            validation = validate_agent_working_schema(run_path)
            result = {
                **validation,
                "correction_applied": False,
                "correction_error": str(exc),
                "correction_operations": operations,
            }
            write_json(
                result_root / f"semantic_correction_application_{correction_round}.json",
                result,
            )
            return result

    result = {
        **validation,
        "correction_applied": True,
        "correction_error": "",
        "correction_operations": operations,
    }
    write_json(
        result_root / f"semantic_correction_application_{correction_round}.json",
        result,
    )
    return result


def _apply_operations(
    *,
    run_path: Path,
    plan: SemanticCorrectionPlanPayload,
    operations: list[dict[str, Any]],
) -> None:
    working_root = run_path / "working" / "data_schema"
    result_root = run_path / "result"

    if plan.write_dictionaries:
        result = write_dictionaries(
            working_root=working_root,
            dictionaries=[
                item.model_dump(exclude_none=True) for item in plan.write_dictionaries
            ],
        )
        operations.append(_operation("write_dictionaries", result))

    if plan.write_schema_document is not None or plan.write_entities:
        result = write_schema_core(
            working_root=working_root,
            schema=(
                plan.write_schema_document.model_dump(exclude_none=True)
                if plan.write_schema_document is not None
                else None
            ),
            entities=[item.model_dump(exclude_none=True) for item in plan.write_entities],
        )
        operations.append(_operation("write_schema_core", result))

    if plan.patch_dictionaries:
        result = patch_dictionaries(
            working_root=working_root,
            dictionaries=[
                item.model_dump(exclude_unset=True, exclude_none=True)
                for item in plan.patch_dictionaries
            ],
        )
        operations.append(_operation("patch_dictionaries", result))

    if plan.patch_schema is not None or plan.patch_entities:
        result = patch_schema_core(
            working_root=working_root,
            schema_patch=(
                plan.patch_schema.model_dump(exclude_unset=True, exclude_none=True)
                if plan.patch_schema is not None
                else None
            ),
            entities=[
                item.model_dump(exclude_unset=True, exclude_none=True)
                for item in plan.patch_entities
            ],
        )
        operations.append(_operation("patch_schema_core", result))

    if plan.write_relations:
        result = write_relations(
            working_root=working_root,
            relations=[item.model_dump(exclude_none=True) for item in plan.write_relations],
        )
        operations.append(_operation("write_relations", result))

    if plan.patch_relations:
        result = patch_relations(
            working_root=working_root,
            relations=[
                item.model_dump(exclude_unset=True, exclude_none=True)
                for item in plan.patch_relations
            ],
        )
        operations.append(_operation("patch_relations", result))

    if plan.remove_targets:
        result = remove_run_additions(
            run_path=run_path,
            targets=list(plan.remove_targets),
        )
        operations.append(_operation("remove_run_additions", result))

    if plan.requirement_updates:
        result = patch_requirement_results(
            working_root=working_root,
            result_root=result_root,
            updates=[
                item.model_dump(exclude_none=True) for item in plan.requirement_updates
            ],
            agent_note=plan.agent_note,
            warnings=plan.warnings,
        )
        operations.append(_operation("patch_requirement_results", result))


def _operation(name: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"operation": name, "result": result}


def _restore_snapshot(
    *,
    working_root: Path,
    backup_working: Path,
    report_path: Path,
    backup_report: Path,
    report_existed: bool,
) -> None:
    shutil.rmtree(working_root)
    shutil.copytree(backup_working, working_root)
    if report_existed:
        shutil.copy2(backup_report, report_path)
    else:
        report_path.unlink(missing_ok=True)
