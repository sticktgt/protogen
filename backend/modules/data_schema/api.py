from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state
from backend.modules.data_schema import service
from backend.modules.data_schema.agent_api import router as agent_router
from backend.modules.data_schema.agent_paths import run_root
from backend.modules.data_schema.agent_runs import (
    SchemaLocked,
    ensure_schema_writable,
    get_run,
    resolve_preview_root,
)
from backend.modules.data_schema.files import read_json
from backend.modules.data_schema.requirements_source import read_preview_requirements
from backend.modules.data_schema.schemas import (
    CodeLinkCreate,
    EntityCreate,
    EntityUpdate,
    ExternalLinkCreate,
    FieldCreate,
    FieldUpdate,
    RelationCreate,
    RelationUpdate,
    RequirementLinkCreate,
    SchemaUpdate,
)

router = APIRouter(tags=["data-schema"])
router.include_router(agent_router)


def assert_access(state: AppState, user: dict, workspace_id: str) -> None:
    if not state.workspaces.user_can_access(user, workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace unavailable")


def module_root_or_403(
    state: AppState,
    user: dict,
    workspace_id: str,
    *,
    write: bool = False,
):
    assert_access(state, user, workspace_id)
    root = service.module_root(state, workspace_id)
    if write:
        try:
            ensure_schema_writable(root)
        except SchemaLocked as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": str(exc), "run_id": exc.run.get("run_id")},
            ) from exc
    return root


def read_root_or_preview(
    state: AppState,
    user: dict,
    workspace_id: str,
    preview_run_id: str | None,
):
    root = module_root_or_403(state, user, workspace_id)
    if not preview_run_id:
        return root
    try:
        return resolve_preview_root(root, preview_run_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _data_schema_agent_config(state: AppState) -> dict:
    module_config = state.config.read_module_runtime_config("data_schema") or {}
    if not isinstance(module_config, dict):
        return {}
    agent = module_config.get("agent", {})
    return agent if isinstance(agent, dict) else {}


def _configured_requirements_max_bytes(config: dict) -> int:
    requirements = config.get("requirements", {}) if isinstance(config, dict) else {}
    value = requirements.get("max_bytes") if isinstance(requirements, dict) else None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="agent.requirements.max_bytes must be configured as a positive integer",
        ) from exc
    if parsed <= 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="agent.requirements.max_bytes must be configured as a positive integer",
        )
    return parsed


