"""
File durable des webhooks WhatsApp.

Architecture:
  1. `routes_webhook.py` reçoit un POST Meta, vérifie la signature, puis appelle
     `enqueue_webhook_event(payload)` qui INSERT la ligne en DB et répond 200 OK.
  2. Un worker périodique `periodic_process_webhook_events()` (lancé au startup
     dans `main.py`) consomme la file :
        a. Récupère les locks orphelins (`reclaim_stale_processing()`).
        b. Boucle `claim_next_event()` (FOR UPDATE SKIP LOCKED → multi-worker safe)
           puis appelle `handle_incoming_message(payload)`.
        c. `mark_event_done()` ou `mark_event_failed()` avec back-off exponentiel.
  3. Une déduplication par `signature_id` évite de retraiter les retries Meta
     (Meta réessaie un webhook si on n'a pas répondu 200 OK assez vite).

Conception volontairement simple : pas de Redis ni Celery - juste asyncpg +
SKIP LOCKED sur PostgreSQL, qui est suffisant pour les volumes de webhook
WhatsApp et reste rejouable / observable depuis la table `webhook_events`.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.pg import fetch_all, fetch_one, get_pool

logger = logging.getLogger(__name__)

# ─── Tunables ────────────────────────────────────────────────────────────────
# Combien d'évènements le worker traite par cycle.
_BATCH_SIZE = 20
# Temps entre deux cycles quand la file est vide.
_IDLE_SLEEP_SECONDS = 2.0
# Délai sans `locked_at` mis à jour avant de considérer un lock comme orphelin.
_STALE_LOCK_MINUTES = 5
# Back-off exponentiel : 5s, 25s, 2min, 10min, 50min (cap à 1h).
_RETRY_BACKOFFS_SECONDS = [5, 25, 120, 600, 3000]
_MAX_BACKOFF_SECONDS = 3600

# Identifiant unique du worker pour le champ `locked_by` (debug).
_WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


# ─── Utilitaires ─────────────────────────────────────────────────────────────


def _compute_signature_id(payload: Dict[str, Any]) -> str:
    """
    Empreinte stable pour dédupliquer les retries Meta.

    Stratégie:
      1. Si on trouve un `messages[*].id` ou `statuses[*].id` dans le payload,
         on les concatène - c'est l'identifiant Meta, déjà stable.
      2. Sinon, fallback : SHA-256 du payload sérialisé canoniquement.
    """
    ids: List[str] = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {}) or {}
                for m in value.get("messages", []) or []:
                    if m.get("id"):
                        ids.append(f"m:{m['id']}")
                for s in value.get("statuses", []) or []:
                    if s.get("id"):
                        ids.append(f"s:{s['id']}:{s.get('status', '')}")
    except (AttributeError, TypeError):
        pass

    if ids:
        return "|".join(sorted(ids))[:512]

    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(serialized).hexdigest()}"


def _next_attempt_at(attempts: int) -> datetime:
    """Calcule la prochaine date de retry après `attempts` échecs."""
    idx = min(attempts, len(_RETRY_BACKOFFS_SECONDS) - 1)
    delay = _RETRY_BACKOFFS_SECONDS[idx] if attempts > 0 else _RETRY_BACKOFFS_SECONDS[0]
    delay = min(delay, _MAX_BACKOFF_SECONDS)
    return datetime.now(timezone.utc) + timedelta(seconds=delay)


# ─── API publique ────────────────────────────────────────────────────────────


async def enqueue_webhook_event(
    payload: Dict[str, Any],
    *,
    source: str = "whatsapp",
) -> Optional[str]:
    """
    INSERT le payload dans `webhook_events` et renvoie l'id (ou l'id existant
    si un évènement avec le même `signature_id` existe déjà - déduplication).

    Renvoie `None` si le pool PostgreSQL n'est pas disponible (le caller doit
    alors fallback sur l'ancien comportement asyncio.create_task).
    """
    if not get_pool():
        return None

    signature_id = _compute_signature_id(payload)

    # ON CONFLICT DO NOTHING + RETURNING ne renvoie rien si conflit, donc on
    # fait un SELECT en fallback pour récupérer l'id de l'évènement existant.
    row = await fetch_one(
        """
        INSERT INTO webhook_events (signature_id, source, payload)
        VALUES ($1, $2, $3::jsonb)
        ON CONFLICT (signature_id) DO NOTHING
        RETURNING id, 'inserted' AS state
        """,
        signature_id,
        source,
        json.dumps(payload),
    )

    if row:
        logger.debug("webhook_event %s inséré (sig=%s)", row["id"], signature_id[:32])
        return str(row["id"])

    existing = await fetch_one(
        "SELECT id, status FROM webhook_events WHERE signature_id = $1",
        signature_id,
    )
    if existing:
        logger.info(
            "webhook_event dédupliqué (sig=%s, status=%s, id=%s)",
            signature_id[:32],
            existing["status"],
            existing["id"],
        )
        return str(existing["id"])

    logger.warning("Insert webhook_event échoué et aucun existant trouvé (sig=%s)", signature_id[:32])
    return None


async def reclaim_stale_processing() -> int:
    """
    Replace les lignes `processing` orphelines (worker mort) en `pending`
    pour qu'elles soient re-claim au prochain cycle.
    """
    if not get_pool():
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_STALE_LOCK_MINUTES)
    rows = await fetch_all(
        """
        UPDATE webhook_events
        SET status = 'pending',
            locked_by = NULL,
            locked_at = NULL,
            next_attempt_at = now()
        WHERE status = 'processing' AND locked_at < $1
        RETURNING id
        """,
        cutoff,
    )
    if rows:
        logger.warning(
            "♻️ %d webhook_event(s) orphelin(s) repris (lock > %d min)",
            len(rows),
            _STALE_LOCK_MINUTES,
        )
    return len(rows)


async def claim_next_event() -> Optional[Dict[str, Any]]:
    """
    Réserve atomiquement le prochain évènement à traiter.

    Utilise `FOR UPDATE SKIP LOCKED` pour permettre plusieurs workers
    concurrents (sur plusieurs instances backend, par ex.) sans deadlock.
    """
    pool = get_pool()
    if not pool:
        return None

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, payload, attempts, max_attempts
                FROM webhook_events
                WHERE status IN ('pending', 'failed')
                  AND next_attempt_at <= now()
                  AND attempts < max_attempts
                ORDER BY next_attempt_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            )
            if not row:
                return None

            await conn.execute(
                """
                UPDATE webhook_events
                SET status = 'processing',
                    locked_by = $1,
                    locked_at = now()
                WHERE id = $2
                """,
                _WORKER_ID,
                row["id"],
            )
            return {
                "id": row["id"],
                "payload": row["payload"] if isinstance(row["payload"], dict)
                           else json.loads(row["payload"]),
                "attempts": row["attempts"],
                "max_attempts": row["max_attempts"],
            }


async def mark_event_done(event_id: Any) -> None:
    if not get_pool():
        return
    await fetch_one(
        """
        UPDATE webhook_events
        SET status = 'done',
            processed_at = now(),
            locked_by = NULL,
            locked_at = NULL,
            last_error = NULL
        WHERE id = $1
        RETURNING id
        """,
        event_id,
    )


async def mark_event_failed(
    event_id: Any,
    error: str,
    *,
    attempts: int,
    max_attempts: int,
) -> None:
    """
    Marque l'évènement comme `failed` (retentable) ou `failed` permanent quand
    `attempts + 1 >= max_attempts`. Le worker re-claim la ligne au prochain
    cycle quand `next_attempt_at` est dépassé.
    """
    if not get_pool():
        return
    new_attempts = attempts + 1
    next_at = _next_attempt_at(new_attempts)
    truncated = (error or "")[:1000]

    if new_attempts >= max_attempts:
        # On garde `status = 'failed'` mais l'index `idx_webhook_events_ready`
        # filtre déjà sur `attempts < max_attempts` côté claim - donc le
        # worker ne retentera plus. La ligne reste en DB pour audit.
        logger.error(
            "❌ webhook_event %s définitivement échoué après %d tentatives: %s",
            event_id,
            new_attempts,
            truncated[:200],
        )

    await fetch_one(
        """
        UPDATE webhook_events
        SET status = 'failed',
            attempts = $2,
            last_error = $3,
            next_attempt_at = $4,
            locked_by = NULL,
            locked_at = NULL
        WHERE id = $1
        RETURNING id
        """,
        event_id,
        new_attempts,
        truncated,
        next_at,
    )


# ─── Observabilité (lecture admin) ───────────────────────────────────────────


async def list_webhook_events(
    *,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Liste les évènements de la file pour un endpoint admin.

    `payload` est *exclu* de la projection (peut être très gros) - on l'expose
    via `get_webhook_event_detail()` quand on cible une ligne précise.
    """
    if not get_pool():
        return []

    if status:
        rows = await fetch_all(
            """
            SELECT id, signature_id, source, status, attempts, max_attempts,
                   last_error, locked_by, locked_at,
                   next_attempt_at, received_at, processed_at
            FROM webhook_events
            WHERE status = $1
            ORDER BY received_at DESC
            LIMIT $2 OFFSET $3
            """,
            status,
            min(limit, 500),
            max(offset, 0),
        )
    else:
        rows = await fetch_all(
            """
            SELECT id, signature_id, source, status, attempts, max_attempts,
                   last_error, locked_by, locked_at,
                   next_attempt_at, received_at, processed_at
            FROM webhook_events
            ORDER BY received_at DESC
            LIMIT $1 OFFSET $2
            """,
            min(limit, 500),
            max(offset, 0),
        )
    return rows


