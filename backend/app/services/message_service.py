import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.db import supabase
from app.services.account_service import (
    get_account_by_id,
    get_account_by_phone_number_id,
)


async def handle_incoming_message(data: dict):
    """
    Parse le webhook WhatsApp Cloud API et stocke les messages + statuts.
    """
    print("Webhook received:", data)

    for entry in data.get("entry", []):
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            account = get_account_by_phone_number_id(metadata.get("phone_number_id"))
            if not account:
                print("Unknown account for payload; skipping", metadata)
                continue

            contacts_map = {c.get("wa_id"): c for c in value.get("contacts", []) if c.get("wa_id")}

            for message in value.get("messages", []):
                _process_incoming_message(account["id"], message, contacts_map)

            for status in value.get("statuses", []):
                _process_status(status, account)

    return True


def _process_incoming_message(
    account_id: str, message: Dict[str, Any], contacts_map: Dict[str, Any]
):
    wa_id = message.get("from")
    if not wa_id:
        return

    contact_info = contacts_map.get(wa_id, {})
    profile_name = (
        contact_info.get("profile", {}).get("name")
        if isinstance(contact_info.get("profile"), dict)
        else None
    )

    timestamp_iso = _timestamp_to_iso(message.get("timestamp"))
    contact = _upsert_contact(wa_id, profile_name)
    conversation = _upsert_conversation(account_id, contact["id"], wa_id, timestamp_iso)
    msg_type_raw = message.get("type")
    msg_type = msg_type_raw.lower() if isinstance(msg_type_raw, str) else msg_type_raw

    content_text = _extract_content_text(message)
    media_meta = _extract_media_metadata(message)

    supabase.table("messages").upsert(
        {
            "conversation_id": conversation["id"],
            "direction": "inbound",
            "content_text": content_text,
            "timestamp": timestamp_iso,
            "wa_message_id": message.get("id"),
            "message_type": msg_type,
            "status": "received",
            "media_id": media_meta.get("media_id"),
            "media_mime_type": media_meta.get("media_mime_type"),
            "media_filename": media_meta.get("media_filename"),
        },
        on_conflict="wa_message_id",
    ).execute()

    _update_conversation_timestamp(conversation["id"], timestamp_iso)
    _increment_unread_count(conversation)


