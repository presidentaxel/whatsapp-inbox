from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services import whatsapp_api_service as svc


class _FakeHttpClient:
    async def get(self, *args, **kwargs):
        req = httpx.Request("GET", "https://graph.facebook.com/v21.0/waba/message_templates")
        return httpx.Response(
            403,
            request=req,
            json={
                "error": {
                    "message": "(#200) Permissions error",
                    "type": "OAuthException",
                    "code": 200,
                }
            },
        )


def _run(coro):
    return asyncio.run(coro)


def test_list_message_templates_surfaces_meta_error(monkeypatch):
    async def _mock_get_http_client():
        return _FakeHttpClient()

    monkeypatch.setattr(svc, "get_http_client", _mock_get_http_client)

    with pytest.raises(svc.WhatsAppAPIError) as exc:
        _run(
            svc.list_message_templates(
                waba_id="waba-1",
                access_token="token-1",
            )
        )
    assert "OAuthException" in str(exc.value)
    assert "Permissions error" in str(exc.value)

