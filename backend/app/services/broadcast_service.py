import csv
import io
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.db import supabase, supabase_execute
from app.core.pg import execute as pg_execute, fetch_all, fetch_one, get_pool
from app.services.account_service import get_account_by_id
from app.services.conversation_service import (
    find_or_create_conversation as _find_or_create_conversation,
    normalize_phone_number,
)
from app.services.message_service import (
    send_message,
    is_within_free_window,
)
from app.services.pending_template_service import create_and_queue_template
from app.services.template_deduplication import find_or_create_template

logger = logging.getLogger(__name__)


def _parse_scheduled_for_iso(value: Optional[str]) -> Optional[datetime]:
    if not value or not str(value).strip():
        return None
    s = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ==================== GROUPES ====================

async def create_broadcast_group(
    account_id: str,
    name: str,
    description: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Crée un nouveau groupe de diffusion"""
    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO broadcast_groups (account_id, name, description, created_by)
            VALUES ($1::uuid, $2, $3, $4::uuid)
            RETURNING *
            """,
            account_id, name, description, created_by,
        )
        if not row:
            raise ValueError("Failed to create broadcast group")
        return row
    result = await supabase_execute(
        supabase.table("broadcast_groups")
        .insert({
            "account_id": account_id,
            "name": name,
            "description": description,
            "created_by": created_by,
        })
    )
    if not result.data or len(result.data) == 0:
        raise ValueError("Failed to create broadcast group")
    return result.data[0]


async def get_broadcast_group(group_id: str) -> Optional[Dict[str, Any]]:
    """Récupère un groupe par son ID"""
    if get_pool():
        return await fetch_one("SELECT * FROM broadcast_groups WHERE id = $1::uuid LIMIT 1", group_id)
    result = await supabase_execute(
        supabase.table("broadcast_groups").select("*").eq("id", group_id).limit(1)
    )
    return result.data[0] if result.data and len(result.data) > 0 else None


async def get_broadcast_groups(account_id: str) -> List[Dict[str, Any]]:
    """Récupère tous les groupes d'un compte"""
    if get_pool():
        rows = await fetch_all(
            "SELECT * FROM broadcast_groups WHERE account_id = $1::uuid ORDER BY created_at DESC",
            account_id,
        )
        return rows
    result = await supabase_execute(
        supabase.table("broadcast_groups")
        .select("*")
        .eq("account_id", account_id)
        .order("created_at", desc=True)
    )
    return result.data or []


async def update_broadcast_group(
    group_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Met à jour un groupe"""
    if get_pool():
        now = datetime.now(timezone.utc)
        if name is not None and description is not None:
            await pg_execute(
                "UPDATE broadcast_groups SET name = $2, description = $3, updated_at = $4::timestamptz WHERE id = $1::uuid",
                group_id, name, description, now,
            )
        elif name is not None:
            await pg_execute(
                "UPDATE broadcast_groups SET name = $2, updated_at = $3::timestamptz WHERE id = $1::uuid",
                group_id, name, now,
            )
        elif description is not None:
            await pg_execute(
                "UPDATE broadcast_groups SET description = $2, updated_at = $3::timestamptz WHERE id = $1::uuid",
                group_id, description, now,
            )
        else:
            await pg_execute(
                "UPDATE broadcast_groups SET updated_at = $2::timestamptz WHERE id = $1::uuid",
                group_id, now,
            )
        return await fetch_one("SELECT * FROM broadcast_groups WHERE id = $1::uuid LIMIT 1", group_id)
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if name is not None:
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
    await supabase_execute(
        supabase.table("broadcast_groups").update(update_data).eq("id", group_id)
    )
    updated = await supabase_execute(
        supabase.table("broadcast_groups").select("*").eq("id", group_id).limit(1)
    )
    return updated.data[0] if updated.data and len(updated.data) > 0 else None


async def delete_broadcast_group(group_id: str) -> bool:
    """Supprime un groupe (cascade sur recipients et campaigns)"""
    if get_pool():
        await pg_execute("DELETE FROM broadcast_groups WHERE id = $1::uuid", group_id)
    else:
        await supabase_execute(
            supabase.table("broadcast_groups").delete().eq("id", group_id)
        )
    return True


# ==================== DESTINATAIRES ====================

async def add_recipient_to_group(
    group_id: str,
    phone_number: str,
    contact_id: Optional[str] = None,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Ajoute un destinataire à un groupe"""
    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO broadcast_group_recipients (group_id, contact_id, phone_number, display_name)
            VALUES ($1::uuid, $2::uuid, $3, $4)
            RETURNING *
            """,
            group_id, contact_id, phone_number, display_name,
        )
        if not row:
            raise ValueError("Failed to add recipient to group")
        return row
    result = await supabase_execute(
        supabase.table("broadcast_group_recipients")
        .insert({
            "group_id": group_id,
            "contact_id": contact_id,
            "phone_number": phone_number,
            "display_name": display_name,
        })
    )
    if not result.data or len(result.data) == 0:
        raise ValueError("Failed to add recipient to group")
    return result.data[0]


async def get_group_recipients(group_id: str) -> List[Dict[str, Any]]:
    """Récupère tous les destinataires d'un groupe"""
    if get_pool():
        rows = await fetch_all(
            """
            SELECT r.*, c.display_name AS contact_display_name, c.whatsapp_number AS contact_whatsapp_number, c.profile_picture_url AS contact_profile_picture_url
            FROM broadcast_group_recipients r
            LEFT JOIN contacts c ON c.id = r.contact_id
            WHERE r.group_id = $1::uuid
            ORDER BY r.created_at ASC
            """,
            group_id,
        )
        # Normaliser pour ressembler au format Supabase (contacts: { display_name, whatsapp_number, profile_picture_url })
        out = []
        for r in rows:
            row = dict(r)
            if row.get("contact_display_name") is not None or row.get("contact_whatsapp_number") is not None or row.get("contact_profile_picture_url") is not None:
                row["contacts"] = {
                    "display_name": row.pop("contact_display_name", None),
                    "whatsapp_number": row.pop("contact_whatsapp_number", None),
                    "profile_picture_url": row.pop("contact_profile_picture_url", None),
                }
            else:
                for k in list(row.keys()):
                    if k.startswith("contact_"):
                        row.pop(k, None)
                row["contacts"] = None
            out.append(row)
        return out
    result = await supabase_execute(
        supabase.table("broadcast_group_recipients")
        .select("*, contacts(display_name, whatsapp_number, profile_picture_url)")
        .eq("group_id", group_id)
        .order("created_at", desc=False)
    )
    return result.data or []


async def phone_in_broadcast_group(group_id: str, normalized_phone: str) -> bool:
    """True si le numéro normalisé est membre du groupe (comparaison numéros normalisés)."""
    from app.services.conversation_service import normalize_phone_number

    target = normalize_phone_number(normalized_phone or "")
    if not target:
        return False
    recipients = await get_group_recipients(group_id)
    for r in recipients:
        p = normalize_phone_number(str(r.get("phone_number") or ""))
        if p and p == target:
            return True
    return False


async def remove_recipient_from_group(recipient_id: str) -> bool:
    """Retire un destinataire d'un groupe"""
    if get_pool():
        await pg_execute("DELETE FROM broadcast_group_recipients WHERE id = $1::uuid", recipient_id)
    else:
        await supabase_execute(
            supabase.table("broadcast_group_recipients").delete().eq("id", recipient_id)
        )
    return True


# ==================== IMPORT CSV / LISTE (contacts + inbox + groupe) ====================

_MAX_IMPORT_ROWS = 10000
_MAX_IMPORT_BYTES = 6 * 1024 * 1024


def _normalize_csv_header(h: str) -> str:
    s = (h or "").strip().lower()
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), (" ", "_"), ("°", "")):
        s = s.replace(a, b)
    return s.strip("_").strip()


