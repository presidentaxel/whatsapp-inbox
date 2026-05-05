"""
Version améliorée de bot_service avec:
- Circuit breaker pour Gemini API
- Retry logic sur les erreurs réseau
- Cache pour les bot profiles
- Meilleure gestion des erreurs
- Timeouts optimisés
- Prompt système structuré + PLAYBOOK délimité
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException

from app.core.cache import cached, invalidate_cache_pattern
from app.core.circuit_breaker import gemini_circuit_breaker, CircuitBreakerOpenError
from app.core.config import settings
from app.core.db import supabase, supabase_execute
from app.core.http_client import get_http_client
from app.core.retry import retry_on_gemini_transient

logger = logging.getLogger("uvicorn.error").getChild("bot.gemini")
logger.setLevel(logging.INFO)

_BOT_CONFIDENCE_MIN_THRESHOLD = 0.72


def _ai_history_line_content(row: Dict[str, Any]) -> str:
    """Texte vu par l’IA : transcription pour audio/voice si disponible, sinon content_text."""
    base = (row.get("content_text") or "").strip()
    mt = (row.get("message_type") or "").lower()
    tr = (row.get("audio_transcript") or "").strip()
    if mt in ("audio", "voice") and tr:
        return tr
    return base


async def fetch_message_history_rows_for_ai(conversation_id: str) -> List[Dict[str, Any]]:
    """Derniers messages de la conversation (ordre chronologique), pour Gemini."""
    lim = max(1, int(getattr(settings, "GEMINI_CONVERSATION_HISTORY_LIMIT", 200) or 200))
    res = await supabase_execute(
        supabase.table("messages")
        .select("direction, content_text, message_type, audio_transcript")
        .eq("conversation_id", conversation_id)
        .order("timestamp", desc=True)
        .limit(lim)
    )
    return list(reversed(res.data or []))


def _truncate_ai_context_text(text: str) -> str:
    max_c = int(getattr(settings, "GEMINI_CONVERSATION_HISTORY_MAX_CHARS", 0) or 0)
    if max_c <= 0 or len(text) <= max_c:
        return text
    return "…(début tronqué)\n" + text[-(max_c - 24) :]


async def conversation_transcript_for_flow_variables(conversation_id: str) -> str:
    """Transcript multiligne pour {{flow_recent_user_text}} et prompts du graphe."""
    rows = await fetch_message_history_rows_for_ai(conversation_id)
    lines: List[str] = []
    for row in rows:
        content = _ai_history_line_content(row)
        if not content:
            continue
        role = "Client" if row.get("direction") == "inbound" else "Entreprise"
        lines.append(f"{role}: {content}")
    return _truncate_ai_context_text("\n".join(lines))


def _normalize_profile(row: Dict[str, Any], account_id: str) -> Dict[str, Any]:
    custom_fields = row.get("custom_fields") or []
    normalized_fields = []
    for field in custom_fields:
        if not isinstance(field, dict):
            continue
        normalized_fields.append(
            {
                "id": field.get("id") or str(uuid.uuid4()),
                "label": field.get("label", "").strip(),
                "value": field.get("value", "").strip(),
            }
        )
    template_config = _sanitize_template_config(row.get("template_config") or {})

    return {
        "id": row.get("id"),
        "account_id": account_id,
        "business_name": row.get("business_name") or "",
        "description": row.get("description") or "",
        "address": row.get("address") or "",
        "hours": row.get("hours") or "",
        "knowledge_base": row.get("knowledge_base") or "",
        "custom_fields": normalized_fields,
        "updated_at": row.get("updated_at"),
        "template_config": template_config,
        "published_playground_flow": row.get("published_playground_flow"),
        "default_playground_flow_id": row.get("default_playground_flow_id"),
    }


@cached(ttl_seconds=300, key_prefix="bot_profile")
async def get_bot_profile(account_id: str) -> Dict[str, Any]:
    """
    Récupère le bot profile avec cache (5 min TTL).

    Les profils changent rarement, le cache évite des appels DB inutiles.
    """
    res = await supabase_execute(
        supabase.table("bot_profiles").select("*").eq("account_id", account_id).limit(1)
    )
    if res.data:
        return _normalize_profile(res.data[0], account_id)

    placeholder = {
        "account_id": account_id,
        "business_name": "",
        "description": "",
        "address": "",
        "hours": "",
        "knowledge_base": "",
        "custom_fields": [],
        "template_config": _sanitize_template_config({}),
        "published_playground_flow": None,
        "default_playground_flow_id": None,
    }
    return placeholder


async def upsert_bot_profile(account_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Met à jour le bot profile et invalide le cache.
    Les clés absentes du payload conservent les valeurs en base (mises à jour partielles).
    """
    res_exist = await supabase_execute(
        supabase.table("bot_profiles").select("*").eq("account_id", account_id).limit(1)
    )
    existing: Dict[str, Any] = dict(res_exist.data[0]) if res_exist.data else {}
    merged: Dict[str, Any] = {**existing, **payload}

    custom_fields = merged.get("custom_fields") or []
    normalized_fields = []
    for field in custom_fields:
        if not field.get("label") and not field.get("value"):
            continue
        normalized_fields.append(
            {
                "id": field.get("id") or str(uuid.uuid4()),
                "label": field.get("label", "").strip(),
                "value": field.get("value", "").strip(),
            }
        )

    upsert_payload = {
        "account_id": account_id,
        "business_name": merged.get("business_name"),
        "description": merged.get("description"),
        "address": merged.get("address"),
        "hours": merged.get("hours"),
        "knowledge_base": merged.get("knowledge_base"),
        "custom_fields": normalized_fields,
        "template_config": _sanitize_template_config(merged.get("template_config") or {}),
    }
    if "published_playground_flow" in merged:
        upsert_payload["published_playground_flow"] = merged.get("published_playground_flow")
    if "default_playground_flow_id" in merged:
        upsert_payload["default_playground_flow_id"] = merged.get("default_playground_flow_id")
    await supabase_execute(
        supabase.table("bot_profiles").upsert(
            upsert_payload,
            on_conflict="account_id",
        )
    )

    # Invalider le cache
    await invalidate_cache_pattern(f"bot_profile:{account_id}")

    return await get_bot_profile(account_id)


# Réponses bot conversationnel : court délai. Playground assist (gros JSON) : voir read_timeout.
_GEMINI_DEFAULT_READ_TIMEOUT_S = 15.0
_GEMINI_PLAYGROUND_ASSIST_READ_TIMEOUT_S = 120.0


