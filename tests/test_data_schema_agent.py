from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.data_schema.agent_completion import validate_agent_working_schema
from backend.modules.data_schema.agent_assessments import validate_requirement_assessments
from backend.modules.data_schema.agent_diagnostics import (
    ensure_diagnostics_archive,
    stored_diagnostics_archive_path,
)
from backend.modules.data_schema.agent_paths import completed_run_file, run_root, runtime_root
from backend.modules.data_schema.agent_requirements import (
    RequirementsSourceError,
    load_requirements_from_workspace,
)
from backend.modules.data_schema.agent_preview import finalize_preview
from backend.modules.data_schema.agent_exports import build_requirements_data_result
from backend.modules.data_schema.agent_report import (
    build_factual_summary,
    ensure_agent_report,
    finalize_agent_report,
)
from backend.modules.data_schema.agent_execution import (
    record_limit_stop,
    validation_correction_thread_id,
)
from backend.modules.data_schema.agent_monitor import AgentRunStopped, _reported_model
from backend.modules.data_schema.agent_llm import LlmConfigurationError, _reasoning_effort
from backend.modules.data_schema.agent_llm_retry import (
    invoke_with_transient_llm_retry,
    llm_http_status_code,
)
from backend.modules.data_schema.agent_manual_review import build_manual_review_result
from backend.modules.data_schema.agent_events import read_events
from backend.modules.data_schema.agent_semantic_context import build_semantic_review_context
from backend.modules.data_schema.agent_semantic_requirement_groups import (
    group_requirements_by_current_result,
)
from backend.modules.data_schema.agent_semantic_verification_context import (
    build_semantic_verification_context,
)
from backend.modules.data_schema.agent_review_correction_context import (
    build_review_correction_context,
)
from backend.modules.data_schema.agent_addition_removal import remove_run_additions
from backend.modules.data_schema.agent_traceability_patch import (
    patch_requirement_assessments,
    patch_requirement_links,
    patch_requirement_results,
    write_complete_requirement_results,
)
from backend.modules.data_schema.agent_semantic_invocation import normalize_semantic_review
from backend.modules.data_schema.agent_semantic_models import SemanticReviewPayload
from backend.modules.data_schema.agent_semantic_review import _combine_reviews
from backend.modules.data_schema.agent_semantic_correction_apply import (
    apply_semantic_correction_plan,
)
from backend.modules.data_schema.agent_semantic_correction_models import (
    SemanticCorrectionPlanPayload,
)
from backend.modules.data_schema.agent_runtime_layout import ensure_runtime_layout
from backend.modules.data_schema.agent_runs import (
    apply_run,
    create_run,
    reject_run,
    reset_for_regeneration,
    update_run,
    get_run,
)
from backend.modules.data_schema.agent_schema_patch import (
    patch_dictionaries,
    patch_schema_core,
)
from backend.modules.data_schema.agent_schema_patch_models import CorePatchArgs
from backend.modules.data_schema.agent_schema_io import (
    write_dictionaries,
    write_relations,
    write_requirement_links,
    write_schema_core,
)
from backend.modules.data_schema.agent_target_references import materialize_requirement_link
from backend.modules.data_schema.agent_snapshots import latest_snapshot
from backend.modules.data_schema.agent_tool_observability import (
    tool_argument_shape,
    tool_file_count,
    tool_path,
)
from backend.modules.data_schema.agent_tools import (
    CoreWriteArgs,
    DictionariesWriteArgs,
    RelationsWriteArgs,
    RequirementResultsPatchArgs,
)
from backend.modules.data_schema.agent_tool_models import (
    AgentReportPayload,
    RequirementLinksWriteArgs,
)
from backend.modules.data_schema.files import read_json, write_json
from backend.modules.data_schema.requirements_source import (
    file_sha256,
    resolve_requirements,
)

AGENT_CONFIG = yaml.safe_load(
    (PROJECT_ROOT / "modules/data_schema/config.yaml").read_text(encoding="utf-8")
)["agent"]

SEMANTIC_REVIEW_TEST_CONFIG = {
    "enabled": True,
    "max_correction_rounds": 1,
    "response_attempts": 2,
    "max_issues": 24,
    "max_context_bytes": 1048576,
}



def test_transient_llm_retry_retries_configured_server_error_once(monkeypatch) -> None:
    calls = 0

    class ServerError(RuntimeError):
        status_code = 500

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ServerError("temporary")
        return "ok"

    monkeypatch.setattr(
        "backend.modules.data_schema.agent_llm_retry.time.sleep",
        lambda _: None,
    )
    config = {
        "llm": {
            "transient_retry": {
                "max_retries": 1,
                "delay_seconds": 2,
                "status_codes": [500, 502, 503, 504],
            }
        }
    }

    assert invoke_with_transient_llm_retry(operation, agent_config=config) == "ok"
    assert calls == 2


def test_transient_llm_retry_does_not_retry_timeout_or_client_error() -> None:
    config = {
        "llm": {
            "transient_retry": {
                "max_retries": 1,
                "delay_seconds": 0,
                "status_codes": [500, 502, 503, 504],
            }
        }
    }

    class ClientError(RuntimeError):
        status_code = 400

    for error in (TimeoutError("slow"), ClientError("bad request")):
        calls = 0

        def operation() -> None:
            nonlocal calls
            calls += 1
            raise error

        with pytest.raises(type(error)):
            invoke_with_transient_llm_retry(operation, agent_config=config)
        assert calls == 1


def test_llm_http_status_code_reads_provider_response() -> None:
    class Response:
        status_code = 503

    class ProviderError(RuntimeError):
        response = Response()

    assert llm_http_status_code(ProviderError("temporary")) == 503

def test_reasoning_effort_is_provider_profile_and_model_specific() -> None:
    config = {
        "reasoning_effort": {
            "ollama-cloud": {
                "generation": "none",
                "review": "low",
            }
        },
        "reasoning_effort_by_model": {
            "ollama-cloud": {
                "primary-model": {"generation": "low"},
            }
        },
    }

    assert (
        _reasoning_effort(
            config,
            provider="ollama-cloud",
            model="other-model",
            profile="generation",
        )
        == "none"
    )
    assert (
        _reasoning_effort(
            config,
            provider="ollama-cloud",
            model="primary-model",
            profile="generation",
        )
        == "low"
    )
    assert (
        _reasoning_effort(
            config,
            provider="ollama-cloud",
            model="primary-model",
            profile="review",
        )
        == "low"
    )
    assert (
        _reasoning_effort(
            config,
            provider="openai",
            model="primary-model",
            profile="generation",
        )
        is None
    )


def test_reasoning_effort_rejects_unknown_level() -> None:
    with pytest.raises(LlmConfigurationError):
        _reasoning_effort(
            {"reasoning_effort": {"ollama-cloud": {"generation": "extreme"}}},
            provider="ollama-cloud",
            profile="generation",
        )


def test_data_schema_agent_frontend_module_imports() -> None:
    modules = [
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-observability-render.js",
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-changes-render.js",
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-render.js",
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-semantic-review-render.js",
        PROJECT_ROOT / "frontend/modules/data_schema/js/preview-change-markers.js",
        PROJECT_ROOT / "frontend/modules/data_schema/js/preview-change-graph.js",
    ]
    script = ";".join(f"import({path.resolve().as_uri()!r})" for path in modules)
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr



def test_completed_run_duration_is_frozen_at_last_event() -> None:
    module_uri = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-observability-render.js"
    ).resolve().as_uri()
    script = f"""
      import {{ renderRunObservability }} from {module_uri!r};
      const html = renderRunObservability(
        {{ started_at: '2026-07-31T07:19:45.036Z', updated_at: '2026-07-31T07:30:19.705Z' }},
        {{
          last_event_at: '2026-07-31T07:30:19.704Z',
          token_usage_available: true,
          limits: {{ max_duration_seconds: 1200 }}
        }},
        [],
        false
      );
      console.log(html);
    """
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "10 мин 34 сек / 20 мин 0 сек" in result.stdout


def test_agent_preview_uses_detailed_requirement_warnings_and_hides_validation_payloads() -> None:
    controller = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-controller.js"
    ).read_text(encoding="utf-8")
    renderer = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-render.js"
    ).read_text(encoding="utf-8")

    assert "loadAgentRequirementsResult" in controller
    assert "collectWarnings(run.validation_warnings, requirementsResult)" in renderer
    assert "function humanAgentNote" in renderer
    assert "assessment_counts" in renderer


def test_execution_log_is_open_only_while_run_is_active() -> None:
    source = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-observability-render.js"
    ).read_text(encoding="utf-8")

    assert "<details class=\"agent-event-log\" ${running ? 'open' : ''}>" in source
    assert '<details class="agent-event-log" open>' not in source

def test_change_list_and_categories_are_collapsed_by_default() -> None:
    source = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-render.js"
    ).read_text(encoding="utf-8")

    assert '<details class="agent-changes-root" open>' not in source
    assert '<details class="agent-change-group" open>' not in source




def test_result_summary_does_not_duplicate_change_statistics() -> None:
    summary = build_factual_summary(
        {
            "statistics": {
                "entities": {"added": 2, "modified": 1, "deleted": 0},
                "fields": {"added": 5, "modified": 3, "deleted": 1},
            }
        },
        {
            "assessment_counts": {
                "linked": 7,
                "cross_cutting_data": 1,
                "no_data": 2,
                "unclear": 0,
            }
        },
    )

    assert summary.startswith("Синхронизация схемы данных завершена. Требования:")
    assert "7 с прямой трассировкой" in summary
    assert "Сущности:" not in summary
    assert "поля:" not in summary