def _phone_from_normalized_row(r: Dict[str, str]) -> Optional[str]:
    for key in ("phone", "telephone", "tel", "mobile", "whatsapp", "numero"):
        v = (r.get(key) or "").strip()
        if v:
            return v
    digits_min = 8
    for v in r.values():
        vv = (v or "").strip()
        d = re.sub(r"\D", "", vv)
        if len(d) >= digits_min:
            return vv
    return None


def _display_name_from_normalized_row(r: Dict[str, str]) -> Optional[str]:
    pre = (r.get("prenom") or r.get("firstname") or "").strip()
    nom = (r.get("nom") or r.get("nom_famille") or r.get("lastname") or "").strip()
    if pre and nom:
        return f"{pre} {nom}".strip()
    for key in ("name", "display_name", "fullname", "contact", "client", "societe", "entreprise", "company"):
        v = (r.get(key) or "").strip()
        if v:
            return v
    return None


def parse_broadcast_import_csv(content: bytes, max_rows: int = _MAX_IMPORT_ROWS) -> List[Dict[str, str]]:
    """
    Parse un CSV (séparateur , ; ou tab). Colonnes reconnues : phone / telephone / mobile / nom / prenom / name…
    Retourne une liste de {"phone": str brute, "name": str optionnelle}.
    """
    if len(content) > _MAX_IMPORT_BYTES:
        raise ValueError("file_too_large")
    text = content.decode("utf-8-sig", errors="replace")
    buf = io.StringIO(text)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    buf.seek(0)
    reader = csv.DictReader(buf, dialect=dialect)
    out: List[Dict[str, str]] = []
    for i, raw in enumerate(reader):
        if i >= max_rows:
            break
        if not raw:
            continue
        canon: Dict[str, str] = {}
        for k, v in raw.items():
            if k is None:
                continue
            nk = _normalize_csv_header(str(k))
            if not nk:
                continue
            canon[nk] = ("" if v is None else str(v)).strip()
        phone = _phone_from_normalized_row(canon)
        if not phone:
            continue
        name = _display_name_from_normalized_row(canon) or ""
        out.append({"phone": phone, "name": name})
    return out


async def _update_contact_display_name(contact_id: str, display_name: str) -> None:
    if not contact_id or not display_name or not str(display_name).strip():
        return
    n = str(display_name).strip()
    if get_pool():
        await pg_execute(
            "UPDATE contacts SET display_name = $2 WHERE id = $1::uuid",
            contact_id,
            n,
        )
    else:
        await supabase_execute(supabase.table("contacts").update({"display_name": n}).eq("id", contact_id))


async def _ensure_contact_only(phone: str, display_name: Optional[str]) -> Optional[str]:
    """Contact WhatsApp global (sans créer de conversation)."""
    dn = str(display_name).strip() if display_name else None
    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO contacts (whatsapp_number, display_name)
            VALUES ($1, $2)
            ON CONFLICT (whatsapp_number) DO UPDATE SET
                display_name = CASE
                    WHEN EXCLUDED.display_name IS NOT NULL AND BTRIM(EXCLUDED.display_name) <> ''
                    THEN EXCLUDED.display_name
                    ELSE contacts.display_name
                END
            RETURNING id
            """,
            phone,
            dn,
        )
        return str(row["id"]) if row else None
    payload: Dict[str, Any] = {"whatsapp_number": phone}
    if dn:
        payload["display_name"] = dn
    res = await supabase_execute(supabase.table("contacts").upsert(payload, on_conflict="whatsapp_number"))
    if res.data and len(res.data) > 0:
        return str(res.data[0]["id"])
    sel = await supabase_execute(
        supabase.table("contacts").select("id").eq("whatsapp_number", phone).limit(1)
    )
    if sel.data and len(sel.data) > 0:
        cid = str(sel.data[0]["id"])
        if dn:
            await supabase_execute(supabase.table("contacts").update({"display_name": dn}).eq("id", cid))
        return cid
    return None


async def upsert_recipient_to_group(
    group_id: str,
    phone_number: str,
    contact_id: Optional[str],
    display_name: Optional[str],
) -> Dict[str, Any]:
    """Ajoute ou met à jour un destinataire (même numéro dans le groupe)."""
    dn = str(display_name).strip() if display_name else None
    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO broadcast_group_recipients (group_id, contact_id, phone_number, display_name)
            VALUES ($1::uuid, $2::uuid, $3, $4)
            ON CONFLICT (group_id, phone_number) DO UPDATE SET
                contact_id = COALESCE(EXCLUDED.contact_id, broadcast_group_recipients.contact_id),
                display_name = CASE
                    WHEN EXCLUDED.display_name IS NOT NULL AND BTRIM(EXCLUDED.display_name) <> ''
                    THEN EXCLUDED.display_name
                    ELSE broadcast_group_recipients.display_name
                END
            RETURNING *
            """,
            group_id,
            contact_id,
            phone_number,
            dn,
        )
        if not row:
            raise ValueError("upsert_recipient_failed")
        return dict(row)
    res = await supabase_execute(
        supabase.table("broadcast_group_recipients").upsert(
            {
                "group_id": group_id,
                "contact_id": contact_id,
                "phone_number": phone_number,
                "display_name": dn,
            },
            on_conflict="group_id,phone_number",
        )
    )
    if res.data and len(res.data) > 0:
        return res.data[0]
    sel = await supabase_execute(
        supabase.table("broadcast_group_recipients")
        .select("*")
        .eq("group_id", group_id)
        .eq("phone_number", phone_number)
        .limit(1)
    )
    if sel.data and len(sel.data) > 0:
        return sel.data[0]
    raise ValueError("upsert_recipient_failed")


