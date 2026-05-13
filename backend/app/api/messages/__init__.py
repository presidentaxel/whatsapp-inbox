"""
Routes `messages` - package découpé par responsabilité.

Le router agrégateur ci-dessous est ce que `main.py` monte sous `/messages`.
Chaque sous-module définit son propre `APIRouter` et y attache ses endpoints.
On les concatène ici, donc l'API publique reste **identique** au mono-fichier
historique (`routes_messages.py`).

Découpage:
  - read.py       : lectures (GET messages, GET media, fenêtre gratuite, prix)
  - send.py       : envois (texte, free, auto-template, media, interactive)
  - templates.py  : templates listing + envoi template + check status
  - media.py      : galeries, vérif/téléchargement, test-storage, transcription
  - actions.py    : édition, suppression, pin/unpin, réactions, check-whatsapp
"""
from fastapi import APIRouter

from .read import router as read_router
from .send import router as send_router
from .templates import router as templates_router
from .media import router as media_router
from .actions import router as actions_router

router = APIRouter()
router.include_router(read_router)
router.include_router(send_router)
router.include_router(templates_router)
router.include_router(media_router)
router.include_router(actions_router)

__all__ = ["router"]
