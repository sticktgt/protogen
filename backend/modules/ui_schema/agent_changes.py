from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from backend.modules.ui_schema.agent_exports import build_requirements_ui_result
from backend.modules.ui_schema.agent_file_diff import write_file_diff_result
from backend.modules.ui_schema.agent_structural_churn import build_structural_churn_report
from backend.modules.ui_schema.files import write_json
from backend.modules.ui_schema.storage import (
    list_pages,
    read_app,
    read_requirement_links,
    read_schema,
    read_ui_links,
)

IGNORED_MANIFEST_PATHS = {"index.json"}


def build_change_report(base_root: Path, working_root: Path) -> dict[str, Any]:
    base = _collect_schema_objects(base_root)
    working = _collect_schema_objects(working_root)
    changes: list[dict[str, Any]] = []
    statistics: dict[str, dict[str, int]] = {}
    category_map = {
        "page": "pages",
        "ui_element": "elements",
        "ui_link": "ui_links",
        "requirement_link": "requirement_links",
        "application": "application",
    }

    for object_type, target_category in category_map.items():
        old_items, new_items = base[object_type], working[object_type]
        added = sorted(new_items.keys() - old_items.keys())
        deleted = sorted(old_items.keys() - new_items.keys())
        modified = sorted(
            key for key in old_items.keys() & new_items.keys()
            if old_items[key]["compare"] != new_items[key]["compare"]
        )
        statistics[target_category] = {
            "added": len(added), "modified": len(modified), "deleted": len(deleted)
        }
        changes.extend(_change_entry("added", after=new_items[key]) for key in added)
        changes.extend(
            _change_entry("modified", before=old_items[key], after=new_items[key])
            for key in modified
        )
        changes.extend(_change_entry("deleted", before=old_items[key]) for key in deleted)

    base_manifest, working_manifest = build_file_manifest(base_root), build_file_manifest(working_root)
    files_added = sorted(working_manifest.keys() - base_manifest.keys())
    files_deleted = sorted(base_manifest.keys() - working_manifest.keys())
    files_modified = sorted(
        path for path in base_manifest.keys() & working_manifest.keys()
        if base_manifest[path]["sha256"] != working_manifest[path]["sha256"]
    )
    statistics["files"] = {
        "added": len(files_added), "modified": len(files_modified), "deleted": len(files_deleted)
    }
    return {
        "statistics": statistics,
        "changes": changes,
        "changed_files": {"added": files_added, "modified": files_modified, "deleted": files_deleted},
    }


