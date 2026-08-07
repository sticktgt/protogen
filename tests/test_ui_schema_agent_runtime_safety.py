from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# The uploaded module bundle intentionally omits the application shell.
# Production provides backend.app.state; the tests need only the type placeholder.
import types
if "backend.app.state" not in sys.modules:
    app_package = types.ModuleType("backend.app")
    app_package.__path__ = []
    state_module = types.ModuleType("backend.app.state")
    state_module.AppState = type("AppState", (), {})
    sys.modules["backend.app"] = app_package
    sys.modules["backend.app.state"] = state_module

from backend.modules.ui_schema.agent_cleanup_review import (
    _normalize_payload,
    run_optional_cleanup_review,
)
from backend.modules.ui_schema.agent_cleanup_review_models import CleanupReviewPayload
from backend.modules.ui_schema.agent_file_diff import build_file_diff
from backend.modules.ui_schema.agent_manual_review import (
    build_manual_review_result,
    merge_traceability_with_inherited_links,
)
from backend.modules.ui_schema.agent_page_tools import write_page_elements
from backend.modules.ui_schema.agent_preservation import delete_new_elements
from backend.modules.ui_schema.agent_validation_rules import validate_requirement_links
from backend.modules.ui_schema.agent_runs import create_run, run_root
from backend.modules.ui_schema.files import read_json, write_json
from backend.modules.ui_schema.requirements_source import file_sha256

AGENT_CONFIG = yaml.safe_load(
    (PROJECT_ROOT / "modules/ui_schema/config.yaml").read_text(encoding="utf-8")
)["agent"]


def test_file_diff_reports_added_modified_and_deleted_files(tmp_path: Path) -> None:
    base = tmp_path / "base"
    working = tmp_path / "working"
    base.mkdir()
    working.mkdir()
    (base / "schema.json").write_text('{\n  "title": "До"\n}\n', encoding="utf-8")
    (working / "schema.json").write_text('{\n  "title": "После"\n}\n', encoding="utf-8")
    (base / "deleted.json").write_text('{"deleted": true}\n', encoding="utf-8")
    (working / "added.json").write_text('{"added": true}\n', encoding="utf-8")
    (base / "index.json").write_text('{"old": true}\n', encoding="utf-8")
    (working / "index.json").write_text('{"new": true}\n', encoding="utf-8")

    result = build_file_diff(base, working)

    assert result["summary"] == {
        "files": 3,
        "added": 1,
        "modified": 1,
        "deleted": 1,
        "additions": 2,
        "deletions": 2,
    }
    assert [item["path"] for item in result["files"]] == [
        "added.json",
        "schema.json",
        "deleted.json",
    ]
    assert all(item["path"] != "index.json" for item in result["files"])



def test_inherited_legacy_requirement_relation_is_warning_not_error() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    validate_requirement_links(
        {
            "links": [
                {
                    "id": "legacy-link",
                    "requirement_id": "REQ-OLD",
                    "target_type": "ui_element",
                    "target_id": "home.summary",
                    "relation": "displays_summary",
                },
                {
                    "id": "current-link",
                    "requirement_id": "REQ-CURRENT",
                    "target_type": "ui_element",
                    "target_id": "home.summary",
                    "relation": "displays_summary",
                },
            ]
        },
        requirement_ids={"REQ-CURRENT"},
        page_ids={"home"},
        element_ids={"home.summary"},
        errors=errors,
        warnings=warnings,
    )

    assert errors == [
        "Связь с требованием current-link использует неподдерживаемый тип связи: displays_summary"
    ]
    assert warnings[0].startswith("Найдены сохранённые связи с 1 требованием")
    assert warnings[1].startswith("У 1 сохранённой связи")


def test_inherited_missing_target_is_manual_review_warning() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    validate_requirement_links(
        {
            "links": [
                {
                    "id": "legacy-link",
                    "requirement_id": "REQ-OLD",
                    "target_type": "ui_element",
                    "target_id": "removed.element",
                    "relation": "implemented_by",
                }
            ]
        },
        requirement_ids=set(),
        page_ids=set(),
        element_ids=set(),
        errors=errors,
        warnings=warnings,
    )

    assert errors == []
    assert warnings[0].startswith("Найдены сохранённые связи с 1 требованием")
    assert warnings[1].startswith("У 1 сохранённой связи")