async def import_recipients_for_broadcast_group(
    group_id: str,
    account_id: str,
    rows: List[Dict[str, Any]],
    *,
    create_conversations: bool = True,
) -> Dict[str, Any]:
    """
    Pour chaque ligne : normalise le numéro, met à jour/crée le contact, optionnellement la conversation inbox,
    puis rattache au groupe de campagne.
    """
    imported = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []

    for raw in rows:
        raw_phone = (raw.get("phone") or raw.get("telephone") or "").strip()
        if not raw_phone:
            skipped += 1
            continue
        name_raw = raw.get("name") or raw.get("display_name") or ""
        display_name = str(name_raw).strip() if name_raw else None

        normalized = normalize_phone_number(raw_phone)
        if not normalized:
            errors.append({"phone": raw_phone, "error": "invalid_phone"})
            continue

        contact_id: Optional[str] = None
        try:
            if create_conversations:
                conv = await _find_or_create_conversation(account_id, normalized)
                if not conv:
                    errors.append({"phone": raw_phone, "error": "conversation_failed"})
                    continue
                contact_id = conv.get("contact_id")
            else:
                contact_id = await _ensure_contact_only(normalized, display_name)
                if not contact_id:
                    errors.append({"phone": raw_phone, "error": "contact_failed"})
                    continue
        except ValueError as e:
            errors.append({"phone": raw_phone, "error": str(e)})
            continue
        except Exception as e:
            logger.exception("import row failed for %s", raw_phone)
            errors.append({"phone": raw_phone, "error": str(e)})
            continue

        if contact_id and display_name:
            await _update_contact_display_name(str(contact_id), display_name)

        try:
            await upsert_recipient_to_group(
                group_id,
                normalized,
                str(contact_id) if contact_id else None,
                display_name,
            )
            imported += 1
        except Exception as e:
            logger.exception("upsert recipient failed for %s", normalized)
            errors.append({"phone": raw_phone, "error": str(e)})

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_input_rows": len(rows),
    }


# ==================== CAMPAGNES ====================

async def create_broadcast_campaign(
    group_id: str,
    account_id: str,
    content_text: str,
    message_type: str = "text",
    media_url: Optional[str] = None,
    sent_by: Optional[str] = None,
    scheduled_for: Optional[datetime] = None,
    defer_dispatch: bool = False,
) -> Dict[str, Any]:
    """Crée une ligne campagne (envoi immédiat ou planifié si defer_dispatch)."""
    recipients = await get_group_recipients(group_id)
    total_recipients = len(recipients)

    if get_pool():
        if defer_dispatch and scheduled_for is not None:
            row = await fetch_one(
                """
                INSERT INTO broadcast_campaigns (
                    group_id, account_id, content_text, message_type, media_url, sent_by, total_recipients,
                    scheduled_for, schedule_status, sent_at
                )
                VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6::uuid, $7, $8::timestamptz, 'scheduled', NULL)
                RETURNING *
                """,
                group_id,
                account_id,
                content_text,
                message_type,
                media_url,
                sent_by,
                total_recipients,
                scheduled_for,
            )
        else:
            row = await fetch_one(
                """
                INSERT INTO broadcast_campaigns (
                    group_id, account_id, content_text, message_type, media_url, sent_by, total_recipients,
                    scheduled_for, schedule_status, sent_at
                )
                VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6::uuid, $7, NULL, 'done', now())
                RETURNING *
                """,
                group_id,
                account_id,
                content_text,
                message_type,
                media_url,
                sent_by,
                total_recipients,
            )
        if not row:
            raise ValueError("Failed to create broadcast campaign")
        return row

    insert_payload: Dict[str, Any] = {
        "group_id": group_id,
        "account_id": account_id,
        "content_text": content_text,
        "message_type": message_type,
        "media_url": media_url,
        "sent_by": sent_by,
        "total_recipients": total_recipients,
    }
    if defer_dispatch and scheduled_for is not None:
        insert_payload["scheduled_for"] = scheduled_for.isoformat()
        insert_payload["schedule_status"] = "scheduled"
        insert_payload["sent_at"] = None
    else:
        insert_payload["schedule_status"] = "done"
        insert_payload["sent_at"] = datetime.now(timezone.utc).isoformat()

    result = await supabase_execute(
        supabase.table("broadcast_campaigns").insert(insert_payload)
    )
    if not result.data or len(result.data) == 0:
        raise ValueError("Failed to create broadcast campaign")
    return result.data[0]


async def get_broadcast_campaign(campaign_id: str) -> Optional[Dict[str, Any]]:
    """Récupère une campagne par son ID"""
    if get_pool():
        return await fetch_one("SELECT * FROM broadcast_campaigns WHERE id = $1::uuid LIMIT 1", campaign_id)
    result = await supabase_execute(
        supabase.table("broadcast_campaigns").select("*").eq("id", campaign_id).limit(1)
    )
    return result.data[0] if result.data and len(result.data) > 0 else None