def _user_visible_gemini_failure(exc: BaseException) -> str:
    """Message client sans URL ni clé API (les exceptions httpx peuvent les inclure)."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            return (
                "Le fournisseur IA limite temporairement les requêtes. Réessaie dans une minute."
            )
        if code >= 500:
            return (
                "Le service IA est temporairement indisponible ou surchargé (erreur côté Google). "
                "Réessaie dans quelques instants."
            )
        if code == 400:
            return (
                "La requête vers l’IA a été refusée (paramètres ou quota). Vérifie le modèle configuré (GEMINI_MODEL)."
            )
        return f"L’IA a renvoyé une erreur HTTP {code}."
    if isinstance(exc, httpx.TimeoutException):
        return "L’appel à l’IA a expiré. Réessaie avec un message plus court."
    return "Erreur réseau ou inattendue lors de l’appel à l’IA. Réessaie plus tard."


async def _call_gemini_api_once(
    endpoint: str,
    payload: dict,
    conversation_id: str,
    *,
    read_timeout: float = _GEMINI_DEFAULT_READ_TIMEOUT_S,
) -> dict:
    """
    Un POST Gemini sans retry Tenacity.

    À utiliser pour la classification Axelia (un timeout ne doit pas enchaîner 5 rounds).
    """
    client = await get_http_client()

    read_s = float(read_timeout) if read_timeout else _GEMINI_DEFAULT_READ_TIMEOUT_S
    if read_s > _GEMINI_DEFAULT_READ_TIMEOUT_S:
        # Assistant Playground : gros prompt / réponse JSON - laisser plus de marge réseau.
        timeout = httpx.Timeout(
            connect=10.0,
            read=read_s,
            write=60.0,
            pool=5.0,
        )
    else:
        timeout = httpx.Timeout(
            connect=3.0,
            read=read_s,
            write=5.0,
            pool=5.0,
        )

    try:
        response = await client.post(
            endpoint,
            params={"key": settings.GEMINI_API_KEY},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        is_classify = str(conversation_id).startswith("classify-")
        if is_classify:
            logger.warning(
                "Gemini read timeout for %s (read=%ss)",
                conversation_id,
                read_s,
            )
        else:
            logger.error(
                "Gemini timeout for conversation %s (read=%ss)",
                conversation_id,
                read_s,
            )
        raise
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        body = exc.response.text
        logger.error(
            "❌ Gemini API error for conversation %s (status=%s): %s",
            conversation_id,
            status_code,
            body,  # Log full body, not truncated
        )
        raise


@retry_on_gemini_transient(max_attempts=5, min_wait=2.0, max_wait=45.0)
async def _call_gemini_api(
    endpoint: str,
    payload: dict,
    conversation_id: str,
    *,
    read_timeout: float = _GEMINI_DEFAULT_READ_TIMEOUT_S,
) -> dict:
    """
    Appelle l'API Gemini avec retry sur les erreurs réseau.

    Raises:
        httpx.HTTPStatusError: Si l'API retourne une erreur HTTP
        httpx.TimeoutException: Si le timeout est dépassé
        httpx.NetworkError: Si problème réseau
    """
    return await _call_gemini_api_once(
        endpoint, payload, conversation_id, read_timeout=read_timeout
    )


async def generate_bot_reply(
    conversation_id: str,
    account_id: str,
    latest_user_message: str,
    contact_name: Optional[str] = None,
) -> Optional[str]:
    """
    Génère une réponse bot via Gemini avec:
    - Circuit breaker pour éviter les appels si Gemini est down
    - Retry automatique sur les erreurs réseau
    - Timeout réduit (15s au lieu de 45s)
    - Cache du bot profile

    Returns:
        La réponse générée, ou None en cas d'erreur
    """
    if not settings.GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY absent, skipping bot generation for %s", conversation_id)
        return None

    latest_user_message = (latest_user_message or "").strip()
    if not latest_user_message:
        logger.info("Gemini skip: empty user message for %s", conversation_id)
        return None

    payload = await generate_bot_reply_with_confidence(
        conversation_id=conversation_id,
        account_id=account_id,
        latest_user_message=latest_user_message,
        contact_name=contact_name,
    )
    return payload.get("reply")


async def generate_bot_reply_with_confidence(
    conversation_id: str,
    account_id: str,
    latest_user_message: str,
    contact_name: Optional[str] = None,
) -> Dict[str, Any]:
    if not settings.GEMINI_API_KEY:
        return {
            "reply": None,
            "confidence": 0.0,
            "confidence_reasons": ["GEMINI_API_KEY absent côté serveur."],
            "qa_queries_used": [],
        }
    latest_user_message = (latest_user_message or "").strip()
    if not latest_user_message:
        return {
            "reply": None,
            "confidence": 0.0,
            "confidence_reasons": ["Message utilisateur vide."],
            "qa_queries_used": [],
        }

    # Récupérer le profil (avec cache)
    profile = await get_bot_profile(account_id)
    knowledge_text = _build_knowledge_text(profile, contact_name)

    logger.info(
        "Gemini context for conversation %s: account=%s, message_len=%d, knowledge_len=%d",
        conversation_id,
        account_id,
        len(latest_user_message),
        len(knowledge_text),
    )
    logger.debug(
        "Gemini knowledge payload for %s:\n%s",
        conversation_id,
        _trim_for_log(knowledge_text),
    )

    history_rows = await fetch_message_history_rows_for_ai(conversation_id)

    conversation_parts: List[Dict[str, Any]] = []
    for row in history_rows:
        content = _ai_history_line_content(row)
        if not content:
            continue
        role = "user" if row.get("direction") == "inbound" else "model"
        conversation_parts.append({"role": role, "parts": [{"text": content}]})

    # Dernier tour utilisateur = message courant (ex. transcription d’un vocal, pas le placeholder [voice])
    if conversation_parts and conversation_parts[-1]["role"] == "user":
        conversation_parts[-1] = {"role": "user", "parts": [{"text": latest_user_message}]}
    else:
        conversation_parts.append({"role": "user", "parts": [{"text": latest_user_message}]})

    logger.debug(
        "Gemini conversation payload for %s:\n%s",
        conversation_id,
        _format_conversation_preview(conversation_parts),
    )

    # Prompt système structuré
    instruction = (
        "Tu es un assistant SAV WhatsApp francophone pour une entreprise décrite dans un playbook structuré.\n"
        "\n"
        "Rôle et langue :\n"
        "- Tu réponds uniquement en français.\n"
        "- Tu joues le rôle d'un assistant service client / support pour l'entreprise décrite.\n"
        "\n"
        "Sources et vérité :\n"
        "- Tes réponses doivent s'appuyer exclusivement sur les informations présentes dans le PLAYBOOK ci-dessous.\n"
        "- Le PLAYBOOK est structuré en sections (par exemple : '## SYSTEM RULES', '## INFOS ENTREPRISE', "
        "'## OFFRES / SERVICES', '## CONDITIONS & PROCÉDURES', '## CAS SPÉCIAUX', '## LIENS UTILES', "
        "'## ESCALADE HUMAIN', '## RÈGLES SPÉCIALES BOT').\n"
        "- Tu appliques en priorité les règles indiquées dans '## SYSTEM RULES' et '## RÈGLES SPÉCIALES BOT'.\n"
        "- Tu n'inventes jamais de données, même si la question est proche de sujets couverts.\n"
        "\n"
        "Gestion des informations manquantes :\n"
        "- Si des informations sont manquantes, réponds de manière prudente, factuelle et concise.\n"
        "- Si les données semblent contradictoires, signale sobrement qu'une vérification humaine est utile.\n"
        "- N'invente jamais de prix, délais, disponibilités ou conditions absents des sources.\n"
        "\n"
        "Contenus non textuels :\n"
        "- Les messages vocaux sont transcrits automatiquement : le texte que tu reçois pour un vocal est "
        "la transcription ; réponds normalement à ce contenu.\n"
        "- Si l'utilisateur envoie une image ou une vidéo (sans texte utile), tu réponds : "
        "\"Je ne peux pas lire ce type de contenu, pouvez-vous me l'écrire ?\".\n"
        "\n"
        "Contraintes métier :\n"
        "- Tu ne promets jamais de tarifs, de délais, de disponibilités ou de réservations qui ne sont pas "
        "explicitement décrits dans le PLAYBOOK.\n"
        "- Tu n'encourages pas un appel direct ou un contact hors WhatsApp ; tu peux proposer : "
        "\"Vous pouvez passer directement au bureau\" lorsque c'est pertinent.\n"
        "- Si l'entreprise ne prend pas de réservations par WhatsApp, tu le rappelles clairement.\n"
        "\n"
        "Style de réponse :\n"
        "- Commence toujours par une phrase de réponse directe et claire.\n"
        "- Ensuite, ajoute seulement si c'est utile quelques puces avec les informations clés ou les étapes à suivre.\n"
        "- Tu restes professionnel, courtois et concis.\n"
        "- Tu n'utilises pas de mise en forme Markdown avec des doubles astérisques, ni de titres Markdown ; "
        "uniquement du texte simple et des listes avec des tirets si nécessaire.\n"
    )

    logger.info(f"🔍 [GEMINI DEBUG] Using model: {settings.GEMINI_MODEL}")

    qa_block = ""
    qa_matches: List[Dict[str, Any]] = []
    qa_queries_used: List[str] = []
    try:
        from app.services.qa_service import format_qa_context
        qa_queries_used = await _build_related_qa_queries(account_id, latest_user_message)
        qa_matches = await _search_similar_qa_multi_query(account_id, qa_queries_used, per_query_limit=5, final_limit=8)
        qa_block = format_qa_context(qa_matches)
    except Exception as _qa_exc:
        logger.debug("bot reply: QA RAG lookup skipped: %s", _qa_exc)

    system_text_full = f"{instruction}\n\nContexte entreprise (PLAYBOOK):\n{knowledge_text}"
    if qa_block:
        system_text_full = f"{system_text_full}{qa_block}"
    system_text_full = system_text_full.strip()

    generation_config: Dict[str, Any] = {
        "temperature": 0.4,
        "maxOutputTokens": 2048,
    }
    if str(settings.GEMINI_MODEL).startswith("gemini-2.5-"):
        generation_config["thinkingConfig"] = {
            "thinkingBudget": 512
        }
    
    payload_v1beta = {
        "system_instruction": {
            "role": "system",
            "parts": [
                {
                    "text": system_text_full
                }
            ],
        },
        "contents": conversation_parts,
        "generationConfig": generation_config,
    }
    
    system_message = {
        "role": "user",
        "parts": [{"text": system_text_full}],
    }
    payload_v1 = {
        "contents": [system_message] + conversation_parts,
        "generationConfig": generation_config,
    }

    # Try v1beta endpoint first
    endpoint_v1beta = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )
    
    # Fallback v1 endpoint
    endpoint_v1 = (
        f"https://generativelanguage.googleapis.com/v1/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )

    # Try v1beta first
    logger.info(f"🔍 [GEMINI DEBUG] Trying v1beta endpoint: {endpoint_v1beta}")
    try:
        data = await gemini_circuit_breaker.call_async(
            _call_gemini_api, endpoint_v1beta, payload_v1beta, conversation_id
        )
    except httpx.HTTPStatusError as exc:
        # If 404 (model not found in v1beta) or 400 (invalid payload), try v1
        if exc.response.status_code in (404, 400):
            logger.warning(
                f"🔍 [GEMINI DEBUG] v1beta failed (status={exc.response.status_code}), trying v1 endpoint"
            )
            logger.info(f"🔍 [GEMINI DEBUG] Trying v1 endpoint: {endpoint_v1}")
            try:
                data = await gemini_circuit_breaker.call_async(
                    _call_gemini_api, endpoint_v1, payload_v1, conversation_id
                )
            except Exception as exc2:
                logger.error(f"❌ Both v1beta and v1 failed. v1 error: {exc2}")
                return None
        else:
            # Other HTTP errors, don't retry
            logger.error(f"❌ Gemini API error: {exc}")
            return None
    except CircuitBreakerOpenError:
        logger.warning(
            "Gemini circuit breaker open, skipping generation for conversation %s",
            conversation_id,
        )
        return None
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.error("Gemini call failed for %s: %s", conversation_id, str(exc))
        return None
    except Exception as exc:  # sécurité
        logger.exception("Unexpected error while calling Gemini for %s: %s", conversation_id, exc)
        return None

    # Debug: log response structure
    logger.info(f"🔍 [GEMINI DEBUG] Response keys: {list(data.keys())}")
    if "promptFeedback" in data:
        logger.warning(f"🔍 [GEMINI DEBUG] Prompt feedback: {data['promptFeedback']}")
    if "candidates" not in data:
        logger.error(f"🔍 [GEMINI DEBUG] No 'candidates' key in response: {data}")
        return None

    candidates: List[Dict[str, Any]] = data.get("candidates") or []
    logger.info(f"🔍 [GEMINI DEBUG] Number of candidates: {len(candidates)}")
    
    for idx, candidate in enumerate(candidates):
        logger.info(f"🔍 [GEMINI DEBUG] Candidate {idx} keys: {list(candidate.keys())}")
        if "finishReason" in candidate:
            logger.info(f"🔍 [GEMINI DEBUG] Candidate {idx} finishReason: {candidate['finishReason']}")
        if "safetyRatings" in candidate:
            logger.info(f"🔍 [GEMINI DEBUG] Candidate {idx} safetyRatings: {candidate['safetyRatings']}")
        
        content = candidate.get("content", {})
        logger.info(f"🔍 [GEMINI DEBUG] Candidate {idx} content keys: {list(content.keys())}")
        parts = content.get("parts") or []
        logger.info(f"🔍 [GEMINI DEBUG] Candidate {idx} number of parts: {len(parts)}")
        
        for part_idx, part in enumerate(parts):
            logger.info(f"🔍 [GEMINI DEBUG] Candidate {idx} part {part_idx} keys: {list(part.keys())}")
            text = (part.get("text") or "").strip()
            if text:
                logger.info(
                    "✅ Gemini produced reply for conversation %s (chars=%d)",
                    conversation_id,
                    len(text),
                )
                confidence, reasons = _compute_bot_confidence(
                    knowledge_text=knowledge_text,
                    qa_matches=qa_matches,
                    user_message=latest_user_message,
                    generated_reply=text,
                )
                logger.info(
                    "🔍 [BOT CONFIDENCE] conversation=%s confidence=%.2f reasons=%s qa_queries=%s qa_count=%d",
                    conversation_id,
                    confidence,
                    reasons,
                    qa_queries_used,
                    len(qa_matches),
                )
                return {
                    "reply": text,
                    "confidence": confidence,
                    "confidence_reasons": reasons,
                    "qa_queries_used": qa_queries_used,
                }
            else:
                logger.warning(f"🔍 [GEMINI DEBUG] Candidate {idx} part {part_idx} has no text: {part}")

    logger.warning(f"❌ Gemini returned no usable candidates for conversation {conversation_id}. Full response: {json.dumps(data, indent=2)[:1000]}")
    return {
        "reply": None,
        "confidence": 0.0,
        "confidence_reasons": ["Gemini n'a pas renvoyé de texte exploitable."],
        "qa_queries_used": qa_queries_used,
    }


async def _build_related_qa_queries(account_id: str, user_message: str) -> List[str]:
    base = (user_message or "").strip()
    if not base:
        return []
    seen = set()
    queries: List[str] = []
    for item in [base, _normalize_short_query(base)]:
        t = (item or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            queries.append(t)
    gemini_queries = await _generate_related_queries_with_gemini(account_id, base)
    for q in gemini_queries:
        k = q.lower().strip()
        if k and k not in seen:
            seen.add(k)
            queries.append(q.strip())
    return queries[:6]


async def _generate_related_queries_with_gemini(account_id: str, user_message: str) -> List[str]:
    if not settings.GEMINI_API_KEY:
        return []
    model = settings.GEMINI_MODEL
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    instruction = (
        "Tu reçois une question client WhatsApp en français.\n"
        "Génère 4 reformulations de recherche Q&A, courtes, orientées base de connaissances.\n"
        "Contraintes:\n"
        "- une reformulation par ligne\n"
        "- pas de numérotation\n"
        "- pas de guillemets\n"
        "- français uniquement\n"
        "- garder les entités (marque, modèle, produit)\n"
        "Retourne uniquement les lignes de requêtes."
    )
    payload = {
        "system_instruction": {"role": "system", "parts": [{"text": instruction}]},
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 256,
        },
    }
    try:
        data = await gemini_circuit_breaker.call_async(
            _call_gemini_api, endpoint, payload, f"qa-expand-{account_id}"
        )
    except Exception as exc:
        logger.debug("QA query expansion skipped: %s", exc)
        return []
    out: List[str] = []
    for c in data.get("candidates") or []:
        for part in (c.get("content") or {}).get("parts") or []:
            txt = (part.get("text") or "").strip()
            if not txt:
                continue
            for line in txt.splitlines():
                q = line.strip(" -\t\r\n")
                if len(q) >= 3:
                    out.append(q)
    return out[:4]


def _normalize_short_query(text: str) -> str:
    t = " ".join((text or "").split())
    if not t:
        return ""
    t = re.sub(r"\bmodel\s*([0-9]+)\b", r"model \1", t, flags=re.IGNORECASE)
    t = t.replace("tesla 3", "tesla model 3")
    return t


async def _search_similar_qa_multi_query(
    account_id: str,
    queries: List[str],
    *,
    per_query_limit: int = 5,
    final_limit: int = 8,
) -> List[Dict[str, Any]]:
    from app.services.qa_service import search_similar_qa

    by_id: Dict[str, Dict[str, Any]] = {}
    for q in queries:
        if not q.strip():
            continue
        rows = await search_similar_qa(account_id, q, limit=per_query_limit)
        for row in rows:
            rid = str(row.get("id") or "")
            if not rid:
                continue
            existing = by_id.get(rid)
            sim_new = float(row.get("similarity") or 0.0)
            sim_old = float(existing.get("similarity") or 0.0) if existing else -1.0
            if not existing or sim_new > sim_old:
                by_id[rid] = row
    merged = list(by_id.values())
    merged.sort(key=lambda x: float(x.get("similarity") or 0.0), reverse=True)
    return merged[:final_limit]


def _extract_prices_eur(text: str) -> List[float]:
    vals: List[float] = []
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*€", text or "", flags=re.IGNORECASE):
        raw = m.group(1).replace(",", ".")
        try:
            vals.append(float(raw))
        except ValueError:
            continue
    return vals


def _compute_bot_confidence(
    *,
    knowledge_text: str,
    qa_matches: List[Dict[str, Any]],
    user_message: str,
    generated_reply: str,
) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    # Base quality
    kb_body = (knowledge_text or "").replace("```PLAYBOOK", "").replace("```", "").strip()
    has_kb = kb_body and kb_body.lower() != "aucune information fournie."
    qa_count = len(qa_matches or [])
    avg_sim = 0.0
    if qa_count:
        sims = [float(x.get("similarity") or 0.0) for x in qa_matches]
        avg_sim = sum(sims) / len(sims)
    confidence = 0.2
    if has_kb:
        confidence += 0.22
        reasons.append("Playbook présent.")
    else:
        reasons.append("Playbook vide.")
    if qa_count:
        confidence += min(0.4, qa_count * 0.09)
        confidence += min(0.18, max(0.0, avg_sim - 0.3))
        reasons.append(f"{qa_count} Q&A trouvés (similarité moyenne {avg_sim:.2f}).")
    else:
        reasons.append("Aucun Q&A pertinent trouvé.")

    # Data consistency: conflicts between playbook and Q&A prices.
    kb_prices = _extract_prices_eur(kb_body)
    qa_prices: List[float] = []
    for qa in qa_matches:
        qa_prices.extend(_extract_prices_eur((qa.get("answer") or "")))
    unique_kb = sorted({round(v, 2) for v in kb_prices})
    unique_qa = sorted({round(v, 2) for v in qa_prices})
    if unique_qa and len(unique_qa) > 1:
        confidence -= 0.18
        reasons.append(f"Q&A contradictoires sur les prix ({unique_qa}).")
    if unique_kb and unique_qa:
        if set(unique_kb) != set(unique_qa):
            confidence -= 0.22
            reasons.append(f"Incohérence prix Playbook {unique_kb} vs Q&A {unique_qa}.")
    # Penalize generic fallback-like answer.
    low_info_markers = (
        "je me renseigne auprès d'un collègue",
        "je reviens vers vous",
    )
    if any(m in (generated_reply or "").lower() for m in low_info_markers):
        confidence -= 0.2
        reasons.append("Réponse générée peu informative.")
    # Mention coverage: if user asks price and answer has no euro amount, lower confidence.
    asks_price = any(k in (user_message or "").lower() for k in ("prix", "coût", "combien", "tarif"))
    if asks_price and not _extract_prices_eur(generated_reply or ""):
        confidence -= 0.18
        reasons.append("Question tarifaire sans prix explicite dans la réponse.")
    confidence = max(0.0, min(1.0, confidence))
    if confidence >= _BOT_CONFIDENCE_MIN_THRESHOLD:
        reasons.append("Confiance suffisante pour envoi automatique.")
    else:
        reasons.append("Confiance insuffisante, escalade humain recommandée.")
    return confidence, reasons


async def generate_flow_gemini_keyword(
    conversation_id: str,
    _account_id: str,
    user_text: str,
    system_prompt: str,
    hint: Optional[str] = None,
    *,
    recent_user_context: Optional[str] = None,
) -> Optional[str]:
    """
    Appel Gemini « routeur » : une seule réponse courte (mot-clé), pour les nœuds Gemini du playground.
    """
    if not settings.GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY absent, skip flow gemini for %s", conversation_id)
        return None
    user_text = (user_text or "").strip()
    if not user_text:
        return None
    base = (system_prompt or "").strip()
    if "[INSERER LE TEXTE DU USER ICI]" in base:
        instruction = base.replace("[INSERER LE TEXTE DU USER ICI]", user_text)
    else:
        instruction = f"{base}\n\nTexte de l'utilisateur :\n{user_text}"
    if hint:
        instruction = f"{instruction}\n\nConsigne complémentaire :\n{hint.strip()}"
    rc = (recent_user_context or "").strip()
    rc_max = max(1200, int(getattr(settings, "GEMINI_FLOW_RECENT_CONTEXT_CHARS", 32000) or 32000))
    if rc:
        instruction = (
            f"{instruction}\n\n"
            "Messages utilisateur récents sur ce fil (contexte, ne pas citer mot pour mot) :\n"
            f"{rc[:rc_max]}"
        )

    generation_config: Dict[str, Any] = {
        "temperature": 0.1,
        "maxOutputTokens": 32,
    }
    if str(settings.GEMINI_MODEL).startswith("gemini-2.5-"):
        generation_config["thinkingConfig"] = {"thinkingBudget": 512}

    conversation_parts = [{"role": "user", "parts": [{"text": "Analyse et réponds selon les instructions."}]}]

    payload_v1beta = {
        "system_instruction": {
            "role": "system",
            "parts": [{"text": instruction}],
        },
        "contents": conversation_parts,
        "generationConfig": generation_config,
    }
    system_message = {
        "role": "user",
        "parts": [{"text": instruction}],
    }
    payload_v1 = {
        "contents": [system_message] + conversation_parts,
        "generationConfig": generation_config,
    }

    endpoint_v1beta = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )
    endpoint_v1 = (
        f"https://generativelanguage.googleapis.com/v1/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )

    try:
        try:
            data = await gemini_circuit_breaker.call_async(
                _call_gemini_api, endpoint_v1beta, payload_v1beta, conversation_id
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (404, 400):
                data = await gemini_circuit_breaker.call_async(
                    _call_gemini_api, endpoint_v1, payload_v1, conversation_id
                )
            else:
                raise
    except BaseException as exc:
        logger.error("Flow Gemini keyword failed for %s: %s (%s)", conversation_id, exc, type(exc).__name__)
        return None

    candidates: List[Dict[str, Any]] = data.get("candidates") or []
    for candidate in candidates:
        parts = (candidate.get("content") or {}).get("parts") or []
        for part in parts:
            text = (part.get("text") or "").strip()
            if text:
                # Toute la réponse (pas seul le 1er mot) : le routeur peut renvoyer une phrase ;
                # _gemini_pick fait une correspondance par sous-chaîne sur les intentions.
                return text
    return None


async def generate_flow_gemini_text_reply(
    conversation_id: str,
    account_id: str,
    user_text: str,
    system_prompt: str,
    hint: Optional[str] = None,
    node_knowledge: Optional[str] = None,
) -> Optional[str]:
    """
    Nœud Gemini « sans intentions » mais avec prompt système : réponse conversationnelle
    complète (pour {{varKey}} puis sendText / interactive), pas le playbook SAV.
    Utilise l'historique de la conversation + la base de connaissances du bot_profile
    + une base de connaissances optionnelle spécifique au nœud.
    """
    if not settings.GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY absent, skip flow gemini text for %s", conversation_id)
        return None
    user_text = (user_text or "").strip()
    base = (system_prompt or "").strip()
    if not base:
        return None

    knowledge_block = ""
    try:
        profile = await get_bot_profile(account_id)
        kb_parts: List[str] = []
        if profile.get("business_name"):
            kb_parts.append(f"Entreprise: {profile['business_name']}")
        if profile.get("description"):
            kb_parts.append(f"Description: {profile['description']}")
        if profile.get("address"):
            kb_parts.append(f"Adresse: {profile['address']}")
        if profile.get("hours"):
            kb_parts.append(f"Horaires: {profile['hours']}")
        if profile.get("knowledge_base"):
            kb_parts.append(profile["knowledge_base"])
        for field in profile.get("custom_fields", []):
            label = field.get("label")
            value = field.get("value")
            if label and value:
                kb_parts.append(f"{label}: {value}")
        if node_knowledge and node_knowledge.strip():
            kb_parts.append(node_knowledge.strip())
        if kb_parts:
            knowledge_block = "\n\nBASE DE CONNAISSANCES (utilise ces infos pour répondre) :\n" + "\n".join(kb_parts)
    except Exception as kb_exc:
        logger.warning("Flow Gemini: could not load knowledge base: %s", kb_exc)

    if "[INSERER LE TEXTE DU USER ICI]" in base:
        instruction = base.replace("[INSERER LE TEXTE DU USER ICI]", user_text or "(aucun message)")
    else:
        instruction = f"{base}\n\nDernier message de l'utilisateur :\n{user_text or '(aucun message)'}"
    if hint:
        instruction = f"{instruction}\n\nConsigne complémentaire :\n{hint.strip()}"
    if knowledge_block:
        instruction = f"{instruction}{knowledge_block}"

    try:
        from app.services.qa_service import search_similar_qa, format_qa_context
        qa_matches = await search_similar_qa(account_id, user_text or "", limit=5)
        qa_block = format_qa_context(qa_matches)
        if qa_block:
            instruction = f"{instruction}{qa_block}"
    except Exception as _qa_exc:
        logger.debug("flow gemini: QA RAG lookup skipped: %s", _qa_exc)

    instruction = (
        f"{instruction}\n\n"
        "Réponds en français. Réponse directe au client (pas de préambule méta, pas de guillemets autour du message entier)."
    )

    generation_config: Dict[str, Any] = {
        "temperature": 0.55,
        "maxOutputTokens": 1024,
    }
    if str(settings.GEMINI_MODEL).startswith("gemini-2.5-"):
        generation_config["thinkingConfig"] = {"thinkingBudget": 512}

    conversation_parts: List[Dict[str, Any]] = []
    try:
        history_rows = await fetch_message_history_rows_for_ai(conversation_id)
        for row in history_rows:
            content = _ai_history_line_content(row)
            if not content:
                continue
            role = "user" if row.get("direction") == "inbound" else "model"
            conversation_parts.append({"role": role, "parts": [{"text": content}]})
    except Exception as hist_exc:
        logger.warning("Flow Gemini text: could not load history: %s", hist_exc)

    ut = user_text or "Rédige la réponse demandée."
    if conversation_parts and conversation_parts[-1]["role"] == "user":
        conversation_parts[-1] = {"role": "user", "parts": [{"text": ut}]}
    else:
        conversation_parts.append({"role": "user", "parts": [{"text": ut}]})

    payload_v1beta = {
        "system_instruction": {
            "role": "system",
            "parts": [{"text": instruction}],
        },
        "contents": conversation_parts,
        "generationConfig": generation_config,
    }
    system_message = {
        "role": "user",
        "parts": [{"text": instruction}],
    }
    payload_v1 = {
        "contents": [system_message] + conversation_parts,
        "generationConfig": generation_config,
    }

    endpoint_v1beta = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )
    endpoint_v1 = (
        f"https://generativelanguage.googleapis.com/v1/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )

    try:
        try:
            data = await gemini_circuit_breaker.call_async(
                _call_gemini_api, endpoint_v1beta, payload_v1beta, conversation_id
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (404, 400):
                data = await gemini_circuit_breaker.call_async(
                    _call_gemini_api, endpoint_v1, payload_v1, conversation_id
                )
            else:
                raise
    except BaseException as exc:
        logger.error("Flow Gemini text reply failed for %s: %s (%s)", conversation_id, exc, type(exc).__name__)
        return None

    candidates: List[Dict[str, Any]] = data.get("candidates") or []
    for candidate in candidates:
        parts = (candidate.get("content") or {}).get("parts") or []
        for part in parts:
            if part.get("thought"):
                continue
            text = (part.get("text") or "").strip()
            if text:
                return text
    return None


def _build_knowledge_text(profile: Dict[str, Any], contact_name: Optional[str]) -> str:
    """
    Construit le PLAYBOOK à partir du template + des champs libres.

    Le texte est encapsulé dans un bloc délimité:
    ```PLAYBOOK
    ...
    ```
    """
    lines: List[str] = []

    template_cfg = profile.get("template_config") or {}
    mode = str(template_cfg.get("playbook_input_mode") or "structured").strip().lower()
    pitch = str(template_cfg.get("playbook_pitch") or "").strip()
    use_pitch_body = mode == "pitch" and bool(pitch)
    use_pitch_mode = mode == "pitch"

    if use_pitch_body:
        lines.append(pitch)
    else:
        template_text = _render_template_sections(template_cfg)
        if template_text:
            lines.append(template_text)

    if profile.get("business_name"):
        lines.append(f"Nom: {profile['business_name']}")
    if profile.get("description"):
        lines.append(f"Description: {profile['description']}")
    if profile.get("address"):
        lines.append(f"Adresse: {profile['address']}")
    if profile.get("hours"):
        lines.append(f"Horaires: {profile['hours']}")

    if not use_pitch_mode:
        if profile.get("knowledge_base"):
            lines.append(f"Informations additionnelles: {profile['knowledge_base']}")

        for field in profile.get("custom_fields", []):
            label = field.get("label")
            value = field.get("value")
            if label and value:
                lines.append(f"{label}: {value}")

    if contact_name:
        lines.append(f"Prenom/nom du contact: {contact_name}")

    core = "\n".join(lines).strip() or "Aucune information fournie."
    return f"```PLAYBOOK\n{core}\n```"


def _trim_for_log(text: str, limit: int = 500) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... (truncated)"


def _format_conversation_preview(parts: List[Dict[str, Any]], limit: int = 24) -> str:
    preview_lines = []
    for entry in parts[-limit:]:
        role = entry.get("role")
        text = ""
        for part in entry.get("parts", []):
            fragment = (part.get("text") or "").strip()
            if fragment:
                text = fragment
                break
        preview_lines.append(f"{role}: {_trim_for_log(text, 250)}")
    return "\n".join(preview_lines)


def _sanitize_template_config(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}

    def _clean_str(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    sanitized: Dict[str, Any] = {}

    sanitized["system_rules"] = {
        "language": _clean_str(data.get("system_rules", {}).get("language")),
        "tone": _clean_str(data.get("system_rules", {}).get("tone")),
        "role": _clean_str(data.get("system_rules", {}).get("role")),
        "mission": _clean_str(data.get("system_rules", {}).get("mission")),
        "style": _clean_str(data.get("system_rules", {}).get("style")),
        "priority": _clean_str(data.get("system_rules", {}).get("priority")),
        "response_policy": _clean_str(data.get("system_rules", {}).get("response_policy")),
        "security": _clean_str(data.get("system_rules", {}).get("security")),
    }

    sanitized["company"] = {
        "name": _clean_str(data.get("company", {}).get("name")),
        "address": _clean_str(data.get("company", {}).get("address")),
        "hours_block": _clean_str(data.get("company", {}).get("hours_block")),
        "zone": _clean_str(data.get("company", {}).get("zone")),
        "rendezvous": _clean_str(data.get("company", {}).get("rendezvous")),
        "activity": _clean_str(data.get("company", {}).get("activity")),
    }

    def _clean_items(items: Any, fields: List[str]) -> List[Dict[str, str]]:
        cleaned: List[Dict[str, str]] = []
        if not isinstance(items, list):
            return cleaned
        for raw in items:
            if not isinstance(raw, dict):
                continue
            entry = {field: _clean_str(raw.get(field)) for field in fields}
            if any(entry.values()):
                cleaned.append(entry)
        return cleaned

    sanitized["offers"] = _clean_items(data.get("offers"), ["category", "content"])
    sanitized["procedures"] = _clean_items(data.get("procedures"), ["name", "steps"])
    sanitized["faq"] = _clean_items(data.get("faq"), ["question", "answer"])
    sanitized["special_cases"] = _clean_items(
        data.get("special_cases"),
        ["case", "response"],
    )

    sanitized["conditions"] = {
        "zone": _clean_str(data.get("conditions", {}).get("zone")),
        "payment": _clean_str(data.get("conditions", {}).get("payment")),
        "engagement": _clean_str(data.get("conditions", {}).get("engagement")),
        "restrictions": _clean_str(data.get("conditions", {}).get("restrictions")),
        "documents": _clean_str(data.get("conditions", {}).get("documents")),
    }

    sanitized["links"] = {
        "site": _clean_str(data.get("links", {}).get("site")),
        "products": _clean_str(data.get("links", {}).get("products")),
        "form": _clean_str(data.get("links", {}).get("form")),
        "other": _clean_str(data.get("links", {}).get("other")),
    }

    sanitized["escalation"] = {
        "procedure": _clean_str(data.get("escalation", {}).get("procedure")),
        "contact": _clean_str(data.get("escalation", {}).get("contact")),
        "hours": _clean_str(data.get("escalation", {}).get("hours")),
    }

    sanitized["special_rules"] = _clean_str(data.get("special_rules"))

    pitch_raw = _clean_str(data.get("playbook_pitch"))
    if len(pitch_raw) > 100_000:
        pitch_raw = pitch_raw[:100_000]
    sanitized["playbook_pitch"] = pitch_raw
    mode_raw = str(data.get("playbook_input_mode") or "structured").strip().lower()
    sanitized["playbook_input_mode"] = "pitch" if mode_raw == "pitch" else "structured"

    return sanitized


def _render_template_sections(template: Dict[str, Any]) -> str:
    if not template:
        return ""

    lines: List[str] = []

    sys = template.get("system_rules") or {}
    if any(sys.values()):
        lines.append("## SYSTEM RULES")
        if sys.get("role"):
            lines.append(f"Rôle: {sys['role']}")
        if sys.get("mission"):
            lines.append(f"Mission: {sys['mission']}")
        if sys.get("language"):
            lines.append(f"Langue par défaut: {sys['language']}")
        if sys.get("tone"):
            lines.append(f"Ton attendu: {sys['tone']}")
        if sys.get("style"):
            lines.append(f"Style de réponse: {sys['style']}")
        if sys.get("priority"):
            lines.append(f"Priorité des sources: {sys['priority']}")
        if sys.get("response_policy"):
            lines.append(f"Politique de réponse: {sys['response_policy']}")
        if sys.get("security"):
            lines.append(f"Règles de sécurité: {sys['security']}")

    company = template.get("company") or {}
    if any(company.values()):
        lines.append("\n## INFOS ENTREPRISE")
        if company.get("name"):
            lines.append(f"Nom entreprise: {company['name']}")
        if company.get("address"):
            lines.append(f"Adresse: {company['address']}")
        if company.get("hours_block"):
            lines.append(f"Horaires détaillés: {company['hours_block']}")
        if company.get("zone"):
            lines.append(f"Zone couverte: {company['zone']}")
        if company.get("rendezvous"):
            lines.append(f"Rendez-vous: {company['rendezvous']}")
        if company.get("activity"):
            lines.append(f"Activité principale: {company['activity']}")

    offers = template.get("offers") or []
    if offers:
        lines.append("\n## OFFRES / SERVICES")
        for offer in offers:
            if not any(offer.values()):
                continue
            if offer.get("category"):
                lines.append(f"### Catégorie: {offer['category']}")
            if offer.get("content"):
                lines.append(offer["content"])

    conditions = template.get("conditions") or {}
    if any(conditions.values()):
        lines.append("\n## CONDITIONS & PROCÉDURES")
        if conditions.get("zone"):
            lines.append(f"Zone: {conditions['zone']}")
        if conditions.get("payment"):
            lines.append(f"Paiement / dépôt: {conditions['payment']}")
        if conditions.get("engagement"):
            lines.append(f"Engagement: {conditions['engagement']}")
        if conditions.get("restrictions"):
            lines.append(f"Restrictions: {conditions['restrictions']}")
        if conditions.get("documents"):
            lines.append("Documents requis:\n" + conditions["documents"])

    procedures = template.get("procedures") or []
    if procedures:
        lines.append("\n## PROCÉDURES SIMPLIFIÉES")
        for proc in procedures:
            if not any(proc.values()):
                continue
            title = proc.get("name") or "Procédure"
            lines.append(f"### {title}")
            if proc.get("steps"):
                lines.append(proc["steps"])

    faq = template.get("faq") or []
    if faq:
        lines.append("\n## FAQ")
        for item in faq:
            if not any(item.values()):
                continue
            if item.get("question"):
                lines.append(f"Q: {item['question']}")
            if item.get("answer"):
                lines.append(f"R: {item['answer']}")

    special_cases = template.get("special_cases") or []
    if special_cases:
        lines.append("\n## CAS SPÉCIAUX")
        for case in special_cases:
            if not any(case.values()):
                continue
            if case.get("case"):
                lines.append(f"Si {case['case']}:")
            if case.get("response"):
                lines.append(case["response"])

    links = template.get("links") or {}
    if any(links.values()):
        lines.append("\n## LIENS UTILES")
        if links.get("site"):
            lines.append(f"Site: {links['site']}")
        if links.get("products"):
            lines.append(f"Produits: {links['products']}")
        if links.get("form"):
            lines.append(f"Formulaire: {links['form']}")
        if links.get("other"):
            lines.append(f"Autre: {links['other']}")

    escalation = template.get("escalation") or {}
    if any(escalation.values()):
        lines.append("\n## ESCALADE HUMAIN")
        if escalation.get("procedure"):
            lines.append(f"Procédure: {escalation['procedure']}")
        if escalation.get("contact"):
            lines.append(f"Contact: {escalation['contact']}")
        if escalation.get("hours"):
            lines.append(f"Horaires du contact: {escalation['hours']}")

    if template.get("special_rules"):
        lines.append("\n## RÈGLES SPÉCIALES BOT")
        lines.append(template["special_rules"])

    return "\n".join(filter(None, lines)).strip()


_PLAYGROUND_ASSIST_NODE_TYPES = frozenset(
    {
        "start",
        "sendText",
        "sendTemplate",
        "gemini",
        "interactiveNode",
        "routerNode",
        "handoffNode",
        "delayNode",
        "waitUntilNode",
        "timeWindowNode",
        "logicNode",
    }
)

# Tours user+assistant envoyés à Gemini (le graphe actuel occupe déjà beaucoup de contexte).
_PLAYGROUND_ASSIST_MAX_MESSAGES = 96


def _playground_assist_max_output_tokens(is_ask: bool) -> int:
    """Plafond sortie : l’API refuse ou tronque selon le modèle ; les graphes agents ont besoin de marge."""
    if is_ask:
        return 8192
    m = str(settings.GEMINI_MODEL).lower()
    if "gemini-2.5" in m or "gemini-2.0" in m:
        return 65536
    if "gemini-1.5" in m:
        return 8192
    return 32768


def _playground_assist_collect_model_text(data: dict) -> str:
    """Concatène le texte utile ; ignore les parts marquées thought (Gemini 2.5+)."""
    raw = ""
    for candidate in data.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            if part.get("thought"):
                continue
            raw += part.get("text") or ""
    return raw


def _playground_assist_try_reply_only_json(t: str) -> Optional[str]:
    """
    Si le JSON racine est tronqué (souvent dans « graph ») mais que « reply » est complet,
    extrait uniquement la chaîne reply via JSONDecoder.
    """
    s = t.strip()
    if not s.startswith("{"):
        return None
    key = '"reply"'
    i = s.find(key)
    if i < 0:
        return None
    j = i + len(key)
    while j < len(s) and s[j] in " \t\n\r":
        j += 1
    if j >= len(s) or s[j] != ":":
        return None
    j += 1
    while j < len(s) and s[j] in " \t\n\r":
        j += 1
    if j >= len(s):
        return None
    dec = json.JSONDecoder()
    try:
        val, _end = dec.raw_decode(s, j)
    except json.JSONDecodeError:
        return None
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    return None


def _playground_assist_parse_model_payload(raw_text: str) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Retourne (payload, partial) où partial=True si seul « reply » a pu être récupéré (JSON tronqué).
    """
    parsed = _parse_playground_assistant_json(raw_text)
    if isinstance(parsed, dict) and "reply" in parsed:
        return parsed, False
    t = (raw_text or "").strip()
    if t.startswith("{"):
        try:
            j = json.loads(t)
            if isinstance(j, dict) and "reply" in j:
                return j, False
        except json.JSONDecodeError:
            pass
    reply_only = _playground_assist_try_reply_only_json(t)
    if reply_only is not None:
        return {"reply": reply_only, "graph": None}, True
    return None, False


