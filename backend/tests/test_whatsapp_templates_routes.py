from __future__ import annotations

import asyncio

from app.api import routes_whatsapp_templates as routes
from app.core.permissions import PermissionCodes
from app.schemas.whatsapp import (
    CreateMessageTemplateRequest,
    DeleteMessageTemplateRequest,
)


class _FakeUser:
    def __init__(self):
        self.id = "user-test"
        self.calls: list[tuple[str, str | None]] = []

    def require(self, permission: str, account_id: str | None = None):
        self.calls.append((permission, account_id))


def _run(coro):
    return asyncio.run(coro)


def test_create_template_requires_messages_send(monkeypatch):
    account_id = "acc-1"
    user = _FakeUser()

    async def _mock_get_account_by_id(_account_id: str):
        assert _account_id == account_id
        return {"waba_id": "waba-1", "access_token": "token-1"}

    async def _mock_create_message_template(**kwargs):
        assert kwargs["waba_id"] == "waba-1"
        assert kwargs["access_token"] == "token-1"
        return {"id": "tpl-1"}

    monkeypatch.setattr(routes, "get_account_by_id", _mock_get_account_by_id)
    monkeypatch.setattr(
        routes.whatsapp_api_service,
        "create_message_template",
        _mock_create_message_template,
    )

    request = CreateMessageTemplateRequest(
        name="relance_essai",
        category="UTILITY",
        language="fr",
        components=[{"type": "BODY", "text": "Bonjour {{1}}"}],
    )

    result = _run(routes.create_template(account_id, request, user))
    assert result["success"] is True
    assert user.calls[0] == (PermissionCodes.MESSAGES_SEND, account_id)


def test_delete_template_requires_messages_send(monkeypatch):
    account_id = "acc-1"
    user = _FakeUser()

    async def _mock_get_account_by_id(_account_id: str):
        assert _account_id == account_id
        return {"waba_id": "waba-1", "access_token": "token-1"}

    async def _mock_delete_message_template(**kwargs):
        assert kwargs["waba_id"] == "waba-1"
        assert kwargs["access_token"] == "token-1"
        assert kwargs["name"] == "relance_essai"
        return {"success": True}

    monkeypatch.setattr(routes, "get_account_by_id", _mock_get_account_by_id)
    monkeypatch.setattr(
        routes.whatsapp_api_service,
        "delete_message_template",
        _mock_delete_message_template,
    )

    request = DeleteMessageTemplateRequest(name="relance_essai")
    result = _run(routes.delete_template(account_id, request, user))
    assert result["success"] is True
    assert user.calls[0] == (PermissionCodes.MESSAGES_SEND, account_id)

