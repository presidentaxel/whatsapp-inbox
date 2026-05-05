from __future__ import annotations

import asyncio
from types import SimpleNamespace

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


def test_resolve_account_for_template_skills_falls_back_from_all_scope(monkeypatch):
    class _User:
        def accounts_for(self, permission: str):
            assert permission == "messages.view"
            return {"acc-a", "acc-b"}

    rt = skills.AxeliaSkillsRuntime(
        acting_user=_User(),
        perimeter_mode="all",
        pending_attachment=None,
    )
    token = skills._axelia_skills_runtime.set(rt)

    async def _mock_get_account_by_id(aid: str):
        if aid == "acc-b":
            return {"id": "acc-b", "waba_id": "waba-1", "access_token": "token-1"}
        return {"id": aid}

    monkeypatch.setattr(
        "app.services.account_service.get_account_by_id",
        _mock_get_account_by_id,
    )

    try:
        resolved = _run(
            skills._resolve_account_for_template_skills(
                {},
                required_permission="messages.view",
            )
        )
    finally:
        skills._axelia_skills_runtime.reset(token)

    assert resolved["id"] == "acc-b"
    assert resolved["waba_id"] == "waba-1"

