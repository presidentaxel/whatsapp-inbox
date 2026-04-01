from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services.playground_flow_service import (
    append_subgraph_to_flow,
    create_flow,
    delete_flow,
    duplicate_flow,
    get_flow_by_id,
    list_playground_flows_with_default_flag,
    set_default_flow,
    update_flow,
)

router = APIRouter()


def _require_flow_account_access(user: CurrentUser, account_id: str) -> None:
    user.require(PermissionCodes.CONVERSATIONS_VIEW, account_id)


@router.get("")
async def list_flows(
    account_id: str = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    acc = await get_account_by_id(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="account_not_found")
    _require_flow_account_access(current_user, account_id)
    return await list_playground_flows_with_default_flag(account_id)


@router.get("/{flow_id}")
async def get_flow(
    flow_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    _require_flow_account_access(current_user, str(row["account_id"]))
    return row


@router.post("")
async def create_playground_flow(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    account_id = payload.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id_required")
    acc = await get_account_by_id(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="account_not_found")
    _require_flow_account_access(current_user, account_id)
    name = (payload.get("name") or "Nouveau flux").strip()
    graph = payload.get("graph")
    row = await create_flow(account_id, name, graph)
    if not row:
        raise HTTPException(status_code=500, detail="create_failed")
    return row


@router.put("/{flow_id}")
async def put_flow(
    flow_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    _require_flow_account_access(current_user, str(row["account_id"]))
    if not current_user.permissions.has(PermissionCodes.MESSAGES_SEND, str(row["account_id"])):
        raise HTTPException(status_code=403, detail="permission_denied")
    set_name = "name" in payload
    set_graph = "graph" in payload
    if not set_name and not set_graph:
        raise HTTPException(status_code=400, detail="name_or_graph_required")
    updated = await update_flow(
        flow_id,
        name=payload.get("name"),
        graph=payload.get("graph"),
        set_name=set_name,
        set_graph=set_graph,
    )
    if not updated:
        raise HTTPException(status_code=500, detail="update_failed")
    return updated


@router.delete("/{flow_id}")
async def remove_flow(
    flow_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    aid = str(row["account_id"])
    _require_flow_account_access(current_user, aid)
    if not current_user.permissions.has(PermissionCodes.MESSAGES_SEND, aid):
        raise HTTPException(status_code=403, detail="permission_denied")
    ok = await delete_flow(flow_id)
    if not ok:
        raise HTTPException(status_code=500, detail="delete_failed")
    return {"status": "ok"}


@router.post("/{flow_id}/set-default")
async def make_default(
    flow_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    aid = str(row["account_id"])
    _require_flow_account_access(current_user, aid)
    if not current_user.permissions.has(PermissionCodes.MESSAGES_SEND, aid):
        raise HTTPException(status_code=403, detail="permission_denied")
    ok = await set_default_flow(aid, flow_id)
    if not ok:
        raise HTTPException(status_code=400, detail="set_default_failed")
    return {"status": "ok", "default_playground_flow_id": flow_id}


@router.post("/duplicate")
async def duplicate_playground_flow(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    source_flow_id = payload.get("source_flow_id")
    target_account_id = payload.get("target_account_id")
    name = payload.get("name")
    node_ids = payload.get("node_ids")  # optionnel = sous-graphe
    if not source_flow_id or not target_account_id:
        raise HTTPException(status_code=400, detail="source_flow_id_and_target_account_id_required")
    src = await get_flow_by_id(source_flow_id)
    if not src:
        raise HTTPException(status_code=404, detail="flow_not_found")
    _require_flow_account_access(current_user, str(src["account_id"]))
    tgt_acc = await get_account_by_id(target_account_id)
    if not tgt_acc:
        raise HTTPException(status_code=404, detail="target_account_not_found")
    _require_flow_account_access(current_user, target_account_id)
    if not current_user.permissions.has(PermissionCodes.MESSAGES_SEND, target_account_id):
        raise HTTPException(status_code=403, detail="permission_denied_target")
    subgraph = None
    if isinstance(node_ids, list) and node_ids:
        subgraph = [str(x) for x in node_ids]
    created = await duplicate_flow(source_flow_id, target_account_id, name=name, subgraph_node_ids=subgraph)
    if not created:
        raise HTTPException(status_code=500, detail="duplicate_failed")
    return created


@router.post("/{flow_id}/paste-subgraph")
async def paste_subgraph(
    flow_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    aid = str(row["account_id"])
    _require_flow_account_access(current_user, aid)
    if not current_user.permissions.has(PermissionCodes.MESSAGES_SEND, aid):
        raise HTTPException(status_code=403, detail="permission_denied")
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise HTTPException(status_code=400, detail="nodes_and_edges_arrays_required")
    updated = await append_subgraph_to_flow(flow_id, nodes, edges)
    if not updated:
        raise HTTPException(status_code=500, detail="paste_failed")
    return updated