def build_file_manifest(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in IGNORED_MANIFEST_PATHS:
            continue
        content = path.read_bytes()
        result[relative] = {"sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}
    return result


def write_result_files(
    *, base_root: Path, working_root: Path, requirements_file: Path,
    agent_report_file: Path, result_path: Path, run: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    changes = build_change_report(base_root, working_root)
    requirements_result = build_requirements_ui_result(
        requirements_file=requirements_file,
        ui_schema_root=working_root,
        agent_report_file=agent_report_file,
        run=run,
    )
    changes["statistics"]["assessments"] = requirements_result["assessment_counts"]
    changes["statistics"]["traceability"] = requirements_result["traceability"]
    changes["traceability_warnings"] = requirements_result.get("traceability_warnings", [])
    changes["requirement_assessments"] = requirements_result.get("assessment_details", {})
    structural_churn = build_structural_churn_report(base_root, working_root)
    changes["structural_churn"] = structural_churn.get("summary", {})
    write_json(result_path / "structural_churn.json", structural_churn)
    write_json(result_path / "changes.json", changes)
    write_file_diff_result(
        base_root=base_root,
        working_root=working_root,
        result_path=result_path,
    )
    write_json(result_path / "requirements_ui_result.json", requirements_result)
    return changes, requirements_result


def _collect_schema_objects(root: Path) -> dict[str, dict[str, dict[str, Any]]]:
    result = {key: {} for key in ("application", "page", "ui_element", "ui_link", "requirement_link")}
    schema = read_schema(root)
    app = read_app(root)
    app_compare = {key: value for key, value in app.items() if key != "root_elements"}
    app_compare["schema_application"] = schema.get("application", {})
    result["application"]["app"] = _item(
        "application", "app", app.get("title") or "Приложение", app_compare
    )
    _collect_elements(app.get("root_elements", []), result["ui_element"], page_id=None)

    for page_order, page_ref in enumerate(list_pages(root)):
        page = page_ref.get("details") or {}
        page_id = page_ref.get("id") or page.get("id")
        if not page_id:
            continue
        compare = {key: value for key, value in page.items() if key != "elements"}
        compare["schema_file"] = page_ref.get("file")
        compare["schema_order"] = page_order
        result["page"][page_id] = {
            **_item("page", page_id, page.get("title") or page_ref.get("title") or page_id, compare),
            "page_id": page_id,
        }
        _collect_elements(page.get("elements", []), result["ui_element"], page_id=page_id)

    for link in read_ui_links(root).get("links", []):
        if not isinstance(link, dict):
            continue
        key = _ui_link_key(link)
        compare = {name: value for name, value in link.items() if name != "id"}
        source_id = link.get("source_id")
        target_id = link.get("target_id")
        source_type = link.get("source_type")
        target_type = link.get("target_type")
        source_page_id = _object_page_id(result, source_type, source_id)
        target_page_id = _object_page_id(result, target_type, target_id)
        result["ui_link"][key] = {
            **_item("ui_link", str(link.get("id") or key), _link_title(link), compare),
            "semantic_key": key,
            "source_id": source_id,
            "target_id": target_id,
            "source_type": source_type,
            "target_type": target_type,
            "source_page_id": source_page_id,
            "target_page_id": target_page_id,
            "page_id": target_page_id or source_page_id,
            "relation": link.get("relation"),
        }

    for link in read_requirement_links(root).get("links", []):
        if not isinstance(link, dict):
            continue
        key = _requirement_link_key(link)
        compare = {name: value for name, value in link.items() if name != "id"}
        target_id = link.get("target_id")
        target_type = link.get("target_type")
        target_page_id = _object_page_id(result, target_type, target_id)
        result["requirement_link"][key] = {
            **_item(
                "requirement_link",
                str(link.get("id") or key),
                f"{link.get('requirement_id')} → {target_id}",
                compare,
            ),
            "semantic_key": key,
            "requirement_id": link.get("requirement_id"),
            "target_id": target_id,
            "target_type": target_type,
            "page_id": target_page_id,
            "relation": link.get("relation"),
        }
    return result


def _object_page_id(
    collected: dict[str, dict[str, dict[str, Any]]],
    object_type: Any,
    object_id: Any,
) -> str | None:
    if object_type == "page" and isinstance(object_id, str):
        return object_id
    if object_type == "ui_element" and isinstance(object_id, str):
        return collected["ui_element"].get(object_id, {}).get("page_id")
    return None


def _item(object_type: str, object_id: str, title: str, compare: dict[str, Any]) -> dict[str, Any]:
    return {"object_type": object_type, "object_id": object_id, "title": title, "compare": compare}


def _collect_elements(
    elements: Iterable[Any], target: dict[str, dict[str, Any]], *,
    page_id: str | None, parent_id: str | None = None,
) -> None:
    for position, element in enumerate(elements or []):
        if not isinstance(element, dict) or not isinstance(element.get("id"), str):
            continue
        element_id = element["id"]
        compare = {key: value for key, value in element.items() if key != "children"}
        compare["parent_id"] = parent_id
        compare["page_id"] = page_id
        compare["position"] = position
        target[element_id] = {
            **_item("ui_element", element_id, element.get("label") or element_id, compare),
            "page_id": page_id, "parent_id": parent_id,
            "position": position,
            "label": element.get("label") or element_id, "element_type": element.get("type"),
        }
        _collect_elements(element.get("children", []), target, page_id=page_id, parent_id=element_id)


def _change_entry(
    action: str, *, before: dict[str, Any] | None = None, after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = after or before or {}
    entry = {"action": action, **{key: value for key, value in source.items() if key != "compare"}}
    old_value = before.get("compare", {}) if before else None
    new_value = after.get("compare", {}) if after else None
    entry["before"] = old_value
    entry["after"] = new_value
    entry["field_changes"] = _field_changes(old_value or {}, new_value or {}) if action == "modified" else []
    return entry


def _field_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"field": key, "before": before.get(key), "after": after.get(key)}
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    ]


def _ui_link_key(link: dict[str, Any]) -> str:
    return "|".join(
        str(link.get(key) or "")
        for key in ("source_type", "source_id", "target_type", "target_id", "relation")
    )


def _requirement_link_key(link: dict[str, Any]) -> str:
    return "|".join(str(link.get(key) or "") for key in ("requirement_id", "target_type", "target_id", "relation"))


def _link_title(link: dict[str, Any]) -> str:
    return f"{link.get('source_id')} {link.get('relation')} {link.get('target_id')}"
