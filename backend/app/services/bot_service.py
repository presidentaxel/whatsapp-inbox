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

import logging
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException

from app.core.cache import cached, invalidate_cache_pattern
from app.core.circuit_breaker import gemini_circuit_breaker, CircuitBreakerOpenError
from app.core.config import settings
from app.core.db import supabase, supabase_execute
from app.core.http_client import get_http_client
from app.core.retry import retry_on_network_error

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
    }
    return placeholder


async def upsert_bot_profile(account_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Met à jour le bot profile et invalide le cache.
    """
    custom_fields = payload.get("custom_fields") or []
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
        "business_name": payload.get("business_name"),
        "description": payload.get("description"),
        "address": payload.get("address"),
        "hours": payload.get("hours"),
        "knowledge_base": payload.get("knowledge_base"),
        "custom_fields": normalized_fields,
        "template_config": _sanitize_template_config(payload.get("template_config") or {}),
    }
    await supabase_execute(
        supabase.table("bot_profiles").upsert(
            upsert_payload,
            on_conflict="account_id",
        )
    )

    # Invalider le cache
    await invalidate_cache_pattern(f"bot_profile:{account_id}")

    return await get_bot_profile(account_id)


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def _call_gemini_api(
    endpoint: str,
    payload: dict,
    conversation_id: str,
) -> dict:
    """
    Appelle l'API Gemini avec retry sur les erreurs réseau.

    Raises:
        httpx.HTTPStatusError: Si l'API retourne une erreur HTTP
        httpx.TimeoutException: Si le timeout est dépassé
        httpx.NetworkError: Si problème réseau
    """
    client = await get_http_client()

    # Timeout spécifique pour Gemini
    timeout = httpx.Timeout(
        connect=3.0,
        read=15.0,  # 15s au lieu de 45s
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
        logger.error("Gemini timeout for conversation %s after 15s", conversation_id)
        raise
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        body = exc.response.text
        logger.warning(
            "Gemini API error for conversation %s (status=%s): %s",
            conversation_id,
            status_code,
            body[:200],
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

    payload = {
        "system_instruction": {
            "role": "system",
            "parts": [
                {
                    "text": f"{instruction}\n\nContexte entreprise (PLAYBOOK):\n{knowledge_text}".strip()
                }
            ],
        },
        "contents": conversation_parts,
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 250,
        },
    }

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )

    try:
        async with gemini_circuit_breaker:
            data = await _call_gemini_api(endpoint, payload, conversation_id)
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

    candidates: List[Dict[str, Any]] = data.get("candidates") or []
    for candidate in candidates:
        parts = candidate.get("content", {}).get("parts") or []
        for part in parts:
            text = (part.get("text") or "").strip()
            if text:
                logger.info(
                    "Gemini produced reply for conversation %s (chars=%d)",
                    conversation_id,
                    len(text),
                )
                return text

    logger.info("Gemini returned no usable candidates for conversation %s", conversation_id)
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

    template_text = _render_template_sections(profile.get("template_config") or {})
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

    return "\n".join(filter(None, lines)).trim()