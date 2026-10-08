from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_agent_result_sections_use_same_collapsible_card_wrapper() -> None:
    render = (PROJECT_ROOT / "frontend/modules/ui_schema/js/agent-render.js").read_text(encoding="utf-8")
    manual = (PROJECT_ROOT / "frontend/modules/ui_schema/js/agent-manual-review-render.js").read_text(encoding="utf-8")
    diff = (PROJECT_ROOT / "frontend/modules/ui_schema/js/agent-file-diff-render.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "frontend/modules/ui_schema/css/module.css").read_text(encoding="utf-8")

    assert '<section class="card agent-collapsible-card">' in render
    assert '<section class="card agent-collapsible-card agent-manual-review">' in manual
    assert '<section class="card agent-collapsible-card">' in diff
    assert ".agent-collapsible-card > details > summary" in css
    assert ".agent-collapsible-card .agent-changes-root-body" in css
    assert ".agent-run-meta dd {" in css
    assert ".agent-resource-card strong {" in css
    assert css.count("font-size: 14px;") >= 2
