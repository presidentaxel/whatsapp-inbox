"""
Sécurité des webhooks WhatsApp (Meta).

Fournit la vérification de la signature `X-Hub-Signature-256` envoyée par Meta
sur tous les webhooks. La signature est un HMAC-SHA256 du *raw body* avec
`META_APP_SECRET` comme clé.

Référence Meta:
https://developers.facebook.com/docs/graph-api/webhooks/getting-started#verification-requests
"""
from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_SIGNATURE_HEADER = "X-Hub-Signature-256"
_SIGNATURE_PREFIX = "sha256="


def _compute_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"{_SIGNATURE_PREFIX}{digest}"


async def verify_meta_signature(request: Request) -> bytes:
    """
    Vérifie la signature Meta du webhook entrant et renvoie le *raw body*.

    Comportement:
      - Si `META_APP_SECRET` n'est pas défini ET `WEBHOOK_SIGNATURE_REQUIRED=false`,
        la vérification est *skippée* (logguée en WARNING) - utile pour le dev local.
      - Sinon, exige un header `X-Hub-Signature-256` valide.
      - Renvoie le body brut pour que l'appelant puisse le réutiliser sans
        re-consommer le stream FastAPI.
    """
    body = await request.body()

    secret = settings.META_APP_SECRET
    if not secret:
        if settings.WEBHOOK_SIGNATURE_REQUIRED:
            logger.error(
                "META_APP_SECRET manquant alors que WEBHOOK_SIGNATURE_REQUIRED=true. "
                "Refus du webhook."
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="webhook_signature_not_configured",
            )
        logger.warning(
            "META_APP_SECRET non configuré : signature webhook ignorée. "
            "À NE PAS UTILISER EN PRODUCTION."
        )
        return body

    received = request.headers.get(_SIGNATURE_HEADER) or request.headers.get(
        _SIGNATURE_HEADER.lower()
    )
    if not received:
        logger.warning("Webhook reçu sans header %s", _SIGNATURE_HEADER)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_signature",
        )

    expected = _compute_signature(secret, body)
    # `compare_digest` pour éviter une attaque par timing.
    if not hmac.compare_digest(received.strip(), expected):
        logger.warning("Signature webhook invalide (header=%s...)", received[:20])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_signature",
        )

    return body
