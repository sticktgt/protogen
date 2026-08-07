from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.ui_schema.agent_change_bundle import (
    UiSchemaChangeBundleArgs,
    apply_ui_schema_change_bundle,
    change_bundle_limits,
)
from backend.modules.ui_schema.agent_completion import validate_and_mark_completion
from backend.modules.ui_schema.agent_context import build_synchronization_context
from backend.modules.ui_schema.agent_coverage_plan import (
    CoveragePlanBatchWriteArgs,
    CoveragePlanItem,
    CoveragePlanRevisionArgs,
    require_coverage_plan,
    revise_coverage_plan_items,
    schema_change_plan_context,
    write_coverage_plan_batch,
)
from backend.modules.ui_schema.agent_coverage_plan_review import (
    CoveragePlanReviewArgs,
    auto_complete_empty_coverage_review,
    build_coverage_plan_review_context,
    review_coverage_plan,
)
from backend.modules.ui_schema.agent_coverage_plan_targets import build_coverage_plan_target_report
from backend.modules.ui_schema.agent_coverage_plan_execution import (
    build_coverage_plan_execution_report,
    finalize_coverage_plan_execution,
    invalidate_coverage_plan_execution,
)
from backend.modules.ui_schema.agent_element_batch_tools import (
    PageElementChange,
    PageElementMove,
    element_batch_limit,
)
from backend.modules.ui_schema.agent_object_cleanup import remove_schema_objects
from backend.modules.ui_schema.agent_page_tools import PageDocumentArgs, page_element_limit
from backend.modules.ui_schema.agent_preservation import (
    delete_new_elements,
    normalize_element_ids,
)
from backend.modules.ui_schema.agent_review_batches import (
    build_review_batches,
    next_review_batch_id,
    public_review_batch_context,
)
from backend.modules.ui_schema.agent_requirement_batches import (
    configured_requirement_fields,
)
from backend.modules.ui_schema.agent_repair_validation import (
    run_mutation_with_optional_revalidation,
)
from backend.modules.ui_schema.agent_schema_io import delete_page_file, recoverable_tool_result
from backend.modules.ui_schema.files import read_json
from backend.modules.ui_schema.agent_tool_payloads import decode_json_argument
from backend.modules.ui_schema.agent_traceability_dirty import (
    mark_traceability_targets_dirty,
)
from backend.modules.ui_schema.agent_traceability_correction import (
    build_traceability_correction_context,
    dirty_requirement_ids,
)
from backend.modules.ui_schema.agent_traceability_models import TraceabilityWriteArgs
from backend.modules.ui_schema.agent_requirement_decisions import TraceabilityItem
from backend.modules.ui_schema.agent_traceability_batches import write_traceability_batch
from backend.modules.ui_schema.agent_traceability_review import (
    TraceabilityReviewArgs,
    review_traceability,
)
from backend.modules.ui_schema.agent_workflow_context import build_current_workflow_context


class RemoveSchemaObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["page", "ui_element"]
    target_id: str = Field(description="Exact existing page or UI element ID")
    reason: str = Field(
        description="Concrete reason why the object is obsolete, duplicated or replaced"
    )
    requirement_ids: list[str] = Field(
        default_factory=list,
        description="Current requirement IDs that support the removal",
    )


class RemoveSchemaObjectsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    removals: list[RemoveSchemaObject] = Field(
        min_length=1,
        max_length=30,
        description="Explicit deletions. Omission from a bundle never means deletion.",
    )


class DeleteElementsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_ids: list[str] | str = Field(
        description=(
            "IDs of elements created during the current run. Existing base elements are "
            "protected. A valid JSON-encoded list is accepted for compatibility."
        )
    )
    reason: str = Field(description="Why these newly generated elements must be removed")


