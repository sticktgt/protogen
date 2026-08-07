from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_ROOT = PROJECT_ROOT / "modules/ui_schema/agent/prompts"
AGENT_INSTRUCTIONS = PROJECT_ROOT / "modules/ui_schema/agent/AGENT_INSTRUCTIONS.md"
PIPELINE_PROMPTS = (
    "pipeline_analysis.md",
    "pipeline_planning.md",
    "pipeline_repair.md",
    "pipeline_audit.md",
    "pipeline_correction.md",
    "pipeline_structural_review.md",
)
CHANGE_RULES = "pipeline_change_rules.md"
OUTPUT_CONTRACT = "pipeline_output_contract.md"


def _read(name: str) -> str:
    return (PROMPT_ROOT / name).read_text(encoding="utf-8")


def test_pipeline_roles_are_separate_and_have_common_runtime_placeholders() -> None:
    prompts = {name: _read(name) for name in PIPELINE_PROMPTS}

    assert "только семантический анализ" in prompts["pipeline_analysis.md"]
    assert "только для требований из `batch.requirements`" in prompts["pipeline_planning.md"]
    assert "отклонённый транзакционный пакет" in prompts["pipeline_repair.md"]
    assert "Верни только реальные дефекты" in prompts["pipeline_audit.md"]
    assert "ID из `required_requirement_ids`" in prompts["pipeline_correction.md"]
    assert "компактную структурную доводку" in prompts["pipeline_structural_review.md"]
    assert "audit_mode=correction_verification" in prompts["pipeline_audit.md"]
    assert "id_container_mismatch" in prompts["pipeline_structural_review.md"]
    assert "self_navigation" in prompts["pipeline_structural_review.md"]
    for text in prompts.values():
        assert "{context_json}" in text
        assert "{validation_errors_json}" in text
        assert "{previous_output_json}" in text
        assert "{output_contract}" in text
    for name in (
        "pipeline_planning.md",
        "pipeline_repair.md",
        "pipeline_correction.md",
        "pipeline_structural_review.md",
    ):
        assert "{change_rules}" in prompts[name]

    contract = _read(OUTPUT_CONTRACT)
    assert "{output_tool_name}" in contract
    assert "{output_schema_json}" in contract
    assert "аргументе `payload`" in contract


def test_pipeline_prompts_do_not_delegate_stage_or_tool_selection_to_model() -> None:
    combined = "\n".join(_read(name) for name in PIPELINE_PROMPTS)

    assert "Backend сам выбрал этап" in combined
    for legacy in (
        "write_ui_schema_coverage_plan_batch",
        "review_ui_schema_coverage_plan",
        "write_ui_schema_traceability_batch",
        "review_ui_schema_traceability",
        "finalize_ui_schema_changes",
    ):
        assert legacy not in combined


def test_change_rules_are_single_source_for_schema_mutations() -> None:
    rules = _read(CHANGE_RULES)
    planning = _read("pipeline_planning.md")
    repair = _read("pipeline_repair.md")
    correction = _read("pipeline_correction.md")
    structural = _read("pipeline_structural_review.md")

    assert "По умолчанию сохраняй существующие страницы, элементы и их иерархию" in rules
    assert "Не перемещай существующий элемент только ради" in rules
    assert "Вложенные `children` нового контейнера" in rules
    assert "Исправляй сразу весь список ошибок" in rules
    assert "Смена родителя существующего элемента допустима только через `move_elements`" in rules
    assert "цель уже существует" in rules
    assert "не повторяй `action=create`" in rules
    assert "элемент с `link_source: true`" in rules
    assert "тип `table_column`, а не `text`" in rules
    assert "корне допустимы только типы с `root_allowed`" in rules
    assert "может иметь пустые цели" in rules
    assert "{change_rules}" in planning
    assert "{change_rules}" in repair
    assert "{change_rules}" in correction
    assert "{change_rules}" in structural


def test_planning_and_repair_prefer_stable_minimal_prototype() -> None:
    planning = _read("pipeline_planning.md")
    repair = _read("pipeline_repair.md")

    assert "минимально достаточный `changes`-пакет" in planning
    assert "не перестраивай страницу" in planning
    assert "не переноси поля ради композиционной аккуратности" in planning
    assert "не добавляй `move_elements` автоматически" in repair
    assert "оставить существующий элемент у текущего родителя" in repair
    assert "Исправь каждый перечисленный дефект" in repair
    assert "`technical_index`" in planning
    assert "`technical_issues`" in repair
    assert "локальную `ui_schema`" in repair


def test_audit_is_issue_only_and_correction_is_targeted() -> None:
    audit = _read("pipeline_audit.md")
    correction = _read("pipeline_correction.md")

    assert "не переписывай все решения" in audit
    assert "Для корректного решения ничего не возвращай" in audit
    assert "Не перегенерируй остальные решения" in correction
    assert "только этот пакет" in correction
    assert "проверь всё поддерево и связи" in correction
    assert "Не создавай второй элемент с тем же назначением" in correction


def test_model_tasks_are_kept_in_prompt_files_and_pipeline_parameters_in_config() -> None:
    config = yaml.safe_load(
        (PROJECT_ROOT / "modules/ui_schema/config.yaml").read_text(encoding="utf-8")
    )["agent"]
    instructions = AGENT_INSTRUCTIONS.read_text(encoding="utf-8")

    assert set(config["prompts"]) >= {
        "pipeline_analysis",
        "pipeline_planning",
        "pipeline_repair",
        "pipeline_audit",
        "pipeline_correction",
        "pipeline_structural_review",
        "pipeline_output_contract",
        "pipeline_change_rules",
    }
    assert config["pipeline"]["change_rules_prompt"] == "pipeline_change_rules"
    assert set(config["pipeline"]["stages"]) == {
        "analysis",
        "planning",
        "repair",
        "audit",
        "correction",
        "structural_review",
    }
    assert "pipeline_change_rules.md" in instructions
    assert "config.yaml" in instructions


def test_pipeline_batches_are_bounded_for_small_models() -> None:
    config = yaml.safe_load(
        (PROJECT_ROOT / "modules/ui_schema/config.yaml").read_text(encoding="utf-8")
    )["agent"]["pipeline"]

    assert config["planning_batch_size"] == 12
    assert config["correction_batch_size"] == 12
    assert config["stage_attempts"] == 3
    assert config["apply_repair_attempts"] == 3
    assert config["correction_rounds"] == 1
    assert config["structural_review_candidate_limit"] == 24


def test_runtime_prompts_are_bounded_and_domain_neutral() -> None:
    names = (*PIPELINE_PROMPTS, CHANGE_RULES)
    combined = "\n".join(_read(name) for name in names).lower()

    assert all(len(_read(name)) < 5000 for name in names)
    import re

    for value in ("карта клиента", "выписка по счёту", "банк", "кредит", "вклад"):
        assert re.search(rf"(?<![а-яё]){re.escape(value)}(?![а-яё])", combined) is None


def test_output_contract_prefers_clear_russian_without_forced_translation() -> None:
    contract = _read(OUTPUT_CONTRACT)

    assert "по возможности пиши кратко и понятно по-русски" in contract
    assert "Допустимы общеупотребительные английские термины" in contract
    assert "не переводи их механически" in contract
    assert "полностью по-русски" not in contract