async def get_broadcast_campaigns(group_id: Optional[str] = None, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Récupère les campagnes (optionnellement filtrées par groupe ou compte)"""
    if get_pool():
        if group_id and account_id:
            return await fetch_all(
                """
                SELECT * FROM broadcast_campaigns
                WHERE group_id = $1::uuid AND account_id = $2::uuid
                ORDER BY COALESCE(sent_at, scheduled_for) DESC NULLS LAST
                """,
                group_id, account_id,
            )
        if group_id:
            return await fetch_all(
                """
                SELECT * FROM broadcast_campaigns
                WHERE group_id = $1::uuid
                ORDER BY COALESCE(sent_at, scheduled_for) DESC NULLS LAST
                """,
                group_id,
            )
        if account_id:
            return await fetch_all(
                """
                SELECT * FROM broadcast_campaigns
                WHERE account_id = $1::uuid
                ORDER BY COALESCE(sent_at, scheduled_for) DESC NULLS LAST
                """,
                account_id,
            )
        return await fetch_all(
            "SELECT * FROM broadcast_campaigns ORDER BY COALESCE(sent_at, scheduled_for) DESC NULLS LAST"
        )
    query = supabase.table("broadcast_campaigns").select("*")
    if group_id:
        query = query.eq("group_id", group_id)
    if account_id:
        query = query.eq("account_id", account_id)
    query = query.order("sent_at", desc=True)
    result = await supabase_execute(query)
    return result.data or []


async def execute_broadcast_campaign_dispatch(campaign: Dict[str, Any]) -> Dict[str, Any]:
    """
    Exécute l'envoi pour une ligne broadcast_campaigns existante (immédiat ou relance planifiée).

    Gère trois cas :
    1. Tous gratuits (-24h) : envoi normal immédiat
    2. Tous payants (+24h) : création template puis envoi avec template
    3. Mix : envoi immédiat aux gratuits, création template puis envoi aux payants
    """
    group_id = str(campaign["group_id"])
    account_id = str(campaign["account_id"])
    content_text = campaign["content_text"]

    # 2. Récupérer tous les destinataires
    recipients = await get_group_recipients(group_id)
    
    if not recipients:
        logger.warning(f"No recipients in group {group_id}")
        return campaign
    
    # 3. Vérifier chaque destinataire pour séparer gratuits et payants
    account = await get_account_by_id(account_id)
    if not account:
        raise ValueError("Account not found")
    
    free_recipients = []  # Destinataires dans la fenêtre gratuite (-24h)
    paid_recipients = []  # Destinataires hors fenêtre (+24h)
    
    for recipient in recipients:
        phone_number = recipient["phone_number"]
        conversation = await _find_or_create_conversation(account_id, phone_number)
        if not conversation:
            logger.error(f"Failed to find/create conversation for {phone_number}")
            # Marquer comme échoué
            await create_recipient_stat(
                campaign_id=campaign["id"],
                recipient_id=recipient["id"],
                phone_number=phone_number,
                message_id=None,
                failed_at=datetime.now(timezone.utc).isoformat(),
                error_message="Failed to find/create conversation",
            )
            continue
        
        is_free, _ = await is_within_free_window(conversation["id"])
        if is_free:
            free_recipients.append((recipient, conversation))
        else:
            paid_recipients.append((recipient, conversation))
    
    logger.info(f"📊 Broadcast campaign {campaign['id']}: {len(free_recipients)} gratuits, {len(paid_recipients)} payants")
    
    # 4. Cas 1 : Tous gratuits - Envoi normal immédiat
    if len(paid_recipients) == 0:
        logger.info("✅ Broadcast campaign: tous les destinataires sont en fenêtre gratuite, envoi normal")
        sent_count = 0
        failed_count = 0
        
        for recipient, conversation in free_recipients:
            try:
                phone_number = recipient["phone_number"]
                
                # Envoyer le message normalement
                message_result = await send_message({
                    "conversation_id": conversation["id"],
                    "content": content_text,
                }, force_send=True)
                
                if message_result.get("error"):
                    logger.error(f"Failed to send message to {phone_number}: {message_result.get('error')}")
                    failed_count += 1
                    await create_recipient_stat(
                        campaign_id=campaign["id"],
                        recipient_id=recipient["id"],
                        phone_number=phone_number,
                        message_id=None,
                        failed_at=datetime.now(timezone.utc).isoformat(),
                        error_message=message_result.get("message", "Unknown error"),
                    )
                else:
                    import asyncio
                    await asyncio.sleep(0.5)  # Attendre l'insertion asynchrone
                    
                    wa_message_id = message_result.get("message_id")
                    message_db = None
                    if wa_message_id:
                        if get_pool():
                            row = await fetch_one("SELECT id FROM messages WHERE wa_message_id = $1 LIMIT 1", wa_message_id)
                            if row:
                                message_db = row["id"]
                        else:
                            message_db_result = await supabase_execute(
                                supabase.table("messages")
                                .select("id")
                                .eq("wa_message_id", wa_message_id)
                                .limit(1)
                            )
                            if message_db_result.data and len(message_db_result.data) > 0:
                                message_db = message_db_result.data[0]["id"]
                    
                    await create_recipient_stat(
                        campaign_id=campaign["id"],
                        recipient_id=recipient["id"],
                        phone_number=phone_number,
                        message_id=message_db,
                    )
                    sent_count += 1
                    
            except Exception as e:
                logger.error(f"Error sending to recipient {recipient.get('phone_number')}: {e}", exc_info=True)
                failed_count += 1
        
        await update_campaign_counters(campaign["id"])
        return campaign
    
    # 5. Cas 2 : Tous payants - Créer template puis envoyer avec template
    if len(free_recipients) == 0:
        logger.info("📧 Broadcast campaign: tous les destinataires sont hors fenêtre, création template")
        
        # Utiliser la première conversation comme référence pour le template
        first_recipient, first_conversation = paid_recipients[0]
        
        timestamp_iso = datetime.now(timezone.utc).isoformat()
        timestamp_dt = datetime.now(timezone.utc)
        fake_message_id = None
        if get_pool():
            row = await fetch_one(
                """
                INSERT INTO messages (conversation_id, direction, content_text, timestamp, message_type, status)
                VALUES ($1::uuid, $2, $3, $4::timestamptz, $5, $6)
                RETURNING id
                """,
                first_conversation["id"], "outbound", content_text, timestamp_dt, "text", "sent",
            )
            if not row:
                raise ValueError("Failed to create fake message for template")
            fake_message_id = row["id"]
        else:
            fake_message_payload = {
                "conversation_id": first_conversation["id"],
                "direction": "outbound",
                "content_text": content_text,
                "timestamp": timestamp_iso,
                "message_type": "text",
                "status": "sent",
            }
            fake_message_result = await supabase_execute(
                supabase.table("messages").insert(fake_message_payload)
            )
            if not fake_message_result.data:
                raise ValueError("Failed to create fake message for template")
            fake_message_id = fake_message_result.data[0]["id"]
        
        # Créer le template pour la campagne
        template_result = await find_or_create_template(
            conversation_id=first_conversation["id"],
            account_id=account_id,
            message_id=fake_message_id,
            text_content=content_text,
            campaign_id=campaign["id"]
        )
        
        if not template_result.get("success"):
            error_message = "; ".join(template_result.get("errors", ["Erreur inconnue"]))
            logger.error(f"❌ Failed to create template for broadcast: {error_message}")
            if get_pool():
                await pg_execute(
                    "UPDATE broadcast_campaigns SET failed_count = $2 WHERE id = $1::uuid",
                    campaign["id"], len(paid_recipients),
                )
            else:
                await supabase_execute(
                    supabase.table("broadcast_campaigns")
                    .update({"failed_count": len(paid_recipients)})
                    .eq("id", campaign["id"])
                )
            raise ValueError(f"Template creation failed: {error_message}")
        
        # Lier le template à la campagne
        if get_pool():
            await pg_execute(
                "UPDATE pending_template_messages SET campaign_id = $2::uuid WHERE message_id = $1::uuid",
                fake_message_id, campaign["id"],
            )
        else:
            await supabase_execute(
                supabase.table("pending_template_messages")
                .update({"campaign_id": campaign["id"]})
                .eq("message_id", fake_message_id)
            )
        
        logger.info(f"✅ Template '{template_result.get('template_name')}' created and queued for campaign {campaign['id']}")
        
        # Créer des messages "fake" pour tous les destinataires payants
        for recipient, conversation in paid_recipients:
            phone_number = recipient["phone_number"]
            
            message_db_id = None
            if get_pool():
                row = await fetch_one(
                    """
                    INSERT INTO messages (conversation_id, direction, content_text, timestamp, message_type, status)
                    VALUES ($1::uuid, $2, $3, $4::timestamptz, $5, $6)
                    RETURNING id
                    """,
                    conversation["id"], "outbound", content_text, timestamp_iso, "text", "sent",
                )
                if row:
                    message_db_id = row["id"]
            else:
                recipient_fake_message = {
                    "conversation_id": conversation["id"],
                    "direction": "outbound",
                    "content_text": content_text,
                    "timestamp": timestamp_iso,
                    "message_type": "text",
                    "status": "sent",
                }
                recipient_message_result = await supabase_execute(
                    supabase.table("messages").insert(recipient_fake_message)
                )
                if recipient_message_result.data:
                    message_db_id = recipient_message_result.data[0]["id"]
            
            await create_recipient_stat(
                campaign_id=campaign["id"],
                recipient_id=recipient["id"],
                phone_number=phone_number,
                message_id=message_db_id,
            )
        
        await update_campaign_counters(campaign["id"])
        return campaign
    
    # 6. Cas 3 : Mix - Envoyer aux gratuits immédiatement, créer template pour les payants
    logger.info(f"📧 Broadcast campaign: mix de gratuits ({len(free_recipients)}) et payants ({len(paid_recipients)})")
    
    # 6a. Envoyer immédiatement aux gratuits
    sent_count = 0
    failed_count = 0
    
    for recipient, conversation in free_recipients:
        try:
            phone_number = recipient["phone_number"]
            
            message_result = await send_message({
                "conversation_id": conversation["id"],
                "content": content_text,
            }, force_send=True)
            
            if message_result.get("error"):
                logger.error(f"Failed to send message to {phone_number}: {message_result.get('error')}")
                failed_count += 1
                await create_recipient_stat(
                    campaign_id=campaign["id"],
                    recipient_id=recipient["id"],
                    phone_number=phone_number,
                    message_id=None,
                    failed_at=datetime.now(timezone.utc).isoformat(),
                    error_message=message_result.get("message", "Unknown error"),
                )
            else:
                import asyncio
                await asyncio.sleep(0.5)
                
                wa_message_id = message_result.get("message_id")
                message_db = None
                if wa_message_id:
                    if get_pool():
                        row = await fetch_one("SELECT id FROM messages WHERE wa_message_id = $1 LIMIT 1", wa_message_id)
                        if row:
                            message_db = row["id"]
                    else:
                        message_db_result = await supabase_execute(
                            supabase.table("messages")
                            .select("id")
                            .eq("wa_message_id", wa_message_id)
                            .limit(1)
                        )
                        if message_db_result.data and len(message_db_result.data) > 0:
                            message_db = message_db_result.data[0]["id"]
                
                await create_recipient_stat(
                    campaign_id=campaign["id"],
                    recipient_id=recipient["id"],
                    phone_number=phone_number,
                    message_id=message_db,
                )
                sent_count += 1
                
        except Exception as e:
            logger.error(f"Error sending to recipient {recipient.get('phone_number')}: {e}", exc_info=True)
            failed_count += 1
    
    logger.info(f"✅ Envoyé aux gratuits: {sent_count} réussis, {failed_count} échoués")
    
    # 6b. Créer le template pour les payants (un seul template pour tous)
    first_paid_recipient, first_paid_conversation = paid_recipients[0]
    
    timestamp_iso = datetime.now(timezone.utc).isoformat()
    fake_message_id = None
    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO messages (conversation_id, direction, content_text, timestamp, message_type, status)
            VALUES ($1::uuid, $2, $3, $4::timestamptz, $5, $6)
            RETURNING id
            """,
            first_paid_conversation["id"], "outbound", content_text, timestamp_iso, "text", "sent",
        )
        if not row:
            logger.error("❌ Failed to create fake message for template (mix case)")
            for recipient, _ in paid_recipients:
                await create_recipient_stat(
                    campaign_id=campaign["id"],
                    recipient_id=recipient["id"],
                    phone_number=recipient["phone_number"],
                    message_id=None,
                    failed_at=datetime.now(timezone.utc).isoformat(),
                    error_message="Failed to create template",
                )
            await update_campaign_counters(campaign["id"])
            return campaign
        fake_message_id = row["id"]
    else:
        fake_message_payload = {
            "conversation_id": first_paid_conversation["id"],
            "direction": "outbound",
            "content_text": content_text,
            "timestamp": timestamp_iso,
            "message_type": "text",
            "status": "sent",
        }
        fake_message_result = await supabase_execute(
            supabase.table("messages").insert(fake_message_payload)
        )
        if not fake_message_result.data:
            logger.error("❌ Failed to create fake message for template (mix case)")
            for recipient, _ in paid_recipients:
                await create_recipient_stat(
                    campaign_id=campaign["id"],
                    recipient_id=recipient["id"],
                    phone_number=recipient["phone_number"],
                    message_id=None,
                    failed_at=datetime.now(timezone.utc).isoformat(),
                    error_message="Failed to create template",
                )
            await update_campaign_counters(campaign["id"])
            return campaign
        fake_message_id = fake_message_result.data[0]["id"]
    
    # Créer le template pour la campagne
    template_result = await find_or_create_template(
        conversation_id=first_paid_conversation["id"],
        account_id=account_id,
        message_id=fake_message_id,
        text_content=content_text,
        campaign_id=campaign["id"]
    )
    
    if not template_result.get("success"):
        error_message = "; ".join(template_result.get("errors", ["Erreur inconnue"]))
        logger.error(f"❌ Failed to create template for broadcast (mix case): {error_message}")
        for recipient, _ in paid_recipients:
            await create_recipient_stat(
                campaign_id=campaign["id"],
                recipient_id=recipient["id"],
                phone_number=recipient["phone_number"],
                message_id=None,
                failed_at=datetime.now(timezone.utc).isoformat(),
                error_message=f"Template creation failed: {error_message}",
            )
        await update_campaign_counters(campaign["id"])
        return campaign
    
    # Lier le template à la campagne
    if get_pool():
        await pg_execute(
            "UPDATE pending_template_messages SET campaign_id = $2::uuid WHERE message_id = $1::uuid",
            fake_message_id, campaign["id"],
        )
    else:
        await supabase_execute(
            supabase.table("pending_template_messages")
            .update({"campaign_id": campaign["id"]})
            .eq("message_id", fake_message_id)
        )
    
    logger.info(f"✅ Template '{template_result.get('template_name')}' created and queued for campaign {campaign['id']} (mix case)")
    
    # Créer des messages "fake" pour tous les destinataires payants
    for recipient, conversation in paid_recipients:
        phone_number = recipient["phone_number"]
        message_db_id = None
        if get_pool():
            row = await fetch_one(
                """
                INSERT INTO messages (conversation_id, direction, content_text, timestamp, message_type, status)
                VALUES ($1::uuid, $2, $3, $4::timestamptz, $5, $6)
                RETURNING id
                """,
                conversation["id"], "outbound", content_text, timestamp_iso, "text", "sent",
            )
            if row:
                message_db_id = row["id"]
        else:
            recipient_fake_message = {
                "conversation_id": conversation["id"],
                "direction": "outbound",
                "content_text": content_text,
                "timestamp": timestamp_iso,
                "message_type": "text",
                "status": "sent",
            }
            recipient_message_result = await supabase_execute(
                supabase.table("messages").insert(recipient_fake_message)
            )
            if recipient_message_result.data:
                message_db_id = recipient_message_result.data[0]["id"]
        
        await create_recipient_stat(
            campaign_id=campaign["id"],
            recipient_id=recipient["id"],
            phone_number=phone_number,
            message_id=message_db_id,
        )
    
    # Mettre à jour les compteurs de la campagne
    await update_campaign_counters(campaign["id"])

    return campaign


