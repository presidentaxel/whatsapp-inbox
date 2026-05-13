"""
Imports et helpers partagés par les sous-routers `messages/`.

But: éviter de redéclarer 30+ imports dans chaque sous-fichier. Tout ce qui
est réutilisé par plus d'un sous-router vit ici. Chaque sous-fichier ne
réimporte que ce dont il a besoin via `from ._common import ...`.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.auth import get_current_user
from app.core.cache import get_cache
from app.core.db import supabase, supabase_execute, SUPABASE_IN_CLAUSE_CHUNK_SIZE
from app.core.permissions import CurrentUser, PermissionCodes
from app.core.pg import fetch_all, get_pool
from app.services import whatsapp_api_service
from app.services.account_service import get_account_by_id
from app.services.audio_transcription_service import transcribe_inbound_audio_on_demand_for_message
from app.services.conversation_service import get_conversation_by_id
from app.services.media_background_service import process_unsaved_media_for_conversation
from app.services.message_service import (
    fetch_message_media_content,
    get_message_by_id,
    get_messages,
    is_within_free_window,
    calculate_message_price,
    send_message,
    send_free_message,
    send_media_message_with_storage,
    send_interactive_message_with_storage,
    update_message_content,
    delete_message_scope,
)
from app.services.reactions_service import (
    add_reaction,
    remove_reaction,
    send_reaction_to_whatsapp,
)
from app.services.template_deduplication import find_or_create_template
from app.services.whatsapp_api_service import check_phone_number_has_whatsapp


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# S'assurer que les logs sont visibles (préservé du module historique)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = True


__all__ = [
    "APIRouter",
    "Depends",
    "HTTPException",
    "Query",
    "StreamingResponse",
    "datetime",
    "timezone",
    "json",
    "logger",
    "get_current_user",
    "get_cache",
    "supabase",
    "supabase_execute",
    "SUPABASE_IN_CLAUSE_CHUNK_SIZE",
    "CurrentUser",
    "PermissionCodes",
    "fetch_all",
    "get_pool",
    "whatsapp_api_service",
    "get_account_by_id",
    "transcribe_inbound_audio_on_demand_for_message",
    "get_conversation_by_id",
    "process_unsaved_media_for_conversation",
    "add_reaction",
    "fetch_message_media_content",
    "get_message_by_id",
    "get_messages",
    "is_within_free_window",
    "calculate_message_price",
    "remove_reaction",
    "send_message",
    "send_free_message",
    "send_media_message_with_storage",
    "send_interactive_message_with_storage",
    "send_reaction_to_whatsapp",
    "update_message_content",
    "delete_message_scope",
    "find_or_create_template",
    "check_phone_number_has_whatsapp",
]
