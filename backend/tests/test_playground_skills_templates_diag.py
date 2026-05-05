from __future__ import annotations

import asyncio

from app.services import playground_skills as skills


def _run(coro):
    return asyncio.run(coro)


def test_skill_list_templates_returns_diagnostic_when_credentials_missing():
    result = _run(skills._skill_list_templates({}, {"id": "acc-1"}))
    assert "error" in result
    assert "diagnostic" in result
    assert result["diagnostic"]["account_id"] == "acc-1"
    assert result["diagnostic"]["has_waba_id"] is False
    assert result["diagnostic"]["has_access_token"] is False

