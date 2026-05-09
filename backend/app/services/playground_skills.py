"""
Registre de skills pour l'assistant Playground.

Chaque skill est une fonction que le bot peut invoquer via tool_calls dans sa réponse JSON.
Le bot ne reçoit que le catalogue (nom + description) - les données sont chargées à la demande.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.permissions import PermissionCodes
from app.services.agent_studio_service import (
    ALLOWED_AGENT_TOOLS as _AGENT_STUDIO_TOOL_SLUGS,
    SENSITIVE_AGENT_TOOLS as _AGENT_STUDIO_SENSITIVE_SLUGS,
)

logger = logging.getLogger("uvicorn.error").getChild("playground_skills")

_PARALLEL_SKILL_CALLS = 5


@dataclass(frozen=True)
class AxeliaPendingAttachment:
    """Pièce jointe vivante de la requête Axelia courante, accessible aux skills.

    Utilisé pour les flux multi-étapes (ex. créer un template avec un en-tête image :
    le skill ``prepare_template_image_header`` lit ces bytes pour les uploader
    vers Meta et obtenir un ``media_id``, sans demander à l'utilisateur de re-fournir
    le fichier).
    """

    mime_type: str
    raw_bytes: bytes
    filename: Optional[str] = None


@dataclass(frozen=True)
class AxeliaSkillsRuntime:
    """Contexte d’exécution des outils Axelia (injecté via ContextVar pendant execute_tool_calls)."""

    acting_user: Optional[Any]
    perimeter_mode: str
    pending_attachment: Optional[AxeliaPendingAttachment] = None


_axelia_skills_runtime: contextvars.ContextVar[Optional[AxeliaSkillsRuntime]] = contextvars.ContextVar(
    "_axelia_skills_runtime",
    default=None,
)


def _axelia_rt() -> Optional[AxeliaSkillsRuntime]:
    return _axelia_skills_runtime.get()


def _user_may_use_contacts_api(user: Any) -> bool:
    """Aligné sur GET /contacts : permission globale ou au moins un compte avec scope contacts."""
    if user.permissions.has(PermissionCodes.CONTACTS_VIEW):
        return True
    scoped = user.accounts_for(PermissionCodes.CONTACTS_VIEW)
    return bool(scoped)


def _skill_args_want_all_accessible(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> bool:
    scope_raw = (args.get("account_scope") or "primary").strip().lower()
    if scope_raw in ("all_accessible", "all", "tous", "tous_les_comptes"):
        return True
    aid = str(account.get("id") or "")
    rt = _axelia_rt()
    if not aid and rt and rt.perimeter_mode == "all":
        return True
    return False


def _slim_agent_studio_config_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Résumé compact pour list_agent_studio_configs (économie de tokens)."""
    from app.services.agent_studio_service import normalize_agent_config

    cfg = normalize_agent_config(row.get("config"))
    objective = cfg.get("objective") or {}
    if not isinstance(objective, dict):
        objective = {}
    pg = str(objective.get("primary_goal") or "").strip()
    routing = cfg.get("routing") or {}
    intents = routing.get("intents") if isinstance(routing, dict) else None
    intents_n = len(intents) if isinstance(intents, list) else 0
    deployment = cfg.get("deployment") or {}
    dep_st = deployment.get("status") if isinstance(deployment, dict) else None
    preview_len = 400
    if len(pg) > preview_len:
        pg_prev = pg[:preview_len] + "…"
    else:
        pg_prev = pg
    return {
        "id": str(row.get("id") or ""),
        "account_id": str(row.get("account_id") or ""),
        "name": cfg.get("name"),
        "is_default": bool(row.get("is_default")),
        "version": row.get("version"),
        "deployment_status": dep_st,
        "updated_at": row.get("updated_at"),
        "intents_count": intents_n,
        "primary_goal_preview": pg_prev,
    }


def _user_may_read_agent_studio(user: Any, account_id: str) -> bool:
    aid = str(account_id or "").strip()
    if not aid:
        return False
    return bool(
        user.permissions.has(PermissionCodes.CONVERSATIONS_VIEW, aid)
        and user.permissions.has(PermissionCodes.AGENT_STUDIO_ACCESS, aid)
    )


def _resolve_waba_credentials(account: Dict[str, Any]) -> tuple:
    """Resolve waba_id and access_token with env fallbacks."""
    waba_id = account.get("waba_id") or settings.WHATSAPP_BUSINESS_ACCOUNT_ID
    token = account.get("access_token") or settings.WHATSAPP_TOKEN
    return waba_id, token


async def _resolve_account_for_template_skills(
    account: Dict[str, Any],
    *,
    required_permission: str,
) -> Dict[str, Any]:
    """
    Résout un compte exploitable pour les skills templates.
    En mode périmètre `all`, `account` peut être vide: on choisit alors
    le premier compte autorisé par permissions qui possède waba_id + access_token.
    """
    from app.services.account_service import get_account_by_id, get_all_accounts

    if account.get("id"):
        return account

    rt = _axelia_rt()
    user = rt.acting_user if rt else None
    if not user:
        return account

    ids = user.accounts_for(required_permission)
    if ids is None:
        rows = await get_all_accounts(None)
        candidate_ids = [str(r.get("id") or "") for r in rows]
    else:
        candidate_ids = [str(i) for i in ids]

    for aid in candidate_ids[:50]:
        if not aid:
            continue
        full = await get_account_by_id(aid)
        if not full:
            continue
        if full.get("waba_id") and full.get("access_token"):
            logger.info(
                "Resolved template skill account automatically: account_id=%s permission=%s",
                aid,
                required_permission,
            )
            return full
    return account


SKILLS_CATALOG: List[Dict[str, Any]] = [
    {
        "name": "list_templates",
        "description": "Liste les templates Meta du compte (nom, langue, statut, catégorie, résumé des composants).",
        "parameters": [
            {
                "name": "account_scope",
                "type": "string",
                "required": False,
                "enum": ["primary", "all_accessible"],
            },
        ],
        "use_when": "tu dois savoir quels templates existent avant de proposer un sendTemplate.",
    },
    {
        "name": "get_template_status",
        "description": "Vérifie le statut d'un template spécifique par nom (APPROVED, PENDING, REJECTED).",
        "parameters": [
            {"name": "template_name", "type": "string", "required": True},
            {
                "name": "account_scope",
                "type": "string",
                "required": False,
                "enum": ["primary", "all_accessible"],
            },
        ],
        "use_when": "tu veux vérifier qu'un template est APPROVED avant de l'utiliser dans le graphe.",
    },
    {
        "name": "prepare_template_image_header",
        "description": (
            "Upload l'image jointe au message courant vers WhatsApp Business pour obtenir un "
            "media_id (string) à utiliser comme header_handle d'un template avec en-tête image. "
            "Aucun paramètre : on lit la PJ vivante du tour courant. "
            "Étape PRÉPARATOIRE : rien n'est encore poussé côté template - pas de carte de "
            "confirmation, c'est un appel direct dans tool_calls."
        ),
        "parameters": [],
        "use_when": (
            "l'utilisateur a joint une image (PNG ou JPEG, ≤ 5 Mo) et veut un template avec "
            "en-tête IMAGE. À appeler AVANT create_template ; le media_id retourné sert de "
            "header_handle dans components[0].example.header_handle."
        ),
    },
    {
        "name": "create_template",
        "description": (
            "Crée un nouveau template Meta (soumis à review). Retourne l'id + statut PENDING. "
            "Action sensible : tu inclus l'appel dans tool_calls avec un spec COMPLET, "
            "le backend ne déclenche l'envoi à Meta qu'après clic utilisateur sur la carte de confirmation."
        ),
        "parameters": [
            {"name": "name", "type": "string", "required": True},
            {"name": "category", "type": "string", "required": True, "enum": ["MARKETING", "UTILITY"]},
            {"name": "language", "type": "string", "required": True},
            {"name": "components", "type": "array", "required": True},
        ],
        "use_when": (
            "le template nécessaire n'existe pas. "
            "Mode « propose-puis-corrige » OBLIGATOIRE : ne pose JAMAIS le nom, la catégorie et la langue "
            "comme questions séparées. À la première intention claire de l'utilisateur, propose un spec "
            "complet (texte + nom + catégorie + langue) ; après son choix d'une variante (ou « ok »), "
            "émets directement tool_calls=[create_template(...)] avec des défauts raisonnables. "
            "Défauts : name = slug court fr ASCII (snake_case, ex. accueil_engageant_01) ; "
            "category = MARKETING pour accueil/promo/annonce, UTILITY pour confirmation/rappel/OTP/livraison/RDV ; "
            "language = 'fr' (sauf indice clair contraire). "
            "Ta `reply` doit dire : « Je crée ce template tel quel - nom: X, catégorie: Y, langue: fr. "
            "Confirme dans la carte ou dis-moi ce que tu veux changer (nom, catégorie, texte). » "
            "Si l'utilisateur corrige (« change le nom en xyz », « passe en utility », « remplace bonjour par salut »), "
            "ré-émets immédiatement create_template avec les args corrigés - ne lui repose pas la question."
        ),
    },
    {
        "name": "list_broadcast_groups",
        "description": "Liste les groupes de diffusion du compte (id, nom, nombre de membres).",
        "parameters": [
            {
                "name": "account_scope",
                "type": "string",
                "required": False,
                "enum": ["primary", "all_accessible"],
            },
        ],
        "use_when": (
            "l'utilisateur veut programmer un envoi ou cibler un groupe ; "
            "avec account_scope=all_accessible, agrège les groupes sur toutes les lignes accessibles."
        ),
    },
]

