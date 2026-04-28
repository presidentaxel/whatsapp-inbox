"""Chat Axelia — Gemini avec routage fast / pro (évaluation de difficulté).

Avec périmètre compte WABA : mêmes outils (skills) que l’assistant Playground
(templates Meta, groupes de diffusion).
"""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import httpx

from app.core.circuit_breaker import CircuitBreakerOpenError, gemini_circuit_breaker
from app.core.config import settings
from app.services.audio_transcription_service import _extract_text_from_gemini_response
from app.services.bot_service import (
    _call_gemini_api,
    _call_gemini_api_once,
    _partition_playground_tool_calls,
    _playground_assist_clean_reply_string,
    _playground_assist_collect_model_text,
    _playground_assist_finish_reason,
    _playground_assist_parse_model_payload,
)
from app.services.playground_skills import (
    execute_tool_calls,
    get_axelia_skills_prompt_section,
)

if TYPE_CHECKING:
    from app.core.permissions import CurrentUser

logger = logging.getLogger("uvicorn.error").getChild("axelia")

_AXELIA_SYSTEM_PROMPT = (
    "Tu es Axelia, un assistant IA intégré à l’interface CRM WhatsApp de l’équipe. "
    "Tu réponds en français, avec un ton clair et professionnel, sauf si l’utilisateur "
    "choisit explicitement une autre langue. "
    "Tu peux rédiger, résumer, expliquer, brainstormer ou proposer des formulations de messages "
    "destinés à des clients WhatsApp. "
    "Tu n’inventes pas de faits précis sur l’entreprise : si tu manques de contexte, "
    "tu le dis et tu demandes ce qu’il faut. "
    "Tu n’utilises pas de titres Markdown avec des dièses ; reste sobre (paragraphes et listes à tirets si utile). "
    "Pour toute action sensible (création template Meta, blocage d’un contact sur une ligne WhatsApp), "
    "tu attends une confirmation explicite dans l’interface ; tu respectes le périmètre du seul compte WABA "
    "que l’utilisateur a sélectionné pour cette discussion."
)

_AXEL_META_HINT = """RAPPEL META / WHATSAPP (concis) :
- Fenêtre 24 h après le dernier message client : messages libres ; hors fenêtre, template approuvé requis pour le premier envoi entreprise→client.
- Templates : catégories MARKETING / UTILITY, variables {{1}}, {{first_name}}, etc., statuts APPROVED / PENDING / REJECTED.
"""

_AXELIA_SECTOR_FOCUS: Dict[str, str] = {
    "general": "",
    "templates": (
        "PRIORITÉ SECTEUR : TEMPLATES META — utilise proactivement list_templates et au besoin "
        "get_template_status ; propose create_template (avec confirmation utilisateur avant envoi Meta) si un template manque."
    ),
    "broadcast": (
        "PRIORITÉ SECTEUR : DIFFUSION / AUDIENCES — utilise list_broadcast_groups pour lister les groupes "
        "et leur effectif lorsque tu parles de ciblage, campagnes ou envois de masse."
    ),
    "writing": (
        "PRIORITÉ SECTEUR : RÉDACTION WHATSAPP — formulations courtes, claires, conformes Meta ; précise tutoiement/vouvoiement si utile."
    ),
    "flows": (
        "PRIORITÉ SECTEUR : PARCOURS & AUTOMATION — explique fenêtre 24h, types de nœuds (Gemini avec intents, routeur, sendTemplate vs session), "
        "bonnes pratiques sans improviser les détails données internes Meta."
    ),
}

_CLASSIFIER_PROMPT = (
    "Tu es un classifieur compact. À partir du transcript ci-dessous, estime uniquement "
    "la difficulté relative de la DERNIÈRE demande utilisateur (sans tenir compte du ton poli). "
    "0 = très simple : salutations, merci au revoir, question d’un mot, réponse triviale. "
    "0.3 = question courte sur un sujet simple. "
    "0.6 = explication structurée, plusieurs contraintes, rédaction métier. "
    "1 = tâche très lourde : raisonnement long, code complexe, analyse juridique/financière fine, "
    "recherche multi-étapes, ou conversation avec beaucoup de contexte technique.\n"
    "Réponds par un unique objet JSON (sans markdown, sans texte autour) : "
    '{"difficulty": <nombre entre 0 et 1>}'
)

_MAX_TURNS = 48
_MAX_TEXT_PER_PART = 12000
_AXELIA_TOOLS_READ_TIMEOUT_S = 120.0
_MAX_SKILL_ROUNDS = 4


