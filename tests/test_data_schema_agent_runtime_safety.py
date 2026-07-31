from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from backend.modules.data_schema.agent_schema_patch import (
    patch_dictionaries,
    patch_relations,
    patch_schema_core,
)
from backend.modules.data_schema.agent_schema_patch_models import CorePatchArgs
from backend.modules.data_schema.files import read_json, write_json


def test_json_writes_remain_readable_during_parallel_updates(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    write_json(path, {"value": 0})
    errors: list[Exception] = []

    def writer(offset: int) -> None:
        try:
            for index in range(60):
                write_json(path, {"value": offset + index, "payload": "x" * 500})
        except Exception as exc:  # pragma: no cover - collected for assertion
            errors.append(exc)

    def reader() -> None:
        try:
            for _ in range(240):
                value = read_json(path, {})
                assert isinstance(value, dict)
        except Exception as exc:  # pragma: no cover - collected for assertion
            errors.append(exc)

    threads = [
        threading.Thread(target=writer, args=(0,)),
        threading.Thread(target=writer, args=(1000,)),
        threading.Thread(target=reader),
        threading.Thread(target=reader),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert isinstance(read_json(path, {}), dict)
    assert not list(tmp_path.glob(".metrics.json.*.tmp"))


def test_read_json_retries_a_temporarily_incomplete_file(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    path.write_text("", encoding="utf-8")

    def complete_file() -> None:
        time.sleep(0.005)
        path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    thread = threading.Thread(target=complete_file)
    thread.start()
    assert read_json(path, {}) == {"ok": True}
    thread.join()


def test_direct_workflow_limits_come_from_module_config() -> None:
    import yaml

    config_path = Path(__file__).resolve().parents[1] / "modules/data_schema/config.yaml"
    agent = yaml.safe_load(config_path.read_text(encoding="utf-8"))["agent"]

    assert agent["validation_retries"] == 1
    assert agent["execution"]["max_llm_calls"] == 18
    assert agent["execution"]["max_total_tokens"] == 600000
    assert "generation" not in agent
    assert agent["semantic_review"]["max_correction_rounds"] == 3


def test_core_patch_updates_existing_fields_without_full_payload(tmp_path: Path) -> None:
    working = _working_schema(tmp_path)
    payload = CorePatchArgs.model_validate(
        {
            "entities": [
                {
                    "id": "record",
                    "fields": [
                        {
                            "id": "status",
                            "type": "dictionary",
                            "dictionary_id": "record_status",
                        }
                    ],
                }
            ]
        }
    )

    patch_schema_core(
        working_root=working,
        schema_patch=None,
        entities=[item.model_dump(exclude_unset=True) for item in payload.entities],
    )

    entity = read_json(working / "entities/record.json", {})
    assert entity["title"] == "Запись"
    assert entity["fields"][0] == {
        "id": "status",
        "title": "Статус",
        "type": "dictionary",
        "required": False,
        "description": "",
        "dictionary_id": "record_status",
    }


def test_dictionary_and_relation_patches_require_only_exact_existing_ids(tmp_path: Path) -> None:
    working = _working_schema(tmp_path)

    patch_dictionaries(
        working_root=working,
        dictionaries=[{"id": "record_status", "description": "Актуальные состояния"}],
    )
    patch_relations(
        working_root=working,
        relations=[{"id": "record_has_detail", "description": "Уточнённое описание"}],
    )

    dictionaries = read_json(working / "dictionaries.json", {})["dictionaries"]
    relations = read_json(working / "relations.json", {})["relations"]
    assert dictionaries[0]["title"] == "Статус записи"
    assert dictionaries[0]["description"] == "Актуальные состояния"
    assert relations[0]["title"] == "Запись содержит деталь"
    assert relations[0]["description"] == "Уточнённое описание"


def _working_schema(tmp_path: Path) -> Path:
    working = tmp_path / "data_schema"
    write_json(
        working / "schema.json",
        {
            "schema_version": "0.1",
            "title": "Схема",
            "entities": [
                {"id": "record", "title": "Запись", "file": "entities/record.json"},
                {"id": "detail", "title": "Деталь", "file": "entities/detail.json"},
            ],
        },
    )
    write_json(
        working / "entities/record.json",
        {
            "id": "record",
            "title": "Запись",
            "description": "",
            "fields": [
                {
                    "id": "status",
                    "title": "Статус",
                    "type": "string",
                    "required": False,
                    "description": "",
                }
            ],
        },
    )
    write_json(
        working / "entities/detail.json",
        {"id": "detail", "title": "Деталь", "description": "", "fields": []},
    )
    write_json(
        working / "dictionaries.json",
        {
            "dictionaries": [
                {
                    "id": "record_status",
                    "title": "Статус записи",
                    "description": "",
                    "values": [{"id": "active", "title": "Активна"}],
                }
            ]
        },
    )
    write_json(
        working / "relations.json",
        {
            "relations": [
                {
                    "id": "record_has_detail",
                    "title": "Запись содержит деталь",
                    "source_entity": "record",
                    "target_entity": "detail",
                    "cardinality": "one_to_many",
                    "description": "",
                }
            ]
        },
    )
    write_json(working / "mappings/requirement_data_links.json", {"links": []})
    write_json(working / "mappings/ui_data_links.json", {"links": []})
    write_json(working / "mappings/api_data_links.json", {"links": []})
    write_json(working / "code_links.json", {"links": []})
    write_json(working / "requirements_source.json", {})
    return working