def _process_status(status_payload: Dict[str, Any], account: Dict[str, Any]):
    message_id = status_payload.get("id")
    status_value = status_payload.get("status")
    recipient_id = status_payload.get("recipient_id")
    timestamp_iso = _timestamp_to_iso(status_payload.get("timestamp"))

    if not message_id or not status_value:
        return

    existing = (
        supabase.table("messages")
        .select("id, conversation_id")
        .eq("wa_message_id", message_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        record = existing.data[0]
        supabase.table("messages").update(
            {"status": status_value, "timestamp": timestamp_iso}
        ).eq("id", record["id"]).execute()
        _update_conversation_timestamp(record["conversation_id"], timestamp_iso)
        return

    if not recipient_id or not account:
        return

    conversation = (
        supabase.table("conversations")
        .select("id")
        .eq("account_id", account.get("id"))
        .eq("client_number", recipient_id)
        .limit(1)
        .execute()
    )

    if conversation.data:
        conv = conversation.data[0]
    else:
        contact = _upsert_contact(recipient_id, None)
        conv = _upsert_conversation(account["id"], contact["id"], recipient_id, timestamp_iso)

    supabase.table("messages").upsert(
        {
            "conversation_id": conv["id"],
            "direction": "outbound",
            "content_text": "[status update]",
            "timestamp": timestamp_iso,
            "wa_message_id": message_id,
            "message_type": status_payload.get("type") or "status",
            "status": status_value,
        },
        on_conflict="wa_message_id",
    ).execute()
    _update_conversation_timestamp(conv["id"], timestamp_iso)


def _upsert_contact(wa_id: str, profile_name: Optional[str]):
    payload = {"whatsapp_number": wa_id}
    if profile_name:
        payload["display_name"] = profile_name

    res = (
        supabase.table("contacts")
        .upsert(payload, on_conflict="whatsapp_number")
        .execute()
    )
    return res.data[0]


def _upsert_conversation(
    account_id: str, contact_id: str, client_number: str, timestamp_iso: str
):
    res = (
        supabase.table("conversations")
        .upsert(
            {
                "contact_id": contact_id,
                "client_number": client_number,
                "account_id": account_id,
                "status": "open",
                "updated_at": timestamp_iso,
            },
            on_conflict="account_id,client_number",
        )
        .execute()
    )
    return res.data[0]


def _extract_content_text(message: Dict[str, Any]) -> str:
    msg_type = message.get("type")
    if isinstance(msg_type, str):
        msg_type = msg_type.lower()

    if msg_type == "text":
        return message.get("text", {}).get("body", "")

    if msg_type == "interactive":
        interactive = message.get("interactive", {})
        if interactive.get("type") == "button_reply":
            return interactive.get("button_reply", {}).get("title", "")
        if interactive.get("type") == "list_reply":
            return interactive.get("list_reply", {}).get("title", "")

    if msg_type == "image":
        caption = message.get("image", {}).get("caption")
        return caption or "[image]"

    if msg_type == "audio":
        return "[audio]"

    if msg_type == "document":
        caption = message.get("document", {}).get("caption")
        return caption or "[document]"

    # fallback: conserver la totalité du payload
    return json.dumps(message)


def _timestamp_to_iso(raw_ts: Optional[str]) -> str:
    if raw_ts:
        try:
            return datetime.fromtimestamp(int(raw_ts), tz=timezone.utc).isoformat()
        except (ValueError, TypeError):
            pass

    return datetime.now(timezone.utc).isoformat()


def _update_conversation_timestamp(conversation_id: str, timestamp_iso: Optional[str] = None):
    supabase.table("conversations").update(
        {"updated_at": timestamp_iso or datetime.now(timezone.utc).isoformat()}
    ).eq("id", conversation_id).execute()


def _increment_unread_count(conversation: Dict[str, Any]):
    current = conversation.get("unread_count") or 0
    new_value = current + 1
    supabase.table("conversations").update({"unread_count": new_value}).eq("id", conversation["id"]).execute()
    conversation["unread_count"] = new_value


async def get_messages(conversation_id: str):
    res = (
        supabase.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("timestamp")
        .execute()
    )
    return res.data


async def send_message(payload: dict):
    conv_id = payload.get("conversation_id")
    text = payload.get("content")

    if not conv_id or not text:
        return {"error": "invalid_payload", "message": "conversation_id and content are required"}

    conv_res = supabase.table("conversations").select("*").eq("id", conv_id).execute()
    if not conv_res.data:
        return {"error": "conversation_not_found"}

    conversation = conv_res.data[0]
    to_number = conversation["client_number"]
    account_id = conversation.get("account_id")

    account = get_account_by_id(account_id)
    if not account:
        return {"error": "account_not_found"}

    phone_id = account.get("phone_number_id") or settings.WHATSAPP_PHONE_ID
    token = account.get("access_token") or settings.WHATSAPP_TOKEN

    if not phone_id or not token:
        return {"error": "whatsapp_not_configured"}

    body = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://graph.facebook.com/v19.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )

    if response.is_error:
        print("WhatsApp send error:", response.status_code, response.text)
        return {
            "error": "whatsapp_api_error",
            "status_code": response.status_code,
            "details": response.text,
        }

    message_id = None
    try:
        response_json = response.json()
        message_id = response_json.get("messages", [{}])[0].get("id")
    except ValueError:
        response_json = None

    timestamp_iso = datetime.now(timezone.utc).isoformat()
    message_payload = {
        "conversation_id": conv_id,
        "direction": "outbound",
        "content_text": text,
        "timestamp": timestamp_iso,
        "wa_message_id": message_id,
        "message_type": "text",
        "status": "sent",
    }

    supabase.table("messages").upsert(message_payload, on_conflict="wa_message_id").execute()
    _update_conversation_timestamp(conv_id, timestamp_iso)

    return {"status": "sent", "message_id": message_id}


def _extract_media_metadata(message: Dict[str, Any]) -> Dict[str, Optional[str]]:
    msg_type = message.get("type")
    if isinstance(msg_type, str):
        msg_type = msg_type.lower()
    media_section: Optional[Dict[str, Any]] = None

    if msg_type in {"audio", "voice"}:
        media_section = message.get("audio") or message.get("voice")
    elif msg_type == "image":
        media_section = message.get("image")
    elif msg_type == "video":
        media_section = message.get("video")
    elif msg_type == "document":
        media_section = message.get("document")
    elif msg_type == "sticker":
        media_section = message.get("sticker")
    elif msg_type == "interactive":
        interactive = message.get("interactive", {})
        if interactive.get("type") == "list_reply":
            media_section = None
    elif msg_type == "contacts":
        media_section = None

    if media_section and media_section.get("id"):
        return {
            "media_id": media_section.get("id"),
            "media_mime_type": media_section.get("mime_type"),
            "media_filename": media_section.get("filename") or media_section.get("sha256"),
        }

    return {}


async def get_message_by_id(message_id: str) -> Optional[Dict[str, Any]]:
    res = (
        supabase.table("messages")
        .select("*")
        .eq("id", message_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


async def fetch_message_media_content(
    message: Dict[str, Any], account: Dict[str, Any]
) -> Tuple[bytes, str, Optional[str]]:
    media_id = message.get("media_id")
    if not media_id:
        raise ValueError("media_missing")

    token = account.get("access_token") or settings.WHATSAPP_TOKEN
    if not token:
        raise ValueError("missing_token")

    async with httpx.AsyncClient(timeout=60) as client:
        meta_resp = await client.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            params={"access_token": token},
        )
        meta_resp.raise_for_status()
        meta_json = meta_resp.json()
        download_url = meta_json.get("url")
        mime_type = (
            meta_json.get("mime_type")
            or message.get("media_mime_type")
            or "application/octet-stream"
        )

        if not download_url:
            raise ValueError("media_url_missing")

        media_resp = await client.get(download_url, params={"access_token": token})
        media_resp.raise_for_status()
        content = media_resp.content

    filename = message.get("media_filename") or meta_json.get("file_name")
    return content, mime_type, filename