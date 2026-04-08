"""
CRUD flux Playground (graphes par compte WABA), défaut, copie et collage de sous-graphes.
"""
from __future__ import annotations

import copy
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.db import supabase, supabase_execute
from app.core.cache import invalidate_cache_pattern
from app.core.pg import fetch_one, fetch_all, execute, get_pool

logger = logging.getLogger("uvicorn.error").getChild("playground_flows")


def _normalize_graph(g: Any) -> Dict[str, Any]:
    if isinstance(g, str):
        try:
            g = json.loads(g)
        except Exception:
            g = None
    if not isinstance(g, dict):
        return {"nodes": [], "edges": [], "v": 2}
    nodes = g.get("nodes")
    edges = g.get("edges")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    return {"nodes": nodes, "edges": edges, "v": g.get("v", 2)}


async def _invalidate_bot_profile(account_id: str) -> None:
    await invalidate_cache_pattern(f"bot_profile:{account_id}")


async def list_flows_for_account(account_id: str) -> List[Dict[str, Any]]:
    if get_pool():
        rows = await fetch_all(
            """
            SELECT id, account_id, name, created_at, updated_at
            FROM playground_flows
            WHERE account_id = $1::uuid
            ORDER BY updated_at DESC
            """,
            account_id,
        )
        return [dict(r) for r in rows]
    res = await supabase_execute(
        supabase.table("playground_flows")
        .select("id, account_id, name, created_at, updated_at")
        .eq("account_id", account_id)
        .order("updated_at", desc=True)
    )
    return res.data or []


async def get_flow_by_id(flow_id: str) -> Optional[Dict[str, Any]]:
    if get_pool():
        row = await fetch_one(
            "SELECT * FROM playground_flows WHERE id = $1::uuid",
            flow_id,
        )
        return dict(row) if row else None
    res = await supabase_execute(
        supabase.table("playground_flows").select("*").eq("id", flow_id).limit(1)
    )
    return res.data[0] if res.data else None


async def get_default_flow_id_for_account(account_id: str) -> Optional[str]:
    if get_pool():
        row = await fetch_one(
            """
            SELECT default_playground_flow_id FROM bot_profiles
            WHERE account_id = $1::uuid LIMIT 1
            """,
            account_id,
        )
        if row and row.get("default_playground_flow_id"):
            return str(row["default_playground_flow_id"])
        return None
    res = await supabase_execute(
        supabase.table("bot_profiles")
        .select("default_playground_flow_id")
        .eq("account_id", account_id)
        .limit(1)
    )
    if not res.data:
        return None
    df = res.data[0].get("default_playground_flow_id")
    return str(df) if df else None


async def list_playground_flows_with_default_flag(account_id: str) -> List[Dict[str, Any]]:
    """Liste des flux + indicateur is_default (même payload que GET /bot/playground-flows)."""
    default_id = await get_default_flow_id_for_account(account_id)
    rows = await list_flows_for_account(account_id)
    out: List[Dict[str, Any]] = []
    for r in rows:
        rid = str(r.get("id"))
        out.append(
            {
                **r,
                "is_default": bool(default_id and rid == str(default_id)),
            }
        )
    return out


async def resolve_graph_for_conversation(
    account_id: str,
    conversation: Dict[str, Any],
    profile: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Retourne (graph_dict, flow_uuid_str) ou (None, None).
    Ordre : playground_flow_id sur la conversation → default_playground_flow_id → published_playground_flow.
    """
    flow_id: Optional[str] = None
    cf = conversation.get("playground_flow_id")
    if cf:
        flow_id = str(cf)
    if not flow_id:
        df = profile.get("default_playground_flow_id")
        if df:
            flow_id = str(df)
    if flow_id:
        row = await get_flow_by_id(flow_id)
        if row and str(row.get("account_id")) == str(account_id):
            return _normalize_graph(row.get("graph")), flow_id
        logger.warning(
            "playground flow %s missing or wrong account (expected %s)",
            flow_id,
            account_id,
        )
    legacy = profile.get("published_playground_flow")
    if legacy and isinstance(legacy, dict) and legacy.get("nodes"):
        return _normalize_graph(legacy), None
    return None, None


async def create_flow(account_id: str, name: str, graph: Optional[dict] = None) -> Dict[str, Any]:
    payload = {
        "account_id": account_id,
        "name": (name or "Sans titre").strip() or "Sans titre",
        "graph": _normalize_graph(graph),
    }
    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO playground_flows (account_id, name, graph)
            VALUES ($1::uuid, $2, $3::jsonb)
            RETURNING *
            """,
            account_id,
            payload["name"],
            json.dumps(payload["graph"]),
        )
        await _invalidate_bot_profile(account_id)
        return dict(row) if row else {}
    res = await supabase_execute(supabase.table("playground_flows").insert(payload).select("*"))
    await _invalidate_bot_profile(account_id)
    return res.data[0] if res.data else {}


