from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict


class PipelineOutputEnvelope(BaseModel):
    """Minimal transport envelope for provider-compatible stage output."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any]


def extract_stage_payload(response: Any, *, expected_name: str) -> dict[str, Any]:
    """Extract one stage payload from normalized or provider-native responses."""
    matching = [
        args
        for name, args in _tool_calls(response)
        if name == expected_name
    ]
    if len(matching) > 1:
        raise ValueError(
            f"Ожидался один вызов output tool {expected_name}, получено {len(matching)}"
        )
    if matching:
        return _unwrap_payload(
            matching[0],
            source=f"аргументы output tool {expected_name}",
        )

    content = _response_text(response)
    if content:
        return _unwrap_payload(
            _parse_json_object(content, source="текстовый ответ модели"),
            source="текстовый ответ модели",
        )

    summary = response_transport_summary(response)
    raise ValueError(
        f"Модель не вернула output tool {expected_name} или JSON-объект; "
        f"transport={json.dumps(summary, ensure_ascii=False, separators=(',', ':'))}"
    )


def response_transport_summary(response: Any) -> dict[str, Any]:
    additional = _mapping_value(response, "additional_kwargs")
    content = _mapping_value(response, "content")
    return {
        "response_type": type(response).__name__,
        "normalized_tool_calls": len(_list_value(response, "tool_calls")),
        "additional_keys": sorted(additional) if isinstance(additional, dict) else [],
        "content_type": type(content).__name__,
        "content_length": len(content) if isinstance(content, (str, list)) else 0,
    }


def _tool_calls(response: Any) -> list[tuple[str | None, Any]]:
    result: list[tuple[str | None, Any]] = []
    for call in _list_value(response, "tool_calls"):
        normalized = _normalize_tool_call(call)
        if normalized is not None:
            result.append(normalized)

    additional = _mapping_value(response, "additional_kwargs")
    if isinstance(additional, dict):
        for call in additional.get("tool_calls", []) or []:
            normalized = _normalize_tool_call(call)
            if normalized is not None and normalized not in result:
                result.append(normalized)
        function_call = additional.get("function_call")
        normalized = _normalize_tool_call(function_call)
        if normalized is not None and normalized not in result:
            result.append(normalized)

    content = _mapping_value(response, "content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if str(block.get("type") or "") not in {
                "tool_call",
                "tool_use",
                "function_call",
            }:
                continue
            normalized = _normalize_tool_call(block)
            if normalized is not None and normalized not in result:
                result.append(normalized)
    return result


def _normalize_tool_call(call: Any) -> tuple[str | None, Any] | None:
    if call is None:
        return None
    if isinstance(call, dict):
        function = call.get("function")
        if isinstance(function, dict):
            return function.get("name"), function.get("arguments")
        name = call.get("name")
        args = call.get("args")
        if args is None:
            args = call.get("input")
        if args is None:
            args = call.get("arguments")
        return name, args

    function = getattr(call, "function", None)
    if function is not None:
        if isinstance(function, dict):
            return function.get("name"), function.get("arguments")
        return getattr(function, "name", None), getattr(function, "arguments", None)
    name = getattr(call, "name", None)
    args = getattr(call, "args", None)
    if args is None:
        args = getattr(call, "input", None)
    if name is None and args is None:
        return None
    return name, args


def _unwrap_payload(value: Any, *, source: str) -> dict[str, Any]:
    if isinstance(value, str):
        value = _parse_json_object(value, source=source)
    if not isinstance(value, dict):
        raise ValueError(f"{source} должны быть JSON-объектом")
    if "payload" not in value:
        return value
    payload = value.get("payload")
    if isinstance(payload, str):
        payload = _parse_json_object(payload, source=f"{source}.payload")
    if not isinstance(payload, dict):
        raise ValueError(f"{source}.payload должен быть JSON-объектом")
    return payload


def _response_text(response: Any) -> str:
    content = _mapping_value(response, "content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        if str(block.get("type") or "") not in {"text", "output_text"}:
            continue
        text = block.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts).strip()


def _parse_json_object(value: str, *, source: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
            if text.lower().startswith("json\n"):
                text = text[5:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} не является JSON-объектом") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{source} должен быть JSON-объектом")
    return parsed


def _mapping_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _list_value(value: Any, key: str) -> list[Any]:
    result = _mapping_value(value, key)
    return result if isinstance(result, list) else []
