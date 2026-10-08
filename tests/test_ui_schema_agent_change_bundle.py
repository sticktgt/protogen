from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.ui_schema.agent_change_bundle import (
    UiSchemaChangeBundleArgs,
    apply_ui_schema_change_bundle,
)
from backend.modules.ui_schema.files import read_json, write_json

def test_change_bundle_applies_pages_elements_and_links_transactionally(tmp_path: Path) -> None:
    working = _prepared_schema(tmp_path)
    result = tmp_path / "result"

    response = apply_ui_schema_change_bundle(
        working_root=working,
        result_root=result,
        create_pages=[
            {
                "page_id": "page.two",
                "title": "Second page",
                "elements": [
                    {
                        "id": "page.two.main",
                        "type": "section",
                        "label": "Main",
                    }
                ],
            }
        ],
        upsert_elements=[
            {
                "page_id": "page.one",
                "parent_id": "page.one.main",
                "element": {
                    "id": "page.one.value",
                    "type": "button",
                    "label": "Open second page",
                },
            }
        ],
        move_elements=[],
        ui_links=[
            {
                "source_id": "page.one.value",
                "target_id": "page.two",
                "relation": "navigates_to",
            }
        ],
        maximum_pages=4,
        maximum_top_level_elements=10,
        maximum_element_changes=20,
        maximum_moves=10,
        maximum_links=20,
    )

    assert response["ok"] is True
    assert response["created_pages"] == ["page.two"]
    assert response["element_change_count"] == 1
    assert response["touched_target_ids"] == [
        "page.one",
        "page.one.main",
        "page.one.value",
        "page.two",
    ]
    assert read_json(working / "pages/page.two.json", {})["id"] == "page.two"
    assert read_json(working / "links.json", {})["links"][0]["target_id"] == "page.two"

def test_change_bundle_rejects_non_interactive_ui_link_source_transactionally(
    tmp_path: Path,
) -> None:
    working = _prepared_schema(tmp_path)
    before_links = read_json(working / "links.json", {})

    with pytest.raises(
        ValueError,
        match=r"Элемент page\.one\.main не может быть источником UI-связи",
    ):
        apply_ui_schema_change_bundle(
            working_root=working,
            result_root=tmp_path / "result",
            create_pages=[],
            update_pages=[],
            upsert_elements=[],
            move_elements=[],
            ui_links=[
                {
                    "source_id": "page.one.main",
                    "target_id": "page.one",
                    "relation": "navigates_to",
                }
            ],
            maximum_pages=4,
            maximum_top_level_elements=10,
            maximum_element_changes=20,
            maximum_moves=10,
            maximum_links=20,
        )

    assert read_json(working / "links.json", {}) == before_links

def test_change_bundle_rolls_back_all_changes_on_failure(tmp_path: Path) -> None:
    working = _prepared_schema(tmp_path)
    before_schema = read_json(working / "schema.json", {})

    with pytest.raises(ValueError, match="Parent element missing.parent"):
        apply_ui_schema_change_bundle(
            working_root=working,
            result_root=tmp_path / "result",
            create_pages=[
                {
                    "page_id": "page.two",
                    "title": "Second page",
                    "elements": [],
                }
            ],
            upsert_elements=[
                {
                    "page_id": "page.one",
                    "parent_id": "missing.parent",
                    "element": {
                        "id": "page.one.value",
                        "type": "text",
                        "label": "Visible value",
                    },
                }
            ],
            move_elements=[],
            ui_links=[],
            maximum_pages=4,
            maximum_top_level_elements=10,
            maximum_element_changes=20,
            maximum_moves=10,
            maximum_links=20,
        )

    assert not (working / "pages/page.two.json").exists()
    assert read_json(working / "schema.json", {}) == before_schema
    page = read_json(working / "pages/page.one.json", {})
    assert page["elements"][0].get("children", []) == []

def test_change_bundle_can_confirm_that_no_file_changes_are_needed(tmp_path: Path) -> None:
    working = _prepared_schema(tmp_path)

    args = UiSchemaChangeBundleArgs(no_changes_reason="Existing UI already covers the reviewed plan.")
    response = apply_ui_schema_change_bundle(
        working_root=working,
        result_root=tmp_path / "result",
        create_pages=args.create_pages,
        upsert_elements=args.upsert_elements,
        move_elements=args.move_elements,
        ui_links=args.ui_links,
        no_changes_reason=args.no_changes_reason,
        maximum_pages=4,
        maximum_top_level_elements=10,
        maximum_element_changes=20,
        maximum_moves=10,
        maximum_links=20,
    )

    assert response["ok"] is True
    assert response["no_changes"] is True
    assert response["touched_target_ids"] == []

