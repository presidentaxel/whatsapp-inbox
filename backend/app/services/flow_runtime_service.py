"""
Moteur nodal aligné sur le playground React Flow : session Supabase + exécution webhook.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.core.db import supabase, supabase_execute
from app.core.cache import invalidate_cache_pattern
from app.core.pg import fetch_all, get_pool

logger = logging.getLogger("uvicorn.error").getChild("bot.flow")

_FLOW_DELAY_MAX_SECONDS = 86400.0 * 30


def _parse_iso_utc(raw: Any) -> Optional[datetime]:
    if raw is None or raw == "":
        return None
    try:
        s = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _delay_node_seconds(data: dict) -> Optional[float]:
    try:
        d = float(data.get("duration") or 0)
    except (TypeError, ValueError):
        return None
    if d <= 0:
        return None
    u = (data.get("unit") or "s").strip().lower()
    mult = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}.get(u)
    if mult is None:
        return None
    sec = d * mult
    return min(sec, _FLOW_DELAY_MAX_SECONDS)


def _send_template_has_quick_replies(data: dict) -> bool:
    """True si le nœud sendTemplate attend une réponse bouton (quick replies Meta)."""
    qrb = data.get("quickReplyButtons")
    return isinstance(qrb, list) and len(qrb) > 0


def _interactive_timeout_seconds(data: dict) -> Optional[float]:
    """Délai avant branche `timeout` sur interactiveNode / sendTemplate (timeoutDuration + timeoutUnit)."""
    try:
        d = float(data.get("timeoutDuration") or 0)
    except (TypeError, ValueError):
        return None
    if d <= 0:
        return None
    u = (data.get("timeoutUnit") or "h").strip().lower()
    mult = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}.get(u)
    if mult is None:
        return None
    sec = d * mult
    return min(sec, _FLOW_DELAY_MAX_SECONDS)


def _consume_due_flow_delay(session: Dict[str, Any], now: datetime) -> bool:
    """
    Si flowDelayUntil est passé, efface le délai et renseigne continueFromNodeId.
    Retourne True si un délai échu a été consommé.
    """
    until = _parse_iso_utc(session.get("flowDelayUntil"))
    if until is None:
        return False
    if until > now:
        return False
    resume = session.pop("flowDelayResumeNodeId", None)
    session["flowDelayUntil"] = None
    session["currentNodeId"] = None
    session["afterInteractiveTarget"] = None
    if resume:
        session["continueFromNodeId"] = resume
    return True


def extract_inbound_flow_signals(message: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait texte, id bouton Meta et id ligne liste depuis le payload brut webhook."""
    msg_type = (message.get("type") or "").lower()
    out: Dict[str, Any] = {"text": "", "button_id": None, "list_row_id": None}
    if msg_type == "text":
        out["text"] = (message.get("text") or {}).get("body") or ""
    elif msg_type == "interactive":
        inter = message.get("interactive") or {}
        if inter.get("type") == "button_reply":
            br = inter.get("button_reply") or {}
            out["text"] = br.get("title") or ""
            out["button_id"] = br.get("id")
        elif inter.get("type") == "list_reply":
            lr = inter.get("list_reply") or {}
            out["text"] = lr.get("title") or ""
            out["list_row_id"] = lr.get("id")
    elif msg_type == "button":
        bd = message.get("button") or {}
        out["text"] = bd.get("text") or bd.get("payload") or ""
        out["button_id"] = bd.get("payload")
    return out


def _subst_vars(text: str, variables: Dict[str, Any]) -> str:
    if not text:
        return text or ""
    out = str(text)
    items = [(str(k), str(v if v is not None else "")) for k, v in variables.items() if k is not None]
    # Bidirectional accent alias: réponse_… ↔ reponse_…
    accent_prefix = "réponse"
    ascii_prefix = "reponse"
    extra: List[Tuple[str, str]] = []
    for key, repl in items:
        if key.startswith(accent_prefix):
            ascii_key = ascii_prefix + key[len(accent_prefix):]
            if ascii_key != key:
                extra.append((ascii_key, repl))
        elif key.startswith(ascii_prefix):
            accented_key = accent_prefix + key[len(ascii_prefix):]
            if accented_key != key:
                extra.append((accented_key, repl))
    items.extend(extra)
    # Clés les plus longues d’abord (ex. contact.firstName avant contact)
    items.sort(key=lambda kv: len(kv[0]), reverse=True)
    for key, repl in items:
        out = out.replace("{{" + key + "}}", repl)
    for key, repl in items:
        out = out.replace("{" + key + "}", repl)
    return out


