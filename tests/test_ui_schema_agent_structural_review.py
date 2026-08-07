from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import types

if "backend.app.state" not in sys.modules:
    app_package = types.ModuleType("backend.app")
    app_package.__path__ = []
    state_module = types.ModuleType("backend.app.state")
    state_module.AppState = type("AppState", (), {})
    sys.modules["backend.app"] = app_package
    sys.modules["backend.app.state"] = state_module

from backend.modules.ui_schema.agent_change_bundle import apply_ui_schema_change_bundle
from backend.modules.ui_schema.agent_pipeline_models import (
    PipelineDecision,
    PipelineElementChange,
    PipelineElementMove,
    PipelineStructuralChangeBundle,
    PipelineStructuralResolution,
    PipelineStructuralReviewOutput,
    PipelineTarget,
    PipelineUiLink,
)
from backend.modules.ui_schema.agent_pipeline_structural import (
    run_structural_review,
    validate_structural_review_output,
)
from backend.modules.ui_schema.agent_structural_candidates import (
    collect_structural_candidates,
)
from backend.modules.ui_schema.agent_write_validation import validate_generated_document
from backend.modules.ui_schema.files import read_json, write_json


def test_table_column_requires_table_parent() -> None:
    page = {
        "id": "sample",
        "title": "Sample",
        "elements": [
            {
                "id": "sample.status",
                "type": "table_column",
                "label": "Status",
            }
        ],
    }

    with pytest.raises(
        ValueError,
        match=r"table_column нельзя размещать в корне страницы",
    ):
        validate_generated_document("pages/sample.json", page)

    valid = {
        "id": "sample",
        "title": "Sample",
        "elements": [
            {
                "id": "sample.table",
                "type": "table",
                "label": "Rows",
                "children": [
                    {
                        "id": "sample.status",
                        "type": "table_column",
                        "label": "Status",
                    }
                ],
            }
        ],
    }
    validate_generated_document("pages/sample.json", valid)


def test_structural_candidates_are_limited_to_new_empty_containers_and_duplicates(
    tmp_path: Path,
) -> None:
    base, working = _schema_pair(tmp_path)
    page = read_json(working / "pages/home.json", {})
    page["elements"][0]["children"].extend(
        [
            {
                "id": "home.greeting.copy",
                "type": "text",
                "label": "Приветствие клиента",
            },
            {
                "id": "home.empty_wizard",
                "type": "wizard",
                "label": "Мастер",
                "children": [],
            },
        ]
    )
    write_json(working / "pages/home.json", page)

    decisions = [
        {
            "requirement_id": "R-1",
            "targets": [
                {
                    "target_type": "ui_element",
                    "target_id": "home.greeting.copy",
                }
            ],
        }
    ]
    candidates, context = collect_structural_candidates(
        base_root=base,
        working_root=working,
        decisions=decisions,
        maximum_candidates=10,
    )

    assert {item["kind"] for item in candidates} == {
        "duplicate_siblings",
        "empty_new_container",
    }
    duplicate = next(item for item in candidates if item["kind"] == "duplicate_siblings")
    assert duplicate["new_element_ids"] == ["home.greeting.copy"]
    assert duplicate["existing_element_ids"] == ["home.greeting"]
    assert duplicate["related_requirement_ids"] == ["R-1"]
    assert context["truncated"] is False
    assert set(context["documents"]) == {"home"}