def _playground_assist_finish_reason(data: dict) -> Optional[str]:
    cands = data.get("candidates") or []
    if not cands or not isinstance(cands[0], dict):
        return None
    c0 = cands[0]
    return c0.get("finishReason") or c0.get("finish_reason")


def _playground_assist_fallback_reply(
    raw_text: str, *, finish_reason: Optional[str] = None
) -> str:
    fr = (finish_reason or "").strip().upper()
    if "MAX_TOKEN" in fr:
        return (
            "La génération a été coupée par la limite de tokens (réponse + graphe trop volumineux). "
            "Demande une modification très ciblée (un seul nœud, une seule branche, ou une variable), "
            "ou passe en mode Ask pour une explication sans graphe."
        )
    t = (raw_text or "").strip()
    if not t:
        return "Réponse vide du modèle."
    logger.warning(
        "Playground assist: parse JSON échoué, finishReason=%s, len=%s, extrait=%r",
        finish_reason,
        len(t),
        t[:500] + ("…" if len(t) > 500 else ""),
    )
    if len(t) > 3000:
        return (
            "La réponse de l’IA n’est pas un JSON complet (souvent troncature au milieu du graphe). "
            "Réessaie avec une demande plus courte ou une modification locale, ou utilise le mode Ask."
        )
    return (
        "Impossible d’interpréter la réponse de l’IA. Réessaie en une phrase, ou en mode Ask. "
        f"(Aperçu : {t[:240]}{'…' if len(t) > 240 else ''})"
    )


