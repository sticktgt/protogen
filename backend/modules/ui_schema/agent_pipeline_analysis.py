from __future__ import annotations

from typing import Any

from backend.modules.ui_schema.agent_pipeline_context import common_context, fixed_batches
from backend.modules.ui_schema.agent_pipeline_models import (
    RequirementAnalysisItem,
    RequirementAnalysisOutput,
)
from backend.modules.ui_schema.agent_pipeline_runtime import PipelineRuntime
from backend.modules.ui_schema.agent_pipeline_validation import validate_analysis_batch
from backend.modules.ui_schema.agent_pipeline_values import unique_strings
from backend.modules.ui_schema.files import write_json


def run_analysis_batches(
    *,
    runtime: PipelineRuntime,
    requirements: list[dict[str, Any]],
    batch_size: int,
) -> tuple[list[RequirementAnalysisItem], list[str], int]:
    runtime.phase("analyzing_requirements", "Анализ требований группами")
    analyses: list[RequirementAnalysisItem] = []
    warnings: list[str] = []
    batches = fixed_batches(requirements, batch_size)
    for index, batch in enumerate(batches, start=1):
        runtime.ensure_not_cancelled()
        expected_ids = [str(item.get("id") or "") for item in batch]
        output = runtime.invoke_validated(
            output_model=RequirementAnalysisOutput,
            stage="analysis",
            base_context={
                **common_context(runtime.run_path, include_schema=False),
                "batch": {
                    "index": index,
                    "total": len(batches),
                    "requirements": batch,
                },
            },
            validator=lambda value, ids=expected_ids: validate_analysis_batch(
                value.items,
                expected_requirement_ids=ids,
            ),
        )
        analyses.extend(output.items)
        warnings.extend(output.warnings)
        write_json(
            runtime.run_path / "result" / "analysis.json",
            {
                "completed_batches": index,
                "total_batches": len(batches),
                "items": [item.model_dump() for item in analyses],
                "warnings": unique_strings(warnings),
            },
        )
    return analyses, warnings, len(batches)
