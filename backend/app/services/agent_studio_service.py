from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.db import supabase, supabase_execute
from app.core.pg import execute, fetch_all, fetch_one, get_pool

ALLOWED_AGENT_TOOLS = frozenset(
    {
        "list_templates",
        "get_template_status",
        "create_template",
        "prepare_template_image_header",
        "list_broadcast_groups",
        "search_inbox_messages",
        "get_conversation_digest",
        "summarize_contact_inbox",
        "search_contacts",
        "get_contact",
        "list_recent_conversations",
        "find_satisfied_contacts",
        "list_broadcast_campaigns",
        "get_campaign_summary",
        "get_whatsapp_business_profile",
        "meta_block_contact",
    }
)

SENSITIVE_AGENT_TOOLS = frozenset({"create_template", "meta_block_contact"})


def default_agent_config() -> Dict[str, Any]:
    return {
        "name": "Nouvel agent",
        "objective": {"primary_goal": "", "kpi": [], "audience": None},
        "routing": {
            "fallback": "human",
            "confidence_threshold": 0.72,
            "intents": [],
        },
        "policies": {
            "tone": "pro",
            "forbidden_actions": [],
            "escalation_rules": [],
        },
        "capabilities": {
            "allowed_tools": [],
            "require_approval_for": [],
        },
        "tests": [],
        "deployment": {"status": "draft", "canary_percent": None},
    }


def normalize_agent_config(raw: Any) -> Dict[str, Any]:
    base = default_agent_config()
    if not isinstance(raw, dict):
        return base
    out = {**base, **raw}
    for key in ("objective", "routing", "policies", "capabilities", "deployment"):
        merged = base.get(key, {})
        incoming = raw.get(key)
        if isinstance(merged, dict) and isinstance(incoming, dict):
            out[key] = {**merged, **incoming}
        else:
            out[key] = merged if not isinstance(incoming, dict) else incoming
    tests_raw = raw.get("tests")
    out["tests"] = tests_raw if isinstance(tests_raw, list) else []
    return out


