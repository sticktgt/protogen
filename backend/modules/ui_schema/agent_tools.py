from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.modules.ui_schema.agent_completion import validate_and_mark_completion
from backend.modules.ui_schema.agent_context import build_synchronization_context
from backend.modules.ui_schema.agent_preservation import (
    delete_new_elements,
    normalize_element_ids,
)
from backend.modules.ui_schema.agent_schema_io import (
    delete_page_file,
    max_page_files,
    recoverable_tool_result,
    write_ui_schema_bundle as write_schema_bundle,
)
from backend.modules.ui_schema.agent_tool_payloads import (
    decode_json_argument,
    normalize_core_argument,
    normalize_document_content,
    normalize_pages_argument,
    normalize_traceability_argument,
)


class CoreWriteArgs(BaseModel):
    app: dict[str, Any] | None = Field(
        default=None,
        description="Native JSON object for app.json. Omit when unchanged.",
    )
    schema_document: dict[str, Any] | None = Field(
        default=None,
        description="Native JSON object for schema.json. Omit when unchanged.",
    )
    links: dict[str, Any] | None = Field(
        default=None,
        description="Native JSON object for links.json. Omit when unchanged.",
    )

    @field_validator("app", "schema_document", "links", mode="before")
    @classmethod
    def normalize_json_object(cls, value: Any, info):
        if value is None:
            return None
        file_path = {
            "app": "app.json",
            "schema_document": "schema.json",
            "links": "links.json",
        }[info.field_name]
        return normalize_document_content(file_path, value)


class PageWrite(BaseModel):
    file_path: str = Field(
        description="Relative page path such as pages/reports.statement.json"
    )
    content: dict[str, Any] = Field(
        description="Native JSON page object. Never pass a JSON-encoded string."
    )

    @field_validator("content", mode="before")
    @classmethod
    def normalize_page_content(cls, value: Any, info):
        return normalize_document_content("pages/page.json", value)


