"""
Moteur nodal aligné sur le playground React Flow : session Supabase + exécution webhook.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.core.db import supabase, supabase_execute
from app.core.cache import invalidate_cache_pattern
from app.core.pg import execute, fetch_all, get_pool

logger = logging.getLogger("uvicorn.error").getChild("bot.flow")

_FLOW_DELAY_MAX_SECONDS = 86400.0 * 30


def _norm_reply_label(s: Any) -> str:
    """Normalise un libellé de bouton pour comparaison tolérante (casse, espaces, Unicode)."""
    if s is None:
        return ""
    t = unicodedata.normalize("NFC", str(s)).strip()
    t = " ".join(t.split())
    return t.casefold()


def _flow_button_matches(
    inbound_text: str,
    button_id: Optional[str],
    btn: Dict[str, Any],
) -> bool:
    """True si le clic/reply correspond au bouton du graphe ou Meta (id ou libellé)."""
    bid = str(btn.get("id") or btn.get("payload") or "").strip()
    title = (btn.get("text") or btn.get("title") or "").strip()
    if bid and button_id is not None and str(button_id).strip() == bid:
        return True
    if title and _norm_reply_label(inbound_text) == _norm_reply_label(title):
        return True
    if button_id is not None and title and _norm_reply_label(button_id) == _norm_reply_label(title):
        return True
    return False


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


def _parse_naive_local_until_to_utc(raw: str, tz_name: str) -> Optional[datetime]:
    """
    Interprète une date « datetime-local » (sans fuseau) selon timezoneNote, en UTC.
    Formats acceptés : YYYY-MM-DDTHH:mm ou YYYY-MM-DDTHH:mm:ss.
    """
    s = (raw or "").strip()
    if not s or len(s) < 16:
        return None
    if s[4] != "-" or s[10] != "T":
        return None
    try:
        part = s[:19] if len(s) >= 19 and s[16] == ":" else s[:16]
        local_naive = datetime.fromisoformat(part)
    except Exception:
        return None
    tz_key = (tz_name or "").strip() or "UTC"
    if tz_key.upper() == "UTC":
        return local_naive.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_key)
        return local_naive.replace(tzinfo=tz).astimezone(timezone.utc)
    except Exception:
        logger.warning("waitUntilNode: fuseau invalide %r, traité comme UTC", tz_name)
        return local_naive.replace(tzinfo=timezone.utc)


def _until_string_has_explicit_offset(u: str) -> bool:
    ul = (u or "").strip()
    if ul.endswith("Z"):
        return True
    if re.search(r"[+-]\d{2}(:?\d{2})?$", ul):
        return True
    return False


def _wait_until_deadline_utc(data: dict, variables: Dict[str, Any]) -> Optional[datetime]:
    """
    Instant cible en UTC pour waitUntilNode, ou None (passthrough sans attente planifiée).
    Priorité : untilFromVarKey → until (datetime-local naïf + fuseau, ou ISO avec offset).
    """
    vk = (data.get("untilFromVarKey") or "").strip()
    if vk:
        raw = variables.get(vk)
        if raw is None or raw == "":
            return None
        return _parse_iso_utc(str(raw))
    u = (data.get("until") or "").strip()
    if not u:
        return None
    tz_note = (data.get("timezoneNote") or "").strip()
    if not _until_string_has_explicit_offset(u) and re.match(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", u
    ):
        return _parse_naive_local_until_to_utc(u, tz_note)
    return _parse_iso_utc(u)


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
        elif isinstance(inter.get("button_reply"), dict):
            # Payload sans champ `type` au niveau interactive (certaines simulations / webhooks)
            br = inter.get("button_reply") or {}
            out["text"] = (br.get("title") or br.get("text") or "").strip()
            out["button_id"] = br.get("id")
        elif isinstance(inter.get("list_reply"), dict):
            lr = inter.get("list_reply") or {}
            out["text"] = (lr.get("title") or lr.get("text") or "").strip()
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


def _start_sort_key(item: Tuple[str, dict]) -> Tuple[int, int, str]:
    nid, n = item
    pri = (n.get("data") or {}).get("entryPriority")
    try:
        p = int(pri) if pri is not None and str(pri).strip() != "" else 0
    except (TypeError, ValueError):
        p = 0
    trigger = (n.get("data") or {}).get("triggerType")
    # À priorité égale : préférer « message entrant » à « campagne » (entrée contact explicite).
    kind_tie = 0 if trigger == "message_in" else 1
    return (-p, kind_tie, nid)


def _candidate_starts_for_inbound(
    nodes_by_id: Dict[str, dict], inbound_text: str
) -> List[Tuple[str, dict]]:
    """Nœuds start dont le filtre message (message_in / campagne) accepte le texte entrant."""
    starts: List[Tuple[str, dict]] = [
        (nid, n) for nid, n in nodes_by_id.items() if n.get("type") == "start"
    ]
    if not starts:
        return []
    return [(nid, n) for nid, n in starts if _start_allows_message(n, inbound_text)]


def _resolve_playground_audience_scope(data: dict) -> str:
    raw = (data.get("playgroundAudienceScope") or "").strip().lower()
    if raw in ("all", "group", "phones"):
        return raw
    if (data.get("audienceBroadcastGroupId") or "").strip():
        return "group"
    return "all"


async def _start_passes_audience_filter(data: dict, trigger: str, phone: str) -> bool:
    """Filtre « qui a ce scénario » pour message_in et playground_audience (groupes / liste / tout le monde)."""
    if trigger not in ("message_in", "playground_audience"):
        return True
    scope = _resolve_playground_audience_scope(data)
    if scope == "all":
        return True
    from app.services.conversation_service import normalize_phone_number
    from app.services.broadcast_service import phone_in_broadcast_group

    norm = normalize_phone_number(phone or "")
    if not norm:
        return False
    if scope == "phones":
        raw = data.get("playgroundAudiencePhones") or []
        if not isinstance(raw, list):
            return False
        for p in raw:
            if normalize_phone_number(str(p or "")) == norm:
                return True
        return False
    if scope == "group":
        gid = (data.get("audienceBroadcastGroupId") or "").strip()
        if not gid:
            return False
        return await phone_in_broadcast_group(gid, norm)
    return True


async def _pick_entry_start_node_id(
    nodes_by_id: Dict[str, dict],
    inbound_text: str,
    phone: str,
) -> Optional[str]:
    """Comme _pick_start_node_id + restriction audience (groupes / contacts) sur l’entrée."""
    allowed = _candidate_starts_for_inbound(nodes_by_id, inbound_text)
    if not allowed:
        return None
    filtered: List[Tuple[str, dict]] = []
    for nid, n in allowed:
        data = n.get("data") or {}
        tr = data.get("triggerType")
        if await _start_passes_audience_filter(data, str(tr or ""), phone):
            filtered.append((nid, n))
    if not filtered:
        return None
    filtered.sort(key=_start_sort_key)
    return filtered[0][0]


def _pick_start_node_id(nodes_by_id: Dict[str, dict], inbound_text: str) -> Optional[str]:
    """Plusieurs nœuds start : filtre message uniquement (tests / compat)."""
    allowed = _candidate_starts_for_inbound(nodes_by_id, inbound_text)
    if not allowed:
        return None
    allowed.sort(key=_start_sort_key)
    return allowed[0][0]


def _is_playground_audience_start_node(
    nodes_by_id: Dict[str, dict], node_id: Optional[str]
) -> bool:
    """Vrai si node_id est un nœud start « Campagne planifiée » (ne reçoit pas les messages contact)."""
    if not node_id or node_id not in nodes_by_id:
        return False
    n = nodes_by_id[node_id]
    if n.get("type") != "start":
        return False
    return (n.get("data") or {}).get("triggerType") == "playground_audience"


def _sanitize_stale_flow_session_pointers(
    session: Dict[str, Any], nodes_by_id: Dict[str, dict]
) -> None:
    """
    Après republication / import du graphe, les ids React peuvent changer alors que bot_flow_state
    référence encore d’anciens nœuds : le moteur ne « voit » plus l’attente (template, etc.) et peut
    refuser le message sur l’entrée audience ou le filtre mot-clé.
    """
    cur = session.get("currentNodeId")
    if cur and cur not in nodes_by_id:
        logger.warning(
            "playground flow: currentNodeId %r not in graph, clearing await state",
            cur,
        )
        session["currentNodeId"] = None
        session["afterInteractiveTarget"] = None
    aft = session.get("afterInteractiveTarget")
    if aft and aft not in nodes_by_id:
        session["afterInteractiveTarget"] = None
    cf = session.get("continueFromNodeId")
    if cf and cf not in nodes_by_id:
        logger.warning(
            "playground flow: continueFromNodeId %r not in graph, clearing",
            cf,
        )
        session["continueFromNodeId"] = None
    es = session.get("entryStartNodeId")
    if es and es not in nodes_by_id:
        logger.warning(
            "playground flow: entryStartNodeId %r not in graph, clearing",
            es,
        )
        session["entryStartNodeId"] = None
    resume = session.get("flowDelayResumeNodeId")
    if resume and resume not in nodes_by_id:
        logger.warning(
            "playground flow: flowDelayResumeNodeId %r not in graph, clearing delay",
            resume,
        )
        session["flowDelayUntil"] = None
        session["flowDelayResumeNodeId"] = None
    gcbn = session.get("geminiClarifyByNode")
    if isinstance(gcbn, dict):
        stale = [k for k in gcbn if k not in nodes_by_id]
        for k in stale:
            gcbn.pop(k, None)
        if stale:
            session["geminiClarifyByNode"] = gcbn


def _message_in_filter_matches(data: dict, inbound_text: str) -> bool:
    """Filtre messageMatch / messageKeyword (message_in et entrée campagne avec mêmes champs)."""
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


def _start_allows_message(start_node: dict, inbound_text: str) -> bool:
    data = start_node.get("data") or {}
    trigger = data.get("triggerType")
    # Entrée « Campagne planifiée » : l’éditeur duplique souvent messageMatch/keyword.
    # Avant, on refusait tout message contact → graphes « audience only » + any ne démarraient jamais.
    if trigger == "playground_audience":
        return _message_in_filter_matches(data, inbound_text)
    if trigger != "message_in":
        return True
    return _message_in_filter_matches(data, inbound_text)


def _router_pick(
    routes: List[dict],
    edges: List[dict],
    router_id: str,
    inbound_text: str,
    button_id: Optional[str],
    list_row_id: Optional[str],
) -> Optional[str]:
    text = (inbound_text or "").strip()
    text_norm = _norm_reply_label(text)
    bid_norm = _norm_reply_label(button_id) if button_id else ""
    for i, route in enumerate(routes or []):
        m = (route.get("match") or "").strip()
        if not m:
            continue
        m_norm = _norm_reply_label(m)
        rid = (route.get("buttonId") or route.get("quickReplyId") or "").strip()
        if button_id and (m == button_id or m_norm == bid_norm):
            return _successor(edges, router_id, f"route-{i}")
        if button_id and rid and _norm_reply_label(rid) == bid_norm:
            return _successor(edges, router_id, f"route-{i}")
        if list_row_id and m == list_row_id:
            return _successor(edges, router_id, f"route-{i}")
        if text == m or text.lower() == m.lower() or text_norm == m_norm:
            return _successor(edges, router_id, f"route-{i}")
    return _successor(edges, router_id, "escape")


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _flow_trace_append(
    flow_trace: Optional[List[Dict[str, Any]]],
    event: Dict[str, Any],
) -> None:
    if flow_trace is None:
        return
    flow_trace.append(event)


def _gemini_intent_token_fallback(user_norm: str, intents: List[dict]) -> Optional[int]:
    """
    Si le mot-clé « complet » renvoyé par Gemini ne matche pas, tente un match par
    mots du libellé d'intention (≥3 car.) présents dans le message utilisateur.
    Utile pour les intentions multi-mots (« LOUER SUV » vs « je veux louer »).
    """
    if not user_norm or not intents:
        return None
    for i, row in enumerate(intents or []):
        raw_kw = (row.get("keyword") or "").strip()
        if not raw_kw:
            continue
        for tok in re.findall(r"[A-Z0-9À-ÿ]+", _strip_accents(raw_kw.upper())):
            if len(tok) < 3:
                continue
            if tok in user_norm:
                return i
    return None


def _is_simple_greeting_only(text: str) -> bool:
    """Message très court du type seulement « bonjour » / « salut » (sans demande métier)."""
    t = (text or "").strip()
    if not t or len(t) > 56:
        return False
    tl = t.lower()
    m = re.match(
        r"^(bonjour|salut|hello|hi|hey|coucou|bonsoir|good morning|bonne journ[ée]e)\b",
        tl,
        re.I,
    )
    if not m:
        return False
    rest = tl[m.end() :].strip(" \t\n\r!.?…")
    return len(rest) < 2


def _cosine_similarity_vec(a: List[float], b: List[float]) -> float:
    """Similarité cosinus entre deux vecteurs (même dimension)."""
    import math

    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def _gemini_intent_embedding_match(
    inbound_text: str,
    intents: List[dict],
    threshold: float,
) -> Optional[int]:
    """
    Si le routage par mot-clé échoue, choisit l'intention dont le texte (keyword + label)
    est le plus proche sémantiquement du message (embeddings Gemini).
    """
    from app.services.qa_service import embed_text

    if not intents or not (inbound_text or "").strip():
        return None
    query = (inbound_text or "").strip()[:2000]
    qv = await embed_text(query)
    if not qv:
        return None
    best_i: Optional[int] = None
    best_sim = -1.0
    for i, row in enumerate(intents or []):
        if not isinstance(row, dict):
            continue
        kw = (row.get("keyword") or "").strip()
        lbl = (row.get("label") or "").strip()
        phrase = f"{kw} {lbl}".strip() or kw or lbl
        if not phrase:
            continue
        iv = await embed_text(phrase[:2000])
        if not iv:
            continue
        sim = _cosine_similarity_vec(qv, iv)
        if sim > best_sim:
            best_sim = sim
            best_i = i
    if best_i is None or best_sim < threshold:
        return None
    return best_i


def _gemini_pick(
    intents: List[dict],
    edges: List[dict],
    gemini_id: str,
    raw_keyword: Optional[str],
    inbound_text: str = "",
) -> Tuple[Optional[str], str, Optional[int]]:
    """
    Route le nœud Gemini vers la bonne sortie.
    Retourne (prochain_nœud, raison, index_intention_ou_None).
    raison ∈ matched | intent_unknown | empty_keyword.
    """
    word_raw = (raw_keyword or "").strip().upper()
    word = _strip_accents(word_raw)
    user_norm = _strip_accents((inbound_text or "").upper())
    logger.info(
        "gemini_pick: raw=%r  normalized=%r  intents=%s",
        word_raw, word,
        [r.get("keyword") for r in (intents or [])],
    )
    if not word:
        # Salutation minimale sans mot-clé : branche intent-0 (première intention = parcours principal),
        # pas intent-1 (souvent SAV ou secondaire dans les graphes).
        if len(intents or []) >= 1 and _is_simple_greeting_only(inbound_text):
            n = _successor(edges, gemini_id, "intent-0")
            if n:
                logger.info("gemini_pick: greeting only → intent-0 (fallback)")
                return (n, "matched", 0)
        return (_successor(edges, gemini_id, "intent-unknown"), "empty_keyword", None)
    for i, row in enumerate(intents or []):
        kw = _strip_accents((row.get("keyword") or "").strip().upper())
        if kw and kw in word:
            logger.info("gemini_pick: matched intent-%d (%s)", i, kw)
            return (_successor(edges, gemini_id, f"intent-{i}"), "matched", i)
    for i, row in enumerate(intents or []):
        kw = _strip_accents((row.get("keyword") or "").strip().upper())
        if kw and word.startswith(kw):
            logger.info("gemini_pick: startswith match intent-%d (%s)", i, kw)
            return (_successor(edges, gemini_id, f"intent-{i}"), "matched", i)
    # Mots-clés d’intention aussi cherchés dans le message utilisateur (ex. « louer » sans le mot anglais).
    for i, row in enumerate(intents or []):
        kw = _strip_accents((row.get("keyword") or "").strip().upper())
        if kw and kw in user_norm:
            logger.info("gemini_pick: user text matched intent-%d (%s)", i, kw)
            return (_successor(edges, gemini_id, f"intent-{i}"), "matched", i)
    ti = _gemini_intent_token_fallback(user_norm, intents or [])
    if ti is not None:
        logger.info("gemini_pick: token fallback intent-%d", ti)
        return (_successor(edges, gemini_id, f"intent-{ti}"), "matched", ti)
    if len(intents or []) >= 1 and _is_simple_greeting_only(inbound_text):
        n = _successor(edges, gemini_id, "intent-0")
        if n:
            logger.info("gemini_pick: no keyword match, greeting only → intent-0")
            return (n, "matched", 0)
    logger.warning("gemini_pick: no intent matched for %r", word)
    return (_successor(edges, gemini_id, "intent-unknown"), "intent_unknown", None)


def _build_gemini_clarify_system_prompt(
    intents: List[dict],
    router_system_prompt: str,
    tone: str,
) -> str:
    """Prompt pour une question de clarification quand le routage par mot-clé est ambigu."""
    labels: List[str] = []
    for row in intents or []:
        if not isinstance(row, dict):
            continue
        lbl = (row.get("label") or "").strip()
        kw = (row.get("keyword") or "").strip()
        if lbl and kw and lbl.lower() != kw.lower():
            labels.append(f"{lbl} ({kw})")
        elif lbl or kw:
            labels.append(lbl or kw)
    opt = ", ".join(labels) if labels else "les sujets proposés"
    base = (router_system_prompt or "").strip()
    tone_s = (tone or "").strip()
    parts = [
        "Tu es un assistant conversationnel. Le message du client est ambigu ou ne permet pas "
        "de choisir clairement une intention parmi les options possibles.",
        f"Options à départager : {opt}.",
    ]
    if base:
        parts.append(f"Contexte métier (rappel) : {base}")
    if tone_s:
        parts.append(f"Ton : {tone_s}")
    parts.append(
        "Réponds une seule phrase courte et naturelle pour demander une précision utile "
        "(sans inventer de faits, sans lister de mots-clés techniques)."
    )
    return "\n\n".join(parts)


def _get_var(variables: Dict[str, Any], name: str) -> Any:
    """Lookup with réponse ↔ reponse accent alias fallback."""
    val = variables.get(name)
    if val is not None:
        return val
    accent_prefix = "réponse"
    ascii_prefix = "reponse"
    if name.startswith(accent_prefix):
        alt = ascii_prefix + name[len(accent_prefix):]
        return variables.get(alt)
    if name.startswith(ascii_prefix):
        alt = accent_prefix + name[len(ascii_prefix):]
        return variables.get(alt)
    return None


def _evaluate_logic_condition(
    expression: str,
    variables: Dict[str, Any],
) -> bool:
    """
    Évalue une condition logique générée par le frontend playground.
    Formes supportées (combinables avec &&) :
      String(varKey ?? '').trim() === "value"
      String(varKey ?? '').includes("value")
      RegExp("pattern").test(String(varKey ?? ''))
    Retourne True si l'expression est considérée vraie, False sinon.
    """
    expr = (expression or "").strip()
    if not expr:
        return True

    parts = [p.strip() for p in re.split(r"\s*&&\s*", expr) if p.strip()]
    if not parts:
        return True

    _VAR_PAT = r"[\w.]+"

    for part in parts:
        clean = part.strip()
        if clean.startswith("(") and clean.endswith(")"):
            clean = clean[1:-1].strip()

        m_eq = re.search(
            r"""String\(\s*(""" + _VAR_PAT + r""")\s*\?\?.*?\)\.trim\(\)\s*===\s*["'](.+?)["']""",
            clean,
        )
        if m_eq:
            var_name = m_eq.group(1)
            expected = m_eq.group(2)
            actual = str(_get_var(variables, var_name) or "").strip()
            if actual != expected:
                return False
            continue

        m_inc = re.search(
            r"""String\(\s*(""" + _VAR_PAT + r""")\s*\?\?.*?\)\.includes\(\s*["'](.+?)["']\s*\)""",
            clean,
        )
        if m_inc:
            var_name = m_inc.group(1)
            expected = m_inc.group(2)
            actual = str(_get_var(variables, var_name) or "")
            if expected not in actual:
                return False
            continue

        m_re = re.search(
            r"""RegExp\(\s*["'](.+?)["']\s*\)\.test\(\s*String\(\s*(""" + _VAR_PAT + r""")""",
            clean,
        )
        if m_re:
            pattern = m_re.group(1)
            var_name = m_re.group(2)
            actual = str(_get_var(variables, var_name) or "")
            try:
                if not re.search(pattern, actual):
                    return False
            except re.error:
                return False
            continue

        m_simple_eq = re.match(
            r"""^(""" + _VAR_PAT + r""")\s*===?\s*["'](.+?)["']$""",
            clean,
        )
        if m_simple_eq:
            var_name = m_simple_eq.group(1)
            expected = m_simple_eq.group(2)
            actual = str(_get_var(variables, var_name) or "").strip()
            if actual != expected:
                return False
            continue

        logger.warning(
            "logicNode: unrecognised condition fragment %r - treating as true",
            clean[:120],
        )

    return True