async def get_webhook_event_stats() -> Dict[str, Any]:
    """
    Tableau de bord rapide : compteurs par statut + plus vieil évènement
    `pending` ou `failed` (utile pour détecter une file qui ne draine plus).
    """
    if not get_pool():
        return {"available": False}

    stats_rows = await fetch_all(
        "SELECT status, count(*) AS count FROM webhook_events GROUP BY status"
    )
    by_status = {r["status"]: r["count"] for r in stats_rows}

    oldest = await fetch_one(
        """
        SELECT id, status, received_at, attempts, last_error
        FROM webhook_events
        WHERE status IN ('pending', 'failed')
          AND attempts < max_attempts
        ORDER BY received_at ASC
        LIMIT 1
        """
    )

    return {
        "available": True,
        "by_status": by_status,
        "total": sum(by_status.values()),
        "oldest_unprocessed": oldest,
    }


async def get_webhook_event_detail(event_id: Any) -> Optional[Dict[str, Any]]:
    """Détail complet d'un évènement (incluant `payload` JSONB)."""
    if not get_pool():
        return None
    return await fetch_one(
        "SELECT * FROM webhook_events WHERE id = $1",
        event_id,
    )


async def retry_webhook_event(event_id: Any) -> bool:
    """
    Force le retry d'un évènement échoué : remet `pending`, reset le compteur
    de tentatives à `max_attempts - 1` (pour laisser une dernière chance), et
    `next_attempt_at = now()` pour le claim immédiat.

    Renvoie True si une ligne a été mise à jour.
    """
    if not get_pool():
        return False
    row = await fetch_one(
        """
        UPDATE webhook_events
        SET status = 'pending',
            attempts = GREATEST(0, max_attempts - 1),
            last_error = NULL,
            locked_by = NULL,
            locked_at = NULL,
            next_attempt_at = now()
        WHERE id = $1
        RETURNING id
        """,
        event_id,
    )
    return row is not None


