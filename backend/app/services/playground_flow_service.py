"""
CRUD flux Playground (graphes par compte WABA), défaut, copie et collage de sous-graphes.
"""
from __future__ import annotations

import copy
import json
import logging
import uuid
from datetime import datetime, timezone
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