def test_change_bundle_requires_operations_or_explicit_no_change_reason(tmp_path: Path) -> None:
    args = UiSchemaChangeBundleArgs()
    with pytest.raises(ValueError, match="At least one change operation"):
        apply_ui_schema_change_bundle(
            working_root=_prepared_schema(tmp_path),
            result_root=tmp_path / "result",
            create_pages=args.create_pages,
            upsert_elements=args.upsert_elements,
            move_elements=args.move_elements,
            ui_links=args.ui_links,
            no_changes_reason=args.no_changes_reason,
            maximum_pages=4,
            maximum_top_level_elements=10,
            maximum_element_changes=20,
            maximum_moves=10,
            maximum_links=20,
        )

def test_change_bundle_updates_existing_page_metadata_transactionally(
    tmp_path: Path,
) -> None:
    working = _prepared_schema(tmp_path)

    response = apply_ui_schema_change_bundle(
        working_root=working,
        result_root=tmp_path / "result",
        create_pages=[],
        update_pages=[
            {
                "page_id": "page.one",
                "title": "Updated page",
                "description": "Updated purpose",
            }
        ],
        upsert_elements=[],
        move_elements=[],
        ui_links=[],
        maximum_pages=4,
        maximum_top_level_elements=10,
        maximum_element_changes=20,
        maximum_moves=10,
        maximum_links=20,
    )

    assert response["updated_pages"] == ["page.one"]
    assert response["updated_page_count"] == 1
    assert "page.one" in response["touched_target_ids"]
    page = read_json(working / "pages/page.one.json", {})
    assert page["title"] == "Updated page"
    assert page["description"] == "Updated purpose"
    schema = read_json(working / "schema.json", {})
    assert schema["pages"][0]["title"] == "Updated page"

def _prepared_schema(tmp_path: Path) -> Path:
    working = tmp_path / "working/ui_schema"
    write_json(
        working / "schema.json",
        {
            "schema_version": "0.1",
            "application": {"name": "Sample"},
            "pages": [
                {"id": "page.one", "title": "First page", "file": "pages/page.one.json"}
            ],
        },
    )
    write_json(
        working / "app.json",
        {"id": "app", "title": "Sample", "root_elements": []},
    )
    write_json(working / "links.json", {"links": []})
    write_json(
        working / "pages/page.one.json",
        {
            "id": "page.one",
            "title": "First page",
            "elements": [
                {
                    "id": "page.one.main",
                    "type": "section",
                    "label": "Main",
                    "children": [],
                }
            ],
        },
    )
    return working

def test_change_bundle_args_decode_strict_json_arrays() -> None:
    args = UiSchemaChangeBundleArgs.model_validate(
        {
            "create_pages": '[{"page_id":"page.two","title":"Second page","elements":[]}]',
            "upsert_elements": "[]",
            "move_elements": "[]",
            "ui_links": "[]",
        }
    )

    assert len(args.create_pages) == 1
    assert args.create_pages[0].page_id == "page.two"
    assert args.upsert_elements == []

def test_change_bundle_args_do_not_treat_markdown_as_json() -> None:
    with pytest.raises(Exception):
        UiSchemaChangeBundleArgs.model_validate(
            {
                "create_pages": '```json\n[{"page_id":"page.two","title":"Second page"}]\n```'
            }
        )

def test_change_bundle_accepts_id_as_page_id_alias() -> None:
    args = UiSchemaChangeBundleArgs.model_validate(
        {
            "create_pages": [
                {"id": "page.alias", "title": "Alias page", "elements": []}
            ]
        }
    )

    assert args.create_pages[0].page_id == "page.alias"