def validate_agent_config(config: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    cfg = normalize_agent_config(config)
    routing = cfg.get("routing") or {}
    policies = cfg.get("policies") or {}
    capabilities = cfg.get("capabilities") or {}
    objective = cfg.get("objective") or {}
    tests = cfg.get("tests") or []
    deployment = cfg.get("deployment") or {}

    if not str(objective.get("primary_goal") or "").strip():
        issues.append({"severity": "error", "message": "primary_goal_required"})
    if float(routing.get("confidence_threshold") or 0) <= 0:
        issues.append({"severity": "error", "message": "confidence_threshold_invalid"})

    intents = routing.get("intents") or []
    intent_keys = set()
    for i, intent in enumerate(intents):
        if not isinstance(intent, dict):
            issues.append({"severity": "error", "message": f"intent_{i}_invalid"})
            continue
        key = str(intent.get("key") or "").strip()
        handler = str(intent.get("handler") or "").strip()
        if not key:
            issues.append({"severity": "error", "message": f"intent_{i}_missing_key"})
        if key in intent_keys:
            issues.append({"severity": "error", "message": f"intent_{i}_duplicate_key"})
        intent_keys.add(key)
        if not handler:
            issues.append({"severity": "error", "message": f"intent_{i}_missing_handler"})

    forbidden = {
        str(x).strip()
        for x in (policies.get("forbidden_actions") or [])
        if str(x).strip()
    }
    approvals = {
        str(x).strip()
        for x in (capabilities.get("require_approval_for") or [])
        if str(x).strip()
    }
    if forbidden & approvals:
        issues.append({"severity": "warning", "message": "forbidden_actions_overlap_require_approval"})

    allowed_tools = {
        str(x).strip()
        for x in (capabilities.get("allowed_tools") or [])
        if str(x).strip()
    }
    unknown_allowed = sorted(x for x in allowed_tools if x not in ALLOWED_AGENT_TOOLS)
    if unknown_allowed:
        issues.append(
            {
                "severity": "error",
                "message": "unknown_allowed_tools",
                "details": ",".join(unknown_allowed),
            }
        )
    unknown_approvals = sorted(x for x in approvals if x not in ALLOWED_AGENT_TOOLS)
    if unknown_approvals:
        issues.append(
            {
                "severity": "error",
                "message": "unknown_require_approval_tools",
                "details": ",".join(unknown_approvals),
            }
        )
    missing_allowlist_for_approval = sorted(x for x in approvals if x not in allowed_tools)
    if missing_allowlist_for_approval:
        issues.append(
            {
                "severity": "error",
                "message": "require_approval_not_in_allowed_tools",
                "details": ",".join(missing_allowlist_for_approval),
            }
        )
    sensitive_without_approval = sorted(
        x for x in allowed_tools if x in SENSITIVE_AGENT_TOOLS and x not in approvals
    )
    if sensitive_without_approval:
        issues.append(
            {
                "severity": "error",
                "message": "sensitive_tools_must_require_approval",
                "details": ",".join(sensitive_without_approval),
            }
        )

    status = str(deployment.get("status") or "draft").strip().lower()
    canary_percent = deployment.get("canary_percent")
    if status == "canary" and (canary_percent is None or int(canary_percent) <= 0):
        issues.append({"severity": "error", "message": "canary_percent_required"})
    if status == "active" and len(tests) == 0:
        issues.append({"severity": "warning", "message": "no_tests_defined_for_active_agent"})

    for i, tc in enumerate(tests):
        if not isinstance(tc, dict):
            issues.append({"severity": "error", "message": f"test_{i}_invalid"})
            continue
        if not str(tc.get("input") or "").strip():
            issues.append({"severity": "error", "message": f"test_{i}_missing_input"})
        if not str(tc.get("expected_behavior") or "").strip():
            issues.append({"severity": "error", "message": f"test_{i}_missing_expected_behavior"})

    return issues


def can_deploy_agent_config(config: Dict[str, Any]) -> Tuple[bool, List[Dict[str, str]]]:
    issues = validate_agent_config(config)
    blocking = [i for i in issues if str(i.get("severity")) == "error"]
    return len(blocking) == 0, blocking


def map_config_to_runtime_graph(config: Dict[str, Any]) -> Dict[str, Any]:
    cfg = normalize_agent_config(config)
    intents = cfg.get("routing", {}).get("intents") or []
    nodes: List[Dict[str, Any]] = [
        {
            "id": "start",
            "type": "start",
            "position": {"x": 180, "y": 30},
            "data": {
                "triggerType": "message_in",
                "messageMatch": "any",
                "messageKeyword": "",
                "varKey": "reponse_entree",
            },
        },
        {
            "id": "agent-gemini",
            "type": "gemini",
            "position": {"x": 180, "y": 190},
            "data": {
                "hint": cfg.get("objective", {}).get("primary_goal") or "",
                "systemPrompt": "",
                "varKey": "agent_reply",
                "intents": intents,
                "structuredMemory": True,
            },
        },
    ]
    edges: List[Dict[str, Any]] = [
        {"id": "e-start-gemini", "source": "start", "target": "agent-gemini"}
    ]

    fallback = str(cfg.get("routing", {}).get("fallback") or "human").strip()
    if fallback == "human":
        nodes.append(
            {
                "id": "fallback-human",
                "type": "handoffNode",
                "position": {"x": 460, "y": 340},
                "data": {
                    "assignAgent": "",
                    "internalMessage": "Escalade automatique (confidence faible / route inconnue)",
                    "varKey": "fallback_handoff",
                },
            }
        )
        edges.append(
            {
                "id": "e-gemini-fallback",
                "source": "agent-gemini",
                "sourceHandle": "fallback",
                "target": "fallback-human",
            }
        )

    return {"v": 2, "nodes": nodes, "edges": edges}


def simulate_agent_route(config: Dict[str, Any], input_text: str) -> Dict[str, Any]:
    cfg = normalize_agent_config(config)
    text = str(input_text or "").strip().lower()
    intents = cfg.get("routing", {}).get("intents") or []
    for intent in intents:
        key = str(intent.get("key") or "").strip().lower()
        desc = str(intent.get("description") or "").strip().lower()
        if not key:
            continue
        if key in text or (
            desc and any(tok in text for tok in desc.split(" ") if len(tok) > 3)
        ):
            return {
                "route": key,
                "handler": intent.get("handler"),
                "confidence": max(0.72, float(intent.get("min_confidence") or 0.72)),
            }
    return {
        "route": "fallback",
        "handler": cfg.get("routing", {}).get("fallback") or "human",
        "confidence": 0.0,
    }


async def list_agent_configs(account_id: str) -> List[Dict[str, Any]]:
    if get_pool():
        rows = await fetch_all(
            """
            SELECT id, account_id, version, config, is_default, created_by, updated_by, created_at, updated_at
            FROM agent_studio_configs
            WHERE account_id = $1::uuid
            ORDER BY updated_at DESC
            """,
            account_id,
        )
        return [dict(r) for r in rows]
    res = await supabase_execute(
        supabase.table("agent_studio_configs")
        .select("id,account_id,version,config,is_default,created_by,updated_by,created_at,updated_at")
        .eq("account_id", account_id)
        .order("updated_at", desc=True)
    )
    return list(res.data or [])


async def get_agent_config(config_id: str) -> Optional[Dict[str, Any]]:
    if get_pool():
        row = await fetch_one(
            "SELECT * FROM agent_studio_configs WHERE id = $1::uuid LIMIT 1", config_id
        )
        return dict(row) if row else None
    res = await supabase_execute(
        supabase.table("agent_studio_configs").select("*").eq("id", config_id).limit(1)
    )
    return res.data[0] if res.data else None


async def create_agent_config(
    account_id: str, config: Dict[str, Any], user_id: str
) -> Dict[str, Any]:
    cfg = normalize_agent_config(config)
    now = datetime.now(timezone.utc)
    payload = {
        "account_id": account_id,
        "version": "v1",
        "config": cfg,
        "is_default": False,
        "created_by": user_id,
        "updated_by": user_id,
        "updated_at": now,
    }
    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO agent_studio_configs (account_id, version, config, is_default, created_by, updated_by, updated_at)
            VALUES ($1::uuid, 'v1', $2::jsonb, false, $3::uuid, $3::uuid, $4::timestamptz)
            RETURNING *
            """,
            account_id,
            json.dumps(cfg),
            user_id,
            now,
        )
        return dict(row) if row else {}
    res = await supabase_execute(supabase.table("agent_studio_configs").insert(payload))
    return res.data[0] if res.data else payload


async def update_agent_config(
    config_id: str, config: Dict[str, Any], user_id: str
) -> Optional[Dict[str, Any]]:
    row = await get_agent_config(config_id)
    if not row:
        return None
    cfg = normalize_agent_config(config)
    now = datetime.now(timezone.utc)
    if get_pool():
        await execute(
            """
            UPDATE agent_studio_configs
            SET config = $2::jsonb, updated_by = $3::uuid, updated_at = $4::timestamptz
            WHERE id = $1::uuid
            """,
            config_id,
            json.dumps(cfg),
            user_id,
            now,
        )
        return await get_agent_config(config_id)
    await supabase_execute(
        supabase.table("agent_studio_configs")
        .update(
            {
                "config": cfg,
                "updated_by": user_id,
                "updated_at": now.isoformat(),
            }
        )
        .eq("id", config_id)
    )
    return await get_agent_config(config_id)


async def set_agent_default(config_id: str, account_id: str) -> bool:
    if get_pool():
        await execute(
            "UPDATE agent_studio_configs SET is_default = false WHERE account_id = $1::uuid",
            account_id,
        )
        await execute(
            "UPDATE agent_studio_configs SET is_default = true WHERE id = $1::uuid AND account_id = $2::uuid",
            config_id,
            account_id,
        )
        return True
    await supabase_execute(
        supabase.table("agent_studio_configs")
        .update({"is_default": False})
        .eq("account_id", account_id)
    )
    await supabase_execute(
        supabase.table("agent_studio_configs")
        .update({"is_default": True})
        .eq("id", config_id)
        .eq("account_id", account_id)
    )
    return True


async def create_release(
    config_id: str,
    account_id: str,
    mode: str,
    actor_user_id: str,
    notes: Optional[str] = None,
):
    if mode not in {"canary", "activate", "pause"}:
        raise ValueError("invalid_release_mode")
    row = await get_agent_config(config_id)
    if not row:
        return None
    cfg = normalize_agent_config(row.get("config") or {})
    can_deploy, blocking = can_deploy_agent_config(cfg)
    if mode in {"canary", "activate"} and not can_deploy:
        details = ",".join(str(i.get("message")) for i in blocking)
        raise ValueError(f"config_not_deployable:{details}")
    deployment = cfg.get("deployment") or {}
    if mode == "canary":
        deployment["status"] = "canary"
    elif mode == "activate":
        deployment["status"] = "active"
    elif mode == "pause":
        deployment["status"] = "paused"
    cfg["deployment"] = deployment
    await update_agent_config(config_id, cfg, actor_user_id)
    if mode in ("canary", "activate"):
        await set_agent_default(config_id, account_id)

    payload = {
        "account_id": account_id,
        "agent_config_id": config_id,
        "release_mode": mode,
        "config_snapshot": cfg,
        "notes": notes or "",
        "created_by": actor_user_id,
    }
    if get_pool():
        release = await fetch_one(
            """
            INSERT INTO agent_studio_releases (account_id, agent_config_id, release_mode, config_snapshot, notes, created_by)
            VALUES ($1::uuid, $2::uuid, $3, $4::jsonb, $5, $6::uuid)
            RETURNING *
            """,
            account_id,
            config_id,
            mode,
            json.dumps(cfg),
            payload["notes"],
            actor_user_id,
        )
        return dict(release) if release else None
    res = await supabase_execute(supabase.table("agent_studio_releases").insert(payload))
    return res.data[0] if res.data else payload


async def rollback_release(config_id: str, release_id: str, actor_user_id: str) -> Tuple[bool, str]:
    cfg_row = await get_agent_config(config_id)
    if not cfg_row:
        return False, "config_not_found"
    account_id = str(cfg_row["account_id"])
    if get_pool():
        release = await fetch_one(
            """
            SELECT id, config_snapshot
            FROM agent_studio_releases
            WHERE id = $1::uuid AND agent_config_id = $2::uuid AND account_id = $3::uuid
            LIMIT 1
            """,
            release_id,
            config_id,
            account_id,
        )
        if not release:
            return False, "release_not_found"
        snapshot = release.get("config_snapshot")
    else:
        res = await supabase_execute(
            supabase.table("agent_studio_releases")
            .select("id,config_snapshot")
            .eq("id", release_id)
            .eq("agent_config_id", config_id)
            .eq("account_id", account_id)
            .limit(1)
        )
        if not res.data:
            return False, "release_not_found"
        snapshot = res.data[0].get("config_snapshot")

    cfg = normalize_agent_config(snapshot if isinstance(snapshot, dict) else {})
    updated = await update_agent_config(config_id, cfg, actor_user_id)
    if not updated:
        return False, "update_failed"
    return True, "ok"

