from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspacePayload(BaseModel):
    workspace_id: str


class AppUpdate(WorkspacePayload):
    title: str | None = None
    description: str | None = None


class PageCreate(WorkspacePayload):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""


class PageUpdate(WorkspacePayload):
    title: str | None = None
    description: str | None = None


class ElementCreate(WorkspacePayload):
    id: str | None = None
    parent_id: str | None = None
    type: str = "section"
    label: str = Field(min_length=1)
    description: str = ""
    purpose: str = ""


class ElementUpdate(WorkspacePayload):
    type: str | None = None
    label: str | None = None
    description: str | None = None
    purpose: str | None = None


class RequirementLinkCreate(WorkspacePayload):
    requirement_id: str = Field(min_length=1)
    target_type: str = Field(pattern="^(page|ui_element)$")
    target_id: str = Field(min_length=1)
    relation: str = "implemented_by"
    implementation_status: str = "planned"


class CodeLinkCreate(WorkspacePayload):
    target_type: str = Field(pattern="^(page|ui_element)$")
    target_id: str = Field(min_length=1)
    kind: str = "frontend_file"
    path: str = ""


class UiLinkCreate(WorkspacePayload):
    source_type: str = Field(pattern="^(page|ui_element)$")
    source_id: str = Field(min_length=1)
    target_type: str = Field(pattern="^(page|ui_element)$")
    target_id: str = Field(min_length=1)
    relation: str = "navigates_to"
