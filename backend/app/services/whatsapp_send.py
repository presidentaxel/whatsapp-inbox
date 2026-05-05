"""
Primitive d'envoi HTTP vers l'API WhatsApp Cloud (Graph v19).

Extraite de `message_service.py` pour pouvoir être réutilisée depuis d'autres
services (reactions, etc.) sans cycle d'imports.
"""
from __future__ import annotations

import httpx

from app.core.http_client import get_http_client
from app.core.retry import retry_on_network_error

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def send_with_retry(phone_id: str, token: str, body: dict) -> httpx.Response:
    """Envoie un message WhatsApp avec retry automatique sur erreurs réseau."""
    client = await get_http_client()
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    return response
