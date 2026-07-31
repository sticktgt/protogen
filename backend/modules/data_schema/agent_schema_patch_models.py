from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.modules.data_schema.agent_json_arguments import (
    normalize_array_argument,
    normalize_optional_object_argument,
)


class SchemaPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("schema_patch must contain at least one changed property")
        return self


class FieldPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    type: str | None = Field(default=None, min_length=1)
    required: bool | None = None
    description: str | None = None
    dictionary_id: str | None = None


class EntityPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    fields: list[FieldPatchPayload] = Field(default_factory=list)

    @field_validator("fields", mode="before")
    @classmethod
    def normalize_fields(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="entity field patches", wrapper_key="fields")


class CorePatchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_patch: SchemaPatchPayload | None = None
    entities: list[EntityPatchPayload] = Field(default_factory=list)

    @field_validator("schema_patch", mode="before")
    @classmethod
    def normalize_schema_patch(cls, value: Any) -> Any:
        return normalize_optional_object_argument(value, label="schema_patch")

    @field_validator("entities", mode="before")
    @classmethod
    def normalize_entities(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="entity patches", wrapper_key="entities")

    @model_validator(mode="after")
    def require_changes(self):
        if self.schema_patch is None and not self.entities:
            raise ValueError("core patch must contain schema_patch or entities")
        return self


class DictionaryValuePatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None


class DictionaryPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    values: list[DictionaryValuePatchPayload] = Field(default_factory=list)

    @field_validator("values", mode="before")
    @classmethod
    def normalize_values(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="dictionary value patches",
            wrapper_key="values",
        )


class DictionariesPatchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dictionaries: list[DictionaryPatchPayload] = Field(min_length=1)

    @field_validator("dictionaries", mode="before")
    @classmethod
    def normalize_dictionaries(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="dictionary patches",
            wrapper_key="dictionaries",
        )


class RelationPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    source_entity: str | None = Field(default=None, min_length=1)
    target_entity: str | None = Field(default=None, min_length=1)
    cardinality: str | None = Field(default=None, min_length=1)
    description: str | None = None


class RelationsPatchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relations: list[RelationPatchPayload] = Field(min_length=1)

    @field_validator("relations", mode="before")
    @classmethod
    def normalize_relations(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="relation patches", wrapper_key="relations")
