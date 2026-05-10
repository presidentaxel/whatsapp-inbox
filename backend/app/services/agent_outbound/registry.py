"""
Jalon M0 / M4 - Spécification du noyau agent (outils v1).

Catalogue **vide** tant qu’aucune liste d’outils dédiée n’est réintroduite côté produit :
les anciens outils internes (templates, inbox, Meta…) ne sont plus exposés ni validés ici.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.services.agent_outbound.security import (
    coerce_kernel_tool_slug,
    validate_args_security_shape,
)

# Doit rester strictement aligné sur ``agent_studio_service.ALLOWED_AGENT_TOOLS``
# (sans import circulaire / effet de bord DB au chargement du module).
AGENT_STUDIO_ALLOWLIST_SLUGS: frozenset[str] = frozenset()

# Sous-ensemble exécutable en lecture seule pour la boucle outbound (vide = aucun outil).
AGENT_KERNEL_V1_READ_TOOLS: frozenset[str] = frozenset()


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


_TOOL_SPECS_V1: Tuple[AgentOutboundToolSpec, ...] = ()


def _spec_index() -> Dict[str, AgentOutboundToolSpec]:
    return {s.name: s for s in _TOOL_SPECS_V1}


def build_effective_kernel_v1_allowlist(allowed_tools: Iterable[str]) -> frozenset[str]:
    """Intersection demandée (config agent) ∩ outils noyau v1 lecture seule."""
    wanted: set[str] = set()
    for x in allowed_tools:
        c = coerce_kernel_tool_slug(str(x))
        if c:
            wanted.add(c)
    return frozenset(wanted & AGENT_KERNEL_V1_READ_TOOLS)


def build_agent_kernel_v1_catalog(
    allowed_tools: Iterable[str],
) -> Tuple[List[AgentOutboundToolSpec], List[str]]:
    """
    Construit le catalogue exposable au modèle : intersection ``allowed_tools`` ∩ noyau v1 lecture.

    Retourne (specs ordonnés par nom), (outils demandés mais non disponibles en v1 lecture :
    inconnus d’Agent Studio, écriture, ou hors périmètre kernel).
    """
    wanted_raw = [str(x).strip() for x in allowed_tools if str(x).strip()]
    wanted_set: set[str] = set()
    rejected: List[str] = []
    for raw in wanted_raw:
        c = coerce_kernel_tool_slug(raw)
        if c:
            wanted_set.add(c)
        else:
            rejected.append(raw)

    allowed_set = set(AGENT_STUDIO_ALLOWLIST_SLUGS)

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

    if validate_args_security_shape(args):
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
        if ptype == "integer":
            if isinstance(val, bool) or not isinstance(val, int):
                return AgentOutboundToolErrorCode.INVALID_ARGUMENTS
        if isinstance(val, str) and "minLength" in prop:
            if len(val.strip()) < int(prop["minLength"]):
                return AgentOutboundToolErrorCode.INVALID_ARGUMENTS

    for key, val in args.items():
        prop = properties.get(key) or {}
        if type(val) is int:
            if "minimum" in prop and val < int(prop["minimum"]):
                return AgentOutboundToolErrorCode.INVALID_ARGUMENTS
            if "maximum" in prop and val > int(prop["maximum"]):
                return AgentOutboundToolErrorCode.INVALID_ARGUMENTS
        enum = prop.get("enum")
        if enum and val not in enum:
            return AgentOutboundToolErrorCode.INVALID_ARGUMENTS

    return None
