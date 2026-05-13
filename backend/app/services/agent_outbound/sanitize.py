"""
Réduction des fuites sensibles dans les résultats d’outils avant réinjection au modèle (synthèse client).

Les outils s’exécutent déjà dans le périmètre ``account`` ; ce module évite que des champs techniques
(tokens, secrets, e-mails…) ou des blobs énormes ne soient copiés tels quels dans le contexte Gemini.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, List

_EMAIL_RE = re.compile(r"[^\s@<>\"']+@[^\s@<>\"']+\.[^\s@<>\"']+", re.IGNORECASE)
_BEARER_RE = re.compile(r"(?i)bearer\s+[a-z0-9._\-]{10,}")
_JWTISH_RE = re.compile(r"\beyJ[a-z0-9_\-]{20,}\.[a-z0-9_\-]{10,}\.[a-z0-9_\-]{10,}\b", re.IGNORECASE)

_REDACT_PLACEHOLDER = "[masqué]"


def _key_is_sensitive(key: str) -> bool:
    lk = (key or "").lower().replace("-", "_")
    if lk in ("max_tokens", "max_output_tokens", "token_count", "thinking_budget"):
        return False
    bad = (
        "password",
        "authorization",
        "private_key",
        "api_key",
        "apikey",
        "client_secret",
        "service_role",
        "access_token",
        "refresh_token",
        "bearer",
        "signing_secret",
        "credential",
        "webhook_secret",
        "waba_token",
        "whatsapp_token",
    )
    if any(b in lk for b in bad):
        return True
    if lk.endswith("_token"):
        return True
    return False


def _sanitize_string(s: str) -> str:
    if not s:
        return s
    out = _EMAIL_RE.sub(_REDACT_PLACEHOLDER, s)
    out = _BEARER_RE.sub(f"Bearer {_REDACT_PLACEHOLDER}", out)
    out = _JWTISH_RE.sub(_REDACT_PLACEHOLDER, out)
    return out


def _sanitize_value(val: Any) -> Any:
    if isinstance(val, str):
        return _sanitize_string(val)
    if isinstance(val, dict):
        return sanitize_tool_result_object(val)
    if isinstance(val, list):
        return [_sanitize_value(x) for x in val[:500]]
    return val


def sanitize_tool_result_object(obj: dict[str, Any]) -> dict[str, Any]:
    """Copie défensive + masquage des champs sensibles (un niveau de clés + récursion sur dict/list)."""
    out: dict[str, Any] = {}
    for k, v in obj.items():
        if _key_is_sensitive(str(k)):
            out[k] = _REDACT_PLACEHOLDER
        elif isinstance(v, dict):
            out[k] = sanitize_tool_result_object(v)
        elif isinstance(v, list):
            out[k] = [_sanitize_value(x) for x in v[:500]]
        elif isinstance(v, str):
            out[k] = _sanitize_string(v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def sanitize_kernel_tool_results_for_model(results: List[dict[str, Any]]) -> List[dict[str, Any]]:
    """
    Nettoie la liste ``[{"skill": ..., "result": ...}, ...]`` renvoyée par le noyau avant sérialisation JSON.

    Pour les erreurs (``error`` / ``kernel_error``), ne fait qu’assainir les chaînes visibles (e-mails, JWT).
    """
    cleaned: List[dict[str, Any]] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        res = item.get("result")
        if isinstance(res, dict):
            if res.get("kernel_error") or res.get("error"):
                res_out = dict(res)
                msg = res_out.get("error")
                if isinstance(msg, str):
                    res_out["error"] = _sanitize_string(msg[:2000])
                ke = res_out.get("kernel_error")
                if isinstance(ke, dict):
                    ke2 = dict(ke)
                    det = ke2.get("detail")
                    if isinstance(det, str):
                        ke2["detail"] = _sanitize_string(str(det)[:2000])
                    res_out["kernel_error"] = ke2
                item["result"] = res_out
            else:
                item["result"] = sanitize_tool_result_object(res)
        cleaned.append(item)
    return cleaned


def sanitize_tool_results_json_blob(blob: str) -> str:
    """Parse JSON (liste d’objets), nettoie, re-sérialise ; en cas d’échec retourne le blob tronqué."""
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return blob[:8000] + ("…" if len(blob) > 8000 else "")
    if isinstance(data, list):
        out = sanitize_kernel_tool_results_for_model([x for x in data if isinstance(x, dict)])
        return json.dumps(out, ensure_ascii=False)
    return blob