def _playground_assist_clean_reply_string(reply_str: str) -> str:
    """Évite d’afficher tout le JSON dans le champ « reply » si le modèle s’emballe."""
    s = (reply_str or "").strip()
    if not s:
        return s
    if len(s) > 6000:
        return s[:5999] + "…"
    if s.startswith("{") and '"reply"' in s:
        try:
            j = json.loads(s)
            if isinstance(j, dict) and isinstance(j.get("reply"), str):
                inner = j["reply"].strip()
                if inner:
                    return inner
        except json.JSONDecodeError:
            pass
    return s


def _parse_playground_assistant_json(text: str) -> Optional[Dict[str, Any]]:
    if not text or not str(text).strip():
        return None
    t = str(text).strip()
    if "```" in t:
        for chunk in t.split("```"):
            c = chunk.strip()
            if c.lower().startswith("json"):
                c = c[4:].strip()
            if c.startswith("{"):
                try:
                    return json.loads(c)
                except json.JSONDecodeError:
                    continue
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    i0 = t.find("{")
    i1 = t.rfind("}")
    if i0 >= 0 and i1 > i0:
        try:
            return json.loads(t[i0 : i1 + 1])
        except json.JSONDecodeError:
            return None
    return None


def _validate_playground_assist_graph(g: Dict[str, Any]) -> bool:
    nodes = g.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return False
    if not any(isinstance(n, dict) and n.get("type") == "start" for n in nodes):
        return False
    seen: set = set()
    for n in nodes:
        if not isinstance(n, dict):
            return False
        nid = n.get("id")
        ntype = n.get("type")
        if not nid or not isinstance(nid, str):
            return False
        if nid in seen:
            return False
        seen.add(nid)
        if ntype not in _PLAYGROUND_ASSIST_NODE_TYPES:
            return False
        if ntype == "interactiveNode":
            idata = n.get("data") or {}
            if not isinstance(idata, dict):
                return False
            if _interactive_node_illegal_meta_template_fields(idata):
                return False
        pos = n.get("position")
        if not isinstance(pos, dict):
            return False
        if not isinstance(pos.get("x"), (int, float)) or not isinstance(pos.get("y"), (int, float)):
            return False
    edges = g.get("edges")
    if edges is None:
        edges = []
    if not isinstance(edges, list):
        return False
    for e in edges:
        if not isinstance(e, dict):
            return False
        s, t = e.get("source"), e.get("target")
        if not s or not t or s not in seen or t not in seen:
            return False
    return True