def test_change_bundle_flattens_nested_children_into_idempotent_upserts(tmp_path: Path) -> None:
    working = _prepared_schema(tmp_path)

    first = apply_ui_schema_change_bundle(
        working_root=working,
        result_root=tmp_path / "result",
        create_pages=[],
        upsert_elements=[
            {
                "page_id": "page.one",
                "parent_id": "page.one.main",
                "element": {
                    "id": "page.one.panel",
                    "type": "section",
                    "label": "Panel",
                    "children": [
                        {
                            "id": "page.one.panel.value",
                            "type": "text",
                            "label": "Value",
                        }
                    ],
                },
            }
        ],
        move_elements=[],
        ui_links=[],
        maximum_pages=4,
        maximum_top_level_elements=10,
        maximum_element_changes=20,
        maximum_moves=10,
        maximum_links=20,
    )
    second = apply_ui_schema_change_bundle(
        working_root=working,
        result_root=tmp_path / "result",
        create_pages=[],
        upsert_elements=[
            {
                "page_id": "page.one",
                "parent_id": "page.one.main",
                "element": {
                    "id": "page.one.panel",
                    "type": "section",
                    "label": "Updated panel",
                    "children": [
                        {
                            "id": "page.one.panel.value",
                            "type": "text",
                            "label": "Updated value",
                        }
                    ],
                },
            }
        ],
        move_elements=[],
        ui_links=[],
        maximum_pages=4,
        maximum_top_level_elements=10,
        maximum_element_changes=20,
        maximum_moves=10,
        maximum_links=20,
    )

    assert first["element_change_count"] == 2
    assert second["element_change_count"] == 2
    page = read_json(working / "pages/page.one.json", {})
    panel = page["elements"][0]["children"][0]
    assert panel["label"] == "Updated panel"
    assert panel["children"][0]["label"] == "Updated value"

def test_change_bundles_preserve_links_from_previous_batches(tmp_path: Path) -> None:
    working = _prepared_schema(tmp_path)
    page = read_json(working / "pages/page.one.json", {})
    page["elements"][0]["children"] = [
        {
            "id": "page.one.first",
            "type": "button",
            "label": "First",
        },
        {
            "id": "page.one.second",
            "type": "button",
            "label": "Second",
        },
    ]
    write_json(working / "pages/page.one.json", page)

    common = {
        "working_root": working,
        "result_root": tmp_path / "result",
        "create_pages": [],
        "update_pages": [],
        "upsert_elements": [],
        "move_elements": [],
        "maximum_pages": 4,
        "maximum_top_level_elements": 10,
        "maximum_element_changes": 20,
        "maximum_moves": 10,
        "maximum_links": 20,
    }
    apply_ui_schema_change_bundle(
        **common,
        ui_links=[
            {
                "id": "link.first",
                "source_id": "page.one.first",
                "target_id": "page.one",
                "relation": "navigates_to",
            }
        ],
    )
    apply_ui_schema_change_bundle(
        **common,
        ui_links=[
            {
                "source_id": "page.one.second",
                "target_id": "page.one",
                "relation": "navigates_to",
            }
        ],
    )

    links = read_json(working / "links.json", {})["links"]
    assert len(links) == 2
    assert links[0]["id"] == "link.first"
    assert links[1]["source_id"] == "page.one.second"
    assert links[1]["target_id"] == "page.one"

def test_change_bundle_reuses_existing_id_for_same_ui_link(tmp_path: Path) -> None:
    working = _prepared_schema(tmp_path)
    page = read_json(working / "pages/page.one.json", {})
    page["elements"][0]["children"] = [
        {
            "id": "page.one.action",
            "type": "button",
            "label": "Action",
        }
    ]
    write_json(working / "pages/page.one.json", page)
    write_json(
        working / "links.json",
        {
            "links": [
                {
                    "id": "stable.link",
                    "source_type": "ui_element",
                    "source_id": "page.one.action",
                    "target_type": "page",
                    "target_id": "page.one",
                    "relation": "navigates_to",
                }
            ]
        },
    )

    apply_ui_schema_change_bundle(
        working_root=working,
        result_root=tmp_path / "result",
        create_pages=[],
        update_pages=[],
        upsert_elements=[],
        move_elements=[],
        ui_links=[
            {
                "source_id": "page.one.action",
                "target_id": "page.one",
                "relation": "navigates_to",
            }
        ],
        maximum_pages=4,
        maximum_top_level_elements=10,
        maximum_element_changes=20,
        maximum_moves=10,
        maximum_links=20,
    )

    links = read_json(working / "links.json", {})["links"]
    assert len(links) == 1
    assert links[0]["id"] == "stable.link"

