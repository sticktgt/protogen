from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from backend.modules.ui_schema.agent_change_bundle import (
    apply_ui_schema_change_bundle,
    change_bundle_limits,
)
from backend.modules.ui_schema.agent_events import append_event, elapsed_seconds
from backend.modules.ui_schema.agent_limits import execution_limits
from backend.modules.ui_schema.agent_monitor import AgentRunCancellation
from backend.modules.ui_schema.agent_pipeline_llm import (
    PipelineStageError,
    invoke_structured_stage,
)
from backend.modules.ui_schema.agent_pipeline_settings import pipeline_settings
from backend.modules.ui_schema.agent_runs import is_cancelled, update_run
from backend.modules.ui_schema.files import read_json, write_json

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class PipelineRuntime:
    module_root: Path
    run_id: str
    run_path: Path
    model: Any
    agent_config: dict[str, Any]
    callback: Any
    metadata: dict[str, Any]

    def phase(self, phase: str, message: str) -> None:
        update_run(self.module_root, self.run_id, status="running", phase=phase)
        write_json(
            self.run_path / "result" / "pipeline_state.json",
            {"version": 2, "status": "running", "phase": phase},
        )
        append_event(
            self.module_root,
            self.run_id,
            event_type="phase",
            message=message,
            data={"phase": phase},
        )

    def ensure_not_cancelled(self) -> None:
        if is_cancelled(self.module_root, self.run_id):
            raise AgentRunCancellation("Задача отменена пользователем")

    def remaining_duration_seconds(self) -> int:
        maximum = execution_limits(self.agent_config)["max_duration_seconds"]
        metrics = read_json(self.run_path / "metrics.json", {})
        elapsed = elapsed_seconds(str(metrics.get("started_at") or ""))
        return max(0, maximum - elapsed)

    def invoke_validated(
        self,
        *,
        output_model: type[T],
        stage: str,
        base_context: dict[str, Any],
        validator: Callable[[T], list[str]],
    ) -> T:
        maximum_attempts = int(pipeline_settings(self.agent_config)["stage_attempts"])
        feedback: list[str] = []
        previous_output: dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt in range(1, maximum_attempts + 1):
            context = {
                **base_context,
                "validation_feedback": feedback,
                "previous_output": previous_output,
                "attempt": attempt,
            }
            try:
                output = invoke_structured_stage(
                    model=self.model,
                    output_model=output_model,
                    stage=stage,
                    context=context,
                    module_root=self.module_root,
                    run_id=self.run_id,
                    agent_config=self.agent_config,
                    callback=self.callback,
                    invocation_metadata=self.metadata,
                    attempts=1,
                    attempt_number=attempt,
                    attempt_total=maximum_attempts,
                )
            except PipelineStageError as exc:
                last_error = exc
                feedback = exc.validation_errors or [str(exc)]
                if exc.previous_output is not None:
                    previous_output = exc.previous_output
                continue
            feedback = validator(output)
            previous_output = output.model_dump()
            if not feedback:
                return output
            append_event(
                self.module_root,
                self.run_id,
                event_type="pipeline_stage_validation_failed",
                level="warning",
                message=(
                    f"Этап {stage} требует исправления: ошибок {len(feedback)}; "
                    f"{feedback[0][:300]}"
                ),
                data={
                    "stage": stage,
                    "attempt": attempt,
                    "validation_errors": feedback[:20],
                },
            )
        if last_error and not feedback:
            raise last_error
        raise PipelineStageError(
            f"Этап {stage} не прошёл техническую проверку: "
            + "; ".join(feedback[:20])
        )

    def apply_changes(
        self,
        changes: Any,
        *,
        allow_remove_new_elements: bool = False,
        allow_remove_ui_links: bool = False,
    ) -> dict[str, Any]:
        limits = change_bundle_limits(self.agent_config)
        execution = (
            self.agent_config.get("execution", {})
            if isinstance(self.agent_config, dict)
            else {}
        )
        removals = list(getattr(changes, "remove_elements", []) or [])
        if removals and not allow_remove_new_elements:
            raise ValueError(
                "remove_elements is allowed only during structural review"
            )
        link_removals = list(getattr(changes, "remove_ui_links", []) or [])
        if link_removals and not allow_remove_ui_links:
            raise ValueError(
                "remove_ui_links is allowed only during structural review"
            )
        return apply_ui_schema_change_bundle(
            working_root=self.run_path / "working" / "ui_schema",
            result_root=self.run_path / "result",
            create_pages=[
                item.model_dump() for item in getattr(changes, "create_pages", [])
            ],
            upsert_elements=[
                item.model_dump() for item in getattr(changes, "upsert_elements", [])
            ],
            move_elements=[
                item.model_dump() for item in getattr(changes, "move_elements", [])
            ],
            ui_links=[item.model_dump() for item in getattr(changes, "ui_links", [])],
            no_changes_reason=changes.no_changes_reason,
            maximum_pages=limits["pages"],
            maximum_top_level_elements=int(
                execution["write_page_max_top_level_elements"]
            ),
            maximum_element_changes=int(
                execution["write_element_batch_max_changes"]
            ),
            maximum_moves=limits["moves"],
            maximum_links=limits["links"],
            update_pages=[
                item.model_dump() for item in getattr(changes, "update_pages", [])
            ],
            remove_elements=removals,
            remove_ui_links=link_removals,
            base_root=self.run_path / "base" / "ui_schema",
            maximum_removals=limits["removals"],
        )

    def event(
        self,
        *,
        event_type: str,
        message: str,
        level: str = "info",
        data: dict[str, Any] | None = None,
    ) -> None:
        append_event(
            self.module_root,
            self.run_id,
            event_type=event_type,
            level=level,
            message=message,
            data=data or {},
        )
