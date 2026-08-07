from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_diagnostic_settings import run_diagnostic_settings
from backend.modules.ui_schema.files import read_json, write_json

_LOGGER = logging.getLogger(__name__)
_HISTORY_LOCK = threading.RLock()

_ERROR_CODE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Missing required file|Page file does not exist|UI schema folder does not exist", re.I), "missing_file"),
    (re.compile(r"Invalid JSON|must contain a JSON object", re.I), "invalid_json"),
    (re.compile(r"Duplicate UI object id|Duplicate UI link id|Повторяющ", re.I), "duplicate_id"),
    (re.compile(r"missing source|missing target|отсутствующую цель|Cannot infer", re.I), "missing_target"),
    (re.compile(r"non-empty label|непуст.*label", re.I), "missing_label"),
    (re.compile(r"unsupported.*type|not allowed inside|unsupported root type|недопустим.*тип|нельзя размещать", re.I), "invalid_element_type"),
    (re.compile(r"schema\.pages|registered|Unregistered page file|must reference file", re.I), "page_registry"),
    (re.compile(r"requirement|требован", re.I), "requirement_traceability"),
    (re.compile(r"base schema|базов.*схем|protected|preserv", re.I), "base_preservation"),
)


def record_validation_attempt(
    run_path: Path,
    validation: dict[str, Any],
    *,
    source: str,
    retry_index: int | None = None,
) -> None:
    try:
        _record_validation_attempt(
            run_path,
            validation,
            source=source,
            retry_index=retry_index,
        )
    except (OSError, TypeError, ValueError):
        _LOGGER.exception("Failed to record UI Schema validation history")


def _record_validation_attempt(
    run_path: Path,
    validation: dict[str, Any],
    *,
    source: str,
    retry_index: int | None,
) -> None:
    settings = run_diagnostic_settings(run_path).get("validation_history", {})
    if not settings.get("enabled", True):
        return

    errors = [str(item) for item in validation.get("errors", [])]
    warnings = [str(item) for item in validation.get("warnings", [])]
    max_errors = int(settings.get("max_errors_per_entry", 100))
    max_error_length = int(settings.get("max_error_length", 1200))
    max_hints = int(settings.get("max_repair_hints_per_entry", 100))
    hints = validation.get("repair_hints", [])
    hints = hints if isinstance(hints, list) else []

    path = run_path / "result" / "validation_history.json"
    with _HISTORY_LOCK:
        stored = read_json(path, {"format_version": "0.1", "attempts": []})
        attempts = stored.get("attempts", []) if isinstance(stored, dict) else []
        attempts = [item for item in attempts if isinstance(item, dict)]
        sequence = max((int(item.get("sequence", 0)) for item in attempts), default=0) + 1
        entry: dict[str, Any] = {
            "sequence": sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": str(source),
            "valid": bool(validation.get("valid")),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "error_codes": validation_error_codes(errors),
            "errors": [item[:max_error_length] for item in errors[:max_errors]],
            "warnings": [item[:max_error_length] for item in warnings[:max_errors]],
            "repair_hints": hints[:max_hints],
            "assessment_counts": (
                validation.get("assessment_counts", {})
                if isinstance(validation.get("assessment_counts"), dict)
                else {}
            ),
        }
        if retry_index is not None:
            entry["retry_index"] = int(retry_index)
        attempts.append(entry)
        attempts = _bounded_history(attempts, int(settings.get("max_entries", 64)))
        write_json(
            path,
            {
                "format_version": "0.1",
                "attempts": attempts,
                "total_recorded": sequence,
            },
        )


def validation_error_codes(errors: list[str]) -> list[str]:
    return list(dict.fromkeys(_validation_error_code(item) for item in errors))


def _validation_error_code(message: str) -> str:
    for pattern, code in _ERROR_CODE_PATTERNS:
        if pattern.search(message):
            return code
    return "validation_error"


def _bounded_history(items: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    if len(items) <= maximum:
        return items
    if maximum == 1:
        return [items[-1]]
    return [items[0], *items[-(maximum - 1):]]
