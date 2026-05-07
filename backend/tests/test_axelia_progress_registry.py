"""Registre de progression in-memory : set / get / clear / TTL / ownership."""

import time

from app.services.axelia_chat_service import (
    progress_clear,
    progress_get,
    progress_set,
)


def test_set_and_get():
    key = "key-set-and-get"
    progress_set(key, {"phase": "thinking", "user_id": "u1"})
    p = progress_get(key, owner_user_id="u1")
    assert p is not None
    assert p["phase"] == "thinking"
    assert p["user_id"] == "u1"
    assert "ts" in p
    progress_clear(key)


def test_owner_filter_blocks_other_user():
    key = "key-owner-filter"
    progress_set(key, {"phase": "tool", "user_id": "alice"})
    assert progress_get(key, owner_user_id="alice") is not None
    assert progress_get(key, owner_user_id="bob") is None
    # Sans filtre owner, on accepte (utile pour les tests / debug interne).
    raw = progress_get(key)
    assert raw and raw.get("user_id") == "alice"
    progress_clear(key)


def test_owner_filter_rejects_entries_without_user_id():
    key = "key-owner-missing-user-id"
    progress_set(key, {"phase": "tool"})
    assert progress_get(key, owner_user_id="alice") is None
    progress_clear(key)


def test_clear_removes_entry():
    key = "key-clear"
    progress_set(key, {"phase": "received"})
    assert progress_get(key) is not None
    progress_clear(key)
    assert progress_get(key) is None


def test_set_merges_payload():
    """Les appels successifs n’écrasent que les champs fournis (merge)."""
    key = "key-merge"
    progress_set(key, {"phase": "thinking", "user_id": "u9", "skills": []})
    progress_set(key, {"skill": "list_templates"})
    p = progress_get(key, owner_user_id="u9")
    assert p["phase"] == "thinking"
    assert p["skill"] == "list_templates"
    assert p["skills"] == []
    progress_clear(key)


def test_empty_key_is_noop():
    progress_set("", {"phase": "thinking"})
    assert progress_get("") is None
    # Ne lève pas non plus en clear
    progress_clear(None)
    progress_clear("")


def test_get_returns_copy_not_internal_ref():
    """Le dict retourné est isolé : muter le résultat ne corrompt pas le registre."""
    key = "key-copy"
    progress_set(key, {"phase": "thinking", "user_id": "u"})
    p = progress_get(key, owner_user_id="u")
    p["phase"] = "MUTATED"
    fresh = progress_get(key, owner_user_id="u")
    assert fresh["phase"] == "thinking"
    progress_clear(key)


def test_ts_is_recent():
    key = "key-ts"
    before = time.time()
    progress_set(key, {"phase": "thinking"})
    p = progress_get(key)
    after = time.time()
    assert before - 0.5 <= p["ts"] <= after + 0.5
    progress_clear(key)