async def update_flow(
    flow_id: str,
    name: Optional[str] = None,
    graph: Optional[dict] = None,
    *,
    set_name: bool = False,
    set_graph: bool = False,
) -> Optional[Dict[str, Any]]:
    row = await get_flow_by_id(flow_id)
    if not row:
        return None
    account_id = str(row["account_id"])
    ts_dt = datetime.now(timezone.utc)
    patch: Dict[str, Any] = {"updated_at": ts_dt.isoformat()}
    if set_name:
        patch["name"] = (name or "").strip() or "Sans titre"
    if set_graph and graph is not None:
        patch["graph"] = _normalize_graph(graph)
    if get_pool():
        if set_name and set_graph:
            await execute(
                """
                UPDATE playground_flows
                SET name = $2, graph = $3::jsonb, updated_at = $4::timestamptz
                WHERE id = $1::uuid
                """,
                flow_id,
                patch["name"],
                json.dumps(patch["graph"]),
                ts_dt,
            )
        elif set_graph:
            await execute(
                """
                UPDATE playground_flows
                SET graph = $2::jsonb, updated_at = $3::timestamptz
                WHERE id = $1::uuid
                """,
                flow_id,
                json.dumps(patch["graph"]),
                ts_dt,
            )
        elif set_name:
            await execute(
                """
                UPDATE playground_flows
                SET name = $2, updated_at = $3::timestamptz
                WHERE id = $1::uuid
                """,
                flow_id,
                patch["name"],
                ts_dt,
            )
        else:
            return await get_flow_by_id(flow_id)
    else:
        await supabase_execute(
            supabase.table("playground_flows").update(patch).eq("id", flow_id)
        )
    await _invalidate_bot_profile(account_id)
    return await get_flow_by_id(flow_id)


async def delete_flow(flow_id: str) -> bool:
    row = await get_flow_by_id(flow_id)
    if not row:
        return False
    account_id = str(row["account_id"])
    if get_pool():
        await execute("DELETE FROM playground_flows WHERE id = $1::uuid", flow_id)
        await execute(
            """
            UPDATE bot_profiles SET default_playground_flow_id = NULL
            WHERE default_playground_flow_id = $1::uuid
            """,
            flow_id,
        )
        await execute(
            """
            UPDATE conversations SET playground_flow_id = NULL
            WHERE playground_flow_id = $1::uuid
            """,
            flow_id,
        )
    else:
        await supabase_execute(supabase.table("playground_flows").delete().eq("id", flow_id))
        await supabase_execute(
            supabase.table("bot_profiles")
            .update({"default_playground_flow_id": None})
            .eq("default_playground_flow_id", flow_id)
        )
        await supabase_execute(
            supabase.table("conversations")
            .update({"playground_flow_id": None})
            .eq("playground_flow_id", flow_id)
        )
    await _invalidate_bot_profile(account_id)
    return True


async def set_default_flow(account_id: str, flow_id: str) -> bool:
    flow = await get_flow_by_id(flow_id)
    if not flow or str(flow.get("account_id")) != str(account_id):
        return False
    if get_pool():
        await execute(
            """
            UPDATE bot_profiles
            SET default_playground_flow_id = $2::uuid
            WHERE account_id = $1::uuid
            """,
            account_id,
            flow_id,
        )
    else:
        await supabase_execute(
            supabase.table("bot_profiles")
            .update({"default_playground_flow_id": flow_id})
            .eq("account_id", account_id)
        )
    await _invalidate_bot_profile(account_id)
    return True


def _remap_subgraph(nodes: List[dict], edges: List[dict]) -> Dict[str, Any]:
    id_map = {n["id"]: str(uuid.uuid4()) for n in nodes if n.get("id")}
    new_nodes = []
    for n in nodes:
        oid = n.get("id")
        if not oid or oid not in id_map:
            continue
        nc = copy.deepcopy(n)
        nc["id"] = id_map[oid]
        short = id_map[oid].replace("-", "")[:12]
        if isinstance(nc.get("data"), dict):
            nc["data"] = {**nc["data"], "varKey": f"réponse_{short}"}
        new_nodes.append(nc)
    new_edges = []
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in id_map and t in id_map:
            ne = {**copy.deepcopy(e), "id": str(uuid.uuid4())}
            ne["source"] = id_map[s]
            ne["target"] = id_map[t]
            new_edges.append(ne)
    return {"nodes": new_nodes, "edges": new_edges, "v": 2}


