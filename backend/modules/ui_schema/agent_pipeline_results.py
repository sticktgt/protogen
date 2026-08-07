from __future__ import annotations

from pathlib import Path
from typing import Iterable

from backend.modules.ui_schema.agent_pipeline_models import PipelineDecision
from backend.modules.ui_schema.agent_traceability import write_traceability_chunk


def write_pipeline_results(
    *,
    run_path: Path,
    decisions: Iterable[PipelineDecision],
    agent_note: str,
    warnings: list[str],
) -> dict:
    links: list[dict] = []
    report = {
        "summary": "",
        "agent_note": str(agent_note or ""),
        "cross_cutting_ui": [],
        "no_ui": [],
        "unclear": [],
        "warnings": [str(item) for item in warnings if str(item).strip()],
    }
    for decision in decisions:
        for target in decision.targets:
            links.append(
                {
                    "requirement_id": decision.requirement_id,
                    "target_type": target.target_type,
                    "target_id": target.target_id,
                    "relation": "implemented_by",
                    "implementation_status": target.implementation_status,
                }
            )
        if decision.classification == "cross_cutting_ui":
            report["cross_cutting_ui"].append(
                {
                    "requirement_id": decision.requirement_id,
                    "reason": decision.reason,
                    "scope": "targeted" if decision.targets else "global",
                }
            )
        elif decision.classification == "no_ui":
            report["no_ui"].append(
                {
                    "requirement_id": decision.requirement_id,
                    "reason": decision.reason,
                }
            )
        elif decision.classification == "unclear":
            report["unclear"].append(
                {
                    "requirement_id": decision.requirement_id,
                    "reason": decision.reason,
                }
            )
    return write_traceability_chunk(
        run_path=run_path,
        working_root=run_path / "working" / "ui_schema",
        result_root=run_path / "result",
        requirement_ui_links={"links": links},
        agent_report=report,
    )
