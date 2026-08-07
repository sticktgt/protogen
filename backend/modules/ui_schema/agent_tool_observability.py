from __future__ import annotations

import hashlib
import json
from typing import Any


def recoverable_tool_error(output: Any) -> str:
    value = getattr(output, "content", output)
    if isinstance(value, list):
        text_parts = []
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
            elif isinstance(item, str):
                text_parts.append(item)
        value = "".join(text_parts)
    if isinstance(value, dict):
        payload = value
    else:
        text = str(value or "").strip()
        if not text.startswith("{"):
            return ""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return ""
    if isinstance(payload, dict) and payload.get("ok") is False:
        return str(payload.get("error") or "Операция отклонена")[:500]
    return ""


def extract_tool_args(value: Any) -> dict[str, Any]:
    normalized = _plain_tool_value(value)
    if isinstance(normalized, dict):
        return normalized
    text = str(normalized or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text[:500]}
    parsed = _plain_tool_value(parsed)
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def tool_signature(name: str, args: dict[str, Any]) -> str:
    payload = json.dumps(
        [name, _safe_signature_value(args)],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tool_path(args: dict[str, Any]) -> str:
    for key in ("file_path", "path"):
        value = args.get(key)
        if isinstance(value, str):
            return value[:200]
    page_id = args.get("page_id")
    if isinstance(page_id, str) and page_id:
        return "app.json" if page_id == "app" else f"pages/{page_id}.json"

    paths = _bundle_document_paths(args)
    if paths:
        preview = ", ".join(paths[:3])
        suffix = f" и ещё {len(paths) - 3}" if len(paths) > 3 else ""
        return f"{preview}{suffix}"[:300]

    if args.get("items") is not None:
        return "result/coverage_plan.json or result/traceability_items.json"
    supplied = [name for name in ("app", "schema_document", "links") if args.get(name) is not None]
    if supplied:
        return ", ".join(supplied)
    if args.get("links") is not None:
        return "links.json"
    return ""


def tool_file_count(args: dict[str, Any]) -> int | None:
    if isinstance(args.get("page_id"), str):
        return 1
    paths = _bundle_document_paths(args)
    if paths:
        return len(paths)
    if args.get("items") is not None:
        return 1
    supplied = sum(1 for name in ("app", "schema_document", "links") if args.get(name) is not None)
    if supplied:
        return supplied
    if args.get("links") is not None:
        return 1
    return None


def _bundle_document_paths(args: dict[str, Any]) -> list[str]:
    paths: list[str] = []

    def add(path: str) -> None:
        if path and path not in paths:
            paths.append(path)

    for key in ("changes", "moves", "upsert_elements", "move_elements"):
        value = args.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            page_id = item.get("page_id") if isinstance(item, dict) else None
            if isinstance(page_id, str) and page_id:
                add("app.json" if page_id == "app" else f"pages/{page_id}.json")

    pages = _page_writes(args.get("pages") or args.get("create_pages"))
    for item in pages or []:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file_path") or item.get("path") or "").strip()
        if not file_path:
            page_id = str(item.get("page_id") or "").strip()
            file_path = f"pages/{page_id}.json" if page_id else ""
        add(file_path)

    if args.get("ui_links") is not None:
        add("links.json")
    return paths


def tool_message(name: str, path: str) -> str:
    labels = {
        "read_file": "Чтение файла",
        "write_file": "Запись временного файла",
        "edit_file": "Изменение временного файла",
        "ls": "Просмотр каталога",
        "glob": "Поиск файлов",
        "grep": "Поиск по содержимому",
        "load_synchronization_context": "Загрузка контекста синхронизации",
        "write_ui_schema_coverage_plan_batch": "Запись группы плана покрытия требований",
        "review_ui_schema_coverage_plan": "Проверка решений плана покрытия",
        "apply_ui_schema_changes": "Применение пакета изменений UI-схемы",
        "finalize_ui_schema_changes": "Проверка выполнения плана изменений",
        "revise_ui_schema_coverage_plan": "Пересмотр пунктов плана покрытия",
        "write_ui_schema_traceability_batch": "Запись группы трассировки требований",
        "review_ui_schema_traceability": "Проверка итоговой трассировки",
        "validate_ui_schema_state": "Промежуточная проверка UI-схемы",
        "delete_ui_schema_page_file": "Удаление файла страницы",
    }
    label = labels.get(name, f"Вызов инструмента {name}")
    suffix = f": {path}" if path else ""
    return f"{label}{suffix}"


def _page_writes(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("pages"), list):
            return value["pages"]
        return [
            {"file_path": str(name), "content": content}
            for name, content in value.items()
        ]
    if isinstance(value, str):
        try:
            parsed = json.loads(value.strip())
        except json.JSONDecodeError:
            return None
        return _page_writes(parsed)
    return None


def _safe_signature_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _safe_signature_value(item)
            for key, item in value.items()
            if key not in {"content", "data"}
        }
    if isinstance(value, list):
        return [_safe_signature_value(item) for item in value]
    return value


def _plain_tool_value(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            value = model_dump(exclude_none=True)
        except TypeError:
            value = model_dump()
    if isinstance(value, dict):
        return {str(key): _plain_tool_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_tool_value(item) for item in value]
    return value