async def duplicate_flow(
    source_flow_id: str,
    target_account_id: str,
    name: Optional[str] = None,
    subgraph_node_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    src = await get_flow_by_id(source_flow_id)
    if not src:
        return None
    g = _normalize_graph(src.get("graph"))
    nodes = g["nodes"]
    edges = g["edges"]
    if subgraph_node_ids:
        sid = set(subgraph_node_ids)
        nodes = [n for n in nodes if n.get("id") in sid]
        edges = [e for e in edges if e.get("source") in sid and e.get("target") in sid]
        g = _remap_subgraph(nodes, edges)
    else:
        g = copy.deepcopy(g)
        g = _remap_subgraph(g["nodes"], g["edges"])
    nm = (name or f"{src.get('name', 'Flux')} (copie)").strip()
    return await create_flow(target_account_id, nm, g)


async def append_subgraph_to_flow(target_flow_id: str, nodes: List[dict], edges: List[dict]) -> Optional[Dict[str, Any]]:
    row = await get_flow_by_id(target_flow_id)
    if not row:
        return None
    base = _normalize_graph(row.get("graph"))
    remapped = _remap_subgraph(nodes, edges)
    base["nodes"] = base["nodes"] + remapped["nodes"]
    base["edges"] = base["edges"] + remapped["edges"]
    return await update_flow(target_flow_id, graph=base, set_graph=True)


async def import_playground_flow_audience(
    flow_id: str,
    rows: List[Dict[str, Any]],
    *,
    broadcast_group_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pour chaque ligne (téléphone + nom optionnel) : conversation inbox, contact,
    conversation liée à ce scénario playground, bot activé en mode playground.
    Optionnel : ajout / mise à jour dans un groupe de diffusion (campagnes classiques).
    """
    from app.services.broadcast_service import (
        _update_contact_display_name,
        get_broadcast_group,
        upsert_recipient_to_group,
    )
    from app.services.conversation_service import (
        find_or_create_conversation,
        normalize_phone_number,
        set_conversation_bot_mode,
        set_conversation_playground_flow,
    )

    flow = await get_flow_by_id(flow_id)
    if not flow:
        raise ValueError("flow_not_found")
    account_id = str(flow["account_id"])

    if broadcast_group_id:
        grp = await get_broadcast_group(broadcast_group_id)
        if not grp or str(grp["account_id"]) != account_id:
            raise ValueError("invalid_broadcast_group")

    imported = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []

    for raw in rows:
        raw_phone = (raw.get("phone") or raw.get("telephone") or "").strip()
        if not raw_phone:
            skipped += 1
            continue
        name_raw = raw.get("name") or raw.get("display_name") or ""
        display_name = str(name_raw).strip() if name_raw else None

        normalized = normalize_phone_number(raw_phone)
        if not normalized:
            errors.append({"phone": raw_phone, "error": "invalid_phone"})
            continue

        try:
            conv = await find_or_create_conversation(account_id, normalized)
            if not conv:
                errors.append({"phone": raw_phone, "error": "conversation_failed"})
                continue
            conv_id = conv.get("id")
            contact_id = conv.get("contact_id")
            if not conv_id:
                errors.append({"phone": raw_phone, "error": "conversation_failed"})
                continue

            await set_conversation_playground_flow(str(conv_id), flow_id)
            await set_conversation_bot_mode(str(conv_id), True, "playground")

            if contact_id and display_name:
                await _update_contact_display_name(str(contact_id), display_name)

            if broadcast_group_id:
                await upsert_recipient_to_group(
                    broadcast_group_id,
                    normalized,
                    str(contact_id) if contact_id else None,
                    display_name,
                )
            imported += 1
        except Exception as e:
            logger.exception("playground audience import failed for %s", raw_phone)
            errors.append({"phone": raw_phone, "error": str(e)})

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_input_rows": len(rows),
        "playground_flow_id": flow_id,
        "account_id": account_id,
    }


def _parse_schedule_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


async def create_scheduled_flow_launch(
    flow_id: str,
    account_id: str,
    broadcast_group_id: str,
    entry_node_id: str,
    scheduled_for_raw: str,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Enregistre un lancement de graphe à une date/heure pour tous les membres du groupe."""
    from app.services.broadcast_service import get_broadcast_group

    flow = await get_flow_by_id(flow_id)
    if not flow or str(flow["account_id"]) != str(account_id):
        raise ValueError("flow_not_found")

    grp = await get_broadcast_group(broadcast_group_id)
    if not grp or str(grp["account_id"]) != str(account_id):
        raise ValueError("invalid_broadcast_group")

    g = _normalize_graph(flow.get("graph"))
    nodes_by_id = {n["id"]: n for n in g.get("nodes") or [] if n.get("id")}
    eid = str(entry_node_id).strip()
    if eid not in nodes_by_id:
        raise ValueError("invalid_entry_node")
    node = nodes_by_id[eid]
    if node.get("type") != "start":
        raise ValueError("entry_not_start")
    data = node.get("data") or {}
    if data.get("triggerType") != "playground_audience":
        raise ValueError("entry_not_campaign_trigger")

    sched = _parse_schedule_datetime(scheduled_for_raw)
    if not sched:
        raise ValueError("invalid_schedule_time")
    now = datetime.now(timezone.utc)
    if sched <= now + timedelta(seconds=5):
        raise ValueError("schedule_time_must_be_future")

    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO playground_scheduled_flow_launches (
                account_id, playground_flow_id, broadcast_group_id, entry_node_id,
                scheduled_for, schedule_status, created_by
            )
            VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5::timestamptz, 'scheduled', $6::uuid)
            RETURNING *
            """,
            account_id,
            flow_id,
            broadcast_group_id,
            eid,
            sched,
            created_by,
        )
        if not row:
            raise ValueError("insert_failed")
        return dict(row)

    ins = {
        "account_id": account_id,
        "playground_flow_id": flow_id,
        "broadcast_group_id": broadcast_group_id,
        "entry_node_id": eid,
        "scheduled_for": sched.isoformat(),
        "schedule_status": "scheduled",
        "created_by": created_by,
    }
    res = await supabase_execute(
        supabase.table("playground_scheduled_flow_launches").insert(ins)
    )
    if not res.data:
        raise ValueError("insert_failed")
    return res.data[0]


async def _claim_next_scheduled_flow_launch(now_utc: datetime) -> Optional[Dict[str, Any]]:
    pool = get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                WITH cte AS (
                  SELECT id FROM playground_scheduled_flow_launches
                  WHERE schedule_status = 'scheduled'
                    AND scheduled_for <= $1::timestamptz
                  ORDER BY scheduled_for ASC
                  LIMIT 1
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE playground_scheduled_flow_launches b
                SET schedule_status = 'sending'
                FROM cte
                WHERE b.id = cte.id AND b.schedule_status = 'scheduled'
                RETURNING b.*
                """,
                now_utc,
            )
            return dict(row) if row else None


