"""Chat Axelia - Gemini avec routage fast / pro (évaluation de difficulté).

Avec périmètre compte WABA : mêmes outils (skills) que l’assistant Playground
(templates Meta, groupes de diffusion).
"""
from __future__ import annotations

import asyncio
import base64
import collections
import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
)

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
    AxeliaPendingAttachment,
    AxeliaSkillsRuntime,
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
    "tu attends une confirmation explicite dans l’interface ; tu respectes le périmètre décrit "
    "dans le bloc « CONTEXTE PÉRIMÈTRE CRM » (ligne unique ou ensemble des lignes accessibles)."
)

_AXEL_META_HINT = """RAPPEL META / WHATSAPP (concis) :
- Fenêtre 24 h après le dernier message client : messages libres ; hors fenêtre, template approuvé requis pour le premier envoi entreprise→client.
- Templates : catégories MARKETING / UTILITY, variables {{1}}, {{first_name}}, etc., statuts APPROVED / PENDING / REJECTED.
"""

_FRENCH_WEEKDAYS = (
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)
_FRENCH_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def _today_anchor_prompt(now: Optional[datetime] = None) -> str:
    """Bloc à injecter dans le prompt système pour ancrer le modèle sur la date du jour.

    Sans ce bloc, Gemini interprète « cette semaine » / « le mois dernier » à partir de
    sa date d'entraînement (typiquement 2024) - ce qui produit des plages factuellement
    fausses passées à ``search_inbox_messages``.
    """
    n = now or datetime.now(timezone.utc)
    iso_today = n.strftime("%Y-%m-%d")
    weekday = _FRENCH_WEEKDAYS[n.weekday()]
    month = _FRENCH_MONTHS[n.month - 1]
    iso_week_year, iso_week_num, _ = n.isocalendar()
    return (
        "\n\n=== DATE COURANTE (côté serveur, autoritaire) ===\n"
        f"Aujourd'hui : {weekday} {n.day} {month} {n.year} "
        f"(date ISO : {iso_today}, semaine ISO S{iso_week_num:02d}-{iso_week_year}, fuseau UTC).\n"
        "Toute formulation relative comme « cette semaine », « le mois dernier », « hier », "
        "« les 30 derniers jours », « le trimestre en cours » DOIT être calculée à partir "
        "de cette date - jamais à partir de ta connaissance d'entraînement.\n"
        "Quand tu construis une plage `since` / `until` pour `search_inbox_messages` "
        "(ou tout autre filtre temporel), déduis-la explicitement de la date ci-dessus "
        "et **vérifie l'année** : si tu écris une année antérieure à celle indiquée ici, "
        "c'est une erreur.\n"
        "=== FIN DATE COURANTE ===\n"
    )


def _compose_axelia_system_text(perimeter_extra: str = "") -> str:
    """Préfixe systématique pour le prompt système Axelia (base + ancrage date)."""
    return _AXELIA_SYSTEM_PROMPT + _today_anchor_prompt() + (perimeter_extra or "")

