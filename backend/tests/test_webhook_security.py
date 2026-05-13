"""
Tests de la vérification de signature Meta sur les webhooks WhatsApp
(`app.core.webhook_security.verify_meta_signature`).

Ces tests *isolent* la fonction du framework FastAPI en construisant un faux
objet Request minimaliste avec les attributs utilisés (`body`, `headers`,
`client`). Pas de TestClient - pas besoin de mocker tout le pool DB.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.core.webhook_security import (
    _compute_signature,
    verify_meta_signature,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


class _FakeRequest:
    """Mimétisme strict de l'API utilisée par `verify_meta_signature`."""

    def __init__(self, body: bytes, headers: dict[str, str] | None = None):
        self._body = body
        self.headers = headers or {}
        self.client = SimpleNamespace(host="127.0.0.1")

    async def body(self) -> bytes:  # pragma: no cover - trivial
        return self._body


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _settings(*, secret: str | None, required: bool):
    return SimpleNamespace(
        META_APP_SECRET=secret,
        WEBHOOK_SIGNATURE_REQUIRED=required,
    )


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_compute_signature_matches_meta_format():
    """`_compute_signature` doit produire le format `sha256=<hex>` attendu par Meta."""
    sig = _compute_signature("secret", b'{"hello":"world"}')
    assert sig.startswith("sha256=")
    assert len(sig) == len("sha256=") + 64  # SHA-256 hex = 64 chars


def test_signature_valid_returns_body():
    body = b'{"object":"whatsapp_business_account"}'
    secret = "topsecret"
    headers = {"X-Hub-Signature-256": _sign(secret, body)}
    req = _FakeRequest(body, headers)

    with patch("app.core.webhook_security.settings", _settings(secret=secret, required=True)):
        result = asyncio.run(verify_meta_signature(req))
        assert result == body


def test_signature_invalid_returns_401():
    body = b'{"object":"whatsapp_business_account"}'
    headers = {"X-Hub-Signature-256": "sha256=" + "0" * 64}
    req = _FakeRequest(body, headers)

    with patch("app.core.webhook_security.settings", _settings(secret="topsecret", required=True)):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(verify_meta_signature(req))
        assert exc.value.status_code == 401
        assert exc.value.detail == "invalid_signature"


def test_signature_missing_header_returns_401():
    body = b'{"object":"whatsapp_business_account"}'
    req = _FakeRequest(body, headers={})  # pas de X-Hub-Signature-256

    with patch("app.core.webhook_security.settings", _settings(secret="topsecret", required=True)):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(verify_meta_signature(req))
        assert exc.value.status_code == 401
        assert exc.value.detail == "missing_signature"


def test_signature_skipped_when_secret_missing_and_not_required():
    """Mode dev local : pas de secret, signature ignorée → on retourne le body."""
    body = b'{"foo":"bar"}'
    req = _FakeRequest(body, headers={})

    with patch("app.core.webhook_security.settings", _settings(secret=None, required=False)):
        result = asyncio.run(verify_meta_signature(req))
        assert result == body


def test_signature_required_but_secret_missing_returns_500():
    """Mauvaise config prod : on refuse plutôt que d'accepter en aveugle."""
    req = _FakeRequest(b"{}", headers={})

    with patch("app.core.webhook_security.settings", _settings(secret=None, required=True)):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(verify_meta_signature(req))
        assert exc.value.status_code == 500
        assert exc.value.detail == "webhook_signature_not_configured"


def test_signature_uses_constant_time_compare():
    """
    Sanity check : on s'appuie sur `hmac.compare_digest` côté impl. Ce test
    documente l'intent - un attaquant ne peut pas inférer la signature attendue
    via une attaque par timing en envoyant des signatures partiellement bonnes.
    """
    body = b'{"x":1}'
    secret = "abc"
    correct = _sign(secret, body)
    # Différentes longueurs invalides, même chemin de code
    bad_signatures = [
        "sha256=00",                          # trop courte
        "sha256=" + "a" * 64,                 # taille correcte, mauvaise valeur
        correct[:-2] + "ff",                  # 1 caractère différent à la fin
    ]
    for bad in bad_signatures:
        req = _FakeRequest(body, {"X-Hub-Signature-256": bad})
        with patch("app.core.webhook_security.settings", _settings(secret=secret, required=True)):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(verify_meta_signature(req))
            assert exc.value.status_code == 401, f"signature bidon acceptée: {bad}"


def test_realistic_meta_payload_is_validated():
    """Format réaliste d'un webhook Meta avec messages."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "+33...", "phone_number_id": "PHID"},
                            "messages": [{"from": "33611111111", "id": "wamid.XXX", "timestamp": "1700000000", "type": "text", "text": {"body": "hello"}}],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    secret = "meta-app-secret-32chars-aaaaaaaaaaa"
    headers = {"x-hub-signature-256": _sign(secret, body)}  # noter la casse minuscule
    req = _FakeRequest(body, headers)

    with patch("app.core.webhook_security.settings", _settings(secret=secret, required=True)):
        result = asyncio.run(verify_meta_signature(req))
        assert json.loads(result) == payload
