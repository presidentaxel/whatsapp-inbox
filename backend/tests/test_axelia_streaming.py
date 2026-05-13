"""Tests pour les briques streaming/budget/metrics ajoutées à axelia_chat_service.

Tous purement unitaires (pas d'appel Gemini réel).
"""

from __future__ import annotations

import json

import pytest

from app.services import axelia_chat_service as svc


# ---------------------------------------------------------------------------
# Extracteur de reply partiel pour le streaming JSON
# ---------------------------------------------------------------------------


def _accumulate(consume, chunks):
    out = []
    for c in chunks:
        delta = consume(c)
        if delta:
            out.append(delta)
    return "".join(out)


def test_partial_reply_extractor_simple_split():
    consume, finalize = svc.make_partial_reply_extractor()
    full_json = '{"reply": "Bonjour le monde", "tool_calls": []}'
    # Coupe en plusieurs chunks
    chunks = [full_json[:5], full_json[5:15], full_json[15:30], full_json[30:]]
    assembled = _accumulate(consume, chunks)
    assert assembled == "Bonjour le monde"
    assert finalize() == "Bonjour le monde"


def test_partial_reply_extractor_handles_escapes():
    consume, finalize = svc.make_partial_reply_extractor()
    full_json = json.dumps(
        {"reply": "Ligne 1\nLigne 2 avec \"guillemets\" et \\backslash", "tool_calls": []},
        ensure_ascii=False,
    )
    out = ""
    # On envoie 1 caractère à la fois pour stresser l'état "échappement partiel"
    for ch in full_json:
        d = consume(ch)
        if d:
            out += d
    assert out == "Ligne 1\nLigne 2 avec \"guillemets\" et \\backslash"


def test_partial_reply_extractor_truncated_returns_partial():
    consume, finalize = svc.make_partial_reply_extractor()
    truncated = '{"reply": "Texte coupe au milieu'
    out = _accumulate(consume, [truncated])
    assert out == "Texte coupe au milieu"
    # finalize() peut renvoyer la même valeur (best-effort)
    assert finalize() == "Texte coupe au milieu"


def test_partial_reply_extractor_no_reply_field():
    consume, finalize = svc.make_partial_reply_extractor()
    # Pas de champ reply → ne devrait rien émettre
    out = _accumulate(consume, ['{"tool_calls": [{"skill": "x"}]}'])
    assert out == ""
    assert finalize() == ""


# ---------------------------------------------------------------------------
# Découpage texte (effet « tape-à-l'écran » côté streaming simulé)
# ---------------------------------------------------------------------------


def test_chunk_text_preserves_full_content():
    text = (
        "Voici une réponse Axelia un peu longue avec plusieurs phrases. "
        "Elle doit être restituée intégralement après recollage des morceaux."
    )
    parts = list(svc._chunk_text(text))
    assert "".join(parts) == text
    assert len(parts) > 1


def test_chunk_text_empty():
    assert list(svc._chunk_text("")) == []


# ---------------------------------------------------------------------------
# Métriques observabilité
# ---------------------------------------------------------------------------


def test_metrics_record_and_snapshot_basics():
    svc.metrics_reset_for_tests()
    svc.metrics_record_call(
        model="gemini-2.5-flash",
        duration_ms=1234.5,
        used_tools=False,
        skill_rounds=0,
        skill_executions=0,
        used_classifier=False,
        used_pro=False,
        json_partial=False,
        json_failed=False,
        failed=False,
        input_tokens=1000,
        output_tokens=200,
        cache_state="miss",
    )
    svc.metrics_record_call(
        model="gemini-2.5-pro",
        duration_ms=5678.9,
        used_tools=True,
        skill_rounds=3,
        skill_executions=4,
        used_classifier=True,
        used_pro=True,
        json_partial=True,
        json_failed=False,
        failed=False,
        input_tokens=4000,
        output_tokens=1500,
        cache_state="hit",
    )
    snap = svc.metrics_snapshot()
    c = snap["counters"]
    assert c["calls_total"] == 2
    assert c["calls_with_tools"] == 1
    assert c["calls_no_tools"] == 1
    assert c["calls_pro_model"] == 1
    assert c["calls_fast_model"] == 1
    assert c["calls_classifier_full"] == 1
    assert c["calls_classifier_shortcut"] == 1
    assert c["json_parse_partial"] == 1
    assert c["context_cache_hits"] == 1
    assert c["context_cache_misses"] == 1
    assert c["input_tokens_total"] == 5000
    assert c["output_tokens_total"] == 1700

    ratios = snap["ratios"]
    assert ratios["pro_share"] == 0.5
    assert ratios["tools_share"] == 0.5

    per_model = snap["per_model"]
    assert "gemini-2.5-flash" in per_model
    assert per_model["gemini-2.5-flash"]["calls"] == 1
    assert per_model["gemini-2.5-flash"]["avg_duration_ms"] == 1234.5

    assert len(snap["recent"]) == 2


