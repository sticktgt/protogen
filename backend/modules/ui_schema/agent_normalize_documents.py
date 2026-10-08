from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.files import read_json, write_json


def normalize_document_conventions(*, working_root: Path) -> list[dict[str, Any]]:
    """Normalize deterministic storage conventions without inventing UI semantics."""
    actions: list[dict[str, Any]] = []
    actions.extend(_normalize_schema_registry(working_root))
    actions.extend(_normalize_element_labels(working_root))
    return actions


def canonicalize_schema_document(schema: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize page references accepted from provider tool calls."""
    result = dict(schema)
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result
    normalized: list[Any] = []
    for item in pages:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        page = dict(item)
        page_id = page.get("id")
        if isinstance(page_id, str) and page_id.strip():
            page_id = page_id.strip()
            page["id"] = page_id
            page["file"] = f"pages/{page_id}.json"
            page.pop("file_path", None)
            page.pop("path", None)
        normalized.append(page)
    result["pages"] = normalized
    return result


def normalize_element_labels_in_document(document: dict[str, Any], *, collection_key: str) -> int:
    items = document.get(collection_key)
    if not isinstance(items, list):
        return 0
    return _normalize_label_tree(items)


def _normalize_schema_registry(working_root: Path) -> list[dict[str, Any]]:
    path = working_root / "schema.json"
    schema = read_json(path, {})
    if not isinstance(schema, dict):
        return []

    original_pages = schema.get("pages")
    canonical = canonicalize_schema_document(schema)
    pages = canonical.get("pages")
    if not isinstance(pages, list):
        pages = []

    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in pages:
        if not isinstance(item, dict):
            continue
        page_id = item.get("id")
        if not isinstance(page_id, str) or not page_id.strip():
            continue
        page_id = page_id.strip()
        if page_id not in by_id:
            order.append(page_id)
        by_id[page_id] = dict(item)

    added: list[str] = []
    pages_root = working_root / "pages"
    if pages_root.is_dir():
        for page_path in sorted(pages_root.glob("*.json")):
            page = read_json(page_path, {})
            if not isinstance(page, dict):
                continue
            page_id = page.get("id")
            if not isinstance(page_id, str) or not page_id.strip():
                continue
            page_id = page_id.strip()
            expected = f"pages/{page_id}.json"
            current = by_id.get(page_id)
            title = page.get("title")
            if current is None:
                current = {"id": page_id, "file": expected}
                if isinstance(title, str) and title.strip():
                    current["title"] = title.strip()
                by_id[page_id] = current
                order.append(page_id)
                added.append(page_id)
            else:
                current["file"] = expected
                current.pop("file_path", None)
                current.pop("path", None)
                if not current.get("title") and isinstance(title, str) and title.strip():
                    current["title"] = title.strip()

    canonical["pages"] = [by_id[page_id] for page_id in order]
    if canonical == schema:
        return []
    write_json(path, canonical)

    normalized_count = 0
    if isinstance(original_pages, list):
        for item in original_pages:
            if isinstance(item, dict) and ("file_path" in item or "path" in item):
                normalized_count += 1
    message_parts: list[str] = []
    if normalized_count:
        message_parts.append(f"канонизировано ссылок на page-файлы: {normalized_count}")
    if added:
        message_parts.append(f"зарегистрировано page-файлов: {len(added)}")
    return [
        {
            "type": "schema_page_registry_normalized",
            "severity": "info",
            "count": normalized_count + len(added),
            "affected_ids": added,
            "message": "Backend синхронизировал реестр страниц: " + ", ".join(message_parts),
        }
    ]


def _normalize_element_labels(working_root: Path) -> list[dict[str, Any]]:
    total = 0
    documents = [(working_root / "app.json", "root_elements")]
    documents.extend((path, "elements") for path in sorted((working_root / "pages").glob("*.json")))
    for path, collection_key in documents:
        document = read_json(path, {})
        if not isinstance(document, dict):
            continue
        changed = normalize_element_labels_in_document(document, collection_key=collection_key)
        if changed:
            write_json(path, document)
            total += changed
    if not total:
        return []
    return [
        {
            "type": "element_labels_from_titles",
            "severity": "info",
            "count": total,
            "message": (
                f"Backend заполнил label из уже переданного title/text для {total} "
                "UI-элементов; новая бизнес-семантика не добавлялась."
            ),
        }
    ]


def _normalize_label_tree(items: list[Any]) -> int:
    changed = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            for key in ("title", "text", "name", "placeholder"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    item["label"] = candidate.strip()
                    changed += 1
                    break
        children = item.get("children")
        if isinstance(children, list):
            changed += _normalize_label_tree(children)
    return changed