def _interactive_node_illegal_meta_template_fields(data: Dict[str, Any]) -> bool:
    """
    True si interactiveNode abuse des champs réservés aux templates Meta.
    Le moteur n'envoie PAS de template depuis interactiveNode : il faut sendTemplate.
    """
    if not isinstance(data, dict):
        return False
    if data.get("templateName") or data.get("templateLanguage") or data.get("selectedTemplateKey"):
        return True
    uk = str(data.get("uiKind") or "").strip().lower()
    if uk in ("template", "sendtemplate", "meta_template"):
        return True
    return False


def _coerce_send_template_node_data(data: Dict[str, Any]) -> None:
    """Normalise timeout et quick replies pour sendTemplate (souvent mal nommés par le LLM)."""
    if not isinstance(data, dict):
        return
    ts = data.pop("timeoutSeconds", None)
    if ts is not None and ts != "":
        try:
            sec = float(ts)
            if sec > 0 and not str(data.get("timeoutDuration") or "").strip():
                data["timeoutDuration"] = str(int(sec))
                data["timeoutUnit"] = "s"
        except (TypeError, ValueError):
            pass
    qr = data.get("quickReplyButtons")
    if not isinstance(qr, list) or not qr:
        ch = data.get("choices")
        if isinstance(ch, list) and ch:
            out: List[Dict[str, Any]] = []
            for i, c in enumerate(ch):
                if not isinstance(c, dict):
                    continue
                title = _first_nonempty_str(
                    c.get("title"),
                    c.get("text"),
                    c.get("label"),
                )
                if title:
                    out.append(
                        {
                            "type": "QUICK_REPLY",
                            "text": title,
                            "id": str(c.get("id") or f"qr_{i}"),
                        }
                    )
            if out:
                data["quickReplyButtons"] = out


