"""
Rate limiting via SlowAPI.

Une seule instance de `Limiter` est partagée par toute l'application. Les
limites se configurent via `app/core/config.py` (variables `RATE_LIMIT_*`).

Le limiter clé sur `X-Forwarded-For` (premier IP) si présent, sinon sur
`request.client.host`. Cela suppose un reverse-proxy de confiance (Caddy,
nginx, Cloudflare). Si ton infra ne strip/set pas cet en-tête, change
`_client_key` pour ne pas se baser dessus.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


def _client_key(request: Request) -> str:
    """
    Identifie le client pour appliquer la limite.

    Priorités:
      1. ID utilisateur si déjà authentifié et présent sur `request.state`.
      2. Premier IP du header `X-Forwarded-For` (proxy de confiance).
      3. IP directe (`request.client.host`).
    """
    user_id = getattr(getattr(request, "state", None), "user_id", None)
    if user_id:
        return f"user:{user_id}"

    fwd: Optional[str] = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()

    return get_remote_address(request)


# `enabled=False` court-circuite TOUT (utile pour les tests / dev).
limiter = Limiter(
    key_func=_client_key,
    default_limits=[settings.RATE_LIMIT_DEFAULT] if settings.RATE_LIMIT_ENABLED else [],
    enabled=settings.RATE_LIMIT_ENABLED,
    headers_enabled=True,
)


async def rate_limit_exceeded_handler(
    request: StarletteRequest, exc: RateLimitExceeded
) -> JSONResponse:
    """Handler standardisé : JSON 429 avec retry-after."""
    logger.warning(
        "Rate limit dépassé: path=%s key=%s detail=%s",
        request.url.path,
        _client_key(request),  # type: ignore[arg-type]
        exc.detail,
    )
    response = JSONResponse(
        status_code=429,
        content={"detail": "rate_limited", "limit": str(exc.detail)},
    )
    response.headers["Retry-After"] = "60"
    return response
