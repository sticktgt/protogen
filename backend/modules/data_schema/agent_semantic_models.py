from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.data_schema.agent_json_arguments import normalize_array_argument


class SemanticReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: Literal["must_fix", "advisory"]
    category: str = Field(min_length=1)
    message: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    requirement_ids: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)

    @field_validator("requirement_ids", "targets", mode="before")
    @classmethod
    def normalize_string_arrays(cls, value: Any, info) -> Any:
        if value is None:
            return []
        return normalize_array_argument(value, label=info.field_name, wrapper_key=info.field_name)


class SemanticReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "revise"]
    coverage_complete: bool = Field(
        description=(
            "True only when the requested review scope was checked completely. "
            "An incomplete review cannot approve the candidate."
        )
    )
    verified_issue_ids: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    issues: list[SemanticReviewIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    review_note: str = ""

    @field_validator("issues", "strengths", "verified_issue_ids", mode="before")
    @classmethod
    def normalize_arrays(cls, value: Any, info) -> Any:
        if value is None:
            return []
        return normalize_array_argument(value, label=info.field_name, wrapper_key=info.field_name)