async def send_broadcast_campaign(
    group_id: str,
    account_id: str,
    content_text: str,
    message_type: str = "text",
    media_url: Optional[str] = None,
    sent_by: Optional[str] = None,
    scheduled_for: Optional[str] = None,
) -> Dict[str, Any]:
    """Crée une campagne et envoie tout de suite, ou planifie si scheduled_for est dans le futur."""
    now = datetime.now(timezone.utc)
    sched_dt = _parse_scheduled_for_iso(scheduled_for)
    defer = sched_dt is not None and sched_dt > now + timedelta(seconds=5)

    campaign = await create_broadcast_campaign(
        group_id=group_id,
        account_id=account_id,
        content_text=content_text,
        message_type=message_type,
        media_url=media_url,
        sent_by=sent_by,
        scheduled_for=sched_dt,
        defer_dispatch=defer,
    )
    if defer:
        logger.info(
            "📅 Broadcast campaign %s scheduled for %s (UTC)",
            campaign.get("id"),
            sched_dt,
        )
        return campaign
    return await execute_broadcast_campaign_dispatch(campaign)


async def _claim_next_due_scheduled_campaign(now_utc: datetime) -> Optional[Dict[str, Any]]:
    pool = get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                WITH cte AS (
                  SELECT id FROM broadcast_campaigns
                  WHERE schedule_status = 'scheduled'
                    AND scheduled_for IS NOT NULL
                    AND scheduled_for <= $1::timestamptz
                  ORDER BY scheduled_for ASC
                  LIMIT 1
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE broadcast_campaigns b
                SET schedule_status = 'sending'
                FROM cte
                WHERE b.id = cte.id AND b.schedule_status = 'scheduled'
                RETURNING b.*
                """,
                now_utc,
            )
            return dict(row) if row else None


async def _mark_scheduled_campaign_done(campaign_id: str) -> None:
    if get_pool():
        await pg_execute(
            """
            UPDATE broadcast_campaigns
            SET schedule_status = 'done', sent_at = COALESCE(sent_at, now())
            WHERE id = $1::uuid
            """,
            campaign_id,
        )
        return
    await supabase_execute(
        supabase.table("broadcast_campaigns")
        .update(
            {
                "schedule_status": "done",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", campaign_id)
    )


async def _mark_scheduled_campaign_failed(campaign_id: str) -> None:
    if get_pool():
        await pg_execute(
            "UPDATE broadcast_campaigns SET schedule_status = 'failed' WHERE id = $1::uuid",
            campaign_id,
        )
        return
    await supabase_execute(
        supabase.table("broadcast_campaigns")
        .update({"schedule_status": "failed"})
        .eq("id", campaign_id)
    )


async def process_due_scheduled_broadcasts_once() -> int:
    """Traite jusqu'à 15 campagnes dont l'heure d'envoi est dépassée."""
    if not get_pool():
        return 0

    now = datetime.now(timezone.utc)
    n = 0
    for _ in range(15):
        claimed = await _claim_next_due_scheduled_campaign(now)
        if not claimed:
            break
        try:
            await execute_broadcast_campaign_dispatch(claimed)
            await _mark_scheduled_campaign_done(str(claimed["id"]))
            n += 1
        except Exception:
            logger.exception(
                "scheduled broadcast dispatch failed campaign_id=%s",
                claimed.get("id"),
            )
            await _mark_scheduled_campaign_failed(str(claimed["id"]))
            n += 1
    return n


async def periodic_scheduled_broadcasts():
    import asyncio

    while True:
        try:
            await asyncio.sleep(30)
            await process_due_scheduled_broadcasts_once()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("periodic_scheduled_broadcasts tick failed")


# ==================== STATISTIQUES ====================

async def create_recipient_stat(
    campaign_id: str,
    recipient_id: str,
    phone_number: str,
    message_id: Optional[str] = None,
    sent_at: Optional[str] = None,
    failed_at: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Crée une entrée de statistique pour un destinataire"""
    now_iso = datetime.now(timezone.utc).isoformat()
    sent_at_val = sent_at if sent_at else (None if failed_at else now_iso)
    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO broadcast_recipient_stats (campaign_id, recipient_id, phone_number, message_id, sent_at, failed_at, error_message)
            VALUES ($1::uuid, $2::uuid, $3, $4::uuid, $5::timestamptz, $6::timestamptz, $7)
            RETURNING *
            """,
            campaign_id, recipient_id, phone_number, message_id, sent_at_val, failed_at, error_message,
        )
        if not row:
            raise ValueError("Failed to create recipient stat")
        return row
    stat_data = {
        "campaign_id": campaign_id,
        "recipient_id": recipient_id,
        "phone_number": phone_number,
        "message_id": message_id,
    }
    if sent_at_val:
        stat_data["sent_at"] = sent_at_val
    if failed_at:
        stat_data["failed_at"] = failed_at
        stat_data["error_message"] = error_message
    result = await supabase_execute(
        supabase.table("broadcast_recipient_stats").insert(stat_data)
    )
    if not result.data or len(result.data) == 0:
        raise ValueError("Failed to create recipient stat")
    return result.data[0]


async def get_recipient_stat_by_message_id(message_id: str) -> Optional[Dict[str, Any]]:
    """Trouve une stat par l'ID du message"""
    if get_pool():
        return await fetch_one(
            "SELECT * FROM broadcast_recipient_stats WHERE message_id = $1::uuid LIMIT 1",
            message_id,
        )
    result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .select("*")
        .eq("message_id", message_id)
        .limit(1)
    )
    return result.data[0] if result.data and len(result.data) > 0 else None