def test_metrics_failure_counts():
    svc.metrics_reset_for_tests()
    svc.metrics_record_call(
        model="gemini-2.5-flash",
        duration_ms=10.0,
        used_tools=False,
        skill_rounds=0,
        skill_executions=0,
        used_classifier=False,
        used_pro=False,
        json_partial=False,
        json_failed=True,
        failed=True,
    )
    snap = svc.metrics_snapshot()
    assert snap["counters"]["calls_failed"] == 1
    assert snap["counters"]["json_parse_failed"] == 1
    assert snap["ratios"]["failure_rate"] == 1.0


# ---------------------------------------------------------------------------
# Estimation tokens
# ---------------------------------------------------------------------------


def test_estimate_tokens_grows_with_text():
    short = svc._estimate_tokens("Bonjour")
    longer = svc._estimate_tokens("Bonjour " * 100)
    assert short >= 1
    assert longer > short


def test_approx_tokens_in_response_extracts_usage():
    data = {
        "usageMetadata": {
            "promptTokenCount": 1500,
            "candidatesTokenCount": 1700,  # totalTokenCount style (incluant prompt)
            "totalTokenCount": 1700,
        }
    }
    in_tok, out_tok = svc._approx_tokens_in_response(data)
    assert in_tok == 1500
    assert out_tok == 200  # 1700 - 1500


def test_approx_tokens_in_response_missing():
    in_tok, out_tok = svc._approx_tokens_in_response({})
    assert in_tok == 0
    assert out_tok == 0


# ---------------------------------------------------------------------------
# Résumé d'historique (déclenchement / no-op)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_old_turns_noop_below_threshold():
    msgs = [{"role": "user", "text": f"msg {i}"} for i in range(5)]
    out = await svc.maybe_summarize_old_turns(
        msgs, fast_model="gemini-2.5-flash", log_label="test"
    )
    assert out == msgs


@pytest.mark.asyncio
async def test_summarize_old_turns_keeps_recent(monkeypatch):
    # Stub _call_gemini_api_once pour éviter un vrai appel réseau
    async def fake_call(*args, **kwargs):
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Résumé synthétique des échanges précédents."}]
                    }
                }
            ]
        }

    monkeypatch.setattr(svc, "_call_gemini_api_once", fake_call)

    msgs = [
        {"role": "user" if i % 2 == 0 else "model", "text": f"message #{i}"}
        for i in range(40)
    ]
    out = await svc.maybe_summarize_old_turns(
        msgs, fast_model="gemini-2.5-flash", log_label="test"
    )
    # Doit contenir 1 message synthétique en tête + les 16 derniers
    assert len(out) == 1 + svc._HISTORY_SUMMARY_KEEP_RECENT
    assert "Résumé" in (out[0].get("text") or "")
    # Les 16 derniers messages d'origine sont préservés
    last_orig = msgs[-svc._HISTORY_SUMMARY_KEEP_RECENT:]
    assert out[1:] == last_orig


# ---------------------------------------------------------------------------
# Context cache : cache key + skip si trop court
# ---------------------------------------------------------------------------


def test_context_cache_key_stable_and_distinct():
    a = svc._context_cache_key("gemini-2.5-flash", "Système A")
    b = svc._context_cache_key("gemini-2.5-flash", "Système A")
    c = svc._context_cache_key("gemini-2.5-flash", "Système B")
    d = svc._context_cache_key("gemini-2.5-pro", "Système A")
    assert a == b
    assert a != c
    assert a != d


def test_context_cache_eligible_model():
    assert svc._context_cache_eligible_model("gemini-2.5-flash") is True
    assert svc._context_cache_eligible_model("gemini-1.0-pro") is False
    assert svc._context_cache_eligible_model("") is False


@pytest.mark.asyncio
async def test_context_cache_skips_short_system_prompt(monkeypatch):
    # Système trop court → skip sans appel réseau
    name, state = await svc.maybe_get_or_create_context_cache(
        model_id="gemini-2.5-flash",
        system_text="Système court",
        log_label="test",
    )
    assert name is None
    assert state == "skip"


# ---------------------------------------------------------------------------
# SSE format helper
# ---------------------------------------------------------------------------


def test_format_sse_correct_structure():
    out = svc._format_sse("token", {"chunk": "Bonjour"})
    text = out.decode("utf-8")
    assert text.startswith("event: token\n")
    assert "\ndata: {" in text
    assert text.endswith("\n\n")
    payload_line = [l for l in text.split("\n") if l.startswith("data:")][0]
    payload = json.loads(payload_line[6:])
    assert payload == {"chunk": "Bonjour"}


# ---------------------------------------------------------------------------
# Ancrage temporel du prompt système
# ---------------------------------------------------------------------------


def test_today_anchor_prompt_contains_iso_date():
    from datetime import datetime, timezone

    fixed = datetime(2026, 4, 30, 13, 5, tzinfo=timezone.utc)
    out = svc._today_anchor_prompt(now=fixed)

    assert "DATE COURANTE" in out
    assert "FIN DATE COURANTE" in out
    assert "2026-04-30" in out
    assert "jeudi" in out
    assert "30 avril 2026" in out
    assert "S18-2026" in out
    assert "search_inbox_messages" in out