def test_inherited_requirement_links_are_non_blocking_and_preserved(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    base = run_path / "base" / "ui_schema" / "mappings"
    working = run_path / "working" / "ui_schema" / "mappings"
    input_root = run_path / "input"
    base.mkdir(parents=True)
    working.mkdir(parents=True)
    input_root.mkdir(parents=True)
    write_json(
        input_root / "requirements.json",
        {"requirements": [{"id": "REQ-CURRENT", "name": "Текущее"}]},
    )
    old_link = {
        "id": "old_link",
        "requirement_id": "REQ-OLD",
        "target_type": "ui_element",
        "target_id": "page.legacy",
        "relation": "implemented_by",
    }
    write_json(base / "requirement_ui_links.json", {"links": [old_link]})
    write_json(
        run_path / "working" / "ui_schema" / "app.json",
        {
            "id": "app",
            "title": "App",
            "root_elements": [
                {"id": "page.legacy", "type": "text", "label": "Legacy"}
            ],
        },
    )
    write_json(
        working / "requirement_ui_links.json",
        {
            "links": [
                old_link,
                {
                    "id": "current_link",
                    "requirement_id": "REQ-CURRENT",
                    "target_type": "page",
                    "target_id": "page.current",
                    "relation": "implemented_by",
                },
            ]
        },
    )

    result = build_manual_review_result(run_path)

    assert result["counts"]["inherited_requirement_ids"] == 1
    assert result["counts"]["inherited_requirement_links"] == 1
    assert result["inherited_requirement_links"][0]["requirement_id"] == "REQ-OLD"
    assert result["counts"]["inherited_link_issues"] == 0
    assert read_json(working / "requirement_ui_links.json", {})["links"][0] == old_link


def test_complete_requirement_input_removes_out_of_scope_links(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    mapping = run_path / "working" / "ui_schema" / "mappings"
    input_root = run_path / "input"
    mapping.mkdir(parents=True)
    input_root.mkdir(parents=True)
    write_json(input_root / "requirements.json", {"requirements": [{"id": "REQ-CURRENT"}]})
    write_json(
        mapping / "requirement_ui_links.json",
        {
            "links": [
                {
                    "id": "old",
                    "requirement_id": "REQ-OLD",
                    "target_type": "page",
                    "target_id": "legacy",
                    "relation": "implemented_by",
                },
                {
                    "id": "current-old",
                    "requirement_id": "REQ-CURRENT",
                    "target_type": "page",
                    "target_id": "old-target",
                    "relation": "implemented_by",
                },
            ]
        },
    )

    merged = merge_traceability_with_inherited_links(
        run_path,
        {
            "links": [
                {
                    "id": "current-new",
                    "requirement_id": "REQ-CURRENT",
                    "target_type": "page",
                    "target_id": "new-target",
                    "relation": "implemented_by",
                }
            ]
        },
    )

    assert [item["id"] for item in merged["links"]] == ["current-new"]



def test_absent_requirement_link_is_removed_and_shown_for_manual_decision(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    base_mapping = run_path / "base" / "ui_schema" / "mappings"
    working_mapping = run_path / "working" / "ui_schema" / "mappings"
    input_root = run_path / "input"
    base_mapping.mkdir(parents=True)
    working_mapping.mkdir(parents=True)
    input_root.mkdir(parents=True)
    write_json(
        input_root / "requirements.json",
        {"requirements": [{"id": "REQ-FINAL", "status": "approved"}]},
    )
    legacy_link = {
        "id": "legacy-link",
        "requirement_id": "REQ-REMOVED",
        "target_type": "page",
        "target_id": "legacy.page",
        "relation": "implemented_by",
    }
    write_json(base_mapping / "requirement_ui_links.json", {"links": [legacy_link]})
    write_json(working_mapping / "requirement_ui_links.json", {"links": [legacy_link]})

    merged = merge_traceability_with_inherited_links(
        run_path,
        {
            "links": [
                {
                    "id": "final-link",
                    "requirement_id": "REQ-FINAL",
                    "target_type": "page",
                    "target_id": "final.page",
                    "relation": "implemented_by",
                }
            ]
        },
    )
    write_json(working_mapping / "requirement_ui_links.json", merged)
    review = build_manual_review_result(run_path)

    assert [item["id"] for item in merged["links"]] == ["final-link"]
    assert review["counts"]["inherited_requirement_ids"] == 1
    assert review["inherited_requirement_links"][0]["requirement_id"] == "REQ-REMOVED"
    assert review["inherited_requirement_links"][0]["links"][0]["status"] == "removed"




def test_cleanup_review_accepts_only_exact_base_targets() -> None:
    payload = CleanupReviewPayload.model_validate(
        {
            "summary": "Проверен один кандидат",
            "cleanup_candidates": [
                {
                    "category": "duplicate_navigation",
                    "message": "Старая ссылка выглядит заменённой новой навигацией.",
                    "recommendation": "Сравнить назначения ссылок вручную.",
                    "requirement_ids": ["REQ-1"],
                    "targets": ["ui_link:legacy-link"],
                }
            ],
        }
    )

    result = _normalize_payload(
        payload,
        allowed_targets={"ui_link:legacy-link"},
        max_candidates=5,
    )

    assert result["status"] == "completed"
    assert result["cleanup_candidates"][0]["targets"] == ["ui_link:legacy-link"]

    with pytest.raises(ValueError, match="неизвестные базовые объекты"):
        _normalize_payload(
            payload,
            allowed_targets={"page:other"},
            max_candidates=5,
        )


def test_cleanup_review_is_disabled_by_default_without_model_call(tmp_path: Path, monkeypatch) -> None:
    module_root, run_id = _create_run(tmp_path, requirements=[])
    monkeypatch.setattr(
        "backend.modules.ui_schema.agent_cleanup_review.create_chat_model",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("model must not be called")),
    )

    result = run_optional_cleanup_review(
        root=run_root(module_root, run_id),
        module_root=module_root,
        run_id=run_id,
        llm_settings={},
        agent_config=AGENT_CONFIG,
        callback=None,
    )

    assert result["status"] == "disabled"
    assert result["cleanup_candidates"] == []


def test_cleanup_review_failure_does_not_change_schema_or_fail_run(tmp_path: Path, monkeypatch) -> None:
    module_root, run_id = _create_run(tmp_path, requirements=[])
    root = run_root(module_root, run_id)
    before = (root / "working" / "ui_schema" / "app.json").read_bytes()
    config = {**AGENT_CONFIG, "manual_review": {"cleanup_candidates": {"enabled": True}}}
    monkeypatch.setattr(
        "backend.modules.ui_schema.agent_cleanup_review.build_cleanup_review_context",
        lambda *args, **kwargs: {
            "base_objects": [{"target": "ui_element:app.menu"}],
            "allowed_targets": ["ui_element:app.menu"],
        },
    )
    monkeypatch.setattr(
        "backend.modules.ui_schema.agent_cleanup_review._invoke_cleanup_review",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("temporary review failure")),
    )

    result = run_optional_cleanup_review(
        root=root,
        module_root=module_root,
        run_id=run_id,
        llm_settings={},
        agent_config=config,
        callback=None,
    )

    assert result["status"] == "failed"
    assert "основной результат не изменён" in result["summary"]
    assert (root / "working" / "ui_schema" / "app.json").read_bytes() == before


def test_existing_base_element_cannot_be_deleted_by_agent_tool(tmp_path: Path) -> None:
    base = tmp_path / "base"
    working = tmp_path / "working"
    for root in (base, working):
        (root / "pages").mkdir(parents=True)
        write_json(root / "app.json", {"id": "app", "title": "App", "root_elements": []})
        write_json(
            root / "pages" / "home.json",
            {
                "id": "home",
                "title": "Home",
                "elements": [{"id": "home.title", "type": "text", "label": "Заголовок"}],
            },
        )

    with pytest.raises(ValueError, match="Existing base elements cannot be deleted"):
        delete_new_elements(
            base_root=base,
            working_root=working,
            element_ids=["home.title"],
            reason="test",
        )


def _create_run(tmp_path: Path, *, requirements: list[dict]) -> tuple[Path, str]:
    workspace = tmp_path / "workspace"
    module_root = workspace / "ui_schema"
    shutil.copytree(PROJECT_ROOT / "modules/ui_schema/init", module_root)
    (module_root / "requirements.json").unlink(missing_ok=True)
    source = workspace / "requirements" / "requirements.json"
    source.parent.mkdir(parents=True)
    write_json(source, {"requirements": requirements})
    run = create_run(
        module_root=module_root,
        workspace_id="workspace-test",
        requirements_data={"requirements": requirements},
        requirements_file_name=source.name,
        requirements_source_path="requirements/requirements.json",
        requirements_source_sha256=file_sha256(source),
        user_request="",
        base_mode="current",
        llm_public={"provider": "test", "model": "test"},
        config=AGENT_CONFIG,
    )
    return module_root, run["run_id"]


def test_manual_review_marks_inherited_legacy_relations(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    base_mapping = run_path / "base" / "ui_schema" / "mappings"
    working_mapping = run_path / "working" / "ui_schema" / "mappings"
    input_root = run_path / "input"
    base_mapping.mkdir(parents=True)
    working_mapping.mkdir(parents=True)
    input_root.mkdir(parents=True)
    write_json(input_root / "requirements.json", {"requirements": []})
    legacy_link = {
        "id": "legacy-link",
        "requirement_id": "REQ-OLD",
        "target_type": "page",
        "target_id": "legacy.page",
        "relation": "provides_access",
    }
    write_json(base_mapping / "requirement_ui_links.json", {"links": [legacy_link]})
    write_json(working_mapping / "requirement_ui_links.json", {"links": [legacy_link]})
    working_root = run_path / "working" / "ui_schema"
    write_json(
        working_root / "schema.json",
        {
            "schema_version": "0.1",
            "application": {"name": "App", "description": ""},
            "pages": [
                {"id": "legacy.page", "title": "Legacy", "file": "pages/legacy.page.json"}
            ],
        },
    )
    write_json(
        working_root / "pages" / "legacy.page.json",
        {"id": "legacy.page", "title": "Legacy", "elements": []},
    )

    review = build_manual_review_result(run_path)

    assert review["counts"]["inherited_link_issues"] == 1
    inherited = review["inherited_requirement_links"][0]
    link = inherited["links"][0]
    assert link["target_label"] == "Legacy"
    assert link["page_title"] == "Legacy"
    assert link["relation_label"] == "предоставляет доступ"
    assert link["issues"][0]["code"] == "unsupported_relation"
    assert "implemented_by" in link["issues"][0]["recommendation"]
    assert "provides_access" in inherited["issues"][0]



def test_cleanup_review_payload_requires_russian_narrative() -> None:
    from pydantic import ValidationError
    from backend.modules.ui_schema.agent_cleanup_review_models import CleanupReviewPayload

    with pytest.raises(ValidationError):
        CleanupReviewPayload.model_validate({
            "summary": "No cleanup candidates",
            "cleanup_candidates": [],
        })

    payload = CleanupReviewPayload.model_validate({
        "summary": "Надёжных кандидатов на очистку не найдено.",
        "cleanup_candidates": [],
    })
    assert payload.summary.startswith("Надёжных")


def test_inherited_requirement_warnings_are_russian() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    validate_requirement_links(
        {
            "links": [
                {
                    "id": "legacy-link",
                    "requirement_id": "REQ-OLD",
                    "target_type": "ui_element",
                    "target_id": "home.summary",
                    "relation": "displays_summary",
                }
            ]
        },
        requirement_ids=set(),
        page_ids={"home"},
        element_ids={"home.summary"},
        errors=errors,
        warnings=warnings,
    )

    assert errors == []
    assert warnings[0].startswith("Найдены сохранённые связи с 1 требованием")
    assert "раздел «Ручная проверка»" in warnings[0]
    assert warnings[1].startswith("У 1 сохранённой связи")
    assert "Целевые объекты" in warnings[1]


def test_targeted_element_write_and_explicit_move_are_separate(tmp_path: Path) -> None:
    from backend.modules.ui_schema.agent_element_batch_tools import (
        move_page_elements_batch,
        write_page_elements_batch,
    )

    working = tmp_path / "working" / "ui_schema"
    pages = working / "pages"
    pages.mkdir(parents=True)
    write_json(
        pages / "accounts.list.json",
        {
            "id": "accounts.list",
            "title": "Счета",
            "elements": [
                {
                    "id": "accounts.list.table",
                    "type": "table",
                    "label": "Счета",
                    "children": [
                        {
                            "id": "accounts.list.table.column.number",
                            "type": "table_column",
                            "label": "Номер",
                        }
                    ],
                }
            ],
        },
    )
    write_json(
        pages / "deposits.open.json",
        {
            "id": "deposits.open",
            "title": "Открытие вклада",
            "elements": [
                {"id": "deposits.open.offer_panel", "type": "section", "label": "Условия"},
                {"id": "deposits.open.application", "type": "form", "label": "Заявка"},
                {"id": "deposits.open.calculator", "type": "details_panel", "label": "Расчёт"},
            ],
        },
    )

    write_page_elements_batch(
        working_root=working,
        changes=[
            {
                "page_id": "accounts.list",
                "parent_id": "accounts.list.table",
                "element": {
                    "id": "accounts.list.table.column.status",
                    "type": "table_column",
                    "label": "Статус",
                },
            },
            {
                "page_id": "deposits.open",
                "parent_id": "deposits.open",
                "element": {
                    "id": "deposits.open.wizard",
                    "type": "wizard",
                    "label": "Мастер открытия вклада",
                },
            },
        ],
    )
    move_page_elements_batch(
        working_root=working,
        moves=[
            {
                "page_id": "deposits.open",
                "element_id": element_id,
                "new_parent_id": "deposits.open.wizard",
            }
            for element_id in (
                "deposits.open.offer_panel",
                "deposits.open.application",
                "deposits.open.calculator",
            )
        ],
    )

    accounts = read_json(pages / "accounts.list.json", {})
    table = accounts["elements"][0]
    assert [item["id"] for item in table["children"]] == [
        "accounts.list.table.column.number",
        "accounts.list.table.column.status",
    ]

    deposits = read_json(pages / "deposits.open.json", {})
    assert [item["id"] for item in deposits["elements"]] == ["deposits.open.wizard"]
    assert [item["id"] for item in deposits["elements"][0]["children"]] == [
        "deposits.open.offer_panel",
        "deposits.open.application",
        "deposits.open.calculator",
    ]


def test_validation_repair_hints_point_to_exact_page_and_parent(tmp_path: Path) -> None:
    from backend.modules.ui_schema.agent_repair_hints import build_repair_hints

    run_path = tmp_path / "run"
    working = run_path / "working" / "ui_schema"
    (working / "pages").mkdir(parents=True)
    (working / "mappings").mkdir(parents=True)
    (run_path / "input").mkdir(parents=True)
    write_json(run_path / "input" / "requirements.json", {"requirements": [{"id": "REQ-1"}]})
    write_json(
        working / "schema.json",
        {"pages": [{"id": "accounts.list", "file": "pages/accounts.list.json"}]},
    )
    write_json(working / "app.json", {"root_elements": []})
    write_json(
        working / "pages" / "accounts.list.json",
        {
            "id": "accounts.list",
            "elements": [
                {
                    "id": "accounts.list.table",
                    "type": "table",
                    "label": "Счета",
                    "children": [],
                }
            ],
        },
    )
    write_json(
        working / "mappings" / "requirement_ui_links.json",
        {
            "links": [
                {
                    "id": "link-1",
                    "requirement_id": "REQ-1",
                    "target_type": "ui_element",
                    "target_id": "accounts.list.table.column.status",
                    "relation": "implemented_by",
                }
            ]
        },
    )

    assert build_repair_hints(run_path) == [
        {
            "kind": "missing_requirement_link_target",
            "link_id": "link-1",
            "requirement_id": "REQ-1",
            "target_type": "ui_element",
            "target_id": "accounts.list.table.column.status",
            "page_id": "accounts.list",
            "parent_id": "accounts.list.table",
            "suggested_tool": "apply_ui_schema_changes",
            "instruction": (
                "Если цель должна существовать, одним пакетным вызовом создай содержательный "
                "контейнер вместе с минимальными обязательными дочерними элементами из требования. "
                "Не создавай пустой контейнер только ради target ID. Если отдельная цель не нужна, "
                "исправь связь на существующий содержательный объект."
            ),
        }
    ]


def test_change_bundle_error_recommends_transactional_arguments() -> None:
    from backend.modules.ui_schema.agent_middleware import _tool_error_hint

    hint = _tool_error_hint("apply_ui_schema_changes", ValueError("bad payload"))
    assert "upsert_elements" in hint
    assert "откатывается" in hint
    assert "не повторяй" in hint.lower()


def test_page_elements_rejects_id_already_nested_elsewhere(tmp_path: Path) -> None:
    working_root = tmp_path / "working" / "ui_schema"
    result_root = tmp_path / "result"
    page_path = working_root / "pages" / "cards.list.json"
    original = {
        "id": "cards.list",
        "title": "Карты",
        "description": "",
        "elements": [
            {
                "id": "cards.list.content",
                "type": "section",
                "label": "Содержимое",
                "children": [
                    {
                        "id": "cards.list.table",
                        "type": "table",
                        "label": "Таблица карт",
                        "children": [],
                    }
                ],
            }
        ],
    }
    write_json(page_path, original)

    with pytest.raises(ValueError, match="move existing elements implicitly"):
        write_page_elements(
            working_root=working_root,
            base_root=tmp_path / "base" / "ui_schema",
            result_root=result_root,
            page_id="cards.list",
            elements=[
                {
                    "id": "cards.list.table",
                    "type": "table",
                    "label": "Таблица карт",
                    "children": [
                        {
                            "id": "cards.list.table.column.status",
                            "type": "table_column",
                            "label": "Статус",
                        }
                    ],
                }
            ],
            maximum_top_level_elements=16,
        )

    assert read_json(page_path, {}) == original


def test_page_elements_can_replace_existing_top_level_group(tmp_path: Path) -> None:
    working_root = tmp_path / "working" / "ui_schema"
    result_root = tmp_path / "result"
    page_path = working_root / "pages" / "accounts.list.json"
    write_json(
        page_path,
        {
            "id": "accounts.list",
            "title": "Счета",
            "description": "",
            "elements": [
                {
                    "id": "accounts.list.table",
                    "type": "table",
                    "label": "Старая таблица",
                    "children": [],
                },
                {
                    "id": "accounts.list.filters",
                    "type": "filter_panel",
                    "label": "Фильтры",
                    "children": [],
                },
            ],
        },
    )

    result = write_page_elements(
        working_root=working_root,
        base_root=tmp_path / "base" / "ui_schema",
        result_root=result_root,
        page_id="accounts.list",
        elements=[
            {
                "id": "accounts.list.table",
                "type": "table",
                "label": "Новая таблица",
                "children": [
                    {
                        "id": "accounts.list.table.column.number",
                        "type": "table_column",
                        "label": "Номер",
                    }
                ],
            }
        ],
        maximum_top_level_elements=16,
    )

    page = read_json(page_path, {})
    assert result["ok"] is True
    assert [item["id"] for item in page["elements"]] == [
        "accounts.list.filters",
        "accounts.list.table",
    ]
    assert page["elements"][1]["children"][0]["id"] == "accounts.list.table.column.number"


def test_page_elements_rejects_page_copied_from_base(tmp_path: Path) -> None:
    base_root = tmp_path / "base" / "ui_schema"
    working_root = tmp_path / "working" / "ui_schema"
    result_root = tmp_path / "result"
    base_page = {
        "id": "home",
        "title": "Главная",
        "description": "",
        "elements": [],
    }
    write_json(base_root / "pages" / "home.json", base_page)
    write_json(working_root / "pages" / "home.json", base_page)

    with pytest.raises(ValueError, match="only for a new page"):
        write_page_elements(
            working_root=working_root,
            base_root=base_root,
            result_root=result_root,
            page_id="home",
            elements=[
                {
                    "id": "home.title",
                    "type": "text",
                    "label": "Главная",
                }
            ],
            maximum_top_level_elements=16,
        )
