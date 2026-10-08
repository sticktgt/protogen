from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.files import read_json

_DEFAULTS: dict[str, Any] = {
    "validation_history": {
        "enabled": True,
        "max_entries": 64,
        "max_error_length": 1200,
        "max_errors_per_entry": 100,
        "max_repair_hints_per_entry": 100,
    },
    "tool_trace": {
        "enabled": True,
        "max_entries": 256,
        "max_error_length": 600,
    },
    "source_fingerprints": {
        "enabled": True,
        "include_git_commit": True,
        "build_id_environment": ["PROTOARCHITECT_BUILD_ID", "BUILD_ID"],
        "commit_id_environment": ["GIT_COMMIT", "CI_COMMIT_SHA"],
    },
}


def diagnostic_settings(agent_config: dict[str, Any] | None) -> dict[str, Any]:
    configured = (
        agent_config.get("diagnostics", {})
        if isinstance(agent_config, dict)
        else {}
    )
    configured = configured if isinstance(configured, dict) else {}
    result: dict[str, Any] = {}
    for section, defaults in _DEFAULTS.items():
        value = configured.get(section, {})
        value = value if isinstance(value, dict) else {}
        merged = dict(defaults)
        merged.update(value)
        result[section] = _normalize_section(section, merged)
    return result


def run_diagnostic_settings(run_path: Path) -> dict[str, Any]:
    run = read_json(run_path / "run.json", {})
    config = run.get("config", {}) if isinstance(run, dict) else {}
    return diagnostic_settings(config if isinstance(config, dict) else {})


def _normalize_section(name: str, value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["enabled"] = bool(value.get("enabled", True))
    if name == "validation_history":
        result["max_entries"] = _bounded_int(value.get("max_entries"), 64, 1, 500)
        result["max_error_length"] = _bounded_int(
            value.get("max_error_length"), 1200, 100, 10000
        )
        result["max_errors_per_entry"] = _bounded_int(
            value.get("max_errors_per_entry"), 100, 1, 500
        )
        result["max_repair_hints_per_entry"] = _bounded_int(
            value.get("max_repair_hints_per_entry"), 100, 1, 500
        )
    elif name == "tool_trace":
        result["max_entries"] = _bounded_int(value.get("max_entries"), 256, 1, 2000)
        result["max_error_length"] = _bounded_int(
            value.get("max_error_length"), 600, 100, 5000
        )
    elif name == "source_fingerprints":
        result["include_git_commit"] = bool(value.get("include_git_commit", True))
        for key, default in (
            ("build_id_environment", ["PROTOARCHITECT_BUILD_ID", "BUILD_ID"]),
            ("commit_id_environment", ["GIT_COMMIT", "CI_COMMIT_SHA"]),
        ):
            configured = value.get(key)
            if isinstance(configured, list):
                result[key] = [str(item).strip() for item in configured if str(item).strip()]
            else:
                result[key] = list(default)
    return result


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))