_AXELIA_SECTOR_FOCUS: Dict[str, str] = {
    "general": "",
    "templates": (
        "PRIORITÉ SECTEUR : TEMPLATES META - utilise proactivement list_templates et au besoin "
        "get_template_status ; propose create_template (avec confirmation utilisateur avant envoi Meta) si un template manque."
    ),
    "broadcast": (
        "PRIORITÉ SECTEUR : DIFFUSION / AUDIENCES - utilise list_broadcast_groups pour lister les groupes "
        "et leur effectif lorsque tu parles de ciblage, campagnes ou envois de masse."
    ),
    "writing": (
        "PRIORITÉ SECTEUR : RÉDACTION WHATSAPP - formulations courtes, claires, conformes Meta ; précise tutoiement/vouvoiement si utile."
    ),
    "flows": (
        "PRIORITÉ SECTEUR : PARCOURS & AUTOMATION - explique fenêtre 24h, types de nœuds (Gemini avec intents, routeur, sendTemplate vs session), "
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

# ---------------------------------------------------------------------------
# Budget dynamique de la boucle skills (rounds + tokens cumulés) - remplace l'ancien
# `_MAX_SKILL_ROUNDS = 4` figé. Permet aux requêtes lourdes (résumé multi-comptes…)
# de continuer si elles sont productives, et à l'inverse de couper plus tôt si le
# coût explose.
# ---------------------------------------------------------------------------
_MAX_SKILL_ROUNDS_HARD = 8
_MAX_SKILL_TOKENS_BUDGET = 60_000  # tokens cumulés (input + output) avant de stopper la boucle
_MAX_SKILL_ROUNDS_NO_PROGRESS = 2  # rounds consécutifs sans nouveau skill exécuté

# Résumé d'historique : au-delà de ce seuil de tours, les plus anciens sont remplacés
# par un résumé compact (1 appel flash supplémentaire, en best-effort).
_HISTORY_SUMMARY_TRIGGER_TURNS = 32
_HISTORY_SUMMARY_KEEP_RECENT = 16
_HISTORY_SUMMARY_MAX_CHARS = 1800

# Pièces jointes inline acceptées par Gemini (extension côté Axelia).
# Note : on garde une liste fermée ; tout fichier hors liste est rejeté côté API.
_INLINE_MIME_PREFIXES = ("image/",)
_INLINE_MIME_EXACT = {"application/pdf"}

# Base64 « propre » : seuls A-Za-z0-9+/= sont valides après nettoyage.
_BASE64_CLEAN_RE = re.compile(r"[\s\r\n\t]+")
_BASE64_ALPHABET_RE = re.compile(r"[A-Za-z0-9+/]")


def _decode_attachment_b64(b64: str) -> bytes:
    """Décode une chaîne base64 envoyée par le frontend en tolérant :
    - les data-URL (`data:image/png;base64,...`) - on ne garde que le suffixe ;
    - les espaces / retours chariot insérés (rare mais on l'a vu en prod) ;
    - le padding manquant (on l'ajoute jusqu'au multiple de 4).

    Lève ``ValueError("attachment_invalid_base64")`` si la chaîne reste invalide
    une fois nettoyée - utilisé pour mapper côté frontend l'erreur lisible.
    """
    if not isinstance(b64, str) or not b64:
        raise ValueError("attachment_invalid_base64")
    s = b64.strip()
    if s.startswith("data:") and ";base64," in s:
        s = s.split(";base64,", 1)[1]
    s = _BASE64_CLEAN_RE.sub("", s)
    if not s:
        raise ValueError("attachment_invalid_base64")
    # Pré-check : s'il ne reste plus aucun caractère du jeu base64 standard, c'est
    # forcément invalide (sinon b64decode(validate=False) strippe silencieusement et
    # renvoie b"" - on perdrait l'erreur).
    if not _BASE64_ALPHABET_RE.search(s):
        raise ValueError("attachment_invalid_base64")
    pad = (-len(s)) % 4
    if pad:
        s = s + ("=" * pad)
    try:
        decoded = base64.b64decode(s, validate=False)
    except Exception as exc:
        raise ValueError("attachment_invalid_base64") from exc
    if not decoded:
        raise ValueError("attachment_invalid_base64")
    return decoded


def _inline_mime_supported(mime: str) -> bool:
    m = (mime or "").strip().lower()
    if not m:
        return False
    if any(m.startswith(p) for p in _INLINE_MIME_PREFIXES):
        return True
    return m in _INLINE_MIME_EXACT


# ---------------------------------------------------------------------------
# Court-circuit du classifieur de difficulté (économie de latence + tokens)
# ---------------------------------------------------------------------------

_FAST_PATH_MAX_LEN = 70
_FAST_PATH_PHRASES = {
    "merci", "thanks", "thx", "ok", "okay", "ok merci", "super",
    "parfait", "salut", "bonjour", "bonsoir", "hello", "hi",
    "à plus", "ciao", "oui", "non", "yes", "no", "d'accord", "daccord",
    "à toi", "stp", "svp", "cool", "génial",
}

# Mots-clés qui indiquent que la requête mérite probablement le pro / le skill loop.
_TOOL_HINT_TOKENS = (
    "template", "templates", "diffusion", "campagne", "groupe", "audience",
    "inbox", "résum", "resum", "contact", "discussion", "conversation",
    "envoyer", "envoy", "meta", "ligne", "compte", "blocage", "bloque",
    "broadcast", "inbox", "client", "facture", "automation", "parcours",
    "json", "schema", "regex", "formule", "script", "code",
)


def _maybe_difficulty_shortcut(messages: List[Dict[str, Any]]) -> Optional[float]:
    """Heuristique synchrone pour éviter un appel Gemini de classification sur les
    messages triviaux ("merci", "ok", "salut"…) ou sans signaux outils.

    Retourne :
      - 0.0 si on peut sauter le classifieur et partir en fast,
      - None pour laisser le classifieur trancher (cas où on veut potentiellement le pro).
    """
    last_user_text = ""
    for m in reversed(messages or []):
        if not isinstance(m, dict):
            continue
        if (m.get("role") or "").lower() == "user":
            last_user_text = (m.get("text") or "").strip()
            break
    if not last_user_text:
        return 0.0

    norm = last_user_text.lower().rstrip(".!?¿¡;:,…").strip()
    if norm in _FAST_PATH_PHRASES:
        return 0.0

    if len(last_user_text) > _FAST_PATH_MAX_LEN:
        return None

    compact = re.sub(r"[^a-zàâçéèêëîïôùûüœ ]+", " ", norm).strip()
    if not compact:
        return 0.0
    tokens = set(compact.split())
    if any(tok in _TOOL_HINT_TOKENS or any(tok.startswith(t) for t in _TOOL_HINT_TOKENS) for tok in tokens):
        return None
    word_count = len(tokens)
    if word_count <= 8:
        return 0.0
    return None


# ---------------------------------------------------------------------------
# Registre de progression (in-memory) - pour SSE / polling côté UI
# ---------------------------------------------------------------------------

_PROGRESS_TTL_S = 600.0
_progress_lock = threading.Lock()
_progress_store: Dict[str, Dict[str, Any]] = {}


def _progress_cleanup_locked() -> None:
    cutoff = time.time() - _PROGRESS_TTL_S
    for k in list(_progress_store.keys()):
        if _progress_store[k].get("ts", 0) < cutoff:
            _progress_store.pop(k, None)


def progress_set(key: Optional[str], payload: Dict[str, Any]) -> None:
    """Met à jour la progression d’une requête Axelia (skill courant, phase…)."""
    if not key:
        return
    with _progress_lock:
        _progress_cleanup_locked()
        existing = _progress_store.get(key) or {}
        merged = {**existing, **payload, "ts": time.time()}
        _progress_store[key] = merged


def progress_get(key: str, *, owner_user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Lit la progression. Si owner_user_id est fourni, refuse si différent du payload."""
    if not key:
        return None
    with _progress_lock:
        _progress_cleanup_locked()
        p = _progress_store.get(key)
        if not p:
            return None
        if owner_user_id is not None and p.get("user_id") and p["user_id"] != owner_user_id:
            return None
        return dict(p)


def progress_clear(key: Optional[str]) -> None:
    if not key:
        return
    with _progress_lock:
        _progress_store.pop(key, None)


_VALID_AXELIA_TASK_STATUS = frozenset({"pending", "in_progress", "done", "cancelled"})

# Titres courts + phrase UX (alignés sur l’UI Axelia) — utilisés si le modèle n’envoie pas task_plan.
_AXELIA_AUTO_PLAN_BY_SKILL: Dict[str, tuple[str, str]] = {
    "list_templates": ("Templates Meta", "Je consulte la liste des modèles sur Meta…"),
    "get_template_status": ("Statut template", "Je vérifie le statut du template sur Meta…"),
    "create_template": ("Création template", "Je prépare la fiche template…"),
    "prepare_template_image_header": ("Image template", "Je transfère l’image vers WhatsApp…"),
    "list_broadcast_groups": ("Groupes diffusion", "Je charge les groupes de diffusion…"),
    "search_inbox_messages": ("Recherche inbox", "Je parcours les messages de l’inbox…"),
    "get_conversation_digest": ("Fil de discussion", "Je lis le détail de cette conversation…"),
    "summarize_contact_inbox": ("Résumé contact", "Je synthétise l’historique avec ce contact…"),
    "search_contacts": ("Recherche contacts", "Je recherche dans le CRM…"),
    "get_contact": ("Fiche contact", "J’ouvre la fiche du contact…"),
    "list_recent_conversations": ("Conversations récentes", "Je liste les derniers fils actifs…"),
    "list_broadcast_campaigns": ("Campagnes", "Je charge les campagnes envoyées…"),
    "get_campaign_summary": ("Statistiques campagne", "J’analyse les stats de livraison et de lecture…"),
    "get_whatsapp_business_profile": ("Profil WABA", "Je lis le profil public WhatsApp Business…"),
    "meta_block_contact": ("Blocage Meta", "Je prépare l’action sensible côté Meta…"),
}


def _axelia_synthetic_task_row(skill_name: str, row_id_suffix: int) -> Dict[str, Any]:
    title, thought = _AXELIA_AUTO_PLAN_BY_SKILL.get(
        skill_name,
        ("Action outil", f"J’exécute « {skill_name} »…"),
    )
    return {
        "id": f"auto-{row_id_suffix}",
        "title": title,
        "thought": thought,
        "status": "pending",
        "skill": skill_name,
    }


def _augment_axelia_task_plan_for_safe_calls(
    todos: List[Dict[str, Any]],
    safe: List[Dict[str, Any]],
) -> None:
    """Complète ``todos`` pour couvrir chaque entrée de ``safe`` sans exiger task_plan du modèle."""
    names: List[str] = []
    for tc in safe:
        if not isinstance(tc, dict):
            continue
        sn = (tc.get("skill") or tc.get("name") or "").strip()
        if sn:
            names.append(sn)
    if not names:
        return

    used_pending: set[int] = set()

    def _consume_pending(sn: str) -> Optional[int]:
        for j, t in enumerate(todos):
            if j in used_pending or t.get("status") != "pending":
                continue
            if (t.get("skill") or "").strip() == sn:
                return j
        for j, t in enumerate(todos):
            if j in used_pending or t.get("status") != "pending":
                continue
            if not (t.get("skill") or "").strip():
                return j
        return None

    for sn in names:
        j = _consume_pending(sn)
        if j is not None:
            used_pending.add(j)
            row = todos[j]
            if not (row.get("skill") or "").strip():
                row["skill"] = sn
            title, thought = _AXELIA_AUTO_PLAN_BY_SKILL.get(
                sn,
                ("Action outil", f"J’exécute « {sn} »…"),
            )
            row.setdefault("title", title)
            row.setdefault("thought", thought)
        else:
            todos.append(_axelia_synthetic_task_row(sn, len(todos)))


def _normalize_axelia_task_plan(raw: Any, *, limit: int = 16) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for i, item in enumerate(raw[:limit]):
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id") or f"{i + 1}").strip() or f"{i + 1}"
        title = str(item.get("title") or item.get("label") or "").strip() or f"Étape {i + 1}"
        thought = str(item.get("thought") or item.get("note") or "").strip()
        st = str(item.get("status") or "pending").strip().lower()
        if st not in _VALID_AXELIA_TASK_STATUS:
            st = "pending"
        skill_raw = str(item.get("skill") or "").strip()
        row: Dict[str, Any] = {
            "id": tid,
            "title": title,
            "thought": thought,
            "status": st,
        }
        if skill_raw:
            row["skill"] = skill_raw
        out.append(row)
    return out


def _pick_task_indices_for_tools(
    todos: List[Dict[str, Any]], safe: List[Dict[str, Any]]
) -> List[int]:
    """Associe chaque appel à une entrée encore ``pending`` (champ ``skill`` sinon file)."""
    pending_idx = [i for i, t in enumerate(todos) if t.get("status") == "pending"]
    if not pending_idx or not safe:
        return []
    names = [
        (tc.get("skill") or tc.get("name") or "").strip()
        for tc in safe
        if isinstance(tc, dict)
    ]
    picked: List[int] = []
    for sn in names:
        matched: Optional[int] = None
        if sn:
            for i in pending_idx:
                if (todos[i].get("skill") or "").strip() == sn:
                    matched = i
                    break
        if matched is None and pending_idx:
            matched = pending_idx[0]
        if matched is not None:
            picked.append(matched)
            pending_idx = [i for i in pending_idx if i != matched]
    return picked


def _apply_task_progress_payload(
    *,
    progress_key: Optional[str],
    todos: List[Dict[str, Any]],
    phase: str,
    skills_used: List[str],
    rounds_done: int,
    running_skill_names: List[str],
    skills_running: Optional[List[str]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "phase": phase,
        "skill": (running_skill_names[0] if running_skill_names else None),
        "skills_running": skills_running if skills_running is not None else running_skill_names,
        "skills": list(skills_used),
        "round": rounds_done,
    }
    if todos:
        payload["todos"] = [dict(t) for t in todos]
    else:
        payload["todos"] = []
    progress_set(progress_key, payload)


# ---------------------------------------------------------------------------
# Métriques d'observabilité (in-memory) - adapté à un déploiement single-instance.
# Pour multi-worker, remplacer par un backend partagé (Redis / Prometheus).
# ---------------------------------------------------------------------------

_METRICS_RECENT_SIZE = 200
_metrics_lock = threading.Lock()
_metrics_counters: Dict[str, int] = {
    "calls_total": 0,
    "calls_with_tools": 0,
    "calls_no_tools": 0,
    "calls_classifier_shortcut": 0,
    "calls_classifier_full": 0,
    "calls_fast_model": 0,
    "calls_pro_model": 0,
    "calls_failed": 0,
    "json_parse_partial": 0,
    "json_parse_failed": 0,
    "skill_rounds_total": 0,
    "skill_executions_total": 0,
    "skill_loop_budget_hit": 0,
    "input_tokens_total": 0,
    "output_tokens_total": 0,
    "context_cache_hits": 0,
    "context_cache_misses": 0,
    "context_cache_failures": 0,
}
_metrics_recent: "collections.deque[Dict[str, Any]]" = collections.deque(
    maxlen=_METRICS_RECENT_SIZE
)
_metrics_per_model: Dict[str, Dict[str, float]] = {}


def metrics_record_call(
    *,
    model: str,
    duration_ms: float,
    used_tools: bool,
    skill_rounds: int,
    skill_executions: int,
    used_classifier: bool,
    used_pro: bool,
    json_partial: bool,
    json_failed: bool,
    failed: bool,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_state: str = "none",
    budget_hit: bool = False,
) -> None:
    """Enregistre une fin d'appel `/axelia/chat` côté serveur (synchrone, jamais bloquant)."""
    with _metrics_lock:
        _metrics_counters["calls_total"] += 1
        if used_tools:
            _metrics_counters["calls_with_tools"] += 1
        else:
            _metrics_counters["calls_no_tools"] += 1
        if used_classifier:
            _metrics_counters["calls_classifier_full"] += 1
        else:
            _metrics_counters["calls_classifier_shortcut"] += 1
        if used_pro:
            _metrics_counters["calls_pro_model"] += 1
        else:
            _metrics_counters["calls_fast_model"] += 1
        if failed:
            _metrics_counters["calls_failed"] += 1
        if json_partial:
            _metrics_counters["json_parse_partial"] += 1
        if json_failed:
            _metrics_counters["json_parse_failed"] += 1
        if budget_hit:
            _metrics_counters["skill_loop_budget_hit"] += 1
        _metrics_counters["skill_rounds_total"] += skill_rounds
        _metrics_counters["skill_executions_total"] += skill_executions
        _metrics_counters["input_tokens_total"] += int(max(0, input_tokens))
        _metrics_counters["output_tokens_total"] += int(max(0, output_tokens))
        if cache_state == "hit":
            _metrics_counters["context_cache_hits"] += 1
        elif cache_state == "miss":
            _metrics_counters["context_cache_misses"] += 1
        elif cache_state == "fail":
            _metrics_counters["context_cache_failures"] += 1

        per = _metrics_per_model.setdefault(
            model or "unknown",
            {"calls": 0, "duration_ms_sum": 0.0, "input_tokens": 0, "output_tokens": 0},
        )
        per["calls"] += 1
        per["duration_ms_sum"] += float(max(0.0, duration_ms))
        per["input_tokens"] += int(max(0, input_tokens))
        per["output_tokens"] += int(max(0, output_tokens))

        _metrics_recent.append(
            {
                "ts": time.time(),
                "model": model,
                "duration_ms": round(float(duration_ms), 1),
                "used_tools": used_tools,
                "rounds": skill_rounds,
                "skill_executions": skill_executions,
                "classifier": "shortcut" if not used_classifier else "full",
                "json_partial": json_partial,
                "json_failed": json_failed,
                "failed": failed,
                "input_tokens": int(max(0, input_tokens)),
                "output_tokens": int(max(0, output_tokens)),
                "cache": cache_state,
                "budget_hit": budget_hit,
            }
        )


def metrics_snapshot() -> Dict[str, Any]:
    """Lecture cohérente des compteurs + dérivés (latences moyennes, ratios)."""
    with _metrics_lock:
        counters = dict(_metrics_counters)
        per_model: Dict[str, Dict[str, float]] = {}
        for model, agg in _metrics_per_model.items():
            calls = max(1, int(agg["calls"]))
            per_model[model] = {
                "calls": int(agg["calls"]),
                "avg_duration_ms": round(agg["duration_ms_sum"] / calls, 1),
                "input_tokens": int(agg["input_tokens"]),
                "output_tokens": int(agg["output_tokens"]),
            }
        recent = list(_metrics_recent)

    total = max(1, counters["calls_total"])
    cache_attempts = max(
        1,
        counters["context_cache_hits"]
        + counters["context_cache_misses"]
        + counters["context_cache_failures"],
    )
    return {
        "counters": counters,
        "ratios": {
            "pro_share": round(counters["calls_pro_model"] / total, 4),
            "tools_share": round(counters["calls_with_tools"] / total, 4),
            "shortcut_share": round(counters["calls_classifier_shortcut"] / total, 4),
            "failure_rate": round(counters["calls_failed"] / total, 4),
            "json_partial_rate": round(counters["json_parse_partial"] / total, 4),
            "json_fail_rate": round(counters["json_parse_failed"] / total, 4),
            "cache_hit_rate": round(
                counters["context_cache_hits"] / cache_attempts, 4
            ),
        },
        "per_model": per_model,
        "recent": recent[-50:],
        "ts": time.time(),
    }


def metrics_reset_for_tests() -> None:
    """Réservé aux tests pour un point de départ propre."""
    with _metrics_lock:
        for k in _metrics_counters:
            _metrics_counters[k] = 0
        _metrics_per_model.clear()
        _metrics_recent.clear()


# ---------------------------------------------------------------------------
# Context caching Gemini (best-effort) - partage la portion statique du system prompt
# entre toutes les requêtes Axelia. Si le modèle ou la taille ne le permettent pas,
# on retombe silencieusement sur le mode normal (pas de blocage utilisateur).
# ---------------------------------------------------------------------------

_CONTEXT_CACHE_TTL_S = 1800.0  # 30 min (le serveur Gemini renouvelle si on l'utilise)
_CONTEXT_CACHE_MIN_CHARS = 4000  # ~1024 tokens : seuil minimal de cacheabilité côté API
_context_cache_lock = threading.Lock()
_context_cache_store: Dict[Tuple[str, str], Dict[str, Any]] = {}
# Modèles connus pour ne PAS supporter `cachedContent` - on n'essaie même pas.
_CONTEXT_CACHE_MODEL_BLOCKLIST = ("gemini-1.0-",)


def _context_cache_eligible_model(model_id: str) -> bool:
    if not model_id:
        return False
    return not any(model_id.startswith(p) for p in _CONTEXT_CACHE_MODEL_BLOCKLIST)


def _context_cache_key(model_id: str, system_text: str) -> Tuple[str, str]:
    digest = hashlib.sha256(system_text.encode("utf-8", errors="ignore")).hexdigest()[
        :32
    ]
    return (model_id, digest)


def _context_cache_get_locked(
    cache_key: Tuple[str, str],
) -> Optional[Dict[str, Any]]:
    entry = _context_cache_store.get(cache_key)
    if not entry:
        return None
    if entry.get("expires_at", 0) <= time.time():
        _context_cache_store.pop(cache_key, None)
        return None
    return entry


async def _context_cache_create(
    *,
    model_id: str,
    system_text: str,
    log_label: str,
    timeout_s: float = 10.0,
) -> Optional[str]:
    """Crée un `cachedContent` côté Gemini. Retourne `name` (ex. "cachedContents/xyz") ou None."""
    if not _context_cache_eligible_model(model_id):
        return None
    if len(system_text) < _CONTEXT_CACHE_MIN_CHARS:
        # Trop petit, l'API rejettera (min 1024 tokens sur la plupart des modèles 2.x).
        return None
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/cachedContents"
    )
    payload = {
        "model": f"models/{model_id}",
        "systemInstruction": {
            "role": "system",
            "parts": [{"text": system_text}],
        },
        "ttl": f"{int(_CONTEXT_CACHE_TTL_S)}s",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                endpoint,
                params={"key": settings.GEMINI_API_KEY},
                json=payload,
            )
        if resp.status_code >= 400:
            logger.info(
                "axelia cache: create rejected (%s) %s - %s",
                resp.status_code,
                log_label,
                resp.text[:240],
            )
            return None
        data = resp.json()
        name = data.get("name")
        if isinstance(name, str) and name.startswith("cachedContents/"):
            return name
        return None
    except Exception as exc:
        logger.info("axelia cache: create failed (%s): %s", log_label, exc)
        return None


async def maybe_get_or_create_context_cache(
    *,
    model_id: str,
    system_text: str,
    log_label: str,
) -> Tuple[Optional[str], str]:
    """
    Renvoie `(cached_content_name | None, state)` où `state` ∈ {"hit", "miss", "fail", "skip"}.
    `skip` : tentative non lancée (modèle non éligible / système trop court).
    """
    if not _context_cache_eligible_model(model_id):
        return None, "skip"
    if len(system_text) < _CONTEXT_CACHE_MIN_CHARS:
        return None, "skip"
    cache_key = _context_cache_key(model_id, system_text)
    with _context_cache_lock:
        entry = _context_cache_get_locked(cache_key)
    if entry:
        return entry["name"], "hit"
    name = await _context_cache_create(
        model_id=model_id, system_text=system_text, log_label=log_label
    )
    if not name:
        return None, "fail"
    with _context_cache_lock:
        _context_cache_store[cache_key] = {
            "name": name,
            "expires_at": time.time() + _CONTEXT_CACHE_TTL_S,
        }
    return name, "miss"


def context_cache_stats() -> Dict[str, Any]:
    with _context_cache_lock:
        return {
            "size": len(_context_cache_store),
            "entries": [
                {
                    "model": k[0],
                    "ttl_remaining_s": max(0, int(v["expires_at"] - time.time())),
                }
                for k, v in _context_cache_store.items()
            ],
        }


# ---------------------------------------------------------------------------
# Estimation tokens / résumé d'historique
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Approximation grossière : ~4 caractères par token pour le français/anglais courant."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _approx_tokens_in_response(data: Dict[str, Any]) -> Tuple[int, int]:
    """Extrait `(input_tokens, output_tokens)` de la réponse Gemini si dispo, sinon (0, 0)."""
    try:
        usage = data.get("usageMetadata") or {}
        in_tok = int(usage.get("promptTokenCount") or 0)
        out_tok = int(
            usage.get("candidatesTokenCount") or usage.get("totalTokenCount") or 0
        )
        if out_tok and in_tok:
            out_tok = max(0, out_tok - in_tok) if out_tok > in_tok else out_tok
        return in_tok, out_tok
    except Exception:
        return 0, 0


async def maybe_summarize_old_turns(
    messages: List[Dict[str, Any]],
    *,
    fast_model: str,
    log_label: str,
) -> List[Dict[str, Any]]:
    """Si l'historique dépasse `_HISTORY_SUMMARY_TRIGGER_TURNS`, condense les plus anciens
    en un seul message synthétique (rôle `model`) injecté en tête, et garde les
    `_HISTORY_SUMMARY_KEEP_RECENT` derniers tels quels.

    Best-effort : en cas d'erreur, on retourne l'historique brut (fallback `_MAX_TURNS`).
    """
    if not isinstance(messages, list) or len(messages) <= _HISTORY_SUMMARY_TRIGGER_TURNS:
        return messages
    head = messages[: -_HISTORY_SUMMARY_KEEP_RECENT]
    tail = messages[-_HISTORY_SUMMARY_KEEP_RECENT:]
    if not head:
        return messages

    transcript_lines: List[str] = []
    char_budget = 6000
    for m in head:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "").lower()
        text = (m.get("text") or "").strip()
        if not text:
            continue
        prefix = "Utilisateur" if role == "user" else "Axelia"
        snippet = text if len(text) <= 600 else text[:600] + "…"
        transcript_lines.append(f"{prefix}: {snippet}")
        char_budget -= len(snippet) + len(prefix) + 4
        if char_budget <= 0:
            break
    if not transcript_lines:
        return messages

    summarize_user = (
        "Tu es un compresseur de contexte. Résume en français très concis (≤ 8 lignes) "
        "les éléments factuels, demandes en cours et préférences mentionnées dans ce transcript. "
        "Pas de salutations, pas de meta-commentaire, pas de Markdown.\n\n"
        "TRANSCRIPT À RÉSUMER :\n" + "\n".join(transcript_lines)
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": summarize_user}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 600,
        },
    }
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{fast_model}:generateContent"
    )
    label = f"summary-{log_label}"
    try:
        data = await _call_gemini_api_once(
            endpoint,
            payload,
            label,
            read_timeout=float(settings.AXELIA_CLASSIFY_READ_TIMEOUT),
        )
    except Exception as exc:
        logger.info("axelia summary: échec best-effort (%s)", exc)
        return messages

    summary_text = (_extract_text_from_gemini_response(data or {}) or "").strip()
    if not summary_text:
        return messages
    if len(summary_text) > _HISTORY_SUMMARY_MAX_CHARS:
        summary_text = summary_text[: _HISTORY_SUMMARY_MAX_CHARS - 1] + "…"

    summary_block = (
        "[Résumé automatique des échanges plus anciens - pour mémoire, le détail "
        "n'est plus accessible aux outils inbox] :\n" + summary_text
    )
    return [{"role": "model", "text": summary_block}] + list(tail)