def test_today_anchor_prompt_warns_against_training_year():
    out = svc._today_anchor_prompt()
    assert "entraînement" in out
    assert "année" in out


def test_compose_axelia_system_text_includes_today_anchor():
    full = svc._compose_axelia_system_text("\n\nPÉRIMÈTRE TEST")
    assert svc._AXELIA_SYSTEM_PROMPT.split(".")[0] in full
    assert "=== DATE COURANTE" in full
    assert "PÉRIMÈTRE TEST" in full
    assert full.find("DATE COURANTE") < full.find("PÉRIMÈTRE TEST")


def test_compose_axelia_system_text_expert_depth_instruction():
    full = svc._compose_axelia_system_text(response_depth="expert")
    assert "MODE DE RÉPONSE = EXPERT" in full
    assert "recommandations priorisées" in full


def test_skill_budget_profile_by_depth():
    assert svc._skill_budget_profile("brief") == (6, 45_000, 1)
    assert svc._skill_budget_profile("standard") == (
        svc._MAX_SKILL_ROUNDS_HARD,
        svc._MAX_SKILL_TOKENS_BUDGET,
        svc._MAX_SKILL_ROUNDS_NO_PROGRESS,
    )
    assert svc._skill_budget_profile("expert") == (12, 95_000, 3)


# ---------------------------------------------------------------------------
# Parsing classifieur de difficulté (robustesse aux sorties tronquées)
# ---------------------------------------------------------------------------


def test_parse_difficulty_json_well_formed():
    assert svc._parse_difficulty_json('{"difficulty": 0.7}') == pytest.approx(0.7)


def test_parse_difficulty_json_clamps_range():
    assert svc._parse_difficulty_json('{"difficulty": 1.4}') == 1.0
    assert svc._parse_difficulty_json('{"difficulty": -0.2}') == 0.0


def test_parse_difficulty_json_handles_markdown_fence():
    raw = "```json\n{\"difficulty\": 0.3}\n```"
    assert svc._parse_difficulty_json(raw) == pytest.approx(0.3)


def test_parse_difficulty_json_truncated_with_value_returns_value():
    # Cas d'une sortie tronquée par MAX_TOKENS mais avec la valeur déjà émise
    assert svc._parse_difficulty_json('{"difficulty":0.55') == pytest.approx(0.55)


def test_parse_difficulty_json_truncated_without_value_returns_none():
    # Le bug du screenshot : `{"difficulty":` sans valeur → None (et non plus une exception)
    assert svc._parse_difficulty_json('{"difficulty":') is None
    assert svc._parse_difficulty_json('{"difficulty"') is None


def test_parse_difficulty_json_empty_or_garbage_returns_none():
    assert svc._parse_difficulty_json("") is None
    assert svc._parse_difficulty_json("   ") is None
    assert svc._parse_difficulty_json("xyz") is None


def test_parse_difficulty_json_loose_quoting():
    # Variantes de quoting / espacement régulièrement renvoyées par les LLM
    assert svc._parse_difficulty_json('difficulty: 0.4') == pytest.approx(0.4)
    assert svc._parse_difficulty_json("'difficulty': 0.4") == pytest.approx(0.4)
    assert svc._parse_difficulty_json('Voici la difficulté : "difficulty":0.9') == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_run_axelia_chat_expert_forces_pro_and_skips_shortcut(monkeypatch):
    monkeypatch.setattr(svc.settings, "GEMINI_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(svc.settings, "AXELIA_FAST_MODEL", "gemini-2.5-flash", raising=False)
    monkeypatch.setattr(svc.settings, "AXELIA_PRO_MODEL", "gemini-2.5-pro", raising=False)
    monkeypatch.setattr(svc.settings, "AXELIA_DIFFICULTY_THRESHOLD", 0.99, raising=False)

    def _should_not_be_called(_messages):
        raise AssertionError("shortcut must be bypassed in expert mode")

    monkeypatch.setattr(svc, "_maybe_difficulty_shortcut", _should_not_be_called)
    async def _fake_estimate_difficulty(**kwargs):
        return 0.1

    monkeypatch.setattr(svc, "estimate_difficulty", _fake_estimate_difficulty)

    async def _fake_generate_once(**kwargs):
        assert kwargs["model_id"] == "gemini-2.5-pro"
        assert kwargs["response_depth"] == "expert"
        return "ok expert"

    monkeypatch.setattr(svc, "_generate_once", _fake_generate_once)

    text, model, skills, pending = await svc.run_axelia_chat(
        messages=[{"role": "user", "text": "Réponds de façon experte"}],
        response_depth="expert",
        log_label="test-expert",
    )
    assert text == "ok expert"
    assert model == "gemini-2.5-pro"
    assert skills is None
    assert pending is None
