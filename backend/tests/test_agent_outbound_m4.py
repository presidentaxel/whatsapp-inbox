"""Jalon M4 : durcissement défensif du noyau agent outbound."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.services.agent_outbound import kernel as agent_kernel
from app.services.agent_outbound.kernel import run_agent_kernel_v1_tool_calls
from app.services.agent_outbound.registry import (
    AgentOutboundToolErrorCode,
    build_agent_kernel_v1_catalog,
    build_effective_kernel_v1_allowlist,
    validate_agent_kernel_v1_args,
)
from app.services.agent_outbound.security import (
    coerce_kernel_tool_slug,
    validate_args_security_shape,
)


def test_coerce_kernel_tool_slug_accepts_known_slugs():
    assert coerce_kernel_tool_slug("list_templates") == "list_templates"
    assert coerce_kernel_tool_slug("  List_Templates  ") == "list_templates"


def test_coerce_kernel_tool_slug_rejects_injection_attempts():
    assert coerce_kernel_tool_slug("list_templates; DROP") is None
    assert coerce_kernel_tool_slug("search_inbox_messages' OR 1=1") is None
    assert coerce_kernel_tool_slug("") is None
    assert coerce_kernel_tool_slug("list-templates") is None


def test_validate_args_security_shape():
    assert validate_args_security_shape({"query": "ok"}) is None
    assert validate_args_security_shape({"__proto__": 1}) == "arg_key_forbidden"
    assert validate_args_security_shape({"$where": 1}) == "arg_key_forbidden"
    assert validate_args_security_shape({"a": "x" * 9000}) == "arg_string_too_long"
    assert validate_args_security_shape({str(i): i for i in range(30)}) == "too_many_arg_keys"


def test_validate_agent_kernel_rejects_bool_as_integer():
    assert (
        validate_agent_kernel_v1_args(
            "search_inbox_messages",
            {"query": "x", "limit": True},
        )
        == AgentOutboundToolErrorCode.INVALID_ARGUMENTS
    )


def test_validate_agent_kernel_rejects_prototype_pollution_keys():
    assert (
        validate_agent_kernel_v1_args(
            "search_inbox_messages",
            {"query": "x", "__proto__": {}},
        )
        == AgentOutboundToolErrorCode.INVALID_ARGUMENTS
    )


def test_build_effective_allowlist_coerces_case():
    eff = build_effective_kernel_v1_allowlist(["List_Templates", "search_inbox_messages"])
    assert eff == frozenset({"list_templates", "search_inbox_messages"})


def test_build_catalog_records_malformed_entries_in_rejected():
    specs, rejected = build_agent_kernel_v1_catalog(
        ["list_templates", "'; DROP--", "search_inbox_messages"]
    )
    assert {s.name for s in specs} == {"list_templates", "search_inbox_messages"}
    assert any("DROP" in r for r in rejected)


def test_run_kernel_rejects_malformed_skill_name():
    async def _go():
        return await run_agent_kernel_v1_tool_calls(
            account={"id": "a1"},
            allowed_tools=["list_templates"],
            tool_calls=[{"skill": "list_templates';--", "args": {}}],
        )

    out = asyncio.run(_go())
    assert out[0]["result"]["kernel_error"]["code"] == AgentOutboundToolErrorCode.UNKNOWN_TOOL.value


def test_run_kernel_truncates_excess_tool_calls():
    calls = [{"skill": "list_templates", "args": {}} for _ in range(12)]

    async def _go():
        with patch.object(
            agent_kernel,
            "_invoke_playground_skill",
            new_callable=AsyncMock,
            return_value={"ok": True},
        ) as inv:
            out = await run_agent_kernel_v1_tool_calls(
                account={"id": "a1"},
                allowed_tools=["list_templates"],
                tool_calls=calls,
            )
        return out, inv.await_count

    out, n = asyncio.run(_go())
    assert len(out) == 8
    assert n == 8