# ---------------------------------------------------------------------------
# Extraction incrémentale du champ `reply` dans une chaîne JSON partielle
# (utilisé pour le streaming token-par-token de la réponse finale).
# ---------------------------------------------------------------------------


def make_partial_reply_extractor():
    """
    Renvoie `(consume(chunk: str) -> str, finalize() -> str)`.

    `consume` accumule le texte JSON brut et émet le delta visible du champ `reply`
    (chaîne décodée de ses échappements). `finalize()` retourne le reply complet une fois
    l'accumulation terminée (best-effort si JSON tronqué).
    """
    state = {"buffer": "", "emitted_len": 0, "found_reply_start": False}

    def _decode_partial(raw_inner: str) -> str:
        """Décodage best-effort des séquences d'échappement JSON dans une chaîne incomplète."""
        if not raw_inner:
            return ""
        # Tente un decode complet ; si une séquence \X est tronquée à la fin, on la retire.
        candidate = raw_inner
        while candidate:
            try:
                return json.loads('"' + candidate + '"')
            except json.JSONDecodeError:
                # Retire le dernier caractère et réessaie ; l'échappement partiel
                # sera émis au prochain chunk quand il sera complet.
                candidate = candidate[:-1]
        return ""

    def consume(chunk: str) -> str:
        if not chunk:
            return ""
        state["buffer"] += chunk
        buf = state["buffer"]

        if not state["found_reply_start"]:
            # Cherche `"reply"\s*:\s*"` (début de la valeur string)
            m = re.search(r'"reply"\s*:\s*"', buf)
            if not m:
                return ""
            state["found_reply_start"] = True
            state["reply_value_start"] = m.end()

        start = state["reply_value_start"]
        # Trouve le caractère " non échappé qui ferme la valeur, OU consomme tout le reste.
        i = start + state["emitted_len"]
        end_index: Optional[int] = None
        # On scanne depuis le début de la valeur pour gérer correctement les `\\\"` et autres
        # - peu coûteux car cumulé et rare en boucle serrée.
        scan_i = start
        while scan_i < len(buf):
            ch = buf[scan_i]
            if ch == "\\":
                scan_i += 2
                continue
            if ch == '"':
                end_index = scan_i
                break
            scan_i += 1

        if end_index is not None:
            raw_inner = buf[start:end_index]
        else:
            raw_inner = buf[start:]
        decoded = _decode_partial(raw_inner)
        already = state["emitted_len"]
        if len(decoded) <= already:
            return ""
        delta = decoded[already:]
        state["emitted_len"] = len(decoded)
        return delta

    def finalize() -> str:
        if not state["found_reply_start"]:
            # Retombe sur l'extracteur tolérant existant (pour les JSON très tronqués)
            try:
                from app.services.bot_service import (
                    _playground_assist_try_reply_only_json,
                )
            except Exception:
                return ""
            return _playground_assist_try_reply_only_json(state["buffer"]) or ""
        start = state["reply_value_start"]
        buf = state["buffer"]
        scan_i = start
        end_index: Optional[int] = None
        while scan_i < len(buf):
            ch = buf[scan_i]
            if ch == "\\":
                scan_i += 2
                continue
            if ch == '"':
                end_index = scan_i
                break
            scan_i += 1
        raw_inner = buf[start : end_index if end_index is not None else len(buf)]
        try:
            return json.loads('"' + raw_inner + '"')
        except json.JSONDecodeError:
            # Retombe sur le decode partiel
            candidate = raw_inner
            while candidate:
                try:
                    return json.loads('"' + candidate + '"')
                except json.JSONDecodeError:
                    candidate = candidate[:-1]
            return ""

    return consume, finalize


