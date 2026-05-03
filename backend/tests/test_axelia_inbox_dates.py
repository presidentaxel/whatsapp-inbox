"""Tests pour le filtre temporel `since` / `until` de search_inbox_messages."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import axelia_inbox_tools as tools
from app.services import playground_skills as skills


# ---------------------------------------------------------------------------
# parse_iso_datetime
# ---------------------------------------------------------------------------


def test_parse_iso_date_only_assumes_midnight_utc():
    dt = tools.parse_iso_datetime("2025-04-01")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert (dt.year, dt.month, dt.day) == (2025, 4, 1)
    assert (dt.hour, dt.minute, dt.second, dt.microsecond) == (0, 0, 0, 0)


def test_parse_iso_date_only_end_of_day():
    dt = tools.parse_iso_datetime("2025-04-30", end_of_day=True)
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == (2025, 4, 30)
    assert (dt.hour, dt.minute, dt.second, dt.microsecond) == (
        23,
        59,
        59,
        999_999,
    )


def test_parse_iso_with_z_suffix():
    dt = tools.parse_iso_datetime("2025-04-01T08:30:00Z")
    assert dt is not None
    assert dt == datetime(2025, 4, 1, 8, 30, 0, tzinfo=timezone.utc)


def test_parse_iso_with_offset():
    dt = tools.parse_iso_datetime("2025-04-01T10:00:00+02:00")
    assert dt is not None
    # Comparaison robuste : on compare la version UTC pour ne pas dépendre du tzinfo retourné.
    assert dt.astimezone(timezone.utc) == datetime(
        2025, 4, 1, 8, 0, 0, tzinfo=timezone.utc
    )


def test_parse_iso_naive_assumes_utc():
    dt = tools.parse_iso_datetime("2025-04-01T12:34:56")
    assert dt is not None
    assert dt.tzinfo == timezone.utc


def test_parse_iso_invalid_returns_none():
    assert tools.parse_iso_datetime("hier") is None
    assert tools.parse_iso_datetime("not-a-date") is None
    assert tools.parse_iso_datetime("") is None
    assert tools.parse_iso_datetime(None) is None


def test_parse_iso_passthrough_datetime():
    raw = datetime(2025, 4, 1, tzinfo=timezone.utc)
    assert tools.parse_iso_datetime(raw) is raw


# ---------------------------------------------------------------------------
# _resolve_date_range : auto-correction si since > until
# ---------------------------------------------------------------------------


def test_resolve_date_range_swaps_when_inverted():
    s, u = tools._resolve_date_range("2025-04-30", "2025-04-01")
    assert s is not None and u is not None
    assert s.day == 1
    assert u.day == 30


def test_resolve_date_range_keeps_order():
    s, u = tools._resolve_date_range("2025-04-01", "2025-04-30")
    assert s.day == 1
    assert u.day == 30


def test_resolve_date_range_handles_partial():
    s, u = tools._resolve_date_range("2025-04-01", None)
    assert s is not None and u is None
    s, u = tools._resolve_date_range(None, "2025-04-30")
    assert s is None and u is not None


# ---------------------------------------------------------------------------
# _to_naive_utc : asyncpg refuse les datetimes aware sur `timestamp without time zone`.
# ---------------------------------------------------------------------------


def test_to_naive_utc_strips_tzinfo_and_normalises():
    aware = datetime(2025, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
    naive = tools._to_naive_utc(aware)
    assert naive.tzinfo is None
    assert naive == datetime(2025, 4, 1, 10, 0, 0)


def test_to_naive_utc_converts_offset_to_utc():
    """Un datetime en +02:00 doit être projeté en UTC avant de perdre tzinfo."""
    dt = tools.parse_iso_datetime("2024-05-14T00:00:00+02:00")
    assert dt is not None
    naive = tools._to_naive_utc(dt)
    assert naive.tzinfo is None
    # 00:00 +02:00 == 22:00 UTC le 13 mai
    assert naive == datetime(2024, 5, 13, 22, 0, 0)


def test_to_naive_utc_passthrough_when_already_naive():
    dt = datetime(2024, 5, 14, 12, 0, 0)
    assert tools._to_naive_utc(dt) is dt


# ---------------------------------------------------------------------------
# Régression : avant la correction, passer un datetime aware à asyncpg sur la
# colonne `timestamp without time zone` levait `DataError: can't subtract
# offset-naive and offset-aware datetimes`. On vérifie ici que le pool path
# convertit bien en datetimes naïfs avant le bind.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_path_binds_naive_datetimes(monkeypatch):
    """Le bind asyncpg ne doit jamais recevoir de datetime aware pour `m.timestamp`."""

    captured = {"params": None}

    async def fake_fetch_all(query, *args, **kwargs):
        captured["params"] = list(args)
        return []

    # Force la voie pool : `get_pool()` doit retourner quelque chose de truthy.
    monkeypatch.setattr(tools, "get_pool", lambda: SimpleNamespace(name="dummy"))
    monkeypatch.setattr(tools, "fetch_all", fake_fetch_all)

    out = await tools.search_messages_text_for_account(
        "11111111-1111-1111-1111-111111111111",
        "remboursement",
        limit=10,
        match_mode="all",
        since="2024-05-14T00:00:00+02:00",
        until="2024-05-31",
    )

    assert out["total"] == 0
    params = captured["params"]
    assert params is not None
    # Tous les datetimes liés en SQL doivent être naïfs.
    aware = [p for p in params if isinstance(p, datetime) and p.tzinfo is not None]
    assert aware == [], f"asyncpg recevrait des datetimes aware : {aware!r}"
    # Et il y a bien deux bornes de date dans les params.
    naive = [p for p in params if isinstance(p, datetime) and p.tzinfo is None]
    assert len(naive) == 2
    # since (en UTC) = 2024-05-13 22:00 ; until (date pure) = 2024-05-31 23:59:59.999999
    assert naive[0] == datetime(2024, 5, 13, 22, 0, 0)
    assert naive[1] == datetime(2024, 5, 31, 23, 59, 59, 999_999)


@pytest.mark.asyncio
async def test_pool_path_includes_date_filter_meta(monkeypatch):
    """Le payload retourné expose `date_filter` (pour que le LLM cite la plage)."""

    async def fake_fetch_all(query, *args, **kwargs):
        return []

    monkeypatch.setattr(tools, "get_pool", lambda: SimpleNamespace(name="dummy"))
    monkeypatch.setattr(tools, "fetch_all", fake_fetch_all)

    out = await tools.search_messages_text_for_account(
        "11111111-1111-1111-1111-111111111111",
        "bug",
        since="2025-04-01",
        until="2025-04-30",
    )
    assert "date_filter" in out
    assert "since" in out["date_filter"]
    assert "until" in out["date_filter"]


# ---------------------------------------------------------------------------
# Catalogue exposé au LLM : la doc des paramètres `since`/`until` doit y figurer.
# ---------------------------------------------------------------------------


def test_skill_catalog_advertises_date_params():
    entry = next(
        (s for s in skills.AXELIA_ONLY_SKILLS if s["name"] == "search_inbox_messages"),
        None,
    )
    assert entry is not None
    param_names = {p["name"] for p in entry["parameters"]}
    assert {"since", "until"}.issubset(param_names)
    desc = entry["description"]
    assert "since" in desc and "until" in desc


def test_axelia_skills_prompt_section_mentions_dates():
    text = skills.get_axelia_skills_prompt_section()
    assert "since" in text and "until" in text


# ---------------------------------------------------------------------------
# Validation côté skill wrapper (sans accès Supabase) : un `since` invalide
# remonte une erreur explicite plutôt qu'un filtrage silencieux.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_rejects_invalid_since():
    out = await skills._skill_search_inbox_messages(
        {"query": "bonjour", "since": "hier"},
        {"id": "00000000-0000-0000-0000-000000000000"},
    )
    assert "error" in out
    assert "since" in out["error"].lower()
    assert out["hits"] == []


@pytest.mark.asyncio
async def test_skill_rejects_invalid_until():
    out = await skills._skill_search_inbox_messages(
        {"query": "bonjour", "until": "demain"},
        {"id": "00000000-0000-0000-0000-000000000000"},
    )
    assert "error" in out
    assert "until" in out["error"].lower()


@pytest.mark.asyncio
async def test_skill_forwards_valid_dates(monkeypatch):
    """Patch la fonction métier pour vérifier que le wrapper passe bien `since`/`until`."""

    captured: dict = {}

    async def fake_search(account_id, query, **kwargs):
        captured["account_id"] = account_id
        captured["query"] = query
        captured["since"] = kwargs.get("since")
        captured["until"] = kwargs.get("until")
        captured["limit"] = kwargs.get("limit")
        captured["match_mode"] = kwargs.get("match_mode")
        return {"hits": [], "total": 0}

    # Le skill wrapper importe la fonction depuis axelia_inbox_tools à l'intérieur de la
    # fonction (import différé), donc on patch dans ce module-source.
    monkeypatch.setattr(
        tools, "search_messages_text_for_account", fake_search
    )

    out = await skills._skill_search_inbox_messages(
        {
            "query": "remboursement",
            "since": "2025-04-01",
            "until": "2025-04-30",
            "limit": 12,
            "match_mode": "any",
        },
        {"id": "11111111-1111-1111-1111-111111111111"},
    )

    assert out == {"hits": [], "total": 0}
    assert captured["account_id"] == "11111111-1111-1111-1111-111111111111"
    assert captured["query"] == "remboursement"
    assert captured["since"] == "2025-04-01"
    assert captured["until"] == "2025-04-30"
    assert captured["limit"] == 12
    assert captured["match_mode"] == "any"
