from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspacePayload(BaseModel):
    workspace_id: str


class SchemaUpdate(WorkspacePayload):
    title: str | None = None
    description: str | None = None


class EntityCreate(WorkspacePayload):
    id: str | None = None
    title: str = Field(min_length=1)
    description: str = ""


class EntityUpdate(WorkspacePayload):
    title: str | None = None
    description: str | None = None


class FieldCreate(WorkspacePayload):
    id: str | None = None
    title: str = Field(min_length=1)
    type: str = "string"
    required: bool = False
    description: str = ""
    dictionary_id: str | None = None


class FieldUpdate(WorkspacePayload):
    title: str | None = None
    type: str | None = None
    required: bool | None = None
    description: str | None = None
    dictionary_id: str | None = None


class RelationCreate(WorkspacePayload):
    id: str | None = None
    title: str = Field(min_length=1)
    source_entity: str = Field(min_length=1)
    target_entity: str = Field(min_length=1)
    cardinality: str = "one_to_many"
    description: str = ""


class RelationUpdate(WorkspacePayload):
    title: str | None = None
    source_entity: str | None = None
    target_entity: str | None = None
    cardinality: str | None = None
    description: str | None = None


class RequirementLinkCreate(WorkspacePayload):
    requirement_id: str = Field(min_length=1)
    target_type: str = Field(pattern="^(entity|field|relation|dictionary|dictionary_value)$")
    target_id: str = Field(min_length=1)
    relation: str = "defines"
    implementation_status: str = "planned"


class ExternalLinkCreate(WorkspacePayload):
    data_target_type: str = Field(pattern="^(entity|field|relation|dictionary|dictionary_value)$")
    data_target_id: str = Field(min_length=1)
    external_target_type: str = Field(min_length=1)
    external_target_id: str = Field(min_length=1)
    relation: str = "uses"


class CodeLinkCreate(WorkspacePayload):
    target_type: str = Field(pattern="^(entity|field|relation|dictionary|dictionary_value)$")
    target_id: str = Field(min_length=1)
    code_type: str = "model"
    path: str = ""
    status: str = "planned"