def test_structural_review_removes_new_duplicate_and_updates_decision(
    tmp_path: Path,
) -> None:
    base, working = _schema_pair(tmp_path)
    page = read_json(working / "pages/home.json", {})
    page["elements"][0]["children"].append(
        {
            "id": "home.greeting.copy",
            "type": "text",
            "label": "Приветствие клиента",
        }
    )
    write_json(working / "pages/home.json", page)
    run_path = tmp_path / "run"
    write_json(run_path / "input/task.json", {"operation": "synchronize"})

    current = PipelineDecision(
        requirement_id="R-1",
        ui_effect="display",
        classification="direct_ui",
        targets=[
            PipelineTarget(
                target_type="ui_element",
                target_id="home.greeting.copy",
                action="create",
                implementation_status="implemented",
            )
        ],
        reason="Новое приветствие показывает результат.",
    )
    corrected = PipelineDecision(
        requirement_id="R-1",
        ui_effect="display",
        classification="direct_ui",
        targets=[
            PipelineTarget(
                target_type="ui_element",
                target_id="home.greeting",
                action="reuse",
                implementation_status="implemented",
            )
        ],
        reason="Существующее приветствие уже показывает результат.",
    )

    class FakeRuntime:
        def __init__(self) -> None:
            self.run_path = run_path

        def invoke_validated(self, *, validator, **_kwargs):
            output = PipelineStructuralReviewOutput(
                resolutions=[
                    PipelineStructuralResolution(
                        candidate_id="duplicate:home.greeting.copy",
                        action="remove",
                        reason="Новый элемент дублирует существующий.",
                    )
                ],
                decisions=[corrected],
                changes=PipelineStructuralChangeBundle(
                    remove_elements=["home.greeting.copy"]
                ),
            )
            assert validator(output) == []
            return output

        def apply_changes(
            self, changes, *, allow_remove_new_elements=False, allow_remove_ui_links=False
        ):
            assert allow_remove_new_elements is True
            assert allow_remove_ui_links is True
            return apply_ui_schema_change_bundle(
                working_root=working,
                result_root=run_path / "result",
                base_root=base,
                create_pages=[],
                update_pages=[],
                upsert_elements=[],
                move_elements=[],
                ui_links=[],
                remove_elements=changes.remove_elements,
                remove_ui_links=changes.remove_ui_links,
                no_changes_reason=changes.no_changes_reason,
                maximum_pages=4,
                maximum_top_level_elements=20,
                maximum_element_changes=20,
                maximum_moves=10,
                maximum_links=20,
                maximum_removals=10,
            )

        def event(self, **_kwargs):
            raise AssertionError("repair event is not expected")

    final, _notes, warnings, candidate_count = run_structural_review(
        runtime=FakeRuntime(),
        requirements=[{"id": "R-1", "name": "Приветствие"}],
        decisions=[current],
        maximum_candidates=10,
        maximum_apply_repairs=1,
    )

    assert candidate_count == 1
    assert warnings == []
    assert final[0].targets[0].target_id == "home.greeting"
    updated = read_json(working / "pages/home.json", {})
    child_ids = [item["id"] for item in updated["elements"][0]["children"]]
    assert child_ids == ["home.greeting"]


def test_structural_removal_cannot_delete_base_element_or_base_descendant(
    tmp_path: Path,
) -> None:
    base, working = _schema_pair(tmp_path)

    with pytest.raises(ValueError, match="Existing base elements cannot be removed"):
        apply_ui_schema_change_bundle(
            working_root=working,
            result_root=tmp_path / "result",
            base_root=base,
            create_pages=[],
            update_pages=[],
            upsert_elements=[],
            move_elements=[],
            ui_links=[],
            remove_elements=["home.greeting"],
            maximum_pages=4,
            maximum_top_level_elements=20,
            maximum_element_changes=20,
            maximum_moves=10,
            maximum_links=20,
            maximum_removals=10,
        )


def test_structural_candidates_cover_local_composition_defects(
    tmp_path: Path,
) -> None:
    base, working = _schema_pair(tmp_path)
    for root in (base, working):
        page = read_json(root / "pages/home.json", {})
        page["elements"].append(
            {
                "id": "home.summary_table",
                "type": "table",
                "label": "Сводка",
                "children": [],
            }
        )
        write_json(root / "pages/home.json", page)

    page = read_json(working / "pages/home.json", {})
    page["elements"].extend(
        [
            {
                "id": "home.operations",
                "type": "list",
                "label": "Операции",
                "children": [],
            },
            {
                "id": "home.operations.amount",
                "type": "text",
                "label": "Сумма операции",
            },
            {
                "id": "home.other",
                "type": "section",
                "label": "Другой блок",
                "children": [
                    {
                        "id": "home.other.greeting",
                        "type": "text",
                        "label": "Приветствие клиента",
                    }
                ],
            },
            {
                "id": "home.statement",
                "type": "button",
                "label": "Сформировать выписку",
            },
        ]
    )
    write_json(working / "pages/home.json", page)
    write_json(
        working / "links.json",
        {
            "links": [
                {
                    "id": "link.home.statement",
                    "source_type": "ui_element",
                    "source_id": "home.statement",
                    "target_type": "page",
                    "target_id": "home",
                    "relation": "navigates_to",
                }
            ]
        },
    )

    decisions = [
        {
            "requirement_id": "R-1",
            "targets": [
                {
                    "target_type": "ui_element",
                    "target_id": "home.summary_table",
                    "action": "extend",
                }
            ],
        },
        {
            "requirement_id": "R-2",
            "targets": [
                {
                    "target_type": "ui_element",
                    "target_id": "home.operations.amount",
                    "action": "create",
                }
            ],
        },
        {
            "requirement_id": "R-3",
            "targets": [
                {
                    "target_type": "ui_element",
                    "target_id": "home.other.greeting",
                    "action": "create",
                }
            ],
        },
        {
            "requirement_id": "R-4",
            "targets": [
                {
                    "target_type": "ui_element",
                    "target_id": "home.statement",
                    "action": "create",
                }
            ],
        },
    ]
    candidates, context = collect_structural_candidates(
        base_root=base,
        working_root=working,
        decisions=decisions,
        maximum_candidates=20,
    )

    kinds = {item["kind"] for item in candidates}
    assert {
        "empty_extended_container",
        "empty_new_container",
        "id_container_mismatch",
        "duplicate_page_elements",
        "self_navigation",
    } <= kinds
    placement = next(
        item for item in candidates if item["kind"] == "id_container_mismatch"
    )
    assert placement["new_element_ids"] == ["home.operations.amount"]
    assert placement["facts"]["allowed_parent_ids"] == ["home.operations"]
    self_link = next(item for item in candidates if item["kind"] == "self_navigation")
    assert self_link["link_ids"] == ["link.home.statement"]
    assert context["ui_links"][0]["id"] == "link.home.statement"