class PagesWriteArgs(BaseModel):
    pages: list[PageWrite] = Field(
        description=(
            "Native JSON array of changed or new pages. Each item has file_path and "
            "content. Do not include unchanged pages and do not serialize the array."
        )
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_pages(cls, value: Any):
        if not isinstance(value, dict) or "pages" not in value:
            return value
        return {**value, "pages": normalize_pages_argument(value["pages"])}


class RequirementAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(description="Exact requirement ID from synchronization context")
    reason: str = Field(description="Short factual reason for this final assessment")


class CrossCuttingAssessment(RequirementAssessment):
    scope: Literal["global", "targeted"] = Field(
        default="global",
        description=(
            "global when the UI rule applies to the whole interface and may have no direct "
            "target; targeted when concrete requirement links identify affected pages/elements"
        ),
    )


class AgentReportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        default="",
        description="Deprecated compatibility field. Leave empty; backend generates the factual summary.",
    )
    agent_note: str = Field(
        default="",
        description=(
            "Optional model comment about decisions or caveats. Do not claim complete coverage "
            "or repeat counts; backend generates the factual summary."
        ),
    )
    cross_cutting_ui: list[CrossCuttingAssessment] = Field(default_factory=list)
    no_ui: list[RequirementAssessment] = Field(default_factory=list)
    unclear: list[RequirementAssessment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TraceabilityWriteArgs(BaseModel):
    requirement_ui_links: dict[str, Any] = Field(
        description=(
            "Native JSON object for mappings/requirement_ui_links.json with a links array."
        )
    )
    agent_report: AgentReportPayload = Field(
        description=(
            "Native JSON object with one exclusive final assessment for every requirement: "
            "direct UI requirements are represented only by links; use cross_cutting_ui, "
            "no_ui or unclear for all remaining requirements."
        )
    )

    @field_validator("requirement_ui_links", mode="before")
    @classmethod
    def normalize_requirement_links(cls, value: Any):
        return normalize_document_content("mappings/requirement_ui_links.json", value)

    @field_validator("agent_report", mode="before")
    @classmethod
    def normalize_agent_report(cls, value: Any):
        return normalize_document_content("result/agent_report.json", value)


class DeleteElementsArgs(BaseModel):
    element_ids: list[str] | str = Field(
        description=(
            "IDs of elements created during the current run. Existing base elements "
            "are protected. A valid JSON-encoded list is accepted for compatibility."
        )
    )
    reason: str = Field(description="Why these newly generated elements must be removed")


def create_agent_tools(*, run_path: Path, agent_config: dict[str, Any]):
    from langchain.tools import tool

    working_root = run_path / "working" / "ui_schema"
    base_root = run_path / "base" / "ui_schema"
    result_root = run_path / "result"
    maximum_page_files = max_page_files(agent_config)

    @tool
    def load_synchronization_context() -> str:
        """Load the complete, current synchronization input exactly once.

        Returns task parameters, all requirements, the current temporary UI
        schema, allowed element types and the latest validation errors.
        """
        return json.dumps(
            build_synchronization_context(run_path),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @tool(args_schema=CoreWriteArgs)
    def write_ui_schema_core(
        app: dict[str, Any] | None = None,
        schema_document: dict[str, Any] | None = None,
        links: dict[str, Any] | None = None,
    ) -> str:
        """Write changed application, page registry and UI navigation documents.

        Pass native JSON objects, not strings. Omitted documents remain unchanged.
        Existing pages and elements omitted from updates are preserved by backend.
        """
        return recoverable_tool_result(
            lambda: write_schema_bundle(
                working_root=working_root,
                result_root=result_root,
                files=normalize_core_argument(app=app, schema=schema_document, links=links),
                maximum_files=3,
            )
        )

    @tool(args_schema=PagesWriteArgs)
    def write_ui_schema_pages(pages: list[dict[str, Any]]) -> str:
        """Write a batch of new or changed page objects.

        Include only pages that actually change. Use one native JSON array with
        file_path/content items. Existing omitted pages and elements are preserved.
        """
        return recoverable_tool_result(
            lambda: write_schema_bundle(
                working_root=working_root,
                result_root=result_root,
                files=normalize_pages_argument(_plain_model_values(pages)),
                maximum_files=maximum_page_files,
            )
        )

    @tool(args_schema=TraceabilityWriteArgs)
    def write_ui_schema_traceability(
        requirement_ui_links: dict[str, Any],
        agent_report: AgentReportPayload | dict[str, Any],
    ) -> str:
        """Write requirement-to-UI links and exclusive requirement assessments.

        Direct UI requirements are represented by links. Every remaining requirement
        must appear exactly once in cross_cutting_ui, no_ui or unclear. The optional
        agent_note is advisory; backend generates the factual summary. This tool does
        not modify the external requirements file.
        """
        return recoverable_tool_result(
            lambda: write_schema_bundle(
                working_root=working_root,
                result_root=result_root,
                files=normalize_traceability_argument(
                    requirement_ui_links=requirement_ui_links,
                    agent_report=_plain_model_value(agent_report),
                ),
                maximum_files=2,
            )
        )

    @tool
    def delete_ui_schema_page_file(file_path: str) -> str:
        """Delete a page created during this run; base pages are protected."""
        return recoverable_tool_result(
            lambda: delete_page_file(
                working_root=working_root, base_root=base_root, file_path=file_path
            )
        )

    @tool(args_schema=DeleteElementsArgs)
    def delete_ui_schema_elements(element_ids: list[str] | str, reason: str) -> str:
        """Delete invalid elements created during this run only.

        Existing elements copied from the base schema cannot be removed by AI
        synchronization. Use this only to correct newly generated output.
        """
        return recoverable_tool_result(
            lambda: delete_new_elements(
                base_root=base_root,
                working_root=working_root,
                element_ids=normalize_element_ids(
                    decode_json_argument(element_ids, label="element_ids")
                ),
                reason=reason,
            )
        )

    @tool
    def validate_ui_schema_state() -> str:
        """Normalize and validate the temporary UI schema. A valid result completes the run."""
        validation = validate_and_mark_completion(run_path)
        return json.dumps(
            {
                **validation,
                "completed": bool(validation.get("valid")),
                "next_action": (
                    "stop" if validation.get("valid") else "fix_errors_and_validate_again"
                ),
            },
            ensure_ascii=False,
        )

    return [
        load_synchronization_context,
        write_ui_schema_core,
        write_ui_schema_pages,
        write_ui_schema_traceability,
        delete_ui_schema_page_file,
        delete_ui_schema_elements,
        validate_ui_schema_state,
    ]


def _plain_model_values(items: list[Any]) -> list[Any]:
    result: list[Any] = []
    for item in items:
        if isinstance(item, BaseModel):
            result.append(item.model_dump())
        else:
            result.append(item)
    return result


def _plain_model_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    return value