def format_perimeter_context_prompt(
    perimeter_context: Optional[Dict[str, Any]],
) -> str:
    """
    Bloc injecté dans le prompt pour que le modèle connaisse la ligne WABA sélectionnée
    (données serveur, pas à inférer depuis l’utilisateur).
    """
    if not perimeter_context or not isinstance(perimeter_context, dict):
        return ""
    mode = (perimeter_context.get("mode") or "").strip()
    ui_hint = (perimeter_context.get("ui_hint") or "").strip()
    hint_line = f"\nLibellé affiché côté interface : {ui_hint}" if ui_hint else ""

    if mode == "single":
        p = perimeter_context.get("primary") or {}
        name = (p.get("name") or "-").strip()
        phone = (p.get("phone_number") or "-").strip()
        aid = (p.get("id") or "").strip()
        return (
            "\n=== CONTEXTE PÉRIMÈTRE CRM (fourni par le serveur) ===\n"
            "L’utilisateur a sélectionné **une ligne WhatsApp Business** enregistrée dans le CRM Axel.\n"
            f"- Nom du compte / WABA : {name}\n"
            f"- Téléphone affiché (ligne) : {phone}\n"
            f"- Identifiant technique du compte (UUID) : {aid}\n"
            "Tu travailles **exclusivement** sur cette ligne pour les données inbox (messages, contacts, templates Meta de ce compte).\n"
            "Pour toute question sur l’historique, les résumés ou « qui a dit quoi », tu DOIS utiliser les outils "
            "`search_inbox_messages`, `get_conversation_digest` et `summarize_contact_inbox` - "
            "**ne dis pas** que tu n’as pas accès au CRM lorsque ce bloc est présent.\n"
            "Si l’utilisateur demande « sur quel WABA » ou « quel compte », réponds avec le nom et le téléphone ci‑dessus."
            f"{hint_line}\n"
            "=== FIN CONTEXTE PÉRIMÈTRE ===\n"
        )

    if mode == "all":
        lines = [
            "\n=== CONTEXTE PÉRIMÈTRE CRM (fourni par le serveur) ===\n",
            "Mode interface : **Tous les comptes** - équivalent à « toutes les lignes WhatsApp Business **auxquelles "
            "cet utilisateur a accès** » (filtrage serveur sur conversations.view), **pas** l’ensemble de la base.\n",
            "Avec **un seul** compte accessible, ce périmètre se comporte comme une ligne unique pour les données inbox.\n",
            "Pour l’inbox : tu peux appeler `search_inbox_messages` et `summarize_contact_inbox` avec "
            "`account_scope: \"all_accessible\"` afin d’**agréger** recherche ou résumé **sur toutes ces lignes** "
            "(le serveur itère compte par compte, avec limites et timeouts). "
            "Ne refuse pas une synthèse multi-lignes sous prétexte qu’une ligne ne peut être lue qu’isolément.\n",
            "Pour les actions **Meta par compte** (templates, groupes, blocage), une ligne WABA explicite reste "
            "nécessaire : utilise le sélecteur ou demande quelle ligne si l’action est par nature mono-compte.\n",
        ]
        preview = perimeter_context.get("all_accounts_preview") or []
        if preview:
            lines.append("Comptes WABA visibles (extrait) :\n")
            for row in preview[:30]:
                nm = (row.get("name") or "-").strip()
                ph = (row.get("phone_number") or "-").strip()
                i = (row.get("id") or "").strip()
                lines.append(f"- {nm} - {ph} (id {i})\n")
        else:
            lines.append("(Aucun compte listé - droits à vérifier.)\n")
        lines.append(hint_line + "\n" if hint_line else "")
        lines.append("=== FIN CONTEXTE PÉRIMÈTRE ===\n")
        return "".join(lines)

    return ""


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
            b64_in = attachment.get("data_base64") or ""
            if not _inline_mime_supported(mime):
                raise ValueError("attachment_unsupported_mime")
            # ``_decode_attachment_b64`` lève ValueError("attachment_invalid_base64") en cas d'échec ;
            # on récupère les bytes pour pouvoir, en aval, normaliser la chaîne réinjectée à Gemini
            # (sans whitespace) afin d'éviter tout rejet silencieux côté API.
            raw = _decode_attachment_b64(b64_in)
            clean_b64 = base64.b64encode(raw).decode("ascii")
            parts.append({"inlineData": {"mimeType": mime, "data": clean_b64}})
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
    """Tente d'extraire `difficulty` d'une sortie LLM, même si elle est tronquée
    (`{"difficulty":` sans valeur) ou bruitée (markdown fences, texte libre)."""
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
        # Regex tolérant : capture la première valeur numérique associée à `difficulty`
        # même sans accolade finale ni markdown, avec ou sans espaces / guillemets.
        m = re.search(r'["\']?difficulty["\']?\s*:\s*([0-9]*\.?[0-9]+)', s, re.IGNORECASE)
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

    # Important sur Gemini 2.5 : par défaut le modèle « pense » et consomme tout le
    # `maxOutputTokens` budget en raisonnement caché → la sortie visible est tronquée
    # (`{"difficulty":` puis MAX_TOKENS). Ici la tâche est triviale, on force
    # thinkingBudget=0 sur Flash. Sur Pro (qui ne supporte pas 0) on garde un mini-budget.
    gen: Dict[str, Any] = {
        "temperature": 0,
        "maxOutputTokens": 256,
        "responseMimeType": "application/json",
        "responseSchema": {
            "type": "object",
            "properties": {
                "difficulty": {"type": "number"},
            },
            "required": ["difficulty"],
        },
    }
    fmid = (fast_model or "").lower()
    if fmid.startswith("gemini-2.5-flash"):
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    elif fmid.startswith("gemini-2.5-"):
        gen["thinkingConfig"] = {"thinkingBudget": 128}

    # Variante v1 (sans responseSchema, garanti supporté partout) en repli.
    gen_v1: Dict[str, Any] = {
        "temperature": 0,
        "maxOutputTokens": 256,
    }
    payload_v1beta: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": classify_user}]}],
        "generationConfig": gen,
    }
    payload_v1: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": classify_user}]}],
        "generationConfig": gen_v1,
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
        logger.warning(
            "axelia: difficulty parse failed, raw=%r - fallback=%.2f",
            (text or "")[:200],
            fb,
        )
        return fb
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
    perimeter_extra: str = "",
    metrics_out: Optional[Dict[str, Any]] = None,
) -> str:
    gen: Dict[str, Any] = {
        "temperature": 0.7,
        "maxOutputTokens": 4096,
    }
    if str(model_id).startswith("gemini-2.5-"):
        gen["thinkingConfig"] = {"thinkingBudget": 1024}

    sys_full = _compose_axelia_system_text(perimeter_extra)

    cached_name, cache_state = await maybe_get_or_create_context_cache(
        model_id=model_id, system_text=sys_full, log_label=log_label
    )
    if metrics_out is not None:
        metrics_out["cache_state"] = cache_state

    payload_v1beta: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": gen,
    }
    if cached_name:
        payload_v1beta["cachedContent"] = cached_name
    else:
        payload_v1beta["system_instruction"] = {
            "role": "system",
            "parts": [{"text": sys_full}],
        }
    payload_v1: Dict[str, Any] = {
        "contents": [
            {"role": "user", "parts": [{"text": sys_full}]},
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

    if metrics_out is not None:
        in_tok, out_tok = _approx_tokens_in_response(data or {})
        metrics_out["input_tokens"] = (metrics_out.get("input_tokens") or 0) + in_tok
        metrics_out["output_tokens"] = (metrics_out.get("output_tokens") or 0) + out_tok

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
    account: Optional[Dict[str, Any]],
    sector: Optional[str],
    log_label: str,
    chosen_model: str,
    approve_tool_calls: Optional[List[Dict[str, Any]]],
    acting_user: Optional["CurrentUser"] = None,
    perimeter_context: Optional[Dict[str, Any]] = None,
    perimeter_extra: str = "",
    progress_key: Optional[str] = None,
    metrics_out: Optional[Dict[str, Any]] = None,
    attachment: Optional[Dict[str, str]] = None,
) -> Tuple[str, str, List[str], Optional[List[Dict[str, Any]]]]:
    pre_skills: List[str] = []
    msgs_work = [m for m in messages if isinstance(m, dict)]
    acc_for_skills: Dict[str, Any] = dict(account) if account else {}
    perimeter_mode = str((perimeter_context or {}).get("mode") or "single").strip()
    if perimeter_mode not in ("single", "all"):
        perimeter_mode = "single" if acc_for_skills.get("id") else "all"

    # On rend la PJ courante visible aux skills via le runtime ContextVar : utile pour
    # les flux multi-étapes (ex. ``prepare_template_image_header`` doit accéder aux
    # bytes pour uploader vers Meta sans redemander le fichier à l'utilisateur).
    pending_att: Optional[AxeliaPendingAttachment] = None
    if attachment:
        try:
            mime = (attachment.get("mime_type") or "").strip().lower()
            b64 = attachment.get("data_base64") or ""
            if mime and b64:
                pending_att = AxeliaPendingAttachment(
                    mime_type=mime,
                    raw_bytes=_decode_attachment_b64(b64),
                )
        except ValueError:
            # On laisse remonter l'erreur via _build_contents plus bas (cas standard).
            pending_att = None

    ax_rt = AxeliaSkillsRuntime(
        acting_user=acting_user,
        perimeter_mode=perimeter_mode,
        pending_attachment=pending_att,
    )
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
            approve_results.extend(
                await execute_tool_calls(creates, acc_for_skills, axelia_runtime=ax_rt)
            )
        if blocks:
            from app.services.axelia_meta_actions import execute_meta_block_approved

            for tc in blocks:
                res = await execute_meta_block_approved(
                    tc.get("args") or {},
                    account=acc_for_skills,
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
                    + json.dumps(approve_results, ensure_ascii=False, default=str)
                ),
            }
        )

    sector_key = _norm_sector(sector) or "general"
    sector_line = _AXELIA_SECTOR_FOCUS.get(sector_key) or ""

    aid = str(acc_for_skills.get("id") or "").strip()
    if aid:
        account_name = (acc_for_skills.get("name") or "").strip() or "-"
        account_phone = (acc_for_skills.get("phone_number") or "").strip() or "-"
        uuid_hint = aid
    else:
        account_name = "-"
        account_phone = "-"
        uuid_hint = (
            "(aucun UUID ligne verrouillé - outils inbox multi-lignes via account_scope=all_accessible)"
        )

    system_text = (
        _compose_axelia_system_text(perimeter_extra)
        + "\n\n"
        + _AXEL_META_HINT
        + ("\n\n" + sector_line if sector_line else "")
        + "\n\n"
        + get_axelia_skills_prompt_section()
        + "\n\nRappel technique : UUID compte actif pour les skills dépendants d’une ligne : "
        + uuid_hint
        + f" - ligne « {account_name} », téléphone {account_phone}."
    )

    # ``_build_contents`` produit le même format que ``_messages_to_gem_hist`` mais
    # gère en plus l'attachement (image / PDF). On l'utilise systématiquement pour
    # que la première itération de la boucle skills voie l'image (vision).
    hist = _build_contents(msgs_work, attachment)
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

    cached_name, cache_state = await maybe_get_or_create_context_cache(
        model_id=chosen_model, system_text=system_text, log_label=log_label
    )
    if metrics_out is not None:
        metrics_out["cache_state"] = cache_state

    payload_v1beta: Dict[str, Any] = {
        "contents": hist,
        "generationConfig": gen,
    }
    if cached_name:
        payload_v1beta["cachedContent"] = cached_name
    else:
        payload_v1beta["system_instruction"] = {
            "role": "system",
            "parts": [{"text": system_text}],
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
    last_todos: List[Dict[str, Any]] = []

    _apply_task_progress_payload(
        progress_key=progress_key,
        todos=last_todos,
        phase="thinking",
        skills_used=list(skills_used),
        rounds_done=0,
        running_skill_names=[],
        skills_running=[],
    )

    # Budget dynamique : on tourne tant que (rounds < hard cap) ET (tokens < budget)
    # ET (au moins un nouveau skill exécuté dans les N derniers rounds).
    rounds_done = 0
    cumulative_tokens = 0
    rounds_no_progress = 0
    skill_executions_total_local = 0
    budget_hit = False
    in_tok_first, out_tok_first = _approx_tokens_in_response(data or {})
    cumulative_tokens += in_tok_first + out_tok_first

    while True:
        raw_text = _playground_assist_collect_model_text(data or {})
        finish_reason = _playground_assist_finish_reason(data or {})
        parsed, partial_json = _playground_assist_parse_model_payload(raw_text)
        if not isinstance(parsed, dict):
            if metrics_out is not None:
                metrics_out["json_failed"] = True
                metrics_out["rounds"] = rounds_done
                metrics_out["skill_executions"] = skill_executions_total_local
            reply_err = _axelia_json_fallback(raw_text, finish_reason=finish_reason)
            merged = list(dict.fromkeys([*pre_skills, *skills_used]))
            return reply_err, chosen_model, merged, frozen_pending or None

        if "task_plan" in parsed:
            tp = parsed.get("task_plan")
            if tp == []:
                last_todos = []
            elif isinstance(tp, list):
                last_todos = _normalize_axelia_task_plan(tp)

        tool_calls = parsed.get("tool_calls")
        if not tool_calls or not isinstance(tool_calls, list) or not tool_calls:
            break

        if rounds_done >= _MAX_SKILL_ROUNDS_HARD:
            logger.info(
                "axelia tools: hard rounds cap (%s) atteint pour %s",
                _MAX_SKILL_ROUNDS_HARD,
                log_label,
            )
            budget_hit = True
            break
        if cumulative_tokens >= _MAX_SKILL_TOKENS_BUDGET:
            logger.info(
                "axelia tools: token budget (%s) dépassé après %d rounds (%s)",
                _MAX_SKILL_TOKENS_BUDGET,
                rounds_done,
                log_label,
            )
            budget_hit = True
            break

        safe, p_create = _partition_playground_tool_calls(tool_calls)
        if p_create:
            frozen_pending = p_create

        if p_create and not safe:

            def _early_reply(_parsed=parsed, _raw_text=raw_text, _partial_json=partial_json) -> str:
                r = _parsed.get("reply")
                rs = r.strip() if isinstance(r, str) else ""
                rs = _playground_assist_clean_reply_string(rs)
                if not rs:
                    rs = _playground_assist_clean_reply_string((_raw_text or "").strip()) or "Réponse vide."
                if _partial_json:
                    rs += (
                        "\n\n_(Réponse possiblement tronquée ; confirme la création du template ci-dessous "
                        "quand tu es prêt·e.)_"
                    )
                return rs

            er = _early_reply()
            merged = list(dict.fromkeys([*pre_skills, *skills_used]))
            return er, chosen_model, merged, p_create

        if safe:
            _augment_axelia_task_plan_for_safe_calls(last_todos, safe)

        running_skill_names = [
            (tc.get("skill") or tc.get("name") or "").strip()
            for tc in safe
            if isinstance(tc, dict)
        ]
        batch_indices: List[int] = []
        if last_todos:
            batch_indices = _pick_task_indices_for_tools(last_todos, safe)
            for i in batch_indices:
                if 0 <= i < len(last_todos):
                    last_todos[i]["status"] = "in_progress"

        _apply_task_progress_payload(
            progress_key=progress_key,
            todos=last_todos,
            phase="tool",
            skills_used=list(skills_used),
            rounds_done=rounds_done + 1,
            running_skill_names=running_skill_names,
            skills_running=running_skill_names,
        )

        skill_results = await execute_tool_calls(
            safe, acc_for_skills, axelia_runtime=ax_rt
        )
        last_skill_results = skill_results
        new_skill_names = [r["skill"] for r in skill_results if r.get("skill")]
        skills_used.extend(new_skill_names)
        skill_executions_total_local += len(new_skill_names)
        if new_skill_names:
            rounds_no_progress = 0
        else:
            rounds_no_progress += 1

        if batch_indices:
            for i in batch_indices:
                if 0 <= i < len(last_todos):
                    last_todos[i]["status"] = "done"

        _apply_task_progress_payload(
            progress_key=progress_key,
            todos=last_todos,
            phase="thinking",
            skills_used=list(skills_used),
            rounds_done=rounds_done + 1,
            running_skill_names=[],
            skills_running=[],
        )

        tool_result_text = (
            "Résultats des skills demandés :\n"
            + json.dumps(skill_results, ensure_ascii=False, indent=2, default=str)
        )
        hist.append({"role": "model", "parts": [{"text": raw_text}]})
        hist.append({"role": "user", "parts": [{"text": tool_result_text}]})

        payload_v1beta["contents"] = hist
        payload_v1["contents"] = [flat_system] + hist

        rounds_done += 1
        if rounds_no_progress >= _MAX_SKILL_ROUNDS_NO_PROGRESS:
            logger.info(
                "axelia tools: %d rounds sans nouveau skill exécuté - arrêt boucle",
                rounds_no_progress,
            )
            budget_hit = True
            break

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
                    last_skill_results, ensure_ascii=False, default=str
                )
            return fb, chosen_model, merged_skills, frozen_pending or None
        in_tok_round, out_tok_round = _approx_tokens_in_response(data or {})
        cumulative_tokens += in_tok_round + out_tok_round

    exited_with_final_reply = (
        isinstance(parsed, dict)
        and last_todos
        and not (
            isinstance(parsed.get("tool_calls"), list) and parsed.get("tool_calls")
        )
    )
    if exited_with_final_reply and not budget_hit:
        for t in last_todos:
            if t.get("status") not in ("cancelled", "done"):
                t["status"] = "done"
        _apply_task_progress_payload(
            progress_key=progress_key,
            todos=last_todos,
            phase="thinking",
            skills_used=list(skills_used),
            rounds_done=rounds_done,
            running_skill_names=[],
            skills_running=[],
        )

    if metrics_out is not None:
        metrics_out["rounds"] = rounds_done
        metrics_out["skill_executions"] = skill_executions_total_local
        metrics_out["budget_hit"] = budget_hit
        metrics_out["json_partial"] = partial_json
        metrics_out["input_tokens"] = (
            metrics_out.get("input_tokens") or 0
        ) + cumulative_tokens // 2
        metrics_out["output_tokens"] = (
            metrics_out.get("output_tokens") or 0
        ) + cumulative_tokens // 2

    if not isinstance(parsed, dict):
        if metrics_out is not None:
            metrics_out["json_failed"] = True
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
    if budget_hit:
        reply_str += (
            "\n\n_(J'ai arrêté la chaîne d'outils ici pour rester dans le budget de calcul ; "
            "demande-moi un détail précis si tu veux pousser plus loin.)_"
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
    perimeter_context: Optional[Dict[str, Any]] = None,
    progress_key: Optional[str] = None,
) -> Tuple[str, str, Optional[List[str]], Optional[List[Dict[str, Any]]]]:
    """
    Génère la réponse Axelia.

    Sans compte WABA précis ou avec pièce jointe : même comportement historique (texte seul).

    Avec périmètre **toutes les lignes accessibles** (`perimeter_context.mode == "all"`) et sans PJ :
    boucle Gemini + skills (inbox multi-compte via `account_scope=all_accessible`).

    Avec une ligne WABA résolue (`account`) et sans PJ : idem avec périmètre mono-ligne.

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

    fast = settings.AXELIA_FAST_MODEL
    pro = settings.AXELIA_PRO_MODEL
    thr = float(settings.AXELIA_DIFFICULTY_THRESHOLD)

    # Résumé d'historique : compresse les vieux tours en un seul message
    # synthétique pour ne pas saturer le contexte du modèle.
    if not approve_tool_calls:
        try:
            messages = await maybe_summarize_old_turns(
                messages, fast_model=fast, log_label=log_label
            )
        except Exception as exc:
            logger.info("axelia summary: skipped (%s)", exc)

    contents = _build_contents(messages, attachment)
    if not contents:
        raise ValueError("empty_messages")

    perimeter_text = format_perimeter_context_prompt(perimeter_context)

    perimeter_mode = (
        str((perimeter_context or {}).get("mode") or "").strip()
        if perimeter_context
        else ""
    )
    # Une PJ image / PDF n'empêche plus la boucle skills : elle est passée à
    # `_run_axelia_with_tools` (vision sur la première itération) et exposée aux skills
    # via `AxeliaSkillsRuntime.pending_attachment` pour les flux multi-étapes
    # (ex. en-tête image d'un template Meta).
    use_skill_loop = bool(account) or perimeter_mode == "all"

    progress_set(
        progress_key,
        {"phase": "classifying", "skills": [], "round": 0},
    )

    shortcut = (
        _maybe_difficulty_shortcut(messages) if not approve_tool_calls else None
    )
    used_classifier = False
    if shortcut is not None:
        diff = shortcut
        logger.info(
            "axelia route: shortcut difficulty=%.2f -> model=%s tools=%s",
            diff,
            fast,
            use_skill_loop,
        )
    else:
        used_classifier = True
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
        use_skill_loop,
    )

    progress_set(
        progress_key,
        {"phase": "thinking", "model": chosen, "skills": [], "round": 0},
    )

    metrics_collector: Dict[str, Any] = {
        "rounds": 0,
        "skill_executions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "json_partial": False,
        "json_failed": False,
        "cache_state": "none",
        "budget_hit": False,
    }
    failed = False
    started_at = time.perf_counter()
    try:
        if use_skill_loop:
            try:
                return await _run_axelia_with_tools(
                    messages=messages,
                    account=account,
                    sector=sector,
                    log_label=log_label,
                    chosen_model=chosen,
                    approve_tool_calls=approve_tool_calls,
                    acting_user=acting_user,
                    perimeter_context=perimeter_context,
                    perimeter_extra=perimeter_text,
                    progress_key=progress_key,
                    metrics_out=metrics_collector,
                    attachment=attachment,
                )
            except ValueError:
                failed = True
                raise
            except Exception as exc:
                failed = True
                logger.exception("axelia tools crashed: %s", exc)
                raise ValueError("axelia_failed") from None

        try:
            text = await _generate_once(
                model_id=chosen,
                contents=contents,
                log_label=log_label,
                perimeter_extra=perimeter_text,
                metrics_out=metrics_collector,
            )
        except Exception:
            failed = True
            raise
        return text, chosen, None, None
    finally:
        progress_clear(progress_key)
        try:
            duration_ms = (time.perf_counter() - started_at) * 1000.0
            metrics_record_call(
                model=chosen,
                duration_ms=duration_ms,
                used_tools=use_skill_loop,
                skill_rounds=int(metrics_collector.get("rounds") or 0),
                skill_executions=int(metrics_collector.get("skill_executions") or 0),
                used_classifier=used_classifier,
                used_pro=(chosen == pro),
                json_partial=bool(metrics_collector.get("json_partial")),
                json_failed=bool(metrics_collector.get("json_failed")),
                failed=failed,
                input_tokens=int(metrics_collector.get("input_tokens") or 0),
                output_tokens=int(metrics_collector.get("output_tokens") or 0),
                cache_state=str(metrics_collector.get("cache_state") or "none"),
                budget_hit=bool(metrics_collector.get("budget_hit")),
            )
        except Exception:
            logger.debug("axelia metrics record failed (ignored)", exc_info=True)


# ---------------------------------------------------------------------------
# Streaming SSE - token-par-token pour les requêtes texte simples + chunks
# artificiels pour la voie « skill loop » (chaîne d'outils).
# ---------------------------------------------------------------------------

_STREAM_CHUNK_CHARS = 24
_STREAM_CHUNK_DELAY_S = 0.025


def _format_sse(event: str, data: Dict[str, Any]) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


async def _stream_real_text_only(
    *,
    model_id: str,
    contents: List[Dict[str, Any]],
    perimeter_extra: str,
    log_label: str,
    metrics_out: Dict[str, Any],
) -> AsyncIterator[str]:
    """Streaming Gemini réel pour le mode texte simple (pas de boucle d'outils)."""
    sys_full = _compose_axelia_system_text(perimeter_extra)
    cached_name, cache_state = await maybe_get_or_create_context_cache(
        model_id=model_id, system_text=sys_full, log_label=log_label
    )
    metrics_out["cache_state"] = cache_state

    gen: Dict[str, Any] = {
        "temperature": 0.7,
        "maxOutputTokens": 4096,
    }
    if str(model_id).startswith("gemini-2.5-"):
        gen["thinkingConfig"] = {"thinkingBudget": 1024}

    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": gen,
    }
    if cached_name:
        payload["cachedContent"] = cached_name
    else:
        payload["system_instruction"] = {
            "role": "system",
            "parts": [{"text": sys_full}],
        }

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_id}:streamGenerateContent"
    )
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)
    in_tokens = 0
    out_tokens = 0
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            endpoint,
            params={"key": settings.GEMINI_API_KEY, "alt": "sse"},
            json=payload,
        ) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", errors="ignore")
                logger.warning(
                    "axelia stream: HTTP %s - %s", resp.status_code, body[:240]
                )
                raise ValueError("gemini_unavailable")
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    raw = line[5:].lstrip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        chunk_obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    candidates = chunk_obj.get("candidates") or []
                    text_part = ""
                    for cand in candidates:
                        for p in (cand.get("content") or {}).get("parts") or []:
                            if p.get("thought"):
                                continue
                            t = p.get("text") or ""
                            if t:
                                text_part += t
                    usage = chunk_obj.get("usageMetadata") or {}
                    if usage:
                        in_tokens = int(usage.get("promptTokenCount") or in_tokens)
                        out_tokens = int(
                            usage.get("candidatesTokenCount") or out_tokens
                        )
                    if text_part:
                        yield text_part
    metrics_out["input_tokens"] = (metrics_out.get("input_tokens") or 0) + in_tokens
    metrics_out["output_tokens"] = (
        metrics_out.get("output_tokens") or 0
    ) + out_tokens


