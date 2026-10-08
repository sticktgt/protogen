from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_changes import write_result_files
from backend.modules.ui_schema.agent_diagnostics import build_diagnostics_archive
from backend.modules.ui_schema.agent_events import append_event
from backend.modules.ui_schema.agent_manual_review import write_manual_review_result
from backend.modules.ui_schema.agent_report import ensure_agent_report, finalize_agent_report
from backend.modules.ui_schema.agent_runs import get_run, run_root, update_run
from backend.modules.ui_schema.files import read_json, write_json


def finalize_preview(
    module_root: Path,
    run_id: str,
    validation: dict[str, Any],
    *,
    cleanup_review: dict[str, Any] | None = None,
    event_message: str = "Проверка пройдена, формируется статистика изменений и preview",
) -> None:
    root = run_root(module_root, run_id)
    ensure_agent_report(root, {})
    write_json(root / "result" / "validation.json", validation)
    update_run(module_root, run_id, phase="building_preview")
    append_event(
        module_root,
        run_id,
        event_type="phase",
        message=event_message,
        data={"phase": "building_preview"},
    )
    run = get_run(module_root, run_id)
    changes, requirements_result = write_result_files(
        base_root=root / "base" / "ui_schema",
        working_root=root / "working" / "ui_schema",
        requirements_file=root / "input" / "requirements.json",
        agent_report_file=root / "result" / "agent_report.json",
        result_path=root / "result",
        run=run,
    )
    report = finalize_agent_report(
        report_path=root / "result" / "agent_report.json",
        changes=changes,
        requirements_result=requirements_result,
    )
    manual_review = write_manual_review_result(root, cleanup_review)
    cleanup_warning = str(
        (manual_review.get("cleanup_review") or {}).get("warning") or ""
    ).strip()
    append_event(
        module_root,
        run_id,
        event_type="preview_ready",
        message="Результат готов к просмотру и подтверждению",
    )
    traceability_warnings = list(requirements_result.get("traceability_warnings", []))
    report_warnings = (
        [str(item) for item in report.get("warnings", [])]
        if isinstance(report.get("warnings"), list)
        else []
    )
    update_run(
        module_root,
        run_id,
        status="preview_ready",
        phase="completed",
        statistics=changes.get("statistics", {}),
        agent_report=str(report.get("summary") or ""),
        agent_note=str(report.get("agent_note") or ""),
        validation_errors=[],
        validation_error_count=0,
        validation_warnings=[
            *validation.get("warnings", []),
            *traceability_warnings,
            *report_warnings,
            *([cleanup_warning] if cleanup_warning else []),
        ],
        error="",
        stop_reason="",
        manual_review=manual_review,
    )
    build_diagnostics_archive(module_root, run_id)
