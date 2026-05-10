"""
Jalon M1 / M4 - Exécution des outils du noyau agent (syscall layer).

- Politique : seuls les noms dans ``allowed_tools`` ∩ lecture v1 sont exécutés.
- M4 : slugs normalisés (``coerce_kernel_tool_slug``), plafond d’appels par tour,
  validation args (forme + schéma) avant dispatch.
- Dispatch : réutilise ``playground_skills.execute_skill`` sans runtime Axelia
  (pas de ``AxeliaSkillsRuntime`` : les skills restent mono-ligne / primary).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Iterable, List

from app.services.agent_outbound.registry import (
    AGENT_KERNEL_V1_READ_TOOLS,
    AGENT_STUDIO_ALLOWLIST_SLUGS,
    AgentOutboundToolErrorCode,
    agent_tool_error_for_model,
    agent_tool_error_payload,
    build_effective_kernel_v1_allowlist,
    validate_agent_kernel_v1_args,
)
from app.services.agent_outbound.security import coerce_kernel_tool_slug

logger = logging.getLogger("uvicorn.error").getChild("agent_outbound.kernel")

_PARALLEL_TOOL_CALLS = 5
_MAX_TOOL_CALLS_PER_ROUND = 8


async def _invoke_playground_skill(
    skill_name: str,
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    """Point d’extension testable (patch) - import paresseux pour éviter cycles au chargement."""
    from app.services.playground_skills import execute_skill

    return await execute_skill(skill_name, args, account)


def _failed_skill(
    skill_name: str,
    code: AgentOutboundToolErrorCode,
    *,
    detail: str | None = None,
) -> Dict[str, Any]:
    payload = agent_tool_error_payload(code, tool_name=skill_name or None, detail=detail)
    return {
        "skill": skill_name,
        "result": {
            "error": agent_tool_error_for_model(code),
            "kernel_error": payload,
        },
    }


def _policy_error_for_tool(skill_name: str) -> AgentOutboundToolErrorCode:
    if skill_name not in AGENT_STUDIO_ALLOWLIST_SLUGS:
        return AgentOutboundToolErrorCode.UNKNOWN_TOOL
    if skill_name not in AGENT_KERNEL_V1_READ_TOOLS:
        return AgentOutboundToolErrorCode.TOOL_NOT_IN_KERNEL_V1
    return AgentOutboundToolErrorCode.NOT_ALLOWED_BY_POLICY


async def _run_one_tool_call(
    *,
    account: Dict[str, Any],
    effective: frozenset[str],
    tc: Dict[str, Any],
) -> Dict[str, Any]:
    name_raw = (tc.get("skill") or tc.get("name") or "").strip()
    name = coerce_kernel_tool_slug(name_raw) or ""
    raw_args = tc.get("args") if tc.get("args") is not None else tc.get("arguments")
    args = dict(raw_args) if isinstance(raw_args, dict) else {}

    if not name_raw:
        return _failed_skill(
            "",
            AgentOutboundToolErrorCode.UNKNOWN_TOOL,
            detail="missing_tool_name",
        )

    if not name:
        return _failed_skill(
            name_raw[:120],
            AgentOutboundToolErrorCode.UNKNOWN_TOOL,
            detail="malformed_tool_name",
        )

    if name not in effective:
        code = _policy_error_for_tool(name)
        logger.info(
            "agent kernel v1: tool %s rejected by policy (effective_allowlist size=%d)",
            name,
            len(effective),
        )
        return _failed_skill(name, code)

    val_err = validate_agent_kernel_v1_args(name, args)
    if val_err:
        return {
            "skill": name,
            "result": {
                "error": agent_tool_error_for_model(val_err),
                "kernel_error": agent_tool_error_payload(val_err, tool_name=name),
            },
        }

    result = await _invoke_playground_skill(name, args, account)
    return {"skill": name, "result": result}


async def run_agent_kernel_v1_tool_calls(
    *,
    account: Dict[str, Any],
    allowed_tools: Iterable[str],
    tool_calls: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Exécute une liste de ``tool_calls`` (même forme qu’Axelia : ``skill``/``name``, ``args``/``arguments``).

    Retourne une liste de ``{"skill": str, "result": dict}`` alignée sur ``execute_tool_calls`` playground,
    avec métadonnées ``kernel_error`` dans ``result`` lorsque la validation / politique bloque avant Meta/DB.
    """
    effective = build_effective_kernel_v1_allowlist(allowed_tools)
    if not tool_calls:
        return []

    if len(tool_calls) > _MAX_TOOL_CALLS_PER_ROUND:
        logger.warning(
            "agent kernel v1: truncating tool_calls from %d to %d",
            len(tool_calls),
            _MAX_TOOL_CALLS_PER_ROUND,
        )
        tool_calls = tool_calls[:_MAX_TOOL_CALLS_PER_ROUND]

    out: List[Dict[str, Any]] = []
    for off in range(0, len(tool_calls), _PARALLEL_TOOL_CALLS):
        subset = tool_calls[off : off + _PARALLEL_TOOL_CALLS]
        chunk = await asyncio.gather(
            *(_run_one_tool_call(account=account, effective=effective, tc=tc) for tc in subset)
        )
        out.extend(list(chunk))
    return out
