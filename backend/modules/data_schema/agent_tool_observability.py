from __future__ import annotations

import hashlib
import json
from typing import Any


def recoverable_tool_error(output: Any) -> str:
    value = getattr(output, "content", output)
    if isinstance(value, list):
        value = "".join(
            str(item.get("text") or "") if isinstance(item, dict) else str(item)
            for item in value
        )
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
    payload = json.dumps([name, _safe_signature_value(args)], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tool_argument_shape(args: dict[str, Any]) -> dict[str, str]:
    """Return only argument types and sizes, without logging business content."""
    return {str(key): _value_shape(value) for key, value in sorted(args.items())}


def tool_path(args: dict[str, Any]) -> str:
    if args.get("dictionaries") is not None:
        return f"dictionaries: {_collection_count(args.get('dictionaries'))}"
    if args.get("entities") is not None:
        return f"entities: {_collection_count(args.get('entities'))}"
    if args.get("relations") is not None:
        return f"relations: {_collection_count(args.get('relations'))}"
    if args.get("updates") is not None:
        return f"requirement updates: {_collection_count(args.get('updates'))}"
    if args.get("links") is not None:
        return f"requirement links: {_collection_count(args.get('links'))}"
    if any(args.get(key) is not None for key in ("cross_cutting_data", "no_data", "unclear")):
        return "agent_report.json"
    return ""


def tool_file_count(args: dict[str, Any]) -> int | None:
    if args.get("dictionaries") is not None:
        return 1
    if args.get("entities") is not None:
        return _collection_count(args.get("entities")) + 1
    if args.get("updates") is not None:
        return 2
    if args.get("relations") is not None or args.get("links") is not None:
        return 1
    return None


def tool_message(name: str, path: str) -> str:
    labels = {
        "load_synchronization_context": "Загрузка контекста синхронизации",
        "write_data_schema_dictionaries": "Запись справочников",
        "write_data_schema_core": "Запись сущностей и полей",
        "write_data_schema_relations": "Запись связей сущностей",
        "write_data_schema_traceability": "Запись полной трассировки требований",
        "validate_data_schema_state": "Проверка временной схемы данных",
    }
    label = labels.get(name, f"Вызов инструмента {name}")
    return f"{label}: {path}" if path else label


def _safe_signature_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _safe_signature_value(item)
            for key, item in value.items()
            if key not in {"description", "agent_note", "reason"}
        }
    if isinstance(value, list):
        return [_safe_signature_value(item) for item in value]
    return value


def _collection_count(value: Any) -> int:
    candidate = value
    if isinstance(candidate, str):
        text = candidate.strip()
        if text.startswith(("[", "{")):
            try:
                candidate = json.loads(text)
            except json.JSONDecodeError:
                return 0
    if isinstance(candidate, dict) and len(candidate) == 1:
        nested = next(iter(candidate.values()))
        if isinstance(nested, list):
            candidate = nested
    return len(candidate) if isinstance(candidate, list) else 0


def _value_shape(value: Any) -> str:
    if isinstance(value, dict):
        return f"object[{len(value)}]"
    if isinstance(value, list):
        return f"array[{len(value)}]"
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{"):
            return f"json-string<object>({len(value)})"
        if text.startswith("["):
            return f"json-string<array>({len(value)})"
        return f"string({len(value)})"
    if value is None:
        return "null"
    return type(value).__name__

