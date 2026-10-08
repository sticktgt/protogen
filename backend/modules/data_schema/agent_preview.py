from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_changes import write_result_files
from backend.modules.data_schema.agent_diagnostics import build_diagnostics_archive
from backend.modules.data_schema.agent_events import append_event
from backend.modules.data_schema.agent_manual_review import ensure_manual_review_result
from backend.modules.data_schema.agent_report import ensure_agent_report, finalize_agent_report
from backend.modules.data_schema.agent_runs import get_run, run_root, update_run
from backend.modules.data_schema.files import read_json, write_json


def finalize_preview(
    module_root: Path,
    run_id: str,
    validation: dict[str, Any],
    *,
    semantic_review: dict[str, Any] | None = None,
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
        base_root=root / "base" / "data_schema",
        working_root=root / "working" / "data_schema",
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
    review = semantic_review if isinstance(semantic_review, dict) else read_json(
        root / "result" / "semantic_review.json", {}
    )
    if not review.get("status"):
        review = {
            "status": "missing",
            "decision": "revise",
            "blocking": True,
            "review_id": "missing",
            "review_kind": "combined",
            "coverage_complete": False,
            "verified_issue_ids": [],
            "summary": "Смысловой аудит результата не завершён.",
            "review_note": "Перегенерируйте результат перед применением.",
            "strengths": [],
            "issue_counts": {"must_fix": 1, "advisory": 0},
            "issues": [],
        }
    apply_blocked = bool(review.get("blocking"))
    manual_review = ensure_manual_review_result(root, review)
    append_event(
        module_root,
        run_id,
        event_type="preview_ready",
        level="warning" if apply_blocked else "info",
        message=(
            "Результат готов к просмотру, но применение заблокировано смысловыми замечаниями"
            if apply_blocked
            else "Результат прошёл техническую и смысловую проверку"
        ),
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
        ],
        error="",
        stop_reason="",
        semantic_review=review,
        manual_review=manual_review,
        apply_blocked=apply_blocked,
    )
    build_diagnostics_archive(module_root, run_id)
