"""
Jalon M2–M3 - Boucle Gemini outbound (1 tour d’outils max) pour l’inbox Agent Studio.

- M2 : ``AGENT_OUTBOUND_GEMINI_TOOLS_ENABLED`` - JSON ``reply`` + ``tool_calls``, exécution noyau, synthèse.
- M3 : ``AGENT_OUTBOUND_REFLECTION_ENABLED`` - après résultats d’outils, un court passage JSON « qualité »
  injecté dans le prompt de synthèse (un seul appel, tokens plafonnés).
- Réutilise ``_call_gemini_api`` (retry Tenacity + circuit breaker via l’appelant).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services.agent_outbound.kernel import run_agent_kernel_v1_tool_calls
from app.services.agent_outbound.parsing import (
    format_reflection_notes,
    normalize_agent_tool_calls_payload,
    parse_json_object,
)
from app.services.agent_outbound.sanitize import sanitize_kernel_tool_results_for_model
from app.services.agent_outbound.registry import (
    AgentOutboundToolSpec,
    build_agent_kernel_v1_catalog,
    build_effective_kernel_v1_allowlist,
)

logger = logging.getLogger("uvicorn.error").getChild("agent_outbound.loop")

_TOOL_RESULTS_MAX_CHARS = 14_000
_REFLECTION_OBS_SNIP_CHARS = 8000


def _compute_reply_confidence(
    *,
    knowledge_text: str,
    qa_matches: List[Dict[str, Any]],
    user_message: str,
    generated_reply: str,
) -> Tuple[float, List[str]]:
    """Indirection testable (patch) vers le scoring inbox existant."""
    from app.services.bot_service import _compute_bot_confidence

    return _compute_bot_confidence(
        knowledge_text=knowledge_text,
        qa_matches=qa_matches,
        user_message=user_message,
        generated_reply=generated_reply,
    )


def _extract_text_from_gemini(data: Dict[str, Any]) -> str:
    for c in data.get("candidates") or []:
        for p in (c.get("content") or {}).get("parts") or []:
            t = (p.get("text") or "").strip()
            if t:
                return t
    return ""


def _round1_response_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "reply": {"type": "string"},
            "tool_calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string"},
                        "args": {"type": "object"},
                    },
                    "required": ["skill", "args"],
                },
            },
        },
        "required": ["tool_calls"],
    }


def _reflection_response_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "sufficiency": {
                "type": "string",
                "enum": ["sufficient", "partial", "insufficient"],
            },
            "brief": {
                "type": "string",
                "description": "Analyse interne max ~600 caractères, en français.",
            },
            "caveats": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["sufficiency", "brief", "caveats"],
    }


async def _run_reflection_pass(
    *,
    conversation_id: str,
    msg: str,
    observation_block: str,
    draft_reply_hint: str,
    read_timeout: float,
) -> str:
    """Un passage Gemini JSON court ; chaîne vide si échec (dégradation silencieuse)."""
    from app.core.config import settings

    obs = (observation_block or "").strip()
    if not obs:
        return ""
    if len(obs) > _REFLECTION_OBS_SNIP_CHARS:
        obs = obs[: _REFLECTION_OBS_SNIP_CHARS - 3] + "…"

    reflect_system = (
        "Tu es un contrôleur qualité interne (le client ne te lit jamais).\n"
        "Tu reçois le dernier message client et les résultats JSON d’outils déjà exécutés.\n"
        "Tâche : juger si les données permettent une réponse fiable, signaler lacunes ou erreurs d’outils, "
        "sans rédiger le message client.\n"
        "Réponds avec un seul objet JSON (schéma imposé) : sufficiency, brief (≤600 caractères), "
        "caveats (0 à 6 courtes chaînes).\n"
        "Rappels : ne pas inventer de faits hors JSON ; si un outil a renvoyé une erreur, cite-la dans caveats.\n"
        "\n## Résultats d’outils (JSON)\n\n```json\n"
        + obs
        + "\n```\n"
    )
    user_part = "Analyse par rapport au dernier message client (extrait ci-dessous)."
    user_text = (msg or "").strip()[:2000]
    if (draft_reply_hint or "").strip():
        user_text += (
            "\n\n---\nBrouillon interne optionnel (tour précédent, ne pas traiter comme vérité) :\n"
            + (draft_reply_hint.strip()[:800])
        )
    contents: List[Dict[str, Any]] = [
        {"role": "user", "parts": [{"text": f"{user_part}\n\n{user_text}"}]},
    ]

    gen_reflect: Dict[str, Any] = {
        "temperature": 0.2,
        "maxOutputTokens": 384,
        "responseMimeType": "application/json",
        "responseSchema": _reflection_response_schema(),
    }
    if str(settings.GEMINI_MODEL).startswith("gemini-2.5-"):
        gen_reflect["thinkingConfig"] = {"thinkingBudget": 256}

    data_r, err_r = await _gemini_generate_once(
        conv_key=f"agent-outbound-r3-reflect-{conversation_id}",
        system_instruction=reflect_system,
        contents=contents,
        generation_config=gen_reflect,
        read_timeout=read_timeout,
    )
    if err_r or not data_r:
        logger.info(
            "agent outbound M3 reflection skipped conversation=%s reason=%s",
            conversation_id,
            err_r or "empty",
        )
        return ""

    text_r = _extract_text_from_gemini(data_r)
    parsed_r = parse_json_object(text_r) if text_r else None
    if not parsed_r:
        logger.info("agent outbound M3 reflection parse failed conversation=%s", conversation_id)
        return ""

    notes = format_reflection_notes(parsed_r)
    if notes:
        logger.info("agent outbound M3 reflection ok conversation=%s chars=%d", conversation_id, len(notes))
    return notes


def _format_tool_catalog_for_system(specs: List[AgentOutboundToolSpec]) -> str:
    blocks: List[str] = []
    for s in specs:
        blocks.append(
            f"#### `{s.name}`\n{s.description}\n"
            f"Arguments (JSON Schema) : ```json\n{json.dumps(s.parameters_json_schema, ensure_ascii=False)}\n```"
        )
    return "\n\n".join(blocks)


def _truncate_tool_results_blob(blob: str) -> str:
    if len(blob) <= _TOOL_RESULTS_MAX_CHARS:
        return blob
    return blob[: _TOOL_RESULTS_MAX_CHARS - 24] + "\n…(tronqué pour le prompt)"


async def _gemini_generate_once(
    *,
    conv_key: str,
    system_instruction: str,
    contents: List[Dict[str, Any]],
    generation_config: Dict[str, Any],
    read_timeout: float,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Un appel generateContent ; retourne (data, erreur_courte) ou (None, raison)."""
    import httpx

    from app.core.circuit_breaker import CircuitBreakerOpenError, gemini_circuit_breaker
    from app.core.config import settings
    from app.services.bot_service import _call_gemini_api

    payload_v1beta = {
        "system_instruction": {"role": "system", "parts": [{"text": system_instruction}]},
        "contents": contents,
        "generationConfig": generation_config,
    }
    flat_system = {"role": "user", "parts": [{"text": system_instruction}]}
    payload_v1 = {
        "contents": [flat_system] + contents,
        "generationConfig": generation_config,
    }
    model = settings.GEMINI_MODEL
    endpoint_v1beta = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    endpoint_v1 = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent"

    def _plain_gen(gen: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in gen.items() if k not in ("responseMimeType", "responseSchema")}

    data: Optional[Dict[str, Any]] = None
    try:
        data = await gemini_circuit_breaker.call_async(
            _call_gemini_api,
            endpoint_v1beta,
            payload_v1beta,
            conv_key,
            read_timeout=read_timeout,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (400, 404) and generation_config.get("responseMimeType"):
            gen_plain = _plain_gen(generation_config)
            payload_v1beta_plain = {**payload_v1beta, "generationConfig": gen_plain}
            try:
                data = await gemini_circuit_breaker.call_async(
                    _call_gemini_api,
                    endpoint_v1beta,
                    payload_v1beta_plain,
                    conv_key,
                    read_timeout=read_timeout,
                )
            except httpx.HTTPStatusError as exc2:
                if exc2.response.status_code not in (400, 404):
                    return None, f"gemini_http_{exc2.response.status_code}"
                payload_v1_plain = {**payload_v1, "generationConfig": gen_plain}
                try:
                    data = await gemini_circuit_breaker.call_async(
                        _call_gemini_api,
                        endpoint_v1,
                        payload_v1,
                        conv_key,
                        read_timeout=read_timeout,
                    )
                except httpx.HTTPStatusError as exc3:
                    if exc3.response.status_code == 400:
                        data = await gemini_circuit_breaker.call_async(
                            _call_gemini_api,
                            endpoint_v1,
                            payload_v1_plain,
                            conv_key,
                            read_timeout=read_timeout,
                        )
                    else:
                        return None, f"gemini_http_{exc3.response.status_code}"
        elif status in (400, 404):
            try:
                data = await gemini_circuit_breaker.call_async(
                    _call_gemini_api,
                    endpoint_v1,
                    payload_v1,
                    conv_key,
                    read_timeout=read_timeout,
                )
            except httpx.HTTPStatusError as exc2:
                return None, f"gemini_http_{exc2.response.status_code}"
        else:
            return None, f"gemini_http_{status}"
    except CircuitBreakerOpenError:
        return None, "gemini_circuit_open"
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("agent outbound loop: gemini network error: %s", exc)
        return None, "gemini_network"
    except Exception as exc:
        logger.exception("agent outbound loop: gemini unexpected: %s", exc)
        return None, "gemini_internal"

    return data, None


async def run_agent_outbound_inbox_gemini_with_tools(
    *,
    conversation_id: str,
    account_id: str,
    account: Dict[str, Any],
    allowed_tools: List[str],
    agent_playbook: str,
    qa_block: str,
    msg: str,
    conversation_parts: List[Dict[str, Any]],
    qa_queries_used: List[str],
    qa_matches: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Génère une réponse inbox avec au plus un tour d’exécution d’outils, optionnellement une réflexion
    qualité (M3), puis une synthèse destinée au client.

    Retour aligné sur ``generate_agent_studio_inbox_reply_with_confidence`` :
    ``reply``, ``confidence``, ``confidence_reasons``, ``qa_queries_used``,
    optionnellement ``agent_kernel_tools_used``, ``agent_outbound_reflection_used`` (M3).
    """
    from app.core.config import settings

    empty = {
        "reply": None,
        "confidence": 0.0,
        "confidence_reasons": [],
        "qa_queries_used": qa_queries_used,
    }

    effective = build_effective_kernel_v1_allowlist(allowed_tools)
    if not effective:
        empty["confidence_reasons"] = ["Aucun outil noyau v1 disponible pour la configuration."]
        return empty

    specs, _rejected = build_agent_kernel_v1_catalog(allowed_tools)
    if not specs:
        empty["confidence_reasons"] = ["Catalogue outils agent vide après filtrage."]
        return empty

    catalog = _format_tool_catalog_for_system(specs)
    read_timeout = float(getattr(settings, "AGENT_OUTBOUND_GEMINI_READ_TIMEOUT_S", 45.0) or 45.0)

    round1_instruction = (
        "Tu es l’agent WhatsApp défini dans la fiche ci-dessous (français).\n"
        "- Tu peux demander **au plus un tour** d’outils listés pour récupérer des faits avant de répondre au client.\n"
        "- Réponds avec **un seul objet JSON** (pas de markdown autour) respectant le schéma imposé par l’API.\n"
        "- Champs : `reply` (optionnel, brouillon court) et `tool_calls` (tableau ; **vide** si tu n’as besoin d’aucun outil).\n"
        "- Chaque entrée de `tool_calls` : `{\"skill\": \"<nom exact>\", \"args\": { ... } }` ; `args` doit respecter le JSON Schema de l’outil.\n"
        "- Noms d’outils **strictement** parmi ceux documentés ci-dessous (sinon le serveur rejettera).\n"
        "- Interdit : inventer des données ; si un outil échoue, tu le verras au tour suivant.\n"
        "- Pas de champ `account_scope` dans `args` (mono-ligne).\n"
        "- Confidentialité : n’utilise les outils que pour des faits nécessaires à **ce** client ; "
        "ne sollicite pas d’historique ou de contacts hors du besoin exprimé.\n"
        "\n## Catalogue outils (noyau lecture seule)\n\n"
        f"{catalog}\n"
    )
    system_round1 = (round1_instruction + "\n---\n## Fiche agent\n\n" + agent_playbook).strip()
    if qa_block:
        system_round1 += "\n\n---\n## Q&A interne (appui factuel)\n\n" + qa_block

    gen_base: Dict[str, Any] = {
        "temperature": 0.35,
        "maxOutputTokens": 1536,
    }
    if str(settings.GEMINI_MODEL).startswith("gemini-2.5-"):
        gen_base["thinkingConfig"] = {"thinkingBudget": 512}

    gen_round1 = {
        **gen_base,
        "responseMimeType": "application/json",
        "responseSchema": _round1_response_schema(),
    }

    conv_key = f"agent-outbound-r1-{conversation_id}"
    data1, err1 = await _gemini_generate_once(
        conv_key=conv_key,
        system_instruction=system_round1,
        contents=conversation_parts,
        generation_config=gen_round1,
        read_timeout=read_timeout,
    )
    if err1 or not data1:
        empty["confidence_reasons"] = [f"Erreur Gemini (tour outils): {err1 or 'empty'}."]
        return empty

    text1 = _extract_text_from_gemini(data1)
    if not text1:
        empty["confidence_reasons"] = ["Gemini n’a pas renvoyé de texte (tour outils)."]
        return empty

    parsed = parse_json_object(text1)
    if not parsed:
        empty["confidence_reasons"] = ["Réponse JSON Gemini illisible (tour outils)."]
        return empty

    tool_calls = normalize_agent_tool_calls_payload(parsed.get("tool_calls"))
    tools_used: List[str] = []

    observation_block = ""
    if tool_calls:
        results = await run_agent_kernel_v1_tool_calls(
            account=account,
            allowed_tools=allowed_tools,
            tool_calls=tool_calls,
        )
        for r in results:
            sk = str(r.get("skill") or "")
            res = r.get("result")
            if isinstance(res, dict) and not res.get("error") and not res.get("kernel_error"):
                if sk:
                    tools_used.append(sk)
        safe_results = sanitize_kernel_tool_results_for_model(results)
        observation_block = _truncate_tool_results_blob(
            json.dumps(safe_results, ensure_ascii=False)
        )

    reflection_notes = ""
    reflection_active = False
    if observation_block and bool(getattr(settings, "AGENT_OUTBOUND_REFLECTION_ENABLED", False)):
        reflex_to = float(getattr(settings, "AGENT_OUTBOUND_REFLECTION_READ_TIMEOUT_S", 25.0) or 25.0)
        reflex_to = min(read_timeout, reflex_to)
        draft_hint = ""
        dr = parsed.get("reply")
        if isinstance(dr, str) and dr.strip():
            draft_hint = dr.strip()
        reflection_notes = await _run_reflection_pass(
            conversation_id=conversation_id,
            msg=msg,
            observation_block=observation_block,
            draft_reply_hint=draft_hint,
            read_timeout=reflex_to,
        )
        reflection_active = bool(reflection_notes)

    round2_instruction = (
        "Tu es l’agent WhatsApp (conversation client, français).\n"
        "Tu reçois éventuellement des **résultats d’outils internes** (JSON). Rédige **uniquement** "
        "le message final à envoyer au client.\n"
        "- Texte simple : pas de Markdown avec doubles astérisques ni titres # ; tirets autorisés.\n"
        "- Ne mentionne pas les outils, APIs, JSON ni « j’ai consulté ».\n"
        "- Ne divulgue **aucune** donnée d’un autre client, numéro, conversation ou identifiant interne "
        "(UUID, jetons, clés) : si le JSON contient plus que le besoin du message actuel, ignore le surplus.\n"
        "- Ne révèle pas d’e-mails ni secrets même s’ils apparaissent dans les observations (considère-les comme non fiables / à masquer).\n"
        "- Si les résultats d’outils sont vides ou en erreur, reste prudent et propose une suite concrète sans inventer.\n"
    )
    if observation_block:
        parts_r2: List[str] = [
            round2_instruction,
            "\n---\n## Observations outils (JSON)\n\n```json\n",
            observation_block,
            "\n```",
        ]
        if reflection_notes:
            parts_r2.extend(
                [
                    "\n\n---\n## Réflexion qualité (interne - ne jamais citer au client)\n\n",
                    reflection_notes,
                ]
            )
        parts_r2.extend(["\n\n---\n## Fiche agent\n\n", agent_playbook])
        system_round2 = "".join(parts_r2).strip()
    else:
        system_round2 = (round2_instruction + "\n---\n## Fiche agent\n\n" + agent_playbook).strip()
    if qa_block:
        system_round2 += "\n\n---\n## Q&A interne\n\n" + qa_block

    gen_round2 = {**gen_base, "maxOutputTokens": 2048}

    data2, err2 = await _gemini_generate_once(
        conv_key=f"agent-outbound-r2-{conversation_id}",
        system_instruction=system_round2,
        contents=conversation_parts,
        generation_config=gen_round2,
        read_timeout=read_timeout,
    )
    if err2 or not data2:
        empty["confidence_reasons"] = [f"Erreur Gemini (synthèse): {err2 or 'empty'}."]
        return empty

    final_text = _extract_text_from_gemini(data2).strip()
    if not final_text:
        empty["confidence_reasons"] = ["Gemini n’a pas renvoyé de texte exploitable (synthèse)."]
        return empty

    confidence, reasons = _compute_reply_confidence(
        knowledge_text=agent_playbook,
        qa_matches=qa_matches,
        user_message=msg,
        generated_reply=final_text,
    )
    reasons_list = list(reasons)
    reasons_list.insert(0, "Mode Agent Studio + outils noyau (M2).")
    if reflection_active:
        reasons_list.insert(1, "Contrôle qualité interne (M3).")
    if tools_used:
        reasons_list.append(f"Outils exécutés: {', '.join(tools_used)}.")

    out: Dict[str, Any] = {
        "reply": final_text,
        "confidence": confidence,
        "confidence_reasons": reasons_list,
        "qa_queries_used": qa_queries_used,
    }
    if tools_used:
        out["agent_kernel_tools_used"] = tools_used
    if reflection_active:
        out["agent_outbound_reflection_used"] = True
    logger.info(
        "agent outbound M2+M3 done conversation=%s account=%s tools_used=%s reflection=%s",
        conversation_id,
        account_id,
        tools_used,
        reflection_active,
    )
    return out
