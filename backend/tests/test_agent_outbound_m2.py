"""Jalon M2 : parsing outbound + chemin nominal boucle mockée."""

import asyncio
import importlib.util
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent_outbound import loop as agent_loop
from app.services.agent_outbound.loop import run_agent_outbound_inbox_gemini_with_tools
from app.services.agent_outbound.parsing import (
    normalize_agent_tool_calls_payload,
    parse_json_object,
    strip_json_fences,
)


def test_strip_json_fences():
    assert strip_json_fences('```json\n{"a":1}\n```') == '{"a":1}'


def test_parse_json_object():
    assert parse_json_object('```\n{"x": 1}\n```') == {"x": 1}
    assert parse_json_object("not json") is None


def test_normalize_agent_tool_calls_payload_aliases_and_cap():
    raw = [
        {"name": "list_templates", "arguments": {}},
        {"skill": "search_inbox_messages", "args": {"query": "x"}},
        "bad",
    ]
    out = normalize_agent_tool_calls_payload(raw)
    assert out == [
        {"skill": "list_templates", "args": {}},
        {"skill": "search_inbox_messages", "args": {"query": "x"}},
    ]


def test_run_agent_outbound_loop_returns_empty_when_no_kernel_tools():
    """Catalogue noyau vide : la boucle sort avant tout appel Gemini."""
    if importlib.util.find_spec("dotenv") is None:
        pytest.skip("python-dotenv requis (import de app.core.config.settings)")

    async def _go():
        with patch.object(
            agent_loop,
            "_gemini_generate_once",
            new_callable=AsyncMock,
        ) as mock_gen:
            out = await run_agent_outbound_inbox_gemini_with_tools(
                conversation_id="conv-1",
                account_id="acc-1",
                account={"id": "acc-1"},
                allowed_tools=["list_templates"],
                agent_playbook="## Agent test",
                qa_block="",
                msg="Bonjour",
                conversation_parts=[{"role": "user", "parts": [{"text": "Bonjour"}]}],
                qa_queries_used=[],
                qa_matches=[],
            )
        return out, mock_gen

    out, mock_gen = asyncio.run(_go())
    mock_gen.assert_not_called()
    assert out.get("reply") is None
    assert any("Aucun outil noyau v1" in r for r in (out.get("confidence_reasons") or []))
