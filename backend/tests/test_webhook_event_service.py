"""
Tests purs sur la logique de la file durable webhook_events
(`app.services.webhook_event_service`).

On teste les briques qui ne dépendent PAS du pool PostgreSQL :
  - `_compute_signature_id` : déduplication des retries Meta
  - `_next_attempt_at`      : back-off exponentiel des retries

Les fonctions DB-dépendantes (`enqueue`, `claim_next`, `mark_*`) sont testées
en intégration (séparément) : ici on garantit juste qu'elles renvoient None
quand le pool est absent (mode dev sans DATABASE_URL).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.services import webhook_event_service as svc


# ─── _compute_signature_id ───────────────────────────────────────────────────


def test_signature_id_uses_message_ids_when_present():
    """
    Quand le payload contient des messages, l'ID est dérivé des `messages[*].id`
    Meta - c'est ce qui rend les retries Meta idempotents.
    """
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {"id": "wamid.AAA"},
                                {"id": "wamid.BBB"},
                            ]
                        }
                    }
                ]
            }
        ]
    }
    sig = svc._compute_signature_id(payload)
    # Les IDs sont triés pour être stables peu importe l'ordre Meta
    assert sig == "m:wamid.AAA|m:wamid.BBB"


def test_signature_id_includes_status_with_state():
    """
    Pour les statuses, l'ID inclut aussi le statut (sent/delivered/read) car
    Meta peut envoyer plusieurs statuses pour le même `id`.
    """
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {"id": "wamid.XXX", "status": "delivered"},
                                {"id": "wamid.XXX", "status": "read"},
                            ]
                        }
                    }
                ]
            }
        ]
    }
    sig = svc._compute_signature_id(payload)
    # Les deux statuses doivent compter comme évènements distincts
    assert "s:wamid.XXX:delivered" in sig
    assert "s:wamid.XXX:read" in sig


def test_signature_id_falls_back_to_sha256_for_unknown_payloads():
    """
    Pas de messages ni statuses → on hashe le body. Garantit l'unicité même
    pour des évènements `account_update`, `message_template_status_update`...
    """
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"foo": "bar"}}]}]}
    sig = svc._compute_signature_id(payload)
    assert sig.startswith("sha256:")
    # 7 = len("sha256:") ; 64 = SHA-256 hex
    assert len(sig) == 7 + 64


def test_signature_id_is_stable_across_calls():
    payload = {"entry": [{"changes": [{"value": {"messages": [{"id": "wamid.ZZZ"}]}}]}]}
    assert svc._compute_signature_id(payload) == svc._compute_signature_id(payload)


def test_signature_id_independent_of_message_order():
    """L'ordre des messages dans le payload Meta ne doit pas changer la signature."""
    payload_a = {"entry": [{"changes": [{"value": {"messages": [{"id": "A"}, {"id": "B"}]}}]}]}
    payload_b = {"entry": [{"changes": [{"value": {"messages": [{"id": "B"}, {"id": "A"}]}}]}]}
    assert svc._compute_signature_id(payload_a) == svc._compute_signature_id(payload_b)


def test_signature_id_handles_empty_payload():
    sig = svc._compute_signature_id({})
    # Pas de messages.id, pas d'erreur, fallback hash
    assert sig.startswith("sha256:")


def test_signature_id_handles_malformed_payload():
    """Robustesse : un payload bizarre ne fait pas crasher la fonction."""
    sig = svc._compute_signature_id({"entry": "not a list"})
    # AttributeError attrapé → fallback hash
    assert sig.startswith("sha256:")


# ─── _next_attempt_at ────────────────────────────────────────────────────────


def test_next_attempt_at_first_retry_is_short():
    """1ère tentative ratée → re-essai dans ~5 secondes."""
    before = datetime.now(timezone.utc)
    next_at = svc._next_attempt_at(attempts=0)
    delta = (next_at - before).total_seconds()
    assert 4 <= delta <= 8, f"Attendu ~5s, obtenu {delta}s"


def test_next_attempt_at_grows_exponentially():
    """Le délai doit croître à chaque échec (5s → 25s → 2min → 10min → 50min)."""
    deltas = []
    before = datetime.now(timezone.utc)
    for attempts in range(0, 5):
        delta = (svc._next_attempt_at(attempts) - before).total_seconds()
        deltas.append(delta)
    # Strictement croissant
    for i in range(1, len(deltas)):
        assert deltas[i] > deltas[i - 1], f"non-monotone: {deltas}"


def test_next_attempt_at_capped_at_one_hour():
    """Garde-fou : même après beaucoup d'échecs, on ne dépasse jamais 1h."""
    before = datetime.now(timezone.utc)
    next_at = svc._next_attempt_at(attempts=99)
    delta = (next_at - before).total_seconds()
    assert delta <= 3700, f"cap dépassé: {delta}s"


# ─── Comportement sans pool DB ──────────────────────────────────────────────


def test_enqueue_returns_none_when_no_pool():
    """En dev sans DATABASE_URL, l'enqueue doit échouer proprement (pas crash)."""
    with patch("app.services.webhook_event_service.get_pool", return_value=None):
        result = asyncio.run(svc.enqueue_webhook_event({"foo": "bar"}))
        assert result is None


def test_reclaim_returns_zero_when_no_pool():
    with patch("app.services.webhook_event_service.get_pool", return_value=None):
        result = asyncio.run(svc.reclaim_stale_processing())
        assert result == 0


def test_claim_returns_none_when_no_pool():
    with patch("app.services.webhook_event_service.get_pool", return_value=None):
        result = asyncio.run(svc.claim_next_event())
        assert result is None


def test_periodic_worker_exits_cleanly_when_no_pool():
    """
    Le worker périodique doit se *terminer* (pas boucler) quand le pool est
    absent - sinon on log en boucle "DATABASE_URL non configuré".
    """
    with patch("app.services.webhook_event_service.get_pool", return_value=None):
        # Doit se terminer immédiatement sans timeout.
        asyncio.run(asyncio.wait_for(svc.periodic_process_webhook_events(), timeout=2.0))


# ─── Tunables ────────────────────────────────────────────────────────────────


def test_worker_id_is_unique_per_process():
    """Le worker_id contient hostname:pid → utile pour debug le `locked_by`."""
    assert ":" in svc._WORKER_ID
    hostname, pid = svc._WORKER_ID.split(":", 1)
    assert hostname  # non vide
    assert pid.isdigit()
