from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

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

from backend.modules.ui_schema.agent_context import build_element_type_context
from backend.modules.ui_schema.agent_repair_hints import build_repair_hints
from backend.modules.ui_schema.agent_schema_io import write_ui_schema_bundle
from backend.modules.ui_schema.agent_tools import create_agent_tools
from backend.modules.ui_schema.files import read_json, write_json


def test_compact_element_catalog_separates_app_roots_from_page_types() -> None:
    catalog = build_element_type_context()

    assert catalog["app_root_type_ids"] == ["main_menu", "top_bar"]
    assert {item["id"] for item in catalog["app"]} >= {
        "main_menu",
        "menu_group",
        "menu_item",
        "top_bar",
        "app_text",
        "app_action",
    }
    assert "section" in {item["id"] for item in catalog["page"]}
    assert "icon" not in catalog["app"][0]
    assert "label" not in catalog["page"][0]


def test_core_write_rejects_page_type_in_app_before_persisting(tmp_path: Path) -> None:
    working_root = tmp_path / "working" / "ui_schema"
    result_root = tmp_path / "result"
    original = {
        "id": "app",
        "title": "Prototype",
        "root_elements": [
            {
                "id": "app.main_menu",
                "type": "main_menu",
                "label": "Меню",
                "children": [],
            }
        ],
    }
    write_json(working_root / "app.json", original)

    with pytest.raises(ValueError, match="Разрешённые корневые типы app.json: main_menu, top_bar"):
        write_ui_schema_bundle(
            working_root=working_root,
            result_root=result_root,
            files=[
                {
                    "file_path": "app.json",
                    "content": {
                        "id": "app",
                        "root_elements": [
                            {
                                "id": "app.top_bar",
                                "type": "section",
                                "label": "Верхняя панель",
                                "children": [],
                            }
                        ],
                    },
                }
            ],
            maximum_files=2,
        )

    assert read_json(working_root / "app.json", {}) == original


def test_core_write_accepts_top_bar_app_root(tmp_path: Path) -> None:
    working_root = tmp_path / "working" / "ui_schema"
    result_root = tmp_path / "result"
    write_json(
        working_root / "app.json",
        {"id": "app", "title": "Prototype", "root_elements": []},
    )

    result = write_ui_schema_bundle(
        working_root=working_root,
        result_root=result_root,
        files=[
            {
                "file_path": "app.json",
                "content": {
                    "id": "app",
                    "root_elements": [
                        {
                            "id": "app.top_bar",
                            "type": "top_bar",
                            "label": "Верхняя панель",
                            "children": [
                                {
                                    "id": "app.top_bar.user",
                                    "type": "app_text",
                                    "label": "Пользователь",
                                    "children": [],
                                },
                                {
                                    "id": "app.top_bar.logout",
                                    "type": "app_action",
                                    "label": "Выйти",
                                    "children": [],
                                }
                            ],
                        }
                    ],
                },
            }
        ],
        maximum_files=2,
    )

    assert result["ok"] is True
    assert read_json(working_root / "app.json", {})["root_elements"][0]["type"] == "top_bar"


def test_core_write_repairs_existing_invalid_app_root_type(tmp_path: Path) -> None:
    working_root = tmp_path / "working" / "ui_schema"
    result_root = tmp_path / "result"
    write_json(
        working_root / "app.json",
        {
            "id": "app",
            "title": "Prototype",
            "root_elements": [
                {
                    "id": "app.main_menu",
                    "type": "main_menu",
                    "label": "Меню",
                    "children": [],
                },
                {
                    "id": "app.top_bar",
                    "type": "section",
                    "label": "Верхняя панель",
                    "children": [],
                },
            ],
        },
    )

    write_ui_schema_bundle(
        working_root=working_root,
        result_root=result_root,
        files=[
            {
                "file_path": "app.json",
                "content": {
                    "id": "app",
                    "root_elements": [
                        {
                            "id": "app.top_bar",
                            "type": "top_bar",
                            "label": "Верхняя панель",
                            "children": [],
                        }
                    ],
                },
            }
        ],
        maximum_files=2,
    )

    roots = read_json(working_root / "app.json", {})["root_elements"]
    assert [item["id"] for item in roots] == ["app.top_bar", "app.main_menu"]
    assert roots[0]["type"] == "top_bar"


def test_validation_repair_hint_names_allowed_app_roots(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "base/ui_schema/app.json",
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
    write_json(
        run_path / "working/ui_schema/app.json",
        {
            "id": "app",
            "root_elements": [
                {
                    "id": "app.main_menu",
                    "type": "main_menu",
                    "label": "Меню",
                    "children": [],
                },
                {
                    "id": "app.top_bar",
                    "type": "section",
                    "label": "Верхняя панель",
                    "children": [],
                },
            ],
        },
    )
    write_json(run_path / "working/ui_schema/schema.json", {"pages": []})
    write_json(
        run_path / "working/ui_schema/mappings/requirement_ui_links.json",
        {"links": []},
    )
    write_json(run_path / "input/requirements.json", {"requirements": []})

    hints = build_repair_hints(run_path)

    assert hints[0]["kind"] == "invalid_app_root_type"
    assert hints[0]["element_id"] == "app.top_bar"
    assert hints[0]["allowed_app_root_types"] == ["main_menu", "top_bar"]
    assert hints[0]["new_in_current_run"] is True
    assert hints[0]["alternative_tool"] == "delete_ui_schema_elements"


def test_context_tool_returns_full_payload_only_once(tmp_path: Path, monkeypatch) -> None:
    class FakeTool:
        def __init__(self, function):
            self.function = function
            self.name = function.__name__

        def invoke(self, arguments):
            return self.function(**arguments)

    def fake_tool(function=None, **_kwargs):
        def decorate(candidate):
            return FakeTool(candidate)

        return decorate(function) if function is not None else decorate

    langchain_module = types.ModuleType("langchain")
    tools_module = types.ModuleType("langchain.tools")
    tools_module.tool = fake_tool
    monkeypatch.setitem(sys.modules, "langchain", langchain_module)
    monkeypatch.setitem(sys.modules, "langchain.tools", tools_module)

    run_path = tmp_path / "run"
    write_json(run_path / "input/task.json", {"operation": "synchronize"})
    write_json(run_path / "input/requirements.json", {"requirements": []})
    write_json(run_path / "working/ui_schema/app.json", {"id": "app", "root_elements": []})
    write_json(run_path / "working/ui_schema/schema.json", {"pages": []})
    write_json(run_path / "working/ui_schema/links.json", {"links": []})
    write_json(
        run_path / "working/ui_schema/mappings/requirement_ui_links.json",
        {"links": []},
    )
    agent_config = yaml.safe_load(
        (PROJECT_ROOT / "modules/ui_schema/config.yaml").read_text(encoding="utf-8")
    )["agent"]
    tools = create_agent_tools(run_path=run_path, agent_config=agent_config)
    load_tool = next(tool for tool in tools if tool.name == "load_synchronization_context")

    first = json.loads(load_tool.invoke({}))
    second_raw = load_tool.invoke({})
    second = json.loads(second_raw)

    assert "ui_schema" in first
    assert second["ok"] is False
    assert second["code"] == "context_already_loaded"
    assert len(second_raw) < 400
