from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.ui_schema.agent_element_batch_tools import (
    PageElementChange,
    PageElementMove,
    move_page_elements_batch,
    write_page_elements_batch,
)
from backend.modules.ui_schema.agent_element_removal import remove_new_elements_batch
from backend.modules.ui_schema.agent_json_arguments import parse_json_array
from backend.modules.ui_schema.agent_link_tools import (
    UiLinkInput,
    remove_new_ui_links_by_id,
    write_ui_links,
)
from backend.modules.ui_schema.agent_move_coordination import (
    coordinate_upserts_with_explicit_moves,
)
from backend.modules.ui_schema.agent_upsert_normalization import flatten_upsert_changes
from backend.modules.ui_schema.agent_page_metadata import update_page_metadata
from backend.modules.ui_schema.agent_page_tools import PageDocumentArgs, write_page_document


class UiSchemaChangeBundleArgs(BaseModel):
    """Apply a coherent technical change set in one transaction."""

    model_config = ConfigDict(extra="forbid")

    create_pages: list[PageDocumentArgs] = Field(
        default_factory=list,
        description="New pages with their coherent initial structures",
    )
    update_pages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Metadata updates for existing pages",
    )
    upsert_elements: list[PageElementChange] = Field(
        default_factory=list,
        description=(
            "Targeted creates and updates across app.json and pages. For a new page "
            "element, omitted parent_id means the page root; a new child must include "
            "an exact parent_id. Root-allowed app elements may omit parent_id. Existing "
            "elements may omit it to keep their parent. Nested children are accepted and "
            "mechanically expanded into ordered targeted upserts; omitted existing children "
            "are preserved and implicit moves remain forbidden."
        ),
    )
    move_elements: list[PageElementMove] = Field(
        default_factory=list,
        description="Explicit parent changes only",
    )
    ui_links: list[UiLinkInput] = Field(
        default_factory=list,
        description=(
            "UI navigation/modal links added or updated by this bundle. "
            "Existing omitted links are preserved."
        ),
    )
    no_changes_reason: str = Field(
        default="",
        description=(
            "Use only when the current managed pipeline batch requires no schema changes. "
            "This advances the workflow without modifying files."
        ),
    )

    @field_validator(
        "create_pages",
        "update_pages",
        "upsert_elements",
        "move_elements",
        "ui_links",
        mode="before",
    )
    @classmethod
    def _decode_json_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)



