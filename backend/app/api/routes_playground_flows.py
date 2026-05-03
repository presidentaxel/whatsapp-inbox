from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services.conversation_service import (
    ensure_playground_sandbox_conversation,
    get_conversation_by_id_fresh,
    reset_playground_sandbox_session,
    set_conversation_bot_mode,
    set_conversation_playground_flow,
)
from app.services.message_service import (
    simulate_playground_campaign_launch,
    simulate_playground_sandbox_inbound,
)
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
from app.services.broadcast_service import parse_broadcast_import_csv
from app.services.playground_flow_service import (
    append_subgraph_to_flow,
    create_flow,
    create_scheduled_flow_launch,
    delete_flow,
    duplicate_flow,
    find_playground_audience_start_node_id,
    get_flow_by_id,
    import_playground_flow_audience as run_playground_audience_import,
    is_playground_audience_start_node,
    list_playground_flows_with_default_flag,
    set_default_flow,
    update_flow,
)

def require_playground_hub_access(current_user: CurrentUser = Depends(get_current_user)) -> None:
    """Toutes les routes Playground exigent la permission globale playground.access."""
    current_user.require(PermissionCodes.PLAYGROUND_ACCESS)


router = APIRouter(dependencies=[Depends(require_playground_hub_access)])


@router.post("/{flow_id}/sandbox-session")
async def playground_sandbox_session(
    flow_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Crée ou réinitialise la conversation de test (numéro réservé) pour le scénario."""
    account_id = payload.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id_required")
    acc = await get_account_by_id(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="account_not_found")
    _require_flow_account_access(current_user, account_id)
    if not current_user.permissions.has(PermissionCodes.MESSAGES_SEND, account_id):
        raise HTTPException(status_code=403, detail="permission_denied")
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    if str(row["account_id"]) != str(account_id):
        raise HTTPException(status_code=400, detail="flow_account_mismatch")
    conv = await ensure_playground_sandbox_conversation(account_id, flow_id)
    if not conv:
        raise HTTPException(status_code=500, detail="sandbox_conversation_failed")
    return {
        "conversation_id": str(conv["id"]),
        "client_number": conv.get("client_number"),
        "conversation": conv,
    }


@router.post("/{flow_id}/sandbox-reset")
async def playground_sandbox_reset(
    flow_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Efface les messages et réinitialise l'état du flux sur la conversation bac à sable."""
    account_id = payload.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id_required")
    acc = await get_account_by_id(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="account_not_found")
    _require_flow_account_access(current_user, account_id)
    if not current_user.permissions.has(PermissionCodes.MESSAGES_SEND, account_id):
        raise HTTPException(status_code=403, detail="permission_denied")
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    if str(row["account_id"]) != str(account_id):
        raise HTTPException(status_code=400, detail="flow_account_mismatch")
    conv = await reset_playground_sandbox_session(account_id, flow_id)
    if not conv:
        raise HTTPException(status_code=500, detail="sandbox_reset_failed")
    return {
        "status": "ok",
        "conversation_id": str(conv["id"]),
        "conversation": conv,
    }


@router.post("/{flow_id}/simulate-inbound")
async def playground_simulate_inbound(
    flow_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Simule un message entrant (client) pour exécuter le scénario Playground.
    Les réponses sortantes sont envoyées comme d'habitude via l'API WhatsApp.
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
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    if str(row["account_id"]) != str(account_id):
        raise HTTPException(status_code=400, detail="flow_account_mismatch")

    message_text = (payload.get("message_text") or "").strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="message_text_required")

    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        conv = await ensure_playground_sandbox_conversation(account_id, flow_id)
        if not conv:
            raise HTTPException(status_code=500, detail="sandbox_conversation_failed")
        conversation_id = str(conv["id"])
    else:
        c = await get_conversation_by_id_fresh(str(conversation_id))
        if not c or str(c["account_id"]) != str(account_id):
            raise HTTPException(status_code=400, detail="invalid_conversation")
        await set_conversation_bot_mode(str(conversation_id), True, "playground")
        await set_conversation_playground_flow(str(conversation_id), flow_id)

    br = payload.get("button_reply")
    if isinstance(br, dict) and (br.get("id") or br.get("title")):
        bid = str(br.get("id") or "").strip()
        title = str(br.get("title") or message_text).strip()
        wa_message = {
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": bid or title, "title": title},
            },
        }
        mt = "interactive"
    else:
        wa_message = {"type": "text", "text": {"body": message_text}}
        mt = "text"

    flow_trace: list = []
    try:
        await simulate_playground_sandbox_inbound(
            str(conversation_id),
            message_text,
            message_type=mt,
            wa_message=wa_message,
            flow_trace=flow_trace,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve

    return {
        "status": "ok",
        "conversation_id": str(conversation_id),
        "flow_trace": flow_trace,
    }


@router.post("/{flow_id}/simulate-inbound-batch")
async def playground_simulate_inbound_batch(
    flow_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Enchaîne plusieurs messages simulés sur la même conversation bac à sable (jeu de phrases de test).
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
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    if str(row["account_id"]) != str(account_id):
        raise HTTPException(status_code=400, detail="flow_account_mismatch")

    phrases_raw = payload.get("phrases")
    if not isinstance(phrases_raw, list):
        raise HTTPException(status_code=400, detail="phrases_required")
    lines = [str(p).strip() for p in phrases_raw if str(p).strip()][:25]
    if not lines:
        raise HTTPException(status_code=400, detail="phrases_empty")

    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        conv = await ensure_playground_sandbox_conversation(account_id, flow_id)
        if not conv:
            raise HTTPException(status_code=500, detail="sandbox_conversation_failed")
        conversation_id = str(conv["id"])
    else:
        c = await get_conversation_by_id_fresh(str(conversation_id))
        if not c or str(c["account_id"]) != str(account_id):
            raise HTTPException(status_code=400, detail="invalid_conversation")
        await set_conversation_bot_mode(str(conversation_id), True, "playground")
        await set_conversation_playground_flow(str(conversation_id), flow_id)

    results: List[Dict[str, Any]] = []
    for line in lines:
        trace: List[Dict[str, Any]] = []
        try:
            await simulate_playground_sandbox_inbound(
                str(conversation_id),
                line,
                message_type="text",
                wa_message={"type": "text", "text": {"body": line}},
                flow_trace=trace,
            )
            results.append(
                {"message_text": line, "flow_trace": trace, "ok": True}
            )
        except ValueError as ve:
            results.append(
                {
                    "message_text": line,
                    "flow_trace": trace,
                    "ok": False,
                    "error": str(ve),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "message_text": line,
                    "flow_trace": trace,
                    "ok": False,
                    "error": str(exc),
                }
            )

    return {
        "status": "ok",
        "conversation_id": str(conversation_id),
        "results": results,
    }


@router.post("/{flow_id}/simulate-campaign-launch")
async def playground_simulate_campaign_launch(
    flow_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Simule un lancement « campagne » (entrée playground_audience) sans message contact,
    comme process_playground_scheduled_launches / schedule-flow-launch.
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
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    if str(row["account_id"]) != str(account_id):
        raise HTTPException(status_code=400, detail="flow_account_mismatch")

    graph = row.get("graph")
    entry_raw = payload.get("entry_node_id")
    entry_node_id = str(entry_raw).strip() if entry_raw else ""
    if not entry_node_id:
        entry_node_id = find_playground_audience_start_node_id(graph) or ""
    if not entry_node_id:
        raise HTTPException(
            status_code=400,
            detail="no_playground_audience_start",
        )
    if not is_playground_audience_start_node(graph, entry_node_id):
        raise HTTPException(
            status_code=400,
            detail="invalid_audience_entry_node",
        )

    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        conv = await ensure_playground_sandbox_conversation(account_id, flow_id)
        if not conv:
            raise HTTPException(status_code=500, detail="sandbox_conversation_failed")
        conversation_id = str(conv["id"])
    else:
        c = await get_conversation_by_id_fresh(str(conversation_id))
        if not c or str(c["account_id"]) != str(account_id):
            raise HTTPException(status_code=400, detail="invalid_conversation")
        await set_conversation_bot_mode(str(conversation_id), True, "playground")
        await set_conversation_playground_flow(str(conversation_id), flow_id)

    flow_trace: list = []
    try:
        ok = await simulate_playground_campaign_launch(
            str(conversation_id),
            entry_node_id,
            flow_trace=flow_trace,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve

    return {
        "status": "ok",
        "conversation_id": str(conversation_id),
        "entry_node_id": entry_node_id,
        "flow_ran": bool(ok),
        "flow_trace": flow_trace,
    }


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
    phase_raw = payload.get("execution_phase")
    phase_str = str(phase_raw).strip().lower() if phase_raw is not None else ""
    if phase_str not in ("", "plan", "execute_step"):
        raise HTTPException(status_code=400, detail="invalid_execution_phase")

    approve_raw = payload.get("approve_tool_calls")
    approve_list = approve_raw if isinstance(approve_raw, list) else None

    result = await generate_playground_assist_reply(
        account_id=str(account_id),
        flow_id=flow_id_str,
        flow_name=name_str,
        graph=graph,
        messages=messages,
        mode=mode_str,
        approve_tool_calls=approve_list,
        execution_phase=phase_str or None,
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


@router.post("/{flow_id}/schedule-flow-launch")
async def post_schedule_flow_launch(
    flow_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Planifie le lancement du graphe pour chaque membre du groupe à l'heure indiquée :
    le moteur enchaîne depuis le nœud Entrée « campagne » vers l'étape suivante (pas de message broadcast séparé).
    """
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    aid = str(row["account_id"])
    _require_flow_account_access(current_user, aid)
    if not current_user.permissions.has(PermissionCodes.MESSAGES_SEND, aid):
        raise HTTPException(status_code=403, detail="permission_denied")

    group_id = payload.get("broadcast_group_id")
    entry_node_id = payload.get("entry_node_id")
    scheduled_for = payload.get("scheduled_for")
    if not entry_node_id or not str(entry_node_id).strip():
        raise HTTPException(status_code=400, detail="entry_node_id_required")
    if not scheduled_for or not str(scheduled_for).strip():
        raise HTTPException(status_code=400, detail="scheduled_for_required")

    try:
        gid = str(group_id).strip() if group_id else None
        return await create_scheduled_flow_launch(
            flow_id=flow_id,
            account_id=aid,
            entry_node_id=str(entry_node_id).strip(),
            scheduled_for_raw=str(scheduled_for).strip(),
            created_by=current_user.id,
            broadcast_group_id_override=gid or None,
        )
    except ValueError as e:
        code = str(e)
        st = 404 if code == "flow_not_found" else 400
        raise HTTPException(status_code=st, detail=code) from e


@router.post("/{flow_id}/import-audience")
async def post_import_playground_audience(
    flow_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Import liste (JSON) : rattache chaque numéro à ce scénario playground (conversation + bot mode playground).
    Optionnel : broadcast_group_id pour aussi alimenter un groupe de campagne.
    """
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    aid = str(row["account_id"])
    _require_flow_account_access(current_user, aid)
    if not current_user.permissions.has(PermissionCodes.MESSAGES_SEND, aid):
        raise HTTPException(status_code=403, detail="permission_denied")

    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="rows_required")

    bg = payload.get("broadcast_group_id")
    bg_id: Optional[str] = None
    if bg is not None and str(bg).strip():
        bg_id = str(bg).strip()

    normalized_rows: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        phone = item.get("phone") or item.get("telephone")
        if not phone:
            continue
        normalized_rows.append(
            {
                "phone": str(phone).strip(),
                "name": item.get("name") or item.get("display_name") or "",
            }
        )
    if not normalized_rows:
        raise HTTPException(status_code=400, detail="no_valid_rows")

    try:
        return await run_playground_audience_import(
            flow_id, normalized_rows, broadcast_group_id=bg_id
        )
    except ValueError as e:
        code = str(e)
        if code == "invalid_broadcast_group":
            raise HTTPException(status_code=400, detail=code) from e
        raise HTTPException(status_code=400, detail=code) from e


@router.post("/{flow_id}/import-audience-csv")
async def post_import_playground_audience_csv(
    flow_id: str,
    file: UploadFile = File(...),
    broadcast_group_id: str = Form(""),
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await get_flow_by_id(flow_id)
    if not row:
        raise HTTPException(status_code=404, detail="flow_not_found")
    aid = str(row["account_id"])
    _require_flow_account_access(current_user, aid)
    if not current_user.permissions.has(PermissionCodes.MESSAGES_SEND, aid):
        raise HTTPException(status_code=403, detail="permission_denied")

    content = await file.read()
    if len(content) > 6 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file_too_large")

    try:
        parsed = parse_broadcast_import_csv(content)
    except ValueError as e:
        if str(e) == "file_too_large":
            raise HTTPException(status_code=413, detail="file_too_large") from e
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not parsed:
        raise HTTPException(status_code=400, detail="csv_empty_or_no_phone_column")

    bg_id = str(broadcast_group_id).strip() or None

    try:
        result = await run_playground_audience_import(
            flow_id, parsed, broadcast_group_id=bg_id
        )
    except ValueError as e:
        code = str(e)
        if code == "invalid_broadcast_group":
            raise HTTPException(status_code=400, detail=code) from e
        raise HTTPException(status_code=400, detail=code) from e
    result["csv_rows_detected"] = len(parsed)
    return result