def _is_inside_time_window(data: dict) -> bool:
    """
    Vérifie si l'heure courante (Europe/Paris par défaut) est dans la plage horaire.
    """
    active_days = data.get("activeDays") or ["1", "2", "3", "4", "5"]
    start_time_str = data.get("startTime") or "09:00"
    end_time_str = data.get("endTime") or "18:00"

    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

    tz_note = (data.get("timezoneNote") or "").strip()
    tz_name = tz_note if tz_note else "Europe/Paris"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Paris")

    now = datetime.now(tz)
    day_str = str(now.isoweekday() % 7)
    if day_str not in active_days:
        return False

    try:
        sh, sm = (start_time_str.split(":") + ["0"])[:2]
        eh, em = (end_time_str.split(":") + ["0"])[:2]
        start_minutes = int(sh) * 60 + int(sm)
        end_minutes = int(eh) * 60 + int(em)
    except (ValueError, TypeError):
        return True

    current_minutes = now.hour * 60 + now.minute
    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes


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
        "geminiClarifyByNode": {},
    }


def _should_pause_after_sendtext_for_successor(successor_type: str) -> bool:
    """
    Après un sendText, attendre le prochain message utilisateur avant le nœud suivant
    (comportement type WhatsApp : une salve de messages auto sans saisie, puis pause).
    Les types listés enchaînent sans attendre une nouvelle entrée utilisateur.
    """
    t = (successor_type or "").lower()
    chain_without_user = {
        "sendtext",
        "sendtemplate",
        "delaynode",
        "logicnode",
        "waituntilnode",
        "timewindownode",
        "handoffnode",
        "handoff",
    }
    if t in chain_without_user:
        return False
    return True


