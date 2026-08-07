from __future__ import annotations

from pathlib import Path

import pytest

from backend.modules.ui_schema.agent_element_batch_tools import (
    move_page_elements_batch,
    write_page_elements_batch,
)
from backend.modules.ui_schema.agent_parent_preservation import (
    reject_implicit_parent_changes,
)
from backend.modules.ui_schema.agent_structural_churn import (
    build_structural_churn_report,
)
from backend.modules.ui_schema.files import read_json, write_json


def _write_page(root: Path, page_id: str, elements: list[dict]) -> Path:
    path = root / "pages" / f"{page_id}.json"
    write_json(
        path,
        {
            "id": page_id,
            "title": page_id,
            "description": "",
            "elements": elements,
        },
    )
    return path


def test_batch_updates_multiple_pages_and_preserves_existing_parent(tmp_path: Path) -> None:
    working = tmp_path / "ui_schema"
    accounts_path = _write_page(
        working,
        "accounts.list",
        [
            {
                "id": "accounts.list.content",
                "type": "section",
                "label": "Содержимое",
                "children": [
                    {
                        "id": "accounts.list.table",
                        "type": "table",
                        "label": "Счета",
                        "children": [],
                    }
                ],
            }
        ],
    )
    cards_path = _write_page(
        working,
        "cards.list",
        [
            {
                "id": "cards.list.content",
                "type": "section",
                "label": "Карты",
                "children": [],
            }
        ],
    )

    result = write_page_elements_batch(
        working_root=working,
        changes=[
            {
                "page_id": "accounts.list",
                "element": {
                    "id": "accounts.list.table",
                    "type": "table",
                    "label": "Список счетов",
                },
            },
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
                "page_id": "cards.list",
                "parent_id": "cards.list.content",
                "element": {
                    "id": "cards.list.open",
                    "type": "button",
                    "label": "Оформить карту",
                },
            },
        ],
        maximum_changes=10,
    )

    assert result["page_count"] == 2
    accounts = read_json(accounts_path, {})
    content = accounts["elements"][0]
    assert content["children"][0]["id"] == "accounts.list.table"
    assert content["children"][0]["label"] == "Список счетов"
    assert content["children"][0]["children"][0]["id"].endswith("column.status")
    cards = read_json(cards_path, {})
    assert cards["elements"][0]["children"][0]["id"] == "cards.list.open"


def test_new_page_element_without_parent_is_created_at_page_root_atomically(tmp_path: Path) -> None:
    working = tmp_path / "ui_schema"
    page_path = _write_page(
        working,
        "home",
        [{"id": "home.content", "type": "section", "label": "Главная", "children": []}],
    )

    result = write_page_elements_batch(
        working_root=working,
        changes=[
            {
                "page_id": "home",
                "parent_id": "home.content",
                "element": {"id": "home.title", "type": "text", "label": "Обзор"},
            },
            {
                "page_id": "home",
                "element": {"id": "home.action", "type": "button", "label": "Продолжить"},
            },
        ],
    )

    page = read_json(page_path, {})
    assert result["changes"][1]["parent_id"] == "home"
    assert [item["id"] for item in page["elements"]] == ["home.content", "home.action"]
    assert page["elements"][0]["children"][0]["id"] == "home.title"


def test_targeted_update_cannot_change_existing_parent(tmp_path: Path) -> None:
    working = tmp_path / "ui_schema"
    page_path = _write_page(
        working,
        "home",
        [
            {
                "id": "home.left",
                "type": "section",
                "label": "Слева",
                "children": [{"id": "home.value", "type": "text", "label": "Значение"}],
            },
            {"id": "home.right", "type": "section", "label": "Справа", "children": []},
        ],
    )
    original = read_json(page_path, {})

    with pytest.raises(ValueError, match="cannot move it"):
        write_page_elements_batch(
            working_root=working,
            changes=[
                {
                    "page_id": "home",
                    "parent_id": "home.right",
                    "element": {"id": "home.value", "type": "text", "label": "Новое значение"},
                }
            ],
        )

    assert read_json(page_path, {}) == original