# Skills additionnels réservés au hub Axelia (inbox CRM / actions sensibles).
AXELIA_ONLY_SKILLS: List[Dict[str, Any]] = [
    {
        "name": "search_inbox_messages",
        "description": (
            "Recherche dans les messages texte du périmètre WABA (toutes conversations) "
            "pour retrouver des échanges. Avec account_scope=all_accessible, interroge "
            "chaque ligne **auxquelles l’utilisateur a accès** (conversations.view), "
            "pas la base globale. Filtre temporel optionnel via since / until "
            "(ISO 8601, sur la colonne timestamp)."
        ),
        "parameters": [
            {"name": "query", "type": "string", "required": True},
            {"name": "limit", "type": "integer", "required": False},
            {
                "name": "account_scope",
                "type": "string",
                "required": False,
                "enum": ["primary", "all_accessible"],
            },
            {
                "name": "match_mode",
                "type": "string",
                "required": False,
                "enum": ["all", "any"],
            },
            {
                "name": "since",
                "type": "string",
                "required": False,
                "description": (
                    "Borne basse ISO 8601 (ex. 2025-04-01 ou 2025-04-01T08:00:00Z). "
                    "Une date pure démarre à 00:00 UTC."
                ),
            },
            {
                "name": "until",
                "type": "string",
                "required": False,
                "description": (
                    "Borne haute ISO 8601 (ex. 2025-04-30 ou 2025-04-30T23:59:59Z). "
                    "Une date pure inclut toute la journée (23:59:59.999999 UTC)."
                ),
            },
        ],
        "use_when": (
            "l’utilisateur cherche qui a évoqué un sujet dans l’historique ; sur **toutes les lignes** "
            "visibles, passer account_scope=all_accessible. "
            "match_mode=any élargit les résultats (au moins un mot-clé) ; all exige tous les mots. "
            "Quand l’utilisateur mentionne une période (« cette semaine », « la semaine dernière », "
            "« entre le 1er et le 15 avril »…), passe explicitement since et until - calcule-les "
            "TOUJOURS depuis le bloc DATE COURANTE du prompt (jamais depuis ta connaissance "
            "d'entraînement, sinon tu produiras une plage avec une mauvaise année). "
            "Relance l’utilisateur uniquement si la plage reste ambiguë après ce calcul."
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
        "name": "summarize_contact_inbox",
        "description": (
            "Agrège les derniers messages de conversations inbox liées à un même contact "
            "(nom affiché ou numéro). "
            "Avec account_scope=primary (défaut) : une ligne WABA (sélecteur ou périmètre unique). "
            "Avec account_scope=all_accessible : **toutes les lignes auxquelles l’utilisateur a accès** "
            "(même logique que « tous les comptes » dans le CRM - filtre conversations.view), "
            "résultats structurés par compte."
        ),
        "parameters": [
            {"name": "contact_search", "type": "string", "required": True},
            {"name": "max_threads", "type": "integer", "required": False},
            {"name": "max_messages_per_thread", "type": "integer", "required": False},
            {
                "name": "account_scope",
                "type": "string",
                "required": False,
                "enum": ["primary", "all_accessible"],
            },
        ],
        "use_when": (
            "l’utilisateur veut résumer les échanges avec une personne ; "
            "sur **toutes les lignes** / « tous les comptes », utiliser account_scope=all_accessible "
            "sans demander de choisir une ligne (le serveur agrège)."
        ),
    },
    {
        "name": "search_contacts",
        "description": (
            "Recherche des contacts CRM présents sur au moins une conversation du "
            "compte WABA (nom, whatsapp_name ou numéro). "
            "Avec account_scope=all_accessible : contacts trouvés par ligne accessible "
            "(permission contacts.view)."
        ),
        "parameters": [
            {"name": "query", "type": "string", "required": True},
            {"name": "limit", "type": "integer", "required": False},
            {
                "name": "account_scope",
                "type": "string",
                "required": False,
                "enum": ["primary", "all_accessible"],
            },
        ],
        "use_when": "identifier ou désambigüiser un contact avant digest ou résumé.",
    },
    {
        "name": "get_contact",
        "description": (
            "Détails d’un contact (UUID) pour la ligne WABA courante : nom, numéros, "
            "nombre de conversations sur ce compte."
        ),
        "parameters": [
            {"name": "contact_id", "type": "string", "required": True},
        ],
        "use_when": "après search_contacts ou quand l’utilisateur fournit un contact_id CRM.",
    },
    {
        "name": "list_recent_conversations",
        "description": (
            "Liste les conversations inbox récentes (tri updated_at), avec extrait métadonnées "
            "contact / statut. account_scope=all_accessible pour un panorama multi-lignes."
        ),
        "parameters": [
            {"name": "limit", "type": "integer", "required": False},
            {
                "name": "account_scope",
                "type": "string",
                "required": False,
                "enum": ["primary", "all_accessible"],
            },
        ],
        "use_when": "l’utilisateur veut voir les derniers fils sans mot-clé ou choisir un conversation_id.",
    },
    {
        "name": "find_satisfied_contacts",
        "description": (
            "Détecte les contacts qui expriment une satisfaction récente (signaux implicites "
            "dans leurs messages entrants), avec score + extraits de preuve. "
            "account_scope=all_accessible agrège sur toutes les lignes accessibles."
        ),
        "parameters": [
            {"name": "days", "type": "integer", "required": False},
            {"name": "limit", "type": "integer", "required": False},
            {
                "name": "account_scope",
                "type": "string",
                "required": False,
                "enum": ["primary", "all_accessible"],
            },
        ],
        "use_when": (
            "l’utilisateur pose une question implicite sur la satisfaction "
            "(ex. « qui était content récemment ? ») sans mots-clés stricts."
        ),
    },
    {
        "name": "list_broadcast_campaigns",
        "description": (
            "Liste les campagnes de diffusion du compte (aperçu contenu, statut, "
            "compteurs livraison). Lecture seule. all_accessible itère les comptes permis."
        ),
        "parameters": [
            {"name": "limit", "type": "integer", "required": False},
            {
                "name": "account_scope",
                "type": "string",
                "required": False,
                "enum": ["primary", "all_accessible"],
            },
        ],
        "use_when": "analyser ou comparer les envois de masse récents.",
    },
    {
        "name": "get_campaign_summary",
        "description": (
            "Statistiques détaillées d’une campagne (UUID) : vue d’ensemble + échantillon "
            "des destinataires. Compte imposé par le campaign_id."
        ),
        "parameters": [
            {"name": "campaign_id", "type": "string", "required": True},
        ],
        "use_when": "après list_broadcast_campaigns ou quand l’utilisateur cite un UUID de campagne.",
    },
    {
        "name": "get_whatsapp_business_profile",
        "description": (
            "Lit le profil business WhatsApp affiché sur la ligne (about, sites, vertical…) "
            "via l’API Meta. Une ligne WABA sélectionnée est requise."
        ),
        "parameters": [],
        "use_when": "questions sur l’identité publique du numéro ou cohérence du messaging.",
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
    {
        "name": "list_agent_studio_configs",
        "description": (
            "Liste les configurations Agent Studio du ou des comptes WABA autorisés "
            "(lecture seule, sans confirmation UI). Retourne pour chaque agent : id, nom, "
            "statut de déploiement (ex. draft), indicateur agent par défaut, extrait d’objectif. "
            "Avec account_scope=all_accessible, parcourt les lignes où l’utilisateur a à la fois "
            "conversations.view et agent_studio.access."
        ),
        "parameters": [
            {
                "name": "account_scope",
                "type": "string",
                "required": False,
                "enum": ["primary", "all_accessible"],
            },
            {
                "name": "account_id",
                "type": "string",
                "required": False,
            },
        ],
        "use_when": (
            "l’utilisateur veut voir quels agents existent, un inventaire, comparer les lignes, "
            "ou avant une modification ; en mode « tous les comptes », utilise account_scope=all_accessible "
            "ou un account_id du bloc périmètre."
        ),
    },
    {
        "name": "get_agent_studio_config",
        "description": (
            "Charge la configuration Agent Studio complète (JSON normalisé) pour un config_id UUID, "
            "plus les anomalies de validation connues du schéma Studio. Lecture seule, sans confirmation UI."
        ),
        "parameters": [
            {"name": "config_id", "type": "string", "required": True},
        ],
        "use_when": (
            "après list_agent_studio_configs ou lorsque l’utilisateur fournit un UUID de configuration ; "
            "pour expliquer en détail objectifs, intents, politiques, outils autorisés."
        ),
    },
    {
        "name": "upsert_agent_studio_routing",
        "description": (
            "Met à jour la partie **règles / routage** d’un agent Studio existant (brouillon ou non) : "
            "intentions (`intents` : key, handler, description, min_confidence optionnel), "
            "stratégie de **fallback** (`human` | `safe_reply` | `ask_clarification`), "
            "**seuil de confiance**, liste **forbidden_actions**. "
            "Nécessite un `config_id` existant. "
            "Action sensible : exécution uniquement après confirmation dans l’UI ; "
            "validation serveur identique à Agent Studio."
        ),
        "parameters": [
            {"name": "config_id", "type": "string", "required": True},
            {"name": "account_id", "type": "string", "required": False},
            {"name": "intents", "type": "array", "required": False},
            {
                "name": "replace_intents",
                "type": "boolean",
                "required": False,
            },
            {
                "name": "fallback",
                "type": "string",
                "required": False,
            },
            {
                "name": "confidence_threshold",
                "type": "number",
                "required": False,
            },
            {"name": "forbidden_actions", "type": "array", "required": False},
        ],
        "use_when": (
            "l’utilisateur veut ajouter ou modifier des intentions (« si le client dit X… »), "
            "le fallback, le seuil de confiance ou les actions interdites ; "
            "après `list_agent_studio_configs` ou `get_agent_studio_config` pour obtenir `config_id`. "
            "`replace_intents` true (défaut) remplace toute la liste ; false fusionne par `key`. "
            "En périmètre multi-comptes, passe `account_id` comme pour upsert_agent_studio_config."
        ),
    },
    {
        "name": "upsert_agent_studio_config",
        "description": (
            "Crée ou met à jour une configuration Agent Studio pour une ligne WABA précise. "
            "La configuration est sauvegardée en mode **brouillon (draft)** : elle n'est jamais "
            "déployée sans une activation manuelle dans Agent Studio (statut deployment.status='draft'). "
            "Action sensible : exécution uniquement après validation humaine dans l'UI. "
            "ATTENTION : `allowed_tools` et `require_approval_for` n'acceptent QUE des slugs "
            "techniques d'outils (voir liste ci-dessous), jamais des libellés métier en français "
            "(p. ex. « Ajustements de facturation », « Litiges graves » sont invalides). "
            "Pour une politique d'escalade humaine sur des thèmes métier, décris-la dans `primary_goal` "
            "ou `audience` (texte libre) - pas dans ces deux champs."
        ),
        "parameters": [
            {"name": "config_id", "type": "string", "required": False},
            {"name": "name", "type": "string", "required": True},
            {"name": "primary_goal", "type": "string", "required": True},
            {"name": "kpi", "type": "array", "required": False},
            {"name": "audience", "type": "string", "required": False},
            {"name": "allowed_tools", "type": "array", "required": False},
            {"name": "require_approval_for", "type": "array", "required": False},
            {"name": "make_default", "type": "boolean", "required": False},
            {
                "name": "account_id",
                "type": "string",
                "required": False,
            },
        ],
        "use_when": (
            "l'utilisateur demande de créer ou modifier un agent Studio ; proposer les changements "
            "puis demander confirmation via la carte d'approbation. "
            "Si le périmètre courant est « tous les comptes » mais qu'une ligne WABA précise a été "
            "identifiée pendant la conversation (nom, téléphone, UUID dans le bloc périmètre), "
            "**inclus l'`account_id` de cette ligne dans les args** : la carte de validation utilisera "
            "directement ce compte sans demander à l'utilisateur de changer de périmètre. "
            "Précise toujours dans la `reply` que la configuration sera enregistrée en **brouillon** "
            "et qu'elle reste à activer manuellement dans Agent Studio. "
            "Si l'utilisateur évoque des cas métier d'escalade (« approbation pour facturation », "
            "« litiges graves » …), ne les place PAS dans `require_approval_for` : intègre-les "
            "à `primary_goal` (ex. « ... escalade vers un humain pour facturation, litiges graves »)."
        ),
    },
]


def get_axelia_skills_prompt_section() -> str:
    """Texte injecté pour Axelia : catalogue skills + JSON (reply, tool_calls, task_plan optionnel)."""
    lines = [
        "OUTILS DISPONIBLES (skills) - Playground + inbox CRM Axelia :",
        "Tu réponds par un **unique** objet JSON ( MIME application/json ) avec les champs :",
        '  {"reply": "<texte visible pour l’utilisateur>", "tool_calls": [], "task_plan": []}',
        'task_plan optionnel ; objets '
        '{"id","title","thought","status","skill"} - tu peux l’omettre ou le laisser vide : '
        "**le serveur génère alors automatiquement** la liste affichée à partir des tool_calls "
        '(titres UX). Tu peux fournir un task_plan uniquement pour des libellés sur mesure. '
        "Jusqu’à 5 tool_calls du même tour s’exécutent **en parallèle**.",
        'Chaque entrée de tool_calls : {"skill": "nom_du_skill", "args": { ... } }',
        "Le backend exécute les skills et te renvoie les résultats dans un message suivant.",
        "Ne devine pas les noms de templates, groupes ou UUID : appelle les skills.",
        "Pour create_template, meta_block_contact, upsert_agent_studio_config et upsert_agent_studio_routing : "
        "confirmation utilisateur obligatoire dans l’UI "
        "(tu inclus tool_calls avec les args ; tu n’exécutes pas toi‑même l’action sensible).",
        "Tu agis dans le périmètre décrit dans le bloc « CONTEXTE PÉRIMÈTRE CRM » du prompt système. "
        "Si une **ligne unique** est sélectionnée, les outils inbox utilisent ce compte. "
        "Si le bloc indique **tous les comptes auxquels l’utilisateur a accès**, "
        "tu peux quand même résumer ou rechercher **sur toutes ces lignes** avec "
        "`account_scope: \"all_accessible\"` sur `search_inbox_messages` et `summarize_contact_inbox` "
        "(agrégation et timeouts côté serveur - ne refuse pas sous prétexte « une ligne à la fois »). "
        "Pour les actions Meta (templates, blocage) ou pour un résumé volontairement limité à une ligne, "
        "reste sur le compte courant ou demande la précision si l’UI ne l’a pas encore fixée. "
        "Pour upsert_agent_studio_config en mode « Tous les comptes » : ne demande pas à l'utilisateur "
        "de changer le sélecteur en haut de l'écran ; passe simplement l'`account_id` cible dans les "
        "args du tool_call et précise dans la reply que l'agent sera créé en **brouillon**.",
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
        "- Templates (création) : mode PROPOSE-PUIS-CORRIGE strict.",
        "  1) D'abord list_templates si pertinent (vérifier qu'aucun template équivalent n'existe).",
        "  2) Tour 1 - propose (sans appel) 2 ou 3 variantes complètes : pour chacune, donne le texte ET un "
        "spec complet (nom suggéré, catégorie suggérée, langue) ; ne pose AUCUNE question ouverte de type "
        "« quel nom ? » ou « quelle catégorie ? ».",
        "  3) Dès que l'utilisateur choisit une variante (« option 1 », « la 2e », « ok pour celle-là », "
        "« va pour ce texte »…) OU accepte la proposition unique, ÉMETS IMMÉDIATEMENT "
        "tool_calls=[create_template(name, category, language='fr', components)] avec des défauts "
        "raisonnables. La carte UI sert de validation finale ; n'enchaîne PAS un tour intermédiaire.",
        "  4) Défauts : name = slug ASCII snake_case (accueil_engageant_01, suivi_commande_01…) ; "
        "category = MARKETING pour engagement/promo/annonce, UTILITY pour confirmation/rappel/OTP/RDV ; "
        "language = 'fr'.",
        "  5) La `reply` accompagnant l'appel doit être brève : « Je crée ce template tel quel - nom: X, "
        "catégorie: Y, langue: fr. Confirme dans la carte ci-dessous, ou dis-moi ce que tu veux changer "
        "(nom, catégorie, texte). »",
        "  6) Correction utilisateur (« change le nom en xyz », « passe en utility », « remplace bonjour "
        "par salut ») → RÉ-ÉMETS create_template avec les args corrigés dans le même format ; ne repose "
        "pas la question. Ne demande une précision que si la correction est ambiguë.",
        "- Templates avec en-tête IMAGE (PNG/JPEG ≤ 5 Mo) :",
        "  a) Si l'utilisateur a joint une image au tour courant ET qu'il veut un en-tête image : "
        "appelle d'abord prepare_template_image_header (sans args) dans tool_calls - c'est un appel "
        "non-sensible, exécuté directement, qui retourne {success, media_id}.",
        "  b) Au tour suivant, utilise ce media_id dans le spec components du create_template : "
        "components = [{type:'HEADER', format:'IMAGE', example:{header_handle:[<media_id>]}}, "
        "{type:'BODY', text:'...'}]. Ne tente JAMAIS d'inventer un media_id.",
        "  c) Si l'utilisateur veut un en-tête image MAIS n'a pas joint de fichier : demande-lui "
        "de joindre une image PNG ou JPEG (≤ 5 Mo) avant d'appeler prepare_template_image_header.",
        "  d) Si prepare_template_image_header échoue (PJ manquante, format invalide, taille…), "
        "explique l'erreur à l'utilisateur en français et propose de réessayer ; ne crée pas le "
        "template avec un faux handle.",
        "- Campagnes / ciblage : list_broadcast_groups ; list_broadcast_campaigns / get_campaign_summary pour les envois.",
        "- Contacts : search_contacts puis get_contact ou summarize_contact_inbox.",
        "- Inbox : search_inbox_messages (match_mode=any pour élargir ; account_scope=all_accessible si multi-lignes ; "
        "since/until ISO pour borner par dates - ex. since=2025-04-01, until=2025-04-30) ; "
        "summarize_contact_inbox idem pour résumé contact multi-lignes.",
        "- Conversations récentes sans mot-clé : list_recent_conversations.",
        "- Profil WhatsApp public : get_whatsapp_business_profile sur une ligne sélectionnée.",
        "- Résumés : get_conversation_digest une fois conversation_id connu ; "
        "summarize_contact_inbox (all_accessible pour toutes les lignes permises).",
        "- Blocage Meta : meta_block_contact seulement avec contact_id réel ; jamais sans confirmation UI.",
        "- Agent Studio (lecture, sans carte de confirmation) : `list_agent_studio_configs` pour inventorier "
        "les agents (résumé par ligne ; account_scope=all_accessible ou account_id explicite en mode multi-comptes) ; "
        "`get_agent_studio_config` pour la fiche complète + anomalies de validation quand tu as un config_id UUID. "
        "**Ne dis pas** que tu ne peux pas lister ou lire les configurations si l'utilisateur a l'accès Studio.",
        "- Agent Studio (écriture) : upsert_agent_studio_config crée/met à jour l'en-tête (objectif, outils…) en **brouillon** ; "
            "upsert_agent_studio_routing met à jour les **règles de routage** (intents, fallback, seuil, forbidden_actions) "
            "sur un config_id existant — même **carte de confirmation**, aucun déploiement auto "
            "(deployment.status inchangé sauf si déjà défini côté UI). "
        "En mode « Tous les comptes », si une ligne WABA précise est identifiable (nom, UUID dans le bloc périmètre), "
        "passe son `account_id` dans les args : ne demande PAS à l'utilisateur de changer le sélecteur en haut "
        "de l'écran avant de valider, la carte d'approbation utilisera ce `account_id` directement. "
        "Indique clairement dans la `reply` : « configuration enregistrée en brouillon, à activer ensuite "
        "depuis Agent Studio » pour rassurer l'utilisateur. "
        "`allowed_tools` et `require_approval_for` n'acceptent QUE les slugs techniques suivants : "
        + ", ".join(sorted(_AGENT_STUDIO_TOOL_SLUGS))
        + " (outils sensibles obligatoires dans `require_approval_for` s'ils sont dans `allowed_tools` : "
        + ", ".join(sorted(_AGENT_STUDIO_SENSITIVE_SLUGS))
        + "). Tout libellé métier en français (« Ajustements de facturation », « Litiges graves »...) y "
        "est INVALIDE et fera échouer la validation : place ces consignes dans `primary_goal` à la place.",
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
    from app.services.whatsapp_api_service import (
        WhatsAppAPIError,
        list_message_templates,
    )
    from app.services.account_service import get_account_by_id

    async def _fetch_templates_for_account(acct: Dict[str, Any]) -> Dict[str, Any]:
        waba_id, token = _resolve_waba_credentials(acct)
        if not waba_id or not token:
            account_id = str(acct.get("id") or "")
            has_waba = bool(acct.get("waba_id"))
            has_token = bool(acct.get("access_token"))
            logger.warning(
                "skill list_templates missing credentials: account_id=%s has_waba_id=%s has_access_token=%s",
                account_id,
                has_waba,
                has_token,
            )
            return {
                "error": "Compte sans waba_id ou access_token configuré.",
                "diagnostic": {
                    "account_id": account_id or None,
                    "has_waba_id": has_waba,
                    "has_access_token": has_token,
                },
                "templates": [],
            }

        all_tpls: List[Dict[str, Any]] = []
        cursor_after: Optional[str] = None
        try:
            for _ in range(10):
                batch = await list_message_templates(str(waba_id), token, limit=100, after=cursor_after)
                chunk = batch.get("data") or []
                if not chunk:
                    break
                all_tpls.extend(chunk)
                cursor_after = (batch.get("paging") or {}).get("cursors", {}).get("after")
                if not cursor_after:
                    break
        except WhatsAppAPIError as exc:
            logger.warning(
                "skill list_templates Meta error: account_id=%s waba_id=%s error=%s",
                str(acct.get("id") or ""),
                str(waba_id),
                str(exc),
            )
            return {
                "error": f"Erreur Meta lors du listing templates: {str(exc)[:220]}",
                "diagnostic": {
                    "account_id": str(acct.get("id") or "") or None,
                    "waba_id": str(waba_id),
                },
                "templates": [],
            }
        return {"templates": [_summarize_template(t) for t in all_tpls]}

    if _skill_args_want_all_accessible(args, account):
        rt = _axelia_rt()
        if not rt or not rt.acting_user:
            return {"error": "Listing templates multi-lignes : contexte utilisateur indisponible."}
        ids = rt.acting_user.accounts_for(PermissionCodes.MESSAGES_VIEW)
        candidate_ids = [str(i) for i in (ids or []) if str(i).strip()]
        if not candidate_ids:
            return {"total": 0, "templates": [], "accounts": []}

        all_templates: List[Dict[str, Any]] = []
        bundles: List[Dict[str, Any]] = []
        for aid in candidate_ids[:50]:
            full = await get_account_by_id(aid)
            if not full:
                continue
            account_name = str(full.get("name") or "").strip() or None
            account_phone = str(full.get("phone_number") or "").strip() or None
            fetched = await _fetch_templates_for_account(full)
            scoped_templates = [
                {
                    **row,
                    "account_id": aid,
                    "account_name": account_name,
                    "account_phone": account_phone,
                }
                for row in fetched.get("templates") or []
            ]
            all_templates.extend(scoped_templates)
            bundle: Dict[str, Any] = {
                "account_id": aid,
                "account_name": account_name,
                "account_phone": account_phone,
                "total": len(fetched.get("templates") or []),
                "templates": fetched.get("templates") or [],
            }
            if fetched.get("error"):
                bundle["error"] = fetched.get("error")
                if fetched.get("diagnostic"):
                    bundle["diagnostic"] = fetched.get("diagnostic")
            bundles.append(bundle)
        return {"total": len(all_templates), "templates": all_templates, "accounts": bundles}

    account = await _resolve_account_for_template_skills(
        account,
        required_permission=PermissionCodes.MESSAGES_VIEW,
    )
    fetched = await _fetch_templates_for_account(account)
    if fetched.get("error"):
        return {
            "error": fetched.get("error"),
            "diagnostic": fetched.get("diagnostic"),
        }
    templates = fetched.get("templates") or []
    return {
        "total": len(templates),
        "templates": templates,
    }


async def _skill_get_template_status(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.whatsapp_api_service import (
        WhatsAppAPIError,
        list_message_templates,
    )
    from app.services.account_service import get_account_by_id

    template_name = (args.get("template_name") or "").strip()
    if not template_name:
        return {"error": "template_name requis."}

    async def _matches_for_account(acct: Dict[str, Any]) -> Dict[str, Any]:
        waba_id, token = _resolve_waba_credentials(acct)
        if not waba_id or not token:
            return {
                "error": "Compte sans waba_id ou access_token configuré.",
                "diagnostic": {
                    "account_id": str(acct.get("id") or "") or None,
                    "has_waba_id": bool(acct.get("waba_id")),
                    "has_access_token": bool(acct.get("access_token")),
                },
                "matches": [],
            }

        all_tpls: List[Dict[str, Any]] = []
        cursor_after: Optional[str] = None
        try:
            for _ in range(10):
                batch = await list_message_templates(str(waba_id), token, limit=100, after=cursor_after)
                chunk = batch.get("data") or []
                if not chunk:
                    break
                all_tpls.extend(chunk)
                cursor_after = (batch.get("paging") or {}).get("cursors", {}).get("after")
                if not cursor_after:
                    break
        except WhatsAppAPIError as exc:
            logger.warning(
                "skill get_template_status Meta error: account_id=%s template=%s waba_id=%s error=%s",
                str(acct.get("id") or ""),
                template_name,
                str(waba_id),
                str(exc),
            )
            return {
                "error": f"Erreur Meta lors de la lecture du template: {str(exc)[:220]}",
                "diagnostic": {
                    "account_id": str(acct.get("id") or "") or None,
                    "waba_id": str(waba_id),
                    "template_name": template_name,
                },
                "matches": [],
            }
        matches = [t for t in all_tpls if t.get("name") == template_name]
        return {"matches": [_summarize_template(t) for t in matches]}

    if _skill_args_want_all_accessible(args, account):
        rt = _axelia_rt()
        if not rt or not rt.acting_user:
            return {"error": "Statut template multi-lignes : contexte utilisateur indisponible."}
        ids = rt.acting_user.accounts_for(PermissionCodes.MESSAGES_VIEW)
        candidate_ids = [str(i) for i in (ids or []) if str(i).strip()]
        if not candidate_ids:
            return {"found": False, "matches": [], "accounts": []}

        scoped_matches: List[Dict[str, Any]] = []
        accounts_out: List[Dict[str, Any]] = []
        for aid in candidate_ids[:50]:
            full = await get_account_by_id(aid)
            if not full:
                continue
            account_name = str(full.get("name") or "").strip() or None
            account_phone = str(full.get("phone_number") or "").strip() or None
            res = await _matches_for_account(full)
            rows = res.get("matches") or []
            scoped_rows = [
                {
                    **row,
                    "account_id": aid,
                    "account_name": account_name,
                    "account_phone": account_phone,
                }
                for row in rows
            ]
            scoped_matches.extend(scoped_rows)
            bundle: Dict[str, Any] = {
                "account_id": aid,
                "account_name": account_name,
                "account_phone": account_phone,
                "found": bool(rows),
                "matches": rows,
            }
            if res.get("error"):
                bundle["error"] = res.get("error")
                if res.get("diagnostic"):
                    bundle["diagnostic"] = res.get("diagnostic")
            accounts_out.append(bundle)
        if not scoped_matches:
            return {
                "found": False,
                "message": f"Aucun template nommé '{template_name}' trouvé.",
                "matches": [],
                "accounts": accounts_out,
            }
        return {"found": True, "matches": scoped_matches, "accounts": accounts_out}

    account = await _resolve_account_for_template_skills(
        account,
        required_permission=PermissionCodes.MESSAGES_VIEW,
    )
    res = await _matches_for_account(account)
    if res.get("error"):
        return {
            "error": res.get("error"),
            "diagnostic": res.get("diagnostic"),
        }
    matches = res.get("matches") or []
    if not matches:
        return {"found": False, "message": f"Aucun template nommé '{template_name}' trouvé."}

    return {
        "found": True,
        "matches": matches,
    }


async def _skill_create_template(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.whatsapp_api_service import create_message_template

    account = await _resolve_account_for_template_skills(
        account,
        required_permission=PermissionCodes.MESSAGES_SEND,
    )
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


_TEMPLATE_HEADER_IMAGE_MIMES = {"image/jpeg", "image/png"}
_TEMPLATE_HEADER_MAX_BYTES = 5 * 1024 * 1024  # Limite Meta côté upload media (5 Mo)


async def _skill_prepare_template_image_header(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    """Upload l'image jointe au tour courant vers l'API WhatsApp Business pour
    obtenir un ``media_id`` réutilisable comme ``header_handle`` lors de la
    création d'un template Meta avec en-tête image.

    Le skill ne prend aucun paramètre : il lit la pièce jointe vivante via
    ``AxeliaSkillsRuntime.pending_attachment``. Le modèle l'appelle juste avant
    ``create_template`` quand l'utilisateur a joint une image et veut un en-tête
    image. Côté UI il n'y a pas de carte de confirmation : c'est une étape
    technique préparatoire (rien n'est encore poussé sur Meta côté template).
    """
    _ = args  # paramètres ignorés pour ce skill
    from app.services.whatsapp_api_service import upload_media_from_bytes

    rt = _axelia_rt()
    if not rt or rt.pending_attachment is None:
        return {
            "error": (
                "Aucune image jointe au message courant. Demande à l'utilisateur de joindre "
                "une image (PNG ou JPEG, ≤ 5 Mo) puis relance ce skill."
            ),
        }

    pa = rt.pending_attachment
    mime = (pa.mime_type or "").strip().lower()
    if mime not in _TEMPLATE_HEADER_IMAGE_MIMES:
        return {
            "error": (
                f"Format `{mime or 'inconnu'}` non accepté pour un en-tête image. "
                "Meta accepte uniquement image/jpeg ou image/png pour les templates."
            ),
        }
    if not pa.raw_bytes:
        return {"error": "La pièce jointe est vide."}
    if len(pa.raw_bytes) > _TEMPLATE_HEADER_MAX_BYTES:
        return {
            "error": (
                f"Image trop volumineuse ({len(pa.raw_bytes)} octets). "
                "Limite Meta : 5 Mo. Demande à l'utilisateur de la compresser."
            ),
        }

    account = await _resolve_account_for_template_skills(
        account,
        required_permission=PermissionCodes.MESSAGES_SEND,
    )
    waba_id, token = _resolve_waba_credentials(account)
    if not waba_id or not token:
        return {"error": "Compte sans waba_id ou access_token configuré."}
    phone_number_id = (account.get("phone_number_id") or "").strip()
    if not phone_number_id:
        return {
            "error": (
                "phone_number_id manquant sur la ligne sélectionnée - impossible "
                "d'uploader le média vers WhatsApp Business."
            ),
        }

    filename = pa.filename or ("template_header.png" if mime == "image/png" else "template_header.jpg")
    try:
        result = await upload_media_from_bytes(
            phone_number_id=phone_number_id,
            access_token=token,
            file_content=pa.raw_bytes,
            filename=filename,
            mime_type=mime,
        )
    except Exception as exc:
        error_msg = str(exc)
        try:
            if hasattr(exc, "response"):
                error_msg = exc.response.text  # type: ignore[union-attr]
        except Exception:
            pass
        logger.error("skill prepare_template_image_header failed: %s", error_msg, exc_info=True)
        return {"error": f"Échec upload image vers Meta: {error_msg[:300]}"}

    media_id = (result or {}).get("id")
    if not media_id:
        return {"error": "Meta n'a pas renvoyé de media_id pour cette image."}

    return {
        "success": True,
        "media_id": str(media_id),
        "mime_type": mime,
        "size_bytes": len(pa.raw_bytes),
        "usage_hint": (
            "Utilise ce media_id comme valeur de `components[0].example.header_handle[0]` "
            "dans l'appel suivant à `create_template` (avec components[0]={type:'HEADER', "
            "format:'IMAGE', example:{header_handle:[<media_id>]}})."
        ),
    }


async def _skill_list_broadcast_groups(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.broadcast_service import get_broadcast_groups, get_group_recipients
    from app.services.account_service import get_account_by_id

    async def _summaries_for_account(account_id: str) -> List[Dict[str, Any]]:
        groups = await get_broadcast_groups(account_id)
        summaries: List[Dict[str, Any]] = []
        for g in groups[:20]:
            gid = str(g.get("id") or "")
            recipients = await get_group_recipients(gid) if gid else []
            summaries.append({
                "id": gid,
                "name": g.get("name") or "(sans nom)",
                "member_count": len(recipients),
            })
        return summaries

    if _skill_args_want_all_accessible(args, account):
        rt = _axelia_rt()
        if not rt or not rt.acting_user:
            return {"error": "Listing multi-lignes : contexte utilisateur indisponible."}
        ids = rt.acting_user.accounts_for(PermissionCodes.MESSAGES_VIEW)
        candidate_ids = [str(i) for i in (ids or []) if str(i).strip()]
        if not candidate_ids:
            return {"total": 0, "groups": [], "accounts": []}

        account_bundles: List[Dict[str, Any]] = []
        merged_groups: List[Dict[str, Any]] = []
        for aid in candidate_ids[:50]:
            full = await get_account_by_id(aid)
            account_name = str((full or {}).get("name") or "").strip() or None
            account_phone = str((full or {}).get("phone_number") or "").strip() or None
            summaries = await _summaries_for_account(aid)
            for row in summaries:
                merged_groups.append({
                    **row,
                    "account_id": aid,
                    "account_name": account_name,
                    "account_phone": account_phone,
                })
            account_bundles.append({
                "account_id": aid,
                "account_name": account_name,
                "account_phone": account_phone,
                "total": len(summaries),
                "groups": summaries,
            })
        return {
            "total": len(merged_groups),
            "groups": merged_groups,
            "accounts": account_bundles,
        }

    account_id = str(account.get("id") or "")
    if not account_id:
        return {"error": "account_id manquant."}
    summaries = await _summaries_for_account(account_id)
    return {"total": len(summaries), "groups": summaries}


async def _skill_search_inbox_messages(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.axelia_inbox_tools import (
        parse_iso_datetime,
        search_messages_all_accessible_accounts,
        search_messages_text_for_account,
    )

    q = (args.get("query") or "").strip()
    lim_raw = args.get("limit")
    try:
        lim_i = int(lim_raw) if lim_raw is not None else 25
    except (TypeError, ValueError):
        lim_i = 25

    mm_raw = (args.get("match_mode") or "all").strip().lower()
    match_mode = mm_raw if mm_raw in ("all", "any") else "all"

    # Plage de dates optionnelle (ISO 8601). On prévalide ici pour pouvoir signaler
    # explicitement à l'utilisateur que la valeur est invalide plutôt que la silencer.
    since_raw = args.get("since")
    until_raw = args.get("until")
    if since_raw and parse_iso_datetime(since_raw) is None:
        return {
            "error": (
                "Paramètre `since` invalide : utiliser ISO 8601 "
                "(ex. 2025-04-01 ou 2025-04-01T08:00:00Z)."
            ),
            "hits": [],
        }
    if until_raw and parse_iso_datetime(until_raw, end_of_day=True) is None:
        return {
            "error": (
                "Paramètre `until` invalide : utiliser ISO 8601 "
                "(ex. 2025-04-30 ou 2025-04-30T23:59:59Z)."
            ),
            "hits": [],
        }

    if _skill_args_want_all_accessible(args, account):
        rt = _axelia_rt()
        if not rt or not rt.acting_user:
            return {"error": "Recherche multi-lignes : contexte utilisateur indisponible."}
        return await search_messages_all_accessible_accounts(
            rt.acting_user,
            q,
            limit_per_account=lim_i,
            match_mode=match_mode,
            since=since_raw,
            until=until_raw,
        )

    aid = str(account.get("id") or "")
    if not aid:
        return {"error": "Compte WABA manquant pour la recherche."}
    return await search_messages_text_for_account(
        aid,
        q,
        limit=lim_i,
        match_mode=match_mode,
        since=since_raw,
        until=until_raw,
    )


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


async def _skill_summarize_contact_inbox(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.axelia_inbox_tools import (
        summarize_contact_inbox_all_accessible_accounts,
        summarize_contact_inbox_for_account,
    )

    q = (args.get("contact_search") or args.get("query") or "").strip()
    try:
        mt = int(args.get("max_threads")) if args.get("max_threads") is not None else 8
    except (TypeError, ValueError):
        mt = 8
    try:
        mm = (
            int(args.get("max_messages_per_thread"))
            if args.get("max_messages_per_thread") is not None
            else 35
        )
    except (TypeError, ValueError):
        mm = 35

    if _skill_args_want_all_accessible(args, account):
        rt = _axelia_rt()
        if not rt or not rt.acting_user:
            return {"error": "Synthèse multi-lignes : contexte utilisateur indisponible."}
        return await summarize_contact_inbox_all_accessible_accounts(
            rt.acting_user,
            q,
            max_threads=mt,
            max_messages_per_thread=mm,
        )

    aid = str(account.get("id") or "")
    if not aid:
        return {"error": "Compte WABA manquant."}
    return await summarize_contact_inbox_for_account(
        aid, q, max_threads=mt, max_messages_per_thread=mm
    )


async def _skill_search_contacts(args: Dict[str, Any], account: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.axelia_crm_tools import (
        search_contacts_all_accessible_accounts,
        search_contacts_for_account,
    )

    q = (args.get("query") or "").strip()
    lim_raw = args.get("limit")
    try:
        lim_i = int(lim_raw) if lim_raw is not None else 15
    except (TypeError, ValueError):
        lim_i = 15

    rt = _axelia_rt()
    if not rt or not rt.acting_user:
        return {"error": "Contexte utilisateur indisponible pour les contacts."}
    if not _user_may_use_contacts_api(rt.acting_user):
        return {"error": "Permission contacts.view requise."}

    if _skill_args_want_all_accessible(args, account):
        return await search_contacts_all_accessible_accounts(
            rt.acting_user,
            q,
            limit_per_account=lim_i,
        )

    aid = str(account.get("id") or "")
    if not aid:
        return {"error": "Compte WABA manquant."}
    return await search_contacts_for_account(aid, q, limit=lim_i)


async def _skill_get_contact(args: Dict[str, Any], account: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.axelia_crm_tools import get_contact_detail_for_account

    rt = _axelia_rt()
    if not rt or not rt.acting_user:
        return {"error": "Contexte utilisateur indisponible."}
    if not _user_may_use_contacts_api(rt.acting_user):
        return {"error": "Permission contacts.view requise."}

    cid = (args.get("contact_id") or "").strip()
    aid = str(account.get("id") or "")
    if not aid:
        return {"error": "Compte WABA manquant."}
    return await get_contact_detail_for_account(aid, cid)


async def _skill_list_recent_conversations(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.axelia_crm_tools import (
        list_recent_conversations_all_accessible,
        list_recent_conversations_for_account,
    )

    lim_raw = args.get("limit")
    try:
        lim_i = int(lim_raw) if lim_raw is not None else 25
    except (TypeError, ValueError):
        lim_i = 25

    rt = _axelia_rt()
    if _skill_args_want_all_accessible(args, account):
        if not rt or not rt.acting_user:
            return {"error": "Contexte utilisateur indisponible."}
        return await list_recent_conversations_all_accessible(
            rt.acting_user,
            limit_per_account=min(lim_i, 35),
        )

    aid = str(account.get("id") or "")
    if not aid:
        return {"error": "Compte WABA manquant."}
    return await list_recent_conversations_for_account(aid, limit=lim_i)


async def _skill_find_satisfied_contacts(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.axelia_inbox_tools import (
        find_satisfied_contacts_all_accessible_accounts,
        find_satisfied_contacts_for_account,
    )

    days_raw = args.get("days")
    limit_raw = args.get("limit")
    try:
        days_i = int(days_raw) if days_raw is not None else 30
    except (TypeError, ValueError):
        days_i = 30
    try:
        lim_i = int(limit_raw) if limit_raw is not None else 12
    except (TypeError, ValueError):
        lim_i = 12

    if _skill_args_want_all_accessible(args, account):
        rt = _axelia_rt()
        if not rt or not rt.acting_user:
            return {"error": "Analyse satisfaction multi-lignes : contexte utilisateur indisponible."}
        return await find_satisfied_contacts_all_accessible_accounts(
            rt.acting_user,
            days=days_i,
            limit_per_account=min(lim_i, 20),
        )

    aid = str(account.get("id") or "")
    if not aid:
        return {"error": "Compte WABA manquant."}
    return await find_satisfied_contacts_for_account(
        aid,
        days=days_i,
        limit=lim_i,
    )


async def _skill_list_broadcast_campaigns(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.axelia_crm_tools import (
        list_broadcast_campaigns_all_accessible,
        list_broadcast_campaigns_for_account,
    )

    lim_raw = args.get("limit")
    try:
        lim_i = int(lim_raw) if lim_raw is not None else 25
    except (TypeError, ValueError):
        lim_i = 25

    rt = _axelia_rt()
    if _skill_args_want_all_accessible(args, account):
        if not rt or not rt.acting_user:
            return {"error": "Contexte utilisateur indisponible."}
        return await list_broadcast_campaigns_all_accessible(
            rt.acting_user,
            limit_per_account=min(lim_i, 30),
        )

    aid = str(account.get("id") or "")
    if not aid:
        return {"error": "Compte WABA manquant."}
    return await list_broadcast_campaigns_for_account(aid, limit=lim_i)


async def _skill_get_campaign_summary(args: Dict[str, Any], account: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.axelia_crm_tools import get_campaign_bundle_skill

    rt = _axelia_rt()
    if not rt or not rt.acting_user:
        return {"error": "Contexte utilisateur indisponible."}

    cid = (args.get("campaign_id") or "").strip()
    return await get_campaign_bundle_skill(rt.acting_user, cid)


async def _skill_get_whatsapp_business_profile(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.account_service import get_account_by_id
    from app.services.axelia_crm_tools import get_whatsapp_business_profile_skill

    aid = str(account.get("id") or "").strip()
    if not aid:
        return {"error": "Sélectionne une ligne WABA pour lire le profil Meta."}

    full = await get_account_by_id(aid)
    if not full:
        return {"error": "Compte introuvable."}
    return await get_whatsapp_business_profile_skill(full)


async def _skill_list_agent_studio_configs(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.agent_studio_service import list_agent_configs
    from app.services.account_service import get_account_by_id
    from app.services.axelia_inbox_tools import (
        _AXELIA_MULTI_MAX_ACCOUNTS,
        list_accessible_account_rows_for_inbox,
    )

    rt = _axelia_rt()
    user = rt.acting_user if rt else None
    if not user:
        return {"error": "Contexte utilisateur indisponible."}

    async def _list_for_account(aid: str, display_name: str) -> Dict[str, Any]:
        rows = await list_agent_configs(aid)
        return {
            "account_id": aid,
            "account_name": display_name,
            "agents": [_slim_agent_studio_config_row(r) for r in rows],
            "total": len(rows),
        }

    explicit_aid = str(args.get("account_id") or "").strip()
    if explicit_aid:
        if not _user_may_read_agent_studio(user, explicit_aid):
            return {"error": "Accès refusé : conversations ou Agent Studio non autorisés sur ce compte."}
        acc_row = await get_account_by_id(explicit_aid)
        nm = (acc_row.get("name") or "-").strip() if acc_row else "-"
        part = await _list_for_account(explicit_aid, nm)
        return {"account_scope": "explicit_account_id", **part}

    if _skill_args_want_all_accessible(args, account):
        rows = await list_accessible_account_rows_for_inbox(user)
        selected = rows[:_AXELIA_MULTI_MAX_ACCOUNTS]
        accounts_out: List[Dict[str, Any]] = []
        for row in selected:
            aid = str(row.get("id") or "")
            if not aid or not _user_may_read_agent_studio(user, aid):
                continue
            nm = (row.get("name") or "-").strip()
            accounts_out.append(await _list_for_account(aid, nm))
        out: Dict[str, Any] = {
            "account_scope": "all_accessible",
            "accounts": accounts_out,
            "accounts_total_in_scope": len(rows),
            "accounts_iterated": len(selected),
            "accounts_capped": len(rows) > _AXELIA_MULTI_MAX_ACCOUNTS,
        }
        if not accounts_out:
            out["hint"] = (
                "Aucune ligne avec à la fois conversations.view et agent_studio.access dans le périmètre, "
                "ou aucun agent enregistré sur ces lignes."
            )
        return out

    aid = str(account.get("id") or "").strip()
    if not aid:
        return {
            "error": (
                "Compte WABA non résolu : sélectionne une ligne, passe account_id (UUID), "
                "ou account_scope=all_accessible."
            )
        }
    if not _user_may_read_agent_studio(user, aid):
        return {"error": "Tu n’as pas accès Agent Studio sur ce compte."}
    nm = (account.get("name") or "-").strip()
    part = await _list_for_account(aid, nm)
    return {"account_scope": "primary", **part}


async def _skill_get_agent_studio_config(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.agent_studio_service import (
        get_agent_config,
        normalize_agent_config,
        validate_agent_config,
    )

    _ = account
    rt = _axelia_rt()
    user = rt.acting_user if rt else None
    if not user:
        return {"error": "Contexte utilisateur indisponible."}

    cid = str(args.get("config_id") or "").strip()
    if not cid:
        return {"error": "Paramètre config_id requis (UUID de la configuration Agent Studio)."}

    row = await get_agent_config(cid)
    if not row:
        return {"error": "Configuration introuvable pour ce config_id."}

    aid = str(row.get("account_id") or "")
    if not _user_may_read_agent_studio(user, aid):
        return {"error": "Accès refusé : tu ne peux pas lire cet agent (compte ou permissions Studio)."}

    cfg = normalize_agent_config(row.get("config") or {})
    issues = validate_agent_config(cfg)
    return {
        "ok": True,
        "id": str(row.get("id") or ""),
        "account_id": aid,
        "is_default": bool(row.get("is_default")),
        "version": row.get("version"),
        "updated_at": row.get("updated_at"),
        "created_at": row.get("created_at"),
        "config": cfg,
        "validation_issues": issues,
    }


_FALLBACK_ROUTING_VALUES = frozenset({"human", "safe_reply", "ask_clarification"})
_MAX_AGENT_STUDIO_INTENTS = 100


async def _skill_upsert_agent_studio_routing(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    """Met à jour routing + forbidden_actions ; exécuté après confirmation UI (comme upsert_agent_studio_config)."""
    from app.services.agent_studio_service import (
        get_agent_config,
        normalize_agent_config,
        update_agent_config,
        validate_agent_config,
    )

    rt = _axelia_rt()
    user = rt.acting_user if rt else None
    if not user:
        return {"error": "Contexte utilisateur indisponible."}

    aid = str(args.get("account_id") or "").strip() or str(account.get("id") or "").strip()
    if not aid:
        return {
            "error": (
                "Sélectionne une ligne WABA ou passe `account_id` (UUID) pour modifier les règles Agent Studio."
            )
        }
    user.require(PermissionCodes.AGENT_STUDIO_ACCESS, aid)

    cfg_id = str(args.get("config_id") or "").strip()
    if not cfg_id:
        return {"error": "config_id requis (UUID de l'agent Studio à modifier)."}

    patch_intents = "intents" in args
    patch_fallback = "fallback" in args
    patch_threshold = "confidence_threshold" in args or "confidenceThreshold" in args
    patch_forbidden = "forbidden_actions" in args or "forbiddenActions" in args

    if not (patch_intents or patch_fallback or patch_threshold or patch_forbidden):
        return {
            "error": (
                "Indique au moins un champ parmi : intents, fallback, confidence_threshold, forbidden_actions."
            )
        }

    row = await get_agent_config(cfg_id)
    if not row:
        return {"error": "config_id introuvable."}
    if str(row.get("account_id") or "") != aid:
        return {"error": "config_id n'appartient pas au compte actif."}

    base_cfg = normalize_agent_config(row.get("config") or {})
    routing = dict(base_cfg.get("routing") or {})

    if patch_fallback:
        fb = str(args.get("fallback") or "").strip()
        if fb not in _FALLBACK_ROUTING_VALUES:
            return {
                "error": (
                    "fallback invalide ; utiliser human, safe_reply ou ask_clarification."
                )
            }
        routing["fallback"] = fb

    if patch_threshold:
        ct_raw = args.get("confidence_threshold")
        if ct_raw is None:
            ct_raw = args.get("confidenceThreshold")
        try:
            ctf = float(ct_raw)
        except (TypeError, ValueError):
            return {"error": "confidence_threshold doit être un nombre."}
        if not (0.0 < ctf <= 1.0):
            return {"error": "confidence_threshold doit être dans l'intervalle ]0, 1]."}
        routing["confidence_threshold"] = ctf

    if patch_intents:
        raw_list = args.get("intents")
        if not isinstance(raw_list, list):
            return {
                "error": "intents doit être une liste d'objets {key, handler, description?, min_confidence?}.",
            }
        if len(raw_list) > _MAX_AGENT_STUDIO_INTENTS:
            return {"error": f"Trop d'intents (max {_MAX_AGENT_STUDIO_INTENTS})."}
        new_intents: List[Dict[str, Any]] = []
        for i, item in enumerate(raw_list):
            if not isinstance(item, dict):
                return {"error": f"intent_{i}_invalid : entrée non objet."}
            key = str(item.get("key") or "").strip()
            handler = str(item.get("handler") or "").strip()
            desc = str(item.get("description") or "").strip()
            if len(key) > 80 or len(handler) > 120:
                return {"error": f"intent_{i} : key (max 80) ou handler (max 120) trop long."}
            mc = item.get("min_confidence")
            mc_out: Optional[float] = None
            if mc is not None and mc != "":
                try:
                    mcf = float(mc)
                    if not (0.0 <= mcf <= 1.0):
                        return {"error": f"intent_{i} : min_confidence doit être dans [0, 1]."}
                    mc_out = mcf
                except (TypeError, ValueError):
                    return {"error": f"intent_{i} : min_confidence invalide."}
            ent: Dict[str, Any] = {"key": key, "handler": handler, "description": desc}
            if mc_out is not None:
                ent["min_confidence"] = mc_out
            new_intents.append(ent)

        replace_raw = args.get("replace_intents")
        if replace_raw is None:
            replace_raw = args.get("replaceIntents")
        replace_b = True if replace_raw is None else bool(replace_raw)

        if replace_b:
            routing["intents"] = new_intents
        else:
            by_key: Dict[str, Dict[str, Any]] = {}
            for x in routing.get("intents") or []:
                if isinstance(x, dict):
                    k = str(x.get("key") or "").strip()
                    if k:
                        by_key[k] = dict(x)
            for ni in new_intents:
                k = str(ni.get("key") or "").strip()
                if k:
                    by_key[k] = ni
            routing["intents"] = list(by_key.values())

    if patch_forbidden:
        fa_raw = args.get("forbidden_actions")
        if fa_raw is None:
            fa_raw = args.get("forbiddenActions")
        if not isinstance(fa_raw, list):
            return {"error": "forbidden_actions doit être une liste de chaînes."}
        policies = dict(base_cfg.get("policies") or {})
        policies["forbidden_actions"] = [str(x).strip() for x in fa_raw if str(x).strip()]
        base_cfg["policies"] = policies

    base_cfg["routing"] = routing

    normalized = normalize_agent_config(base_cfg)
    issues = validate_agent_config(normalized)
    blocking = [i for i in issues if i.get("severity") == "error"]
    if blocking:
        return {
            "error": "Validation Agent Studio en erreur (routage / politiques).",
            "issues": blocking,
            "hint": (
                "Vérifie les intents (clés uniques, handler non vide), le seuil ]0,1], "
                "et la cohérence forbidden_actions vs require_approval_for."
            ),
        }

    saved = await update_agent_config(cfg_id, normalized, user.id)
    if not saved:
        return {"error": "Impossible de sauvegarder les règles Agent Studio."}

    saved_cfg = saved.get("config") if isinstance(saved.get("config"), dict) else {}
    return {
        "ok": True,
        "config_id": saved.get("id"),
        "account_id": saved.get("account_id"),
        "routing": saved_cfg.get("routing"),
        "policies_summary": {
            "forbidden_actions": (saved_cfg.get("policies") or {}).get("forbidden_actions"),
        },
        "warnings": [i for i in issues if i.get("severity") != "error"],
    }


async def _skill_upsert_agent_studio_config(
    args: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services.agent_studio_service import (
        create_agent_config,
        default_agent_config,
        get_agent_config,
        normalize_agent_config,
        set_agent_default,
        update_agent_config,
        validate_agent_config,
    )

    rt = _axelia_rt()
    user = rt.acting_user if rt else None
    if not user:
        return {"error": "Contexte utilisateur indisponible."}

    aid = str(args.get("account_id") or "").strip() or str(account.get("id") or "").strip()
    if not aid:
        return {
            "error": (
                "Sélectionne une ligne WABA pour modifier Agent Studio, ou passe `account_id` (UUID) dans les args."
            )
        }
    user.require(PermissionCodes.AGENT_STUDIO_ACCESS, aid)

    cfg_id = str(args.get("config_id") or "").strip()
    name = str(args.get("name") or "").strip()
    primary_goal = str(args.get("primary_goal") or "").strip()
    if not name or not primary_goal:
        return {"error": "Parametres requis: name et primary_goal."}

    kpi = args.get("kpi")
    if not isinstance(kpi, list):
        kpi = []
    kpi = [str(x).strip() for x in kpi if str(x).strip()]

    audience = str(args.get("audience") or "").strip()
    allowed_tools = args.get("allowed_tools")
    require_approval_for = args.get("require_approval_for")

    base_cfg = default_agent_config()
    row = None
    if cfg_id:
        row = await get_agent_config(cfg_id)
        if not row:
            return {"error": "config_id introuvable."}
        if str(row.get("account_id") or "") != aid:
            return {"error": "config_id n appartient pas au compte actif."}
        base_cfg = normalize_agent_config(row.get("config") or {})

    base_cfg["name"] = name
    objective = dict(base_cfg.get("objective") or {})
    objective["primary_goal"] = primary_goal
    objective["kpi"] = kpi
    objective["audience"] = audience
    base_cfg["objective"] = objective

    caps = dict(base_cfg.get("capabilities") or {})
    if isinstance(allowed_tools, list):
        caps["allowed_tools"] = [str(x).strip() for x in allowed_tools if str(x).strip()]
    if isinstance(require_approval_for, list):
        caps["require_approval_for"] = [
            str(x).strip() for x in require_approval_for if str(x).strip()
        ]
    base_cfg["capabilities"] = caps

    normalized = normalize_agent_config(base_cfg)
    issues = validate_agent_config(normalized)
    blocking = [i for i in issues if i.get("severity") == "error"]
    if blocking:
        # On enrichit l'erreur d'un `hint` actionnable pour que l'IA puisse se corriger
        # toute seule au tour suivant (au lieu de poser la question à l'utilisateur, comme
        # avec un `require_approval_for` rempli de libellés métier français).
        hints: List[str] = []
        for issue in blocking:
            msg = str(issue.get("message") or "")
            details = str(issue.get("details") or "").strip()
            if msg == "unknown_allowed_tools":
                hints.append(
                    "`allowed_tools` contient des entrées non reconnues "
                    f"({details}). N'utilise QUE les slugs techniques suivants : "
                    + ", ".join(sorted(_AGENT_STUDIO_TOOL_SLUGS))
                    + ". Pour exprimer des cas métier (facturation, litiges...), "
                    "ajoute-les en texte libre dans `primary_goal`."
                )
            elif msg == "unknown_require_approval_tools":
                hints.append(
                    "`require_approval_for` contient des entrées non reconnues "
                    f"({details}). Ce champ n'accepte que des slugs d'outils techniques "
                    "(p. ex. " + ", ".join(sorted(_AGENT_STUDIO_SENSITIVE_SLUGS)) + ") "
                    "et chaque entrée DOIT aussi figurer dans `allowed_tools`. "
                    "Les politiques métier (« approbation pour facturation », etc.) "
                    "se décrivent en texte libre dans `primary_goal`."
                )
            elif msg == "require_approval_not_in_allowed_tools":
                hints.append(
                    f"`require_approval_for` ({details}) doit être un sous-ensemble de "
                    "`allowed_tools` : ajoute ces slugs à `allowed_tools` ou retire-les "
                    "de `require_approval_for`."
                )
            elif msg == "sensitive_tools_must_require_approval":
                hints.append(
                    f"Les outils sensibles ({details}) doivent obligatoirement figurer "
                    "dans `require_approval_for` quand ils sont dans `allowed_tools`."
                )
        result: Dict[str, Any] = {
            "error": "Validation Agent Studio en erreur.",
            "issues": blocking,
        }
        if hints:
            result["hint"] = " ".join(hints)
        return result

    if row:
        saved = await update_agent_config(cfg_id, normalized, user.id)
    else:
        saved = await create_agent_config(aid, normalized, user.id)
    if not saved:
        return {"error": "Impossible de sauvegarder la configuration Agent Studio."}

    if bool(args.get("make_default")):
        await set_agent_default(str(saved.get("id") or ""), aid)
        saved = await get_agent_config(str(saved.get("id") or "")) or saved

    return {
        "ok": True,
        "config_id": saved.get("id"),
        "account_id": saved.get("account_id"),
        "name": (saved.get("config") or {}).get("name") if isinstance(saved.get("config"), dict) else name,
        "is_default": bool(saved.get("is_default")),
        "issues": issues,
    }


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
    "prepare_template_image_header": _skill_prepare_template_image_header,
    "list_broadcast_groups": _skill_list_broadcast_groups,
    "search_inbox_messages": _skill_search_inbox_messages,
    "get_conversation_digest": _skill_get_conversation_digest,
    "summarize_contact_inbox": _skill_summarize_contact_inbox,
    "search_contacts": _skill_search_contacts,
    "get_contact": _skill_get_contact,
    "list_recent_conversations": _skill_list_recent_conversations,
    "find_satisfied_contacts": _skill_find_satisfied_contacts,
    "list_broadcast_campaigns": _skill_list_broadcast_campaigns,
    "get_campaign_summary": _skill_get_campaign_summary,
    "get_whatsapp_business_profile": _skill_get_whatsapp_business_profile,
    "list_agent_studio_configs": _skill_list_agent_studio_configs,
    "get_agent_studio_config": _skill_get_agent_studio_config,
    "upsert_agent_studio_routing": _skill_upsert_agent_studio_routing,
    "upsert_agent_studio_config": _skill_upsert_agent_studio_config,
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
        if isinstance(result, dict) and result.get("error"):
            logger.warning(
                "playground skill %s returned error: %s",
                skill_name,
                str(result.get("error"))[:240],
            )
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
    *,
    axelia_runtime: Optional[AxeliaSkillsRuntime] = None,
) -> List[Dict[str, Any]]:
    """Enchaîne les tool_calls par paquets parallèles (5) ; ordre global préservé."""

    async def _one(tc: Dict[str, Any]) -> Dict[str, Any]:
        skill_name = (tc.get("skill") or tc.get("name") or "").strip()
        args = tc.get("args") or tc.get("arguments") or {}
        result = await execute_skill(skill_name, args, account)
        return {"skill": skill_name, "result": result}

    token = None
    if axelia_runtime is not None:
        token = _axelia_skills_runtime.set(axelia_runtime)
    try:
        all_out: List[Dict[str, Any]] = []
        for off in range(0, len(tool_calls), _PARALLEL_SKILL_CALLS):
            subset = tool_calls[off : off + _PARALLEL_SKILL_CALLS]
            all_out.extend(
                list(await asyncio.gather(*(_one(tc) for tc in subset)))
            )
        return all_out
    finally:
        if token is not None:
            _axelia_skills_runtime.reset(token)
