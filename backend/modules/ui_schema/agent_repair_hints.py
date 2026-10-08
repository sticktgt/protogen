from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.element_types import root_type_ids, type_definition
from backend.modules.ui_schema.files import read_json


def build_repair_hints(run_path: Path) -> list[dict[str, Any]]:
    """Build deterministic, non-semantic hints for repairable missing link targets."""
    working_root = run_path / "working" / "ui_schema"
    requirement_ids = _requirement_ids(run_path)
    page_ids, element_ids = _schema_ids(working_root)
    links = read_json(
        working_root / "mappings" / "requirement_ui_links.json", {"links": []}
    ).get("links", [])

    hints: list[dict[str, Any]] = _invalid_app_root_hints(run_path)
    for index, link in enumerate(links or []):
        if not isinstance(link, dict):
            continue
        requirement_id = str(link.get("requirement_id") or "")
        if requirement_id not in requirement_ids:
            continue
        target_type = str(link.get("target_type") or "")
        target_id = str(link.get("target_id") or "")
        if not target_id:
            continue
        missing = (
            target_type == "page" and target_id not in page_ids
        ) or (
            target_type == "ui_element" and target_id not in element_ids
        )
        if not missing:
            continue
        page_id = _longest_prefix(target_id, page_ids)
        parent_id = _longest_prefix(target_id, element_ids)
        same_id_alternative = (
            "page" if target_type == "ui_element" and target_id in page_ids
            else "ui_element" if target_type == "page" and target_id in element_ids
            else None
        )
        if same_id_alternative:
            suggested_tool = "write_ui_schema_traceability_batch"
            instruction = (
                f"Объект с ID {target_id} уже существует как {same_id_alternative}. "
                "Перепроверь target_type и перепиши только это требование. Не создавай новый "
                "объект с похожим ID только ради прохождения validation."
            )
        else:
            suggested_tool = (
                "apply_ui_schema_changes" if target_type == "ui_element" and page_id else None
            )
            instruction = (
                "Если цель должна существовать, одним пакетным вызовом создай содержательный "
                "контейнер вместе с минимальными обязательными дочерними элементами из требования. "
                "Не создавай пустой контейнер только ради target ID. Если отдельная цель не нужна, "
                "исправь связь на существующий содержательный объект."
                if target_type == "ui_element" and page_id
                else "Исправь или удали связь, если целевой объект не должен существовать."
            )
        hint = {
            "kind": "missing_requirement_link_target",
            "link_id": str(link.get("id") or f"link[{index}]"),
            "requirement_id": requirement_id,
            "target_type": target_type,
            "target_id": target_id,
            "page_id": page_id,
            "parent_id": parent_id,
            "suggested_tool": suggested_tool,
            "instruction": instruction,
        }
        if same_id_alternative:
            hint["same_id_alternative_target_type"] = same_id_alternative
        hints.append(hint)
    return hints



def _invalid_app_root_hints(run_path: Path) -> list[dict[str, Any]]:
    working_app = read_json(run_path / "working" / "ui_schema" / "app.json", {})
    base_app = read_json(run_path / "base" / "ui_schema" / "app.json", {})
    base_ids: set[str] = set()
    _collect_elements(base_app.get("root_elements", []), base_ids)
    allowed_roots = sorted(root_type_ids(scope="app"))
    hints: list[dict[str, Any]] = []
    for item in working_app.get("root_elements", []) or []:
        if not isinstance(item, dict):
            continue
        element_id = str(item.get("id") or "")
        type_id = str(item.get("type") or "")
        definition = type_definition(type_id)
        invalid = (
            definition is None
            or definition.get("scope") != "app"
            or type_id not in allowed_roots
        )
        if not invalid or not element_id:
            continue
        new_in_run = element_id not in base_ids
        hints.append(
            {
                "kind": "invalid_app_root_type",
                "element_id": element_id,
                "current_type": type_id,
                "allowed_app_root_types": allowed_roots,
                "new_in_current_run": new_in_run,
                "suggested_tool": "apply_ui_schema_changes",
                "alternative_tool": "delete_ui_schema_elements" if new_in_run else None,
                "instruction": (
                    "Замени type этого корневого app-элемента на подходящий тип из "
                    "allowed_app_root_types через upsert_elements с page_id=app. Если новый элемент "
                    "лишний, удали его через delete_ui_schema_elements."
                ),
            }
        )
    return hints

def _requirement_ids(run_path: Path) -> set[str]:
    data = read_json(run_path / "input" / "requirements.json", {"requirements": []})
    return {
        str(item.get("id") or item.get("code") or "")
        for item in data.get("requirements", []) or []
        if isinstance(item, dict) and str(item.get("id") or item.get("code") or "")
    }


def _schema_ids(root: Path) -> tuple[set[str], set[str]]:
    schema = read_json(root / "schema.json", {})
    page_ids = {
        str(item.get("id"))
        for item in schema.get("pages", []) or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    element_ids: set[str] = set()
    app = read_json(root / "app.json", {})
    _collect_elements(app.get("root_elements", []), element_ids)
    for path in sorted((root / "pages").glob("*.json")):
        page = read_json(path, {})
        page_id = page.get("id")
        if isinstance(page_id, str) and page_id:
            page_ids.add(page_id)
        _collect_elements(page.get("elements", []), element_ids)
    return page_ids, element_ids


def _collect_elements(items: Any, target: set[str]) -> None:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            target.add(item_id)
        _collect_elements(item.get("children", []), target)


def _longest_prefix(target_id: str, candidates: set[str]) -> str | None:
    matches = [
        candidate
        for candidate in candidates
        if target_id == candidate or target_id.startswith(candidate + ".")
    ]
    return max(matches, key=len) if matches else None
