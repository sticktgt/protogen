from __future__ import annotations

from pathlib import Path

from backend.modules.ui_schema.agent_repair_validation import run_mutation_with_optional_revalidation
from backend.modules.ui_schema.files import write_json


def test_repair_validation_preserves_explicit_invalid_next_action(monkeypatch, tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(run_path / "result/validation_preview.json", {"valid": False, "errors": ["x"]})

    monkeypatch.setattr(
        "backend.modules.ui_schema.agent_repair_validation.validate_and_mark_completion",
        lambda *_args, **_kwargs: {"valid": False, "errors": ["still invalid"]},
    )

    result = run_mutation_with_optional_revalidation(
        run_path=run_path,
        operation=lambda: {
            "ok": True,
            "next_action": "rewrite_dirty_traceability_items",
            "preserve_next_action_after_validation": True,
        },
        enabled=True,
        completed_by="test",
    )

    assert result["next_action"] == "rewrite_dirty_traceability_items"