def test_structural_output_allows_only_candidate_move_and_link_target_change(
    tmp_path: Path,
) -> None:
    _base, working = _schema_pair(tmp_path)
    candidates = [
        {
            "candidate_id": "placement:home.operations.amount",
            "kind": "id_container_mismatch",
            "page_id": "home",
            "element_ids": ["home.operations.amount", "home.operations"],
            "new_element_ids": ["home.operations.amount"],
            "affected_element_ids": ["home.operations.amount", "home.operations"],
            "link_ids": [],
            "facts": {"allowed_parent_ids": ["home.operations"]},
        },
        {
            "candidate_id": "self_link:link.home.statement",
            "kind": "self_navigation",
            "page_id": "home",
            "element_ids": ["home.statement"],
            "new_element_ids": [],
            "affected_element_ids": ["home.statement"],
            "link_ids": ["link.home.statement"],
            "facts": {
                "source_page_id": "home",
                "link": {
                    "id": "link.home.statement",
                    "source_type": "ui_element",
                    "source_id": "home.statement",
                    "target_type": "page",
                    "target_id": "home",
                    "relation": "navigates_to",
                },
            },
        },
    ]
    output = PipelineStructuralReviewOutput(
        resolutions=[
            PipelineStructuralResolution(
                candidate_id="placement:home.operations.amount",
                action="modify",
                reason="Поле относится к списку операций.",
            ),
            PipelineStructuralResolution(
                candidate_id="self_link:link.home.statement",
                action="modify",
                reason="Кнопка должна вести на отдельную страницу выписки.",
            ),
        ],
        decisions=[],
        changes=PipelineStructuralChangeBundle(
            move_elements=[
                PipelineElementMove(
                    page_id="home",
                    element_id="home.operations.amount",
                    new_parent_id="home.operations",
                )
            ],
            ui_links=[
                PipelineUiLink(
                    id="link.home.statement",
                    source_type="ui_element",
                    source_id="home.statement",
                    target_type="page",
                    target_id="accounts.statement",
                    relation="navigates_to",
                )
            ],
        ),
    )

    assert validate_structural_review_output(
        output,
        candidates=candidates,
        required_ids=set(),
        schema_root=working,
    ) == []


def test_structural_candidates_include_targeted_new_page_without_navigation(
    tmp_path: Path,
) -> None:
    base, working = _schema_pair(tmp_path)
    for root in (base, working):
        write_json(
            root / "app.json",
            {
                "id": "app",
                "root_elements": [
                    {
                        "id": "app.main_menu",
                        "type": "main_menu",
                        "label": "Меню",
                        "children": [
                            {
                                "id": "app.main_menu.home",
                                "type": "menu_item",
                                "label": "Главная",
                            }
                        ],
                    }
                ],
            },
        )
    write_json(
        working / "pages/cards.list.json",
        {"id": "cards.list", "title": "Карты", "elements": []},
    )
    decisions = [
        {
            "requirement_id": "R-CARDS",
            "targets": [
                {
                    "target_type": "page",
                    "target_id": "cards.list",
                    "action": "create",
                }
            ],
        }
    ]

    candidates, context = collect_structural_candidates(
        base_root=base,
        working_root=working,
        decisions=decisions,
        maximum_candidates=10,
    )

    page_candidate = next(
        item
        for item in candidates
        if item["kind"] == "new_page_without_incoming_navigation"
    )
    assert page_candidate["page_id"] == "cards.list"
    assert page_candidate["related_requirement_ids"] == ["R-CARDS"]
    assert page_candidate["facts"]["allowed_navigation_parent_ids"] == [
        "app.main_menu"
    ]
    assert page_candidate["facts"]["existing_navigation_source_ids"] == [
        "app.main_menu.home"
    ]
    assert set(context["documents"]) == {"app", "cards.list"}