# ─── Worker périodique ───────────────────────────────────────────────────────


async def periodic_process_webhook_events() -> None:
    """
    Boucle infinie de traitement de la file. À lancer comme `asyncio.create_task`
    dans `main.startup_event()`.

    Annulable proprement via CancelledError (cf. `shutdown_event`).
    """
    # Import local pour éviter une dépendance circulaire au démarrage du module.
    from app.services.message_service import handle_incoming_message

    if not get_pool():
        logger.warning(
            "Pool PostgreSQL indisponible (DATABASE_URL absent ou création du pool échouée) : "
            "worker webhook_events désactivé. Les webhooks repasseront par le fallback "
            "asyncio.create_task."
        )
        return

    logger.info("✅ Webhook events worker démarré (id=%s)", _WORKER_ID)

    # Au démarrage on récupère toujours les locks orphelins (worker mort
    # entre `claim_next_event` et `mark_event_done` lors d'un précédent run).
    try:
        await reclaim_stale_processing()
    except Exception:
        logger.exception("Erreur lors du reclaim initial des webhook_events")

    last_reclaim = datetime.now(timezone.utc)

    while True:
        try:
            # Reclaim périodique pour les workers tombés en cours de run.
            if datetime.now(timezone.utc) - last_reclaim > timedelta(minutes=1):
                try:
                    await reclaim_stale_processing()
                except Exception:
                    logger.exception("reclaim_stale_processing a échoué")
                last_reclaim = datetime.now(timezone.utc)

            processed_in_batch = 0
            for _ in range(_BATCH_SIZE):
                event = await claim_next_event()
                if not event:
                    break

                processed_in_batch += 1
                event_id = event["id"]
                try:
                    await handle_incoming_message(event["payload"])
                    await mark_event_done(event_id)
                    logger.info("✅ webhook_event %s traité", event_id)
                except asyncio.CancelledError:
                    # Important: on remet en pending pour que le prochain
                    # worker reprenne, sinon la ligne reste en `processing`
                    # jusqu'au reclaim.
                    await mark_event_failed(
                        event_id,
                        "worker_cancelled",
                        attempts=event["attempts"],
                        max_attempts=event["max_attempts"],
                    )
                    raise
                except Exception as exc:
                    logger.error(
                        "❌ Erreur traitement webhook_event %s: %s",
                        event_id,
                        exc,
                        exc_info=True,
                    )
                    await mark_event_failed(
                        event_id,
                        f"{type(exc).__name__}: {exc}",
                        attempts=event["attempts"],
                        max_attempts=event["max_attempts"],
                    )

            # File vide ou batch consommé → petite pause pour ne pas spinner.
            if processed_in_batch == 0:
                await asyncio.sleep(_IDLE_SLEEP_SECONDS)
            else:
                # On reboucle immédiatement pour drainer en cas de pic.
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            logger.info("🛑 Webhook events worker arrêté")
            raise
        except Exception:
            logger.exception("Erreur dans la boucle webhook_events worker")
            await asyncio.sleep(_IDLE_SLEEP_SECONDS)
