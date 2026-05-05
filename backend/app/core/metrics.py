"""
Compteurs et métriques Prometheus custom.

`prometheus-fastapi-instrumentator` couvre les requêtes HTTP automatiquement.
Ce module ajoute les compteurs métier qu'on veut suivre indépendamment :
chemins de fallback dégradés, événements perdus, etc.

Tous les compteurs sont enregistrés dans le registre par défaut, donc visibles
sur l'endpoint `/metrics` exposé par `app/main.py`.
"""
from __future__ import annotations

from prometheus_client import Counter

# Webhook events : fallback in-memory déclenché quand `DATABASE_URL` n'est pas
# configuré (pas de file durable). Si ce compteur monte en prod, c'est une
# erreur de config : la file durable n'est pas active et un crash entre la
# réponse à Meta et la fin du traitement entraînerait une perte d'évènement.
webhook_fallback_inmemory_total = Counter(
    "webhook_fallback_inmemory_total",
    "Webhooks WhatsApp traités via le fallback in-memory (pool PG indisponible)",
    labelnames=("source",),
)
