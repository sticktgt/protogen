from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.data_schema.agent_json_arguments import normalize_array_argument


class CorrectionDictionaryValuePayload(BaseModel):
    """Dictionary value with an explicit stable ID for a one-shot correction plan."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""


class CorrectionDictionaryPayload(BaseModel):
    """New dictionary whose ID can be referenced later in the same plan."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    values: list[CorrectionDictionaryValuePayload] = Field(default_factory=list)

    @field_validator("values", mode="before")
    @classmethod
    def normalize_values(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="correction dictionary values",
            wrapper_key="values",
        )


class CorrectionFieldPayload(BaseModel):
    """New field with an explicit local ID for a one-shot correction plan."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    type: str = "string"
    required: bool = False
    description: str = ""
    dictionary_id: str | None = None


class CorrectionEntityPayload(BaseModel):
    """New entity whose fields can be referenced later in the same plan."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    fields: list[CorrectionFieldPayload] = Field(default_factory=list)

    @field_validator("fields", mode="before")
    @classmethod
    def normalize_fields(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="correction entity fields",
            wrapper_key="fields",
        )


class CorrectionRelationPayload(BaseModel):
    """New relation with an explicit stable ID for a one-shot correction plan."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_entity: str = Field(min_length=1)
    target_entity: str = Field(min_length=1)
    cardinality: str = "one_to_many"
    description: str = ""