async def update_recipient_stat(
    stat_id: str,
    update_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Met à jour une stat"""
    from datetime import datetime as dt
    if get_pool():
        if "read_at" in update_data and update_data["read_at"]:
            row = await fetch_one(
                "SELECT sent_at FROM broadcast_recipient_stats WHERE id = $1::uuid LIMIT 1", stat_id
            )
            if row and row.get("sent_at"):
                sent_time = dt.fromisoformat(str(row["sent_at"]).replace("Z", "+00:00"))
                read_time = dt.fromisoformat(str(update_data["read_at"]).replace("Z", "+00:00"))
                update_data = {**update_data, "time_to_read": str(read_time - sent_time)}
        if "replied_at" in update_data and update_data["replied_at"]:
            row = await fetch_one(
                "SELECT sent_at FROM broadcast_recipient_stats WHERE id = $1::uuid LIMIT 1", stat_id
            )
            if row and row.get("sent_at"):
                sent_time = dt.fromisoformat(str(row["sent_at"]).replace("Z", "+00:00"))
                reply_time = dt.fromisoformat(str(update_data["replied_at"]).replace("Z", "+00:00"))
                update_data = {**update_data, "time_to_reply": str(reply_time - sent_time)}
        # Construire SET dynamiquement (on ne peut pas faire UPDATE avec dict facilement en paramètres)
        set_parts = []
        args = []
        i = 1
        for k, v in update_data.items():
            if k in ("sent_at", "delivered_at", "read_at", "failed_at", "replied_at"):
                set_parts.append(f"{k} = ${i}::timestamptz")
            elif k in ("time_to_read", "time_to_reply"):
                set_parts.append(f"{k} = ${i}::interval")
            elif k == "error_message":
                set_parts.append(f"{k} = ${i}")
            elif k == "message_id":
                set_parts.append(f"{k} = ${i}::uuid")
            elif k == "reply_message_id":
                set_parts.append(f"{k} = ${i}::uuid")
            else:
                set_parts.append(f"{k} = ${i}")
            args.append(v)
            i += 1
        if not set_parts:
            return await fetch_one("SELECT * FROM broadcast_recipient_stats WHERE id = $1::uuid LIMIT 1", stat_id)
        args.append(stat_id)
        q = "UPDATE broadcast_recipient_stats SET " + ", ".join(set_parts) + f" WHERE id = ${i}::uuid RETURNING *"
        row = await fetch_one(q, *args)
        return row
    if "read_at" in update_data and update_data["read_at"]:
        stat = await supabase_execute(
            supabase.table("broadcast_recipient_stats").select("sent_at").eq("id", stat_id).limit(1)
        )
        if stat.data and len(stat.data) > 0 and stat.data[0].get("sent_at"):
            sent_time = dt.fromisoformat(stat.data[0]["sent_at"].replace("Z", "+00:00"))
            read_time = dt.fromisoformat(update_data["read_at"].replace("Z", "+00:00"))
            update_data["time_to_read"] = str(read_time - sent_time)
    if "replied_at" in update_data and update_data["replied_at"]:
        stat = await supabase_execute(
            supabase.table("broadcast_recipient_stats").select("sent_at").eq("id", stat_id).limit(1)
        )
        if stat.data and len(stat.data) > 0 and stat.data[0].get("sent_at"):
            sent_time = dt.fromisoformat(stat.data[0]["sent_at"].replace("Z", "+00:00"))
            reply_time = dt.fromisoformat(update_data["replied_at"].replace("Z", "+00:00"))
            update_data["time_to_reply"] = str(reply_time - sent_time)
    result = await supabase_execute(
        supabase.table("broadcast_recipient_stats").update(update_data).eq("id", stat_id)
    )
    return result.data[0] if result.data else None


async def update_recipient_stat_from_webhook(
    wa_message_id: str,
    status: str,
    timestamp: str,
    error_message: Optional[str] = None,
) -> bool:
    """
    Met à jour les stats quand on reçoit un webhook de statut WhatsApp
    """
    message_id = None
    if get_pool():
        row = await fetch_one("SELECT id FROM messages WHERE wa_message_id = $1 LIMIT 1", wa_message_id)
        if not row:
            logger.debug(f"No message found with wa_message_id: {wa_message_id}")
            return False
        message_id = row["id"]
    else:
        message_result = await supabase_execute(
            supabase.table("messages").select("id").eq("wa_message_id", wa_message_id).limit(1)
        )
        if not message_result.data or len(message_result.data) == 0:
            logger.debug(f"No message found with wa_message_id: {wa_message_id}")
            return False
        message_id = message_result.data[0]["id"]
    
    stat_data = None
    if get_pool():
        stat_data = await fetch_one(
            "SELECT id, campaign_id FROM broadcast_recipient_stats WHERE message_id = $1::uuid LIMIT 1",
            message_id,
        )
    else:
        stat_result = await supabase_execute(
            supabase.table("broadcast_recipient_stats")
            .select("id, campaign_id")
            .eq("message_id", message_id)
            .limit(1)
        )
        if stat_result.data and len(stat_result.data) > 0:
            stat_data = stat_result.data[0]
    
    if not stat_data:
        return False
    
    stat_id = stat_data["id"]
    
    # Mettre à jour selon le statut
    update_data = {}
    if status == "sent":
        update_data["sent_at"] = timestamp
    elif status == "delivered":
        update_data["delivered_at"] = timestamp
    elif status == "read":
        update_data["read_at"] = timestamp
    elif status == "failed":
        update_data["failed_at"] = timestamp
        if error_message:
            update_data["error_message"] = error_message
    
    if update_data:
        await update_recipient_stat(stat_id, update_data)
        # Mettre à jour les compteurs de la campagne
        campaign_id = stat_data.get("campaign_id")
        if campaign_id:
            await update_campaign_counters(campaign_id)
    
    return True


async def track_reply(conversation_id: str, message_id: str) -> bool:
    """
    Marque qu'un destinataire a répondu à une campagne
    """
    conv = None
    if get_pool():
        conv = await fetch_one(
            "SELECT client_number, account_id FROM conversations WHERE id = $1::uuid LIMIT 1",
            conversation_id,
        )
    else:
        conv_result = await supabase_execute(
            supabase.table("conversations")
            .select("client_number, account_id")
            .eq("id", conversation_id)
            .limit(1)
        )
        if conv_result.data and len(conv_result.data) > 0:
            conv = conv_result.data[0]
    if not conv:
        return False
    
    phone_number = conv["client_number"]
    account_id = conv["account_id"]
    
    stat = None
    if get_pool():
        stat = await fetch_one(
            """
            SELECT id, campaign_id, sent_at FROM broadcast_recipient_stats
            WHERE phone_number = $1 AND replied_at IS NULL AND sent_at IS NOT NULL
            ORDER BY sent_at DESC
            LIMIT 1
            """,
            phone_number,
        )
    else:
        stats_result = await supabase_execute(
            supabase.table("broadcast_recipient_stats")
            .select("id, campaign_id, sent_at")
            .eq("phone_number", phone_number)
            .is_("replied_at", "null")
            .not_.is_("sent_at", "null")
            .order("sent_at", desc=True)
            .limit(1)
        )
        if stats_result.data and len(stats_result.data) > 0:
            stat = stats_result.data[0]
    
    if not stat:
        return False
    
    # Mettre à jour la stat
    await update_recipient_stat(stat["id"], {
        "replied_at": datetime.now(timezone.utc).isoformat(),
        "reply_message_id": message_id,
    })
    
    # Mettre à jour le compteur de la campagne
    await update_campaign_counters(stat["campaign_id"])
    
    return True


async def update_campaign_counters(campaign_id: str) -> bool:
    """Met à jour les compteurs agrégés d'une campagne"""
    if get_pool():
        stats = await fetch_all(
            "SELECT sent_at, delivered_at, read_at, replied_at, failed_at FROM broadcast_recipient_stats WHERE campaign_id = $1::uuid",
            campaign_id,
        )
        if not stats:
            return False
        sent_count = sum(1 for s in stats if s.get("sent_at"))
        delivered_count = sum(1 for s in stats if s.get("delivered_at"))
        read_count = sum(1 for s in stats if s.get("read_at"))
        replied_count = sum(1 for s in stats if s.get("replied_at"))
        failed_count = sum(1 for s in stats if s.get("failed_at"))
        await pg_execute(
            """
            UPDATE broadcast_campaigns SET sent_count = $2, delivered_count = $3, read_count = $4, replied_count = $5, failed_count = $6
            WHERE id = $1::uuid
            """,
            campaign_id, sent_count, delivered_count, read_count, replied_count, failed_count,
        )
        return True
    stats_result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .select("sent_at, delivered_at, read_at, replied_at, failed_at")
        .eq("campaign_id", campaign_id)
    )
    if not stats_result.data:
        return False
    stats = stats_result.data
    sent_count = sum(1 for s in stats if s.get("sent_at"))
    delivered_count = sum(1 for s in stats if s.get("delivered_at"))
    read_count = sum(1 for s in stats if s.get("read_at"))
    replied_count = sum(1 for s in stats if s.get("replied_at"))
    failed_count = sum(1 for s in stats if s.get("failed_at"))
    await supabase_execute(
        supabase.table("broadcast_campaigns")
        .update({
            "sent_count": sent_count,
            "delivered_count": delivered_count,
            "read_count": read_count,
            "replied_count": replied_count,
            "failed_count": failed_count,
        })
        .eq("id", campaign_id)
    )
    return True