def test_explicit_move_changes_parent(tmp_path: Path) -> None:
    working = tmp_path / "ui_schema"
    page_path = _write_page(
        working,
        "home",
        [
            {
                "id": "home.left",
                "type": "section",
                "label": "Слева",
                "children": [{"id": "home.value", "type": "text", "label": "Значение"}],
            },
            {"id": "home.right", "type": "section", "label": "Справа", "children": []},
        ],
    )

    move_page_elements_batch(
        working_root=working,
        moves=[
            {
                "page_id": "home",
                "element_id": "home.value",
                "new_parent_id": "home.right",
            }
        ],
    )

    page = read_json(page_path, {})
    assert page["elements"][0]["children"] == []
    assert page["elements"][1]["children"][0]["id"] == "home.value"


def test_whole_page_payload_rejects_implicit_parent_change() -> None:
    current = [
        {
            "id": "home.content",
            "type": "section",
            "label": "Содержимое",
            "children": [{"id": "home.table", "type": "table", "label": "Таблица"}],
        }
    ]
    incoming = [{"id": "home.table", "type": "table", "label": "Таблица"}]

    with pytest.raises(ValueError, match="move existing elements implicitly"):
        reject_implicit_parent_changes(
            page_id="home",
            current_elements=current,
            incoming_elements=incoming,
        )



def test_structural_churn_report_is_technical_and_deterministic(tmp_path: Path) -> None:
    base = tmp_path / "base"
    working = tmp_path / "working"
    for root in (base, working):
        write_json(root / "app.json", {"id": "app", "root_elements": []})
        write_json(
            root / "schema.json",
            {"pages": [{"id": "home", "title": "Главная", "file": "pages/home.json"}]},
        )

    _write_page(
        base,
        "home",
        [
            {
                "id": "home.left",
                "type": "section",
                "label": "Слева",
                "children": [{"id": "home.value", "type": "text", "label": "Значение"}],
            },
            {"id": "home.right", "type": "section", "label": "Справа", "children": []},
        ],
    )
    _write_page(
        working,
        "home",
        [
            {"id": "home.left", "type": "section", "label": "Слева", "children": []},
            {
                "id": "home.right",
                "type": "section",
                "label": "Справа",
                "children": [
                    {"id": "home.value", "type": "text", "label": "Значение"},
                    {"id": "home.extra", "type": "button", "label": "Действие"},
                ],
            },
        ],
    )

    report = build_structural_churn_report(base, working)
    assert report["summary"] == {
        "moved_existing_elements": 1,
        "emptied_existing_containers": 1,
        "pages_with_count_changes": 1,
    }
    assert report["moved_elements"][0]["element_id"] == "home.value"
    assert report["emptied_containers"][0]["element_id"] == "home.left"
    assert report["page_changes"][0]["element_count_delta"] == 1


def test_page_writer_rejects_existing_page_and_preserves_it(tmp_path: Path) -> None:
    from backend.modules.ui_schema.agent_page_tools import write_page_document

    working = tmp_path / "working"
    result = tmp_path / "result"
    page_path = _write_page(
        working,
        "home",
        [{"id": "home.title", "type": "text", "label": "Главная"}],
    )
    original = read_json(page_path, {})

    with pytest.raises(ValueError, match="accepts new pages only"):
        write_page_document(
            working_root=working,
            result_root=result,
            page_id="home",
            title="Новая главная",
            description="",
            elements=[],
            file_path=None,
            maximum_top_level_elements=16,
        )

    assert read_json(page_path, {}) == original