def _norm_sector(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    k = raw.strip().lower()
    return k if k in _AXELIA_SECTOR_FOCUS else None


def _build_contents(
    messages: List[Dict[str, Any]],
    attachment: Optional[Dict[str, str]],
) -> List[Dict[str, Any]]:
    trimmed = messages[-_MAX_TURNS:]
    last_idx = len(trimmed) - 1
    out: List[Dict[str, Any]] = []
    for i, m in enumerate(trimmed):
        role = m.get("role")
        text = (m.get("text") or "").strip()
        if role not in ("user", "model"):
            continue
        if role == "model":
            if not text:
                continue
            out.append({"role": "model", "parts": [{"text": text[:_MAX_TEXT_PER_PART]}]})
            continue
        parts: List[Dict[str, Any]] = []
        attach_here = attachment is not None and i == last_idx
        if attach_here and attachment:
            mime = (attachment.get("mime_type") or "").strip().lower()
            b64 = attachment.get("data_base64") or ""
            if mime.startswith("image/") and b64:
                try:
                    base64.standard_b64decode(b64, validate=True)
                except Exception:
                    raise ValueError("attachment_invalid_base64")
                parts.append({"inlineData": {"mimeType": mime, "data": b64}})
        if text:
            parts.append({"text": text[:_MAX_TEXT_PER_PART]})
        elif not parts:
            continue
        out.append({"role": "user", "parts": parts})
    return out


def _transcript_snippet(messages: List[Dict[str, Any]], max_chars: int = 2800) -> str:
    lines: List[str] = []
    for m in messages[-24:]:
        r = (m.get("role") or "").strip()
        t = (m.get("text") or "").strip()
        if not t:
            continue
        prefix = "U" if r == "user" else "A"
        lines.append(f"{prefix}: {t[:800]}")
    blob = "\n".join(lines)
    if len(blob) <= max_chars:
        return blob
    return "…\n" + blob[-max_chars:]


def _parse_difficulty_json(raw: str) -> Optional[float]:
    s = (raw or "").strip()
    if not s:
        return None
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        data = json.loads(s)
        d = float(data.get("difficulty"))
        return max(0.0, min(1.0, d))
    except Exception:
        m = re.search(r' difficulty "?\s*:\s*([\d.]+)', s)
        if m:
            try:
                d = float(m.group(1))
                return max(0.0, min(1.0, d))
            except ValueError:
                return None
    return None


async def estimate_difficulty(
    *,
    messages: List[Dict[str, Any]],
    log_label: str,
    fast_model: str,
) -> float:
    snip = _transcript_snippet(messages)
    classify_user = (
        _CLASSIFIER_PROMPT + "\n\n---\nTRANSCRIPT:\n" + snip + "\n---\nRéponds JSON uniquement."
    )
    gen: Dict[str, Any] = {
        "temperature": 0,
        "maxOutputTokens": 120,
    }
    payload_v1beta: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": classify_user}]}],
        "generationConfig": gen,
    }
    payload_v1: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": classify_user}]}],
        "generationConfig": gen,
    }
    ep_b = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{fast_model}:generateContent"
    )
    ep1 = f"https://generativelanguage.googleapis.com/v1/models/{fast_model}:generateContent"
    data = None
    read_s = float(settings.AXELIA_CLASSIFY_READ_TIMEOUT)
    fb = float(settings.AXELIA_CLASSIFY_FALLBACK_DIFFICULTY)
    label = f"classify-{log_label}"
    try:
        try:
            data = await gemini_circuit_breaker.call_async(
                _call_gemini_api_once,
                ep_b,
                payload_v1beta,
                label,
                read_timeout=read_s,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 404):
                data = await gemini_circuit_breaker.call_async(
                    _call_gemini_api_once,
                    ep1,
                    payload_v1,
                    label,
                    read_timeout=read_s,
                )
            else:
                raise
    except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout):
        logger.warning(
            "axelia: classify timeout after %ss, using fallback difficulty=%.2f",
            read_s,
            fb,
        )
        return fb
    except CircuitBreakerOpenError:
        logger.warning(
            "axelia: gemini circuit open for classify, fallback difficulty=%.2f", fb
        )
        return fb
    text = _extract_text_from_gemini_response(data or {})
    diff = _parse_difficulty_json(text or "")
    if diff is None:
        logger.warning("axelia: difficulty parse failed, raw=%r", (text or "")[:200])
        return 0.45
    return diff


