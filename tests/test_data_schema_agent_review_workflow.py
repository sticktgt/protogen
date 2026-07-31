from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "modules/data_schema/config.yaml"
PROMPTS_ROOT = PROJECT_ROOT / "modules/data_schema/agent/prompts"


def _agent_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["agent"]


def _source(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


def _prompt(name: str) -> str:
    return (PROMPTS_ROOT / name).read_text(encoding="utf-8")


def test_direct_workflow_has_bounded_quality_gate() -> None:
    config = _agent_config()
    execution = config["execution"]
    review = config["semantic_review"]

    assert execution["max_llm_calls"] == 18
    assert execution["max_tool_calls"] == 28
    assert execution["max_total_tokens"] == 600000
    assert execution["max_duration_seconds"] == 1200
    assert review["enabled"] is True
    assert review["max_correction_rounds"] == 3
    assert "correction_max_repeated_tool_calls" not in review
    assert review["max_issues"] == 5
    assert config["llm"]["max_retries"] == 0
    assert config["llm"]["reasoning_effort"]["ollama-cloud"] == {
        "generation": "none",
        "correction": "none",
        "review": "low",
        "connection": "none",
    }
    assert config["llm"]["reasoning_effort_by_model"]["ollama-cloud"] == {
        "qwen3.5:397b": {"generation": "low"}
    }
    assert "generation" not in config


def test_runner_uses_direct_generation_and_bounded_semantic_review() -> None:
    runner = _source("backend/modules/data_schema/agent_runner.py")

    assert runner.count("create_data_schema_agent(") == 1
    assert 'role="primary"' not in runner
    assert 'role="correction"' not in runner
    assert "render_run_prompt(agent_config, run)" in runner
    assert "validate_with_retry(" in runner
    assert "review_and_correct_semantics(" in runner
    assert "finalize_preview(" in runner
    assert "build_generation_plan(" not in runner
    assert "build_concept_mappings(" not in runner
    assert "build_traceability_results(" not in runner


def test_factory_has_one_primary_agent_and_structured_correction_invocation() -> None:
    factory = _source("backend/modules/data_schema/agent_factory.py")

    assert '"load_synchronization_context"' in factory
    assert '"write_data_schema_traceability"' in factory
    assert '"patch_data_schema_requirement_results"' not in factory
    assert "record_data_schema_concept_mappings" not in factory
    assert "validate_data_schema_structure" not in factory
    assert "schema_system" not in factory
    assert "traceability_system" not in factory
    assert "sequential_tool_calls_supported," in factory
    assert "enabled=sequential_tool_calls_supported(" in factory
    assert 'profile="generation"' in factory

    review_invocation = _source(
        "backend/modules/data_schema/agent_semantic_invocation.py"
    )
    correction_invocation = _source(
        "backend/modules/data_schema/agent_semantic_correction_invocation.py"
    )
    assert 'profile="review"' in review_invocation
    assert 'profile="correction"' in correction_invocation
    assert "submit_data_schema_semantic_correction" in correction_invocation


def test_primary_prompt_improves_generation_without_extra_stage() -> None:
    system = _prompt("system.md")
    task = _prompt("run.md")

    assert "Один раз вызови `load_synchronization_context`" in task
    assert "write_data_schema_dictionaries" in task
    assert "write_data_schema_core" in task
    assert "write_data_schema_relations" in task
    assert "write_data_schema_traceability" in task
    assert "Ровно один раз" in task
    assert "validate_data_schema_state" in task
    assert "без отдельного tool call" in task
    assert "не создавай отдельные generation plan" in task.lower()
    assert "Финальный самоконтроль" in system
    assert "Requirement links не компенсируют" in system
    assert "ровно один необходимый tool call" in system


def test_quality_gate_has_two_focused_reviews_and_bounded_recovery() -> None:
    review_source = _source("backend/modules/data_schema/agent_semantic_review.py")
    workflow_source = _source(
        "backend/modules/data_schema/agent_semantic_correction_workflow.py"
    )

    assert 'scope="coverage"' in review_source
    assert 'scope="consistency"' in review_source
    assert "run_semantic_correction_rounds(" in review_source
    assert '"review_kind": "combined"' in review_source
    assert "range(1, maximum_rounds + 1)" in workflow_source
    assert "_remaining_blockers_review(" in workflow_source
    assert 'issue.get("disposition") == "must_fix"' in workflow_source
    assert 'review_id = f"verification_{verification_number}"' in workflow_source

    correction_source = _source(
        "backend/modules/data_schema/agent_semantic_correction.py"
    )
    assert correction_source.count("def apply_semantic_correction(") == 1
    assert "invoke_semantic_correction_plan(" in correction_source
    assert "apply_semantic_correction_plan(" in correction_source
    correction_context = _source(
        "backend/modules/data_schema/agent_review_correction_context.py"
    )
    assert '"candidate_schema_catalog"' in correction_context


def test_semantic_context_is_focused_and_excludes_obsolete_artifacts() -> None:
    source = _source("backend/modules/data_schema/agent_semantic_context.py")

    assert 'ReviewScope = Literal["coverage", "consistency"]' in source
    assert 'include_traceability = review_scope == "coverage"' in source
    assert '"generation_plan"' not in source
    assert '"concept_mappings"' not in source
    assert '"change_statistics"' not in source
    assert '"coverage_expectations"' not in source
    assert '"candidate_data_schema"' in source
    assert '"requirement_assessments"' in source
    assert "group_requirements_by_current_result" in source


def test_semantic_prompts_use_practical_quality_threshold() -> None:
    common = _prompt("semantic_review_system.md")
    coverage = _prompt("semantic_coverage_review.md")
    consistency = _prompt("semantic_consistency_review.md")

    assert "Цель — получить применимый прототип" in common
    assert "Если сомневаешься между `must_fix` и `advisory`" in common
    assert "Неверная classification" in common
    assert "дополнительной связи" in common
    assert "не должны блокировать результат" in common
    assert "Отсутствующая relation" in common
    assert "ошибочная `no_data`" in coverage
    assert "являются `advisory`" in coverage
    assert "существенный повторяемый объект" in coverage
    assert "не повышай проблему до `must_fix`" in coverage.lower()
    assert "Отсутствующая relation" in consistency
    assert "это `advisory`" in consistency
    assert "Не требуй идеальной нормализации" in common
    assert "Произвольные дополнительные поля" in common


def test_correction_attempts_all_concrete_review_issues() -> None:
    system = _prompt("semantic_correction_system.md")
    task = _prompt("semantic_correction.md")
    verification = _prompt("semantic_verification.md")

    assert "`correction_round=1`" in system
    assert "`correction_round>1`" in system
    assert "только blockers" in system
    assert "submit_data_schema_semantic_correction" in system
    assert "единственный вызов" in task
    assert "раундах 2 и далее" in task
    assert "только переданные оставшиеся blockers" in task
    assert "expected_issue_ids" in verification
    assert "advisory не блокирует применение" in verification
    assert "следующего точечного recovery-раунда" in verification
    assert "ID-only patch" in system
    assert "локальный `id`" in system


def test_limit_boundary_requires_completed_semantic_review() -> None:
    source = _source("backend/modules/data_schema/agent_execution.py")

    assert "review_approved" in source
    assert 'review.get("coverage_complete") is True' in source
    assert 'not review.get("correction_pending")' in source
    assert 'not run.get("apply_blocked")' in source
    assert "технической и смысловой проверки" in source


def test_diagnostics_describe_direct_workflow_and_quality_gate() -> None:
    source = _source("backend/modules/data_schema/agent_diagnostics.py")

    assert "single_agent_schema_and_direct_traceability" in source
    assert (
        '"verification": "technical_validation_plus_two_focused_semantic_reviews_and_bounded_structured_recovery"'
        in source
    )


def test_prompts_are_domain_independent() -> None:
    combined = "\n".join(
        _prompt(name)
        for name in (
            "system.md",
            "run.md",
            "semantic_review_system.md",
            "semantic_coverage_review.md",
            "semantic_consistency_review.md",
            "semantic_correction.md",
            "semantic_verification.md",
        )
    ).lower()
    for term in ("банк", "кредит", "вклад", "карта", "клиент"):
        assert term not in combined


def test_advisory_issue_enters_correction_workflow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.modules.data_schema import agent_semantic_review as workflow

    root = tmp_path / "run"
    (root / "result").mkdir(parents=True)
    calls: list[str] = []

    def focused_review(*, scope: str, **kwargs):
        calls.append(scope)
        issues = []
        if scope == "coverage":
            issues = [
                {
                    "id": "coverage_1_issue_1",
                    "disposition": "advisory",
                    "category": "traceability",
                    "message": "Небольшой конкретный дефект",
                    "recommendation": "Исправить ссылку",
                    "requirement_ids": ["REQ-1"],
                    "targets": ["entity:item"],
                }
            ]
        return {
            "status": "approved",
            "decision": "approve",
            "blocking": False,
            "review_id": f"{scope}_1",
            "review_kind": scope,
            "coverage_complete": True,
            "verified_issue_ids": [],
            "summary": f"{scope} проверено.",
            "review_note": "",
            "strengths": [],
            "issue_counts": {"must_fix": 0, "advisory": len(issues)},
            "issues": issues,
        }

    def correction_workflow(**kwargs):
        calls.append("correction_workflow")
        return kwargs["validation"], {
            "status": "approved",
            "decision": "approve",
            "blocking": False,
            "review_id": "verification_1",
            "review_kind": "correction_verification",
            "coverage_complete": True,
            "verified_issue_ids": ["coverage_1_issue_1"],
            "summary": "Исправление проверено.",
            "review_note": "",
            "strengths": [],
            "issue_counts": {"must_fix": 0, "advisory": 0},
            "issues": [],
        }

    monkeypatch.setattr(workflow, "_run_focused_review", focused_review)
    monkeypatch.setattr(workflow, "run_semantic_correction_rounds", correction_workflow)
    monkeypatch.setattr(workflow, "record_review_completion", lambda **kwargs: None)
    monkeypatch.setattr(workflow, "is_cancelled", lambda *args: False)

    validation, review = workflow.review_and_correct_semantics(
        root=root,
        module_root=tmp_path / "module",
        run_id="run_test",
        validation={"valid": True, "errors": [], "warnings": []},
        llm_settings={},
        agent_config={"semantic_review": {"enabled": True}},
    )

    assert validation["valid"] is True
    assert review["review_kind"] == "correction_verification"
    assert calls == ["coverage", "consistency", "correction_workflow"]


def test_correction_workflow_runs_targeted_recovery_for_remaining_blockers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.modules.data_schema import agent_semantic_correction_workflow as workflow

    root = tmp_path / "run"
    (root / "result").mkdir(parents=True)
    correction_sources: list[tuple[int, list[str]]] = []
    verification_rounds: list[int] = []

    source_review = {
        "status": "needs_revision",
        "decision": "revise",
        "blocking": True,
        "review_id": "combined_1",
        "review_kind": "combined",
        "coverage_complete": True,
        "summary": "Найдены issues.",
        "issue_counts": {"must_fix": 1, "advisory": 1},
        "issues": [
            {
                "id": "combined_issue_blocker",
                "disposition": "must_fix",
                "category": "missing_core_data",
                "message": "Нет основной структуры",
                "recommendation": "Добавить структуру",
                "requirement_ids": ["REQ-1"],
                "targets": [],
            },
            {
                "id": "combined_issue_advisory",
                "disposition": "advisory",
                "category": "traceability",
                "message": "Неполная ссылка",
                "recommendation": "Обновить ссылку",
                "requirement_ids": ["REQ-2"],
                "targets": [],
            },
        ],
        "source_reviews": [],
    }

    def correction(*, review, correction_round, **kwargs):
        correction_sources.append(
            (
                correction_round,
                [str(issue["disposition"]) for issue in review["issues"]],
            )
        )
        return {
            "valid": True,
            "errors": [],
            "warnings": [],
            "correction_applied": True,
        }

    def verification(*, verification_number, **kwargs):
        verification_rounds.append(verification_number)
        if verification_number == 1:
            return {
                "status": "needs_revision",
                "decision": "revise",
                "blocking": True,
                "review_id": "verification_1",
                "review_kind": "correction_verification",
                "coverage_complete": True,
                "summary": "Остался один blocker.",
                "issue_counts": {"must_fix": 1, "advisory": 1},
                "issues": [
                    {
                        "id": "verification_1_issue_1",
                        "disposition": "must_fix",
                        "category": "missing_core_data",
                        "message": "Остался blocker",
                        "recommendation": "Добавить одно поле",
                        "requirement_ids": ["REQ-1"],
                        "targets": ["entity:item"],
                    },
                    {
                        "id": "verification_1_issue_2",
                        "disposition": "advisory",
                        "category": "cleanup",
                        "message": "Можно очистить",
                        "recommendation": "Удалить лишнее поле",
                        "requirement_ids": [],
                        "targets": ["field:item.legacy"],
                    },
                ],
                "source_reviews": [],
            }
        return {
            "status": "approved",
            "decision": "approve",
            "blocking": False,
            "review_id": "verification_2",
            "review_kind": "correction_verification",
            "coverage_complete": True,
            "summary": "Blocker исправлен.",
            "issue_counts": {"must_fix": 0, "advisory": 0},
            "issues": [],
            "source_reviews": [],
        }

    monkeypatch.setattr(workflow, "apply_semantic_correction", correction)
    monkeypatch.setattr(workflow, "_run_correction_verification", verification)
    monkeypatch.setattr(workflow, "update_run", lambda *args, **kwargs: {})
    monkeypatch.setattr(workflow, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(workflow, "is_cancelled", lambda *args: False)

    validation, review = workflow.run_semantic_correction_rounds(
        root=root,
        module_root=tmp_path / "module",
        run_id="run_recovery",
        validation={"valid": True, "errors": [], "warnings": []},
        source_review=source_review,
        llm_settings={},
        agent_config={"semantic_review": {"max_correction_rounds": 3}},
    )

    assert validation["valid"] is True
    assert review["blocking"] is False
    assert correction_sources == [
        (1, ["must_fix", "advisory"]),
        (2, ["must_fix"]),
    ]
    assert verification_rounds == [1, 2]


def test_failed_correction_application_skips_llm_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.modules.data_schema import agent_semantic_correction_workflow as workflow

    root = tmp_path / "run"
    (root / "result").mkdir(parents=True)
    calls: list[str] = []
    source_review = {
        "status": "needs_revision",
        "decision": "revise",
        "blocking": True,
        "review_id": "combined_1",
        "review_kind": "combined",
        "coverage_complete": True,
        "summary": "Найден дефект.",
        "issue_counts": {"must_fix": 1, "advisory": 0},
        "issues": [
            {
                "id": "combined_issue_1",
                "disposition": "must_fix",
                "category": "coverage",
                "message": "Нужно исправление",
                "recommendation": "Исправить",
                "requirement_ids": ["REQ-1"],
                "targets": [],
            }
        ],
        "source_reviews": [],
    }

    def correction(**kwargs):
        calls.append("correction")
        return {
            "valid": True,
            "errors": [],
            "warnings": [],
            "correction_applied": False,
            "correction_error": "unknown dictionary_id 'planned_dictionary'",
        }

    def verification(**kwargs):
        calls.append("verification")
        raise AssertionError("verification must not run after technical rollback")

    monkeypatch.setattr(workflow, "apply_semantic_correction", correction)
    monkeypatch.setattr(workflow, "_run_correction_verification", verification)
    monkeypatch.setattr(workflow, "record_review_completion", lambda **kwargs: None)
    monkeypatch.setattr(workflow, "update_run", lambda *args, **kwargs: {})
    monkeypatch.setattr(workflow, "is_cancelled", lambda *args: False)

    validation, review = workflow.run_semantic_correction_rounds(
        root=root,
        module_root=tmp_path / "module",
        run_id="run_failed_plan",
        validation={"valid": True, "errors": [], "warnings": []},
        source_review=source_review,
        llm_settings={},
        agent_config={"semantic_review": {"max_correction_rounds": 3}},
    )

    assert validation["correction_applied"] is False
    assert review["review_kind"] == "correction_application"
    assert review["blocking"] is True
    assert "unknown dictionary_id" in review["summary"]
    assert calls == ["correction"]
