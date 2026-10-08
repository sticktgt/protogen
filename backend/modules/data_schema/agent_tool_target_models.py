from __future__ import annotations

from typing import Annotated, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field


class EntityTargetReference(BaseModel):
    """Exact reference to an entity selected by the LLM."""

    model_config = ConfigDict(extra="forbid")
    target_type: Literal["entity"]
    entity_id: str = Field(
        min_length=1,
        description="Exact canonical entity ID returned by a write tool or loaded from context.",
    )


class FieldTargetReference(BaseModel):
    """Exact reference to a field selected by the LLM."""

    model_config = ConfigDict(extra="forbid")
    target_type: Literal["field"]
    entity_id: str = Field(
        min_length=1,
        description="Exact canonical ID of the entity that owns the field.",
    )
    field_id: str = Field(
        min_length=1,
        description="Exact canonical field ID inside entity_id.",
    )


class RelationTargetReference(BaseModel):
    """Exact reference to a relation selected by the LLM."""

    model_config = ConfigDict(extra="forbid")
    target_type: Literal["relation"]
    relation_id: str = Field(
        min_length=1,
        description="Exact canonical relation ID returned by a write tool or loaded from context.",
    )


class DictionaryTargetReference(BaseModel):
    """Exact reference to a dictionary selected by the LLM."""

    model_config = ConfigDict(extra="forbid")
    target_type: Literal["dictionary"]
    dictionary_id: str = Field(
        min_length=1,
        description="Exact canonical dictionary ID returned by a write tool or loaded from context.",
    )


class DictionaryValueTargetReference(BaseModel):
    """Exact reference to a value selected by the LLM."""

    model_config = ConfigDict(extra="forbid")
    target_type: Literal["dictionary_value"]
    dictionary_id: str = Field(
        min_length=1,
        description="Exact canonical ID of the dictionary that owns the value.",
    )
    value_id: str = Field(
        min_length=1,
        description="Exact canonical value ID inside dictionary_id.",
    )


RequirementTargetReference: TypeAlias = Annotated[
    Union[
        EntityTargetReference,
        FieldTargetReference,
        RelationTargetReference,
        DictionaryTargetReference,
        DictionaryValueTargetReference,
    ],
    Field(discriminator="target_type"),
]
