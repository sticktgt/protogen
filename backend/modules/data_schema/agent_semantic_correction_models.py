from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.modules.data_schema.agent_json_arguments import (
    normalize_array_argument,
    normalize_optional_object_argument,
)
from backend.modules.data_schema.agent_schema_patch_models import (
    DictionaryPatchPayload,
    EntityPatchPayload,
    RelationPatchPayload,
    SchemaPatchPayload,
)
from backend.modules.data_schema.agent_semantic_correction_write_models import (
    CorrectionDictionaryPayload,
    CorrectionEntityPayload,
    CorrectionRelationPayload,
)
from backend.modules.data_schema.agent_tool_models import (
    RequirementResultUpdate,
    SchemaPayload,
)


class SemanticCorrectionPlanPayload(BaseModel):
    """One complete, technically executable correction plan selected by the LLM."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    write_schema_document: SchemaPayload | None = None
    write_dictionaries: list[CorrectionDictionaryPayload] = Field(default_factory=list)
    write_entities: list[CorrectionEntityPayload] = Field(default_factory=list)
    write_relations: list[CorrectionRelationPayload] = Field(default_factory=list)
    patch_schema: SchemaPatchPayload | None = None
    patch_dictionaries: list[DictionaryPatchPayload] = Field(default_factory=list)
    patch_entities: list[EntityPatchPayload] = Field(default_factory=list)
    patch_relations: list[RelationPatchPayload] = Field(default_factory=list)
    remove_targets: list[str] = Field(default_factory=list)
    requirement_updates: list[RequirementResultUpdate] = Field(default_factory=list)
    agent_note: str | None = None
    warnings: list[str] | None = None

    @field_validator("write_schema_document", mode="before")
    @classmethod
    def normalize_write_schema_document(cls, value: Any) -> Any:
        return normalize_optional_object_argument(value, label="write_schema_document")

    @field_validator("patch_schema", mode="before")
    @classmethod
    def normalize_patch_schema(cls, value: Any) -> Any:
        return normalize_optional_object_argument(value, label="patch_schema")

    @field_validator("write_dictionaries", mode="before")
    @classmethod
    def normalize_write_dictionaries(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="correction dictionaries to write",
            wrapper_key="write_dictionaries",
        )

    @field_validator("write_entities", mode="before")
    @classmethod
    def normalize_write_entities(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="correction entities to write",
            wrapper_key="write_entities",
        )

    @field_validator("write_relations", mode="before")
    @classmethod
    def normalize_write_relations(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="correction relations to write",
            wrapper_key="write_relations",
        )

    @field_validator("patch_dictionaries", mode="before")
    @classmethod
    def normalize_patch_dictionaries(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="correction dictionary patches",
            wrapper_key="patch_dictionaries",
        )

    @field_validator("patch_entities", mode="before")
    @classmethod
    def normalize_patch_entities(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="correction entity patches",
            wrapper_key="patch_entities",
        )

    @field_validator("patch_relations", mode="before")
    @classmethod
    def normalize_patch_relations(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="correction relation patches",
            wrapper_key="patch_relations",
        )

    @field_validator("remove_targets", mode="before")
    @classmethod
    def normalize_remove_targets(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="correction removal targets",
            wrapper_key="remove_targets",
        )

    @field_validator("requirement_updates", mode="before")
    @classmethod
    def normalize_requirement_updates(cls, value: Any) -> Any:
        return normalize_array_argument(
            value,
            label="correction requirement updates",
            wrapper_key="requirement_updates",
        )

    @field_validator("warnings", mode="before")
    @classmethod
    def normalize_warnings(cls, value: Any) -> Any:
        if value is None:
            return None
        return normalize_array_argument(
            value,
            label="correction warnings",
            wrapper_key="warnings",
        )

    @model_validator(mode="after")
    def require_at_least_one_operation(self):
        if any(
            (
                self.write_schema_document is not None,
                bool(self.write_dictionaries),
                bool(self.write_entities),
                bool(self.write_relations),
                self.patch_schema is not None,
                bool(self.patch_dictionaries),
                bool(self.patch_entities),
                bool(self.patch_relations),
                bool(self.remove_targets),
                bool(self.requirement_updates),
            )
        ):
            return self
        raise ValueError("semantic correction plan must contain at least one operation")