def _warn_unresolved_vars(text: str, node_id: str) -> None:
    """Log if any {{…}} placeholders remain after substitution."""
    if text and "{{" in text and "}}" in text:
        import re as _re
        unresolved = _re.findall(r"\{\{([^}]+)\}\}", text)
        if unresolved:
            logger.warning(
                "playground flow: unresolved variable(s) %s in node %s body",
                unresolved, node_id,
            )


# Remplies à chaque tour depuis le contact / la conversation (prioritaires sur le reste).
_BUILTIN_FLOW_VAR_KEYS = frozenset(
    {
        "contact_name",
        "nom_client",
        "contact_phone",
        "numero_client",
        "contact_first_name",
        "prenom_client",
        # Alias style « objet » (souvent générés par l’IA / autres outils)
        "contact.firstName",
        "contact.first_name",
        "contact.name",
        "contact.phone",
    }
)


def _builtin_flow_variables(
    contact: Optional[Dict[str, Any]],
    conversation: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Variables toujours disponibles dans {{…}} (sendText, sendTemplate, prompts Gemini, etc.).
    """
    c = contact if isinstance(contact, dict) else {}
    conv = conversation if isinstance(conversation, dict) else {}
    display = (c.get("display_name") or "").strip()
    wa = (c.get("whatsapp_number") or "").strip()
    client_num = (conv.get("client_number") or "").strip()
    name = display or wa or ""
    phone = wa or client_num or ""
    first = ""
    if display:
        parts = display.split(None, 1)
        if parts:
            first = parts[0]
    if not first:
        first = name or ""
    return {
        "contact_name": name,
        "nom_client": name,
        "contact_phone": phone,
        "numero_client": phone,
        "contact_first_name": first,
        "prenom_client": first,
        "contact.firstName": first,
        "contact.first_name": first,
        "contact.name": name,
        "contact.phone": phone,
    }


def _apply_builtin_flow_variables(
    variables: Dict[str, Any],
    contact: Optional[Dict[str, Any]],
    conversation: Optional[Dict[str, Any]],
) -> None:
    built = _builtin_flow_variables(contact, conversation)
    for k in _BUILTIN_FLOW_VAR_KEYS:
        if k in built:
            variables[k] = built[k]


def _edges_from(edges: List[dict], source_id: str) -> List[Tuple[str, Optional[str]]]:
    res: List[Tuple[str, Optional[str]]] = []
    for e in edges or []:
        if e.get("source") != source_id:
            continue
        h = e.get("sourceHandle")
        res.append((e.get("target"), h if h else None))
    return res


def _successor(
    edges: List[dict],
    source_id: str,
    handle: Optional[str] = None,
) -> Optional[str]:
    outs = _edges_from(edges, source_id)
    if handle is not None:
        for tgt, h in outs:
            if h == handle:
                return tgt
    for tgt, h in outs:
        if h is None:
            return tgt
    if outs:
        return outs[0][0]
    return None


def _pick_start_node_id(nodes_by_id: Dict[str, dict], inbound_text: str) -> Optional[str]:
    """Plusieurs nœuds start : garde ceux dont le déclencheur matche ; priorité entryPriority décroissante."""
    starts: List[Tuple[str, dict]] = [
        (nid, n) for nid, n in nodes_by_id.items() if n.get("type") == "start"
    ]
    if not starts:
        return None
    allowed = [(nid, n) for nid, n in starts if _start_allows_message(n, inbound_text)]
    if not allowed:
        return None

    def sort_key(item: Tuple[str, dict]) -> Tuple[int, str]:
        nid, n = item
        pri = (n.get("data") or {}).get("entryPriority")
        try:
            p = int(pri) if pri is not None and str(pri).strip() != "" else 0
        except (TypeError, ValueError):
            p = 0
        return (-p, nid)

    allowed.sort(key=sort_key)
    return allowed[0][0]


def _start_allows_message(start_node: dict, inbound_text: str) -> bool:
    data = start_node.get("data") or {}
    if data.get("triggerType") == "playground_audience":
        return False
    if data.get("triggerType") != "message_in":
        return True
    match = data.get("messageMatch") or "any"
    if match == "any":
        return True
    kw = (data.get("messageKeyword") or "").strip()
    text = (inbound_text or "").strip()
    if not kw:
        return True
    if match == "contains":
        return kw.lower() in text.lower()
    if match == "equals":
        return kw.lower() == text.lower()
    if match == "regex":
        try:
            return bool(re.search(kw, text))
        except re.error:
            return False
    return True


def _router_pick(
    routes: List[dict],
    edges: List[dict],
    router_id: str,
    inbound_text: str,
    button_id: Optional[str],
    list_row_id: Optional[str],
) -> Optional[str]:
    text = (inbound_text or "").strip()
    for i, route in enumerate(routes or []):
        m = (route.get("match") or "").strip()
        if not m:
            continue
        if button_id and m == button_id:
            return _successor(edges, router_id, f"route-{i}")
        if list_row_id and m == list_row_id:
            return _successor(edges, router_id, f"route-{i}")
        if text == m or text.lower() == m.lower():
            return _successor(edges, router_id, f"route-{i}")
    return _successor(edges, router_id, "escape")


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _gemini_pick(
    intents: List[dict],
    edges: List[dict],
    gemini_id: str,
    raw_keyword: str,
) -> Optional[str]:
    word_raw = (raw_keyword or "").strip().upper()
    word = _strip_accents(word_raw)
    logger.info(
        "gemini_pick: raw=%r  normalized=%r  intents=%s",
        word_raw, word,
        [r.get("keyword") for r in (intents or [])],
    )
    if not word:
        return _successor(edges, gemini_id, "intent-unknown")
    for i, row in enumerate(intents or []):
        kw = _strip_accents((row.get("keyword") or "").strip().upper())
        if kw and kw in word:
            logger.info("gemini_pick: matched intent-%d (%s)", i, kw)
            return _successor(edges, gemini_id, f"intent-{i}")
    for i, row in enumerate(intents or []):
        kw = _strip_accents((row.get("keyword") or "").strip().upper())
        if kw and word.startswith(kw):
            logger.info("gemini_pick: startswith match intent-%d (%s)", i, kw)
            return _successor(edges, gemini_id, f"intent-{i}")
    logger.warning("gemini_pick: no intent matched for %r", word)
    return _successor(edges, gemini_id, "intent-unknown")


def _default_session(phone: str) -> Dict[str, Any]:
    return {
        "phoneNumber": phone,
        "currentNodeId": None,
        "lastInteractionAt": None,
        "wabaOptIn": False,
        "variables": {},
        "continueFromNodeId": None,
        "afterInteractiveTarget": None,
        "entryStartNodeId": None,
        "activeFlowId": None,
        "flowDelayUntil": None,
        "flowDelayResumeNodeId": None,
    }


async def _persist_session(conversation_id: str, session: Dict[str, Any]) -> None:
    await supabase_execute(
        supabase.table("conversations")
        .update({"bot_flow_state": session})
        .eq("id", conversation_id)
    )
    await invalidate_cache_pattern(f"conversation:{conversation_id}")


async def try_run_playground_flow(
    conversation_id: str,
    conversation: Dict[str, Any],
    contact: Dict[str, Any],
    wa_message: Dict[str, Any],
    content_text: str,
    message_type: Optional[str],
    *,
    scheduled_delay_wake: bool = False,
    scheduled_flow_launch: bool = False,
    launch_entry_node_id: Optional[str] = None,
) -> bool:
    """
    Si un flux playground est publié pour le compte, exécute une étape du graphe.
    Retourne True si le message a été traité par le flux (ne pas appeler le bot Gemini classique).

    scheduled_delay_wake: appel interne quand le délai (delayNode) est échu — pas de message entrant.
    scheduled_flow_launch: lancement programmé depuis un nœud Entrée « campagne » — enchaîne le graphe
    sans message entrant (première étape = successeur du start).
    """
    from app.services.bot_service import (
        get_bot_profile,
        generate_bot_reply,
        generate_flow_gemini_keyword,
        generate_flow_gemini_text_reply,
    )
    from app.services.message_service import (
        send_message,
        send_interactive_message_with_storage,
        _escalate_to_human,
    )
    from app.services.whatsapp_api_service import (
        get_template_named_body_parameter_names,
        send_template_message,
    )
    from app.services.account_service import get_account_by_id
    from app.services.playground_flow_service import resolve_graph_for_conversation
    from app.core.config import settings

    account_id = conversation.get("account_id")
    if not account_id:
        return False

    profile = await get_bot_profile(account_id)
    raw_flow, resolved_flow_id = await resolve_graph_for_conversation(
        str(account_id), conversation, profile
    )
    if not raw_flow:
        logger.warning(
            "playground flow: aucun graphe (ni playground_flows pour cette conv/défaut, "
            "ni published_playground_flow). account_id=%s playground_flow_id=%s",
            account_id,
            conversation.get("playground_flow_id"),
        )
        return False
    nodes_list = raw_flow.get("nodes")
    if not nodes_list or not isinstance(nodes_list, list):
        logger.warning("playground flow: graphe sans liste nodes valide")
        return False

    nodes_by_id: Dict[str, dict] = {n["id"]: n for n in nodes_list if n.get("id")}
    edges: List[dict] = raw_flow.get("edges") or []

    if scheduled_flow_launch:
        lid = str(launch_entry_node_id or "").strip()
        if not lid or lid not in nodes_by_id:
            logger.warning(
                "playground flow scheduled launch: invalid entry node %r flow=%s",
                lid,
                resolved_flow_id,
            )
            return False
        sn = nodes_by_id[lid]
        if sn.get("type") != "start":
            logger.warning("playground flow scheduled launch: node %s is not start", lid)
            return False
        sdata = sn.get("data") or {}
        if sdata.get("triggerType") != "playground_audience":
            logger.warning(
                "playground flow scheduled launch: start %s must be trigger playground_audience",
                lid,
            )
            return False

    signals = extract_inbound_flow_signals(wa_message or {})
    inbound_text = (signals.get("text") or content_text or "").strip()
    button_id = signals.get("button_id")
    list_row_id = signals.get("list_row_id")

    phone = conversation.get("client_number") or ""
    if scheduled_flow_launch:
        session = _default_session(phone)
        session["entryStartNodeId"] = str(launch_entry_node_id).strip()
    else:
        raw_state = conversation.get("bot_flow_state")
        base_sess = _default_session(phone)
        if isinstance(raw_state, dict):
            session = {**base_sess, **raw_state}
            if not isinstance(session.get("variables"), dict):
                session["variables"] = {}
        else:
            session = base_sess
    session["phoneNumber"] = phone or session.get("phoneNumber") or ""
    variables = session["variables"]
    _apply_builtin_flow_variables(variables, contact, conversation)
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    session["lastInteractionAt"] = now_iso
    session["wabaOptIn"] = True

    if scheduled_delay_wake:
        if not session.get("flowDelayUntil") or not session.get("flowDelayResumeNodeId"):
            return False
        if not _consume_due_flow_delay(session, now_dt):
            return False
    elif not scheduled_flow_launch:
        until_pending = _parse_iso_utc(session.get("flowDelayUntil"))
        # Bloquer les messages tant qu'un delayNode est actif (pas de currentNodeId).
        # Avec interactiveNode ou sendTemplate (quick replies) + branche timeout,
        # currentNodeId est renseigné : il faut laisser passer la réponse pour annuler
        # le délai et poursuivre le flux.
        if (
            until_pending is not None
            and until_pending > now_dt
            and not session.get("currentNodeId")
        ):
            await _persist_session(conversation_id, session)
            return True
        _consume_due_flow_delay(session, now_dt)

    flow_key = str(resolved_flow_id) if resolved_flow_id else "legacy"
    prev_flow = session.get("activeFlowId")
    if prev_flow and str(prev_flow) != flow_key:
        session["variables"] = {}
        session["currentNodeId"] = None
        session["continueFromNodeId"] = None
        session["afterInteractiveTarget"] = None
        session["entryStartNodeId"] = None
        session["flowDelayUntil"] = None
        session["flowDelayResumeNodeId"] = None
    session["activeFlowId"] = flow_key

    awaiting = session.get("currentNodeId")
    after_i = session.get("afterInteractiveTarget")

    entry_start = session.get("entryStartNodeId")
    if not scheduled_flow_launch:
        if not entry_start or entry_start not in nodes_by_id:
            entry_start = _pick_start_node_id(nodes_by_id, inbound_text)
            if entry_start:
                session["entryStartNodeId"] = entry_start
    if not entry_start or entry_start not in nodes_by_id:
        logger.warning("playground flow: no matching start node for account %s", account_id)
        return False

    cursor: Optional[str] = None

    if awaiting and awaiting in nodes_by_id:
        wnode = nodes_by_id[awaiting]
        if wnode.get("type") == "interactiveNode":
            data = wnode.get("data") or {}
            vk = data.get("varKey") or "réponse"
            variables[vk] = inbound_text
            if button_id:
                variables[f"{vk}_button_id"] = button_id
            if list_row_id:
                variables[f"{vk}_list_id"] = list_row_id
            choices = data.get("choices") or []
            for i, ch in enumerate(choices):
                if not isinstance(ch, dict):
                    continue
                cid = (ch.get("id") or f"btn_{i}").strip()
                title = (ch.get("title") or "").strip()
                matched = (button_id and cid == button_id) or (
                    title and inbound_text.strip() == title
                )
                if matched and ch.get("saveToVariable"):
                    variables[str(ch["saveToVariable"])] = ch.get("saveValue", True)
            nxt = after_i or _successor(edges, awaiting)
            session["currentNodeId"] = None
            session["afterInteractiveTarget"] = None
            session["flowDelayUntil"] = None
            session["flowDelayResumeNodeId"] = None
            cursor = nxt
        elif wnode.get("type") == "sendTemplate" and _send_template_has_quick_replies(
            wnode.get("data") or {}
        ):
            data = wnode.get("data") or {}
            vk = data.get("varKey") or "réponse"
            variables[vk] = inbound_text
            if button_id:
                variables[f"{vk}_button_id"] = button_id
            quick_btns = [
                b for b in (data.get("quickReplyButtons") or []) if isinstance(b, dict)
            ]
            for i, btn in enumerate(quick_btns):
                bid = str(btn.get("id") or btn.get("payload") or "").strip()
                title = (btn.get("text") or btn.get("title") or "").strip()
                matched = (button_id and bid and bid == button_id) or (
                    title and inbound_text.strip() == title
                )
                if matched and btn.get("saveToVariable"):
                    variables[str(btn["saveToVariable"])] = btn.get("saveValue", True)
            nxt = after_i or _successor(edges, awaiting)
            session["currentNodeId"] = None
            session["afterInteractiveTarget"] = None
            session["flowDelayUntil"] = None
            session["flowDelayResumeNodeId"] = None
            cursor = nxt
        else:
            logger.warning("playground flow: awaiting on non-interactive %s", awaiting)
            session["currentNodeId"] = None
            session["afterInteractiveTarget"] = None
            cursor = session.get("continueFromNodeId") or _successor(edges, entry_start)
    else:
        cf = session.get("continueFromNodeId")
        if cf and cf in nodes_by_id:
            cursor = cf
        else:
            if not scheduled_flow_launch and not _start_allows_message(
                nodes_by_id[entry_start], inbound_text
            ):
                logger.warning(
                    "playground flow: message entrant refusé par le filtre du nœud start "
                    "(message_in / mot-clé). entry_start=%s inbound_preview=%r",
                    entry_start,
                    (inbound_text or "")[:80],
                )
                return False
            cursor = _successor(edges, entry_start)

    if not cursor or cursor not in nodes_by_id:
        await _persist_session(conversation_id, session)
        return True

    account = await get_account_by_id(account_id)
    if not account:
        return False
    phone_id = account.get("phone_number_id") or settings.WHATSAPP_PHONE_ID
    token = account.get("access_token") or settings.WHATSAPP_TOKEN

    max_steps = 40
    step = 0

    while cursor and cursor in nodes_by_id and step < max_steps:
        step += 1
        node = nodes_by_id[cursor]
        ntype = node.get("type")
        data = node.get("data") or {}
        logger.info(
            "playground flow step %d: node=%s type=%s  vars_keys=%s",
            step, cursor, ntype, list(variables.keys()),
        )

        if ntype == "sendText":
            body = _subst_vars(data.get("body") or "", variables)
            _warn_unresolved_vars(body, cursor)
            body = re.sub(r"\{\{[^}]+\}\}", "", body).strip()
            if not body:
                body = "Pouvez-vous préciser votre réponse ?"
            if body:
                await send_message(
                    {"conversation_id": conversation_id, "content": body},
                    skip_bot_trigger=True,
                )
            cursor = _successor(edges, cursor)
            continue

        if ntype == "sendTemplate":
            key = data.get("selectedTemplateKey") or ""
            name = data.get("templateName") or ""
            lang = data.get("templateLanguage") or "fr"
            if "||" in key:
                name, lang = key.split("||", 1)
            name = (name or "").strip()
            lang = (lang or "fr").strip() or "fr"
            if not name or not phone_id or not token:
                logger.warning("sendTemplate skip: missing name or whatsapp config")
                cursor = _successor(edges, cursor)
                continue
            var_vals = data.get("variableValues") or {}
            components: List[Dict[str, Any]] = []
            if isinstance(var_vals, dict) and var_vals:
                named_params: Optional[List[str]] = None
                waba_id = account.get("waba_id")
                if waba_id:
                    try:
                        named_params = await get_template_named_body_parameter_names(
                            str(waba_id),
                            token,
                            name,
                            lang,
                        )
                    except Exception as meta_exc:
                        logger.warning(
                            "sendTemplate: could not resolve named body params: %s",
                            meta_exc,
                        )
                params: List[Dict[str, Any]] = []
                if named_params:
                    for i, pname in enumerate(named_params):
                        raw = var_vals.get(pname)
                        if raw is None:
                            raw = var_vals.get(str(i + 1))
                        params.append(
                            {
                                "type": "text",
                                "parameter_name": pname,
                                "text": _subst_vars(str(raw or ""), variables),
                            }
                        )
                else:
                    keys = list(var_vals.keys())

                    def _sort_var_key(k: Any) -> Any:
                        ks = str(k)
                        if ks.isdigit():
                            return (0, int(ks))
                        return (1, ks)

                    for k in sorted(keys, key=_sort_var_key):
                        v = var_vals[k]
                        params.append(
                            {"type": "text", "text": _subst_vars(str(v or ""), variables)}
                        )
                if params:
                    components.append({"type": "body", "parameters": params})
            try:
                await send_template_message(
                    phone_id,
                    token,
                    conversation["client_number"],
                    name,
                    language_code=lang,
                    components=components or None,
                )
            except Exception as exc:
                logger.error("sendTemplate failed: %s", exc, exc_info=True)
                cursor = _successor(edges, cursor)
                continue
            if _send_template_has_quick_replies(data):
                after_tgt = _successor(edges, cursor)
                session["currentNodeId"] = cursor
                session["afterInteractiveTarget"] = after_tgt
                session["continueFromNodeId"] = after_tgt
                timeout_tgt = _successor(edges, cursor, "timeout")
                timeout_sec = _interactive_timeout_seconds(data)
                if timeout_tgt and timeout_sec is not None:
                    wake_at = datetime.now(timezone.utc) + timedelta(seconds=timeout_sec)
                    session["flowDelayUntil"] = wake_at.isoformat()
                    session["flowDelayResumeNodeId"] = timeout_tgt
                await _persist_session(conversation_id, session)
                return True
            cursor = _successor(edges, cursor)
            continue

        if ntype == "interactiveNode":
            body = _subst_vars(data.get("body") or "", variables)
            _warn_unresolved_vars(body, cursor)
            body = re.sub(r"\{\{[^}]+\}\}", "", body).strip()
            if not body:
                body = "Pouvez-vous préciser votre réponse ?"
            kind = data.get("uiKind") == "list" and "list" or "button"
            choices = [c for c in (data.get("choices") or []) if isinstance(c, dict)]
            if not body:
                cursor = _successor(edges, cursor)
                continue
            after_tgt = _successor(edges, cursor)
            if kind == "button":
                buttons: List[Dict[str, str]] = []
                for i, ch in enumerate(choices[:3]):
                    title = (ch.get("title") or f"Option {i+1}").strip()
                    if len(title) > 20:
                        title = title[:20]
                    bid = (ch.get("id") or f"btn_{i}").strip() or f"btn_{i}"
                    buttons.append({"id": bid, "title": title})
                if not buttons:
                    buttons.append({"id": "btn_a", "title": "OK"})
                action = {
                    "buttons": [
                        {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                        for b in buttons
                    ]
                }
                res = await send_interactive_message_with_storage(
                    conversation_id,
                    "button",
                    body,
                    action,
                    sent_via="flow",
                )
            else:
                rows = []
                for i, ch in enumerate(choices):
                    title = (ch.get("title") or f"Ligne {i+1}").strip()
                    if len(title) > 24:
                        title = title[:24]
                    rid = (ch.get("id") or f"row_{i}").strip() or f"row_{i}"
                    rows.append(
                        {
                            "id": rid,
                            "title": title,
                            "description": (ch.get("description") or "")[:72],
                        }
                    )
                list_btn = (data.get("listButtonText") or "Voir les options").strip() or "Voir les options"
                action = {
                    "button": list_btn[:20],
                    "sections": [{"title": "Options", "rows": rows[:10]}],
                }
                res = await send_interactive_message_with_storage(
                    conversation_id,
                    "list",
                    body,
                    action,
                    sent_via="flow",
                )
            if isinstance(res, dict) and res.get("error"):
                logger.error("interactive send failed: %s", res)
            session["currentNodeId"] = cursor
            session["afterInteractiveTarget"] = after_tgt
            session["continueFromNodeId"] = after_tgt
            timeout_tgt = _successor(edges, cursor, "timeout")
            timeout_sec = _interactive_timeout_seconds(data)
            if timeout_tgt and timeout_sec is not None:
                wake_at = datetime.now(timezone.utc) + timedelta(seconds=timeout_sec)
                session["flowDelayUntil"] = wake_at.isoformat()
                session["flowDelayResumeNodeId"] = timeout_tgt
            await _persist_session(conversation_id, session)
            return True

        if ntype == "routerNode":
            routes = data.get("routes") or []
            nxt = _router_pick(routes, edges, cursor, inbound_text, button_id, list_row_id)
            cursor = nxt
            continue

        if ntype == "gemini":
            intents = data.get("intents") or []
            if not intents:
                vk = data.get("varKey")
                sys_raw = (data.get("systemPrompt") or "").strip()
                if sys_raw:
                    reply = None
                    try:
                        sys_prompt = _subst_vars(sys_raw, variables)
                        hint = data.get("hint") or ""
                        node_kb = (data.get("knowledgeBase") or "").strip()
                        reply = await generate_flow_gemini_text_reply(
                            conversation_id,
                            account_id,
                            inbound_text,
                            sys_prompt,
                            hint if hint else None,
                            node_knowledge=node_kb if node_kb else None,
                        )
                    except BaseException as _gemini_exc:
                        logger.error(
                            "playground flow: gemini gen CRASHED for node %s: %s",
                            cursor, _gemini_exc,
                        )
                    if not reply:
                        logger.warning(
                            "playground flow: gemini text reply empty/None for node %s, "
                            "using fallback. inbound=%r  vars=%s",
                            cursor, (inbound_text or "")[:80],
                            list(variables.keys()),
                        )
                    if vk:
                        variables[vk] = reply if reply else (
                            "Je suis là pour vous aider. Pouvez-vous préciser votre réponse ?"
                        )
                        logger.info(
                            "playground flow: set var %r = %r (node %s)",
                            vk, (variables[vk] or "")[:60], cursor,
                        )
                    cursor = _successor(edges, cursor) or _successor(
                        edges, cursor, "intent-unknown"
                    )
                    continue
                reply = None
                try:
                    cname = contact.get("display_name") or contact.get("whatsapp_number")
                    reply = await generate_bot_reply(
                        conversation_id,
                        account_id,
                        inbound_text,
                        cname,
                    )
                except BaseException as _bot_exc:
                    logger.error(
                        "playground flow: bot reply CRASHED for node %s: %s",
                        cursor, _bot_exc,
                    )
                if vk:
                    variables[vk] = reply if reply else (
                        "Je suis là pour vous aider. Pouvez-vous préciser votre réponse ?"
                    )
                if reply:
                    await send_message(
                        {"conversation_id": conversation_id, "content": reply},
                        skip_bot_trigger=True,
                    )
                cursor = _successor(edges, cursor) or _successor(
                    edges, cursor, "intent-unknown"
                )
                continue
            sys_prompt = _subst_vars(data.get("systemPrompt") or "", variables)
            hint = data.get("hint") or ""
            keyword = None
            try:
                keyword = await generate_flow_gemini_keyword(
                    conversation_id,
                    account_id,
                    inbound_text,
                    sys_prompt,
                    hint if hint else None,
                )
            except BaseException as _kw_exc:
                logger.error(
                    "playground flow: gemini keyword CRASHED for node %s: %s",
                    cursor, _kw_exc,
                )
            logger.info(
                "playground flow: gemini keyword for node %s returned %r (inbound=%r)",
                cursor, keyword, (inbound_text or "")[:60],
            )
            if not keyword:
                cursor = (
                    _successor(edges, cursor, "intent-unknown")
                    or _successor(edges, cursor)
                )
                continue
            vk = data.get("varKey")
            if vk:
                variables[vk] = keyword
            nxt = _gemini_pick(intents, edges, cursor, keyword)
            cursor = nxt
            continue

        if ntype in ("handoff", "handoffNode"):
            from app.services.conversation_service import set_conversation_bot_mode

            note = (data.get("internalMessage") or "").strip() or "Handoff playground"
            await set_conversation_bot_mode(conversation_id, False)
            await _escalate_to_human(conversation, inbound_text or note)
            session["currentNodeId"] = None
            session["continueFromNodeId"] = _successor(edges, cursor)
            await _persist_session(conversation_id, session)
            return True

        if ntype == "delayNode":
            sec = _delay_node_seconds(data)
            if sec is None:
                cursor = _successor(edges, cursor)
                continue
            nxt = _successor(edges, cursor)
            if not nxt:
                await _persist_session(conversation_id, session)
                return True
            wake_at = datetime.now(timezone.utc) + timedelta(seconds=sec)
            session["flowDelayUntil"] = wake_at.isoformat()
            session["flowDelayResumeNodeId"] = nxt
            session["currentNodeId"] = None
            session["afterInteractiveTarget"] = None
            session["continueFromNodeId"] = None
            await _persist_session(conversation_id, session)
            return True

        if ntype in ("waitUntilNode", "timeWindowNode", "logicNode"):
            logger.info("playground flow: passthrough node type %s id=%s", ntype, cursor)
            if ntype == "logicNode" and (data.get("logicMode") or "si") == "si":
                cursor = _successor(edges, cursor, "true") or _successor(edges, cursor)
            else:
                cursor = _successor(edges, cursor)
            continue

        if ntype == "start":
            cursor = _successor(edges, cursor)
            continue

        logger.warning("playground flow: unknown node type %s id=%s", ntype, cursor)
        cursor = _successor(edges, cursor)

    session["currentNodeId"] = None
    session["continueFromNodeId"] = cursor
    session["afterInteractiveTarget"] = None
    await _persist_session(conversation_id, session)
    return True


async def fetch_due_playground_delay_conversation_ids() -> List[str]:
    """IDs des conversations playground avec délai (delayNode) échu."""
    now = datetime.now(timezone.utc)
    if get_pool():
        rows = await fetch_all(
            """
            SELECT id::text AS id
            FROM conversations
            WHERE bot_enabled = true
              AND bot_reply_mode = 'playground'
              AND bot_flow_state IS NOT NULL
              AND bot_flow_state ? 'flowDelayUntil'
              AND NULLIF(trim(bot_flow_state->>'flowDelayUntil'), '') IS NOT NULL
              AND (bot_flow_state->>'flowDelayUntil')::timestamptz <= $1::timestamptz
            """,
            now,
        )
        return [str(r["id"]) for r in rows]

    from app.core.db import supabase, supabase_execute

    res = await supabase_execute(
        supabase.table("conversations")
        .select("id, bot_flow_state")
        .eq("bot_enabled", True)
        .eq("bot_reply_mode", "playground")
    )
    out: List[str] = []
    for row in res.data or []:
        state = row.get("bot_flow_state") or {}
        if not isinstance(state, dict):
            continue
        raw = state.get("flowDelayUntil")
        if not raw:
            continue
        until = _parse_iso_utc(raw)
        if until is None:
            continue
        if until <= now:
            out.append(str(row["id"]))
    return out


async def periodic_playground_flow_delays() -> None:
    """
    Boucle asyncio : réveille les flux playground après un delayNode.
    Pas de Celery — s’appuie sur l’horloge du processus API (comme les autres tâches périodiques).
    """
    import asyncio

    from app.core.cache import invalidate_cache_pattern
    from app.services.conversation_service import get_conversation_by_id

    while True:
        try:
            await asyncio.sleep(45)
            ids = await fetch_due_playground_delay_conversation_ids()
            for cid in ids:
                try:
                    await invalidate_cache_pattern(f"conversation:{cid}")
                    conv = await get_conversation_by_id(cid)
                    if not conv or not conv.get("bot_enabled"):
                        continue
                    if str(conv.get("bot_reply_mode") or "").lower() != "playground":
                        continue
                    contact = conv.get("contacts") or {}
                    await try_run_playground_flow(
                        cid,
                        conv,
                        contact,
                        {},
                        "",
                        "text",
                        scheduled_delay_wake=True,
                    )
                except Exception as exc:
                    logger.error(
                        "playground flow delay wake failed for %s: %s",
                        cid,
                        exc,
                        exc_info=True,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("periodic_playground_flow_delays: %s", exc, exc_info=True)
