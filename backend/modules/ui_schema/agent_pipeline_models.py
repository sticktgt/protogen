from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.modules.ui_schema.agent_json_arguments import parse_json_array
from backend.modules.ui_schema.agent_pipeline_decisions import (
    Classification,
    UiEffect,
    decision_consistency_error,
)


class RequirementAnalysisItem(BaseModel):
    """One model-authored semantic reading of an incoming requirement."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(min_length=1)
    ui_effect: UiEffect
    classification: Classification
    ui_outcomes: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)

    @field_validator("ui_outcomes", mode="before")
    @classmethod
    def _decode_outcomes(cls, value: Any) -> Any:
        return parse_json_array(value)


class RequirementAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RequirementAnalysisItem] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("items", "warnings", mode="before")
    @classmethod
    def _decode_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)


class PipelinePageDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    elements: list[dict[str, Any]] = Field(default_factory=list)
    file_path: str | None = None

    @field_validator("elements", mode="before")
    @classmethod
    def _decode_elements(cls, value: Any) -> Any:
        return parse_json_array(value)


class PipelinePageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(min_length=1)
    title: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _require_metadata(self):
        self.page_id = self.page_id.strip()
        if not self.page_id:
            raise ValueError("page_id must be non-empty")
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError("title must be non-empty when provided")
        if self.title is None and self.description is None:
            raise ValueError("update_pages item requires title or description")
        return self


class PipelineElementChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(min_length=1)
    parent_id: str | None = None
    element: dict[str, Any]
    position: int | None = Field(default=None, ge=0)


class PipelineElementMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(min_length=1)
    element_id: str = Field(min_length=1)
    new_parent_id: str = Field(min_length=1)
    position: int | None = Field(default=None, ge=0)


class PipelineUiLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    source_type: Literal["page", "ui_element"] | None = None
    source_id: str = Field(min_length=1)
    target_type: Literal["page", "ui_element"] | None = None
    target_id: str = Field(min_length=1)
    relation: Literal["navigates_to", "opens_modal"]


class PipelineChangeBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    create_pages: list[PipelinePageDocument] = Field(default_factory=list)
    update_pages: list[PipelinePageUpdate] = Field(default_factory=list)
    upsert_elements: list[PipelineElementChange] = Field(default_factory=list)
    move_elements: list[PipelineElementMove] = Field(default_factory=list)
    ui_links: list[PipelineUiLink] = Field(default_factory=list)
    no_changes_reason: str = ""

    @field_validator(
        "create_pages",
        "update_pages",
        "upsert_elements",
        "move_elements",
        "ui_links",
        mode="before",
    )
    @classmethod
    def _decode_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)

    @model_validator(mode="after")
    def _validate_operations(self):
        self.no_changes_reason = self.no_changes_reason.strip()
        has_operations = any(
            (
                self.create_pages,
                self.update_pages,
                self.upsert_elements,
                self.move_elements,
                self.ui_links,
            )
        )
        if has_operations and self.no_changes_reason:
            raise ValueError(
                "no_changes_reason must be empty when change operations are present"
            )
        if not has_operations and not self.no_changes_reason:
            raise ValueError(
                "changes require at least one operation or no_changes_reason"
            )
        return self


class PipelineTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["page", "ui_element"]
    target_id: str = Field(min_length=1)
    action: Literal["reuse", "extend", "create"]
    implementation_status: Literal["planned", "in_progress", "implemented"]


class PipelineDecision(BaseModel):
    """Canonical model-authored decision used by planning, audit and storage export."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(min_length=1)
    ui_effect: UiEffect
    classification: Classification
    targets: list[PipelineTarget] = Field(default_factory=list)
    reason: str = Field(min_length=1)

    @field_validator("targets", mode="before")
    @classmethod
    def _decode_targets(cls, value: Any) -> Any:
        return parse_json_array(value)

    def consistency_error(self) -> str | None:
        return decision_consistency_error(
            classification=self.classification,
            ui_effect=self.ui_effect,
            target_count=len(self.targets),
        )


class PipelinePlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[PipelineDecision] = Field(min_length=1)
    changes: PipelineChangeBundle
    agent_note: str = Field(default="")
    warnings: list[str] = Field(default_factory=list)

    @field_validator("decisions", "warnings", mode="before")
    @classmethod
    def _decode_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)


class PipelineAuditIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(min_length=1)
    issue: str = Field(min_length=1)


class PipelineAuditOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[PipelineAuditIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("issues", "warnings", mode="before")
    @classmethod
    def _decode_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)


class PipelineCorrectionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[PipelineDecision] = Field(default_factory=list)
    changes: PipelineChangeBundle
    agent_note: str = Field(default="")
    warnings: list[str] = Field(default_factory=list)

    @field_validator("decisions", "warnings", mode="before")
    @classmethod
    def _decode_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)


class PipelineStructuralChangeBundle(BaseModel):
    """Minimal change bundle used only by structural review."""

    model_config = ConfigDict(extra="forbid")

    upsert_elements: list[PipelineElementChange] = Field(default_factory=list)
    move_elements: list[PipelineElementMove] = Field(default_factory=list)
    ui_links: list[PipelineUiLink] = Field(default_factory=list)
    remove_elements: list[str] = Field(default_factory=list)
    remove_ui_links: list[str] = Field(default_factory=list)
    no_changes_reason: str = ""

    @field_validator(
        "upsert_elements",
        "move_elements",
        "ui_links",
        "remove_elements",
        "remove_ui_links",
        mode="before",
    )
    @classmethod
    def _decode_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)

    @model_validator(mode="after")
    def _validate_operations(self):
        self.no_changes_reason = self.no_changes_reason.strip()
        normalized_removals: list[str] = []
        for item in self.remove_elements:
            value = str(item or "").strip()
            if not value:
                raise ValueError("remove_elements items must be non-empty IDs")
            if value not in normalized_removals:
                normalized_removals.append(value)
        self.remove_elements = normalized_removals
        normalized_link_removals: list[str] = []
        for item in self.remove_ui_links:
            value = str(item or "").strip()
            if not value:
                raise ValueError("remove_ui_links items must be non-empty IDs")
            if value not in normalized_link_removals:
                normalized_link_removals.append(value)
        self.remove_ui_links = normalized_link_removals
        has_operations = bool(
            self.upsert_elements
            or self.move_elements
            or self.ui_links
            or self.remove_elements
            or self.remove_ui_links
        )
        if has_operations and self.no_changes_reason:
            raise ValueError(
                "no_changes_reason must be empty when change operations are present"
            )
        if not has_operations and not self.no_changes_reason:
            raise ValueError(
                "changes require at least one operation or no_changes_reason"
            )
        return self


class PipelineStructuralResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    action: Literal["keep", "modify", "remove"]
    reason: str = Field(min_length=1)


class PipelineStructuralReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolutions: list[PipelineStructuralResolution] = Field(min_length=1)
    decisions: list[PipelineDecision] = Field(default_factory=list)
    changes: PipelineStructuralChangeBundle
    agent_note: str = Field(default="")
    warnings: list[str] = Field(default_factory=list)

    @field_validator("resolutions", "decisions", "warnings", mode="before")
    @classmethod
    def _decode_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)
