"""
Registre de skills pour l'assistant Playground.

Chaque skill est une fonction que le bot peut invoquer via tool_calls dans sa réponse JSON.
Le bot ne reçoit que le catalogue (nom + description) - les données sont chargées à la demande.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("uvicorn.error").getChild("playground_skills")


def _resolve_waba_credentials(account: Dict[str, Any]) -> tuple:
    """Resolve waba_id and access_token with env fallbacks."""
    waba_id = account.get("waba_id") or settings.WHATSAPP_BUSINESS_ACCOUNT_ID
    token = account.get("access_token") or settings.WHATSAPP_TOKEN
    return waba_id, token


SKILLS_CATALOG: List[Dict[str, Any]] = [
    {
        "name": "list_templates",
        "description": "Liste les templates Meta du compte (nom, langue, statut, catégorie, résumé des composants).",
        "parameters": [],
        "use_when": "tu dois savoir quels templates existent avant de proposer un sendTemplate.",
    },
    {
        "name": "get_template_status",
        "description": "Vérifie le statut d'un template spécifique par nom (APPROVED, PENDING, REJECTED).",
        "parameters": [
            {"name": "template_name", "type": "string", "required": True},
        ],
        "use_when": "tu veux vérifier qu'un template est APPROVED avant de l'utiliser dans le graphe.",
    },
    {
        "name": "create_template",
        "description": "Crée un nouveau template Meta (soumis à review). Retourne l'id + statut PENDING.",
        "parameters": [
            {"name": "name", "type": "string", "required": True},
            {"name": "category", "type": "string", "required": True, "enum": ["MARKETING", "UTILITY"]},
            {"name": "language", "type": "string", "required": True},
            {"name": "components", "type": "array", "required": True},
        ],
        "use_when": "le template nécessaire n'existe pas. TOUJOURS demander confirmation à l'utilisateur avant d'appeler.",
    },
    {
        "name": "list_broadcast_groups",
        "description": "Liste les groupes de diffusion du compte (id, nom, nombre de membres).",
        "parameters": [],
        "use_when": "l'utilisateur veut programmer un envoi ou cibler un groupe.",
    },
]

# Skills additionnels réservés au hub Axelia (inbox CRM / actions sensibles).
AXELIA_ONLY_SKILLS: List[Dict[str, Any]] = [
    {
        "name": "search_inbox_messages",
        "description": (
            "Recherche dans les messages texte du compte WABA courant (toutes conversations) "
            "pour retrouver des échanges mentionnant des sujets ou mots-clés."
        ),
        "parameters": [
            {"name": "query", "type": "string", "required": True},
            {"name": "limit", "type": "integer", "required": False},
        ],
        "use_when": (
            "l’utilisateur cherche qui a évoqué un sujet, un produit, un prénom dans l’historique."
        ),
    },
    {
        "name": "get_conversation_digest",
        "description": (
            "Récupère les derniers messages texte d’une conversation inbox (résumé ou contexte), "
            "pour le conversation_id UUID connu."
        ),
        "parameters": [
            {"name": "conversation_id", "type": "string", "required": True},
            {"name": "max_messages", "type": "integer", "required": False},
        ],
        "use_when": (
            "résumer ou relire une discussion précise après l’avoir identifiée (souvent via search_inbox_messages)."
        ),
    },
    {
        "name": "meta_block_contact",
        "description": (
            "Bloque un contact sur la ligne WhatsApp Business (API Meta block_users). "
            "Action sensible : le backend ne l’exécute pas tant que l’utilisateur n’a pas confirmé dans l’interface."
        ),
        "parameters": [
            {"name": "contact_id", "type": "string", "required": True},
        ],
        "use_when": (
            "l’utilisateur confirme vouloir bloquer quelqu’un ; contact_id doit provenir des données CRM "
            "(jamais inventé). Si plusieurs comptes WABA, demande explicitement sur quel compte "
            "(doit correspondre au périmètre sélectionné dans l’UI)."
        ),
    },
]


def get_axelia_skills_prompt_section() -> str:
    """
    Version Axelia (hub IA) : mêmes outils que le Playground, sans graphe ni todo.
    """
    lines = [
        "OUTILS DISPONIBLES (skills) — Playground + inbox CRM Axelia :",
        "Tu réponds par un **unique** objet JSON ( MIME application/json ) avec les champs :",
        '  {"reply": "<texte visible pour l’utilisateur>", "tool_calls": []}',
        'Chaque entrée de tool_calls : {"skill": "nom_du_skill", "args": { ... } }',
        "Le backend exécute les skills et te renvoie les résultats dans un message suivant.",
        "Ne devine pas les noms de templates, groupes ou UUID : appelle les skills.",
        "Pour create_template et meta_block_contact : confirmation utilisateur obligatoire dans l’UI "
        "(tu inclus tool_calls avec les args ; tu n’exécutes pas toi‑même l’action sensible).",
        "Tu agis uniquement dans le périmètre du compte WABA sélectionné par l’utilisateur dans l’interface "
        "(pas d’action sur un autre compte). Si le périmètre est « tous les comptes », demande de choisir une ligne avant.",
        "",
    ]
    for sk in [*SKILLS_CATALOG, *AXELIA_ONLY_SKILLS]:
        params_str = "aucun"
        if sk["parameters"]:
            parts = []
            for p in sk["parameters"]:
                s = f"{p['name']} ({p['type']})"
                if p.get("enum"):
                    s += f" [{' | '.join(p['enum'])}]"
                if not p.get("required"):
                    s += " optionnel"
                parts.append(s)
            params_str = ", ".join(parts)
        lines.append(f"- {sk['name']} : {sk['description']}")
        lines.append(f"  Paramètres : {params_str}")
        lines.append(f"  Utilise quand : {sk['use_when']}")
        lines.append("")
    lines.extend([
        "Règles compactes :",
        "- Templates : list_templates → get_template_status si besoin → create_template après accord explicite.",
        "- Campagnes / ciblage : list_broadcast_groups dès que les groupes ou volumes comptent.",
        "- Inbox : search_inbox_messages avec une requête en mots-clés ; affine avec des questions si trop de résultats.",
        "- Résumés : get_conversation_digest une fois conversation_id connu.",
        "- Blocage Meta : meta_block_contact seulement avec contact_id réel ; jamais sans confirmation UI.",
        "- Réponse reply : française, concise, utile ; pas de bloc Markdown avec dièses en titres.",
    ])
    return "\n".join(lines)


def get_skills_prompt_section() -> str:
    """Texte injecté dans le prompt système pour décrire les skills disponibles."""
    lines = [
        "OUTILS DISPONIBLES (skills) :",
        "Tu peux appeler ces outils en ajoutant \"tool_calls\" dans ta réponse JSON.",
        "Le système exécutera les appels et te renverra les résultats dans un message suivant.",
        "Tu pourras alors continuer ta réponse avec les données réelles.",
        "Ne devine JAMAIS les données (noms de templates, groupes…) - appelle le skill correspondant.",
        "IMPORTANT : utilise les skills DE MANIÈRE PROACTIVE. Si l'utilisateur parle de templates, appelle list_templates sans attendre qu'il te le demande.",
        "Si l'utilisateur veut une campagne, appelle list_broadcast_groups immédiatement.",
        "",
    ]
    for sk in SKILLS_CATALOG:
        params_str = "aucun"
        if sk["parameters"]:
            parts = []
            for p in sk["parameters"]:
                s = f"{p['name']} ({p['type']})"
                if p.get("enum"):
                    s += f" [{' | '.join(p['enum'])}]"
                if not p.get("required"):
                    s += " optionnel"
                parts.append(s)
            params_str = ", ".join(parts)
        lines.append(f"- {sk['name']} : {sk['description']}")
        lines.append(f"  Paramètres : {params_str}")
        lines.append(f"  Utilise quand : {sk['use_when']}")
        lines.append("")

    lines.extend([
        "RÈGLES D'EXÉCUTION COMPACTES (économie de tokens) :",
        "- D'abord décider si un skill est vraiment nécessaire. Si la réponse est déductible du contexte local, n'appelle pas de skill.",
        "- Pour les templates : séquence minimale = list_templates -> (optionnel) get_template_status -> (optionnel) create_template après confirmation.",
        "- Réponse courte orientée action (3 à 6 lignes max) + todo mis à jour ; pas de long texte explicatif si non demandé.",
        "- Quand un skill renvoie beaucoup de données, résume uniquement les champs utiles pour la décision suivante (nom, statut, langue, id).",
        "- Une étape todo principale par tour en mode Agent ; éviter de traiter tout le plan dans un seul message.",
        "",
        "RÈGLES VARIABLES TEMPLATE (Meta) :",
        "- Placeholders numériques (BODY avec {{1}}, {{2}}, ...) : indices strictement séquentiels, sans trou ({{1}}, {{2}}, {{3}}...).",
        "- Placeholders nommés (BODY avec {{first_name}}, {{offer_name}}, ...) : noms en minuscules + underscores, uniques.",
        "- Exemples obligatoires selon le type :",
        "  numérique -> variableValues: {\"1\": \"{{contact.firstName}}\", \"2\": \"SUV Premium\"}",
        "  nommé -> variableValues: {\"first_name\": \"{{contact.firstName}}\", \"offer_name\": \"SUV Premium\"}",
        "- Pour create_template, l'example Meta est OBLIGATOIRE quand il y a des variables :",
        "  numérique -> BODY.example.body_text = [[\"Alice\", \"OFFRE SUV\"]]",
        "  nommé -> BODY.example.body_text_named_params = [{\"param_name\":\"first_name\",\"example\":\"Alice\"}]",
        "- Si le body utilise '{{1}}' (mode variable numérique), n'utilise PAS body_text_named_params.",
        "- Si le body utilise '{{first_name}}' (mode nommé), n'utilise PAS body_text.",
        "- Ne mélange pas les conventions dans un même template : si Meta expose des noms, n'invente pas des index; si Meta expose des index, n'invente pas des noms.",
        "",
        "PLAN D'ACTION (todo) :",
        "DÈS que la demande implique plus d'une étape, tu DOIS inclure un champ \"todo\" dans ta PREMIÈRE réponse.",
        "Chaque item : {\"id\": \"1\", \"label\": \"Description courte\", \"status\": \"pending|in_progress|done\"}.",
        "Mets à jour les statuts au fur et à mesure des tours. L'utilisateur voit ce plan en temps réel.",
        "Le premier item en cours doit avoir status \"in_progress\", les suivants \"pending\".",
        "Quand tu appelles un skill, marque l'étape correspondante \"in_progress\" dans la même réponse.",
        "Quand tu reçois les résultats d'un skill, marque l'étape \"done\" et passe à la suivante.",
        "IMPORTANT : inclus TOUJOURS le todo complet (tous les items) dans chaque réponse, même les items déjà \"done\".",
        "Si tu veux retirer la todo de l'interface, renvoie explicitement \"todo\": []. Si tu omets le champ todo, le client réaffiche la todo du tour précédent (utile en changement Ask/Agent).",
        "Quand le client déclenche une exécution de plan en mode Agent, traite UNE étape principale par tour, puis mets à jour todo (done / in_progress) avant de continuer à l'étape suivante.",
        "",
        "GESTION DES RESSOURCES MANQUANTES :",
        "- Si list_templates retourne 0 templates correspondant au besoin : propose à l'utilisateur d'en créer un. Décris le template que tu créerais. "
        "N'inclus create_template dans tool_calls qu'après accord explicite de l'utilisateur ; le backend bloque l'exécution jusqu'à ce qu'il clique « Confirmer la création » dans l'UI (comme une validation de commande).",
        "- Campagnes / premier message entreprise : le graphe doit utiliser le nœud sendTemplate (avec quickReplyButtons si boutons Meta), jamais interactiveNode pour simuler un template.",
        "- Même avec des boutons quick reply, prévoir un fallback hors-sujet : router exact sur les boutons + branche escape vers Gemini (qualification) ou handoff, pour gérer les réponses libres inattendues.",
        "- Si list_broadcast_groups retourne 0 groupes ou aucun groupe correspondant : propose à l'utilisateur d'en créer un manuellement. Explique comment faire dans l'interface.",
        "- Si un groupe de diffusion existe mais est vide (0 membres) : signale-le. Dis à l'utilisateur ce qu'il lui reste à faire (ajouter des contacts).",
        "- Après avoir tout configuré, termine TOUJOURS par un résumé de ce qui est prêt et de ce qu'il reste à faire manuellement (ex: approuver un template, ajouter des contacts à un groupe, etc.).",
    ])
    return "\n".join(lines)


_POS_VAR_RE = re.compile(r"{{\s*([1-9]\d*)\s*}}")
_NAMED_VAR_RE = re.compile(r"{{\s*([a-z_][a-z0-9_]*)\s*}}")


def _validate_template_components_for_meta(components: List[Dict[str, Any]]) -> Optional[str]:
    """
    Validation minimaliste des variables Meta pour réduire les rejets API.
    Cible prioritairement BODY, qui porte la majorité des cas de rejet.
    """
    if not isinstance(components, list) or not components:
        return "components doit être un tableau non vide."

    body = next(
        (
            c
            for c in components
            if isinstance(c, dict) and str(c.get("type") or "").upper() == "BODY"
        ),
        None,
    )
    if not isinstance(body, dict):
        return "Un composant BODY est requis."

    text = str(body.get("text") or "").strip()
    if not text:
        return "BODY.text est requis."

    pos_vars = sorted({int(m.group(1)) for m in _POS_VAR_RE.finditer(text)})
    named_vars = sorted({m.group(1) for m in _NAMED_VAR_RE.finditer(text)})
    # Nettoie les vars nommées qui sont en fait numériques (couvertes par pos_vars)
    named_vars = [v for v in named_vars if not v.isdigit()]

    if pos_vars and named_vars:
        return "BODY.text mélange des variables numériques et nommées. Utilise un seul format."

    if not pos_vars and not named_vars:
        return None

    example = body.get("example")
    if not isinstance(example, dict):
        return "BODY.example est obligatoire quand BODY.text contient des variables."

    if pos_vars:
        expected = list(range(1, max(pos_vars) + 1))
        if pos_vars != expected:
            return f"Variables numériques invalides: attendu {expected}, reçu {pos_vars}."
        body_text = example.get("body_text")
        if not isinstance(body_text, list) or not body_text:
            return "BODY.example.body_text est requis pour des variables numériques."
        first_row = body_text[0] if isinstance(body_text[0], list) else None
        if not isinstance(first_row, list) or len(first_row) < len(pos_vars):
            return (
                "BODY.example.body_text doit contenir au moins une ligne d'exemples "
                f"avec {len(pos_vars)} valeur(s)."
            )
        if example.get("body_text_named_params"):
            return "Ne combine pas body_text et body_text_named_params pour un BODY numérique."
        return None

    named_params = example.get("body_text_named_params")
    if not isinstance(named_params, list) or not named_params:
        return "BODY.example.body_text_named_params est requis pour des variables nommées."
    provided_names = sorted(
        {
            str(p.get("param_name") or "").strip()
            for p in named_params
            if isinstance(p, dict) and str(p.get("param_name") or "").strip()
        }
    )
    if sorted(named_vars) != provided_names:
        return (
            "Variables nommées incohérentes: "
            f"BODY.text={sorted(named_vars)} vs example={provided_names}."
        )
    for p in named_params:
        if not isinstance(p, dict):
            return "Chaque entrée body_text_named_params doit être un objet."
        if not str(p.get("example") or "").strip():
            return "Chaque body_text_named_params doit inclure un champ example non vide."
    if example.get("body_text"):
        return "Ne combine pas body_text et body_text_named_params pour un BODY nommé."
    return None


def _summarize_template(tpl: Dict[str, Any]) -> Dict[str, Any]:
    """Résumé compact d'un template pour ne pas surcharger le contexte."""
    components = tpl.get("components") or []
    comp_summary = []
    for c in components:
        ctype = (c.get("type") or "").upper()
        if ctype == "BODY":
            text = (c.get("text") or "")[:120]
            comp_summary.append(f"BODY: {text}")
        elif ctype == "HEADER":
            fmt = c.get("format") or "TEXT"
            comp_summary.append(f"HEADER({fmt})")
        elif ctype == "BUTTONS":
            btns = c.get("buttons") or []
            btn_labels = [b.get("text") or b.get("type") or "?" for b in btns[:5]]
            comp_summary.append(f"BUTTONS: {', '.join(btn_labels)}")
        elif ctype == "FOOTER":
            comp_summary.append(f"FOOTER: {(c.get('text') or '')[:60]}")
    return {
        "name": tpl.get("name"),
        "language": tpl.get("language"),
        "status": tpl.get("status"),
        "category": tpl.get("category"),
        "components": comp_summary,
    }