async def process_due_playground_scheduled_launches_once() -> int:
    """Traite jusqu'à 15 lancements planifiés (pool PG requis)."""
    from app.services.broadcast_service import get_group_recipients
    from app.services.conversation_service import (
        find_or_create_conversation,
        get_conversation_by_id_fresh,
        normalize_phone_number,
        set_conversation_bot_mode,
        set_conversation_playground_flow,
    )
    from app.services.flow_runtime_service import try_run_playground_flow

    if not get_pool():
        return 0

    now = datetime.now(timezone.utc)
    n = 0
    for _ in range(15):
        row = await _claim_next_scheduled_flow_launch(now)
        if not row:
            break
        launch_id = str(row["id"])
        flow_id = str(row["playground_flow_id"])
        account_id = str(row["account_id"])
        group_id = str(row["broadcast_group_id"])
        entry_node_id = str(row["entry_node_id"])
        try:
            recipients = await get_group_recipients(group_id)
            for rec in recipients:
                phone = (rec.get("phone_number") or "").strip()
                if not phone:
                    continue
                normalized = normalize_phone_number(phone)
                if not normalized:
                    continue
                conv = await find_or_create_conversation(account_id, normalized)
                if not conv or not conv.get("id"):
                    continue
                cid = str(conv["id"])
                await set_conversation_playground_flow(cid, flow_id)
                await set_conversation_bot_mode(cid, True, "playground")
                conv_full = await get_conversation_by_id_fresh(cid)
                if not conv_full:
                    continue
                contact = conv_full.get("contacts")
                if not isinstance(contact, dict):
                    contact = {}
                await try_run_playground_flow(
                    cid,
                    conv_full,
                    contact,
                    {},
                    "",
                    "text",
                    scheduled_flow_launch=True,
                    launch_entry_node_id=entry_node_id,
                )
            await execute(
                """
                UPDATE playground_scheduled_flow_launches
                SET schedule_status = 'done'
                WHERE id = $1::uuid
                """,
                launch_id,
            )
            n += 1
        except Exception:
            logger.exception("playground scheduled flow launch failed id=%s", launch_id)
            await execute(
                """
                UPDATE playground_scheduled_flow_launches
                SET schedule_status = 'failed'
                WHERE id = $1::uuid
                """,
                launch_id,
            )
            n += 1
    return n


async def periodic_playground_scheduled_launches() -> None:
    import asyncio

    while True:
        try:
            await asyncio.sleep(30)
            await process_due_playground_scheduled_launches_once()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("periodic_playground_scheduled_launches tick failed")
