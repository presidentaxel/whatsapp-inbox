"""
Jalon M0 — Spécification du noyau agent (outils v1 lecture seule).

- Catalogue distinct d’Axelia : seuls les noms listés ici sont exposables au modèle
  outbound quand la politique le permet.
- Schémas JSON (arguments) sans ``account_scope=all_accessible`` : le runtime
  agent reste mono-ligne (M1+).
- Codes d’erreur stables pour journalisation et réinjection modèle.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Doit rester strictement aligné sur ``agent_studio_service.ALLOWED_AGENT_TOOLS``
# (sans import circulaire / effet de bord DB au chargement du module).
AGENT_STUDIO_ALLOWLIST_SLUGS: frozenset[str] = frozenset(
    {
        "list_templates",
        "get_template_status",
        "create_template",
        "prepare_template_image_header",
        "list_broadcast_groups",
        "search_inbox_messages",
        "get_conversation_digest",
        "summarize_contact_inbox",
        "search_contacts",
        "get_contact",
        "list_recent_conversations",
        "find_satisfied_contacts",
        "list_broadcast_campaigns",
        "get_campaign_summary",
        "get_whatsapp_business_profile",
        "meta_block_contact",
    }
)

# Outils Agent Studio « sensibles » (écriture / action Meta) — jamais dans le noyau v1 lecture seule.
_AGENT_WRITE_OR_SENSITIVE = frozenset(
    {
        "create_template",
        "prepare_template_image_header",
        "meta_block_contact",
    }
)

# Sous-ensemble lecture seule du catalogue Agent Studio, pour la boucle outbound (kernel).
AGENT_KERNEL_V1_READ_TOOLS: frozenset[str] = frozenset(
    AGENT_STUDIO_ALLOWLIST_SLUGS - _AGENT_WRITE_OR_SENSITIVE
)


class AgentOutboundToolErrorCode(str, Enum):
    """Codes d’erreur normalisés côté noyau agent (stable pour logs / tests)."""

    UNKNOWN_TOOL = "unknown_tool"
    TOOL_NOT_IN_KERNEL_V1 = "tool_not_in_kernel_v1"
    NOT_ALLOWED_BY_POLICY = "not_allowed_by_policy"
    INVALID_ARGUMENTS = "invalid_arguments"
    EXECUTION_FAILED = "execution_failed"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    UPSTREAM_RATE_LIMIT = "upstream_rate_limit"
    INTERNAL = "internal"


def agent_tool_error_payload(
    code: AgentOutboundToolErrorCode,
    *,
    detail: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Structure JSON-serializable pour traces / réponse API interne."""
    out: Dict[str, Any] = {"code": code.value}
    if tool_name:
        out["tool_name"] = tool_name
    if detail:
        out["detail"] = detail[:2000] if len(detail) > 2000 else detail
    return out


def agent_tool_error_for_model(code: AgentOutboundToolErrorCode) -> str:
    """Court message français pour réinjecter au modèle (sans fuite technique)."""
    messages = {
        AgentOutboundToolErrorCode.UNKNOWN_TOOL: (
            "L’outil demandé n’existe pas dans le périmètre de cet agent."
        ),
        AgentOutboundToolErrorCode.TOOL_NOT_IN_KERNEL_V1: (
            "Cet outil n’est pas disponible pour les réponses automatisées sur ce canal."
        ),
        AgentOutboundToolErrorCode.NOT_ALLOWED_BY_POLICY: (
            "Cet outil n’est pas autorisé pour la configuration actuelle de l’agent."
        ),
        AgentOutboundToolErrorCode.INVALID_ARGUMENTS: (
            "Les paramètres de l’outil sont invalides ou incomplets."
        ),
        AgentOutboundToolErrorCode.EXECUTION_FAILED: (
            "L’outil n’a pas pu terminer l’opération demandée."
        ),
        AgentOutboundToolErrorCode.UPSTREAM_TIMEOUT: (
            "Le service externe a mis trop de temps à répondre."
        ),
        AgentOutboundToolErrorCode.UPSTREAM_RATE_LIMIT: (
            "Trop de requêtes ; réessaie plus tard."
        ),
        AgentOutboundToolErrorCode.INTERNAL: (
            "Une erreur interne s’est produite lors de l’exécution de l’outil."
        ),
    }
    return messages.get(code, messages[AgentOutboundToolErrorCode.INTERNAL])