def test_change_rendering_shows_property_before_and_after_values() -> None:
    source = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-changes-render.js"
    ).read_text(encoding="utf-8")

    assert "Изменено свойств" in source
    assert "property.before" in source
    assert "property.after" in source
    assert "agent-change-before" in source
    assert "agent-change-after" in source


def test_execution_and_change_statistics_use_compact_ui_classes() -> None:
    render_source = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-render.js"
    ).read_text(encoding="utf-8")
    changes_source = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-changes-render.js"
    ).read_text(encoding="utf-8")
    css_source = (
        PROJECT_ROOT / "frontend/modules/data_schema/css/module.css"
    ).read_text(encoding="utf-8")

    observability_index = render_source.index("renderRunObservability(run, metrics, events, false)")
    changes_index = render_source.index("renderCompactChangeStatistics(statistics)")
    assert observability_index < changes_index
    assert render_source.count("renderCompactChangeStatistics(statistics)") == 1
    assert "agent-change-stats" in changes_source
    assert ".agent-resource-card strong" in css_source
    assert "font-size: inherit" in css_source
    assert "Готово с предупреждениями" in render_source

def test_valid_preview_is_applyable_and_keeps_manual_regeneration() -> None:
    source = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-render.js"
    ).read_text(encoding="utf-8")

    assert "Готово к применению" in source
    assert "Принять все изменения" in source
    assert "Требует исправления" in source
    assert "renderSemanticReview" in source
    assert "renderManualReview(run.manual_review)" in source
    manual_source = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-manual-review-render.js"
    ).read_text(encoding="utf-8")
    assert "не влияет на статус применения" in manual_source
    assert "Кандидаты на очистку схемы" in manual_source
    assert "querySelectorAll('[data-regenerate-agent-run]')" in (
        PROJECT_ROOT / "frontend/modules/data_schema/js/agent-controller.js"
    ).read_text(encoding="utf-8")


def test_preview_change_markers_are_used_in_map_and_graph() -> None:
    map_source = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/render-map.js"
    ).read_text(encoding="utf-8")
    graph_source = (
        PROJECT_ROOT / "frontend/modules/data_schema/js/graph-joint.js"
    ).read_text(encoding="utf-8")

    assert "entityPreviewChange" in map_source
    assert "fieldPreviewChange" in map_source
    assert "relationPreviewChange" in map_source
    assert "entityPreviewChange" in graph_source
    assert "fieldPreviewChange" in graph_source
    assert "relationPreviewChange" in graph_source


def test_semantic_review_uses_one_structured_correction_round() -> None:
    settings = SEMANTIC_REVIEW_TEST_CONFIG

    assert settings["max_correction_rounds"] == 1
    assert "correction_max_repeated_tool_calls" not in settings

def test_data_schema_stylesheet_has_balanced_blocks() -> None:
    source = (
        PROJECT_ROOT / "frontend/modules/data_schema/css/module.css"
    ).read_text(encoding="utf-8")

    assert source.count("{") == source.count("}")


def test_agent_tool_arguments_accept_provider_serialized_nested_json() -> None:
    core = CoreWriteArgs.model_validate(
        {
            "schema_document": "```json\n{\"description\":\"Логическая схема\"}\n```",
            "entities": [
                {
                    "title": "Клиент",
                    "fields": "[{\"title\":\"Идентификатор\",\"type\":\"uuid\"}]",
                }
            ],
        }
    )
    dictionaries = DictionariesWriteArgs.model_validate(
        {
            "dictionaries": (
                "[{\"title\":\"Статус\","
                "\"values\":\"[{\\\"title\\\":\\\"Активен\\\"}]\"}]"
            )
        }
    )
    relations = RelationsWriteArgs.model_validate(
        {
            "relations": (
                "{\"relations\":[{\"title\":\"Владелец\","
                "\"source_entity\":\"account\","
                "\"target_entity\":\"customer\"}]}"
            )
        }
    )
    links = RequirementLinksWriteArgs.model_validate(
        {
            "links": json.dumps(
                [
                    {
                        "requirement_id": "REQ-0001",
                        "target": json.dumps(
                            {
                                "target_type": "entity",
                                "entity_id": "customer",
                            }
                        ),
                    }
                ]
            )
        }
    )
    report = AgentReportPayload.model_validate(
        {
            "cross_cutting_data": (
                "[{\"requirement_id\":\"REQ-0002\","
                "\"reason\":\"Сквозное правило\"}]"
            ),
            "no_data": "[]",
            "unclear": "[]",
            "warnings": "[\"Проверить терминологию\"]",
        }
    )

    blank_core = CoreWriteArgs.model_validate(
        {"schema_document": "", "entities": []}
    )
    wrapped_blank_core = CoreWriteArgs.model_validate(
        {"schema_document": {"schema_document": ""}, "entities": []}
    )

    assert core.schema_document is not None
    assert blank_core.schema_document is None
    assert wrapped_blank_core.schema_document is None
    assert core.schema_document.description == "Логическая схема"
    assert core.entities[0].fields[0].type == "uuid"
    assert dictionaries.dictionaries[0].values[0].title == "Активен"
    assert relations.relations[0].source_entity == "account"
    assert links.links[0].requirement_id == "REQ-0001"
    assert links.links[0].target_type == "entity"
    assert links.links[0].target_id == "customer"
    assert report.cross_cutting_data[0].requirement_id == "REQ-0002"
    assert report.warnings == ["Проверить терминологию"]





