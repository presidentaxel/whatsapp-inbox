from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services.bot_service import generate_playground_assist_reply
from app.services.playground_assist_thread_service import (
    assert_flow_belongs_to_account,
    create_thread,
    get_thread,
    list_threads,
    restore_thread,
    soft_hide_thread,
    update_thread,
)
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


def _require_assist_threads_write(user: CurrentUser, account_id: str) -> None:
    _require_flow_account_access(user, account_id)
    if not user.permissions.has(PermissionCodes.MESSAGES_SEND, account_id):
        raise HTTPException(status_code=403, detail="permission_denied")


@router.post("/assistant")
async def playground_flow_assistant(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Chat assistant pour le mode Playground : explications et proposition de graphe (JSON).
    """
    account_id = payload.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id_required")
    acc = await get_account_by_id(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="account_not_found")
    _require_flow_account_access(current_user, account_id)
    if not current_user.permissions.has(PermissionCodes.MESSAGES_SEND, account_id):
        raise HTTPException(status_code=403, detail="permission_denied")

    flow_id = payload.get("flow_id")
    flow_id_str = str(flow_id).strip() if flow_id else None
    if flow_id_str:
        row = await get_flow_by_id(flow_id_str)
        if not row:
            raise HTTPException(status_code=404, detail="flow_not_found")
        if str(row["account_id"]) != str(account_id):
            raise HTTPException(status_code=400, detail="flow_account_mismatch")

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages_required")

    graph = payload.get("graph")
    if not isinstance(graph, dict):
        graph = {}

    flow_name = payload.get("flow_name")
    name_str = str(flow_name).strip() if isinstance(flow_name, str) else ""

    mode_raw = payload.get("mode")
    mode_str = str(mode_raw).strip().lower() if mode_raw is not None else "agent"

    result = await generate_playground_assist_reply(
        account_id=str(account_id),
        flow_id=flow_id_str,
        flow_name=name_str,
        graph=graph,
        messages=messages,
        mode=mode_str,
    )
    return result


@router.get("/assist-threads")
async def list_assist_threads(
    account_id: str = Query(...),
    flow_id: str = Query(...),
    archived: bool = Query(False, description="True = uniquement les fils masqués (récupération)"),
    current_user: CurrentUser = Depends(get_current_user),
):
    acc = await get_account_by_id(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="account_not_found")
    _require_flow_account_access(current_user, account_id)
    if not await assert_flow_belongs_to_account(flow_id, account_id):
        raise HTTPException(status_code=404, detail="flow_not_found")
    return await list_threads(
        current_user.id,
        account_id,
        flow_id,
        archived_only=archived,
    )


@router.post("/assist-threads")
async def post_assist_thread(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    account_id = payload.get("account_id")
    flow_id = payload.get("flow_id")
    if not account_id or not flow_id:
        raise HTTPException(status_code=400, detail="account_id_and_flow_id_required")
    acc = await get_account_by_id(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="account_not_found")
    _require_assist_threads_write(current_user, account_id)
    if not await assert_flow_belongs_to_account(str(flow_id), str(account_id)):
        raise HTTPException(status_code=404, detail="flow_not_found")
    title = payload.get("title")
    title_str = str(title).strip() if isinstance(title, str) else ""
    messages = payload.get("messages")
    msg_list = messages if isinstance(messages, list) else []
    row = await create_thread(
        current_user.id,
        str(account_id),
        str(flow_id),
        title_str or "Nouvelle discussion",
        msg_list,
    )
    if not row:
        raise HTTPException(status_code=500, detail="create_failed")
    return row


@router.put("/assist-threads/{thread_id}")
async def put_assist_thread(
    thread_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_thread(thread_id, current_user.id)
    if not row:
        raise HTTPException(status_code=404, detail="thread_not_found")
    _require_assist_threads_write(current_user, str(row["account_id"]))
    set_title = "title" in payload
    set_messages = "messages" in payload
    if not set_title and not set_messages:
        raise HTTPException(status_code=400, detail="title_or_messages_required")
    updated = await update_thread(
        thread_id,
        current_user.id,
        title=payload.get("title"),
        messages=payload.get("messages"),
        set_title=set_title,
        set_messages=set_messages,
    )
    if not updated:
        raise HTTPException(status_code=500, detail="update_failed")
    return updated


@router.delete("/assist-threads/{thread_id}")
async def delete_assist_thread(
    thread_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_thread(thread_id, current_user.id)
    if not row:
        raise HTTPException(status_code=404, detail="thread_not_found")
    _require_assist_threads_write(current_user, str(row["account_id"]))
    ok = await soft_hide_thread(thread_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=400, detail="already_hidden_or_not_found")
    return {"status": "ok", "hidden": True}


@router.patch("/assist-threads/{thread_id}/restore")
async def restore_assist_thread(
    thread_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_thread(thread_id, current_user.id)
    if not row:
        raise HTTPException(status_code=404, detail="thread_not_found")
    _require_assist_threads_write(current_user, str(row["account_id"]))
    ok = await restore_thread(thread_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=400, detail="not_hidden_or_not_found")
    out = await get_thread(thread_id, current_user.id)
    return out or {"status": "ok"}


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
