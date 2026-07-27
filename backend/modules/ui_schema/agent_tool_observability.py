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
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"raw": text[:500]}


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
    pages = _page_writes(args.get("pages"))
    if pages:
        paths = [
            str(item.get("file_path") or item.get("path") or "")
            for item in pages
            if isinstance(item, dict)
        ]
        paths = [item for item in paths if item]
        if paths:
            preview = ", ".join(paths[:3])
            suffix = f" и ещё {len(paths) - 3}" if len(paths) > 3 else ""
            return f"{preview}{suffix}"[:300]
    supplied = [name for name in ("app", "schema_document", "links") if args.get(name) is not None]
    if supplied:
        return ", ".join(supplied)
    if args.get("requirement_ui_links") is not None:
        return "requirement_ui_links.json, agent_report.json"
    return ""


def tool_file_count(args: dict[str, Any]) -> int | None:
    pages = _page_writes(args.get("pages"))
    if pages is not None:
        return len(pages)
    supplied = sum(1 for name in ("app", "schema_document", "links") if args.get(name) is not None)
    if supplied:
        return supplied
    if args.get("requirement_ui_links") is not None:
        return 2
    return None


def tool_message(name: str, path: str) -> str:
    labels = {
        "read_file": "Чтение файла",
        "write_file": "Запись временного файла",
        "edit_file": "Изменение временного файла",
        "ls": "Просмотр каталога",
        "glob": "Поиск файлов",
        "grep": "Поиск по содержимому",
        "load_synchronization_context": "Загрузка контекста синхронизации",
        "write_ui_schema_core": "Запись структуры приложения и UI-связей",
        "write_ui_schema_pages": "Пакетная запись страниц UI-схемы",
        "write_ui_schema_traceability": "Запись трассировки требований и отчёта",
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
