"""Parsing utilitaire pour la boucle outbound (sans dépendance à la config)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

_MAX_TOOL_CALLS_ROUND1 = 5


def strip_json_fences(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def normalize_agent_tool_calls_payload(raw: Any) -> List[Dict[str, Any]]:
    """Normalise ``tool_calls`` issus du JSON modèle vers le format du noyau."""
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw[:_MAX_TOOL_CALLS_ROUND1]:
        if not isinstance(item, dict):
            continue
        skill = str(item.get("skill") or item.get("name") or "").strip()
        raw_args = item.get("args")
        if raw_args is None:
            raw_args = item.get("arguments")
        args = dict(raw_args) if isinstance(raw_args, dict) else {}
        if skill:
            out.append({"skill": skill, "args": args})
    return out


def parse_json_object(text: str) -> Dict[str, Any] | None:
    """Parse un objet JSON depuis la sortie modèle (fences optionnelles)."""
    try:
        obj = json.loads(strip_json_fences(text))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


_REFLECTION_SUFFICIENCY = frozenset({"sufficient", "partial", "insufficient"})


def format_reflection_notes(data: Dict[str, Any], *, max_brief: int = 900) -> str:
    """
    Formate la sortie JSON du tour « réflexion » (M3) pour injection dans le prompt de synthèse.

    Ne doit contenir aucune donnée client sensible hors périmètre déjà présent dans les observations.
    """
    if not isinstance(data, dict):
        return ""
    suff = str(data.get("sufficiency") or "").strip().lower()
    if suff not in _REFLECTION_SUFFICIENCY:
        suff = "partial"
    brief = str(data.get("brief") or "").strip()
    if len(brief) > max_brief:
        brief = brief[: max_brief - 1] + "…"
    caveats_raw = data.get("caveats")
    caveats: List[str] = []
    if isinstance(caveats_raw, list):
        for x in caveats_raw[:6]:
            s = str(x).strip()
            if s:
                caveats.append(s)
    lines = [
        f"- Évaluation des données pour répondre : {suff}",
        f"- Synthèse interne : {brief or '(vide)'}",
    ]
    if caveats:
        lines.append("- Points d’attention :")
        lines.extend(f"  - {c}" for c in caveats)
    return "\n".join(lines).strip()