async def _skill_list_templates(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.whatsapp_api_service import list_message_templates

    waba_id, token = _resolve_waba_credentials(account)
    if not waba_id or not token:
        return {"error": "Compte sans waba_id ou access_token configuré."}

    all_tpls: List[Dict[str, Any]] = []
    cursor_after: Optional[str] = None
    for _ in range(10):
        batch = await list_message_templates(str(waba_id), token, limit=100, after=cursor_after)
        chunk = batch.get("data") or []
        if not chunk:
            break
        all_tpls.extend(chunk)
        cursor_after = (batch.get("paging") or {}).get("cursors", {}).get("after")
        if not cursor_after:
            break

    summaries = [_summarize_template(t) for t in all_tpls]
    return {
        "total": len(summaries),
        "templates": summaries,
    }


async def _skill_get_template_status(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.whatsapp_api_service import list_message_templates

    template_name = (args.get("template_name") or "").strip()
    if not template_name:
        return {"error": "template_name requis."}

    waba_id, token = _resolve_waba_credentials(account)
    if not waba_id or not token:
        return {"error": "Compte sans waba_id ou access_token configuré."}

    all_tpls: List[Dict[str, Any]] = []
    cursor_after: Optional[str] = None
    for _ in range(10):
        batch = await list_message_templates(str(waba_id), token, limit=100, after=cursor_after)
        chunk = batch.get("data") or []
        if not chunk:
            break
        all_tpls.extend(chunk)
        cursor_after = (batch.get("paging") or {}).get("cursors", {}).get("after")
        if not cursor_after:
            break

    matches = [t for t in all_tpls if t.get("name") == template_name]
    if not matches:
        return {"found": False, "message": f"Aucun template nommé '{template_name}' trouvé."}

    return {
        "found": True,
        "matches": [_summarize_template(t) for t in matches],
    }


async def _skill_create_template(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.whatsapp_api_service import create_message_template

    waba_id, token = _resolve_waba_credentials(account)
    if not waba_id or not token:
        return {"error": "Compte sans waba_id ou access_token configuré."}

    name = (args.get("name") or "").strip()
    category = (args.get("category") or "").strip().upper()
    language = (args.get("language") or "fr").strip()
    components = args.get("components")

    if not name:
        return {"error": "name requis."}
    if category not in ("MARKETING", "UTILITY", "AUTHENTICATION"):
        return {"error": f"category invalide: {category}. Utiliser MARKETING ou UTILITY."}
    if not isinstance(components, list) or not components:
        return {"error": "components doit être un tableau non vide."}
    meta_validation_error = _validate_template_components_for_meta(components)
    if meta_validation_error:
        return {
            "error": (
                "Payload template invalide selon les règles Meta: "
                + meta_validation_error
            )
        }

    try:
        result = await create_message_template(
            str(waba_id), token, name, category, language, components,
        )
        return {
            "success": True,
            "template_id": result.get("id"),
            "status": result.get("status", "PENDING"),
            "message": f"Template '{name}' soumis à Meta. Statut initial : {result.get('status', 'PENDING')}.",
        }
    except Exception as exc:
        if isinstance(exc, httpx.ReadTimeout):
            logger.error("skill create_template timeout: %s", exc, exc_info=True)
            return {
                "error": (
                    "Timeout réseau pendant la création du template Meta. "
                    "La requête a été retentée automatiquement; réessaie dans quelques secondes."
                )
            }
        error_msg = str(exc)
        try:
            if hasattr(exc, "response"):
                error_msg = exc.response.text  # type: ignore[union-attr]
        except Exception:
            pass
        logger.error("skill create_template failed: %s", error_msg, exc_info=True)
        return {"error": f"Échec création template: {error_msg[:300]}"}


async def _skill_list_broadcast_groups(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.broadcast_service import get_broadcast_groups, get_group_recipients

    account_id = str(account.get("id") or "")
    if not account_id:
        return {"error": "account_id manquant."}

    groups = await get_broadcast_groups(account_id)
    summaries = []
    for g in groups[:20]:
        gid = str(g.get("id") or "")
        recipients = await get_group_recipients(gid) if gid else []
        summaries.append({
            "id": gid,
            "name": g.get("name") or "(sans nom)",
            "member_count": len(recipients),
        })
    return {"total": len(summaries), "groups": summaries}


async def _skill_search_inbox_messages(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.axelia_inbox_tools import search_messages_text_for_account

    q = (args.get("query") or "").strip()
    lim_raw = args.get("limit")
    try:
        lim_i = int(lim_raw) if lim_raw is not None else 25
    except (TypeError, ValueError):
        lim_i = 25
    aid = str(account.get("id") or "")
    if not aid:
        return {"error": "Compte WABA manquant pour la recherche."}
    return await search_messages_text_for_account(aid, q, limit=lim_i)


async def _skill_get_conversation_digest(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.axelia_inbox_tools import get_conversation_digest_for_account

    cid = (args.get("conversation_id") or "").strip()
    lim_raw = args.get("max_messages")
    try:
        cap = int(lim_raw) if lim_raw is not None else 40
    except (TypeError, ValueError):
        cap = 40
    aid = str(account.get("id") or "")
    if not aid:
        return {"error": "Compte WABA manquant."}
    return await get_conversation_digest_for_account(aid, cid, max_messages=cap)


async def _skill_meta_block_contact_stub(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    _ = args, account
    return {
        "error": (
            "Le blocage Meta est réservé à la file de confirmation utilisateur dans Axelia "
            "(ne peut pas être exécuté directement ici)."
        )
    }


_SKILL_HANDLERS = {
    "list_templates": _skill_list_templates,
    "get_template_status": _skill_get_template_status,
    "create_template": _skill_create_template,
    "list_broadcast_groups": _skill_list_broadcast_groups,
    "search_inbox_messages": _skill_search_inbox_messages,
    "get_conversation_digest": _skill_get_conversation_digest,
    "meta_block_contact": _skill_meta_block_contact_stub,
}


async def execute_skill(
    skill_name: str,
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    """Exécute un skill par nom et retourne le résultat (dict JSON-serializable)."""
    handler = _SKILL_HANDLERS.get(skill_name)
    if not handler:
        return {"error": f"Skill inconnue: {skill_name}"}
    try:
        result = await handler(args or {}, account)
        logger.info(
            "playground skill %s executed (keys=%s)",
            skill_name,
            list(result.keys()) if isinstance(result, dict) else "?",
        )
        return result
    except Exception as exc:
        logger.error("playground skill %s crashed: %s", skill_name, exc, exc_info=True)
        return {"error": f"Erreur interne skill {skill_name}: {str(exc)[:200]}"}


async def execute_tool_calls(
    tool_calls: List[Dict[str, Any]],
    account: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Exécute une liste de tool_calls et retourne les résultats."""
    results = []
    for tc in tool_calls[:5]:
        skill_name = (tc.get("skill") or tc.get("name") or "").strip()
        args = tc.get("args") or tc.get("arguments") or {}
        result = await execute_skill(skill_name, args, account)
        results.append({
            "skill": skill_name,
            "result": result,
        })
    return results
