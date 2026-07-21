from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state
from backend.modules.ui_schema import service
from backend.modules.ui_schema.schemas import (
    AppUpdate,
    CodeLinkCreate,
    ElementCreate,
    ElementUpdate,
    PageCreate,
    PageUpdate,
    RequirementLinkCreate,
    UiLinkCreate,
)

router = APIRouter(tags=["ui-schema"])


def assert_access(state: AppState, user: dict, workspace_id: str) -> None:
    if not state.workspaces.user_can_access(user, workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace unavailable")


def module_root_or_403(state: AppState, user: dict, workspace_id: str):
    assert_access(state, user, workspace_id)
    return service.module_root(state, workspace_id)


@router.get("")
def get_summary(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    assert_access(state, user, workspace_id)
    return service.read_summary(state, workspace_id)




@router.get("/app")
def get_app(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    return service.read_app(root)



@router.put("/app")
def put_app(
    payload: AppUpdate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, payload.workspace_id)
    app = service.update_app(root, payload.model_dump(exclude={"workspace_id"}, exclude_none=True))
    return {"app": app}


@router.post("/app/elements")
def post_app_element(
    payload: ElementCreate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, payload.workspace_id)
    try:
        element = service.add_app_element(root, payload.model_dump(exclude={"workspace_id"}, exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"element": element}


@router.put("/app/elements/{element_id}")
def put_app_element(
    element_id: str,
    payload: ElementUpdate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, payload.workspace_id)
    try:
        element = service.update_app_element(root, element_id, payload.model_dump(exclude={"workspace_id"}, exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"element": element}


@router.delete("/app/elements/{element_id}")
def remove_app_element(
    element_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    try:
        service.delete_app_element(root, element_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"deleted": True}

@router.get("/pages")
def get_pages(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    return {"pages": service.list_pages(root)}


@router.get("/pages/{page_id}")
def get_page(
    page_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    page = service.read_page(root, page_id)
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return page


@router.post("/pages")
def post_page(
    payload: PageCreate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, payload.workspace_id)
    try:
        page = service.create_page(root, payload.model_dump(exclude={"workspace_id"}))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"page": page}


@router.put("/pages/{page_id}")
def put_page(
    page_id: str,
    payload: PageUpdate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, payload.workspace_id)
    try:
        page = service.update_page(root, page_id, payload.model_dump(exclude={"workspace_id"}, exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"page": page}


@router.delete("/pages/{page_id}")
def remove_page(
    page_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    try:
        service.delete_page(root, page_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"deleted": True}


@router.post("/pages/{page_id}/elements")
def post_element(
    page_id: str,
    payload: ElementCreate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, payload.workspace_id)
    try:
        element = service.add_element(root, page_id, payload.model_dump(exclude={"workspace_id"}, exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"element": element}


@router.put("/pages/{page_id}/elements/{element_id}")
def put_element(
    page_id: str,
    element_id: str,
    payload: ElementUpdate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, payload.workspace_id)
    try:
        element = service.update_element(root, page_id, element_id, payload.model_dump(exclude={"workspace_id"}, exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"element": element}


@router.delete("/pages/{page_id}/elements/{element_id}")
def remove_element(
    page_id: str,
    element_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    try:
        service.delete_element(root, page_id, element_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"deleted": True}


@router.get("/requirement-links")
def get_requirement_links(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    return service.read_requirement_links(root)


@router.post("/requirement-links")
def post_requirement_link(
    payload: RequirementLinkCreate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, payload.workspace_id)
    link = service.add_requirement_link(root, payload.model_dump(exclude={"workspace_id"}))
    return {"link": link}


@router.delete("/requirement-links/{link_id}")
def remove_requirement_link(
    link_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    service.delete_requirement_link(root, link_id)
    return {"deleted": True}


@router.get("/requirements")
def get_requirements(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    return service.read_requirements(root)


@router.post("/code-links")
def post_code_link(
    payload: CodeLinkCreate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, payload.workspace_id)
    link = service.add_code_link(root, payload.model_dump(exclude={"workspace_id"}))
    return {"link": link}


@router.delete("/code-links/{link_id}")
def remove_code_link(
    link_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    service.delete_code_link(root, link_id)
    return {"deleted": True}


@router.get("/ui-links")
def get_ui_links(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    return service.read_ui_links(root)


@router.post("/ui-links")
def post_ui_link(
    payload: UiLinkCreate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, payload.workspace_id)
    link = service.add_ui_link(root, payload.model_dump(exclude={"workspace_id"}))
    return {"link": link}


@router.delete("/ui-links/{link_id}")
def remove_ui_link(
    link_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = module_root_or_403(state, user, workspace_id)
    service.delete_ui_link(root, link_id)
    return {"deleted": True}