def test_batch_can_update_app_and_page_in_one_call(tmp_path: Path) -> None:
    working = tmp_path / "ui_schema"
    write_json(
        working / "app.json",
        {
            "id": "app",
            "title": "Приложение",
            "root_elements": [
                {
                    "id": "app.main_menu",
                    "type": "main_menu",
                    "label": "Навигация",
                    "children": [],
                }
            ],
        },
    )
    page_path = _write_page(
        working,
        "overview",
        [{"id": "overview.content", "type": "section", "label": "Обзор", "children": []}],
    )

    result = write_page_elements_batch(
        working_root=working,
        changes=[
            {
                "page_id": "app",
                "parent_id": "app.main_menu",
                "element": {
                    "id": "app.main_menu.overview",
                    "type": "menu_item",
                    "label": "Обзор",
                },
            },
            {
                "page_id": "overview",
                "parent_id": "overview.content",
                "element": {
                    "id": "overview.description",
                    "type": "text",
                    "label": "Краткое описание",
                },
            },
        ],
    )

    assert result["documents"] == ["app", "overview"]
    assert result["document_count"] == 2
    assert result["page_count"] == 1
    app = read_json(working / "app.json", {})
    assert app["root_elements"][0]["children"][0]["id"] == "app.main_menu.overview"
    page = read_json(page_path, {})
    assert page["elements"][0]["children"][0]["id"] == "overview.description"


def test_app_batch_rejects_page_scoped_element_atomically(tmp_path: Path) -> None:
    working = tmp_path / "ui_schema"
    app_path = working / "app.json"
    write_json(
        app_path,
        {
            "id": "app",
            "title": "Приложение",
            "root_elements": [
                {
                    "id": "app.main_menu",
                    "type": "main_menu",
                    "label": "Навигация",
                    "children": [],
                }
            ],
        },
    )
    original = read_json(app_path, {})

    with pytest.raises(ValueError, match="scope"):
        write_page_elements_batch(
            working_root=working,
            changes=[
                {
                    "page_id": "app",
                    "parent_id": "app",
                    "element": {
                        "id": "app.invalid",
                        "type": "section",
                        "label": "Недопустимый корень",
                    },
                }
            ],
        )

    assert read_json(app_path, {}) == original


def test_existing_group_accepts_explicit_nested_upserts_and_preserves_omitted_children(tmp_path: Path) -> None:
    working = tmp_path / "ui_schema"
    page_path = _write_page(
        working,
        "home",
        [
            {
                "id": "home.content",
                "type": "section",
                "label": "Содержимое",
                "children": [
                    {"id": "home.title", "type": "text", "label": "Старый заголовок"},
                    {"id": "home.keep", "type": "text", "label": "Сохранить"},
                ],
            }
        ],
    )

    write_page_elements_batch(
        working_root=working,
        changes=[
            {
                "page_id": "home",
                "element": {
                    "id": "home.content",
                    "type": "section",
                    "label": "Обновлённое содержимое",
                    "children": [
                        {"id": "home.title", "type": "text", "label": "Новый заголовок"},
                        {"id": "home.action", "type": "button", "label": "Продолжить"},
                    ],
                },
            }
        ],
    )

    content = read_json(page_path, {})["elements"][0]
    assert content["label"] == "Обновлённое содержимое"
    assert [item["id"] for item in content["children"]] == [
        "home.title",
        "home.keep",
        "home.action",
    ]
    assert content["children"][0]["label"] == "Новый заголовок"


def test_new_app_root_type_can_omit_parent_id(tmp_path: Path) -> None:
    working = tmp_path / "ui_schema"
    write_json(
        working / "app.json",
        {"id": "app", "title": "Приложение", "root_elements": []},
    )

    write_page_elements_batch(
        working_root=working,
        changes=[
            {
                "page_id": "app",
                "element": {
                    "id": "app.top_bar",
                    "type": "top_bar",
                    "label": "Верхняя панель",
                    "children": [],
                },
            }
        ],
    )

    app = read_json(working / "app.json", {})
    assert app["root_elements"][0]["id"] == "app.top_bar"
