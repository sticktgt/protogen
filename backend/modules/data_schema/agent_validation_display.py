from __future__ import annotations

from typing import Any

_DEFAULT_VISIBLE_ERRORS = 24


def validation_errors_for_ui(
    errors: Any,
    *,
    maximum: int = _DEFAULT_VISIBLE_ERRORS,
) -> list[str]:
    values = [str(item) for item in (errors or []) if str(item)]
    if len(values) <= maximum:
        return values
    hidden = len(values) - maximum
    return [
        *values[:maximum],
        f"… ещё {hidden} ошибок. Полный список сохранён в диагностическом архиве запуска.",
    ]