def _coerce_send_text_node_data(data: Dict[str, Any]) -> None:
    """Le LLM met souvent le texte dans message/text/content au lieu de body (requis UI + moteur)."""
    body = data.get("body")
    if isinstance(body, str) and body.strip():
        return
    for key in ("message", "text", "content", "value"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            data["body"] = v.strip()
            return


def _first_nonempty_str(*vals: Any) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _coerce_router_route_item(item: Any) -> Optional[Dict[str, str]]:
    if isinstance(item, str) and item.strip():
        s = item.strip()
        return {"label": s, "match": s}
    if not isinstance(item, dict):
        return None
    match = _first_nonempty_str(
        item.get("match"),
        item.get("keyword"),
        item.get("value"),
        item.get("text"),
        item.get("pattern"),
        item.get("reply"),
        item.get("id"),
        item.get("message"),
    )
    label = _first_nonempty_str(
        item.get("label"),
        item.get("title"),
        item.get("name"),
    )
    if not match:
        match = label
    if not match:
        return None
    if not label:
        label = match
    return {"label": label, "match": match}


def _coerce_routes_list(raw: List[Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for item in raw:
        row = _coerce_router_route_item(item)
        if row:
            out.append(row)
    return out


def _coerce_router_node_data(data: Dict[str, Any]) -> None:
    """Normalise branches/options/conditions vers data.routes [{label, match}]."""
    for key in ("routes", "branches", "options", "conditions"):
        raw = data.get(key)
        if not isinstance(raw, list) or not raw:
            continue
        fixed = _coerce_routes_list(raw)
        if fixed:
            data["routes"] = fixed
            return


def _coerce_interactive_node_data(data: Dict[str, Any]) -> None:
    """Normalise les champs interactiveNode que Gemini invente souvent."""
    if not data.get("body"):
        for key in ("bodyText", "text", "message", "content"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                data["body"] = v.strip()
                break
    if not data.get("uiKind"):
        it = data.get("interactiveType") or data.get("type_interactive") or ""
        data["uiKind"] = "list" if "list" in str(it).lower() else "buttons"
    if not isinstance(data.get("choices"), list) or not data["choices"]:
        for key in ("buttons", "options", "sections", "items"):
            raw = data.get(key)
            if isinstance(raw, list) and raw:
                choices = []
                for idx, item in enumerate(raw):
                    if isinstance(item, str) and item.strip():
                        choices.append({"id": f"btn_{idx}", "title": item.strip()})
                    elif isinstance(item, dict):
                        title = ""
                        for tk in ("title", "text", "label", "name", "value"):
                            v = item.get(tk)
                            if isinstance(v, str) and v.strip():
                                title = v.strip()
                                break
                        if title:
                            choices.append({"id": item.get("id") or f"btn_{idx}", "title": title})
                if choices:
                    data["choices"] = choices
                    break


_TEMPLATE_STATUS_ALLOWED = frozenset(
    {"unknown", "missing", "pending_review", "approved", "rejected"}
)


_PENDING_USER_CONFIRM_SKILLS = frozenset({"create_template", "meta_block_contact"})


def _partition_playground_tool_calls(
    tool_calls: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Sépare les appels create_template / meta_block_contact (confirmation utilisateur requise) des autres skills."""
    safe: List[Dict[str, Any]] = []
    pending_create: List[Dict[str, Any]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        name = (tc.get("skill") or tc.get("name") or "").strip()
        if name in _PENDING_USER_CONFIRM_SKILLS:
            pending_create.append(tc)
        else:
            safe.append(tc)
    return safe, pending_create


def _coerce_playground_assist_graph_data(g: Dict[str, Any]) -> None:
    """Post-traitement des graphes proposés par l’assistant (noms de champs fréquemment erronés)."""
    nodes = g.get("nodes")
    if not isinstance(nodes, list):
        return
    for n in nodes:
        if not isinstance(n, dict):
            continue
        ntype = n.get("type")
        data = n.get("data")
        if not isinstance(data, dict):
            data = {}
            n["data"] = data
        if ntype == "sendText":
            _coerce_send_text_node_data(data)
        elif ntype == "sendTemplate":
            _coerce_send_template_node_data(data)
            ts = data.get("templateStatus")
            if ts not in _TEMPLATE_STATUS_ALLOWED:
                data["templateStatus"] = "unknown"
        elif ntype == "routerNode":
            _coerce_router_node_data(data)
        elif ntype == "interactiveNode":
            _coerce_interactive_node_data(data)
        elif ntype == "gemini":
            intents = data.get("intents")
            if isinstance(intents, list):
                for intent in intents:
                    if not isinstance(intent, dict):
                        continue
                    if not intent.get("keyword"):
                        kw = intent.get("match") or intent.get("value") or intent.get("text") or ""
                        if isinstance(kw, str) and kw.strip():
                            intent["keyword"] = kw.strip()
                    if not intent.get("label"):
                        intent["label"] = intent.get("keyword") or intent.get("match") or ""

    node_map = {n["id"]: n for n in nodes if isinstance(n, dict) and n.get("id")}
    edges = g.get("edges")
    if isinstance(edges, list):
        for e in edges:
            if not isinstance(e, dict):
                continue
            src_id = e.get("source")
            src_node = node_map.get(src_id) if src_id else None
            if not src_node:
                continue
            sh = e.get("sourceHandle")
            stype = src_node.get("type")
            if stype == "interactiveNode" and sh and sh not in (None, "timeout"):
                e["sourceHandle"] = None
            elif stype == "sendTemplate" and sh and sh not in (None, "timeout"):
                e["sourceHandle"] = None
            elif stype in ("sendText", "delayNode", "waitUntilNode", "start", "handoffNode"):
                if sh:
                    e["sourceHandle"] = None


async def generate_playground_assist_reply(
    *,
    account_id: str,
    flow_id: Optional[str],
    flow_name: str,
    graph: Dict[str, Any],
    messages: List[Dict[str, str]],
    mode: str = "agent",
    approve_tool_calls: Optional[List[Dict[str, Any]]] = None,
    execution_phase: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Assistant éditeur Playground avec skills (tool_calls) et todo-list.
    Boucle multi-tour : Gemini peut demander des skills, le backend les exécute et relance.
    Les appels create_template sont différés jusqu'à confirmation (approve_tool_calls).
    """
    if not settings.GEMINI_API_KEY:
        return {
            "reply": "GEMINI_API_KEY n’est pas configurée côté serveur.",
            "graph": None,
            "todo": None,
            "skills_used": None,
            "pending_tool_calls": None,
        }

    from app.services.playground_flow_service import _normalize_graph
    from app.services.playground_skills import get_skills_prompt_section, execute_tool_calls
    from app.services.account_service import get_account_by_id

    norm = _normalize_graph(graph)
    graph_json = json.dumps(norm, ensure_ascii=False)

    account = await get_account_by_id(account_id) or {}
    pre_skills_used: list = []

    messages_work: List[Dict[str, Any]] = [m for m in messages if isinstance(m, dict)]
    if approve_tool_calls:
        if not isinstance(approve_tool_calls, list) or not approve_tool_calls:
            return {
                "reply": "Aucun outil à exécuter (approve_tool_calls vide).",
                "graph": None,
                "todo": None,
                "skills_used": None,
                "pending_tool_calls": None,
            }
        for tc in approve_tool_calls[:5]:
            if not isinstance(tc, dict):
                continue
            sn = (tc.get("skill") or tc.get("name") or "").strip()
            if sn != "create_template":
                return {
                    "reply": (
                        "Seule la création de template Meta (create_template) peut être confirmée "
                        "via ce flux. Utilise l’assistant normalement pour les autres actions."
                    ),
                    "graph": None,
                    "todo": None,
                    "skills_used": None,
                    "pending_tool_calls": None,
                }
        approve_results = await execute_tool_calls(approve_tool_calls[:5], account)
        pre_skills_used = [r["skill"] for r in approve_results if r.get("skill")]
        messages_work.append(
            {
                "role": "user",
                "content": (
                    "L'utilisateur a confirmé dans l'interface la création du ou des message templates "
                    "sur Meta. Résultat d'exécution (ne pas re-demander confirmation pour ces créations) :\n"
                    + json.dumps(approve_results, ensure_ascii=False, default=str)
                ),
            }
        )

    hist: List[Dict[str, Any]] = []
    for m in messages_work[-_PLAYGROUND_ASSIST_MAX_MESSAGES:]:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "user").strip().lower()
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant":
            hist.append({"role": "model", "parts": [{"text": content}]})
        else:
            hist.append({"role": "user", "parts": [{"text": content}]})

    if not hist:
        return {
            "reply": "Envoie un message pour commencer.",
            "graph": None,
            "todo": None,
            "skills_used": None,
            "pending_tool_calls": None,
        }

    fn = (flow_name or "").strip() or "(sans nom)"
    fid = flow_id or "-"

    assist_mode = (mode or "agent").strip().lower()
    if assist_mode not in ("ask", "agent"):
        assist_mode = "agent"
    is_ask = assist_mode == "ask"
    phase = (execution_phase or "").strip().lower()
    if phase not in ("", "plan", "execute_step"):
        phase = ""
    skills_section = get_skills_prompt_section()

    # ── Partie commune : identité + contexte du scénario ouvert ──
    common_ctx = f"""Tu es l'assistant du « Playground » pour le compte {account_id}.
Scénario ouvert : « {fn} » (id flux : {fid}).

Graphe JSON actuel (React Flow, v=2) :
{graph_json}

Historique de discussion : les entrées « contents » reprennent la conversation dans l'ordre chronologique. Tu DOIS t'en servir : si l'utilisateur dit « oui », « comme avant », « fais-le », ou précise une nuance, elle se rapporte aux messages précédents du même fil.
"""

    # ── Connaissances Meta / WhatsApp Business (partagées) ──
    meta_knowledge = """
CONNAISSANCES META / WHATSAPP BUSINESS API :
- Fenêtre de 24 h : après le dernier message du client, l'entreprise peut envoyer des messages libres (session messages) pendant 24 h. Passé ce délai, seul un Template Message approuvé par Meta peut être envoyé.
- Templates : doivent être créés sur Meta Business Manager puis approuvés (délai ~minutes à ~24 h). Ils peuvent contenir des variables ({{1}}, {{2}}, …). Dans le playground le nœud sendTemplate gère ça.
- Catégories de templates : Marketing, Utility, Authentication. Chaque catégorie a ses propres règles de tarification et d'opt-out.
- Limites de messaging : un numéro WhatsApp Business a des tiers (1K, 10K, 100K, illimité) qui limitent le nombre de conversations uniques initiées par l'entreprise en 24 h glissantes.
- Opt-out : les templates marketing doivent inclure un moyen de se désinscrire. Si trop de clients signalent le numéro, la qualité du numéro baisse et Meta peut restreindre l'envoi.
- Messages interactifs : WhatsApp supporte les boutons (max 3), listes (max 10 sections × 10 lignes), réponses rapides. Dans le playground c'est le nœud interactiveNode.
- Médias : images, vidéos, documents, audio peuvent être envoyés. Les templates peuvent avoir un header média.
- Webhook : Meta envoie les messages entrants et statuts via webhook. Le playground s'en occupe automatiquement.
"""

    phase_directive = ""
    if not is_ask and phase == "plan":
        phase_directive = """

PHASE D'EXÉCUTION : PLAN
- Objectif de ce tour : planifier proprement.
- Priorité : produire/mettre à jour un todo détaillé, ordonné et réaliste.
- Si des vérifications externes sont nécessaires (templates, groupes, statuts), déclenche les tool_calls utiles.
- N'essaie pas d'implémenter tout le graphe d'un coup dans cette phase.
- Si aucun changement de graphe n'est requis à ce stade, renvoie "graph": null.
"""
    elif not is_ask and phase == "execute_step":
        phase_directive = """

PHASE D'EXÉCUTION : EXECUTE_STEP
- Objectif de ce tour : traiter UNE étape principale de todo.
- Mets cette étape à "done" (si terminée) et passe la suivante à "in_progress".
- Garde le todo complet dans la réponse.
- Limite-toi au minimum de modifications de graphe nécessaires pour cette étape.
"""

    if is_ask:
        system_text = (
            common_ctx
            + meta_knowledge
            + """
MODE ACTUEL : ASK (conversation libre avec l'utilisateur).

TON RÔLE :
Tu es un assistant conversationnel polyvalent. Tu as une expertise en automatisation WhatsApp, marketing conversationnel et l'API WhatsApp Business de Meta, MAIS tu n'es pas limité à ces sujets. Si l'utilisateur te pose une question sur n'importe quel sujet (recette, code, conseil, culture générale…), réponds normalement comme un chatbot utile et bienveillant.

QUAND LA QUESTION PORTE SUR WHATSAPP / LE PLAYGROUND :
- Explique les concepts (templates, fenêtre 24h, opt-out, catégories, limites…) de façon claire et actionnable.
- Topologie du graphe : une même sortie (même poignée sourceHandle) ne peut mener qu’à un seul nœud suivant à l’exécution ; plusieurs arêtes depuis la même sortie = seule la première est suivie. Plusieurs arêtes qui arrivent sur un même nœud (chemins qui se rejoignent) est en revanche correct.
- Bloc IA (Gemini avec intentions) : augmenter **maxClarifyAttempts** (ex. 2–4) permet plusieurs échanges de clarification sur le **même** nœud avant intent-unknown ; la branche intent-unknown doit mener à un handoff ou un message utile, pas à une impasse. Éviter un router trop strict sur texte libre sans étape de compréhension.
- Nœud Gemini avec intentions : si le routage par mot-clé est ambigu, le moteur peut envoyer une question de précision avant la branche « inconnu » (champs data.clarifyOnUnknown, data.maxClarifyAttempts sur le nœud ; défaut moteur : jusqu’à 3 précisions puis intent-unknown).
- Donne des conseils stratégiques : quel type de campagne, quand envoyer, comment segmenter, comment respecter les règles Meta.
- Tu peux décrire la structure d'un scénario en langage naturel, mais tu ne génères JAMAIS de graphe JSON (graph = null toujours).
- Si l'utilisateur veut construire ou modifier un scénario, tu peux proposer un plan d'étapes dans "todo" (voir format ci-dessous) ; l'interface affichera un bouton pour passer en mode Agent et exécuter ce plan. Tu peux aussi suggérer explicitement le mode Agent.
- Tu as accès aux skills (list_templates, list_broadcast_groups, etc.) même en mode Ask. Utilise-les pour vérifier les données réelles du compte au lieu de deviner.

QUAND LA QUESTION EST GÉNÉRALE (hors WhatsApp) :
- Réponds normalement, avec pertinence et clarté.
- Ne force pas la conversation vers WhatsApp si ce n'est pas le sujet.

STYLE :
- Réponds en français, de façon claire et concise.
- Sois amical et professionnel.
- Utilise des listes ou étapes numérotées quand c'est utile.
- Reste concis sauf si l'utilisateur demande le détail.

FORMAT DE SORTIE OBLIGATOIRE : un seul objet JSON valide, sans texte hors JSON.
Exemple sans plan : {"reply": "…", "graph": null, "todo": null, "tool_calls": []}
Exemple avec plan d'implémentation (graphe toujours null en Ask) :
{"reply": "…", "graph": null, "todo": [{"id": "1", "label": "Étape concrète", "status": "pending"}], "tool_calls": []}

Règle "todo" en mode ASK :
- null si aucun plan n'est pertinent.
- Sinon tableau {"id": string unique, "label": string, "status": "pending"} - une étape = une action sur le scénario. L'UI propose « Continuer en Agent » pour exécuter le plan sur le graphe.
"""
            + phase_directive
            + "\n" + skills_section
        )
    else:
        system_text = (
            common_ctx
            + meta_knowledge
            + """
MODE ACTUEL : AGENT (construction et édition de scénarios).

TON RÔLE :
Tu es un expert technique en construction de scénarios d'automatisation WhatsApp. Tu connais parfaitement les nœuds du playground, les règles de l'API Meta, et tu produis des graphes JSON valides et exécutables.

SI LA DEMANDE EST HORS-SUJET (pas liée à WhatsApp, au playground ou à l'automatisation) :
- Réponds brièvement que tu es en mode Agent, spécialisé dans la construction de scénarios.
- Suggère à l'utilisateur de passer en mode Ask pour discuter librement.
- Mets "graph": null.

TYPES DE NŒUDS AUTORISÉS : start, sendText, sendTemplate, gemini, interactiveNode, routerNode, handoffNode, delayNode, waitUntilNode, timeWindowNode, logicNode.
Chaque nœud a id (string unique), type, position {x,y}, data (objet selon le type - préserve varKey quand il existe).

CONTRAT DATA (obligatoire pour que le canevas et le moteur WhatsApp fonctionnent) :

▌TEMPLATES META (campagnes, relances, hors fenêtre 24h) - À SÉPARER DES MESSAGES SESSION
- Pour tout premier message « entreprise → client » (groupe de diffusion, relance, offre) : tu DOIS utiliser le nœud **sendTemplate** relié au **start** (audience / lancement planifié : data.triggerType = \"playground_audience\" sur start si pertinent).
- **INTERDIT** : mettre un template Meta dans **interactiveNode** (pas de data.templateName, pas de uiKind \"template\", pas de variableValues de template sur interactiveNode). Un tel graphe est **rejeté** par le validateur. Les interactiveNode servent uniquement aux **messages session** (texte + boutons/liste) une fois la fenêtre ouverte.
- **sendTemplate** obligatoire : data.templateName (nom exact), data.templateLanguage (ex. \"fr\"), data.variableValues (ex. {\"1\": \"{{contact.firstName}}\"} pour {{1}} dans le corps Meta).
- Si le template a des **quick replies** (boutons) côté Meta : remplis **data.quickReplyButtons** avec au moins un objet par bouton, ex. [{\"type\":\"QUICK_REPLY\",\"text\":\"Louer un SUV\",\"id\":\"qr_louer\"}, …]. Le moteur attend ce tableau pour attendre la réponse du client. Les **match** du routerNode en aval doivent reprendre le **texte exact** du bouton (comme renvoyé par WhatsApp).
- IMPORTANT robustesse métier : même avec des boutons, le client peut répondre hors sujet en texte libre. Pour CHAQUE routerNode derrière un template / interactiveNode, prévois systématiquement une branche **escape** vers une gestion intelligente (gemini ou handoff) au lieu de bloquer sur du binaire strict.
- Pattern recommandé : quick-reply router (matches exacts) -> route nominale; et escape -> gemini de qualification (sortie contrôlée ex. INTENT_LOUER / INTENT_SAV / HORS_SUJET) -> second router -> réponse adaptée (clarification, reprise de choix, ou transfert humain).
- **Timeout** après template + quick replies : utilise **data.timeoutDuration** (nombre) + **data.timeoutUnit** parmi \"s\", \"m\", \"h\", \"d\" (ex. 10 min → duration \"10\", unit \"m\"). Ne pas inventer timeoutSeconds seul sans duration ; le post-traitement tente une conversion mais la bonne forme est duration+unit.
- Branche **timeout** : arête sortante avec sourceHandle **\"timeout\"** vers logicNode (set variable) ou autre, **sans** sendText si tu veux zéro message au client.
- **Création d’un nouveau template** : si list_templates ne montre pas le modèle voulu, tu DOIS inclure dans la **même** réponse JSON des **tool_calls** avec **create_template** (paramètres complets) pour déclencher le bouton « Confirmer la création » dans l’UI. Ne te contente pas de décrire le template dans \"reply\" sans tool_calls : l’utilisateur n’aura pas la validation. Tant que la création n’est pas confirmée / approuvée Meta, mets **templateStatus** à **\"missing\"** ou **\"pending_review\"** sur le nœud sendTemplate, **jamais** \"approved\" si le template n’existe pas encore sur le compte.

▌MESSAGES SESSION (réponse libre ou choix après ouverture de session)
- **interactiveNode** : data.uiKind **uniquement** \"buttons\" ou \"list\", data.body, data.choices {id, title}. Pas de champs template Meta ici.

▌ROUTAGE : NE PAS SE LIMITER AU OU/NON BINAIRE SUR TEXTE-LIBRE
- **routerNode** fait une **égalité** (ou presque) sur le texte entrant : si l’utilisateur peut formuler autrement (« ma voiture fuit » vs « panne »), prévois une **branche escape** qui mène à un **gemini** (sans intents) dont le systemPrompt impose une **sortie contrôlée** sur une seule ligne (ex. mots-clés FIXES : URGENT, NORMAL, LOUER, SAV) stockée dans varKey, puis un **deuxième routerNode** sur ce varKey ; OU un **gemini avec intents** (keywords élargis) et branche intent-unknown → message de clarification ou handoff.
- Pour les choix **bouton template** / quick reply, le router sur le texte exact des boutons suffit ; pour le **langage naturel** derrière un sendText, combine router + gemini comme ci-dessus.

- sendText : le texte à envoyer est TOUJOURS dans data.body (string). Ne pas utiliser message, text, content ou value - utiliser body.
- routerNode : data.routes est un tableau d'objets { "label": "…", "match": "…" }. « match » est comparé au message texte entrant (égalité, insensible à la casse). Ordre des branches = indices 0,1,2… Les arêtes sortantes doivent avoir sourceHandle "route-0", "route-1", … pour chaque entrée de routes, et sourceHandle "escape" pour la branche par défaut.
- start (message entrant) : pour accepter n'importe quel premier message, data.messageMatch = "any". Sinon "contains" / "equals" / "regex" avec data.messageKeyword rempli.
- gemini (sans intents) : appelle Gemini avec data.systemPrompt et STOCKE la réponse dans data.varKey (ex. "reponse_ia"). CE NŒUD N'ENVOIE PAS de message. Il FAUT un sendText après avec data.body = "{{reponse_ia}}" pour envoyer la réponse au client.
- gemini (avec intents) : classifie le message et route vers intent-0, intent-1, … ou intent-unknown. data.intents = [{keyword: "mot_clé", label: "Libellé"}]. IMPORTANT : chaque intent DOIT avoir un champ "keyword" (pas "match"). Chaque branche DOIT aboutir à un nœud qui envoie. Comportement moteur : data.clarifyOnUnknown (bool, défaut true) et data.maxClarifyAttempts (entier 0–5, défaut 3 côté moteur). Optionnel : data.useEmbeddingSimilarity (bool) + data.embeddingSimilarityThreshold (0,35–0,95, défaut 0,62) : si le mot-clé échoue, similarité sémantique (embeddings Gemini, coût API). data.structuredMemory (bool, défaut true) : journal des intentions dans la variable **flow_structured_notes** (utilisable dans les prompts avec {{flow_structured_notes}}). Variable **flow_recent_user_text** : derniers messages utilisateur concaténés. Si le routage par mot-clé échoue et que clarifyOnUnknown est true, le serveur envoie une courte question de clarification, fixe continueFromNodeId sur CE MÊME nœud Gemini : l’utilisateur peut ainsi rester « sur l’étape IA » plusieurs messages d’affilée jusqu’à épuisement des tentatives, puis seulement bascule sur intent-unknown. **Pour du langage naturel, préfère maxClarifyAttempts à 2, 3 ou 4** (pas seulement 1) afin de laisser le temps de comprendre avant de router. clarifyOnUnknown: false uniquement si tu veux aller tout de suite sur intent-unknown sans clarification. data.toneInstructions pour le ton des questions de clarification (courtes, humaines, sans jargon).
- handoffNode : data.assignAgent (optionnel), data.internalMessage (note interne), data.tagsText (optionnel). Transfert la conversation à un agent humain.

▌BLOC IA (GEMINI) - COMPRENDRE AVANT DE ROUTER (RENFORCEMENT)
- **Ne pas router trop tôt** : un routerNode seul sur une phrase libre échoue dès que le client reformule. Pour toute entrée ambiguë, place plutôt un **gemini avec intentions** en amont (ou une chaîne escape → gemini comme déjà indiqué), avec des **keywords / labels** qui couvrent des formulations variées ; le systemPrompt du nœud doit rappeler le contexte métier pour aider Gemini à extraire le bon mot-clé.
- **Tours multiples sur le même nœud** : c’est le couple clarifyOnUnknown + maxClarifyAttempts qui permet à l’utilisateur de **rester sur l’étape IA** quelques messages pour clarifier avant intent-unknown. Utilise maxClarifyAttempts ≥ 2 quand le sujet est sensible ou complexe.
- **Branche intent-unknown = filet de sécurité** : toujours prévoir une suite utile - **handoffNode**, sendText d’excuse + consignes, ou gemini sans intents + sendText. Jamais un intent-unknown qui se termine sans message au client.
- **Après épuisement des clarifications** : si l’IA ne peut vraiment pas classer, intent-unknown doit mener à une **prise en charge humaine** ou à un message honnête (« je transmets à un conseiller »), pas à un cul-de-sac.
- **Gemini sans intents** : une passe par message pour produire varKey puis enchaînement ; pour un **dialogue de qualification** avant décision, privilégie **gemini avec intents** + clarification plutôt qu’une suite de plusieurs gemini sans intents mal chaînés.

RÈGLE CRITIQUE DE CHAÎNAGE - chaque chemin du graphe DOIT se terminer par un nœud qui ENVOIE un message : sendText, sendTemplate, interactiveNode, ou handoffNode. Les nœuds de traitement interne (routerNode, gemini, delayNode, logicNode, waitUntilNode, timeWindowNode) N'ENVOIENT PAS. Si un chemin se termine par l'un d'eux, le client ne reçoit RIEN.

RÈGLES META À RESPECTER DANS LES SCÉNARIOS :
- Si le scénario est initié par l'entreprise (pas en réponse à un message entrant), le premier message DOIT être un sendTemplate (pas un sendText - sinon Meta bloque hors fenêtre 24h).
- Les boutons interactifs : max 3 boutons par message.
- Les listes interactives : max 10 sections, max 10 lignes par section.
- Les templates marketing doivent prévoir un moyen d'opt-out.

Variables disponibles pour sendTemplate.variableValues :
{prenom_client}, {contact_first_name}, {contact.firstName}, {nom_client}, {contact.name}, {numero_client}, {contact.phone}.

Limites / comportement moteur (production) :
- UNE SORTIE = UN SUCCESSEUR EFFECTIF : pour un même couple (nœud source, sourceHandle), le moteur ne suit qu’UNE seule arête sortante (la première correspondante). Ne relie JAMAIS deux nœuds différents depuis la même poignée (inside, outside, route-0, escape, intent-0, timeout, etc.) : une seule liaison par sortie nommée. Si tu dois enchaîner deux actions, chaîne-les en série (A → B → C), pas en parallèle depuis la même sortie.
- CONVERGENCE (plusieurs entrées vers un même nœud) : autorisée - chemins alternatifs qui se rejoignent sur un bloc commun (ex. même Bloc IA après deux branches exclusives) ; ce n’est pas une double exécution du nœud dans un même passage.
- timeWindowNode : utiliser sourceHandle "inside" / "outside". Si deux arêtes sans poignée, ordre attendu [0] = hors plage, [1] = dans la plage.
- waitUntilNode : pause réelle jusqu’à la date/heure résolue (sinon enchaînement ou passthrough selon le cas).
- delayNode : pause relative (voir flowDelayUntil ; plafond ~30 jours).
- logicNode : mode « si » évalue data.condition ; modes « ou » / « et » = passthrough sans vrai routage multi-sortie.

INTERPRÉTATION DES DEMANDES UTILISATEUR :
- « texte message: Bonjour » / « envoie Bonjour » → sendText avec data.body = "Bonjour"
- « si dit salut => salut, sinon => Bonjour » → routerNode + sendText par branche
- « réponds avec l'IA » / « utilise Gemini » → gemini (systemPrompt + varKey) PUIS sendText (body = "{varKey}")
- « envoie un template X » → sendTemplate avec data.templateName = "X"
- « fais une campagne / envoie en premier » → commence par sendTemplate (règle Meta fenêtre 24h)
- Si ambigu, privilégie un graphe simple mais exécutable avec contenus explicites.

EXEMPLES DE GRAPHE :
- « texte message: Bonjour » → sendText.data.body = "Bonjour"
- « réponds avec l'IA » →
  gemini (data.systemPrompt = "…", data.varKey = "reponse_ia")
  -> sendText (data.body = "{reponse_ia}")
- « si salut alors salut sinon Bonjour » →
  routerNode.data.routes = [{"label":"salut","match":"salut"}]
  route-0 -> sendText("salut"), escape -> sendText("Bonjour")
- « 3 boutons: A, B, C puis réponse différente par choix » →
  interactiveNode (data.uiKind="buttons", data.body="Choisissez", data.choices=[{id:"btn_0",title:"A"},{id:"btn_1",title:"B"},{id:"btn_2",title:"C"}])
  -> (handle défaut) routerNode (data.routes=[{label:"A",match:"A"},{label:"B",match:"B"},{label:"C",match:"C"}])
  route-0 -> sendText("Réponse A"), route-1 -> sendText("Réponse B"), route-2 -> sendText("Réponse C"), escape -> sendText("Autre")

INSTRUCTIONS DE SORTIE :
- Si tu modifies le graphe : fournis nodes + edges + v:2 dans "graph". Au moins un start, ids stables pour les nœuds conservés, arêtes cohérentes.
- Si tu ne modifies pas le graphe (explication, question…) : mets "graph": null.
- "reply" = message court pour l'humain. Ne JAMAIS coller le JSON complet du graphe dans reply.
- CRÉATION TEMPLATE META : si tu dois appeler create_template dans "tool_calls", le backend N'exécute PAS tant que l'utilisateur n'a pas cliqué « Confirmer » dans l'UI (comme une validation de commande). Explique dans "reply" ce qui sera créé et attends la confirmation. Tu peux combiner create_template avec d'autres skills dans le même tour : les autres s'exécutent, create_template reste en attente jusqu'à confirmation.

FORMAT DE SORTIE OBLIGATOIRE : un seul objet JSON valide, sans texte hors JSON :
{"reply": "message pour l'utilisateur", "graph": null ou {"v":2,"nodes":[...],"edges":[...]}, "todo": null ou [...], "tool_calls": []}
"""
            + phase_directive
            + "\n" + skills_section
        )
    # Agent : graphe complet en JSON → besoin de beaucoup de tokens de sortie (sinon JSON tronqué → parse KO).
    generation_config_base: Dict[str, Any] = {
        "temperature": 0.55 if is_ask else 0.25,
        "maxOutputTokens": _playground_assist_max_output_tokens(is_ask),
    }
    if str(settings.GEMINI_MODEL).startswith("gemini-2.5-"):
        generation_config_base["thinkingConfig"] = {
            "thinkingBudget": 2048 if is_ask else 512
        }
    # Sortie JSON contrainte côté API (sinon le modèle renvoie souvent du texte libre → parse KO).
    generation_config_json: Dict[str, Any] = {
        **generation_config_base,
        "responseMimeType": "application/json",
    }

    payload_v1beta = {
        "system_instruction": {"role": "system", "parts": [{"text": system_text}]},
        "contents": hist,
        "generationConfig": generation_config_json,
    }
    flat_system = {"role": "user", "parts": [{"text": system_text}]}
    payload_v1 = {
        "contents": [flat_system] + hist,
        "generationConfig": generation_config_json,
    }

    endpoint_v1beta = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )
    endpoint_v1 = (
        f"https://generativelanguage.googleapis.com/v1/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )

    conv_key = f"playground-assist-{flow_id or account_id}"

    assist_timeout = _GEMINI_PLAYGROUND_ASSIST_READ_TIMEOUT_S
    try:
        try:
            data = await gemini_circuit_breaker.call_async(
                _call_gemini_api,
                endpoint_v1beta,
                payload_v1beta,
                conv_key,
                read_timeout=assist_timeout,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                logger.warning(
                    "Playground assist: v1beta 400 avec responseMimeType JSON, retentative sans MIME forcé"
                )
                payload_v1beta_plain = {
                    **payload_v1beta,
                    "generationConfig": generation_config_base,
                }
                try:
                    data = await gemini_circuit_breaker.call_async(
                        _call_gemini_api,
                        endpoint_v1beta,
                        payload_v1beta_plain,
                        conv_key,
                        read_timeout=assist_timeout,
                    )
                except httpx.HTTPStatusError as exc2:
                    if exc2.response.status_code in (404, 400):
                        payload_v1_plain = {
                            **payload_v1,
                            "generationConfig": generation_config_base,
                        }
                        try:
                            data = await gemini_circuit_breaker.call_async(
                                _call_gemini_api,
                                endpoint_v1,
                                payload_v1,
                                conv_key,
                                read_timeout=assist_timeout,
                            )
                        except httpx.HTTPStatusError as exc3:
                            if exc3.response.status_code == 400:
                                data = await gemini_circuit_breaker.call_async(
                                    _call_gemini_api,
                                    endpoint_v1,
                                    payload_v1_plain,
                                    conv_key,
                                    read_timeout=assist_timeout,
                                )
                            else:
                                raise exc3
                    else:
                        raise exc2
            elif exc.response.status_code in (404, 400):
                try:
                    data = await gemini_circuit_breaker.call_async(
                        _call_gemini_api,
                        endpoint_v1,
                        payload_v1,
                        conv_key,
                        read_timeout=assist_timeout,
                    )
                except httpx.HTTPStatusError as exc2:
                    if exc2.response.status_code == 400:
                        data = await gemini_circuit_breaker.call_async(
                            _call_gemini_api,
                            endpoint_v1,
                            {
                                **payload_v1,
                                "generationConfig": generation_config_base,
                            },
                            conv_key,
                            read_timeout=assist_timeout,
                        )
                    else:
                        raise exc2
            else:
                raise
    except CircuitBreakerOpenError:
        return {
            "reply": "Le service IA est temporairement indisponible (circuit ouvert). Réessaie dans quelques instants.",
            "graph": None,
            "todo": None,
            "skills_used": None,
            "pending_tool_calls": None,
        }
    except httpx.TimeoutException:
        logger.warning(
            "Playground assist Gemini read timeout after %ss (flow=%s)",
            assist_timeout,
            flow_id or account_id,
        )
        return {
            "reply": (
                f"L’IA a mis trop longtemps à répondre (plus de {int(assist_timeout)} s). "
                "Réessaie : si le scénario est très grand, demande une question courte ou un changement ciblé."
            ),
            "graph": None,
            "todo": None,
            "skills_used": None,
            "pending_tool_calls": None,
        }
    except Exception as exc:
        logger.error("Playground assist Gemini failed: %s", exc, exc_info=True)
        return {
            "reply": _user_visible_gemini_failure(exc),
            "graph": None,
            "todo": None,
            "skills_used": None,
            "pending_tool_calls": None,
        }

    # ── Multi-turn skill loop (max 3 rounds) ──
    _MAX_SKILL_ROUNDS = 3
    last_todo: Optional[list] = None
    skills_used: list = []
    frozen_pending_create: List[Dict[str, Any]] = []
    last_skill_results: List[Dict[str, Any]] = []

    for _round in range(_MAX_SKILL_ROUNDS):
        raw_text = _playground_assist_collect_model_text(data)
        finish_reason = _playground_assist_finish_reason(data)

        parsed, partial_json = _playground_assist_parse_model_payload(raw_text)
        if not isinstance(parsed, dict):
            return {
                "reply": _playground_assist_fallback_reply(
                    raw_text, finish_reason=finish_reason
                ),
                "graph": None,
                "todo": last_todo,
                "skills_used": (pre_skills_used + skills_used) or None,
                "pending_tool_calls": frozen_pending_create or None,
            }

        td = parsed.get("todo")
        if isinstance(td, list) and len(td) > 0:
            last_todo = td

        tool_calls = parsed.get("tool_calls")
        if not tool_calls or not isinstance(tool_calls, list) or not tool_calls:
            break

        safe, p_create = _partition_playground_tool_calls(tool_calls)
        if p_create:
            frozen_pending_create = p_create

        logger.info(
            "Playground assist round %d: tool_calls total=%d safe=%d pending_create=%d",
            _round + 1,
            len(tool_calls),
            len(safe),
            len(p_create),
        )

        if p_create and not safe:

            def _early_reply_and_graph(
                _parsed=parsed,
                _raw_text=raw_text,
                _partial_json=partial_json,
            ) -> tuple[str, Optional[Dict[str, Any]]]:
                r = _parsed.get("reply")
                rs = r.strip() if isinstance(r, str) else ""
                rs = _playground_assist_clean_reply_string(rs)
                if not rs:
                    rs = _playground_assist_clean_reply_string((_raw_text or "").strip()) or "Réponse vide."
                if _partial_json:
                    rs += (
                        "\n\n_(Le JSON de réponse était incomplet - souvent parce que le graphe a été coupé en cours de génération. "
                        "Tu peux relire le texte ci-dessus ; le bouton « Appliquer sur le canevas » n\u2019est pas disponible pour ce tour. "
                        "Réessaie avec une modification plus cible ou en mode Ask.)_"
                    )
                og: Optional[Dict[str, Any]] = None
                if not is_ask and not _partial_json:
                    g = _parsed.get("graph")
                    if g is not None and isinstance(g, dict):
                        merged = _normalize_graph(g)
                        if _validate_playground_assist_graph(merged):
                            _coerce_playground_assist_graph_data(merged)
                            og = merged
                        else:
                            rs += (
                                "\n\n_(Un graphe proposé était présent mais invalide - il n\u2019a pas été renvoyé pour application.)_"
                            )
                return rs, og

            er, eg = _early_reply_and_graph()
            merged_skills = [*(pre_skills_used or []), *(skills_used or [])]
            return {
                "reply": er,
                "graph": eg,
                "todo": last_todo,
                "skills_used": merged_skills or None,
                "pending_tool_calls": p_create,
            }

        skill_results = await execute_tool_calls(safe, account)
        last_skill_results = skill_results
        skills_used.extend(r["skill"] for r in skill_results if r.get("skill"))

        tool_result_text = (
            "Résultats des skills demandés :\n"
            + json.dumps(skill_results, ensure_ascii=False, indent=2, default=str)
        )
        hist.append({"role": "model", "parts": [{"text": raw_text}]})
        hist.append({"role": "user", "parts": [{"text": tool_result_text}]})

        payload_v1beta["contents"] = hist
        payload_v1["contents"] = [flat_system] + hist

        try:
            data = await gemini_circuit_breaker.call_async(
                _call_gemini_api,
                endpoint_v1beta,
                payload_v1beta,
                conv_key,
                read_timeout=assist_timeout,
            )
        except Exception as exc_loop:
            logger.error("Playground assist skill loop Gemini error: %s", exc_loop, exc_info=True)
            merged_skills = list(dict.fromkeys([*(pre_skills_used or []), *(skills_used or [])]))
            fallback_reply = (
                _user_visible_gemini_failure(exc_loop)
                + "\n\nLes vérifications demandées ont bien été exécutées avant l'erreur."
            )
            if last_skill_results:
                fallback_reply += (
                    "\nRésultats skills (résumé JSON) :\n"
                    + json.dumps(last_skill_results, ensure_ascii=False, default=str)
                )
            return {
                "reply": fallback_reply,
                "graph": None,
                "todo": last_todo,
                "skills_used": merged_skills or None,
                "pending_tool_calls": frozen_pending_create or None,
            }

    reply = parsed.get("reply")
    reply_str = reply.strip() if isinstance(reply, str) else ""
    reply_str = _playground_assist_clean_reply_string(reply_str)
    if not reply_str:
        reply_str = _playground_assist_clean_reply_string((raw_text or "").strip()) or "Réponse vide."

    td_final = parsed.get("todo")
    if isinstance(td_final, list) and len(td_final) > 0:
        last_todo = td_final

    if partial_json:
        reply_str += (
            "\n\n_(Le JSON de réponse était incomplet - souvent parce que le graphe a été coupé en cours de génération. "
            "Tu peux relire le texte ci-dessus ; le bouton « Appliquer sur le canevas » n\u2019est pas disponible pour ce tour. "
            "Réessaie avec une modification plus cible ou en mode Ask.)_"
        )

    out_graph: Optional[Dict[str, Any]] = None
    if not is_ask and not partial_json:
        g = parsed.get("graph")
        if g is not None and isinstance(g, dict):
            merged = _normalize_graph(g)
            if _validate_playground_assist_graph(merged):
                _coerce_playground_assist_graph_data(merged)
                out_graph = merged
            else:
                reply_str += (
                    "\n\n_(Un graphe proposé était présent mais invalide - il n\u2019a pas été renvoyé pour application. "
                    "Cause fréquente : utilisation d\u2019un interactiveNode comme template Meta (interdit) - utilise sendTemplate + quickReplyButtons ; "
                    "ou template inexistant sans tool_calls create_template.)_"
                )

    merged_skills = list(dict.fromkeys([*(pre_skills_used or []), *(skills_used or [])]))
    return {
        "reply": reply_str,
        "graph": out_graph,
        "todo": last_todo,
        "skills_used": merged_skills or None,
        "pending_tool_calls": frozen_pending_create or None,
    }