def apply_ui_schema_change_bundle(
    *,
    working_root: Path,
    result_root: Path,
    create_pages: list[PageDocumentArgs | dict[str, Any]],
    upsert_elements: list[PageElementChange | dict[str, Any]],
    move_elements: list[PageElementMove | dict[str, Any]],
    ui_links: list[UiLinkInput | dict[str, Any]],
    no_changes_reason: str = "",
    maximum_pages: int,
    maximum_top_level_elements: int,
    maximum_element_changes: int,
    maximum_moves: int,
    maximum_links: int,
    update_pages: list[dict[str, Any]] | None = None,
    remove_elements: list[str] | None = None,
    remove_ui_links: list[str] | None = None,
    base_root: Path | None = None,
    maximum_removals: int = 0,
) -> dict[str, Any]:
    page_updates = list(update_pages or [])
    element_removals = [str(item or "").strip() for item in (remove_elements or [])]
    element_removals = [item for item in dict.fromkeys(element_removals) if item]
    link_removals = [str(item or "").strip() for item in (remove_ui_links or [])]
    link_removals = [item for item in dict.fromkeys(link_removals) if item]
    if len(create_pages) + len(page_updates) > maximum_pages:
        raise ValueError(
            f"create_pages and update_pages may contain at most {maximum_pages} pages in one bundle"
        )
    upsert_elements = flatten_upsert_changes(list(upsert_elements))
    if len(upsert_elements) > maximum_element_changes:
        raise ValueError(
            f"upsert_elements may contain at most {maximum_element_changes} operations"
        )
    if len(move_elements) > maximum_moves:
        raise ValueError(
            f"move_elements may contain at most {maximum_moves} operations"
        )
    if len(ui_links) > maximum_links:
        raise ValueError(f"ui_links may contain at most {maximum_links} links")
    if len(link_removals) > maximum_links:
        raise ValueError(f"remove_ui_links может содержать не более {maximum_links} ID связей")
    changed_link_ids = {
        str(item.id or "").strip() if isinstance(item, UiLinkInput) else str(item.get("id") or "").strip()
        for item in ui_links
    }
    link_overlap = sorted(set(link_removals) & {item for item in changed_link_ids if item})
    if link_overlap:
        raise ValueError(
            "Одну UI-связь нельзя одновременно обновить и удалить в одном пакете: "
            + ", ".join(link_overlap)
        )
    if link_removals and base_root is None:
        raise ValueError("base_root обязателен при использовании remove_ui_links")
    if element_removals:
        if base_root is None:
            raise ValueError("base_root is required when remove_elements is used")
        if maximum_removals <= 0:
            raise ValueError("maximum_removals must be positive when remove_elements is used")
        if len(element_removals) > maximum_removals:
            raise ValueError(
                f"remove_elements may contain at most {maximum_removals} element IDs"
            )
        changed_ids = {
            (
                item.element.id
                if isinstance(item, PageElementChange)
                else str((item.get("element") or {}).get("id") or "")
            )
            for item in upsert_elements
        }
        overlap = sorted(set(element_removals) & changed_ids)
        if overlap:
            raise ValueError(
                "The same element cannot be upserted and removed in one bundle: "
                + ", ".join(overlap)
            )

    has_operations = any(
        (
            create_pages,
            page_updates,
            upsert_elements,
            move_elements,
            ui_links,
            element_removals,
            link_removals,
        )
    )
    reason = str(no_changes_reason or "").strip()
    if not has_operations:
        if not reason:
            raise ValueError("At least one change operation or no_changes_reason is required")
        return {
            "ok": True,
            "message": "No UI Schema file changes were requested",
            "no_changes": True,
            "no_changes_reason": reason,
            "created_pages": [],
            "created_page_count": 0,
            "updated_pages": [],
            "updated_page_count": 0,
            "element_change_count": 0,
            "move_count": 0,
            "ui_link_count": 0,
            "removed_ui_link_count": 0,
            "removed_ui_link_ids": [],
            "removed_element_count": 0,
            "removed_element_ids": [],
            "touched_target_ids": [],
        }
    if reason:
        raise ValueError("no_changes_reason must be omitted when change operations are present")

    with tempfile.TemporaryDirectory(prefix="ui_schema_bundle_") as temporary:
        snapshot = Path(temporary) / "working"
        shutil.copytree(working_root, snapshot)
        try:
            page_results: list[dict[str, Any]] = []
            for raw_page in create_pages:
                page = (
                    raw_page
                    if isinstance(raw_page, PageDocumentArgs)
                    else PageDocumentArgs.model_validate(raw_page)
                )
                page_results.append(
                    write_page_document(
                        working_root=working_root,
                        result_root=result_root,
                        page_id=page.page_id,
                        title=page.title,
                        description=page.description,
                        elements=page.elements,
                        file_path=page.file_path,
                        maximum_top_level_elements=maximum_top_level_elements,
                    )
                )

            page_update_results: list[dict[str, Any]] = []
            for item in page_updates:
                if not isinstance(item, dict):
                    raise ValueError("Each update_pages item must be an object")
                page_id = str(item.get("page_id") or "").strip()
                if not page_id:
                    raise ValueError("Each update_pages item requires page_id")
                title = item.get("title")
                description = item.get("description")
                if title is None and description is None:
                    raise ValueError(
                        f"update_pages item {page_id} requires title or description"
                    )
                page_update_results.append(
                    update_page_metadata(
                        working_root=working_root,
                        page_id=page_id,
                        title=str(title) if title is not None else None,
                        description=(
                            str(description) if description is not None else None
                        ),
                    )
                )

            coordinated_upserts = coordinate_upserts_with_explicit_moves(
                working_root=working_root,
                upsert_elements=upsert_elements,
                move_elements=move_elements,
            )

            element_result: dict[str, Any] | None = None
            if coordinated_upserts:
                element_result = write_page_elements_batch(
                    working_root=working_root,
                    changes=coordinated_upserts,
                    maximum_changes=maximum_element_changes,
                )

            move_result: dict[str, Any] | None = None
            if move_elements:
                move_result = move_page_elements_batch(
                    working_root=working_root,
                    moves=move_elements,
                    maximum_changes=maximum_moves,
                )

            link_result: dict[str, Any] | None = None
            if ui_links:
                link_result = write_ui_links(
                    working_root=working_root,
                    result_root=result_root,
                    links=ui_links,
                )

            link_removal_result: dict[str, Any] | None = None
            if link_removals:
                link_removal_result = remove_new_ui_links_by_id(
                    base_root=base_root,
                    working_root=working_root,
                    result_root=result_root,
                    link_ids=link_removals,
                )

            removal_result: dict[str, Any] | None = None
            if element_removals:
                removal_result = remove_new_elements_batch(
                    base_root=base_root,
                    working_root=working_root,
                    element_ids=element_removals,
                    maximum_removals=maximum_removals,
                )
        except Exception:
            shutil.rmtree(working_root)
            shutil.copytree(snapshot, working_root)
            raise

    created_page_ids = [
        page.page_id if isinstance(page, PageDocumentArgs) else str(page.get("page_id") or "")
        for page in create_pages
    ]
    updated_page_ids = [
        str(item.get("page_id") or "")
        for item in page_updates
        if isinstance(item, dict) and str(item.get("page_id") or "")
    ]
    touched_element_ids = [
        (
            change.element.id
            if isinstance(change, PageElementChange)
            else str((change.get("element") or {}).get("id") or "")
        )
        for change in upsert_elements
    ]
    touched_parent_ids = [
        (
            str(change.parent_id or "")
            if isinstance(change, PageElementChange)
            else str(change.get("parent_id") or "")
        )
        for change in upsert_elements
    ]
    moved_element_ids = [
        move.element_id if isinstance(move, PageElementMove) else str(move.get("element_id") or "")
        for move in move_elements
    ]
    moved_parent_ids: list[str] = []
    for result in (move_result or {}).get("moves", []):
        if not isinstance(result, dict):
            continue
        moved_parent_ids.extend(
            str(result.get(key) or "")
            for key in ("from_parent_id", "to_parent_id")
        )
    touched_page_ids = {
        (
            change.page_id
            if isinstance(change, PageElementChange)
            else str(change.get("page_id") or "")
        )
        for change in upsert_elements
    }
    touched_page_ids.update(
        move.page_id if isinstance(move, PageElementMove) else str(move.get("page_id") or "")
        for move in move_elements
    )
    touched_page_ids.discard("")
    touched_page_ids.discard("app")
    return {
        "ok": True,
        "message": "Applied one transactional UI Schema change bundle",
        "created_pages": [item for item in created_page_ids if item],
        "created_page_count": len(page_results),
        "updated_pages": updated_page_ids,
        "updated_page_count": len(page_update_results),
        "element_change_count": int((element_result or {}).get("change_count", 0)),
        "move_count": int((move_result or {}).get("move_count", 0)),
        "ui_link_count": len(ui_links),
        "removed_ui_link_count": int(
            (link_removal_result or {}).get("removed_ui_link_count", 0)
        ),
        "removed_ui_link_ids": list(
            (link_removal_result or {}).get("removed_ui_link_ids", [])
        ),
        "removed_element_count": int(
            (removal_result or {}).get("removed_element_count", 0)
        ),
        "removed_element_ids": list(
            (removal_result or {}).get("removed_element_ids", [])
        ),
        "touched_target_ids": sorted(
            {
                *[item for item in created_page_ids if item],
                *[item for item in updated_page_ids if item],
                *[item for item in touched_element_ids if item],
                *[item for item in touched_parent_ids if item and item != "app"],
                *[item for item in moved_element_ids if item],
                *[item for item in moved_parent_ids if item and item != "app"],
                *touched_page_ids,
                *element_removals,
            }
        ),
    }


def change_bundle_limits(agent_config: dict[str, Any]) -> dict[str, int]:
    execution = agent_config.get("execution", {}) if isinstance(agent_config, dict) else {}
    execution = execution if isinstance(execution, dict) else {}
    return {
        "pages": _positive_int(execution.get("apply_change_bundle_max_pages"), 8),
        "moves": _positive_int(execution.get("apply_change_bundle_max_moves"), 40),
        "links": _positive_int(execution.get("apply_change_bundle_max_links"), 120),
        "removals": _positive_int(
            execution.get("apply_change_bundle_max_removals"), 30
        ),
    }


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