def test_structural_candidates_include_existing_container_emptied_by_run(
    tmp_path: Path,
) -> None:
    base, working = _schema_pair(tmp_path)
    for root in (base, working):
        page = read_json(root / "pages/home.json", {})
        page["elements"].append(
            {
                "id": "home.calculator",
                "type": "form",
                "label": "Калькулятор",
                "children": [
                    {
                        "id": "home.calculator.amount",
                        "type": "input",
                        "label": "Сумма",
                    }
                ],
            }
        )
        write_json(root / "pages/home.json", page)

    page = read_json(working / "pages/home.json", {})
    calculator = next(item for item in page["elements"] if item["id"] == "home.calculator")
    amount = calculator["children"].pop()
    page["elements"].append(
        {
            "id": "home.wizard",
            "type": "wizard",
            "label": "Мастер",
            "children": [amount],
        }
    )
    write_json(working / "pages/home.json", page)

    candidates, _context = collect_structural_candidates(
        base_root=base,
        working_root=working,
        decisions=[],
        maximum_candidates=10,
    )

    emptied = next(
        item for item in candidates if item["kind"] == "emptied_existing_container"
    )
    assert emptied["candidate_id"] == "emptied:home.calculator"
    assert emptied["facts"]["original_child_ids"] == ["home.calculator.amount"]
    assert emptied["facts"]["moved_out_child_ids"] == ["home.calculator.amount"]


def test_structural_output_can_add_navigation_for_new_page(
    tmp_path: Path,
) -> None:
    _base, working = _schema_pair(tmp_path)
    write_json(
        working / "app.json",
        {
            "id": "app",
            "root_elements": [
                {
                    "id": "app.main_menu",
                    "type": "main_menu",
                    "label": "Меню",
                    "children": [],
                }
            ],
        },
    )
    candidate = {
        "candidate_id": "new_page_navigation:cards.list",
        "kind": "new_page_without_incoming_navigation",
        "page_id": "cards.list",
        "element_ids": ["app.main_menu"],
        "new_element_ids": [],
        "affected_element_ids": [],
        "link_ids": [],
        "facts": {
            "page_id": "cards.list",
            "allowed_navigation_parent_ids": ["app.main_menu"],
            "existing_navigation_source_ids": [],
        },
    }
    output = PipelineStructuralReviewOutput(
        resolutions=[
            PipelineStructuralResolution(
                candidate_id="new_page_navigation:cards.list",
                action="modify",
                reason="Созданная страница должна быть доступна из меню.",
            )
        ],
        decisions=[],
        changes=PipelineStructuralChangeBundle(
            upsert_elements=[
                PipelineElementChange(
                    page_id="app",
                    parent_id="app.main_menu",
                    element={
                        "id": "app.main_menu.cards",
                        "type": "menu_item",
                        "label": "Карты",
                    },
                )
            ],
            ui_links=[
                PipelineUiLink(
                    source_type="ui_element",
                    source_id="app.main_menu.cards",
                    target_type="page",
                    target_id="cards.list",
                    relation="navigates_to",
                )
            ],
        ),
    )

    assert validate_structural_review_output(
        output,
        candidates=[candidate],
        required_ids=set(),
        schema_root=working,
    ) == []