def create_agent_tools(*, run_path: Path, agent_config: dict[str, Any]):
    from langchain.tools import tool

    working_root = run_path / "working" / "ui_schema"
    base_root = run_path / "base" / "ui_schema"
    result_root = run_path / "result"
    maximum_page_elements = page_element_limit(agent_config)
    maximum_element_changes = element_batch_limit(agent_config)
    bundle_limits = change_bundle_limits(agent_config)
    context_loaded = False

    execution_config = (
        agent_config.get("execution", {}) if isinstance(agent_config, dict) else {}
    )
    execution_config = execution_config if isinstance(execution_config, dict) else {}
    validate_after_traceability = bool(
        execution_config.get("validate_after_traceability", True)
    )
    validate_after_repair_write = bool(
        execution_config.get("validate_after_repair_write", True)
    )

    def workflow_context() -> dict[str, Any]:
        return build_current_workflow_context(run_path, agent_config=agent_config)

    def stage_result(operation: Callable[[], dict[str, Any]]) -> str:
        return recoverable_tool_result(operation, recovery_context=workflow_context)

    def mutation_result(
        tool_name: str,
        operation: Callable[[], dict[str, Any]],
    ) -> str:
        def mutation_recovery_context() -> dict[str, Any]:
            context = workflow_context()
            context["rejected_mutation"] = {
                "tool": tool_name,
                "transaction_rolled_back": True,
                "retry_scope": (
                    "Resend one complete corrected transactional bundle. Do not send only a "
                    "fragment that depends on pages or elements from the rejected bundle."
                ),
            }
            return context

        return recoverable_tool_result(
            lambda: run_mutation_with_optional_revalidation(
                run_path=run_path,
                operation=operation,
                enabled=validate_after_repair_write,
                completed_by=f"{tool_name}:repair_validation",
            ),
            recovery_context=mutation_recovery_context,
        )

    @tool
    def load_synchronization_context() -> str:
        """Load the complete synchronization input once per run."""
        nonlocal context_loaded
        if context_loaded:
            return json.dumps(
                {
                    "ok": False,
                    "code": "context_already_loaded",
                    "error": (
                        "Synchronization context was already loaded in this run. "
                        "Use the existing context and latest validation result."
                    ),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        context = build_synchronization_context(run_path, agent_config=agent_config)
        context_loaded = True
        return json.dumps(context, ensure_ascii=False, separators=(",", ":"))

    @tool(args_schema=CoveragePlanBatchWriteArgs)
    def write_ui_schema_coverage_plan_batch(
        items: list[CoveragePlanItem],
        agent_note: str = "",
    ) -> str:
        """Record decisions for unresolved requirements in the current coverage-plan batch.

        The backend infers the current batch. Valid submitted items are preserved and any
        unresolved or technically inconsistent items are returned with bounded context.
        """
        def operation() -> dict[str, Any]:
            result = write_coverage_plan_batch(
                run_path,
                agent_config=agent_config,
                items=items,
                agent_note=agent_note,
            )
            if result.get("batches_complete"):
                context = build_coverage_plan_review_context(
                    run_path,
                    agent_config=agent_config,
                )
                if int(context.get("candidate_count", 0)) == 0:
                    auto_complete_empty_coverage_review(
                        run_path,
                        agent_config=agent_config,
                    )
                    result["review_complete"] = True
                    result["schema_change_plan"] = schema_change_plan_context(run_path)
                    result["next_action"] = "apply_schema_changes"
                else:
                    from backend.modules.ui_schema.files import write_json
                    review_batches = build_review_batches(
                        context,
                        agent_config=agent_config,
                        prefix="coverage_review",
                    )
                    first_review_id = next_review_batch_id(
                        review_batches,
                        completed_batch_ids=set(),
                    )
                    write_json(run_path / "result" / "coverage_plan_review_pending.json", context)
                    result["quality_review_context"] = public_review_batch_context(
                        context,
                        batches=review_batches,
                        review_batch_id=str(first_review_id),
                        completed_batch_ids=set(),
                    )
                    result["review_complete"] = False
            return result

        return stage_result(operation)

    @tool(args_schema=CoveragePlanReviewArgs)
    def review_ui_schema_coverage_plan(
        items: list[CoveragePlanItem],
        agent_note: str = "",
    ) -> str:
        """Review unresolved candidates in the current blind coverage-review group."""
        return stage_result(
            lambda: review_coverage_plan(
                run_path,
                agent_config=agent_config,
                items=items,
                agent_note=agent_note,
            )
        )

    @tool(args_schema=UiSchemaChangeBundleArgs)
    def apply_ui_schema_changes(
        create_pages: list[PageDocumentArgs] | None = None,
        upsert_elements: list[PageElementChange] | None = None,
        move_elements: list[PageElementMove] | None = None,
        ui_links: list[dict[str, Any]] | None = None,
        no_changes_reason: str = "",
    ) -> str:
        """Apply one coherent transactional change set across app.json and pages."""

        def operation() -> dict[str, Any]:
            require_coverage_plan(run_path, agent_config=agent_config)
            result = apply_ui_schema_change_bundle(
                working_root=working_root,
                result_root=result_root,
                create_pages=list(create_pages or []),
                upsert_elements=list(upsert_elements or []),
                move_elements=list(move_elements or []),
                ui_links=list(ui_links or []),
                no_changes_reason=no_changes_reason,
                maximum_pages=bundle_limits["pages"],
                maximum_top_level_elements=maximum_page_elements,
                maximum_element_changes=maximum_element_changes,
                maximum_moves=bundle_limits["moves"],
                maximum_links=bundle_limits["links"],
            )
            invalidate_coverage_plan_execution(run_path)
            affected = mark_traceability_targets_dirty(
                run_path, result.get("touched_target_ids", [])
            )
            if affected:
                result["traceability_recheck_requirement_ids"] = affected
            execution = build_coverage_plan_execution_report(
                run_path,
                agent_config=agent_config,
            )
            result["coverage_plan_execution"] = {
                "checked_target_count": int(execution.get("checked_target_count", 0)),
                "gap_count": int(execution.get("gap_count", 0)),
                "gaps": list(execution.get("gaps", [])),
                "observation_count": int(execution.get("observation_count", 0)),
                "observations": list(execution.get("observations", [])),
            }
            trace_state = read_json(result_root / "traceability_state.json", {})
            if affected and bool(trace_state.get("initial_batches_complete")) and execution.get("complete"):
                result["traceability_correction_context"] = build_traceability_correction_context(
                    run_path,
                    agent_config=agent_config,
                    requirement_ids=affected,
                )
                result["preserve_next_action_after_validation"] = True
                result["next_action"] = "rewrite_dirty_traceability_items"
            else:
                result["next_action"] = "continue_schema_changes_or_finalize"
            return result

        return mutation_result("apply_ui_schema_changes", operation)

    @tool
    def finalize_ui_schema_changes() -> str:
        """Finalize when planned create targets exist; structural observations remain for review."""
        def operation() -> dict[str, Any]:
            result = finalize_coverage_plan_execution(
                run_path,
                agent_config=agent_config,
            )
            if result.get("complete"):
                trace_state = read_json(result_root / "traceability_state.json", {})
                if bool(trace_state.get("initial_batches_complete")):
                    dirty_ids = dirty_requirement_ids(run_path)
                    if dirty_ids:
                        result["traceability_correction_context"] = build_traceability_correction_context(
                            run_path,
                            agent_config=agent_config,
                            requirement_ids=dirty_ids,
                        )
                        result["next_action"] = "rewrite_dirty_traceability_items"
                    elif bool(trace_state.get("review_complete")):
                        validation = validate_and_mark_completion(
                            run_path,
                            completed_by="finalize_ui_schema_changes:post_traceability",
                        )
                        result.update(validation)
                        result["completed"] = bool(validation.get("valid"))
                        result["next_action"] = (
                            "stop" if validation.get("valid") else "fix_errors_and_continue"
                        )
                    else:
                        result["next_action"] = "continue_traceability_review"
                else:
                    current = workflow_context()
                    result["current_requirement_batch_context"] = current.get(
                        "current_requirement_batch_context"
                    )
                    result["next_action"] = current.get(
                        "next_action", "write_ui_schema_traceability_batch"
                    )
            return result

        return stage_result(operation)

    @tool(args_schema=CoveragePlanRevisionArgs)
    def revise_ui_schema_coverage_plan(
        items: list[CoveragePlanItem],
        reason: str,
    ) -> str:
        """Explicitly revise only plan items whose planned action or target is no longer correct."""
        def operation() -> dict[str, Any]:
            result = revise_coverage_plan_items(
                run_path,
                items=items,
                reason=reason,
            )
            target_report = build_coverage_plan_target_report(run_path)
            result["coverage_plan_target_validation"] = target_report
            if not target_report.get("complete"):
                result["next_action"] = "revise_invalid_coverage_plan_targets"
                return result
            execution = build_coverage_plan_execution_report(
                run_path,
                agent_config=agent_config,
            )
            result["coverage_plan_execution"] = {
                "gap_count": int(execution.get("gap_count", 0)),
                "gaps": list(execution.get("gaps", [])),
                "observation_count": int(execution.get("observation_count", 0)),
                "observations": list(execution.get("observations", [])),
            }
            result["next_action"] = (
                "finalize_ui_schema_changes"
                if execution.get("complete")
                else "apply_schema_changes_or_finalize_again"
            )
            return result

        return stage_result(operation)

    @tool(args_schema=TraceabilityWriteArgs)
    def write_ui_schema_traceability_batch(
        items: list[TraceabilityItem] | None = None,
        agent_note: str = "",
        warnings: list[str] | None = None,
    ) -> str:
        """Write final decisions for unresolved requirements in the current traceability stage."""
        return stage_result(
            lambda: write_traceability_batch(
                run_path=run_path,
                working_root=working_root,
                result_root=result_root,
                agent_config=agent_config,
                items=list(items or []),
                agent_note=agent_note,
                warnings=list(warnings or []),
                validate_after_write=validate_after_traceability,
            )
        )

    @tool(args_schema=TraceabilityReviewArgs)
    def review_ui_schema_traceability(
        items: list[TraceabilityItem],
        agent_note: str = "",
    ) -> str:
        """Review unresolved candidates in the current blind traceability-review group."""
        return stage_result(
            lambda: review_traceability(
                run_path,
                working_root=working_root,
                result_root=result_root,
                agent_config=agent_config,
                items=items,
                agent_note=agent_note,
            )
        )

    @tool(args_schema=RemoveSchemaObjectsArgs)
    def remove_ui_schema_objects(removals: list[RemoveSchemaObject]) -> str:
        """Explicitly remove obsolete existing pages or UI elements."""
        return mutation_result(
            "remove_ui_schema_objects",
            lambda: remove_schema_objects(
                run_path=run_path,
                removals=[_plain_model_value(item) for item in removals],
            ),
        )

    @tool
    def delete_ui_schema_page_file(file_path: str) -> str:
        """Delete a page created during this run; base pages are protected."""
        return mutation_result(
            "delete_ui_schema_page_file",
            lambda: delete_page_file(
                working_root=working_root,
                base_root=base_root,
                file_path=file_path,
            ),
        )

    @tool(args_schema=DeleteElementsArgs)
    def delete_ui_schema_elements(element_ids: list[str] | str, reason: str) -> str:
        """Delete invalid elements created during this run only."""
        return mutation_result(
            "delete_ui_schema_elements",
            lambda: delete_new_elements(
                base_root=base_root,
                working_root=working_root,
                element_ids=normalize_element_ids(
                    decode_json_argument(element_ids, label="element_ids")
                ),
                reason=reason,
            ),
        )

    @tool
    def validate_ui_schema_state() -> str:
        """Normalize and validate the temporary UI schema."""
        validation = validate_and_mark_completion(run_path)
        return json.dumps(
            {
                **validation,
                "completed": bool(validation.get("valid")),
                "next_action": (
                    "stop" if validation.get("valid") else "fix_errors_and_validate_again"
                ),
            },
            ensure_ascii=False,
        )

    return [
        load_synchronization_context,
        write_ui_schema_coverage_plan_batch,
        review_ui_schema_coverage_plan,
        apply_ui_schema_changes,
        finalize_ui_schema_changes,
        revise_ui_schema_coverage_plan,
        write_ui_schema_traceability_batch,
        review_ui_schema_traceability,
        remove_ui_schema_objects,
        delete_ui_schema_page_file,
        delete_ui_schema_elements,
        validate_ui_schema_state,
    ]


def _plain_model_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True)
    if isinstance(value, list):
        return [_plain_model_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain_model_value(item) for key, item in value.items()}
    return value