def test_manual_review_separates_inherited_links_and_cleanup_candidates(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    base_root = run_path / "base" / "data_schema" / "mappings"
    working_root = run_path / "working" / "data_schema" / "mappings"
    input_root = run_path / "input"
    base_root.mkdir(parents=True)
    working_root.mkdir(parents=True)
    input_root.mkdir(parents=True)
    write_json(
        input_root / "requirements.json",
        {"requirements": [{"id": "REQ-CURRENT", "name": "Актуальное"}]},
    )
    links = {
        "links": [
            {
                "requirement_id": "REQ-CURRENT",
                "target_type": "entity",
                "target_id": "current_entity",
                "relation": "defines",
            },
            {
                "requirement_id": "REQ-OLD",
                "target_type": "field",
                "target_id": "legacy.legacy_field",
                "relation": "defines",
            },
        ]
    }
    write_json(base_root / "requirement_data_links.json", links)
    write_json(working_root / "requirement_data_links.json", links)

    result = build_manual_review_result(
        run_path,
        {
            "cleanup_candidates": [
                {
                    "id": "consistency_1_cleanup_1",
                    "category": "obsolete_structure",
                    "message": "Объект может быть устаревшим.",
                    "recommendation": "Проверить необходимость вручную.",
                    "requirement_ids": [],
                    "targets": ["field:legacy.legacy_field"],
                }
            ]
        },
    )

    assert result["counts"] == {
        "inherited_requirement_ids": 1,
        "inherited_requirement_links": 1,
        "cleanup_candidates": 1,
    }
    assert result["inherited_requirement_links"] == [
        {
            "requirement_id": "REQ-OLD",
            "links": [
                {
                    "target_type": "field",
                    "target_id": "legacy.legacy_field",
                    "relation": "defines",
                }
            ],
        }
    ]
    assert result["cleanup_candidates"][0]["targets"] == [
        "field:legacy.legacy_field"
    ]


def test_cleanup_candidates_are_consistency_only_and_do_not_block() -> None:
    payload = SemanticReviewPayload.model_validate(
        {
            "decision": "approve",
            "coverage_complete": True,
            "summary": "Схема применима.",
            "cleanup_candidates": [
                {
                    "category": "obsolete_structure",
                    "message": "Поле выглядит заменённым.",
                    "recommendation": "Проверить и при необходимости удалить вручную.",
                    "targets": ["field:item.legacy_value"],
                }
            ],
        }
    )

    review = normalize_semantic_review(
        payload,
        SEMANTIC_REVIEW_TEST_CONFIG,
        review_id="consistency_1",
        review_kind="consistency",
        expected_issue_ids=[],
    )

    assert review["blocking"] is False
    assert review["issue_counts"] == {"must_fix": 0, "advisory": 0}
    assert review["cleanup_candidates"][0]["id"] == "consistency_1_cleanup_1"

    with pytest.raises(ValueError, match="allowed only in consistency review"):
        normalize_semantic_review(
            payload,
            SEMANTIC_REVIEW_TEST_CONFIG,
            review_id="coverage_1",
            review_kind="coverage",
            expected_issue_ids=[],
        )

def test_semantic_review_issue_requires_concrete_recommendation() -> None:
    with pytest.raises(ValidationError, match="recommendation"):
        SemanticReviewPayload.model_validate(
            {
                "decision": "approve",
                "coverage_complete": True,
                "summary": "Есть замечание",
                "issues": [
                    {
                        "disposition": "advisory",
                        "category": "consistency",
                        "message": "Найден небольшой дефект",
                    }
                ],
            }
        )


def test_combined_review_preserves_focused_issues_and_blocks_only_must_fix() -> None:
    coverage = {
        "review_id": "coverage_1",
        "review_kind": "coverage",
        "decision": "approve",
        "coverage_complete": True,
        "summary": "Покрытие проверено.",
        "review_note": "",
        "strengths": ["Требования классифицированы"],
        "issues": [
            {
                "id": "coverage_1_issue_1",
                "disposition": "advisory",
                "category": "traceability",
                "message": "Небольшой дефект ссылки",
                "recommendation": "Исправить ссылку",
                "requirement_ids": ["REQ-1"],
                "targets": ["entity:item"],
            }
        ],
    }
    consistency = {
        "review_id": "consistency_1",
        "review_kind": "consistency",
        "decision": "revise",
        "coverage_complete": True,
        "summary": "Согласованность проверена.",
        "review_note": "",
        "strengths": [],
        "cleanup_candidates": [
            {
                "id": "consistency_1_cleanup_1",
                "category": "obsolete_structure",
                "message": "Поле может быть устаревшим",
                "recommendation": "Проверить вручную",
                "requirement_ids": [],
                "targets": ["field:item.legacy"],
            }
        ],
        "issues": [
            {
                "id": "consistency_1_issue_1",
                "disposition": "must_fix",
                "category": "relation",
                "message": "Отсутствует значимая связь",
                "recommendation": "Добавить отношение",
                "requirement_ids": ["REQ-2"],
                "targets": ["field:item.owner_id"],
            }
        ],
    }

    combined = _combine_reviews(coverage, consistency)

    assert combined["review_kind"] == "combined"
    assert combined["blocking"] is True
    assert combined["issue_counts"] == {"must_fix": 1, "advisory": 1}
    assert [item["id"] for item in combined["issues"]] == [
        "coverage_1_issue_1",
        "consistency_1_issue_1",
    ]
    assert combined["coverage_complete"] is True
    assert combined["cleanup_candidates"][0]["id"] == "consistency_1_cleanup_1"

def test_semantic_review_accepts_serialized_nested_json_and_blocks_on_model_decision() -> None:
    payload = SemanticReviewPayload.model_validate(
        {
            "decision": "revise",
            "coverage_complete": True,
            "summary": "Требуется исправление",
            "issues": json.dumps(
                [
                    {
                        "disposition": "must_fix",
                        "category": "traceability",
                        "message": "Связь не обоснована",
                        "recommendation": "Удалить нерелевантную связь",
                        "requirement_ids": json.dumps(["REQ-1"]),
                        "targets": json.dumps(["entity:item"]),
                    }
                ],
                ensure_ascii=False,
            ),
            "strengths": '["Сохранены существующие ID"]',
        }
    )

    review = normalize_semantic_review(
        payload,
        SEMANTIC_REVIEW_TEST_CONFIG,
        review_id="coverage_1",
        review_kind="coverage",
        expected_issue_ids=[],
    )

    assert review["blocking"] is True
    assert review["decision"] == "revise"
    assert review["status"] == "needs_revision"
    assert review["issue_counts"]["must_fix"] == 1
    assert review["issues"][0]["requirement_ids"] == ["REQ-1"]
    assert review["issues"][0]["targets"] == ["entity:item"]


def test_semantic_review_approves_advisory_issues_and_normalizes_optional_arrays() -> None:
    payload = SemanticReviewPayload.model_validate(
        {
            "decision": "approve",
            "coverage_complete": True,
            "summary": "Результат можно применить",
            "issues": [
                {
                    "disposition": "advisory",
                    "category": "uncertainty",
                    "message": "Есть конкретный небольшой дефект",
                    "recommendation": "Исправить затронутую ссылку",
                    "requirement_ids": None,
                    "targets": None,
                }
            ],
            "strengths": None,
        }
    )

    review = normalize_semantic_review(
        payload,
        SEMANTIC_REVIEW_TEST_CONFIG,
        review_id="coverage_1",
        review_kind="coverage",
        expected_issue_ids=[],
    )

    assert review["blocking"] is False
    assert review["decision"] == "approve"
    assert review["issues"][0]["disposition"] == "advisory"
    assert review["issues"][0]["requirement_ids"] == []
    assert review["strengths"] == []


def test_semantic_review_rejects_inconsistent_decision_and_issues() -> None:
    payload = SemanticReviewPayload.model_validate(
        {
            "decision": "approve",
            "coverage_complete": True,
            "summary": "Ошибочно одобрено",
            "issues": [
                {
                    "disposition": "must_fix",
                    "category": "traceability",
                    "message": "Требуется изменение",
                    "recommendation": "Исправить затронутый объект",
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="approve conflicts with must_fix"):
        normalize_semantic_review(
            payload,
            SEMANTIC_REVIEW_TEST_CONFIG,
            review_id="coverage_1",
            review_kind="coverage",
            expected_issue_ids=[],
        )



def test_full_review_cannot_approve_incomplete_scope() -> None:
    payload = SemanticReviewPayload.model_validate(
        {
            "decision": "approve",
            "coverage_complete": False,
            "summary": "Не всё проверено",
            "issues": [],
        }
    )

    with pytest.raises(ValueError, match="coverage_complete is false"):
        normalize_semantic_review(
            payload,
            SEMANTIC_REVIEW_TEST_CONFIG,
            review_id="coverage_1",
            review_kind="coverage",
            expected_issue_ids=[],
        )


def test_correction_verification_requires_every_source_issue_id() -> None:
    payload = SemanticReviewPayload.model_validate(
        {
            "decision": "approve",
            "coverage_complete": True,
            "verified_issue_ids": ["semantic_issue_1"],
            "summary": "Исправления проверены",
            "issues": [],
        }
    )

    with pytest.raises(ValueError, match="cover every expected issue"):
        normalize_semantic_review(
            payload,
            SEMANTIC_REVIEW_TEST_CONFIG,
            review_id="verification_1",
            review_kind="correction_verification",
            expected_issue_ids=["semantic_issue_1", "semantic_issue_2"],
        )

    complete = payload.model_copy(
        update={"verified_issue_ids": ["semantic_issue_1", "semantic_issue_2"]}
    )
    review = normalize_semantic_review(
        complete,
        SEMANTIC_REVIEW_TEST_CONFIG,
        review_id="verification_1",
        review_kind="correction_verification",
        expected_issue_ids=["semantic_issue_1", "semantic_issue_2"],
    )
    assert review["status"] == "approved"
    assert review["review_kind"] == "correction_verification"


def test_coverage_requirements_are_grouped_by_stored_current_result() -> None:
    document = {
        "projects": [],
        "groups": [],
        "requirements": [
            {"id": "REQ-NO-DATA", "name": "Первое"},
            {"id": "REQ-CROSS", "name": "Второе"},
            {"id": "REQ-DIRECT", "name": "Третье"},
        ],
    }
    report = {
        "no_data": [{"requirement_id": "REQ-NO-DATA", "reason": ""}],
        "cross_cutting_data": [
            {"requirement_id": "REQ-CROSS", "reason": ""}
        ],
        "unclear": [],
    }

    grouped = group_requirements_by_current_result(document, report)

    assert grouped["current_result_review_order"] == [
        "no_data",
        "cross_cutting_data",
        "unclear",
        "direct",
    ]
    assert [item["id"] for item in grouped["by_current_result"]["no_data"]] == [
        "REQ-NO-DATA"
    ]
    assert [
        item["id"] for item in grouped["by_current_result"]["cross_cutting_data"]
    ] == ["REQ-CROSS"]
    assert [item["id"] for item in grouped["by_current_result"]["direct"]] == [
        "REQ-DIRECT"
    ]


def test_semantic_review_context_is_focused_by_scope(tmp_path: Path) -> None:
    _, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-REVIEW")

    coverage = build_semantic_review_context(
        run_path, review_scope="coverage", review_number=2
    )
    consistency = build_semantic_review_context(
        run_path, review_scope="consistency", review_number=2
    )

    assert coverage["review_scope"] == "coverage"
    assert coverage["review_number"] == 2
    assert coverage["requirements"]["by_current_result"]["direct"][0]["id"] == "REQ-REVIEW"
    assert coverage["requirements"]["current_result_review_order"][0] == "no_data"
    assert coverage["candidate_data_schema"]["entities"]
    assert "requirement_data_links" in coverage["candidate_data_schema"]
    assert "requirement_assessments" in coverage
    assert "requirement_data_links" not in consistency["candidate_data_schema"]
    assert "requirement_assessments" not in consistency
    assert (run_path / "input/semantic_review_context_coverage_2.json").is_file()
    assert (run_path / "input/semantic_review_context_consistency_2.json").is_file()
    reject_run(module_root, run_id)


def test_semantic_verification_context_contains_all_source_issues(tmp_path: Path) -> None:
    _, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-VERIFY")
    source_review = {
        "review_id": "combined_1",
        "summary": "Нужно исправить",
        "issues": [
            {
                "id": "coverage_1_issue_1",
                "disposition": "must_fix",
                "category": "traceability",
                "message": "Ошибка",
                "recommendation": "Исправить связь",
                "requirement_ids": ["REQ-VERIFY"],
                "targets": [],
            },
            {
                "id": "consistency_1_issue_1",
                "disposition": "advisory",
                "category": "optional",
                "message": "Небольшой дефект",
                "recommendation": "Исправить поле",
                "requirement_ids": ["REQ-VERIFY"],
                "targets": [],
            },
        ],
    }

    context = build_semantic_verification_context(
        run_path, source_review, verification_number=1
    )

    assert context["review_scope"] == "correction_verification"
    assert context["expected_issue_ids"] == [
        "coverage_1_issue_1",
        "consistency_1_issue_1",
    ]
    assert len(context["source_review"]["issues"]) == 2
    assert context["current_relevant_state"]["requirements"]["requirements"][0]["id"] == "REQ-VERIFY"
    reject_run(module_root, run_id)


def test_limit_stop_can_finalize_valid_direct_workflow_preview(tmp_path: Path) -> None:
    _, module_root, run_id, _ = _preview_ready_run(tmp_path, "REQ-LIMIT-DIRECT")
    update_run(
        module_root,
        run_id,
        status="running",
        phase="validating",
    )

    record_limit_stop(module_root, run_id, AgentRunStopped("test limit"))

    run = get_run(module_root, run_id)
    assert run["status"] == "preview_ready"
    assert run["phase"] == "completed"

def test_limit_stop_does_not_publish_unreviewed_schema(tmp_path: Path) -> None:
    _, module_root, run_id, _ = _preview_ready_run(tmp_path, "REQ-LIMIT-NO-REVIEW")
    update_run(
        module_root,
        run_id,
        status="running",
        phase="semantic_review",
        semantic_review={},
        apply_blocked=True,
    )

    record_limit_stop(module_root, run_id, AgentRunStopped("test limit"))

    run = get_run(module_root, run_id)
    assert run["status"] == "failed"
    assert run["phase"] == "stopped_by_limit"


def test_apply_rejects_preview_with_unresolved_must_fix(tmp_path: Path) -> None:
    _, module_root, run_id, _ = _preview_ready_run(tmp_path, "REQ-BLOCKED-APPLY")
    update_run(
        module_root,
        run_id,
        semantic_review={
            "status": "needs_revision",
            "decision": "revise",
            "blocking": True,
            "review_id": "verification_1",
            "review_kind": "correction_verification",
            "coverage_complete": True,
        },
        apply_blocked=True,
    )

    with pytest.raises(ValueError, match="смысловую проверку"):
        apply_run(
            module_root,
            run_id,
            keep_last=3,
            requirements_max_bytes=AGENT_CONFIG["requirements"]["max_bytes"],
        )


def test_apply_uses_technical_preview_validation(tmp_path: Path) -> None:
    _, module_root, run_id, _ = _preview_ready_run(tmp_path, "REQ-DIRECT-APPLY")

    result = apply_run(
        module_root,
        run_id,
        keep_last=3,
        requirements_max_bytes=AGENT_CONFIG["requirements"]["max_bytes"],
    )

    assert result["status"] == "applied"

def test_tool_observability_reports_stringified_argument_shape_without_content() -> None:
    args = {
        "schema_document": '{"description":"sensitive description"}',
        "entities": '[{"title":"Клиент"}]',
    }

    shape = tool_argument_shape(args)

    assert shape["schema_document"].startswith("json-string<object>")
    assert shape["entities"].startswith("json-string<array>")
    assert "sensitive description" not in str(shape)
    assert tool_path(args) == "entities: 1"
    assert tool_file_count(args) == 2




def test_review_correction_context_is_scoped_and_lists_safe_removals(tmp_path: Path) -> None:
    workspace, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-SCOPED")
    requirements_file = workspace / "requirements/requirements.json"
    requirements = read_json(requirements_file, {})
    requirements["requirements"].append({"id": "REQ-OTHER", "name": "Другое требование"})
    write_json(requirements_file, requirements)
    write_json(run_path / "input/requirements.json", requirements)
    working_root = run_path / "working/data_schema"
    write_schema_core(
        working_root=working_root,
        schema=None,
        entities=[
            {
                "id": "added_entity",
                "title": "Добавленная сущность",
                "fields": [{"id": "added_field", "title": "Добавленное поле"}],
            }
        ],
    )
    review = {
        "issues": [
            {
                "disposition": "must_fix",
                "requirement_ids": ["REQ-SCOPED"],
                "targets": ["field:added_entity.added_field"],
            }
        ]
    }

    context = build_review_correction_context(
        run_path, review, correction_round=1
    )

    ids = [item["id"] for item in context["requirements"]["requirements"]]
    assert ids == ["REQ-SCOPED"]
    assert "REQ-OTHER" not in json.dumps(context, ensure_ascii=False)
    assert "field:added_entity.added_field" in context["removable_added_targets"]
    reject_run(module_root, run_id)


def test_review_correction_patch_preserves_unaffected_traceability(tmp_path: Path) -> None:
    _, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-PATCH")
    working_root = run_path / "working/data_schema"
    entity_id = read_json(working_root / "schema.json", {})["entities"][0]["id"]
    write_requirement_links(
        working_root=working_root,
        links=[
            {"requirement_id": "REQ-PATCH", "target_type": "entity", "target_id": entity_id},
            {"requirement_id": "REQ-KEEP", "target_type": "entity", "target_id": entity_id},
        ],
    )

    result = patch_requirement_links(
        working_root=working_root,
        updates=[{"requirement_id": "REQ-PATCH", "links": []}],
    )
    patch_requirement_assessments(
        result_root=run_path / "result",
        updates=[
            {
                "requirement_id": "REQ-PATCH",
                "classification": "no_data",
                "reason": "Не влияет на логическую схему",
            }
        ],
        agent_note=None,
        warnings=None,
    )

    links = read_json(working_root / "mappings/requirement_data_links.json", {})["links"]
    assert result["patched_requirement_count"] == 1
    assert all(item["requirement_id"] != "REQ-PATCH" for item in links)
    assert any(item["requirement_id"] == "REQ-KEEP" for item in links)
    report = read_json(run_path / "result/agent_report.json", {})
    assert report["no_data"][0]["requirement_id"] == "REQ-PATCH"
    reject_run(module_root, run_id)


def test_traceability_patch_batches_accumulate_without_erasing_previous_batch(tmp_path: Path) -> None:
    _, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-BATCH-1")
    working_root = run_path / "working/data_schema"
    entity_id = read_json(working_root / "schema.json", {})["entities"][0]["id"]
    write_requirement_links(working_root=working_root, links=[])

    patch_requirement_links(
        working_root=working_root,
        updates=[
            {
                "requirement_id": "REQ-BATCH-1",
                "links": [{"target_type": "entity", "target_id": entity_id, "relation": "uses"}],
            }
        ],
    )
    patch_requirement_links(
        working_root=working_root,
        updates=[
            {
                "requirement_id": "REQ-BATCH-2",
                "links": [{"target_type": "entity", "target_id": entity_id, "relation": "defines"}],
            }
        ],
    )

    links = read_json(working_root / "mappings/requirement_data_links.json", {})["links"]
    assert {item["requirement_id"] for item in links} == {"REQ-BATCH-1", "REQ-BATCH-2"}
    reject_run(module_root, run_id)


def test_complete_traceability_requires_every_input_requirement_once(tmp_path: Path) -> None:
    _, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-FULL-1")
    working_root = run_path / "working/data_schema"
    entity_id = read_json(working_root / "schema.json", {})["entities"][0]["id"]
    write_json(
        run_path / "input/requirements.json",
        {
            "projects": [],
            "groups": [],
            "requirements": [
                {"id": "REQ-FULL-1", "name": "Первое"},
                {"id": "REQ-FULL-2", "name": "Второе"},
            ],
        },
    )

    with pytest.raises(ValueError, match="every input requirement exactly once"):
        write_complete_requirement_results(
            run_path=run_path,
            updates=[
                {
                    "requirement_id": "REQ-FULL-1",
                    "classification": "direct",
                    "links": [
                        {
                            "target_type": "entity",
                            "target_id": entity_id,
                            "relation": "uses",
                        }
                    ],
                }
            ],
            agent_note=None,
            warnings=None,
        )

    result = write_complete_requirement_results(
        run_path=run_path,
        updates=[
            {
                "requirement_id": "REQ-FULL-1",
                "classification": "direct",
                "links": [
                    {
                        "target_type": "entity",
                        "target_id": entity_id,
                        "relation": "uses",
                    }
                ],
            },
            {
                "requirement_id": "REQ-FULL-2",
                "classification": "no_data",
                "links": [],
            },
        ],
        agent_note=None,
        warnings=None,
    )

    assert result["patched_requirement_count"] == 2
    report = read_json(run_path / "result/agent_report.json", {})
    assert report["no_data"] == [
        {"requirement_id": "REQ-FULL-2", "reason": ""}
    ]
    requirements_data = read_json(run_path / "input/requirements.json", {})
    assessment_validation = validate_requirement_assessments(
        run_path=run_path,
        requirements_data=requirements_data,
    )
    assert assessment_validation["valid"] is True
    reject_run(module_root, run_id)


def test_partial_requirement_scope_preserves_inherited_links(tmp_path: Path) -> None:
    workspace = tmp_path / "partial_scope"
    module_root = workspace / "data_schema"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", module_root)
    write_schema_core(
        working_root=module_root,
        schema=None,
        entities=[
            {
                "id": "existing_item",
                "title": "Существующий объект",
                "description": "",
                "fields": [],
            }
        ],
    )
    write_requirement_links(
        working_root=module_root,
        links=[
            {
                "requirement_id": "REQ-HISTORICAL",
                "target_type": "entity",
                "target_id": "existing_item",
                "relation": "defines",
            }
        ],
    )
    requirements_file = workspace / "requirements" / "changed.json"
    requirements = {
        "projects": [],
        "groups": [],
        "requirements": [{"id": "REQ-CURRENT", "name": "Текущее изменение"}],
    }
    write_json(requirements_file, requirements)
    run = create_run(
        module_root=module_root,
        workspace_id="ws_partial",
        requirements_data=requirements,
        requirements_file_name=requirements_file.name,
        requirements_source_path="requirements/changed.json",
        requirements_source_sha256=file_sha256(requirements_file),
        user_request="",
        base_mode="current",
        llm_public={"provider": "test", "model": "test"},
        config=AGENT_CONFIG,
    )
    run_path = run_root(module_root, run["run_id"])
    write_complete_requirement_results(
        run_path=run_path,
        updates=[
            {
                "requirement_id": "REQ-CURRENT",
                "classification": "direct",
                "links": [
                    {
                        "target_type": "entity",
                        "target_id": "existing_item",
                        "relation": "uses",
                    }
                ],
            }
        ],
        agent_note=None,
        warnings=None,
    )

    validation = validate_agent_working_schema(run_path)
    assert validation["valid"] is True
    assert validation["assessment_counts"] == {
        "linked": 1,
        "cross_cutting_data": 0,
        "no_data": 0,
        "unclear": 0,
        "unclassified": 0,
    }
    links = read_json(
        run_path / "working/data_schema/mappings/requirement_data_links.json",
        {"links": []},
    )["links"]
    assert {item["requirement_id"] for item in links} == {
        "REQ-HISTORICAL",
        "REQ-CURRENT",
    }

    coverage = build_semantic_review_context(
        run_path,
        review_scope="coverage",
    )
    review_links = coverage["candidate_data_schema"]["requirement_data_links"]["links"]
    assert {item["requirement_id"] for item in review_links} == {"REQ-CURRENT"}

    correction = build_review_correction_context(
        run_path,
        {
            "issues": [
                {
                    "id": "issue_current",
                    "requirement_ids": ["REQ-CURRENT"],
                    "targets": ["entity:existing_item"],
                }
            ]
        },
        correction_round=1,
    )
    assert {
        item["requirement_id"]
        for item in correction["current_requirement_links"]
    } == {"REQ-CURRENT"}


def test_partial_requirement_scope_rejects_new_unknown_link(tmp_path: Path) -> None:
    workspace = tmp_path / "partial_scope_unknown"
    module_root = workspace / "data_schema"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", module_root)
    write_schema_core(
        working_root=module_root,
        schema=None,
        entities=[
            {
                "id": "existing_item",
                "title": "Существующий объект",
                "description": "",
                "fields": [],
            }
        ],
    )
    requirements_file = workspace / "requirements" / "changed.json"
    requirements = {
        "projects": [],
        "groups": [],
        "requirements": [{"id": "REQ-CURRENT", "name": "Текущее изменение"}],
    }
    write_json(requirements_file, requirements)
    run = create_run(
        module_root=module_root,
        workspace_id="ws_partial_unknown",
        requirements_data=requirements,
        requirements_file_name=requirements_file.name,
        requirements_source_path="requirements/changed.json",
        requirements_source_sha256=file_sha256(requirements_file),
        user_request="",
        base_mode="current",
        llm_public={"provider": "test", "model": "test"},
        config=AGENT_CONFIG,
    )
    run_path = run_root(module_root, run["run_id"])
    write_complete_requirement_results(
        run_path=run_path,
        updates=[
            {
                "requirement_id": "REQ-CURRENT",
                "classification": "direct",
                "links": [
                    {
                        "target_type": "entity",
                        "target_id": "existing_item",
                        "relation": "uses",
                    }
                ],
            }
        ],
        agent_note=None,
        warnings=None,
    )
    links_path = run_path / "working/data_schema/mappings/requirement_data_links.json"
    links_doc = read_json(links_path, {"links": []})
    links_doc["links"].append(
        {
            "id": "unexpected_requirement_link",
            "requirement_id": "REQ-UNKNOWN",
            "target_type": "entity",
            "target_id": "existing_item",
            "relation": "uses",
        }
    )
    write_json(links_path, links_doc)

    validation = validate_agent_working_schema(run_path)
    assert validation["valid"] is False
    assert any(
        "unknown requirement_id REQ-UNKNOWN" in item
        or "Requirement links contain unknown IDs: REQ-UNKNOWN" in item
        for item in validation["errors"]
    )


def test_patch_can_add_nested_field_and_dictionary_value(tmp_path: Path) -> None:
    _, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-NESTED")
    working_root = run_path / "working/data_schema"
    entity_id = read_json(working_root / "schema.json", {})["entities"][0]["id"]
    write_dictionaries(
        working_root=working_root,
        dictionaries=[{"id": "state_codes", "title": "Состояния", "values": []}],
    )

    patch_schema_core(
        working_root=working_root,
        schema_patch=None,
        entities=[
            {
                "id": entity_id,
                "fields": [
                    {
                        "id": "state",
                        "title": "Состояние",
                        "type": "dictionary",
                        "required": True,
                        "description": "Текущее состояние",
                        "dictionary_id": "state_codes",
                    }
                ],
            }
        ],
    )
    patch_dictionaries(
        working_root=working_root,
        dictionaries=[
            {
                "id": "state_codes",
                "values": [{"id": "active", "title": "Активно"}],
            }
        ],
    )

    entity = read_json(working_root / f"entities/{entity_id}.json", {})
    field = next(item for item in entity["fields"] if item["id"] == "state")
    assert field["dictionary_id"] == "state_codes"
    dictionary = read_json(working_root / "dictionaries.json", {})["dictionaries"][0]
    assert dictionary["values"] == [
        {"id": "active", "title": "Активно", "description": ""}
    ]
    reject_run(module_root, run_id)


def test_primary_traceability_and_structured_correction_are_separated() -> None:
    source = (
        PROJECT_ROOT / "backend/modules/data_schema/agent_tools.py"
    ).read_text(encoding="utf-8")
    factory = (
        PROJECT_ROOT / "backend/modules/data_schema/agent_factory.py"
    ).read_text(encoding="utf-8")
    correction_apply = (
        PROJECT_ROOT / "backend/modules/data_schema/agent_semantic_correction_apply.py"
    ).read_text(encoding="utf-8")

    assert "def write_data_schema_traceability" in source
    assert "def patch_data_schema_requirement_results" not in source
    assert "def patch_data_schema_traceability" not in source
    assert '"write_data_schema_traceability"' in factory
    assert '"patch_data_schema_requirement_results"' not in factory
    assert "patch_requirement_results(" in correction_apply


def test_structured_correction_plan_applies_all_operations_in_one_transaction(
    tmp_path: Path,
) -> None:
    _, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-PLAN")
    working_root = run_path / "working/data_schema"
    entity_id = read_json(working_root / "schema.json", {})["entities"][0]["id"]

    plan = SemanticCorrectionPlanPayload.model_validate(
        {
            "summary": "Добавить поле и обновить трассировку.",
            "patch_entities": [
                {
                    "id": entity_id,
                    "fields": [
                        {
                            "id": "display_name",
                            "title": "Отображаемое имя",
                            "type": "string",
                            "required": False,
                            "description": "Имя для отображения",
                        }
                    ],
                }
            ],
            "requirement_updates": [
                {
                    "requirement_id": "REQ-PLAN",
                    "classification": "direct",
                    "links": [
                        {
                            "target_type": "field",
                            "target_id": f"{entity_id}.display_name",
                            "relation": "defines",
                        }
                    ],
                }
            ],
        }
    )

    validation = apply_semantic_correction_plan(run_path=run_path, plan=plan)

    assert validation["valid"] is True
    assert validation["correction_applied"] is True
    entity = read_json(working_root / f"entities/{entity_id}.json", {})
    assert any(item["id"] == "display_name" for item in entity["fields"])
    links = read_json(
        working_root / "mappings/requirement_data_links.json", {"links": []}
    )["links"]
    assert links == [
        {
            "id": links[0]["id"],
            "requirement_id": "REQ-PLAN",
            "target_type": "field",
            "target_id": f"{entity_id}.display_name",
            "relation": "defines",
            "implementation_status": "planned",
        }
    ]
    reject_run(module_root, run_id)


def test_structured_correction_plan_rolls_back_invalid_operations(tmp_path: Path) -> None:
    _, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-ROLLBACK")
    working_root = run_path / "working/data_schema"
    before = read_json(working_root / "schema.json", {})
    plan = SemanticCorrectionPlanPayload.model_validate(
        {
            "summary": "Некорректный технический план.",
            "patch_entities": [
                {
                    "id": "unknown_entity",
                    "title": "Не должно примениться",
                }
            ],
        }
    )

    validation = apply_semantic_correction_plan(run_path=run_path, plan=plan)

    assert validation["valid"] is True
    assert validation["correction_applied"] is False
    assert "Unknown entity ID" in validation["correction_error"]
    assert read_json(working_root / "schema.json", {}) == before
    reject_run(module_root, run_id)


def test_structured_correction_requires_explicit_ids_for_new_objects() -> None:
    with pytest.raises(ValueError, match="write_dictionaries.0.id"):
        SemanticCorrectionPlanPayload.model_validate(
            {
                "summary": "Создать новый справочник.",
                "write_dictionaries": [
                    {
                        "title": "Новый справочник",
                        "values": [
                            {"id": "active", "title": "Активно"}
                        ],
                    }
                ],
            }
        )

    with pytest.raises(ValueError, match="write_entities.0.fields.0.id"):
        SemanticCorrectionPlanPayload.model_validate(
            {
                "summary": "Создать новую сущность.",
                "write_entities": [
                    {
                        "id": "item",
                        "title": "Объект",
                        "fields": [{"title": "Название"}],
                    }
                ],
            }
        )


def test_structured_correction_uses_explicit_dictionary_id_in_same_plan(
    tmp_path: Path,
) -> None:
    _, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-DICT-PLAN")
    working_root = run_path / "working/data_schema"
    entity_id = read_json(working_root / "schema.json", {})["entities"][0]["id"]

    plan = SemanticCorrectionPlanPayload.model_validate(
        {
            "summary": "Добавить справочник и поле со ссылкой на него.",
            "write_dictionaries": [
                {
                    "id": "lifecycle_states",
                    "title": "Состояния жизненного цикла",
                    "values": [
                        {"id": "active", "title": "Активно"},
                        {"id": "closed", "title": "Закрыто"},
                    ],
                }
            ],
            "patch_entities": [
                {
                    "id": entity_id,
                    "fields": [
                        {
                            "id": "lifecycle_state_id",
                            "title": "Состояние",
                            "type": "dictionary",
                            "required": False,
                            "description": "Состояние объекта",
                            "dictionary_id": "lifecycle_states",
                        }
                    ],
                }
            ],
        }
    )

    validation = apply_semantic_correction_plan(run_path=run_path, plan=plan)

    assert validation["correction_applied"] is True
    entity = read_json(working_root / f"entities/{entity_id}.json", {})
    field = next(
        item for item in entity["fields"] if item["id"] == "lifecycle_state_id"
    )
    assert field["dictionary_id"] == "lifecycle_states"
    reject_run(module_root, run_id)


def test_only_current_run_additions_can_be_removed(tmp_path: Path) -> None:
    _, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-REMOVE")
    working_root = run_path / "working/data_schema"
    base_root = run_path / "base/data_schema"
    base_entity_id = read_json(working_root / "schema.json", {})["entities"][0]["id"]
    shutil.copy2(working_root / "schema.json", base_root / "schema.json")
    (base_root / "entities").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        working_root / "entities" / f"{base_entity_id}.json",
        base_root / "entities" / f"{base_entity_id}.json",
    )
    write_schema_core(
        working_root=working_root,
        schema=None,
        entities=[
            {
                "id": base_entity_id,
                "title": "Клиент",
                "fields": [{"id": "temporary", "title": "Временное поле"}],
            }
        ],
    )

    result = remove_run_additions(
        run_path=run_path,
        targets=[f"field:{base_entity_id}.temporary"],
    )
    assert result["removed_count"] == 1
    with pytest.raises(ValueError, match="Only objects added"):
        remove_run_additions(run_path=run_path, targets=[f"entity:{base_entity_id}"])
    reject_run(module_root, run_id)


def test_requirement_result_patch_accepts_provider_serialized_json() -> None:
    results = RequirementResultsPatchArgs.model_validate(
        {
            "updates": json.dumps(
                [
                    {
                        "requirement_id": "REQ-1",
                        "classification": "direct",
                        "links": [
                            {
                                "target": {
                                    "target_type": "field",
                                    "entity_id": "entity_alpha",
                                    "field_id": "field_code",
                                },
                                "relation": "uses",
                            }
                        ],
                    },
                    {
                        "requirement_id": "REQ-2",
                        "classification": "no_data",
                        "links": [],
                        "reason": "UI only",
                        "warnings": ["Проверить границу UI и данных"],
                    },
                ]
            ),
            "warnings": "[]",
        }
    )

    assert results.updates[0].requirement_id == "REQ-1"
    assert results.updates[0].links[0].target_type == "field"
    assert results.updates[0].links[0].target_id == "entity_alpha.field_code"
    assert results.updates[1].classification == "no_data"
    assert results.updates[1].warnings == ["Проверить границу UI и данных"]



def test_requirement_result_allows_omitted_reason_for_simple_exceptions() -> None:
    results = RequirementResultsPatchArgs.model_validate(
        {
            "updates": [
                {
                    "requirement_id": "REQ-NO-DATA",
                    "classification": "no_data",
                    "links": [],
                },
                {
                    "requirement_id": "REQ-CROSS",
                    "classification": "cross_cutting_data",
                    "links": [],
                },
            ]
        }
    )

    assert results.updates[0].reason == ""
    assert results.updates[1].reason == ""
    with pytest.raises(ValidationError, match="classification=unclear"):
        RequirementResultsPatchArgs.model_validate(
            {
                "updates": [
                    {
                        "requirement_id": "REQ-UNCLEAR",
                        "classification": "unclear",
                        "links": [],
                    }
                ]
            }
        )


def test_traceability_normalizes_only_redundant_owner_prefixes(tmp_path: Path) -> None:
    working_root = tmp_path / "data_schema"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", working_root)
    write_schema_core(
        working_root=working_root,
        schema=None,
        entities=[
            {
                "id": "client",
                "title": "Client",
                "fields": [{"id": "client_full_name", "title": "Full name"}],
            }
        ],
    )

    link = materialize_requirement_link(
        working_root=working_root,
        payload={
            "target_type": "field",
            "target_id": "client.full_name",
            "relation": "uses",
        },
    )

    assert link["target_id"] == "client.client_full_name"
    with pytest.raises(ValueError, match="Unknown exact target"):
        materialize_requirement_link(
            working_root=working_root,
            payload={
                "target_type": "field",
                "target_id": "client.display_label",
                "relation": "uses",
            },
        )


def test_id_only_nested_patch_is_accepted_as_noop(tmp_path: Path) -> None:
    args = CorePatchArgs.model_validate(
        {"entities": [{"id": "client", "fields": [{"id": "client_id"}]}]}
    )
    assert args.entities[0].fields[0].id == "client_id"

    working_root = tmp_path / "data_schema"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", working_root)
    write_schema_core(
        working_root=working_root,
        schema=None,
        entities=[
            {
                "id": "client",
                "title": "Client",
                "fields": [{"id": "client_id", "title": "ID", "type": "uuid"}],
            }
        ],
    )
    before = read_json(working_root / "entities/client.json", {})
    patch_schema_core(
        working_root=working_root,
        schema_patch=None,
        entities=[{"id": "client", "fields": [{"id": "client_id"}]}],
    )
    assert read_json(working_root / "entities/client.json", {}) == before

def test_requirement_result_patch_updates_links_and_assessment_together(tmp_path: Path) -> None:
    working_root = tmp_path / "working/data_schema"
    result_root = tmp_path / "result"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", working_root)
    result_root.mkdir(parents=True)
    write_schema_core(
        working_root=working_root,
        schema=None,
        entities=[
            {
                "id": "entity_alpha",
                "title": "Entity Alpha",
                "fields": [{"id": "field_code", "title": "Code"}],
            }
        ],
    )

    patch_requirement_results(
        working_root=working_root,
        result_root=result_root,
        updates=[
            {
                "requirement_id": "REQ-1",
                "classification": "direct",
                "links": [
                    {
                        "target": {
                            "target_type": "field",
                            "entity_id": "entity_alpha",
                            "field_id": "field_code",
                        },
                        "relation": "uses",
                    }
                ],
            },
            {
                "requirement_id": "REQ-2",
                "classification": "no_data",
                "links": [],
                "reason": "No domain data",
                "warnings": ["Needs human confirmation"],
            },
        ],
        agent_note=None,
        warnings=None,
    )

    links = read_json(
        working_root / "mappings/requirement_data_links.json", {"links": []}
    )["links"]
    report = read_json(result_root / "agent_report.json", {})
    assert {item["requirement_id"] for item in links} == {"REQ-1"}
    assert report["no_data"] == [
        {"requirement_id": "REQ-2", "reason": "No domain data"}
    ]
    assert report["requirement_warnings"] == [
        {"requirement_id": "REQ-2", "messages": ["Needs human confirmation"]}
    ]


def test_agent_report_does_not_publish_validation_json_as_human_comment(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    result_path = run_path / "result"
    result_path.mkdir(parents=True)
    technical = json.dumps(
        {
            "valid": True,
            "errors": [],
            "warnings": [],
            "counts": {"entities": 1},
            "completed": True,
            "next_action": "stop",
        }
    )
    write_json(
        result_path / "agent_report.json",
        {
            "summary": "",
            "agent_note": technical,
            "cross_cutting_data": [],
            "no_data": [],
            "unclear": [],
            "warnings": [],
        },
    )

    ensure_agent_report(run_path, {"messages": [{"content": technical}]})
    report = finalize_agent_report(
        report_path=result_path / "agent_report.json",
        changes={},
        requirements_result={"assessment_counts": {}},
    )

    assert report["agent_note"] == ""


def test_requirements_result_exposes_unclear_reason_and_requirement_warning(tmp_path: Path) -> None:
    requirements_file = tmp_path / "requirements.json"
    schema_root = tmp_path / "data_schema"
    report_file = tmp_path / "agent_report.json"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", schema_root)
    write_json(
        requirements_file,
        {
            "requirements": [
                {
                    "id": "REQ-UNCLEAR",
                    "name": "Неоднозначное требование",
                    "description": "Описание",
                }
            ]
        },
    )
    write_json(
        report_file,
        {
            "unclear": [
                {
                    "requirement_id": "REQ-UNCLEAR",
                    "reason": "Недостаточно данных для выбора объекта",
                }
            ],
            "cross_cutting_data": [],
            "no_data": [],
            "warnings": [],
            "requirement_warnings": [
                {
                    "requirement_id": "REQ-UNCLEAR",
                    "messages": ["Нужно уточнить владельца данных"],
                }
            ],
        },
    )

    result = build_requirements_data_result(
        requirements_file=requirements_file,
        schema_root=schema_root,
        agent_report_file=report_file,
        run={"run_id": "run-test"},
    )

    assert result["requirements"][0]["warnings"] == ["Нужно уточнить владельца данных"]
    assert any("REQ-UNCLEAR" in item and "Недостаточно данных" in item for item in result["traceability_warnings"])
    assert any("Нужно уточнить владельца" in item for item in result["traceability_warnings"])


def test_external_requirements_source_is_resolved(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    module_root = workspace / "data_schema"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", module_root)
    requirements_file = workspace / "requirements/requirements.json"
    write_json(
        requirements_file,
        {"projects": [], "groups": [], "requirements": [{"id": "REQ-1"}]},
    )
    write_json(
        module_root / "requirements_source.json",
        {"type": "workspace_file", "path": "requirements/requirements.json"},
    )

    requirements, metadata = resolve_requirements(
        module_root, max_bytes=AGENT_CONFIG["requirements"]["max_bytes"]
    )

    assert requirements["requirements"][0]["id"] == "REQ-1"
    assert metadata["status"] == "available"
    assert metadata["path"] == "requirements/requirements.json"


def test_requirements_source_cannot_escape_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    module_root = workspace / "data_schema"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", module_root)
    write_json(tmp_path / "outside.json", {"requirements": []})

    with pytest.raises(RequirementsSourceError):
        load_requirements_from_workspace(
            module_root=module_root,
            workspace_relative_path="../outside.json",
            max_bytes=AGENT_CONFIG["requirements"]["max_bytes"],
        )


def test_apply_archives_diagnostics_and_removes_heavy_run(tmp_path: Path) -> None:
    workspace, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-APPLY")

    result = apply_run(
        module_root,
        run_id,
        keep_last=3,
        requirements_max_bytes=AGENT_CONFIG["requirements"]["max_bytes"],
    )

    assert result["status"] == "applied"
    assert run_path.is_dir()
    assert {path.name for path in run_path.iterdir()} == {"run.json", "diagnostics"}
    assert completed_run_file(module_root, run_id).is_file()
    completed = read_json(completed_run_file(module_root, run_id), {})
    assert completed["status"] == "applied"
    assert any(event.get("type") == "applied" for event in completed.get("recent_events", []))
    stored_archive = stored_diagnostics_archive_path(module_root, run_id, 1)
    assert stored_archive.is_file()
    assert ensure_diagnostics_archive(module_root, run_id) == stored_archive
    with zipfile.ZipFile(stored_archive) as diagnostics:
        assert "result/validation.json" in diagnostics.namelist()
    assert latest_snapshot(module_root) is not None
    assert read_json(module_root / "requirements_source.json", {})["path"] == (
        "requirements/requirements.json"
    )
    assert not (module_root / "requirements.json").exists()
    resolved, metadata = resolve_requirements(
        module_root, max_bytes=AGENT_CONFIG["requirements"]["max_bytes"]
    )
    assert resolved["requirements"][0]["id"] == "REQ-APPLY"
    assert metadata["changed_since_sync"] is False


def test_apply_requires_unchanged_requirements_source(tmp_path: Path) -> None:
    workspace, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-CHANGED")
    requirements_file = workspace / "requirements/requirements.json"
    changed = read_json(requirements_file, {})
    changed["requirements"].append({"id": "REQ-NEW", "name": "Новое требование"})
    write_json(requirements_file, changed)

    with pytest.raises(ValueError, match="изменился"):
        apply_run(
            module_root,
            run_id,
            keep_last=3,
            requirements_max_bytes=AGENT_CONFIG["requirements"]["max_bytes"],
        )

    assert run_path.is_dir()
    reject_run(module_root, run_id)


def test_regeneration_final_diagnostics_include_previous_attempt(tmp_path: Path) -> None:
    _, module_root, run_id, _ = _preview_ready_run(tmp_path, "REQ-REGEN")
    reset_for_regeneration(module_root, run_id, "Повторная попытка", config=AGENT_CONFIG)
    _write_valid_preview(module_root, run_id, "REQ-REGEN", "Клиент повторной попытки")

    reject_run(module_root, run_id)

    archive = stored_diagnostics_archive_path(module_root, run_id, 2)
    with zipfile.ZipFile(archive) as diagnostics:
        assert "previous_attempts/attempt_1.zip" in diagnostics.namelist()




def test_regeneration_refreshes_llm_metadata_and_event(tmp_path: Path) -> None:
    _, module_root, run_id, _ = _preview_ready_run(tmp_path, "REQ-LLM-REGEN")

    reset_for_regeneration(
        module_root,
        run_id,
        "Смена модели",
        config=AGENT_CONFIG,
        llm_public={
            "provider": "ollama-cloud",
            "model": "deepseek-v4-flash",
            "base_url": "https://ollama.com/v1",
            "api_key_configured": True,
        },
    )

    run = get_run(module_root, run_id)
    assert run["llm"] == {
        "provider": "ollama-cloud",
        "model": "deepseek-v4-flash",
        "base_url": "https://ollama.com/v1",
    }
    events = read_events(module_root, run_id, after=0, limit=20)["events"]
    regeneration = [event for event in events if event.get("type") == "regeneration_started"]
    assert regeneration[-1]["data"]["llm"]["model"] == "deepseek-v4-flash"


def test_reported_model_is_read_from_response_metadata() -> None:
    class Message:
        response_metadata = {"model_name": "glm-5.2"}

    class Generation:
        message = Message()
        generation_info = None

    class Response:
        llm_output = {}
        generations = [[Generation()]]

    assert _reported_model(Response()) == "glm-5.2"


def test_reject_archives_diagnostics_and_removes_heavy_run(tmp_path: Path) -> None:
    _, module_root, run_id, run_path = _preview_ready_run(tmp_path, "REQ-REJECT")

    result = reject_run(module_root, run_id)

    assert result["status"] == "rejected"
    assert run_path.is_dir()
    assert {path.name for path in run_path.iterdir()} == {"run.json", "diagnostics"}
    assert completed_run_file(module_root, run_id).is_file()
    completed = read_json(completed_run_file(module_root, run_id), {})
    assert completed["status"] == "rejected"
    assert any(event.get("type") == "rejected" for event in completed.get("recent_events", []))
    stored_archive = stored_diagnostics_archive_path(module_root, run_id, 1)
    assert stored_archive.is_file()
    assert ensure_diagnostics_archive(module_root, run_id) == stored_archive


def test_requirement_result_patch_rejects_relation_as_classification() -> None:
    with pytest.raises(ValidationError):
        RequirementResultsPatchArgs.model_validate(
            {
                "updates": [
                    {"requirement_id": "REQ-1", "classification": "uses", "links": []},
                ]
            }
        )


def test_requirement_result_patch_enforces_links_and_classification_consistency() -> None:
    with pytest.raises(ValidationError, match="requires at least one direct link"):
        RequirementResultsPatchArgs.model_validate(
            {
                "updates": [
                    {"requirement_id": "REQ-1", "classification": "direct", "links": []},
                ]
            }
        )
    with pytest.raises(ValidationError, match="requires an empty links array"):
        RequirementResultsPatchArgs.model_validate(
            {
                "updates": [
                    {
                        "requirement_id": "REQ-1",
                        "classification": "no_data",
                        "reason": "UI only",
                        "links": [
                            {
                                "target": {
                                    "target_type": "entity",
                                    "entity_id": "entity_alpha",
                                },
                                "relation": "uses",
                            }
                        ],
                    },
                ]
            }
        )


def test_traceability_requires_explicit_structured_targets(tmp_path: Path) -> None:
    working_root = tmp_path / "data_schema"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", working_root)
    core_result = write_schema_core(
        working_root=working_root,
        schema=None,
        entities=[
            {
                "id": "entity_alpha",
                "title": "Entity Alpha",
                "fields": [{"id": "shared_code", "title": "Shared code"}],
            },
            {
                "id": "entity_beta",
                "title": "Entity Beta",
                "fields": [{"id": "shared_code", "title": "Shared code"}],
            },
        ],
    )

    assert {
        "target_type": "field",
        "entity_id": "entity_alpha",
        "field_id": "shared_code",
    } in core_result["canonical_references"]["fields"]

    materialized = materialize_requirement_link(
        working_root=working_root,
        payload={
            "requirement_id": "REQ-1",
            "target": {
                "target_type": "field",
                "entity_id": "entity_beta",
                "field_id": "shared_code",
            },
            "relation": "uses",
        },
    )
    assert materialized["target_type"] == "field"
    assert materialized["target_id"] == "entity_beta.shared_code"

    with pytest.raises(ValueError, match="Unknown exact target"):
        materialize_requirement_link(
            working_root=working_root,
            payload={
                "requirement_id": "REQ-2",
                "target": {
                    "target_type": "field",
                    "entity_id": "entity_missing",
                    "field_id": "shared_code",
                },
            },
        )


def test_agent_traceability_schema_accepts_compact_exact_target_id() -> None:
    payload = RequirementLinksWriteArgs.model_validate(
        {
            "links": [
                {
                    "requirement_id": "REQ-1",
                    "target_type": "field",
                    "target_id": "entity_alpha.shared_code",
                }
            ]
        }
    )
    assert payload.links[0].target_type == "field"
    assert payload.links[0].target_id == "entity_alpha.shared_code"


def test_legacy_target_rejects_fields_inconsistent_with_declared_type() -> None:
    with pytest.raises(ValidationError, match="does not permit fields: value_id"):
        RequirementLinksWriteArgs.model_validate(
            {
                "links": [
                    {
                        "requirement_id": "REQ-1",
                        "target": {
                            "target_type": "dictionary",
                            "dictionary_id": "application_status",
                            "value_id": "draft",
                        },
                    }
                ]
            }
        )


def test_legacy_dictionary_value_target_is_compacted_without_semantic_lookup() -> None:
    payload = RequirementLinksWriteArgs.model_validate(
        {
            "links": [
                {
                    "requirement_id": "REQ-1",
                    "target": {
                        "target_type": "dictionary_value",
                        "dictionary_id": "application_status",
                        "value_id": "draft",
                    },
                    "relation": "defines",
                }
            ]
        }
    )
    assert payload.links[0].target_type == "dictionary_value"
    assert payload.links[0].target_id == "application_status.draft"


def test_write_results_return_exact_canonical_references(tmp_path: Path) -> None:
    working_root = tmp_path / "data_schema"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", working_root)

    dictionaries = write_dictionaries(
        working_root=working_root,
        dictionaries=[
            {
                "title": "State",
                "values": [{"title": "Active"}],
            }
        ],
    )
    dictionary_ref = dictionaries["canonical_references"]["dictionaries"][0]
    value_ref = dictionaries["canonical_references"]["dictionary_values"][0]
    assert dictionary_ref["target_type"] == "dictionary"
    assert value_ref["dictionary_id"] == dictionary_ref["dictionary_id"]

    core = write_schema_core(
        working_root=working_root,
        schema=None,
        entities=[
            {
                "title": "Object",
                "fields": [{"title": "Identifier", "type": "uuid"}],
            }
        ],
    )
    entity_id = core["canonical_references"]["entities"][0]["entity_id"]
    relation = write_relations(
        working_root=working_root,
        relations=[
            {
                "title": "Self relation",
                "source_entity": entity_id,
                "target_entity": entity_id,
            }
        ],
    )
    assert relation["canonical_references"][0]["target_type"] == "relation"


def test_validate_tool_returns_directly_without_callback_exception() -> None:
    tools_source = (
        PROJECT_ROOT / "backend/modules/data_schema/agent_tools.py"
    ).read_text(encoding="utf-8")
    monitor_source = (
        PROJECT_ROOT / "backend/modules/data_schema/agent_monitor.py"
    ).read_text(encoding="utf-8")

    assert "@tool(return_direct=True)" in tools_source
    assert "AgentRunCompleted" not in monitor_source


def test_legacy_runtime_layout_is_migrated_to_one_run_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    module_root = workspace / "data_schema"
    module_root.mkdir(parents=True)
    root = runtime_root(module_root)
    run_id = "run_20260729_120000_abcdef12"
    legacy_completed = root / "completed_runs" / f"{run_id}.json"
    legacy_diagnostics = root / "diagnostics" / run_id / "attempt_1.zip"
    write_json(legacy_completed, {"run_id": run_id, "status": "rejected", "archived": True})
    legacy_diagnostics.parent.mkdir(parents=True, exist_ok=True)
    legacy_diagnostics.write_bytes(b"zip")

    ensure_runtime_layout(module_root)

    canonical = run_root(module_root, run_id)
    assert read_json(canonical / "run.json", {})["status"] == "rejected"
    assert (canonical / "diagnostics" / "attempt_1.zip").read_bytes() == b"zip"
    assert not (root / "completed_runs").exists()
    assert not (root / "diagnostics").exists()


def _preview_ready_run(
    tmp_path: Path,
    requirement_id: str,
) -> tuple[Path, Path, str, Path]:
    workspace = tmp_path / requirement_id.lower()
    module_root = workspace / "data_schema"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", module_root)
    requirements_file = workspace / "requirements/requirements.json"
    requirements = {
        "projects": [],
        "groups": [],
        "requirements": [{"id": requirement_id, "name": "Тестовое требование"}],
    }
    write_json(requirements_file, requirements)
    run = create_run(
        module_root=module_root,
        workspace_id="ws_test",
        requirements_data=requirements,
        requirements_file_name=requirements_file.name,
        requirements_source_path="requirements/requirements.json",
        requirements_source_sha256=file_sha256(requirements_file),
        user_request="",
        base_mode="current",
        llm_public={"provider": "test", "model": "test"},
        config=AGENT_CONFIG,
    )
    run_id = run["run_id"]
    run_path = run_root(module_root, run_id)
    _write_valid_preview(module_root, run_id, requirement_id, "Клиент")
    return workspace, module_root, run_id, run_path


def _write_valid_preview(
    module_root: Path,
    run_id: str,
    requirement_id: str,
    entity_title: str,
) -> None:
    run_path = run_root(module_root, run_id)
    working_root = run_path / "working/data_schema"
    write_schema_core(
        working_root=working_root,
        schema=None,
        entities=[{"title": entity_title, "description": "", "fields": []}],
    )
    entity_id = read_json(working_root / "schema.json", {})["entities"][0]["id"]
    write_relations(working_root=working_root, relations=[])
    write_requirement_links(
        working_root=working_root,
        links=[
            {
                "requirement_id": requirement_id,
                "target_type": "entity",
                "target_id": entity_id,
            }
        ],
    )
    write_json(
        run_path / "result/agent_report.json",
        {
            "summary": "",
            "agent_note": "test",
            "cross_cutting_data": [],
            "no_data": [],
            "unclear": [],
            "warnings": [],
        },
    )
    validation = validate_agent_working_schema(run_path)
    assert validation["valid"], validation
    semantic_review = {
        "status": "approved",
        "decision": "approve",
        "blocking": False,
        "review_id": "combined_1",
        "review_kind": "combined",
        "coverage_complete": True,
        "verified_issue_ids": [],
        "summary": "Проверка пройдена",
        "review_note": "",
        "strengths": [],
        "issue_counts": {"must_fix": 0, "advisory": 0},
        "issues": [],
    }
    finalize_preview(
        module_root,
        run_id,
        validation,
        semantic_review=semantic_review,
    )



def test_core_write_rejects_entity_id_as_dictionary_reference(tmp_path: Path) -> None:
    working_root = tmp_path / "data_schema"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", working_root)
    write_schema_core(
        working_root=working_root,
        schema=None,
        entities=[{"id": "entity_category", "title": "Category", "fields": []}],
    )

    with pytest.raises(ValueError, match="unknown dictionary_id 'entity_category'"):
        write_schema_core(
            working_root=working_root,
            schema=None,
            entities=[
                {
                    "id": "entity_record",
                    "title": "Record",
                    "fields": [
                        {
                            "id": "field_category",
                            "title": "Category",
                            "type": "dictionary",
                            "dictionary_id": "entity_category",
                        }
                    ],
                }
            ],
        )

    assert not (working_root / "entities/entity_record.json").exists()


def test_core_write_accepts_only_existing_exact_dictionary_id(tmp_path: Path) -> None:
    working_root = tmp_path / "data_schema"
    shutil.copytree(PROJECT_ROOT / "modules/data_schema/init", working_root)
    result = write_dictionaries(
        working_root=working_root,
        dictionaries=[{"id": "dict_category", "title": "Category", "values": []}],
    )
    dictionary_id = result["canonical_references"]["dictionaries"][0]["dictionary_id"]

    write_schema_core(
        working_root=working_root,
        schema=None,
        entities=[
            {
                "id": "entity_record",
                "title": "Record",
                "fields": [
                    {
                        "id": "field_category",
                        "title": "Category",
                        "type": "dictionary",
                        "dictionary_id": dictionary_id,
                    }
                ],
            }
        ],
    )

    entity = read_json(working_root / "entities/entity_record.json", {})
    assert entity["fields"][0]["dictionary_id"] == dictionary_id


def test_validation_retry_thread_is_unique_for_each_parent_phase() -> None:
    primary = validation_correction_thread_id(
        {"configurable": {"thread_id": "run_1"}},
        run_id="run_1",
        retry_index=0,
    )
    semantic = validation_correction_thread_id(
        {"configurable": {"thread_id": "run_1_semantic_1"}},
        run_id="run_1",
        retry_index=0,
    )
    second_semantic = validation_correction_thread_id(
        {"configurable": {"thread_id": "run_1_semantic_2"}},
        run_id="run_1",
        retry_index=0,
    )

    assert primary == "run_1_validation_1"
    assert semantic == "run_1_semantic_1_validation_1"
    assert second_semantic == "run_1_semantic_2_validation_1"
    assert len({primary, semantic, second_semantic}) == 3



def test_runner_uses_direct_traceability_without_intermediate_generation() -> None:
    runner = (
        PROJECT_ROOT / "backend/modules/data_schema/agent_runner.py"
    ).read_text(encoding="utf-8")
    prompt = (
        PROJECT_ROOT / "modules/data_schema/agent/prompts/run.md"
    ).read_text(encoding="utf-8")

    assert "write_data_schema_traceability" in prompt
    assert "ровно один раз" in prompt.lower()
    assert "build_traceability_results(" not in runner
    assert "build_generation_plan(" not in runner
    assert "build_concept_mappings(" not in runner

def test_new_schema_ids_are_requested_in_english_not_transliteration() -> None:
    prompt = (
        PROJECT_ROOT / "modules/data_schema/agent/prompts/system.md"
    ).read_text(encoding="utf-8")

    assert "английск" in prompt.lower()
    assert "транслитерац" in prompt.lower()
    assert "title" in prompt and "description" in prompt
