"""
Jalon M4 - Garde-fous défensifs pour le noyau agent outbound.

Réduit la surface d’abus (noms d’outils mal formés, clés d’arguments suspectes, chaînes énormes).
La cohérence multi-tenant reste assurée par les services sous-jacents (account_id, RLS côté API).
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Optional

_TOOL_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# Slugs réels du noyau v1 : lettres minuscules + underscore uniquement.
_MAX_ARG_KEYS = 24
_MAX_ARG_KEY_LEN = 64
_MAX_STRING_ARG_CHARS = 8192


def coerce_kernel_tool_slug(raw: str) -> Optional[str]:
    """Normalise et valide un identifiant d’outil (slug). Retourne ``None`` si invalide."""
    s = (raw or "").strip().lower()
    if not s or not _TOOL_SLUG_RE.fullmatch(s):
        return None
    return s


def validate_args_security_shape(args: Mapping[str, Any]) -> Optional[str]:
    """
    Contrôle structurel des arguments avant validation schéma.

    Retourne un code court si rejet, sinon ``None``.
    """
    if len(args) > _MAX_ARG_KEYS:
        return "too_many_arg_keys"
    unsafe_tokens = ("__proto__", "constructor", "prototype")
    for key in args:
        if not isinstance(key, str):
            return "arg_key_not_str"
        if len(key) > _MAX_ARG_KEY_LEN:
            return "arg_key_too_long"
        if "__" in key or key.startswith("$"):
            return "arg_key_forbidden"
        if key.lower() in unsafe_tokens:
            return "arg_key_forbidden"
    for _k, val in args.items():
        if isinstance(val, str) and len(val) > _MAX_STRING_ARG_CHARS:
            return "arg_string_too_long"
    return None
