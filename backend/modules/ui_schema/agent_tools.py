from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.ui_schema.agent_completion import validate_and_mark_completion
from backend.modules.ui_schema.agent_context import build_synchronization_context
from backend.modules.ui_schema.agent_preservation import (
    delete_new_elements,
    normalize_element_ids,
)
from backend.modules.ui_schema.agent_schema_io import (
    delete_page_file,
    recoverable_tool_result,
    write_ui_schema_bundle as write_schema_bundle,
)
from backend.modules.ui_schema.agent_link_tools import (
    UiLinksWriteArgs,
    write_ui_links,
)
from backend.modules.ui_schema.agent_page_tools import (
    PageDocumentArgs,
    PageElementsArgs,
    page_element_limit,
    write_page_document,
    write_page_elements,
)
from backend.modules.ui_schema.agent_tool_payloads import (
    decode_json_argument,
    normalize_core_argument,
    normalize_document_content,
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

    model_config = ConfigDict(extra="forbid")

    @field_validator("app", "schema_document", mode="before")
    @classmethod
    def normalize_json_object(cls, value: Any, info):
        if value is None:
            return None
        file_path = {
            "app": "app.json",
            "schema_document": "schema.json",
        }[info.field_name]
        return normalize_document_content(file_path, value)



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
    maximum_page_elements = page_element_limit(agent_config)

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
    ) -> str:
        """Write changed application metadata/root elements and the page registry.

        Pass native JSON objects, not strings. Omitted documents remain unchanged.
        Write UI navigation only after page files exist by calling write_ui_schema_links.
        Existing pages and elements omitted from updates are preserved by backend.
        """
        return recoverable_tool_result(
            lambda: write_schema_bundle(
                working_root=working_root,
                result_root=result_root,
                files=normalize_core_argument(app=app, schema=schema_document, links=None),
                maximum_files=2,
            )
        )

    @tool(args_schema=PageDocumentArgs)
    def write_ui_schema_page(
        page_id: str,
        title: str,
        description: str = "",
        elements: list[dict[str, Any]] | None = None,
        file_path: str | None = None,
    ) -> str:
        """Write exactly one new or changed page.

        One page per tool call avoids large provider-generated JSON strings. Pass a native
        elements array. For a large page, create a shell with elements=[] and then call
        write_ui_schema_page_elements with a few top-level groups at a time.
        """
        return recoverable_tool_result(
            lambda: write_page_document(
                working_root=working_root,
                result_root=result_root,
                page_id=page_id,
                title=title,
                description=description,
                elements=list(elements or []),
                file_path=file_path,
                maximum_top_level_elements=maximum_page_elements,
            )
        )

    @tool(args_schema=PageElementsArgs)
    def write_ui_schema_page_elements(
        page_id: str,
        elements: list[dict[str, Any]],
    ) -> str:
        """Add or replace a small batch of top-level groups on an existing page.

        Use this after write_ui_schema_page when a complete page payload would be large.
        Existing top-level groups with different IDs are preserved.
        """
        return recoverable_tool_result(
            lambda: write_page_elements(
                working_root=working_root,
                result_root=result_root,
                page_id=page_id,
                elements=elements,
                maximum_top_level_elements=maximum_page_elements,
            )
        )

    @tool(args_schema=UiLinksWriteArgs)
    def write_ui_schema_links(links: list[dict[str, Any]]) -> str:
        """Write UI navigation/modal links after app and page elements exist.

        Pass a native links array. Backend generates missing technical link IDs and can infer
        source/target types only from exact existing page or element IDs.
        """
        return recoverable_tool_result(
            lambda: write_ui_links(
                working_root=working_root,
                result_root=result_root,
                links=links,
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
        write_ui_schema_page,
        write_ui_schema_page_elements,
        write_ui_schema_links,
        write_ui_schema_traceability,
        delete_ui_schema_page_file,
        delete_ui_schema_elements,
        validate_ui_schema_state,
    ]


def _plain_model_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    return value
