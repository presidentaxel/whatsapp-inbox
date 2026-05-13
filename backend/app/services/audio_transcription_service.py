"""
Transcription des messages audio/voice entrants via Gemini (inline audio).
À la demande (API) et automatiquement pour le bot (Gemini ou Playground) si bot activé sur la conversation.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.circuit_breaker import CircuitBreakerOpenError, gemini_circuit_breaker
from app.core.db import supabase, supabase_execute
from app.core.http_client import get_http_client_for_media
from app.core.pg import execute as pg_execute, get_pool
from app.services.account_service import get_account_by_id
from app.services.bot_service import _call_gemini_api
from app.services.conversation_service import get_conversation_by_id
from app.services.message_service import fetch_message_media_content

logger = logging.getLogger(__name__)

# Nouvelles tentatives après réception (API médias WhatsApp / Gemini parfois instables).
_RETRYABLE_BOT_TRANSCRIPTION_DETAILS = frozenset(
    {
        "media_fetch_failed",
        "transcription_failed",
        "media_not_available",
    }
)
_BOT_TRANSCRIPTION_RETRY_DELAYS_S = (0.0, 0.8, 2.0, 4.0)

_TRANSCRIBE_PROMPT = (
    "Transcris intégralement ce message audio en français. "
    "Réponds uniquement avec la transcription textuelle, sans préambule ni guillemets. "
    "Si tu n'entends rien de clair, réponds exactement : [inaudible]"
)


def _effective_max_bytes() -> int:
    return max(1024, int(settings.GEMINI_AUDIO_TRANSCRIPTION_MAX_BYTES))


def _transcription_model() -> str:
    m = settings.GEMINI_TRANSCRIPTION_MODEL.strip()
    return m or settings.GEMINI_MODEL


def _generation_config(model: str) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {"temperature": 0.2, "maxOutputTokens": 4096}
    ml = (model or "").lower()
    if ml.startswith("gemini-2.5-") or ml.startswith("gemini-3"):
        cfg["thinkingConfig"] = {"thinkingBudget": 512}
    return cfg


def _normalize_audio_mime(raw: str) -> str:
    mt = (raw or "application/octet-stream").split(";")[0].strip().lower()
    if mt in ("audio/opus",):
        return "audio/ogg"
    if mt == "application/octet-stream":
        return "audio/ogg"
    if mt.startswith("audio/"):
        return mt
    if "ogg" in mt:
        return "audio/ogg"
    return mt


def _extract_text_from_gemini_response(data: Dict[str, Any]) -> Optional[str]:
    for cand in data.get("candidates") or []:
        content = cand.get("content") or {}
        for part in content.get("parts") or []:
            text = (part.get("text") or "").strip()
            if text:
                return text
    if "promptFeedback" in data:
        logger.warning("audio transcript: promptFeedback=%s", data.get("promptFeedback"))
    logger.warning(
        "audio transcript: no text in response keys=%s",
        list(data.keys())[:12],
    )
    return None


async def _save_audio_transcript_if_empty(message_id: str, text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    if len(text) > 32000:
        text = text[:32000] + "…"

    if get_pool():
        await pg_execute(
            "UPDATE messages SET audio_transcript = $2 WHERE id = $1::uuid AND audio_transcript IS NULL",
            message_id,
            text,
        )
        return

    await supabase_execute(
        supabase.table("messages")
        .update({"audio_transcript": text})
        .eq("id", message_id)
        .is_("audio_transcript", "null")
    )


async def _fetch_audio_bytes_for_transcription(
    message: Dict[str, Any],
    account: Dict[str, Any],
) -> Tuple[bytes, str]:
    storage_url = message.get("storage_url")
    if storage_url:
        client = await get_http_client_for_media()
        resp = await client.get(storage_url, timeout=120.0, follow_redirects=True)
        resp.raise_for_status()
        header_mime = (resp.headers.get("content-type") or "").split(";")[0].strip()
        mime = header_mime or message.get("media_mime_type") or "audio/ogg"
        return resp.content, mime

    content, mime_type, _ = await fetch_message_media_content(message, account)
    return content, mime_type


async def _transcribe_audio_bytes_with_gemini(
    *,
    media_data: bytes,
    content_type: str,
    log_label: str,
) -> Optional[str]:
    mime = _normalize_audio_mime(content_type)
    if not mime.startswith("audio/"):
        logger.debug("audio transcript: reject mime %r for %s", mime, log_label)
        return None

    model = _transcription_model()
    b64 = base64.standard_b64encode(media_data).decode("ascii")
    parts: List[Dict[str, Any]] = [
        {"inlineData": {"mimeType": mime, "data": b64}},
        {"text": _TRANSCRIBE_PROMPT},
    ]
    payload: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": _generation_config(model),
    }

    endpoint_v1beta = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    endpoint_v1 = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent"

    data: Optional[Dict[str, Any]] = None
    try:
        data = await gemini_circuit_breaker.call_async(
            _call_gemini_api,
            endpoint_v1beta,
            payload,
            log_label,
            read_timeout=120.0,
        )
    except CircuitBreakerOpenError as exc:
        logger.warning("audio transcript: circuit open %s: %s", log_label, exc)
        return None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 404):
            logger.info(
                "audio transcript: v1beta failed (%s), trying v1 for %s",
                exc.response.status_code,
                log_label,
            )
            try:
                data = await gemini_circuit_breaker.call_async(
                    _call_gemini_api,
                    endpoint_v1,
                    payload,
                    log_label,
                    read_timeout=120.0,
                )
            except Exception as exc2:  # noqa: BLE001
                logger.warning(
                    "audio transcript: v1 failed %s: %s body=%s",
                    log_label,
                    exc2,
                    getattr(getattr(exc2, "response", None), "text", "")[:500],
                )
                return None
        else:
            logger.warning(
                "audio transcript: HTTP error %s: %s %s",
                log_label,
                exc.response.status_code,
                exc.response.text[:500],
            )
            return None
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("audio transcript: network error %s: %s", log_label, exc)
        return None

    if not data:
        return None
    return _extract_text_from_gemini_response(data)


async def transcribe_inbound_audio_on_demand_for_message(
    message: Dict[str, Any],
    *,
    for_bot: bool = False,
) -> Dict[str, Any]:
    """
    Retourne soit { ok, transcript, cached }, soit { ok: False, status, detail }.
    for_bot: si True, ignore GEMINI_AUDIO_TRANSCRIPTION_ENABLED (transcription pour bot / playground).
    """
    if not for_bot and not settings.GEMINI_AUDIO_TRANSCRIPTION_ENABLED:
        return {"ok": False, "status": 403, "detail": "audio_transcription_disabled"}

    if not settings.GEMINI_API_KEY:
        return {"ok": False, "status": 503, "detail": "gemini_not_configured"}

    mid = message.get("id")
    if not mid:
        return {"ok": False, "status": 400, "detail": "invalid_message"}

    existing = (message.get("audio_transcript") or "").strip()
    if existing:
        return {"ok": True, "transcript": existing, "cached": True}

    if (message.get("direction") or "").lower() != "inbound":
        return {"ok": False, "status": 400, "detail": "transcription_inbound_only"}

    mtype = (message.get("message_type") or "").lower()
    if mtype not in ("audio", "voice"):
        return {"ok": False, "status": 400, "detail": "not_audio_message"}

    if not message.get("storage_url") and not message.get("media_id"):
        return {"ok": False, "status": 400, "detail": "media_not_available"}

    conversation = await get_conversation_by_id(message.get("conversation_id"))
    if not conversation:
        return {"ok": False, "status": 404, "detail": "conversation_not_found"}

    account = await get_account_by_id(conversation["account_id"])
    if not account:
        return {"ok": False, "status": 404, "detail": "account_not_found"}

    try:
        media_data, raw_mime = await _fetch_audio_bytes_for_transcription(message, account)
    except ValueError as exc:
        code = str(exc)
        if code in ("media_expired_or_invalid", "media_not_found"):
            return {"ok": False, "status": 410, "detail": code}
        if code == "media_missing":
            return {"ok": False, "status": 400, "detail": "media_not_available"}
        return {"ok": False, "status": 502, "detail": "media_fetch_failed"}
    except httpx.HTTPError as exc:
        logger.warning("audio transcript: fetch bytes failed message_id=%s: %s", mid, exc)
        return {"ok": False, "status": 502, "detail": "media_fetch_failed"}

    max_b = _effective_max_bytes()
    if len(media_data) > max_b:
        return {"ok": False, "status": 400, "detail": "audio_file_too_large"}

    text = await _transcribe_audio_bytes_with_gemini(
        media_data=media_data,
        content_type=raw_mime,
        log_label=f"transcribe-{mid}",
    )
    if not text:
        return {"ok": False, "status": 502, "detail": "transcription_failed"}

    try:
        await _save_audio_transcript_if_empty(str(mid), text)
    except Exception:  # noqa: BLE001
        logger.exception("audio transcript: DB save failed message_id=%s", mid)
        return {"ok": False, "status": 500, "detail": "transcription_save_failed"}

    logger.info("audio transcript: saved message_id=%s chars=%d", mid, len(text))
    return {"ok": True, "transcript": text.strip(), "cached": False}


async def ensure_inbound_audio_transcript_for_bot(message_id: str) -> Optional[str]:
    """
    Transcrit un vocal entrant pour alimenter Gemini / playground (même logique que l’API manuelle).
    Réutilise audio_transcript en base si déjà présent.
    Retente quelques fois en cas d’erreur réseau / média non prêt pour laisser le bot avancer.
    """
    from app.services.message_service import get_message_by_id

    last_detail: Optional[str] = None
    for attempt, delay_s in enumerate(_BOT_TRANSCRIPTION_RETRY_DELAYS_S):
        if delay_s:
            await asyncio.sleep(delay_s)
        message = await get_message_by_id(message_id)
        if not message:
            return None
        existing = (message.get("audio_transcript") or "").strip()
        if existing:
            return existing
        result = await transcribe_inbound_audio_on_demand_for_message(message, for_bot=True)
        if result.get("ok"):
            return (result.get("transcript") or "").strip()
        last_detail = str(result.get("detail") or "")
        if last_detail not in _RETRYABLE_BOT_TRANSCRIPTION_DETAILS:
            break
        logger.info(
            "bot: transcription audio nouvel essai message_id=%s attempt=%s/%s detail=%s",
            message_id,
            attempt + 1,
            len(_BOT_TRANSCRIPTION_RETRY_DELAYS_S),
            last_detail,
        )
    logger.warning(
        "bot: transcription audio échouée message_id=%s detail=%s",
        message_id,
        last_detail,
    )
    return None
