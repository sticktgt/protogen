from __future__ import annotations

import shutil
import sys
from pathlib import Path

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

from backend.modules.ui_schema import agent_pipeline
from backend.modules.ui_schema.agent_pipeline_runtime import PipelineRuntime
from backend.modules.ui_schema.agent_pipeline_models import (
    PipelineAuditIssue,
    PipelineAuditOutput,
    PipelineChangeBundle,
    PipelineCorrectionOutput,
    PipelineDecision,
    PipelineElementChange,
    PipelinePageDocument,
    PipelinePageUpdate,
    PipelinePlanOutput,
    PipelineTarget,
    RequirementAnalysisItem,
    RequirementAnalysisOutput,
)
from backend.modules.ui_schema.files import read_json, write_json


def test_managed_pipeline_updates_schema_across_mechanical_planning_batches(
    tmp_path: Path, monkeypatch
) -> None:
    run_path = tmp_path / "run"
    working = run_path / "working" / "ui_schema"
    base = run_path / "base" / "ui_schema"
    shutil.copytree(PROJECT_ROOT / "modules/ui_schema/init", working)
    shutil.copytree(PROJECT_ROOT / "modules/ui_schema/init", base)
    write_json(
        run_path / "input/requirements.json",
        {
            "requirements": [
                {
                    "id": "R-1",
                    "name": "Primary information",
                    "description": "Show primary information.",
                    "acceptanceCriteria": ["The value is visible."],
                },
                {
                    "id": "R-2",
                    "name": "Additional state",
                    "description": "Show an additional state near the information.",
                    "acceptanceCriteria": ["The state is visible."],
                },
            ]
        },
    )
    write_json(run_path / "input/task.json", {"operation": "synchronize"})
    write_json(
        run_path / "run.json",
        {"workspace_id": "workspace", "run_id": "run-test"},
    )

    monkeypatch.setattr(agent_pipeline, "create_chat_model", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(PipelineRuntime, "phase", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(PipelineRuntime, "ensure_not_cancelled", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(PipelineRuntime, "event", lambda *_args, **_kwargs: None)

    calls: list[tuple[str, str]] = []

    def fake_invoke_validated(self, *, stage, base_context, validator, **_kwargs):
        if stage == "analysis":
            requirement = base_context["batch"]["requirements"][0]
            requirement_id = requirement["id"]
            calls.append((stage, requirement_id))
            output = RequirementAnalysisOutput(
                items=[
                    RequirementAnalysisItem(
                        requirement_id=requirement_id,
                        ui_effect="display",
                        classification="direct_ui",
                        ui_outcomes=["Видимый результат"],
                        reason="Требование описывает видимый результат.",
                    )
                ]
            )
        elif stage == "planning":
            requirement_id = base_context["batch"]["requirements"][0]["id"]
            calls.append((stage, requirement_id))
            if requirement_id == "R-1":
                output = PipelinePlanOutput(
                    decisions=[
                        PipelineDecision(
                            requirement_id="R-1",
                            ui_effect="display",
                            classification="direct_ui",
                            targets=[
                                PipelineTarget(
                                    target_type="ui_element",
                                    target_id="profile.panel",
                                    action="create",
                                    implementation_status="implemented",
                                )
                            ],
                            reason="Панель содержит видимую информацию.",
                        )
                    ],
                    changes=PipelineChangeBundle(
                        create_pages=[
                            PipelinePageDocument(
                                page_id="profile",
                                title="Profile",
                                elements=[
                                    {
                                        "id": "profile.panel",
                                        "type": "details_panel",
                                        "label": "Information",
                                        "children": [
                                            {
                                                "id": "profile.name",
                                                "type": "text",
                                                "label": "Name",
                                            }
                                        ],
                                    }
                                ],
                            )
                        ]
                    ),
                )
            else:
                assert "profile.json" in base_context["ui_schema"]["pages"]
                assert any(
                    item["id"] == "profile"
                    for item in base_context["technical_index"]["pages"]
                )
                assert any(
                    item["id"] == "profile.panel"
                    and item["parent_id"] == "profile"
                    for item in base_context["technical_index"]["elements"]
                )
                output = PipelinePlanOutput(
                    decisions=[
                        PipelineDecision(
                            requirement_id="R-2",
                            ui_effect="state",
                            classification="direct_ui",
                            targets=[
                                PipelineTarget(
                                    target_type="ui_element",
                                    target_id="profile.panel",
                                    action="extend",
                                    implementation_status="implemented",
                                )
                            ],
                            reason="Существующая панель дополняется состоянием.",
                        )
                    ],
                    changes=PipelineChangeBundle(
                        update_pages=[
                            PipelinePageUpdate(
                                page_id="profile",
                                title="Updated profile",
                            )
                        ],
                        upsert_elements=[
                            PipelineElementChange(
                                page_id="profile",
                                parent_id="profile.panel",
                                element={
                                    "id": "profile.status",
                                    "type": "text",
                                    "label": "Status",
                                },
                            )
                        ]
                    ),
                )
        elif stage == "audit":
            calls.append((stage, "batch"))
            output = PipelineAuditOutput()
        else:
            raise AssertionError(f"Unexpected stage: {stage}")
        assert validator(output) == []
        return output

    monkeypatch.setattr(PipelineRuntime, "invoke_validated", fake_invoke_validated)

    result = agent_pipeline.run_managed_pipeline(
        module_root=tmp_path / "module",
        run_id="run-test",
        run_path=run_path,
        llm_settings={},
        agent_config=_agent_config(),
        callback=object(),
    )

    assert calls == [
        ("analysis", "R-1"),
        ("analysis", "R-2"),
        ("planning", "R-1"),
        ("planning", "R-2"),
        ("audit", "batch"),
    ]
    page = read_json(working / "pages/profile.json", {})
    assert page["title"] == "Updated profile"
    panel = page["elements"][0]
    assert panel["id"] == "profile.panel"
    assert [item["id"] for item in panel["children"]] == [
        "profile.name",
        "profile.status",
    ]
    links = read_json(working / "mappings/requirement_ui_links.json", {})["links"]
    assert {item["requirement_id"] for item in links} == {"R-1", "R-2"}
    assert read_json(run_path / "result/pipeline_state.json", {})["status"] == "generated"
    assert len(result["decisions"]) == 2


def _agent_config() -> dict:
    return {
        "pipeline": {
            "analysis_batch_size": 1,
            "planning_batch_size": 1,
            "audit_batch_size": 2,
            "correction_batch_size": 1,
            "stage_attempts": 2,
            "apply_repair_attempts": 1,
            "validation_repair_attempts": 1,
            "correction_rounds": 1,
            "structural_review_candidate_limit": 24,
            "output_contract_prompt": "pipeline_output_contract",
            "change_rules_prompt": "pipeline_change_rules",
            "tool_choice": "required",
            "stages": {
                stage: {"prompt": stage, "tool_name": f"submit_{stage}"}
                for stage in (
                    "analysis",
                    "planning",
                    "repair",
                    "audit",
                    "correction",
                    "structural_review",
                )
            },
        },
        "context": {
            "requirement_fields": [
                "id",
                "name",
                "description",
                "acceptanceCriteria",
            ]
        },
        "execution": {
            "write_page_max_top_level_elements": 32,
            "write_element_batch_max_changes": 120,
            "apply_change_bundle_max_pages": 8,
            "apply_change_bundle_max_moves": 40,
            "apply_change_bundle_max_links": 120,
            "apply_change_bundle_max_removals": 30,
        },
    }


def test_structured_stage_renders_retry_feedback_in_dedicated_placeholders(
    monkeypatch,
) -> None:
    import json
    import types

    from backend.modules.ui_schema import agent_pipeline_llm

    class FakeStructuredTool:
        @classmethod
        def from_function(cls, **kwargs):
            return kwargs

    tools_module = types.ModuleType("langchain_core.tools")
    tools_module.StructuredTool = FakeStructuredTool
    core_module = types.ModuleType("langchain_core")
    core_module.__path__ = []
    monkeypatch.setitem(sys.modules, "langchain_core", core_module)
    monkeypatch.setitem(sys.modules, "langchain_core.tools", tools_module)

    rendered: list[dict] = []

    def fake_render(_config, _name, **values):
        rendered.append(values)
        if "context_json" in values:
            return "Structured result\n" + values["context_json"]
        return "Output contract"

    class FakeResponse:
        tool_calls = [
            {
                "name": "submit_analysis",
                "args": {
                    "payload": {
                        "items": [
                            {
                                "requirement_id": "R-1",
                                "ui_effect": "none",
                                "classification": "no_ui",
                                "ui_outcomes": [],
                                "reason": "Нет наблюдаемого результата интерфейса",
                            }
                        ],
                        "warnings": [],
                    }
                },
            }
        ]

    invoked_messages: list[list[dict]] = []

    class FakeModel:
        def bind_tools(self, *_args, **_kwargs):
            return self

        def invoke(self, messages, **_kwargs):
            invoked_messages.append(messages)
            return FakeResponse()

    monkeypatch.setattr(agent_pipeline_llm, "render_prompt", fake_render)
    monkeypatch.setattr(
        agent_pipeline_llm,
        "pipeline_settings",
        lambda _config: {"stage_attempts": 1, "tool_choice": "required"},
    )
    monkeypatch.setattr(agent_pipeline_llm, "stage_prompt_name", lambda *_args: "analysis")
    monkeypatch.setattr(
        agent_pipeline_llm,
        "pipeline_output_contract_prompt_name",
        lambda *_args: "output_contract",
    )
    monkeypatch.setattr(
        agent_pipeline_llm,
        "pipeline_change_rules_prompt_name",
        lambda *_args: "change_rules",
    )
    monkeypatch.setattr(
        agent_pipeline_llm, "stage_tool_name", lambda *_args: "submit_analysis"
    )
    monkeypatch.setattr(agent_pipeline_llm, "append_event", lambda *_args, **_kwargs: None)

    result = agent_pipeline_llm.invoke_structured_stage(
        model=FakeModel(),
        output_model=RequirementAnalysisOutput,
        stage="analysis",
        context={
            "batch": {"requirements": [{"id": "R-1"}]},
            "validation_feedback": ["missing field"],
            "previous_output": {"items": []},
        },
        module_root=Path("."),
        run_id="run",
        agent_config={},
        callback=object(),
        invocation_metadata={},
        attempts=1,
    )

    assert result.items[0].requirement_id == "R-1"
    assert invoked_messages[0][0]["role"] == "user"
    call_values = rendered[-1]
    assert call_values["change_rules"] == "Output contract"
    assert json.loads(call_values["validation_errors_json"]) == ["missing field"]
    assert json.loads(call_values["previous_output_json"]) == {"items": []}
    rendered_context = json.loads(call_values["context_json"])
    assert "validation_feedback" not in rendered_context
    assert "previous_output" not in rendered_context


def test_runtime_retry_preserves_invalid_structured_output_for_feedback(
    tmp_path: Path, monkeypatch
) -> None:
    from backend.modules.ui_schema import agent_pipeline_runtime
    from backend.modules.ui_schema.agent_pipeline_llm import PipelineStageError

    contexts: list[dict] = []

    def fake_stage(**kwargs):
        contexts.append(kwargs["context"])
        if len(contexts) == 1:
            raise PipelineStageError(
                "invalid output",
                validation_errors=["items.0.reason: field required"],
                previous_output={"items": [{"requirement_id": "R-1"}]},
            )
        return RequirementAnalysisOutput(
            items=[
                RequirementAnalysisItem(
                    requirement_id="R-1",
                    ui_effect="none",
                    classification="no_ui",
                    ui_outcomes=[],
                    reason="Нет наблюдаемого результата интерфейса.",
                )
            ]
        )

    monkeypatch.setattr(agent_pipeline_runtime, "invoke_structured_stage", fake_stage)
    runtime = PipelineRuntime(
        module_root=tmp_path,
        run_id="run",
        run_path=tmp_path / "run",
        model=object(),
        agent_config=_agent_config(),
        callback=object(),
        metadata={},
    )

    output = runtime.invoke_validated(
        output_model=RequirementAnalysisOutput,
        stage="analysis",
        base_context={"batch": {"requirements": [{"id": "R-1"}]}},
        validator=lambda _value: [],
    )

    assert output.items[0].requirement_id == "R-1"
    assert contexts[1]["validation_feedback"] == [
        "items.0.reason: field required"
    ]
    assert contexts[1]["previous_output"] == {
        "items": [{"requirement_id": "R-1"}]
    }


def test_runtime_validation_event_contains_exact_feedback(
    tmp_path: Path, monkeypatch
) -> None:
    from backend.modules.ui_schema import agent_pipeline_runtime

    output = RequirementAnalysisOutput(
        items=[
            RequirementAnalysisItem(
                requirement_id="R-1",
                ui_effect="none",
                classification="no_ui",
                ui_outcomes=[],
                reason="Нет наблюдаемого результата интерфейса.",
            )
        ]
    )
    monkeypatch.setattr(
        agent_pipeline_runtime,
        "invoke_structured_stage",
        lambda **_kwargs: output,
    )
    events: list[dict] = []
    monkeypatch.setattr(
        agent_pipeline_runtime,
        "append_event",
        lambda *_args, **kwargs: events.append(kwargs),
    )
    checks = 0

    def validator(_value):
        nonlocal checks
        checks += 1
        return (
            ["R-1: action=reuse требует существующую цель page:sample.list"]
            if checks == 1
            else []
        )

    runtime = PipelineRuntime(
        module_root=tmp_path,
        run_id="run",
        run_path=tmp_path / "run",
        model=object(),
        agent_config=_agent_config(),
        callback=object(),
        metadata={},
    )

    result = runtime.invoke_validated(
        output_model=RequirementAnalysisOutput,
        stage="analysis",
        base_context={"batch": {"requirements": [{"id": "R-1"}]}},
        validator=validator,
    )

    assert result is output
    assert events[0]["event_type"] == "pipeline_stage_validation_failed"
    assert "action=reuse требует существующую цель page:sample.list" in events[0]["message"]
    assert events[0]["data"]["validation_errors"] == [
        "R-1: action=reuse требует существующую цель page:sample.list"
    ]


def test_runtime_keeps_attempt_for_technical_feedback_after_invalid_structure(
    tmp_path: Path, monkeypatch
) -> None:
    from backend.modules.ui_schema import agent_pipeline_runtime
    from backend.modules.ui_schema.agent_pipeline_llm import PipelineStageError

    config = _agent_config()
    config["pipeline"]["stage_attempts"] = 3
    calls: list[dict] = []
    output = RequirementAnalysisOutput(
        items=[
            RequirementAnalysisItem(
                requirement_id="R-1",
                ui_effect="none",
                classification="no_ui",
                ui_outcomes=[],
                reason="Нет наблюдаемого результата интерфейса.",
            )
        ]
    )

    def fake_stage(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise PipelineStageError(
                "Некорректная структура ответа",
                validation_errors=["items.0.reason: обязательное поле отсутствует"],
                previous_output={"items": [{"requirement_id": "R-1"}]},
            )
        return output

    checks = 0

    def validator(_value):
        nonlocal checks
        checks += 1
        if checks == 1:
            return [
                "R-1: цель ui_element:sample.value уже существует, "
                "поэтому action=create недопустим"
            ]
        return []

    monkeypatch.setattr(agent_pipeline_runtime, "invoke_structured_stage", fake_stage)
    monkeypatch.setattr(agent_pipeline_runtime, "append_event", lambda *_args, **_kwargs: None)
    runtime = PipelineRuntime(
        module_root=tmp_path,
        run_id="run",
        run_path=tmp_path / "run",
        model=object(),
        agent_config=config,
        callback=object(),
        metadata={},
    )

    result = runtime.invoke_validated(
        output_model=RequirementAnalysisOutput,
        stage="planning",
        base_context={"batch": {"requirements": [{"id": "R-1"}]}},
        validator=validator,
    )

    assert result is output
    assert len(calls) == 3
    assert [item["attempt_number"] for item in calls] == [1, 2, 3]
    assert all(item["attempt_total"] == 3 for item in calls)
    assert calls[1]["context"]["validation_feedback"] == [
        "items.0.reason: обязательное поле отсутствует"
    ]
    assert calls[2]["context"]["validation_feedback"] == [
        "R-1: цель ui_element:sample.value уже существует, "
        "поэтому action=create недопустим"
    ]


def test_runtime_does_not_reject_explanatory_text_by_language(
    tmp_path: Path, monkeypatch
) -> None:
    from backend.modules.ui_schema import agent_pipeline_runtime

    output = RequirementAnalysisOutput(
        items=[
            RequirementAnalysisItem(
                requirement_id="R-1",
                ui_effect="display",
                classification="direct_ui",
                ui_outcomes=["Поле email and currency term"],
                reason="Existing UI element is sufficient.",
            )
        ]
    )
    calls = 0

    def fake_stage(**_kwargs):
        nonlocal calls
        calls += 1
        return output

    monkeypatch.setattr(agent_pipeline_runtime, "invoke_structured_stage", fake_stage)
    runtime = PipelineRuntime(
        module_root=tmp_path,
        run_id="run",
        run_path=tmp_path / "run",
        model=object(),
        agent_config=_agent_config(),
        callback=object(),
        metadata={},
    )

    result = runtime.invoke_validated(
        output_model=RequirementAnalysisOutput,
        stage="analysis",
        base_context={"batch": {"requirements": [{"id": "R-1"}]}},
        validator=lambda _value: [],
    )

    assert result is output
    assert calls == 1


def test_planning_global_analysis_omits_verbose_outcomes_and_reasons() -> None:
    from backend.modules.ui_schema.agent_pipeline_models import RequirementAnalysisItem
    from backend.modules.ui_schema.agent_pipeline_planning import _compact_global_analysis

    result = _compact_global_analysis(
        [
            RequirementAnalysisItem(
                requirement_id="R-1",
                ui_effect="display",
                classification="direct_ui",
                ui_outcomes=["Длинное описание результата"],
                reason="Длинное обоснование",
            )
        ]
    )

    assert result == [
        {
            "requirement_id": "R-1",
            "ui_effect": "display",
            "classification": "direct_ui",
        }
    ]



def test_pipeline_runs_audit_even_when_previous_time_threshold_would_be_low(
    tmp_path: Path, monkeypatch
) -> None:
    run_path = tmp_path / "run"
    working = run_path / "working" / "ui_schema"
    base = run_path / "base" / "ui_schema"
    shutil.copytree(PROJECT_ROOT / "modules/ui_schema/init", working)
    shutil.copytree(PROJECT_ROOT / "modules/ui_schema/init", base)
    write_json(
        run_path / "input/requirements.json",
        {"requirements": [{"id": "R-1", "name": "Экран результата"}]},
    )
    write_json(run_path / "input/task.json", {"operation": "synchronize"})
    write_json(run_path / "run.json", {"workspace_id": "workspace", "run_id": "run-test"})

    monkeypatch.setattr(agent_pipeline, "create_chat_model", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(PipelineRuntime, "phase", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(PipelineRuntime, "ensure_not_cancelled", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(PipelineRuntime, "event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(PipelineRuntime, "remaining_duration_seconds", lambda _self: 1)

    calls: list[str] = []

    def fake_invoke_validated(self, *, stage, validator, **_kwargs):
        calls.append(stage)
        if stage == "analysis":
            output = RequirementAnalysisOutput(
                items=[
                    RequirementAnalysisItem(
                        requirement_id="R-1",
                        ui_effect="display",
                        classification="direct_ui",
                        ui_outcomes=["Экран результата"],
                        reason="Требование описывает видимый экран.",
                    )
                ]
            )
        elif stage == "planning":
            output = PipelinePlanOutput(
                decisions=[
                    PipelineDecision(
                        requirement_id="R-1",
                        ui_effect="display",
                        classification="direct_ui",
                        targets=[
                            PipelineTarget(
                                target_type="page",
                                target_id="result",
                                action="create",
                                implementation_status="implemented",
                            )
                        ],
                        reason="Создан экран результата.",
                    )
                ],
                changes=PipelineChangeBundle(
                    create_pages=[
                        PipelinePageDocument(
                            page_id="result",
                            title="Result",
                            elements=[],
                        )
                    ]
                ),
            )
        elif stage == "audit":
            output = PipelineAuditOutput()
        else:
            raise AssertionError(f"Unexpected stage: {stage}")
        assert validator(output) == []
        return output

    monkeypatch.setattr(PipelineRuntime, "invoke_validated", fake_invoke_validated)

    result = agent_pipeline.run_managed_pipeline(
        module_root=tmp_path / "module",
        run_id="run-test",
        run_path=run_path,
        llm_settings={},
        agent_config=_agent_config(),
        callback=object(),
    )

    assert calls == ["analysis", "planning", "audit"]
    assert read_json(run_path / "result/audit.json", {})["total_batches"] == 1
    assert read_json(run_path / "result/pipeline_state.json", {})["status"] == "generated"


def test_pipeline_rechecks_once_and_warns_for_remaining_audit_issue(
    tmp_path: Path, monkeypatch
) -> None:
    run_path = tmp_path / "run"
    working = run_path / "working" / "ui_schema"
    base = run_path / "base" / "ui_schema"
    shutil.copytree(PROJECT_ROOT / "modules/ui_schema/init", working)
    shutil.copytree(PROJECT_ROOT / "modules/ui_schema/init", base)
    write_json(
        run_path / "input/requirements.json",
        {"requirements": [{"id": "R-1", "name": "Экран результата"}]},
    )
    write_json(run_path / "input/task.json", {"operation": "synchronize"})
    write_json(run_path / "run.json", {"workspace_id": "workspace", "run_id": "run-test"})

    monkeypatch.setattr(agent_pipeline, "create_chat_model", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(PipelineRuntime, "phase", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(PipelineRuntime, "ensure_not_cancelled", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(PipelineRuntime, "event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(PipelineRuntime, "remaining_duration_seconds", lambda _self: 1)

    calls: list[str] = []
    verification_count = 0
    decision = PipelineDecision(
        requirement_id="R-1",
        ui_effect="display",
        classification="direct_ui",
        targets=[
            PipelineTarget(
                target_type="page",
                target_id="result",
                action="create",
                implementation_status="implemented",
            )
        ],
        reason="Создан экран результата.",
    )
    corrected_decision = PipelineDecision(
        requirement_id="R-1",
        ui_effect="display",
        classification="direct_ui",
        targets=[
            PipelineTarget(
                target_type="page",
                target_id="result",
                action="reuse",
                implementation_status="implemented",
            )
        ],
        reason="Экран результата подтверждён.",
    )

    def fake_invoke_validated(self, *, stage, validator, **_kwargs):
        calls.append(stage)
        if stage == "analysis":
            output = RequirementAnalysisOutput(
                items=[
                    RequirementAnalysisItem(
                        requirement_id="R-1",
                        ui_effect="display",
                        classification="direct_ui",
                        ui_outcomes=["Экран результата"],
                        reason="Требование описывает видимый экран.",
                    )
                ]
            )
        elif stage == "planning":
            output = PipelinePlanOutput(
                decisions=[decision],
                changes=PipelineChangeBundle(
                    create_pages=[
                        PipelinePageDocument(
                            page_id="result",
                            title="Result",
                            elements=[],
                        )
                    ]
                ),
            )
        elif stage == "audit":
            nonlocal verification_count
            is_verification = (
                _kwargs.get("base_context", {}).get("audit_mode")
                == "correction_verification"
            )
            if is_verification:
                verification_count += 1
            if is_verification and verification_count >= 2:
                output = PipelineAuditOutput()
            else:
                output = PipelineAuditOutput(
                    issues=[
                        PipelineAuditIssue(
                            requirement_id="R-1",
                            issue="Нужно перепроверить классификацию.",
                        )
                    ]
                )
        elif stage == "correction":
            output = PipelineCorrectionOutput(
                decisions=[corrected_decision],
                changes=PipelineChangeBundle(
                    no_changes_reason="Текущее решение подтверждено."
                ),
            )
        else:
            raise AssertionError(f"Unexpected stage: {stage}")
        assert validator(output) == []
        return output

    monkeypatch.setattr(PipelineRuntime, "invoke_validated", fake_invoke_validated)

    result = agent_pipeline.run_managed_pipeline(
        module_root=tmp_path / "module",
        run_id="run-test",
        run_path=run_path,
        llm_settings={},
        agent_config=_agent_config(),
        callback=object(),
    )

    assert calls == [
        "analysis",
        "planning",
        "audit",
        "correction",
        "audit",
    ]
    assert read_json(run_path / "result/correction_review_1.json", {})["issues"]
    assert not (run_path / "result/correction_review_2.json").exists()
    assert any("Результат можно проверить вручную" in item for item in result["warnings"])
    assert read_json(run_path / "result/pipeline_state.json", {})["status"] == "generated"