async def get_campaign_stats(campaign_id: str) -> Dict[str, Any]:
    """Récupère les statistiques complètes d'une campagne"""
    campaign = await get_broadcast_campaign(campaign_id)
    if not campaign:
        raise ValueError("Campaign not found")
    
    if get_pool():
        rows = await fetch_all(
            """
            SELECT s.*, r.display_name AS recipient_display_name, r.phone_number AS recipient_phone_number,
                   c.display_name AS contact_display_name, c.whatsapp_number AS contact_whatsapp_number
            FROM broadcast_recipient_stats s
            LEFT JOIN broadcast_group_recipients r ON r.id = s.recipient_id
            LEFT JOIN contacts c ON c.id = r.contact_id
            WHERE s.campaign_id = $1::uuid
            ORDER BY s.created_at ASC
            """,
            campaign_id,
        )
        recipients = []
        for r in rows:
            row = dict(r)
            row["broadcast_group_recipients"] = {
                "display_name": row.pop("recipient_display_name", None),
                "phone_number": row.pop("recipient_phone_number", None),
                "contacts": {
                    "display_name": row.pop("contact_display_name", None),
                    "whatsapp_number": row.pop("contact_whatsapp_number", None),
                } if row.get("contact_display_name") is not None or row.get("contact_whatsapp_number") is not None else None,
            }
            for k in list(row.keys()):
                if k.startswith("recipient_") or k.startswith("contact_"):
                    row.pop(k, None)
            recipients.append(row)
    else:
        stats_result = await supabase_execute(
            supabase.table("broadcast_recipient_stats")
            .select("*, broadcast_group_recipients(display_name, phone_number, contacts(display_name, whatsapp_number))")
            .eq("campaign_id", campaign_id)
            .order("created_at", desc=False)
        )
        recipients = stats_result.data or []
    
    # Calculer les taux
    total = campaign.get("total_recipients", 0)
    delivered = campaign.get("delivered_count", 0)
    read = campaign.get("read_count", 0)
    
    delivery_rate = (delivered / total * 100) if total > 0 else 0
    read_rate = (read / delivered * 100) if delivered > 0 else 0
    reply_rate = (campaign.get("replied_count", 0) / read * 100) if read > 0 else 0
    
    return {
        "campaign": campaign,
        "overview": {
            "total": total,
            "sent": campaign.get("sent_count", 0),
            "delivered": delivered,
            "read": read,
            "replied": campaign.get("replied_count", 0),
            "failed": campaign.get("failed_count", 0),
            "delivery_rate": round(delivery_rate, 2),
            "read_rate": round(read_rate, 2),
            "reply_rate": round(reply_rate, 2),
        },
        "recipients": recipients,
    }