def _axelia_json_fallback(raw_text: str, *, finish_reason: Optional[str] = None) -> str:
    fr = (finish_reason or "").strip().upper()
    if "MAX_TOKEN" in fr:
        return (
            "La génération a été coupée par la limite de tokens. Réessaie en demandant quelque chose de plus court."
        )
    t = (raw_text or "").strip()
    if not t:
        return "Réponse vide du modèle."
    if len(t) > 2800:
        return (
            "La réponse de l’IA n’est pas au format JSON attendu ou est tronquée. Réessaie en une phrase plus ciblée."
        )
    logger.warning(
        "axelia tools: parse JSON failed, finishReason=%s, excerpt=%r",
        finish_reason,
        t[:400],
    )
    return (
        "Je n’ai pas pu interpréter correctement la réponse du modèle. Réessaie, ou reformule la demande "
        f"(extrait : {t[:220]}{'…' if len(t) > 220 else ''})."
    )


async def _generate_once(
    *,
    model_id: str,
    contents: List[Dict[str, Any]],
    log_label: str,
) -> str:
    gen: Dict[str, Any] = {
        "temperature": 0.7,
        "maxOutputTokens": 4096,
    }
    if str(model_id).startswith("gemini-2.5-"):
        gen["thinkingConfig"] = {"thinkingBudget": 1024}

    payload_v1beta: Dict[str, Any] = {
        "system_instruction": {
            "role": "system",
            "parts": [{"text": _AXELIA_SYSTEM_PROMPT}],
        },
        "contents": contents,
        "generationConfig": gen,
    }
    payload_v1: Dict[str, Any] = {
        "contents": [
            {"role": "user", "parts": [{"text": _AXELIA_SYSTEM_PROMPT}]},
            *contents,
        ],
        "generationConfig": gen,
    }
    ep_b = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
    ep1 = f"https://generativelanguage.googleapis.com/v1/models/{model_id}:generateContent"
    data = None
    try:
        data = await gemini_circuit_breaker.call_async(
            _call_gemini_api,
            ep_b,
            payload_v1beta,
            log_label,
            read_timeout=90.0,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 404):
            try:
                data = await gemini_circuit_breaker.call_async(
                    _call_gemini_api,
                    ep1,
                    payload_v1,
                    log_label,
                    read_timeout=90.0,
                )
            except Exception:
                raise
        else:
            raise
    except CircuitBreakerOpenError:
        raise ValueError("gemini_unavailable") from None

    text = _extract_text_from_gemini_response(data or {})
    if not text:
        raise ValueError("empty_reply")
    return text.strip()


