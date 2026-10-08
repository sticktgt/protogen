from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.modules.data_schema.agent_addition_removal import remove_run_additions
from backend.modules.data_schema.agent_completion import validate_and_mark_completion
from backend.modules.data_schema.agent_context import build_synchronization_context
from backend.modules.data_schema.agent_traceability_patch import (
    write_complete_requirement_results,
)
from backend.modules.data_schema.agent_schema_patch import (
    patch_dictionaries,
    patch_relations,
    patch_schema_core,
)
from backend.modules.data_schema.agent_schema_patch_models import (
    CorePatchArgs,
    DictionariesPatchArgs,
    DictionaryPatchPayload,
    EntityPatchPayload,
    RelationPatchPayload,
    RelationsPatchArgs,
    SchemaPatchPayload,
)
from backend.modules.data_schema.agent_schema_io import (
    recoverable_tool_result,
    write_dictionaries,
    write_relations,
    write_schema_core,
)
from backend.modules.data_schema.agent_tool_models import (
    CoreWriteArgs,
    DictionariesWriteArgs,
    DictionaryPayload,
    EntityPayload,
    FieldPayload,
    RelationPayload,
    RelationsWriteArgs,
    RemoveAdditionsArgs,
    RequirementResultUpdate,
    RequirementResultsPatchArgs,
    SchemaPayload,
)


def create_agent_tools(
    *,
    run_path: Path,
    agent_config: dict[str, Any],
    allowed_tools: set[str] | None = None,
):
    from langchain.tools import tool

    working_root = run_path / "working" / "data_schema"
    result_root = run_path / "result"

    @tool
    def load_synchronization_context() -> str:
        """Load requirements, the current temporary data schema, constraints and validation errors."""
        return json.dumps(
            build_synchronization_context(run_path),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @tool(args_schema=DictionariesWriteArgs)
    def write_data_schema_dictionaries(dictionaries: list[DictionaryPayload]) -> str:
        """Add or update logical dictionaries and values. Existing base objects are preserved."""
        return recoverable_tool_result(
            lambda: write_dictionaries(
                working_root=working_root,
                dictionaries=[_plain(item) for item in dictionaries],
            )
        )

    @tool(args_schema=CoreWriteArgs)
    def write_data_schema_core(
        entities: list[EntityPayload],
        schema_document: SchemaPayload | None = None,
    ) -> str:
        """Add or update schema metadata, entities and fields. Existing omitted objects are preserved."""
        return recoverable_tool_result(
            lambda: write_schema_core(
                working_root=working_root,
                schema=_plain(schema_document) if schema_document is not None else None,
                entities=[_plain(item) for item in entities],
            )
        )

    @tool(args_schema=RelationsWriteArgs)
    def write_data_schema_relations(relations: list[RelationPayload]) -> str:
        """Add or update logical entity relations after all referenced entities exist."""
        return recoverable_tool_result(
            lambda: write_relations(
                working_root=working_root,
                relations=[_plain(item) for item in relations],
            )
        )

    @tool(args_schema=DictionariesPatchArgs)
    def patch_data_schema_dictionaries(
        dictionaries: list[DictionaryPatchPayload],
    ) -> str:
        """Patch an existing dictionary and patch or add nested values by exact IDs."""
        return recoverable_tool_result(
            lambda: patch_dictionaries(
                working_root=working_root,
                dictionaries=[_plain_patch(item) for item in dictionaries],
            )
        )

    @tool(args_schema=CorePatchArgs)
    def patch_data_schema_core(
        entities: list[EntityPatchPayload],
        schema_patch: SchemaPatchPayload | None = None,
    ) -> str:
        """Patch existing schema metadata and entities; patch or add nested fields by exact IDs."""
        return recoverable_tool_result(
            lambda: patch_schema_core(
                working_root=working_root,
                schema_patch=(
                    _plain_patch(schema_patch) if schema_patch is not None else None
                ),
                entities=[_plain_patch(item) for item in entities],
            )
        )

    @tool(args_schema=RelationsPatchArgs)
    def patch_data_schema_relations(relations: list[RelationPatchPayload]) -> str:
        """Patch existing relations by exact IDs without resending full objects."""
        return recoverable_tool_result(
            lambda: patch_relations(
                working_root=working_root,
                relations=[_plain_patch(item) for item in relations],
            )
        )

    @tool(args_schema=RemoveAdditionsArgs)
    def remove_data_schema_additions(targets: list[str]) -> str:
        """Remove only entities, fields, relations or dictionary items added by this run."""
        return recoverable_tool_result(
            lambda: remove_run_additions(
                run_path=run_path,
                targets=[str(item) for item in targets],
            )
        )


    @tool(args_schema=RequirementResultsPatchArgs)
    def write_data_schema_traceability(
        updates: list[RequirementResultUpdate],
        agent_note: str | None = None,
        warnings: list[str] | None = None,
    ) -> str:
        """Write the complete result for every input requirement in one call.

        Backend checks only exact completeness of requirement IDs and technical
        target references. Semantic classifications and targets are preserved
        exactly as selected by the model.
        """
        return recoverable_tool_result(
            lambda: write_complete_requirement_results(
                run_path=run_path,
                updates=[_plain(item) for item in updates],
                agent_note=agent_note,
                warnings=warnings,
            )
        )



    @tool(return_direct=True)
    def validate_data_schema_state() -> str:
        """Validate the temporary schema and return directly when validation finishes."""
        validation = validate_and_mark_completion(run_path)
        return json.dumps(
            {
                **validation,
                "completed": bool(validation.get("valid")),
                "next_action": "stop" if validation.get("valid") else "fix_errors_and_validate_again",
            },
            ensure_ascii=False,
        )

    tools = [
        load_synchronization_context,
        write_data_schema_dictionaries,
        write_data_schema_core,
        write_data_schema_relations,
        patch_data_schema_dictionaries,
        patch_data_schema_core,
        patch_data_schema_relations,
        remove_data_schema_additions,
        write_data_schema_traceability,
        validate_data_schema_state,
    ]
    if allowed_tools is None:
        return tools
    return [item for item in tools if item.name in allowed_tools]


def _plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True)
    return value


def _plain_patch(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_unset=True)
    return value
