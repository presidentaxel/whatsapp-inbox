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
    client = await get_http_client()

    read_s = float(read_timeout) if read_timeout else _GEMINI_DEFAULT_READ_TIMEOUT_S
    if read_s > _GEMINI_DEFAULT_READ_TIMEOUT_S:
        # Assistant Playground : gros prompt / réponse JSON — laisser plus de marge réseau.
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

    # Récupérer l'historique
    history_rows = (
        await supabase_execute(
            supabase.table("messages")
            .select("direction, content_text")
            .eq("conversation_id", conversation_id)
            .order("timestamp", desc=True)
            .limit(10)
        )
    ).data
    history_rows.reverse()

    conversation_parts: List[Dict[str, Any]] = []
    for row in history_rows:
        content = (row.get("content_text") or "").strip()
        if not content:
            continue
        role = "user" if row.get("direction") == "inbound" else "model"
        conversation_parts.append({"role": role, "parts": [{"text": content}]})

    if not conversation_parts or conversation_parts[-1]["role"] != "user":
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
        "- Si la question de l'utilisateur nécessite une information absente ou insuffisante dans le PLAYBOOK, "
        "tu ne réponds pas à la question et tu réponds uniquement : "
        "\"Je me renseigne auprès d'un collègue et je reviens vers vous au plus vite\".\n"
        "- Tu ne dis jamais que tu ne sais pas ou que l'information n'existe pas.\n"
        "\n"
        "Contenus non textuels :\n"
        "- Si l'utilisateur envoie une image, une vidéo, un audio ou tout contenu non textuel, tu réponds : "
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
    
    # Config commune pour Gemini
    generation_config: Dict[str, Any] = {
        "temperature": 0.4,
        "maxOutputTokens": 2048,  # plus large pour laisser de la marge
    }
    
    # Si on utilise un modèle 2.5 (Pro / Flash / Flash-Lite avec thinking),
    # on ajoute un thinkingBudget pour éviter qu'il ne mange tout le budget en "pensées".
    if str(settings.GEMINI_MODEL).startswith("gemini-2.5-"):
        generation_config["thinkingConfig"] = {
            "thinkingBudget": 512  # 512 tokens max pour penser, le reste pour répondre
        }
    
    # Try v1beta first (supports system_instruction, but may not have all models)
    payload_v1beta = {
        "system_instruction": {
            "role": "system",
            "parts": [
                {
                    "text": f"{instruction}\n\nContexte entreprise (PLAYBOOK):\n{knowledge_text}".strip()
                }
            ],
        },
        "contents": conversation_parts,
        "generationConfig": generation_config,
    }
    
    # Fallback for v1 API (doesn't support system_instruction, need to put in contents)
    system_message = {
        "role": "user",
        "parts": [
            {
                "text": f"{instruction}\n\nContexte entreprise (PLAYBOOK):\n{knowledge_text}".strip()
            }
        ],
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
                return text
            else:
                logger.warning(f"🔍 [GEMINI DEBUG] Candidate {idx} part {part_idx} has no text: {part}")

    logger.warning(f"❌ Gemini returned no usable candidates for conversation {conversation_id}. Full response: {json.dumps(data, indent=2)[:1000]}")
    return None


async def generate_flow_gemini_keyword(
    conversation_id: str,
    _account_id: str,
    user_text: str,
    system_prompt: str,
    hint: Optional[str] = None,
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

    generation_config: Dict[str, Any] = {
        "temperature": 0.1,
        "maxOutputTokens": 32,
    }
    if str(settings.GEMINI_MODEL).startswith("gemini-2.5-"):
        generation_config["thinkingConfig"] = {"thinkingBudget": 128}

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
                return text.split()[0] if text else None
    return None


async def generate_flow_gemini_text_reply(
    conversation_id: str,
    _account_id: str,
    user_text: str,
    system_prompt: str,
    hint: Optional[str] = None,
) -> Optional[str]:
    """
    Nœud Gemini « sans intentions » mais avec prompt système : réponse conversationnelle
    complète (pour {{varKey}} puis sendText / interactive), pas le playbook SAV.
    Utilise l'historique de la conversation pour un meilleur contexte.
    """
    if not settings.GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY absent, skip flow gemini text for %s", conversation_id)
        return None
    user_text = (user_text or "").strip()
    base = (system_prompt or "").strip()
    if not base:
        return None
    if "[INSERER LE TEXTE DU USER ICI]" in base:
        instruction = base.replace("[INSERER LE TEXTE DU USER ICI]", user_text or "(aucun message)")
    else:
        instruction = f"{base}\n\nDernier message de l'utilisateur :\n{user_text or '(aucun message)'}"
    if hint:
        instruction = f"{instruction}\n\nConsigne complémentaire :\n{hint.strip()}"
    instruction = (
        f"{instruction}\n\n"
        "Réponds en français. Réponse directe au client (pas de préambule méta, pas de guillemets autour du message entier)."
    )

    generation_config: Dict[str, Any] = {
        "temperature": 0.55,
        "maxOutputTokens": 1024,
    }
    if str(settings.GEMINI_MODEL).startswith("gemini-2.5-"):
        generation_config["thinkingConfig"] = {"thinkingBudget": 256}

    conversation_parts: List[Dict[str, Any]] = []
    try:
        history_rows = (
            await supabase_execute(
                supabase.table("messages")
                .select("direction, content_text")
                .eq("conversation_id", conversation_id)
                .order("timestamp", desc=True)
                .limit(8)
            )
        ).data
        history_rows.reverse()
        for row in history_rows:
            content = (row.get("content_text") or "").strip()
            if not content:
                continue
            role = "user" if row.get("direction") == "inbound" else "model"
            conversation_parts.append({"role": role, "parts": [{"text": content}]})
    except Exception as hist_exc:
        logger.warning("Flow Gemini text: could not load history: %s", hist_exc)

    if not conversation_parts or conversation_parts[-1]["role"] != "user":
        conversation_parts.append({"role": "user", "parts": [{"text": user_text or "Rédige la réponse demandée."}]})

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


def _format_conversation_preview(parts: List[Dict[str, Any]], limit: int = 8) -> str:
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


async def generate_playground_assist_reply(
    *,
    account_id: str,
    flow_id: Optional[str],
    flow_name: str,
    graph: Dict[str, Any],
    messages: List[Dict[str, str]],
    mode: str = "agent",
) -> Dict[str, Any]:
    """
    Assistant éditeur Playground : mode « ask » (Q&R / analyse, sans graphe) ou « agent » (peut proposer un graphe complet).
    """
    if not settings.GEMINI_API_KEY:
        return {"reply": "GEMINI_API_KEY n’est pas configurée côté serveur.", "graph": None}

    from app.services.playground_flow_service import _normalize_graph

    norm = _normalize_graph(graph)
    graph_json = json.dumps(norm, ensure_ascii=False)

    hist: List[Dict[str, Any]] = []
    for m in messages[-_PLAYGROUND_ASSIST_MAX_MESSAGES:]:
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
        return {"reply": "Envoie un message pour commencer.", "graph": None}

    fn = (flow_name or "").strip() or "(sans nom)"
    fid = flow_id or "—"

    assist_mode = (mode or "agent").strip().lower()
    if assist_mode not in ("ask", "agent"):
        assist_mode = "agent"
    is_ask = assist_mode == "ask"

    common_ctx = f"""Tu es l’assistant des scénarios « Playground » (automatisations WhatsApp) pour le compte {account_id}.
Scénario ouvert : « {fn} » (id flux : {fid}).

Graphe JSON actuel (React Flow, v=2) :
{graph_json}

Types de nœuds autorisés : start, sendText, sendTemplate, gemini, interactiveNode, routerNode, handoffNode, delayNode, waitUntilNode, timeWindowNode, logicNode.
Chaque nœud a id (string unique), type, position {{x,y}}, data (objet selon le type — préserve varKey quand il existe).

Limites importantes du moteur en production (à mentionner si pertinent) :
- timeWindowNode / waitUntilNode : le serveur ne distingue pas toutes les branches ni l’attente calendaire comme dans l’UI ; seul delayNode fait une vraie pause relative.
- logicNode : modes « si » / « et » / « ou » ne font pas d’IF métier côté serveur comme dans l’UI ; pour du routage par texte préférer routerNode, interactiveNode ou gemini.

Historique de discussion : les entrées « contents » reprennent la conversation dans l’ordre chronologique (tours user puis réponses assistant). Tu DOIS t’en servir : si l’utilisateur dit « oui », « comme avant », « fais-le », ou précise une nuance, elle se rapporte aux messages précédents du même fil.

Variables utiles pour les champs « variableValues » des nœuds sendTemplate (substitution côté serveur au moment de l’envoi, d’après le contact) :
{{prenom_client}}, {{contact_first_name}}, {{contact.firstName}}, {{nom_client}}, {{contact.name}}, {{numero_client}}, {{contact.phone}}.
Il n’y a pas de civilité automatique (M./Mme) en base : pour « M. Dupont » mets par ex. le texte fixe « M. {{nom_client}} » ou « M. {{prenom_client}} » dans la valeur du slot Meta (ex. variable « nom » du template).
"""

    if is_ask:
        system_text = (
            common_ctx
            + """

MODE ACTUEL : ASK (questions / explications uniquement).
- Réponds en français, de façon claire ; reste concis sauf si l’utilisateur demande le détail.
- Tu n’appliques pas de changements : le champ JSON "graph" doit TOUJOURS être null (aucun graphe exporté, même si on te demande de « modifier » — décris plutôt les étapes ou le JSON à construire à la main).
- Tu peux expliquer le parcours, les branches, les risques (UI vs moteur), et suggérer des améliorations en langage naturel.

FORMAT DE SORTIE OBLIGATOIRE : un seul objet JSON valide, sans texte hors JSON :
{"reply": "…", "graph": null}
"""
        )
    else:
        system_text = (
            common_ctx
            + """

MODE ACTUEL : AGENT (édition du scénario).
- Réponds en français. Tu peux expliquer, puis si l’utilisateur veut une modification concrète du canevas, renvoie le graphe COMPLET mis à jour dans "graph".
- Si tu ne modifies pas le graphe, mets "graph": null. Si tu modifies, fournis nodes + edges + v:2, au moins un start, ids stables pour les nœuds conservés, arêtes cohérentes.
- Si la demande est surtout explicative ou le canevas ne change pas : mets toujours "graph": null (évite de renvoyer tout le JSON du graphe pour rien — limite de taille).
- Dans "reply", message court pour l’humain uniquement : ne jamais y coller l’objet JSON complet ni le graphe (le graphe est uniquement dans "graph").

FORMAT DE SORTIE OBLIGATOIRE : un seul objet JSON valide, sans texte hors JSON, de la forme :
{"reply": "message pour l’utilisateur", "graph": null ou {"v":2,"nodes":[...],"edges":[...]}}
"""
        )

    # Agent : graphe complet en JSON → besoin de beaucoup de tokens de sortie (sinon JSON tronqué → parse KO).
    generation_config_base: Dict[str, Any] = {
        "temperature": 0.22 if is_ask else 0.25,
        "maxOutputTokens": _playground_assist_max_output_tokens(is_ask),
    }
    if str(settings.GEMINI_MODEL).startswith("gemini-2.5-"):
        # Budget pensée plus bas en agent pour laisser de la marge au JSON de sortie.
        generation_config_base["thinkingConfig"] = {
            "thinkingBudget": 128 if is_ask else 128
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
        }
    except Exception as exc:
        logger.error("Playground assist Gemini failed: %s", exc, exc_info=True)
        return {"reply": _user_visible_gemini_failure(exc), "graph": None}

    raw_text = _playground_assist_collect_model_text(data)
    finish_reason = _playground_assist_finish_reason(data)

    parsed, partial_json = _playground_assist_parse_model_payload(raw_text)
    if not isinstance(parsed, dict):
        return {
            "reply": _playground_assist_fallback_reply(
                raw_text, finish_reason=finish_reason
            ),
            "graph": None,
        }

    reply = parsed.get("reply")
    reply_str = reply.strip() if isinstance(reply, str) else ""
    reply_str = _playground_assist_clean_reply_string(reply_str)
    if not reply_str:
        reply_str = _playground_assist_clean_reply_string((raw_text or "").strip()) or "Réponse vide."

    if partial_json:
        reply_str += (
            "\n\n_(Le JSON de réponse était incomplet — souvent parce que le graphe a été coupé en cours de génération. "
            "Tu peux relire le texte ci-dessus ; le bouton « Appliquer sur le canevas » n’est pas disponible pour ce tour. "
            "Réessaie avec une modification plus cible ou en mode Ask.)_"
        )

    out_graph: Optional[Dict[str, Any]] = None
    if not is_ask and not partial_json:
        g = parsed.get("graph")
        if g is not None and isinstance(g, dict):
            merged = _normalize_graph(g)
            if _validate_playground_assist_graph(merged):
                out_graph = merged
            else:
                reply_str += (
                    "\n\n_(Un graphe proposé était présent mais invalide — il n’a pas été renvoyé pour application.)_"
                )

    return {"reply": reply_str, "graph": out_graph}