def _messages_to_gem_hist(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    hist: List[Dict[str, Any]] = []
    for m in messages[-_MAX_TURNS:]:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        txt = (m.get("text") or "").strip()
        if not txt:
            continue
        txt = txt[:_MAX_TEXT_PER_PART]
        if role == "model":
            hist.append({"role": "model", "parts": [{"text": txt}]})
        elif role == "user":
            hist.append({"role": "user", "parts": [{"text": txt}]})
    return hist


async def _run_axelia_with_tools(
    *,
    messages: List[Dict[str, Any]],
    account: Dict[str, Any],
    sector: Optional[str],
    log_label: str,
    chosen_model: str,
    approve_tool_calls: Optional[List[Dict[str, Any]]],
    acting_user: Optional["CurrentUser"] = None,
) -> Tuple[str, str, List[str], Optional[List[Dict[str, Any]]]]:
    pre_skills: List[str] = []
    msgs_work = [m for m in messages if isinstance(m, dict)]
    if approve_tool_calls:
        creates: List[Dict[str, Any]] = []
        blocks: List[Dict[str, Any]] = []
        for tc in approve_tool_calls[:5]:
            if not isinstance(tc, dict):
                continue
            sn = (tc.get("skill") or tc.get("name") or "").strip()
            if sn == "create_template":
                creates.append(tc)
            elif sn == "meta_block_contact":
                blocks.append(tc)
            else:
                raise ValueError("invalid_approve_tool_calls")
        if blocks and not acting_user:
            raise ValueError("user_required_for_approve_block")
        approve_results: List[Dict[str, Any]] = []
        if creates:
            approve_results.extend(await execute_tool_calls(creates, account))
        if blocks:
            from app.services.axelia_meta_actions import execute_meta_block_approved

            for tc in blocks:
                res = await execute_meta_block_approved(
                    tc.get("args") or {},
                    account=account,
                    user=acting_user,  # type: ignore[arg-type]
                )
                approve_results.append({"skill": "meta_block_contact", "result": res})
        pre_skills = [r["skill"] for r in approve_results if r.get("skill")]
        msgs_work.append(
            {
                "role": "user",
                "text": (
                    "L’utilisateur a confirmé dans l’interface les actions sensibles suivantes. "
                    "Résultats d’exécution (JSON) :\n"
                    + json.dumps(approve_results, ensure_ascii=False)
                ),
            }
        )

    sector_key = _norm_sector(sector) or "general"
    sector_line = _AXELIA_SECTOR_FOCUS.get(sector_key) or ""

    system_text = (
        _AXELIA_SYSTEM_PROMPT
        + "\n\n"
        + _AXEL_META_HINT
        + ("\n\n" + sector_line if sector_line else "")
        + "\n\n"
        + get_axelia_skills_prompt_section()
        + "\n\nCompte WABA (contexte) : "
        + str(account.get("id") or "")
        + " — les skills utilisent ce compte pour appeler l’API Meta / la base interne."
    )

    hist = _messages_to_gem_hist(msgs_work)
    if not hist:
        raise ValueError("empty_messages")

    gen: Dict[str, Any] = {
        "temperature": 0.65,
        "maxOutputTokens": 8192,
        "responseMimeType": "application/json",
    }
    if str(chosen_model).startswith("gemini-2.5-"):
        gen["thinkingConfig"] = {"thinkingBudget": 1024}

    gen_plain: Dict[str, Any] = {k: v for k, v in gen.items() if k != "responseMimeType"}
    gen_plain["temperature"] = 0.65
    gen_plain["maxOutputTokens"] = 8192
    if str(chosen_model).startswith("gemini-2.5-"):
        gen_plain["thinkingConfig"] = {"thinkingBudget": 1024}

    payload_v1beta: Dict[str, Any] = {
        "system_instruction": {"role": "system", "parts": [{"text": system_text}]},
        "contents": hist,
        "generationConfig": gen,
    }
    flat_system = {"role": "user", "parts": [{"text": system_text}]}
    payload_v1: Dict[str, Any] = {
        "contents": [flat_system] + hist,
        "generationConfig": gen,
    }

    endpoint_v1beta = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{chosen_model}:generateContent"
    )
    endpoint_v1 = (
        f"https://generativelanguage.googleapis.com/v1/models/"
        f"{chosen_model}:generateContent"
    )

    conv_key = f"axelia-tools-{log_label}"
    assist_timeout = _AXELIA_TOOLS_READ_TIMEOUT_S

    data: Optional[Dict[str, Any]] = None
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
                    "axelia tools: v1beta 400 JSON mime, retry plain config"
                )
                payload_v1beta_plain = {**payload_v1beta, "generationConfig": gen_plain}
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
                            "generationConfig": gen_plain,
                        }
                        data = await gemini_circuit_breaker.call_async(
                            _call_gemini_api,
                            endpoint_v1,
                            payload_v1_plain,
                            conv_key,
                            read_timeout=assist_timeout,
                        )
                    else:
                        raise exc2
            elif exc.response.status_code in (404, 400):
                data = await gemini_circuit_breaker.call_async(
                    _call_gemini_api,
                    endpoint_v1,
                    payload_v1,
                    conv_key,
                    read_timeout=assist_timeout,
                )
            else:
                raise
    except CircuitBreakerOpenError:
        raise ValueError("gemini_unavailable") from None
    except httpx.TimeoutException:
        logger.warning("axelia tools: read timeout after %ss", assist_timeout)
        raise ValueError("axelia_tools_timeout") from None

    skills_used: List[str] = list(pre_skills)
    frozen_pending: List[Dict[str, Any]] = []
    last_skill_results: List[Dict[str, Any]] = []
    parsed: Optional[Dict[str, Any]] = None
    partial_json = False
    raw_text = ""

    for _round in range(_MAX_SKILL_ROUNDS):
        raw_text = _playground_assist_collect_model_text(data or {})
        finish_reason = _playground_assist_finish_reason(data or {})
        parsed, partial_json = _playground_assist_parse_model_payload(raw_text)
        if not isinstance(parsed, dict):
            reply_err = _axelia_json_fallback(raw_text, finish_reason=finish_reason)
            merged = list(dict.fromkeys([*pre_skills, *skills_used]))
            return reply_err, chosen_model, merged, frozen_pending or None

        tool_calls = parsed.get("tool_calls")
        if not tool_calls or not isinstance(tool_calls, list) or not tool_calls:
            break

        safe, p_create = _partition_playground_tool_calls(tool_calls)
        if p_create:
            frozen_pending = p_create

        if p_create and not safe:

            def _early_reply() -> str:
                r = parsed.get("reply")
                rs = r.strip() if isinstance(r, str) else ""
                rs = _playground_assist_clean_reply_string(rs)
                if not rs:
                    rs = _playground_assist_clean_reply_string((raw_text or "").strip()) or "Réponse vide."
                if partial_json:
                    rs += (
                        "\n\n_(Réponse possiblement tronquée ; confirme la création du template ci-dessous "
                        "quand tu es prêt·e.)_"
                    )
                return rs

            er = _early_reply()
            merged = list(dict.fromkeys([*pre_skills, *skills_used]))
            return er, chosen_model, merged, p_create

        skill_results = await execute_tool_calls(safe, account)
        last_skill_results = skill_results
        skills_used.extend(r["skill"] for r in skill_results if r.get("skill"))

        tool_result_text = (
            "Résultats des skills demandés :\n"
            + json.dumps(skill_results, ensure_ascii=False, indent=2)
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
            logger.error("axelia tools skill-loop Gemini error: %s", exc_loop, exc_info=True)
            merged_skills = list(dict.fromkeys([*pre_skills, *skills_used]))
            fb = (
                "Une erreur s’est produite pendant la poursuite après les vérifications. "
                + f"Détail technique : {str(exc_loop)[:200]}"
            )
            if last_skill_results:
                fb += "\n\nRésumé des données récupérées :\n" + json.dumps(
                    last_skill_results, ensure_ascii=False
                )
            return fb, chosen_model, merged_skills, frozen_pending or None

    if not isinstance(parsed, dict):
        return (
            "Réponse invalide après les appels d’outils.",
            chosen_model,
            list(dict.fromkeys([*pre_skills, *skills_used])),
            frozen_pending or None,
        )

    reply_raw = parsed.get("reply")
    reply_str = reply_raw.strip() if isinstance(reply_raw, str) else ""
    reply_str = _playground_assist_clean_reply_string(reply_str)
    if not reply_str:
        reply_str = _playground_assist_clean_reply_string((raw_text or "").strip()) or "Réponse vide."
    if partial_json:
        reply_str += (
            "\n\n_(Une partie du JSON modèle était incomplète ; le texte ci-dessus est la partie lisible.)_"
        )

    merged_skills = list(dict.fromkeys([*pre_skills, *skills_used]))
    return reply_str, chosen_model, merged_skills, frozen_pending or None


async def run_axelia_chat(
    *,
    messages: List[Dict[str, Any]],
    attachment: Optional[Dict[str, str]] = None,
    log_label: str = "axelia",
    account: Optional[Dict[str, Any]] = None,
    sector: Optional[str] = None,
    approve_tool_calls: Optional[List[Dict[str, Any]]] = None,
    acting_user: Optional["CurrentUser"] = None,
) -> Tuple[str, str, Optional[List[str]], Optional[List[Dict[str, Any]]]]:
    """
    Génère la réponse Axelia.

    Sans compte WABA précis ou avec pièce jointe : même comportement historique (texte seul).

    Avec `account` (dict compte résolu depuis l’UUID) et sans pièce jointe : boucle Gemini + skills Playground.

    Retourne (texte, model_id, skills_used ou None, pending_tool_calls ou None).
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("gemini_not_configured")

    if approve_tool_calls and not account:
        raise ValueError("account_required_for_approve")

    if approve_tool_calls and acting_user is None:
        for tc in approve_tool_calls[:5]:
            if not isinstance(tc, dict):
                continue
            sn = (tc.get("skill") or tc.get("name") or "").strip()
            if sn == "meta_block_contact":
                raise ValueError("user_required_for_approve_block")

    contents = _build_contents(messages, attachment)
    if not contents:
        raise ValueError("empty_messages")

    fast = settings.AXELIA_FAST_MODEL
    pro = settings.AXELIA_PRO_MODEL
    thr = float(settings.AXELIA_DIFFICULTY_THRESHOLD)

    diff = await estimate_difficulty(
        messages=messages,
        log_label=log_label,
        fast_model=fast,
    )
    chosen = pro if diff >= thr else fast
    logger.info(
        "axelia route: difficulty=%.2f threshold=%.2f -> model=%s tools=%s",
        diff,
        thr,
        chosen,
        bool(account and attachment is None),
    )

    if account and attachment is None:
        try:
            return await _run_axelia_with_tools(
                messages=messages,
                account=account,
                sector=sector,
                log_label=log_label,
                chosen_model=chosen,
                approve_tool_calls=approve_tool_calls,
                acting_user=acting_user,
            )
        except ValueError:
            raise
        except Exception as exc:
            logger.exception("axelia tools crashed: %s", exc)
            raise ValueError("axelia_failed") from None

    text = await _generate_once(
        model_id=chosen,
        contents=contents,
        log_label=log_label,
    )
    return text, chosen, None, None

