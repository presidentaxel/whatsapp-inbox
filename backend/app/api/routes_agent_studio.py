from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.schemas.agent_studio import (
    AgentStudioConfigUpsert,
    AgentStudioSimulateRequest,
    AgentStudioValidateResult,
)
from app.services.account_service import get_account_by_id
from app.services.agent_studio_service import (
    can_deploy_agent_config,
    create_agent_config,
    create_release,
    get_agent_config,
    list_agent_configs,
    map_config_to_runtime_graph,
    rollback_release,
    set_agent_default,
    simulate_agent_route,
    update_agent_config,
    validate_agent_config,
)

router = APIRouter(prefix="/agent-studio", tags=["Agent Studio"])


def require_agent_studio_access(current_user: CurrentUser = Depends(get_current_user)) -> None:
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS)


@router.get("/configs")
async def get_configs(
    account_id: str = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, account_id)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, account_id)
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    rows = await list_agent_configs(account_id)
    return {"items": rows}


@router.get("/configs/{config_id}")
async def get_config(
    config_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    row = await get_agent_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="config_not_found")
    aid = str(row["account_id"])
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, aid)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, aid)
    return row


@router.post("/configs")
async def post_config(
    body: AgentStudioConfigUpsert,
    current_user: CurrentUser = Depends(get_current_user),
):
    account = await get_account_by_id(body.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, body.account_id)
    current_user.require(PermissionCodes.MESSAGES_SEND, body.account_id)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, body.account_id)
    row = await create_agent_config(
        account_id=body.account_id,
        config=body.config.model_dump(mode="json"),
        user_id=current_user.id,
    )
    if not row:
        raise HTTPException(status_code=500, detail="create_failed")
    return row


@router.put("/configs/{config_id}")
async def put_config(
    config_id: str,
    body: AgentStudioConfigUpsert,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_agent_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="config_not_found")
    aid = str(row["account_id"])
    if aid != str(body.account_id):
        raise HTTPException(status_code=400, detail="account_id_mismatch")
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, aid)
    current_user.require(PermissionCodes.MESSAGES_SEND, aid)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, aid)
    out = await update_agent_config(
        config_id=config_id,
        config=body.config.model_dump(mode="json"),
        user_id=current_user.id,
    )
    if not out:
        raise HTTPException(status_code=500, detail="update_failed")
    return out


@router.post("/configs/{config_id}/set-default")
async def post_set_default(
    config_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    row = await get_agent_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="config_not_found")
    aid = str(row["account_id"])
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, aid)
    current_user.require(PermissionCodes.MESSAGES_SEND, aid)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, aid)
    ok = await set_agent_default(config_id, aid)
    if not ok:
        raise HTTPException(status_code=500, detail="set_default_failed")
    return {"status": "ok", "default_agent_config_id": config_id}


@router.post("/configs/{config_id}/validate", response_model=AgentStudioValidateResult)
async def post_validate(
    config_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    row = await get_agent_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="config_not_found")
    aid = str(row["account_id"])
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, aid)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, aid)
    issues = validate_agent_config(row.get("config") or {})
    has_error = any(str(i.get("severity")) == "error" for i in issues)
    return AgentStudioValidateResult(ok=not has_error, issues=issues)


@router.post("/configs/{config_id}/simulate")
async def post_simulate(
    config_id: str,
    body: AgentStudioSimulateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_agent_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="config_not_found")
    aid = str(row["account_id"])
    if aid != str(body.account_id):
        raise HTTPException(status_code=400, detail="account_id_mismatch")
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, aid)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, aid)
    simulation = simulate_agent_route(row.get("config") or {}, body.input_text)
    return {"status": "ok", "simulation": simulation}


@router.get("/configs/{config_id}/runtime-graph")
async def get_runtime_graph(
    config_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    row = await get_agent_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="config_not_found")
    aid = str(row["account_id"])
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, aid)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, aid)
    graph = map_config_to_runtime_graph(row.get("config") or {})
    return {"graph": graph}


@router.post("/configs/{config_id}/deploy/canary")
async def post_deploy_canary(
    config_id: str,
    canary_percent: int = Query(..., ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_agent_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="config_not_found")
    aid = str(row["account_id"])
    current_user.require(PermissionCodes.MESSAGES_SEND, aid)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, aid)
    cfg = row.get("config") or {}
    dep = dict((cfg.get("deployment") or {}))
    dep["status"] = "canary"
    dep["canary_percent"] = int(canary_percent)
    cfg["deployment"] = dep
    deployable, issues = can_deploy_agent_config(cfg)
    if not deployable:
        raise HTTPException(status_code=400, detail={"code": "config_not_deployable", "issues": issues})
    await update_agent_config(config_id, cfg, current_user.id)
    try:
        release = await create_release(config_id, aid, "canary", current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "release": release}


@router.post("/configs/{config_id}/deploy/activate")
async def post_deploy_activate(
    config_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    row = await get_agent_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="config_not_found")
    aid = str(row["account_id"])
    current_user.require(PermissionCodes.MESSAGES_SEND, aid)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, aid)
    deployable, issues = can_deploy_agent_config(row.get("config") or {})
    if not deployable:
        raise HTTPException(status_code=400, detail={"code": "config_not_deployable", "issues": issues})
    try:
        release = await create_release(config_id, aid, "activate", current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "release": release}


@router.post("/configs/{config_id}/deploy/pause")
async def post_deploy_pause(
    config_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    row = await get_agent_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="config_not_found")
    aid = str(row["account_id"])
    current_user.require(PermissionCodes.MESSAGES_SEND, aid)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, aid)
    try:
        release = await create_release(config_id, aid, "pause", current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "release": release}


@router.post("/configs/{config_id}/deploy/rollback/{release_id}")
async def post_deploy_rollback(
    config_id: str,
    release_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_agent_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="config_not_found")
    aid = str(row["account_id"])
    current_user.require(PermissionCodes.MESSAGES_SEND, aid)
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS, aid)
    ok, code = await rollback_release(config_id, release_id, current_user.id)
    if not ok:
        st = 404 if code in ("config_not_found", "release_not_found") else 400
        raise HTTPException(status_code=st, detail=code)
    return {"status": "ok"}