@dataclass(frozen=True)
class AgentOutboundToolSpec:
    name: str
    description: str
    parameters_json_schema: Dict[str, Any]


def _schema_object(
    *,
    properties: Dict[str, Any],
    required: Sequence[str],
) -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(required),
    }


_TOOL_SPECS_V1: Tuple[AgentOutboundToolSpec, ...] = (
    AgentOutboundToolSpec(
        name="list_templates",
        description=(
            "Liste les templates Meta de la ligne (nom, langue, statut, catégorie, résumé des composants)."
        ),
        parameters_json_schema=_schema_object(properties={}, required=[]),
    ),
    AgentOutboundToolSpec(
        name="get_template_status",
        description="Vérifie le statut d’un template Meta par son nom exact.",
        parameters_json_schema=_schema_object(
            properties={
                "template_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nom du template tel que sur Meta.",
                },
            },
            required=["template_name"],
        ),
    ),
    AgentOutboundToolSpec(
        name="list_broadcast_groups",
        description="Liste les groupes de diffusion (id, nom, taille).",
        parameters_json_schema=_schema_object(properties={}, required=[]),
    ),
    AgentOutboundToolSpec(
        name="search_inbox_messages",
        description=(
            "Recherche dans les messages texte de l’inbox de la ligne (toutes conversations), "
            "avec filtres temporels optionnels."
        ),
        parameters_json_schema=_schema_object(
            properties={
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Texte ou mots-clés à retrouver.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "match_mode": {"type": "string", "enum": ["all", "any"]},
                "since": {
                    "type": "string",
                    "description": "Borne basse ISO 8601 (optionnel).",
                },
                "until": {
                    "type": "string",
                    "description": "Borne haute ISO 8601 (optionnel).",
                },
            },
            required=["query"],
        ),
    ),
    AgentOutboundToolSpec(
        name="get_conversation_digest",
        description="Récupère les derniers messages texte d’une conversation (UUID).",
        parameters_json_schema=_schema_object(
            properties={
                "conversation_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "UUID de la conversation inbox.",
                },
                "max_messages": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            required=["conversation_id"],
        ),
    ),
    AgentOutboundToolSpec(
        name="summarize_contact_inbox",
        description=(
            "Agrège les derniers messages des fils liés à un contact (nom affiché, profil WhatsApp ou numéro)."
        ),
        parameters_json_schema=_schema_object(
            properties={
                "contact_search": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Identifiant textuel du contact à résumer.",
                },
                "max_threads": {"type": "integer", "minimum": 1, "maximum": 50},
                "max_messages_per_thread": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            required=["contact_search"],
        ),
    ),
    AgentOutboundToolSpec(
        name="search_contacts",
        description="Recherche des contacts CRM liés à des conversations sur la ligne.",
        parameters_json_schema=_schema_object(
            properties={
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            required=["query"],
        ),
    ),
    AgentOutboundToolSpec(
        name="get_contact",
        description="Détails d’un contact CRM par UUID (ligne courante).",
        parameters_json_schema=_schema_object(
            properties={
                "contact_id": {"type": "string", "minLength": 1},
            },
            required=["contact_id"],
        ),
    ),
    AgentOutboundToolSpec(
        name="list_recent_conversations",
        description="Liste les conversations inbox récentes (métadonnées + extrait).",
        parameters_json_schema=_schema_object(
            properties={
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            required=[],
        ),
    ),
    AgentOutboundToolSpec(
        name="find_satisfied_contacts",
        description="Contacts ayant exprimé une satisfaction récente (signaux dans messages entrants).",
        parameters_json_schema=_schema_object(
            properties={
                "days": {"type": "integer", "minimum": 1, "maximum": 365},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            required=[],
        ),
    ),
    AgentOutboundToolSpec(
        name="list_broadcast_campaigns",
        description="Liste les campagnes de diffusion récentes (statut, compteurs).",
        parameters_json_schema=_schema_object(
            properties={
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            required=[],
        ),
    ),
    AgentOutboundToolSpec(
        name="get_campaign_summary",
        description="Statistiques détaillées d’une campagne par UUID.",
        parameters_json_schema=_schema_object(
            properties={
                "campaign_id": {"type": "string", "minLength": 1},
            },
            required=["campaign_id"],
        ),
    ),
    AgentOutboundToolSpec(
        name="get_whatsapp_business_profile",
        description="Lit le profil business WhatsApp public de la ligne (about, sites, vertical…).",
        parameters_json_schema=_schema_object(properties={}, required=[]),
    ),
)


def _spec_index() -> Dict[str, AgentOutboundToolSpec]:
    return {s.name: s for s in _TOOL_SPECS_V1}


def build_effective_kernel_v1_allowlist(allowed_tools: Iterable[str]) -> frozenset[str]:
    """Intersection demandée (config agent) ∩ outils noyau v1 lecture seule."""
    wanted = {str(x).strip() for x in allowed_tools if str(x).strip()}
    return frozenset(wanted & AGENT_KERNEL_V1_READ_TOOLS)


def build_agent_kernel_v1_catalog(
    allowed_tools: Iterable[str],
) -> Tuple[List[AgentOutboundToolSpec], List[str]]:
    """
    Construit le catalogue exposable au modèle : intersection ``allowed_tools`` ∩ noyau v1 lecture.

    Retourne (specs ordonnés par nom), (outils demandés mais non disponibles en v1 lecture :
    inconnus d’Agent Studio, écriture, ou hors périmètre kernel).
    """
    wanted = [str(x).strip() for x in allowed_tools if str(x).strip()]
    wanted_set = set(wanted)
    allowed_set = set(AGENT_STUDIO_ALLOWLIST_SLUGS)

    rejected: List[str] = []
    for name in sorted(wanted_set):
        if name not in allowed_set:
            rejected.append(name)
        elif name not in AGENT_KERNEL_V1_READ_TOOLS:
            rejected.append(name)

    idx = _spec_index()
    specs: List[AgentOutboundToolSpec] = []
    for name in sorted(wanted_set & set(idx.keys())):
        if name in AGENT_KERNEL_V1_READ_TOOLS:
            specs.append(idx[name])
    return specs, rejected


def validate_agent_kernel_v1_args(tool_name: str, args: Mapping[str, Any]) -> Optional[AgentOutboundToolErrorCode]:
    """
    Validation légère alignée sur les schémas M0 (types / champs requis).

    Retourne un code d’erreur si invalide, sinon ``None``.
    """
    if tool_name not in AGENT_KERNEL_V1_READ_TOOLS:
        if tool_name not in AGENT_STUDIO_ALLOWLIST_SLUGS:
            return AgentOutboundToolErrorCode.UNKNOWN_TOOL
        return AgentOutboundToolErrorCode.TOOL_NOT_IN_KERNEL_V1

    idx = _spec_index()
    spec = idx.get(tool_name)
    if not spec:
        return AgentOutboundToolErrorCode.TOOL_NOT_IN_KERNEL_V1

    if not isinstance(args, Mapping):
        return AgentOutboundToolErrorCode.INVALID_ARGUMENTS

    schema = spec.parameters_json_schema
    required: List[str] = list(schema.get("required") or [])
    properties: Dict[str, Any] = dict(schema.get("properties") or {})

    for key in args:
        if key not in properties:
            return AgentOutboundToolErrorCode.INVALID_ARGUMENTS

    for field in required:
        if field not in args or args[field] in (None, ""):
            return AgentOutboundToolErrorCode.INVALID_ARGUMENTS

    for key, val in args.items():
        prop = properties.get(key) or {}
        ptype = prop.get("type")
        if ptype == "string" and not isinstance(val, str):
            return AgentOutboundToolErrorCode.INVALID_ARGUMENTS
        if ptype == "integer" and not isinstance(val, int):
            return AgentOutboundToolErrorCode.INVALID_ARGUMENTS
        if isinstance(val, str) and "minLength" in prop:
            if len(val.strip()) < int(prop["minLength"]):
                return AgentOutboundToolErrorCode.INVALID_ARGUMENTS

    for key, val in args.items():
        prop = properties.get(key) or {}
        if isinstance(val, int):
            if "minimum" in prop and val < int(prop["minimum"]):
                return AgentOutboundToolErrorCode.INVALID_ARGUMENTS
            if "maximum" in prop and val > int(prop["maximum"]):
                return AgentOutboundToolErrorCode.INVALID_ARGUMENTS
        enum = prop.get("enum")
        if enum and val not in enum:
            return AgentOutboundToolErrorCode.INVALID_ARGUMENTS

    return None
