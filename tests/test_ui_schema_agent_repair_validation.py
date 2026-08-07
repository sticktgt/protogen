from __future__ import annotations

from pathlib import Path

from backend.modules.ui_schema.agent_repair_validation import (
    run_mutation_with_optional_revalidation,
)
from backend.modules.ui_schema.files import write_json


def test_successful_repair_write_revalidates_pending_invalid_state(
    tmp_path: Path, monkeypatch
) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "result" / "validation_preview.json",
        {"valid": False, "errors": ["technical error"], "warnings": []},
    )
    calls: list[str] = []

    def fake_validate(path: Path, *, completed_by: str):
        assert path == run_path
        calls.append(completed_by)
        return {"valid": True, "errors": [], "warnings": []}

    monkeypatch.setattr(
        "backend.modules.ui_schema.agent_repair_validation.validate_and_mark_completion",
        fake_validate,
    )

    result = run_mutation_with_optional_revalidation(
        run_path=run_path,
        operation=lambda: {"ok": True, "change_count": 2},
        enabled=True,
        completed_by="write_ui_schema_elements:repair_validation",
    )

    assert calls == ["write_ui_schema_elements:repair_validation"]
    assert result["completed"] is True
    assert result["next_action"] == "stop"
    assert result["repair_validation"]["valid"] is True


def test_normal_write_does_not_trigger_extra_validation(tmp_path: Path, monkeypatch) -> None:
    run_path = tmp_path / "run"
    monkeypatch.setattr(
        "backend.modules.ui_schema.agent_repair_validation.validate_and_mark_completion",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not validate")),
    )

    result = run_mutation_with_optional_revalidation(
        run_path=run_path,
        operation=lambda: {"ok": True},
        enabled=True,
        completed_by="write_ui_schema_elements:repair_validation",
    )

    assert result == {"ok": True}
