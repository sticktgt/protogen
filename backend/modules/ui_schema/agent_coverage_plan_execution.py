from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_coverage_plan import require_coverage_plan
from backend.modules.ui_schema.agent_requirement_scope import current_requirement_ids
from backend.modules.ui_schema.agent_target_catalog import build_target_catalog
from backend.modules.ui_schema.files import read_json, write_json
from backend.modules.ui_schema.storage import list_pages, read_app

_RESULT_FILE = "coverage_plan_execution.json"


def build_coverage_plan_execution_report(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = require_coverage_plan(run_path)
    base_root = run_path / "base" / "ui_schema"
    working_root = run_path / "working" / "ui_schema"
    base = _target_fingerprints(base_root)
    working = _target_fingerprints(working_root)
    working_catalog = build_target_catalog(working_root)
    blocking_gaps: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    checked = 0

    for item in plan.get("items", []) if isinstance(plan, dict) else []:
        if not isinstance(item, dict) or str(item.get("classification") or "") not in {
            "direct_ui",
            "cross_cutting_ui",
        }:
            continue
        requirement_id = str(item.get("requirement_id") or "").strip()
        for target in item.get("targets", []) if isinstance(item.get("targets"), list) else []:
            if not isinstance(target, dict):
                continue
            action = str(target.get("action") or "").strip()
            if action not in {"create", "extend"}:
                continue
            checked += 1
            target_type = str(target.get("target_type") or "").strip()
            target_id = str(target.get("target_id") or "").strip()
            key = (target_type, target_id)
            base_value = base.get(key)
            working_value = working.get(key)
            signal = ""
            blocking = False
            if action == "create":
                if working_value is None:
                    signal = "planned_create_target_missing"
                    blocking = True
                elif base_value is not None:
                    signal = "planned_create_target_already_existed"
            elif action == "extend":
                if working_value is None:
                    signal = "planned_extend_target_missing"
                    blocking = True
                elif base_value is None:
                    signal = "planned_extend_target_not_in_base"
                elif working_value == base_value:
                    signal = "planned_extend_target_unchanged"
            target_facts = working_catalog.get(key, {})
            if (
                not blocking
                and working_value is not None
                and target_type == "ui_element"
                and str(target_facts.get("element_kind") or "") == "group"
                and int(target_facts.get("child_count") or 0) == 0
            ):
                signal = "planned_group_target_empty"
                blocking = False
            if not signal:
                continue
            record = {
                "requirement_id": requirement_id,
                "target_type": target_type,
                "target_id": target_id,
                "planned_action": action,
                "signal": signal,
            }
            if signal == "planned_group_target_empty" and target_facts:
                record["target_facts"] = {
                    "element_type": str(target_facts.get("element_type") or ""),
                    "element_kind": str(target_facts.get("element_kind") or ""),
                    "child_count": int(target_facts.get("child_count") or 0),
                    "label": str(target_facts.get("label") or ""),
                }
            if blocking:
                blocking_gaps.append(record)
            else:
                observations.append(record)

    payload = {
        "policy": {
            "comparison_is_structural_only": True,
            "backend_does_not_judge_semantic_sufficiency": True,
            "missing_planned_targets_block_finalization": True,
            "empty_planned_group_targets_are_review_observations": True,
            "unchanged_or_misclassified_existing_targets_are_review_observations": True,
        },
        "checked_target_count": checked,
        "gap_count": len(blocking_gaps),
        "blocking_gap_count": len(blocking_gaps),
        "observation_count": len(observations),
        "gaps": blocking_gaps,
        "observations": observations,
        "complete": not blocking_gaps,
    }
    write_json(run_path / "result" / _RESULT_FILE, payload)
    return payload



def finalize_coverage_plan_execution(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_coverage_plan_execution_report(run_path, agent_config=agent_config)
    if report.get("gaps"):
        return {
            **report,
            "ok": False,
            "completed": False,
            "next_action": "apply_missing_targets_or_revise_coverage_plan",
        }
    write_json(
        run_path / "result" / _RESULT_FILE,
        {**report, "complete": True},
    )
    return {**report, "ok": True, "complete": True}


def coverage_plan_execution_errors(run_path: Path) -> list[str]:
    if not current_requirement_ids(run_path):
        return []
    data = read_json(run_path / "result" / _RESULT_FILE, {})
    if bool(data.get("complete")):
        return []
    return [
        "Coverage plan execution is not finalized: create the missing planned targets or explicitly revise those plan items before final traceability"
    ]


def require_coverage_plan_execution_complete(run_path: Path) -> None:
    errors = coverage_plan_execution_errors(run_path)
    if errors:
        raise ValueError(" | ".join(errors))


def invalidate_coverage_plan_execution(run_path: Path) -> None:
    path = run_path / "result" / _RESULT_FILE
    current = read_json(path, {})
    if current:
        write_json(path, {**current, "complete": False})


def _target_fingerprints(schema_root: Path) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    app = read_app(schema_root)
    _collect_elements(app.get("root_elements", []), result)
    for page_ref in list_pages(schema_root):
        page = page_ref.get("details") or {}
        page_id = str(page_ref.get("id") or page.get("id") or "").strip()
        if not page_id:
            continue
        result[("page", page_id)] = _fingerprint(page)
        _collect_elements(page.get("elements", []), result)
    return result


def _collect_elements(elements: Any, result: dict[tuple[str, str], str]) -> None:
    for element in elements if isinstance(elements, list) else []:
        if not isinstance(element, dict):
            continue
        element_id = str(element.get("id") or "").strip()
        if not element_id:
            continue
        result[("ui_element", element_id)] = _fingerprint(element)
        _collect_elements(element.get("children", []), result)


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