def _chunk_text(text: str, size: int = _STREAM_CHUNK_CHARS) -> Iterable[str]:
    """Découpe un texte en morceaux de taille raisonnable pour un effet « tape-à-l'écran »."""
    if not text:
        return
    n = len(text)
    i = 0
    while i < n:
        end = min(i + size, n)
        # Évite de couper au milieu d'un mot quand c'est bon marché.
        if end < n and text[end] not in " \n\t.!?,;:)]}»":
            sp = text.rfind(" ", i + 1, end)
            if sp > i + size // 2:
                end = sp + 1
        yield text[i:end]
        i = end


async def stream_axelia_chat(
    *,
    messages: List[Dict[str, Any]],
    attachment: Optional[Dict[str, str]] = None,
    log_label: str = "axelia-stream",
    account: Optional[Dict[str, Any]] = None,
    sector: Optional[str] = None,
    approve_tool_calls: Optional[List[Dict[str, Any]]] = None,
    acting_user: Optional["CurrentUser"] = None,
    perimeter_context: Optional[Dict[str, Any]] = None,
    progress_key: Optional[str] = None,
) -> AsyncIterator[bytes]:
    """
    Itérateur SSE pour Axelia. Yields des bytes au format ``event: .../data: {...}\\n\\n``.

    Événements émis :
    - ``meta``     : modèle choisi, classifier, périmètre.
    - ``progress`` : phase, skill(s) courant(s), skills cumulés, ``todos`` si ``task_plan`` actif.
    - ``token``    : delta texte du reply final (peut être plusieurs).
    - ``done``     : payload final (text complet, skills, pending_tool_calls, model).
    - ``error``    : ``{code, message}`` côté serveur.
    """
    if not settings.GEMINI_API_KEY:
        yield _format_sse(
            "error", {"code": "gemini_not_configured", "message": "Clé API absente."}
        )
        return

    fast = settings.AXELIA_FAST_MODEL
    pro = settings.AXELIA_PRO_MODEL
    thr = float(settings.AXELIA_DIFFICULTY_THRESHOLD)

    if not approve_tool_calls:
        try:
            messages = await maybe_summarize_old_turns(
                messages, fast_model=fast, log_label=log_label
            )
        except Exception:
            pass

    perimeter_text = format_perimeter_context_prompt(perimeter_context)
    perimeter_mode = (
        str((perimeter_context or {}).get("mode") or "").strip()
        if perimeter_context
        else ""
    )
    # Cf. note dans run_axelia_chat : la PJ ne désactive plus la skill loop, elle est
    # propagée jusque dans `_run_axelia_with_tools` (vision + runtime des skills).
    use_skill_loop = bool(account) or perimeter_mode == "all"

    yield _format_sse(
        "progress",
        {"phase": "classifying", "skills": [], "round": 0},
    )
    progress_set(progress_key, {"phase": "classifying", "skills": [], "round": 0})

    shortcut = (
        _maybe_difficulty_shortcut(messages) if not approve_tool_calls else None
    )
    used_classifier = shortcut is None
    if shortcut is not None:
        diff = shortcut
    else:
        try:
            diff = await estimate_difficulty(
                messages=messages, log_label=log_label, fast_model=fast
            )
        except Exception:
            diff = float(settings.AXELIA_CLASSIFY_FALLBACK_DIFFICULTY)
    chosen = pro if diff >= thr else fast
    yield _format_sse(
        "meta",
        {
            "model": chosen,
            "classifier": "shortcut" if not used_classifier else "full",
            "difficulty": round(diff, 3),
            "tools_path": use_skill_loop,
        },
    )
    progress_set(
        progress_key,
        {"phase": "thinking", "model": chosen, "skills": [], "round": 0},
    )
    yield _format_sse("progress", {"phase": "thinking", "model": chosen})

    metrics_collector: Dict[str, Any] = {
        "rounds": 0,
        "skill_executions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "json_partial": False,
        "json_failed": False,
        "cache_state": "none",
        "budget_hit": False,
    }
    failed = False
    started_at = time.perf_counter()
    final_text = ""
    final_model = chosen
    skills_used: Optional[List[str]] = None
    pending_tool_calls: Optional[List[Dict[str, Any]]] = None

    try:
        if use_skill_loop:
            try:
                final_text, final_model, skills_used, pending_tool_calls = (
                    await _run_axelia_with_tools(
                        messages=messages,
                        account=account,
                        sector=sector,
                        log_label=log_label,
                        chosen_model=chosen,
                        approve_tool_calls=approve_tool_calls,
                        acting_user=acting_user,
                        perimeter_context=perimeter_context,
                        perimeter_extra=perimeter_text,
                        progress_key=progress_key,
                        metrics_out=metrics_collector,
                        attachment=attachment,
                    )
                )
            except ValueError as exc:
                failed = True
                yield _format_sse(
                    "error", {"code": str(exc), "message": str(exc)}
                )
                return
            except Exception as exc:
                failed = True
                logger.exception("axelia stream tools crashed: %s", exc)
                yield _format_sse(
                    "error",
                    {"code": "axelia_failed", "message": "Erreur interne Axelia."},
                )
                return

            # Streaming « simulé » du texte final déjà connu.
            for delta in _chunk_text(final_text):
                yield _format_sse("token", {"chunk": delta})
                await asyncio.sleep(_STREAM_CHUNK_DELAY_S)
        else:
            try:
                contents = _build_contents(messages, attachment)
            except ValueError as exc:
                failed = True
                yield _format_sse(
                    "error",
                    {"code": str(exc), "message": "Pièce jointe non supportée."},
                )
                return
            if not contents:
                failed = True
                yield _format_sse(
                    "error", {"code": "empty_messages", "message": "Pas de message."}
                )
                return
            try:
                buf: List[str] = []
                async for chunk in _stream_real_text_only(
                    model_id=chosen,
                    contents=contents,
                    perimeter_extra=perimeter_text,
                    log_label=log_label,
                    metrics_out=metrics_collector,
                ):
                    buf.append(chunk)
                    yield _format_sse("token", {"chunk": chunk})
                final_text = "".join(buf).strip()
                if not final_text:
                    failed = True
                    yield _format_sse(
                        "error",
                        {"code": "empty_reply", "message": "Réponse vide du modèle."},
                    )
                    return
            except ValueError as exc:
                failed = True
                yield _format_sse(
                    "error", {"code": str(exc), "message": str(exc)}
                )
                return
            except Exception as exc:
                failed = True
                logger.exception("axelia stream simple crashed: %s", exc)
                yield _format_sse(
                    "error",
                    {"code": "axelia_failed", "message": "Erreur interne Axelia."},
                )
                return

        yield _format_sse(
            "done",
            {
                "text": final_text,
                "model": final_model,
                "skills_used": skills_used,
                "pending_tool_calls": pending_tool_calls,
            },
        )
    finally:
        progress_clear(progress_key)
        try:
            duration_ms = (time.perf_counter() - started_at) * 1000.0
            metrics_record_call(
                model=chosen,
                duration_ms=duration_ms,
                used_tools=use_skill_loop,
                skill_rounds=int(metrics_collector.get("rounds") or 0),
                skill_executions=int(metrics_collector.get("skill_executions") or 0),
                used_classifier=used_classifier,
                used_pro=(chosen == pro),
                json_partial=bool(metrics_collector.get("json_partial")),
                json_failed=bool(metrics_collector.get("json_failed")),
                failed=failed,
                input_tokens=int(metrics_collector.get("input_tokens") or 0),
                output_tokens=int(metrics_collector.get("output_tokens") or 0),
                cache_state=str(metrics_collector.get("cache_state") or "none"),
                budget_hit=bool(metrics_collector.get("budget_hit")),
            )
        except Exception:
            logger.debug("axelia stream metrics record failed", exc_info=True)