def test_structural_output_can_add_navigation_for_new_page_with_inferred_types(
    tmp_path: Path,
) -> None:
    _base, working = _schema_pair(tmp_path)
    write_json(
        working / "app.json",
        {
            "id": "app",
            "root_elements": [
                {
                    "id": "app.main_menu",
                    "type": "main_menu",
                    "label": "Меню",
                    "children": [],
                }
            ],
        },
    )
    candidate = {
        "candidate_id": "new_page_navigation:cards.list",
        "kind": "new_page_without_incoming_navigation",
        "page_id": "cards.list",
        "element_ids": ["app.main_menu"],
        "new_element_ids": [],
        "affected_element_ids": [],
        "link_ids": [],
        "facts": {
            "page_id": "cards.list",
            "allowed_navigation_parent_ids": ["app.main_menu"],
            "existing_navigation_source_ids": [],
        },
    }
    output = PipelineStructuralReviewOutput(
        resolutions=[
            PipelineStructuralResolution(
                candidate_id="new_page_navigation:cards.list",
                action="modify",
                reason="Созданная страница должна быть доступна из меню.",
            )
        ],
        decisions=[],
        changes=PipelineStructuralChangeBundle(
            upsert_elements=[
                PipelineElementChange(
                    page_id="app",
                    parent_id="app.main_menu",
                    element={
                        "id": "app.main_menu.cards",
                        "type": "menu_item",
                        "label": "Карты",
                    },
                )
            ],
            ui_links=[
                PipelineUiLink(
                    source_id="app.main_menu.cards",
                    target_id="cards.list",
                    relation="navigates_to",
                )
            ],
        ),
    )

    assert validate_structural_review_output(
        output,
        candidates=[candidate],
        required_ids=set(),
        schema_root=working,
    ) == []


def test_structural_output_rejects_wrong_explicit_target_type_for_new_page(
    tmp_path: Path,
) -> None:
    _base, working = _schema_pair(tmp_path)
    candidate = {
        "candidate_id": "new_page_navigation:cards.list",
        "kind": "new_page_without_incoming_navigation",
        "page_id": "cards.list",
        "element_ids": [],
        "new_element_ids": [],
        "affected_element_ids": [],
        "link_ids": [],
        "facts": {
            "page_id": "cards.list",
            "allowed_navigation_parent_ids": [],
            "existing_navigation_source_ids": ["home.cards"],
        },
    }
    output = PipelineStructuralReviewOutput(
        resolutions=[
            PipelineStructuralResolution(
                candidate_id="new_page_navigation:cards.list",
                action="modify",
                reason="Добавить переход.",
            )
        ],
        decisions=[],
        changes=PipelineStructuralChangeBundle(
            ui_links=[
                PipelineUiLink(
                    source_type="ui_element",
                    source_id="home.cards",
                    target_type="ui_element",
                    target_id="cards.list",
                    relation="navigates_to",
                )
            ],
        ),
    )

    errors = validate_structural_review_output(
        output,
        candidates=[candidate],
        required_ids=set(),
        schema_root=working,
    )
    assert any("вне структурных кандидатов" in item for item in errors)


def test_structural_review_can_remove_new_self_navigation_link(tmp_path: Path) -> None:
    base, working = _schema_pair(tmp_path)
    page = read_json(working / "pages/home.json", {})
    page["elements"].append(
        {"id": "home.statement", "type": "button", "label": "Выписка"}
    )
    write_json(working / "pages/home.json", page)
    write_json(
        working / "links.json",
        {
            "links": [
                {
                    "id": "link.self",
                    "source_type": "ui_element",
                    "source_id": "home.statement",
                    "target_type": "page",
                    "target_id": "home",
                    "relation": "navigates_to",
                }
            ]
        },
    )
    candidates, _ = collect_structural_candidates(
        base_root=base,
        working_root=working,
        decisions=[],
        maximum_candidates=10,
    )
    candidate = next(item for item in candidates if item["kind"] == "self_navigation")
    assert candidate["new_link_ids"] == ["link.self"]

    output = PipelineStructuralReviewOutput(
        resolutions=[
            PipelineStructuralResolution(
                candidate_id=candidate["candidate_id"],
                action="remove",
                reason="Лишний переход на текущую страницу.",
            )
        ],
        decisions=[],
        changes=PipelineStructuralChangeBundle(remove_ui_links=["link.self"]),
    )
    assert validate_structural_review_output(
        output,
        candidates=[candidate],
        required_ids=set(),
        schema_root=working,
    ) == []
    apply_ui_schema_change_bundle(
        working_root=working,
        result_root=tmp_path / "result",
        base_root=base,
        create_pages=[],
        update_pages=[],
        upsert_elements=[],
        move_elements=[],
        ui_links=[],
        remove_elements=[],
        remove_ui_links=["link.self"],
        maximum_pages=4,
        maximum_top_level_elements=20,
        maximum_element_changes=20,
        maximum_moves=10,
        maximum_links=20,
        maximum_removals=10,
    )
    assert read_json(working / "links.json", {})["links"] == []



