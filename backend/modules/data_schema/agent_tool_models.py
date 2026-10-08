from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.modules.data_schema.agent_json_arguments import (
    normalize_array_argument,
    normalize_optional_object_argument,
)
from backend.modules.data_schema.agent_target_references import compact_target_reference


class DictionaryValuePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    title: str = Field(min_length=1)
    description: str = ""


class DictionaryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    title: str = Field(min_length=1)
    description: str = ""
    values: list[DictionaryValuePayload] = Field(default_factory=list)

    @field_validator("values", mode="before")
    @classmethod
    def normalize_values(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="dictionary values", wrapper_key="values")


class FieldPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    title: str = Field(min_length=1)
    type: str = "string"
    required: bool = False
    description: str = ""
    dictionary_id: str | None = None


class EntityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    title: str = Field(min_length=1)
    description: str = ""
    fields: list[FieldPayload] = Field(default_factory=list)

    @field_validator("fields", mode="before")
    @classmethod
    def normalize_fields(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="entity fields", wrapper_key="fields")


class SchemaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    description: str | None = None


class CoreWriteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_document: SchemaPayload | None = Field(
        default=None,
        description="Native JSON object for schema.json metadata. Omit when unchanged.",
    )
    entities: list[EntityPayload] = Field(default_factory=list)

    @field_validator("schema_document", mode="before")
    @classmethod
    def normalize_schema_document(cls, value: Any) -> Any:
        candidate = normalize_optional_object_argument(value, label="schema_document")
        if isinstance(candidate, dict) and set(candidate) == {"schema_document"}:
            return normalize_optional_object_argument(
                candidate["schema_document"],
                label="schema_document wrapper",
            )
        return candidate

    @field_validator("entities", mode="before")
    @classmethod
    def normalize_entities(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="entities", wrapper_key="entities")


class DictionariesWriteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dictionaries: list[DictionaryPayload]

    @field_validator("dictionaries", mode="before")
    @classmethod
    def normalize_dictionaries(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="dictionaries", wrapper_key="dictionaries")


class RelationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    title: str = Field(min_length=1)
    source_entity: str = Field(min_length=1)
    target_entity: str = Field(min_length=1)
    cardinality: str = "one_to_many"
    description: str = ""


class RelationsWriteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relations: list[RelationPayload]

    @field_validator("relations", mode="before")
    @classmethod
    def normalize_relations(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="relations", wrapper_key="relations")




class RemoveAdditionsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: list[str] = Field(min_length=1)

    @field_validator("targets", mode="before")
    @classmethod
    def normalize_targets(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="removal targets", wrapper_key="targets")


class RequirementTargetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_type: Literal["entity", "field", "relation", "dictionary", "dictionary_value"]
    target_id: str = Field(
        min_length=1,
        description=(
            "Exact canonical target ID copied from context or a write-tool result. "
            "Field and dictionary-value IDs contain owner and local ID separated by a dot."
        ),
    )
    relation: Literal["defines", "uses", "clarifies", "validates"] = "defines"
    implementation_status: str = "planned"

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_structured_target(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "target" not in value:
            return value
        payload = dict(value)
        target = payload.pop("target")
        target = normalize_optional_object_argument(target, label="requirement target")
        if isinstance(target, BaseModel):
            target = target.model_dump(exclude_none=True)
        if not isinstance(target, dict):
            raise ValueError("requirement target must be an object")
        target_type, target_id = compact_target_reference(target)
        payload.setdefault("target_type", target_type)
        payload.setdefault("target_id", target_id)
        return payload


class RequirementResultUpdate(BaseModel):
    """Complete traceability result for one requirement.

    The LLM explicitly selects both the direct links and the requirement-level
    classification. Backend validation only enforces their structural
    consistency; it does not choose targets or classifications.
    """

    model_config = ConfigDict(extra="forbid")
    requirement_id: str = Field(min_length=1)
    links: list[RequirementTargetPayload] = Field(default_factory=list)
    classification: Literal["direct", "cross_cutting_data", "no_data", "unclear"] = Field(
        description=(
            "Requirement-level classification. Use direct with one or more links. "
            "Values defines, uses, clarifies and validates belong to link.relation."
        )
    )
    reason: str = Field(
        default="",
        description=(
            "Required for unclear. Optional concise explanation for no_data and "
            "cross_cutting_data; omit it when classification alone is sufficient."
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Optional human-readable notes for this requirement result. "
            "They are preserved verbatim for human review and do not alter classification."
        ),
    )

    @field_validator("links", mode="before")
    @classmethod
    def normalize_links(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="requirement result links", wrapper_key="links")

    @field_validator("warnings", mode="before")
    @classmethod
    def normalize_requirement_warnings(cls, value: Any) -> Any:
        if value is None:
            return []
        return normalize_array_argument(
            value,
            label="requirement result warnings",
            wrapper_key="warnings",
        )

    @model_validator(mode="after")
    def validate_result_shape(self):
        if self.classification == "direct":
            if not self.links:
                raise ValueError("classification=direct requires at least one direct link")
            return self
        if self.links:
            raise ValueError(
                f"classification={self.classification} requires an empty links array"
            )
        if self.classification == "unclear" and not self.reason.strip():
            raise ValueError("classification=unclear requires a non-empty reason")
        return self


class RequirementResultsPatchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    updates: list[RequirementResultUpdate] = Field(min_length=1)
    agent_note: str | None = None
    warnings: list[str] | None = None

    @field_validator("updates", mode="before")
    @classmethod
    def normalize_updates(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="requirement result updates", wrapper_key="updates")

    @field_validator("warnings", mode="before")
    @classmethod
    def normalize_warnings(cls, value: Any) -> Any:
        if value is None:
            return None
        return normalize_array_argument(value, label="assessment warnings", wrapper_key="warnings")

    @model_validator(mode="after")
    def require_unique_requirement_ids(self):
        seen: set[str] = set()
        duplicates: set[str] = set()
        for item in self.updates:
            if item.requirement_id in seen:
                duplicates.add(item.requirement_id)
            seen.add(item.requirement_id)
        if duplicates:
            raise ValueError(
                "Each requirement_id may occur only once in a result patch: "
                + ", ".join(sorted(duplicates))
            )
        return self


class RequirementLinkPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    requirement_id: str = Field(min_length=1)
    target_type: Literal["entity", "field", "relation", "dictionary", "dictionary_value"]
    target_id: str = Field(min_length=1)
    relation: Literal["defines", "uses", "clarifies", "validates"] = "defines"
    implementation_status: str = "planned"

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_structured_target(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "target" not in value:
            return value
        payload = dict(value)
        target = payload.pop("target")
        target = normalize_optional_object_argument(target, label="requirement target")
        if isinstance(target, BaseModel):
            target = target.model_dump(exclude_none=True)
        if not isinstance(target, dict):
            raise ValueError("requirement target must be an object")
        target_type, target_id = compact_target_reference(target)
        payload.setdefault("target_type", target_type)
        payload.setdefault("target_id", target_id)
        return payload


class RequirementLinksWriteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    links: list[RequirementLinkPayload]

    @field_validator("links", mode="before")
    @classmethod
    def normalize_links(cls, value: Any) -> Any:
        return normalize_array_argument(value, label="requirement links", wrapper_key="links")


class RequirementAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: str = Field(min_length=1)
    reason: str = ""


class AgentReportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_note: str = ""
    cross_cutting_data: list[RequirementAssessment] = Field(default_factory=list)
    no_data: list[RequirementAssessment] = Field(default_factory=list)
    unclear: list[RequirementAssessment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("cross_cutting_data", "no_data", "unclear", "warnings", mode="before")
    @classmethod
    def normalize_report_arrays(cls, value: Any, info) -> Any:
        return normalize_array_argument(value, label=info.field_name, wrapper_key=info.field_name)
