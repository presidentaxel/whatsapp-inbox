"""Jalon M2 : parsing outbound + chemin nominal boucle mockée."""

import asyncio
import importlib.util
import json
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


def test_run_agent_outbound_loop_minimal_mocked():
    """Deux appels Gemini mockés, sans outils exécutés."""
    if importlib.util.find_spec("dotenv") is None:
        pytest.skip("python-dotenv requis (import de app.core.config.settings)")

    def _cand(text: str) -> dict:
        return {"candidates": [{"content": {"parts": [{"text": text}]}}]}

    round1 = json.dumps({"reply": "", "tool_calls": []})
    round2 = "Message final pour le client."

    async def _go():
        with patch.object(
            agent_loop,
            "_gemini_generate_once",
            new_callable=AsyncMock,
            side_effect=[(_cand(round1), None), (_cand(round2), None)],
        ), patch.object(
            agent_loop,
            "_compute_reply_confidence",
            return_value=(0.85, ["score_ok"]),
        ):
            return await run_agent_outbound_inbox_gemini_with_tools(
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

    out = asyncio.run(_go())
    assert out.get("reply") == "Message final pour le client."
    assert out.get("confidence") == 0.85
    assert "Mode Agent Studio + outils noyau (M2)." in (out.get("confidence_reasons") or [""])[0]