@router.get("")
def get_summary(
    workspace_id: str = Query(...),
    preview_run_id: str | None = Query(None),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    module_root = module_root_or_403(state, user, workspace_id)
    if not preview_run_id:
        config = _data_schema_agent_config(state)
        return service.read_summary(
            module_root,
            requirements_max_bytes=_configured_requirements_max_bytes(config),
        )
    root = read_root_or_preview(state, user, workspace_id, preview_run_id)
    run = get_run(module_root, preview_run_id)
    run_path = run_root(module_root, preview_run_id)
    requirements, source = read_preview_requirements(run_path, run)
    changes = read_json(run_path / "result" / "changes.json", {})
    return service.read_summary_from_root(
        root,
        requirements=requirements,
        requirements_source=source,
        preview_changes=changes,
    )


@router.get("/schema")
def get_schema(
    workspace_id: str = Query(...),
    preview_run_id: str | None = Query(None),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    return service.read_schema(read_root_or_preview(state, user, workspace_id, preview_run_id))


@router.put("/schema")
def put_schema(payload: SchemaUpdate, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, payload.workspace_id, write=True)
    schema = service.update_schema(root, payload.model_dump(exclude={"workspace_id"}, exclude_none=True))
    return {"schema": schema}


@router.get("/entities")
def get_entities(
    workspace_id: str = Query(...),
    preview_run_id: str | None = Query(None),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    return {"entities": service.list_entities(read_root_or_preview(state, user, workspace_id, preview_run_id))}


@router.get("/entities/{entity_id}")
def get_entity(
    entity_id: str,
    workspace_id: str = Query(...),
    preview_run_id: str | None = Query(None),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    entity = service.read_entity(read_root_or_preview(state, user, workspace_id, preview_run_id), entity_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    return entity


@router.post("/entities")
def post_entity(payload: EntityCreate, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, payload.workspace_id, write=True)
    try:
        entity = service.create_entity(root, payload.model_dump(exclude={"workspace_id"}))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"entity": entity}


@router.put("/entities/{entity_id}")
def put_entity(entity_id: str, payload: EntityUpdate, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, payload.workspace_id, write=True)
    try:
        entity = service.update_entity(root, entity_id, payload.model_dump(exclude={"workspace_id"}, exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"entity": entity}


@router.delete("/entities/{entity_id}")
def remove_entity(entity_id: str, workspace_id: str = Query(...), user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, workspace_id, write=True)
    try:
        service.delete_entity(root, entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"deleted": True}


@router.post("/entities/{entity_id}/fields")
def post_field(entity_id: str, payload: FieldCreate, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, payload.workspace_id, write=True)
    try:
        field = service.add_field(root, entity_id, payload.model_dump(exclude={"workspace_id"}, exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"field": field}


@router.put("/entities/{entity_id}/fields/{field_id}")
def put_field(entity_id: str, field_id: str, payload: FieldUpdate, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, payload.workspace_id, write=True)
    try:
        field = service.update_field(root, entity_id, field_id, payload.model_dump(exclude={"workspace_id"}, exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"field": field}


@router.delete("/entities/{entity_id}/fields/{field_id}")
def remove_field(entity_id: str, field_id: str, workspace_id: str = Query(...), user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, workspace_id, write=True)
    try:
        service.delete_field(root, entity_id, field_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"deleted": True}


@router.get("/relations")
def get_relations(
    workspace_id: str = Query(...),
    preview_run_id: str | None = Query(None),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    return service.read_relations(read_root_or_preview(state, user, workspace_id, preview_run_id))


@router.post("/relations")
def post_relation(payload: RelationCreate, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, payload.workspace_id, write=True)
    try:
        relation = service.create_relation(root, payload.model_dump(exclude={"workspace_id"}))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"relation": relation}


@router.put("/relations/{relation_id}")
def put_relation(relation_id: str, payload: RelationUpdate, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, payload.workspace_id, write=True)
    try:
        relation = service.update_relation(root, relation_id, payload.model_dump(exclude={"workspace_id"}, exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"relation": relation}


@router.delete("/relations/{relation_id}")
def remove_relation(relation_id: str, workspace_id: str = Query(...), user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, workspace_id, write=True)
    try:
        service.delete_relation(root, relation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"deleted": True}


@router.get("/requirements")
def get_requirements(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    config = _data_schema_agent_config(state)
    return service.read_requirements(
        module_root_or_403(state, user, workspace_id),
        max_bytes=_configured_requirements_max_bytes(config),
    )


@router.post("/requirement-links")
def post_requirement_link(payload: RequirementLinkCreate, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, payload.workspace_id, write=True)
    return {"link": service.add_requirement_link(root, payload.model_dump(exclude={"workspace_id"}))}


@router.delete("/requirement-links/{link_id}")
def remove_requirement_link(link_id: str, workspace_id: str = Query(...), user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, workspace_id, write=True)
    service.delete_requirement_link(root, link_id)
    return {"deleted": True}


@router.post("/ui-links")
def post_ui_link(payload: ExternalLinkCreate, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, payload.workspace_id, write=True)
    return {"link": service.add_ui_link(root, payload.model_dump(exclude={"workspace_id"}))}


@router.delete("/ui-links/{link_id}")
def remove_ui_link(link_id: str, workspace_id: str = Query(...), user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, workspace_id, write=True)
    service.delete_ui_link(root, link_id)
    return {"deleted": True}


@router.post("/api-links")
def post_api_link(payload: ExternalLinkCreate, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, payload.workspace_id, write=True)
    return {"link": service.add_api_link(root, payload.model_dump(exclude={"workspace_id"}))}


@router.delete("/api-links/{link_id}")
def remove_api_link(link_id: str, workspace_id: str = Query(...), user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, workspace_id, write=True)
    service.delete_api_link(root, link_id)
    return {"deleted": True}


@router.post("/code-links")
def post_code_link(payload: CodeLinkCreate, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, payload.workspace_id, write=True)
    return {"link": service.add_code_link(root, payload.model_dump(exclude={"workspace_id"}))}


@router.delete("/code-links/{link_id}")
def remove_code_link(link_id: str, workspace_id: str = Query(...), user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    root = module_root_or_403(state, user, workspace_id, write=True)
    service.delete_code_link(root, link_id)
    return {"deleted": True}