async def get_campaign_heatmap(campaign_id: str) -> Dict[str, Any]:
    """Récupère les données pour la heat map (heures/jours)"""
    if get_pool():
        stats = await fetch_all(
            "SELECT read_at, replied_at FROM broadcast_recipient_stats WHERE campaign_id = $1::uuid",
            campaign_id,
        )
    else:
        stats_result = await supabase_execute(
            supabase.table("broadcast_recipient_stats")
            .select("read_at, replied_at")
            .eq("campaign_id", campaign_id)
        )
        stats = stats_result.data or []
    
    # Grouper par heure (0-23)
    read_by_hour = [0] * 24
    reply_by_hour = [0] * 24
    
    # Grouper par jour de la semaine (0=lundi, 6=dimanche)
    read_by_day = [0] * 7
    reply_by_day = [0] * 7
    
    for stat in stats:
        if stat.get("read_at"):
            from datetime import datetime as dt
            read_time = dt.fromisoformat(stat["read_at"].replace('Z', '+00:00'))
            hour = read_time.hour
            day = read_time.weekday()  # 0=lundi, 6=dimanche
            read_by_hour[hour] += 1
            read_by_day[day] += 1
        
        if stat.get("replied_at"):
            from datetime import datetime as dt
            reply_time = dt.fromisoformat(stat["replied_at"].replace('Z', '+00:00'))
            hour = reply_time.hour
            day = reply_time.weekday()
            reply_by_hour[hour] += 1
            reply_by_day[day] += 1
    
    # Formater pour le frontend
    read_by_hour_formatted = [{"hour": h, "count": read_by_hour[h]} for h in range(24)]
    reply_by_hour_formatted = [{"hour": h, "count": reply_by_hour[h]} for h in range(24)]
    
    day_names = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    read_by_day_formatted = [{"day": day_names[d], "count": read_by_day[d]} for d in range(7)]
    reply_by_day_formatted = [{"day": day_names[d], "count": reply_by_day[d]} for d in range(7)]
    
    return {
        "read_by_hour": read_by_hour_formatted,
        "reply_by_hour": reply_by_hour_formatted,
        "read_by_day": read_by_day_formatted,
        "reply_by_day": reply_by_day_formatted,
    }


async def get_campaign_timeline(campaign_id: str) -> List[Dict[str, Any]]:
    """Récupère la timeline pour les courbes temporelles"""
    campaign = await get_broadcast_campaign(campaign_id)
    if not campaign:
        return []
    
    sent_at = campaign.get("sent_at")
    if not sent_at:
        return []
    
    from datetime import datetime as dt
    start_time = dt.fromisoformat(sent_at.replace('Z', '+00:00'))
    
    if get_pool():
        stats = await fetch_all(
            "SELECT read_at, replied_at FROM broadcast_recipient_stats WHERE campaign_id = $1::uuid ORDER BY read_at ASC NULLS LAST",
            campaign_id,
        )
    else:
        stats_result = await supabase_execute(
            supabase.table("broadcast_recipient_stats")
            .select("read_at, replied_at")
            .eq("campaign_id", campaign_id)
            .order("read_at", desc=False)
        )
        stats = stats_result.data or []
    
    # Créer des points de timeline (cumulatif)
    timeline = []
    read_count = 0
    reply_count = 0
    
    # Grouper par heure
    from collections import defaultdict
    reads_by_hour = defaultdict(int)
    replies_by_hour = defaultdict(int)
    
    for stat in stats:
        if stat.get("read_at"):
            read_time = dt.fromisoformat(stat["read_at"].replace('Z', '+00:00'))
            hour_key = read_time.strftime("%Y-%m-%d %H:00:00")
            reads_by_hour[hour_key] += 1
        
        if stat.get("replied_at"):
            reply_time = dt.fromisoformat(stat["replied_at"].replace('Z', '+00:00'))
            hour_key = reply_time.strftime("%Y-%m-%d %H:00:00")
            replies_by_hour[hour_key] += 1
    
    # Créer la timeline
    all_hours = sorted(set(list(reads_by_hour.keys()) + list(replies_by_hour.keys())))
    
    cumulative_reads = 0
    cumulative_replies = 0
    
    for hour in all_hours:
        cumulative_reads += reads_by_hour.get(hour, 0)
        cumulative_replies += replies_by_hour.get(hour, 0)
        
        timeline.append({
            "timestamp": hour,
            "reads": cumulative_reads,
            "replies": cumulative_replies,
        })
    
    return timeline