def test_change_bundle_updates_and_moves_existing_element_in_one_transaction(
    tmp_path: Path,
) -> None:
    working = _prepared_schema(tmp_path)
    page = read_json(working / "pages/page.one.json", {})
    page["elements"][0]["children"] = [
        {
            "id": "page.one.old_group",
            "type": "section",
            "label": "Old group",
            "children": [
                {
                    "id": "page.one.value",
                    "type": "text",
                    "label": "Before",
                }
            ],
        }
    ]
    write_json(working / "pages/page.one.json", page)

    response = apply_ui_schema_change_bundle(
        working_root=working,
        result_root=tmp_path / "result",
        create_pages=[],
        update_pages=[],
        upsert_elements=[
            {
                "page_id": "page.one",
                "parent_id": "page.one.main",
                "element": {
                    "id": "page.one.new_group",
                    "type": "section",
                    "label": "New group",
                },
            },
            {
                "page_id": "page.one",
                "parent_id": "page.one.new_group",
                "element": {
                    "id": "page.one.value",
                    "type": "text",
                    "label": "After",
                },
            },
        ],
        move_elements=[
            {
                "page_id": "page.one",
                "element_id": "page.one.value",
                "new_parent_id": "page.one.new_group",
            }
        ],
        ui_links=[],
        maximum_pages=4,
        maximum_top_level_elements=10,
        maximum_element_changes=20,
        maximum_moves=10,
        maximum_links=20,
    )

    assert response["element_change_count"] == 2
    assert response["move_count"] == 1
    page = read_json(working / "pages/page.one.json", {})
    main_children = page["elements"][0]["children"]
    old_group = next(item for item in main_children if item["id"] == "page.one.old_group")
    new_group = next(item for item in main_children if item["id"] == "page.one.new_group")
    assert old_group.get("children", []) == []
    assert new_group["children"][0]["id"] == "page.one.value"
    assert new_group["children"][0]["label"] == "After"


def test_change_bundle_rejects_conflicting_upsert_and_move_parents_transactionally(
    tmp_path: Path,
) -> None:
    working = _prepared_schema(tmp_path)
    page = read_json(working / "pages/page.one.json", {})
    page["elements"][0]["children"] = [
        {
            "id": "page.one.old_group",
            "type": "section",
            "label": "Old group",
            "children": [
                {
                    "id": "page.one.value",
                    "type": "text",
                    "label": "Before",
                }
            ],
        },
        {
            "id": "page.one.new_group",
            "type": "section",
            "label": "New group",
        },
        {
            "id": "page.one.other_group",
            "type": "section",
            "label": "Other group",
        },
    ]
    write_json(working / "pages/page.one.json", page)
    before = read_json(working / "pages/page.one.json", {})

    with pytest.raises(ValueError, match="противоречивые родители"):
        apply_ui_schema_change_bundle(
            working_root=working,
            result_root=tmp_path / "result",
            create_pages=[],
            update_pages=[],
            upsert_elements=[
                {
                    "page_id": "page.one",
                    "parent_id": "page.one.other_group",
                    "element": {
                        "id": "page.one.value",
                        "type": "text",
                        "label": "After",
                    },
                }
            ],
            move_elements=[
                {
                    "page_id": "page.one",
                    "element_id": "page.one.value",
                    "new_parent_id": "page.one.new_group",
                }
            ],
            ui_links=[],
            maximum_pages=4,
            maximum_top_level_elements=10,
            maximum_element_changes=20,
            maximum_moves=10,
            maximum_links=20,
        )

    assert read_json(working / "pages/page.one.json", {}) == before


def test_change_bundle_reports_all_implicit_moves_from_nested_upsert(
    tmp_path: Path,
) -> None:
    working = _prepared_schema(tmp_path)
    page = read_json(working / "pages/page.one.json", {})
    page["elements"][0]["children"] = [
        {
            "id": "page.one.old_group",
            "type": "section",
            "label": "Old group",
            "children": [
                {"id": "page.one.first", "type": "text", "label": "First"},
                {"id": "page.one.second", "type": "text", "label": "Second"},
            ],
        }
    ]
    write_json(working / "pages/page.one.json", page)
    before = read_json(working / "pages/page.one.json", {})

    with pytest.raises(ValueError) as captured:
        apply_ui_schema_change_bundle(
            working_root=working,
            result_root=tmp_path / "result",
            create_pages=[],
            update_pages=[],
            upsert_elements=[
                {
                    "page_id": "page.one",
                    "parent_id": "page.one.main",
                    "element": {
                        "id": "page.one.new_group",
                        "type": "section",
                        "label": "New group",
                        "children": [
                            {
                                "id": "page.one.first",
                                "type": "text",
                                "label": "First updated",
                            },
                            {
                                "id": "page.one.second",
                                "type": "text",
                                "label": "Second updated",
                            },
                        ],
                    },
                }
            ],
            move_elements=[],
            ui_links=[],
            maximum_pages=4,
            maximum_top_level_elements=10,
            maximum_element_changes=20,
            maximum_moves=10,
            maximum_links=20,
        )

    message = str(captured.value)
    assert message.startswith("Некорректные инструкции размещения элементов:")
    assert "page.one.first" in message
    assert "page.one.second" in message
    assert message.count("upsert_elements не может неявно перенести") == 2
    assert read_json(working / "pages/page.one.json", {}) == before