def test_change_bundle_cannot_remove_base_ui_link(tmp_path: Path) -> None:
    base, working = _schema_pair(tmp_path)
    link = {
        "id": "link.base",
        "source_type": "page",
        "source_id": "home",
        "target_type": "page",
        "target_id": "home",
        "relation": "navigates_to",
    }
    for root in (base, working):
        write_json(root / "links.json", {"links": [link]})

    with pytest.raises(ValueError, match="Нельзя удалить UI-связи из базовой схемы"):
        apply_ui_schema_change_bundle(
            working_root=working,
            result_root=tmp_path / "result",
            base_root=base,
            create_pages=[],
            update_pages=[],
            upsert_elements=[],
            move_elements=[],
            ui_links=[],
            remove_elements=[],
            remove_ui_links=["link.base"],
            maximum_pages=4,
            maximum_top_level_elements=20,
            maximum_element_changes=20,
            maximum_moves=10,
            maximum_links=20,
            maximum_removals=10,
        )
    assert read_json(working / "links.json", {})["links"] == [link]


def test_structural_candidates_detect_multiple_navigation_targets(tmp_path: Path) -> None:
    base, working = _schema_pair(tmp_path)
    for root in (base, working):
        page = read_json(root / "pages/home.json", {})
        page["elements"].append(
            {"id": "home.cards", "type": "button", "label": "Карты"}
        )
        write_json(root / "pages/home.json", page)
        write_json(root / "pages/cards.block.json", {"id": "cards.block", "title": "Блокировка", "elements": []})
        write_json(root / "pages/cards.list.json", {"id": "cards.list", "title": "Карты", "elements": []})
        write_json(
            root / "schema.json",
            {
                "pages": [
                    {"id": "home", "title": "Home"},
                    {"id": "cards.block", "title": "Блокировка"},
                    {"id": "cards.list", "title": "Карты"},
                ]
            },
        )
    write_json(
        base / "links.json",
        {
            "links": [
                {
                    "id": "link.cards.block",
                    "source_type": "ui_element",
                    "source_id": "home.cards",
                    "target_type": "page",
                    "target_id": "cards.block",
                    "relation": "navigates_to",
                }
            ]
        },
    )
    write_json(
        working / "links.json",
        {
            "links": [
                {
                    "id": "link.cards.block",
                    "source_type": "ui_element",
                    "source_id": "home.cards",
                    "target_type": "page",
                    "target_id": "cards.block",
                    "relation": "navigates_to",
                },
                {
                    "id": "link.cards.list",
                    "source_type": "ui_element",
                    "source_id": "home.cards",
                    "target_type": "page",
                    "target_id": "cards.list",
                    "relation": "navigates_to",
                },
            ]
        },
    )

    candidates, context = collect_structural_candidates(
        base_root=base,
        working_root=working,
        decisions=[],
        maximum_candidates=10,
    )
    candidate = next(
        item for item in candidates if item["kind"] == "multiple_navigation_targets"
    )
    assert candidate["link_ids"] == ["link.cards.block", "link.cards.list"]
    assert candidate["new_link_ids"] == ["link.cards.list"]
    assert {item["id"] for item in context["ui_links"]} == {
        "link.cards.block",
        "link.cards.list",
    }
    output = PipelineStructuralReviewOutput(
        resolutions=[
            PipelineStructuralResolution(
                candidate_id=candidate["candidate_id"],
                action="modify",
                reason="Один пункт меню не должен иметь две безусловные цели.",
            )
        ],
        decisions=[],
        changes=PipelineStructuralChangeBundle(remove_ui_links=["link.cards.list"]),
    )
    assert validate_structural_review_output(
        output,
        candidates=[candidate],
        required_ids=set(),
        schema_root=working,
    ) == []


def _schema_pair(tmp_path: Path) -> tuple[Path, Path]:
    run_path = tmp_path / "run"
    base = run_path / "base" / "ui_schema"
    working = run_path / "working" / "ui_schema"
    shutil.copytree(PROJECT_ROOT / "modules/ui_schema/init", base)
    shutil.copytree(PROJECT_ROOT / "modules/ui_schema/init", working)
    page = {
        "id": "home",
        "title": "Home",
        "elements": [
            {
                "id": "home.header",
                "type": "section",
                "label": "Header",
                "children": [
                    {
                        "id": "home.greeting",
                        "type": "text",
                        "label": "Приветствие клиента",
                    }
                ],
            }
        ],
    }
    for root in (base, working):
        write_json(root / "pages/home.json", page)
    return base, working
