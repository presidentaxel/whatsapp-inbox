"""Jalon M1 : exécution des outils noyau agent (politique + validation + dispatch)."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.services.agent_outbound import kernel as agent_kernel
from app.services.agent_outbound.kernel import run_agent_kernel_v1_tool_calls
from app.services.agent_outbound.registry import (
    AgentOutboundToolErrorCode,
    build_effective_kernel_v1_allowlist,
)


def test_run_kernel_empty_tool_calls():
    async def _go():
        return await run_agent_kernel_v1_tool_calls(
            account={"id": "acc1"},
            allowed_tools=["search_inbox_messages"],
            tool_calls=[],
        )

    assert asyncio.run(_go()) == []


def test_build_effective_kernel_v1_allowlist_intersection():
    eff = build_effective_kernel_v1_allowlist(
        ["search_inbox_messages", "create_template", "list_templates"]
    )
    assert eff == frozenset({"search_inbox_messages", "list_templates"})


def test_run_kernel_rejects_tool_not_in_allowlist():
    async def _go():
        return await run_agent_kernel_v1_tool_calls(
            account={"id": "acc1"},
            allowed_tools=["list_templates"],
            tool_calls=[{"skill": "search_inbox_messages", "args": {"query": "x"}}],
        )

    out = asyncio.run(_go())
    assert len(out) == 1
    assert out[0]["skill"] == "search_inbox_messages"
    assert "error" in out[0]["result"]
    assert out[0]["result"]["kernel_error"]["code"] == AgentOutboundToolErrorCode.NOT_ALLOWED_BY_POLICY.value


def test_run_kernel_rejects_unknown_tool():
    async def _go():
        return await run_agent_kernel_v1_tool_calls(
            account={"id": "acc1"},
            allowed_tools=["list_templates", "search_inbox_messages"],
            tool_calls=[{"name": "totally_unknown", "arguments": {}}],
        )

    out = asyncio.run(_go())
    assert out[0]["result"]["kernel_error"]["code"] == AgentOutboundToolErrorCode.UNKNOWN_TOOL.value


def test_run_kernel_validation_before_invoke():
    async def _go():
        with patch.object(
            agent_kernel,
            "_invoke_playground_skill",
            new_callable=AsyncMock,
        ) as mock_ex:
            out = await run_agent_kernel_v1_tool_calls(
                account={"id": "acc1"},
                allowed_tools=["search_inbox_messages"],
                tool_calls=[{"skill": "search_inbox_messages", "args": {"limit": 3}}],
            )
        return out, mock_ex

    out, mock_ex = asyncio.run(_go())
    mock_ex.assert_not_called()
    assert out[0]["result"]["kernel_error"]["code"] == AgentOutboundToolErrorCode.INVALID_ARGUMENTS.value


def test_run_kernel_dispatches_invoke():
    async def _go():
        with patch.object(
            agent_kernel,
            "_invoke_playground_skill",
            new_callable=AsyncMock,
            return_value={"items": [1]},
        ) as mock_ex:
            out = await run_agent_kernel_v1_tool_calls(
                account={"id": "acc1", "waba_id": "w1", "access_token": "t"},
                allowed_tools=["search_inbox_messages"],
                tool_calls=[{"skill": "search_inbox_messages", "args": {"query": "bonjour"}}],
            )
        return out, mock_ex

    out, mock_ex = asyncio.run(_go())
    mock_ex.assert_awaited_once()
    assert out[0]["skill"] == "search_inbox_messages"
    assert out[0]["result"] == {"items": [1]}


def test_run_kernel_parallel_chunk_order():
    async def _go():
        with patch.object(
            agent_kernel,
            "_invoke_playground_skill",
            new_callable=AsyncMock,
            side_effect=[{"a": 1}, {"b": 2}],
        ):
            return await run_agent_kernel_v1_tool_calls(
                account={"id": "acc1"},
                allowed_tools=["list_templates", "get_whatsapp_business_profile"],
                tool_calls=[
                    {"skill": "list_templates", "args": {}},
                    {"skill": "get_whatsapp_business_profile", "args": {}},
                ],
            )

    out = asyncio.run(_go())
    assert [x["skill"] for x in out] == ["list_templates", "get_whatsapp_business_profile"]