def _normalize_flow_session_key(resolved_flow_id: Optional[Any]) -> str:
    """Clé stable pour activeFlowId (évite un reset si l’UUID diffère seulement par la casse)."""
    if resolved_flow_id is None:
        return "legacy"
    s = str(resolved_flow_id).strip()
    if not s:
        return "legacy"
    if s.lower() == "legacy":
        return "legacy"
    return s.lower()


async def _persist_session(conversation_id: str, session: Dict[str, Any]) -> None:
    """
    Quand le pool Postgres est actif, les lectures (get_conversation_by_id_fresh) passent par PG.
    Persister uniquement via Supabase REST ferait diverger l’état lu par le moteur de ce que
    l’on voit dans le dashboard Supabase - d’où écriture PG + invalidation cache.
    """
    if get_pool():
        await execute(
            """
            UPDATE conversations
            SET bot_flow_state = $2::jsonb
            WHERE id = $1::uuid
            """,
            conversation_id,
            json.dumps(session, default=str),
        )
    else:
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
    flow_trace: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Si un flux playground est publié pour le compte, exécute une étape du graphe.
    Retourne True si le message a été traité par le flux (ne pas appeler le bot Gemini classique).

    scheduled_delay_wake: appel interne quand le délai (delayNode) est échu - pas de message entrant.
    scheduled_flow_launch: lancement programmé depuis un nœud Entrée « campagne » - enchaîne le graphe
    sans message entrant (première étape = successeur du start).
    flow_trace: si fourni (liste mutable), y ajoute des événements pour débogage (bac à sable UI).
    """
    from app.services.bot_service import (
        get_bot_profile,
        generate_bot_reply,
        generate_flow_gemini_keyword,
        generate_flow_gemini_text_reply,
        conversation_transcript_for_flow_variables,
    )
    from app.services.message_service import (
        send_message,
        send_interactive_message_with_storage,
        persist_sandbox_flow_template_outbound,
        _escalate_to_human,
    )
    from app.services.whatsapp_api_service import (
        get_template_named_body_parameter_names,
        send_template_message,
    )
    from app.services.account_service import get_account_by_id
    from app.services.conversation_service import SANDBOX_PLAYGROUND_CLIENT_NUMBER
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
        if isinstance(raw_state, str) and raw_state.strip():
            try:
                raw_state = json.loads(raw_state)
            except Exception:
                logger.warning(
                    "playground flow: bot_flow_state non JSON, état ignoré (preview=%r)",
                    raw_state[:120] if len(raw_state) > 120 else raw_state,
                )
                raw_state = None
        if isinstance(raw_state, dict):
            session = {**base_sess, **raw_state}
            if not isinstance(session.get("variables"), dict):
                session["variables"] = {}
        else:
            session = base_sess
    session["phoneNumber"] = phone or session.get("phoneNumber") or ""
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

    flow_key = _normalize_flow_session_key(resolved_flow_id)
    prev_raw = session.get("activeFlowId")
    if prev_raw is not None and str(prev_raw).strip() != "":
        if _normalize_flow_session_key(prev_raw) != flow_key:
            session["variables"] = {}
            session["flowLastUserMessages"] = []
            session["flowStructuredNotes"] = []
            session["currentNodeId"] = None
            session["continueFromNodeId"] = None
            session["afterInteractiveTarget"] = None
            session["entryStartNodeId"] = None
            session["flowDelayUntil"] = None
            session["flowDelayResumeNodeId"] = None
            session["geminiClarifyByNode"] = {}
    session["activeFlowId"] = flow_key
    _sanitize_stale_flow_session_pointers(session, nodes_by_id)

    variables = session["variables"]
    _apply_builtin_flow_variables(variables, contact, conversation)
    if not scheduled_flow_launch and not scheduled_delay_wake:
        lum = session.setdefault("flowLastUserMessages", [])
        if not isinstance(lum, list):
            lum = []
            session["flowLastUserMessages"] = lum
        if inbound_text:
            lum.append((inbound_text or "")[:2000])
            session["flowLastUserMessages"] = lum[-30:]
    try:
        variables["flow_recent_user_text"] = await conversation_transcript_for_flow_variables(
            conversation_id
        )
    except Exception as exc:
        logger.warning(
            "playground flow: flow_recent_user_text depuis la DB impossible (%s), fallback session",
            exc,
        )
        variables["flow_recent_user_text"] = " | ".join(
            str(x) for x in (session.get("flowLastUserMessages") or []) if x
        )
    sn_prev = session.get("flowStructuredNotes")
    if isinstance(sn_prev, list) and sn_prev:
        variables["flow_structured_notes"] = "\n".join(
            str(x) for x in sn_prev[-25:]
        )
    else:
        variables["flow_structured_notes"] = ""

    awaiting = session.get("currentNodeId")
    after_i = session.get("afterInteractiveTarget")

    entry_start = session.get("entryStartNodeId")
    if not scheduled_flow_launch:
        # Après simulate-campaign-launch, entryStartNodeId pointe vers le start « audience ».
        # Les messages contact suivants doivent repasser par un start « message_in », sinon
        # _start_allows_message refusera tout et le mode playground ne renverra rien (pas de Gemini).
        if not entry_start or entry_start not in nodes_by_id:
            entry_start = await _pick_entry_start_node_id(
                nodes_by_id, inbound_text, phone
            )
            if entry_start:
                session["entryStartNodeId"] = entry_start
        elif (
            _is_playground_audience_start_node(nodes_by_id, entry_start)
            and not awaiting
        ):
            picked = await _pick_entry_start_node_id(
                nodes_by_id, inbound_text, phone
            )
            if picked:
                entry_start = picked
                session["entryStartNodeId"] = entry_start
            else:
                entry_start = None
                session["entryStartNodeId"] = None
    if not entry_start or entry_start not in nodes_by_id:
        logger.warning("playground flow: no matching start node for account %s", account_id)
        _flow_trace_append(
            flow_trace,
            {"event": "error", "reason": "no_matching_start"},
        )
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
                matched = _flow_button_matches(
                    inbound_text,
                    button_id,
                    {"id": cid, "text": title, "title": title},
                )
                if matched and ch.get("saveToVariable"):
                    variables[str(ch["saveToVariable"])] = ch.get("saveValue", True)
            nxt = after_i or _successor(edges, awaiting)
            session["currentNodeId"] = None
            session["afterInteractiveTarget"] = None
            session["flowDelayUntil"] = None
            session["flowDelayResumeNodeId"] = None
            cursor = nxt
        elif wnode.get("type") == "sendTemplate":
            data = wnode.get("data") or {}
            if not _send_template_has_quick_replies(data):
                logger.info(
                    "playground flow: reply while awaiting sendTemplate id=%s but quickReplyButtons "
                    "empty in graph - advancing anyway (meta UI can still show buttons)",
                    awaiting,
                )
            vk = data.get("varKey") or "réponse"
            variables[vk] = inbound_text
            if button_id:
                variables[f"{vk}_button_id"] = button_id
            quick_btns = [
                b for b in (data.get("quickReplyButtons") or []) if isinstance(b, dict)
            ]
            for btn in quick_btns:
                if _flow_button_matches(inbound_text, button_id, btn) and btn.get(
                    "saveToVariable"
                ):
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
            session["continueFromNodeId"] = None
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
        _flow_trace_append(
            flow_trace,
            {"event": "done", "reason": "no_cursor"},
        )
        await _persist_session(conversation_id, session)
        return True

    account = await get_account_by_id(account_id)
    if not account:
        return False
    phone_id = account.get("phone_number_id") or settings.WHATSAPP_PHONE_ID
    token = account.get("access_token") or settings.WHATSAPP_TOKEN

    max_steps = 40
    step = 0

    _flow_trace_append(
        flow_trace,
        {"event": "run", "entry": entry_start, "cursor": cursor},
    )

    while cursor and cursor in nodes_by_id and step < max_steps:
        step += 1
        node = nodes_by_id[cursor]
        ntype = node.get("type")
        data = node.get("data") or {}
        _flow_trace_append(
            flow_trace,
            {"event": "visit", "step": step, "nodeId": cursor, "nodeType": ntype},
        )
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
            nxt = _successor(edges, cursor)
            if not nxt or nxt not in nodes_by_id:
                session["continueFromNodeId"] = None
                await _persist_session(conversation_id, session)
                return True
            next_ntype = nodes_by_id[nxt].get("type") or ""
            if _should_pause_after_sendtext_for_successor(next_ntype):
                session["continueFromNodeId"] = nxt
                session["currentNodeId"] = None
                await _persist_session(conversation_id, session)
                return True
            cursor = nxt
            continue

        if ntype == "sendTemplate":
            key = data.get("selectedTemplateKey") or ""
            name = data.get("templateName") or ""
            lang = data.get("templateLanguage") or "fr"
            if "||" in key:
                name, lang = key.split("||", 1)
            name = (name or "").strip()
            lang = (lang or "fr").strip() or "fr"
            is_sandbox_conv = (
                str(conversation.get("client_number") or "").strip()
                == SANDBOX_PLAYGROUND_CLIENT_NUMBER
            )
            if not name:
                logger.warning("sendTemplate skip: missing template name")
                cursor = _successor(edges, cursor)
                continue
            if not is_sandbox_conv and (not phone_id or not token):
                logger.warning("sendTemplate skip: missing name or whatsapp config")
                cursor = _successor(edges, cursor)
                continue
            var_vals = data.get("variableValues") or {}
            components: List[Dict[str, Any]] = []
            if isinstance(var_vals, dict) and var_vals:
                named_params: Optional[List[str]] = None
                # Bac à sable : ne pas appeler Meta pour résoudre les paramètres nommés
                if not is_sandbox_conv:
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
                if is_sandbox_conv:
                    await persist_sandbox_flow_template_outbound(
                        conversation_id,
                        name,
                        lang,
                        components or None,
                        quick_reply_buttons=data.get("quickReplyButtons"),
                    )
                else:
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
            _flow_trace_append(
                flow_trace,
                {"event": "router", "nodeId": cursor, "next": nxt},
            )
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
            recent_ctx = str(variables.get("flow_recent_user_text") or "").strip()
            try:
                keyword = await generate_flow_gemini_keyword(
                    conversation_id,
                    account_id,
                    inbound_text,
                    sys_prompt,
                    hint if hint else None,
                    recent_user_context=recent_ctx if recent_ctx else None,
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
            nxt, reason, matched_idx = _gemini_pick(
                intents, edges, cursor, keyword, inbound_text
            )
            route_via_embedding = False
            try:
                emb_thr = float(data.get("embeddingSimilarityThreshold", 0.62) or 0.62)
            except (TypeError, ValueError):
                emb_thr = 0.62
            emb_thr = max(0.35, min(0.95, emb_thr))
            if (
                reason in ("intent_unknown", "empty_keyword")
                and data.get("useEmbeddingSimilarity")
                and intents
            ):
                try:
                    emb_i = await _gemini_intent_embedding_match(
                        inbound_text, intents, emb_thr
                    )
                except BaseException as _emb_exc:
                    logger.warning(
                        "playground flow: embedding intent match failed node %s: %s",
                        cursor,
                        _emb_exc,
                    )
                    emb_i = None
                if emb_i is not None:
                    nxt = _successor(edges, cursor, f"intent-{emb_i}")
                    reason = "matched"
                    matched_idx = emb_i
                    route_via_embedding = True
                    _flow_trace_append(
                        flow_trace,
                        {
                            "event": "gemini_embedding_match",
                            "nodeId": cursor,
                            "intentIndex": emb_i,
                            "threshold": emb_thr,
                            "next": nxt,
                        },
                    )

            _flow_trace_append(
                flow_trace,
                {
                    "event": "gemini_route",
                    "nodeId": cursor,
                    "keyword": (keyword or "")[:200],
                    "reason": reason,
                    "intentIndex": matched_idx,
                    "next": nxt,
                },
            )

            clarify_on = data.get("clarifyOnUnknown", True)
            try:
                max_clarify = int(data.get("maxClarifyAttempts", 3) or 3)
            except (TypeError, ValueError):
                max_clarify = 3
            max_clarify = max(0, min(max_clarify, 5))

            gcbn = session.get("geminiClarifyByNode")
            if not isinstance(gcbn, dict):
                gcbn = {}
            strikes = int(gcbn.get(cursor) or 0)

            want_clarify = (
                clarify_on
                and reason in ("intent_unknown", "empty_keyword")
                and strikes < max_clarify
            )

            if want_clarify:
                clarify_sys = _build_gemini_clarify_system_prompt(
                    intents,
                    sys_prompt,
                    (data.get("toneInstructions") or "").strip(),
                )
                reply = None
                try:
                    node_kb = (data.get("knowledgeBase") or "").strip()
                    reply = await generate_flow_gemini_text_reply(
                        conversation_id,
                        account_id,
                        inbound_text,
                        clarify_sys,
                        hint if hint else None,
                        node_knowledge=node_kb if node_kb else None,
                    )
                except BaseException as _clar_exc:
                    logger.error(
                        "playground flow: gemini clarify CRASHED for node %s: %s",
                        cursor, _clar_exc,
                    )
                reply = (reply or "").strip()
                if reply:
                    await send_message(
                        {"conversation_id": conversation_id, "content": reply},
                        skip_bot_trigger=True,
                    )
                    vk_cl = data.get("varKey")
                    if vk_cl:
                        variables[vk_cl] = reply
                    gcbn[cursor] = strikes + 1
                    session["geminiClarifyByNode"] = gcbn
                    session["continueFromNodeId"] = cursor
                    session["currentNodeId"] = None
                    _flow_trace_append(
                        flow_trace,
                        {
                            "event": "gemini_clarify",
                            "nodeId": cursor,
                            "strike": strikes + 1,
                            "max": max_clarify,
                        },
                    )
                    await _persist_session(conversation_id, session)
                    return True

            if reason == "matched":
                gcbn.pop(cursor, None)
                session["geminiClarifyByNode"] = gcbn

            if (
                reason == "matched"
                and matched_idx is not None
                and data.get("structuredMemory", True) is not False
                and matched_idx < len(intents)
            ):
                row_m = intents[matched_idx]
                if isinstance(row_m, dict):
                    lbl = (row_m.get("label") or row_m.get("keyword") or "?").strip()
                    suf = " (sémantique)" if route_via_embedding else ""
                    line = f"{lbl}{suf}: {(inbound_text or '')[:160]}"
                    sn = session.setdefault("flowStructuredNotes", [])
                    if not isinstance(sn, list):
                        sn = []
                    sn.append(line)
                    session["flowStructuredNotes"] = sn[-25:]
                    variables["flow_structured_notes"] = "\n".join(
                        str(x) for x in session["flowStructuredNotes"]
                    )

            vk = data.get("varKey")
            if vk:
                if reason == "matched":
                    if route_via_embedding:
                        variables[vk] = (inbound_text or "").strip()[:2000]
                    else:
                        variables[vk] = (
                            (keyword or "").strip()
                            or (inbound_text or "").strip()
                        )
                else:
                    variables[vk] = (keyword or "").strip()

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

        if ntype == "logicNode":
            mode = data.get("logicMode") or "si"
            if mode == "si":
                cond_result = _evaluate_logic_condition(
                    data.get("condition") or "", variables,
                )
                handle = "true" if cond_result else "false"
                logger.info(
                    "playground flow: logicNode %s condition=%r → %s  vars=%s",
                    cursor,
                    (data.get("condition") or "")[:120],
                    handle,
                    {k: str(v)[:40] for k, v in variables.items()},
                )
                cursor = _successor(edges, cursor, handle) or _successor(edges, cursor)
            else:
                cursor = _successor(edges, cursor)
            continue

        if ntype == "timeWindowNode":
            inside = _is_inside_time_window(data)
            handle = "inside" if inside else "outside"
            logger.info(
                "playground flow: timeWindowNode %s → %s (days=%s %s–%s)",
                cursor, handle,
                data.get("activeDays"), data.get("startTime"), data.get("endTime"),
            )
            nxt_tw = _successor(edges, cursor, handle)
            if nxt_tw is None:
                outs = _edges_from(edges, cursor)
                nulls = [(t, h) for t, h in outs if h is None or h == ""]
                if len(nulls) >= 2:
                    # Graphes sans sourceHandle inside/outside : ordre attendu
                    # [0] = hors plage / message fermé, [1] = dans plage / flux normal
                    nxt_tw = nulls[1][0] if inside else nulls[0][0]
                else:
                    nxt_tw = _successor(edges, cursor)
            cursor = nxt_tw
            continue

        if ntype == "waitUntilNode":
            wake = _wait_until_deadline_utc(data, variables)
            if wake is None:
                logger.info(
                    "playground flow: waitUntilNode %s passthrough (pas de date résoluble)",
                    cursor,
                )
                cursor = _successor(edges, cursor)
                continue
            if wake <= now_dt:
                logger.info(
                    "playground flow: waitUntilNode %s échéance dépassée → enchaînement",
                    cursor,
                )
                cursor = _successor(edges, cursor)
                continue
            nxt = _successor(edges, cursor)
            if not nxt:
                await _persist_session(conversation_id, session)
                return True
            session["flowDelayUntil"] = wake.isoformat()
            session["flowDelayResumeNodeId"] = nxt
            session["currentNodeId"] = None
            session["afterInteractiveTarget"] = None
            session["continueFromNodeId"] = None
            await _persist_session(conversation_id, session)
            logger.info(
                "playground flow: waitUntilNode %s pause jusqu’à %s",
                cursor,
                wake.isoformat(),
            )
            return True

        if ntype == "start":
            cursor = _successor(edges, cursor)
            continue

        logger.warning("playground flow: unknown node type %s id=%s", ntype, cursor)
        cursor = _successor(edges, cursor)

    _flow_trace_append(
        flow_trace,
        {"event": "pause", "continueFrom": cursor, "reason": "loop_end"},
    )
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
    Pas de Celery - s’appuie sur l’horloge du processus API (comme les autres tâches périodiques).
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
