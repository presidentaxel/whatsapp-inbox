"""
Service complet pour l'API WhatsApp Business Cloud API
Implémente tous les endpoints de l'API Meta WhatsApp
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.core.http_client import get_http_client, get_http_client_for_media
from app.core.retry import retry_on_network_error

logger = logging.getLogger(__name__)

# Version de l'API WhatsApp
WHATSAPP_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"


class WhatsAppAPIError(Exception):
    """Exception personnalisée pour les erreurs de l'API WhatsApp"""
    def __init__(self, message: str, error_code: Optional[str] = None, error_subcode: Optional[str] = None, is_token_expired: bool = False):
        super().__init__(message)
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.is_token_expired = is_token_expired


def _meta_error_codes(exc: WhatsAppAPIError) -> set:
    """Normalise code / error_subcode Meta (int ou str dans le JSON Graph)."""
    out: set = set()
    for c in (exc.error_code, exc.error_subcode):
        if c is None:
            continue
        out.add(c)
        try:
            out.add(int(c))
        except (TypeError, ValueError):
            pass
    return out


def http_status_and_detail_for_whatsapp_api_error(exc: WhatsAppAPIError) -> tuple[int, str]:
    """
    Mappe les erreurs WhatsApp Cloud API vers un statut HTTP et un message API.
    (#133010) Account not registered : ligne ou phone_number_id non enregistré / invalide côté Meta.
    """
    codes = _meta_error_codes(exc)
    msg_lower = str(exc).lower()
    # Meta: OAuthException (#133010) Account not registered
    if 133010 in codes or "133010" in msg_lower or "account not registered" in msg_lower:
        return (
            422,
            "whatsapp_meta_account_not_registered — Cette ligne WhatsApp n’est pas enregistrée sur Meta "
            "(Cloud API), ou le phone_number_id / le token ne correspond plus à un actif valide. "
            "Vérifie la ligne dans Meta Business Suite et les identifiants du compte dans l’app.",
        )
    if exc.is_token_expired:
        return 401, str(exc)
    return 502, str(exc)


def parse_whatsapp_error(response: httpx.Response) -> WhatsAppAPIError:
    """
    Parse une réponse d'erreur de l'API WhatsApp et retourne une exception appropriée
    """
    error_text = response.text
    error_json = None
    
    try:
        error_json = response.json()
    except:
        pass
    
    # Détecter les erreurs de token expiré
    error_message = error_text.lower()
    is_token_expired = False
    error_code = None
    error_subcode = None
    
    if error_json:
        error_obj = error_json.get("error", {})
        error_code = error_obj.get("code")
        error_subcode = error_obj.get("error_subcode")
        error_message = error_obj.get("message", error_text)
        
        # Détecter les codes d'erreur liés aux tokens expirés
        if error_code == 190 or error_subcode == 463 or "expired" in error_message.lower() or "session has expired" in error_message.lower():
            is_token_expired = True
    
    if is_token_expired:
        message = (
            "Le token d'accès WhatsApp a expiré. "
            "Veuillez le renouveler en exécutant le script de rafraîchissement:\n"
            "  python backend/scripts/refresh_whatsapp_token.py\n\n"
            f"Détails de l'erreur: {error_message}"
        )
        return WhatsAppAPIError(message, error_code, error_subcode, is_token_expired=True)
    
    # Autres erreurs
    if error_json:
        error_obj = error_json.get("error", {})
        message = error_obj.get("message", error_text)
        error_type = error_obj.get("type", "unknown")
        return WhatsAppAPIError(f"{error_type}: {message}", error_code, error_subcode)
    
    return WhatsAppAPIError(f"Erreur WhatsApp API: {error_text}", error_code, error_subcode)


# ============================================================================
# 1. MESSAGES - Envoyer tous types de messages
# ============================================================================

@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def send_text_message(
    phone_number_id: str,
    access_token: str,
    to: str,
    text: str,
    preview_url: bool = False
) -> Dict[str, Any]:
    """
    Envoie un message texte
    POST /{PHONE_NUMBER_ID}/messages
    """
    client = await get_http_client()
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "body": text,
            "preview_url": preview_url
        }
    }
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload
    )
    response.raise_for_status()
    return response.json()


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def send_media_message(
    phone_number_id: str,
    access_token: str,
    to: str,
    media_type: str,  # "image", "audio", "video", "document"
    media_id: Optional[str] = None,
    media_link: Optional[str] = None,
    caption: Optional[str] = None,
    filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envoie un message avec média (image, audio, vidéo, document)
    POST /{PHONE_NUMBER_ID}/messages
    """
    client = await get_http_client()
    
    media_object: Dict[str, Any] = {}
    if media_id:
        media_object["id"] = media_id
    elif media_link:
        media_object["link"] = media_link
    else:
        raise ValueError("media_id or media_link required")
    
    if caption:
        media_object["caption"] = caption
    if filename and media_type == "document":
        media_object["filename"] = filename
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": media_type,
        media_type: media_object
    }
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload
    )
    response.raise_for_status()
    return response.json()


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def send_template_message(
    phone_number_id: str,
    access_token: str,
    to: str,
    template_name: str,
    language_code: str = "en",
    components: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Envoie un message template
    POST /{PHONE_NUMBER_ID}/messages
    """
    client = await get_http_client()
    
    template_payload = {
        "name": template_name,
        "language": {"code": language_code}
    }
    
    # Ne pas inclure "components" du tout si None ou vide, plutôt que d'envoyer null
    # Cela peut faire la différence pour WhatsApp dans certains cas
    if components is not None and len(components) > 0:
        template_payload["components"] = components
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template_payload
    }
    
    # Log pour déboguer
    import logging
    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info(f"📤 [WHATSAPP API] ========== ENVOI TEMPLATE MESSAGE ==========")
    logger.info(f"📤 [WHATSAPP API] template_name: {template_name}")
    logger.info(f"📤 [WHATSAPP API] language_code: {language_code}")
    logger.info(f"📤 [WHATSAPP API] to: {to}")
    logger.info(f"📤 [WHATSAPP API] components: {components}")
    logger.info(f"📤 [WHATSAPP API] components type: {type(components)}")
    if components:
        logger.info(f"📤 [WHATSAPP API] Nombre de components: {len(components)}")
        logger.info(f"📤 [WHATSAPP API] Détail des components:")
        for idx, comp in enumerate(components):
            comp_type = comp.get("type", "UNKNOWN")
            logger.info(f"📤 [WHATSAPP API]   Component {idx + 1}: type={comp_type}")
            if comp_type == "HEADER":
                logger.info(f"📤 [WHATSAPP API]     - format: {comp.get('format')}")
                logger.info(f"📤 [WHATSAPP API]     - text: {repr(comp.get('text'))}")
            elif comp_type == "BODY":
                logger.info(f"📤 [WHATSAPP API]     - text: {repr(comp.get('text')[:100] if comp.get('text') else None)}")
            elif comp_type == "FOOTER":
                logger.info(f"📤 [WHATSAPP API]     - text: {repr(comp.get('text'))}")
            elif comp_type == "BUTTONS":
                buttons_list = comp.get("buttons", [])
                logger.info(f"📤 [WHATSAPP API]     - nombre de boutons: {len(buttons_list)}")
                for btn_idx, btn in enumerate(buttons_list):
                    logger.info(f"📤 [WHATSAPP API]       Bouton {btn_idx + 1}: type={btn.get('type')}, text={repr(btn.get('text'))}")
            logger.info(f"📤 [WHATSAPP API]     Component {idx + 1} complet: {json.dumps(comp, indent=2, ensure_ascii=False)}")
    else:
        logger.warning(f"⚠️ [WHATSAPP API] AUCUN COMPONENT FOURNI!")
    logger.info(f"📤 [WHATSAPP API] Payload complet envoyé à Meta:")
    logger.info(f"📤 [WHATSAPP API] {json.dumps(payload, indent=2, ensure_ascii=False)}")
    logger.info(f"📤 [WHATSAPP API] =============================================")
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload
    )
    
    # Log de la réponse en cas d'erreur
    if response.status_code != 200:
        error_detail = response.text
        logger.error(f"❌ [WHATSAPP API] Error {response.status_code}: {error_detail}")
        try:
            error_json = response.json()
            logger.error(f"❌ [WHATSAPP API] Error JSON: {json.dumps(error_json, indent=2, ensure_ascii=False)}")
        except:
            pass
    else:
        logger.info(f"✅ [WHATSAPP API] Success: {response.text[:500]}")
    
    response.raise_for_status()
    return response.json()


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def send_interactive_buttons(
    phone_number_id: str,
    access_token: str,
    to: str,
    body_text: str,
    buttons: List[Dict[str, str]],  # [{"id": "btn_1", "title": "Button 1"}, ...]
    header_text: Optional[str] = None,
    footer_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envoie un message interactif avec boutons
    POST /{PHONE_NUMBER_ID}/messages
    """
    client = await get_http_client()
    
    interactive_payload: Dict[str, Any] = {
        "type": "button",
        "body": {"text": body_text},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {"id": btn["id"], "title": btn["title"]}
                }
                for btn in buttons[:3]  # Max 3 boutons
            ]
        }
    }
    
    if header_text:
        interactive_payload["header"] = {"type": "text", "text": header_text}
    if footer_text:
        interactive_payload["footer"] = {"text": footer_text}
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": interactive_payload
    }
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload
    )
    response.raise_for_status()
    return response.json()


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def send_interactive_list(
    phone_number_id: str,
    access_token: str,
    to: str,
    body_text: str,
    button_text: str,
    sections: List[Dict[str, Any]],  # [{"title": "Section 1", "rows": [{"id": "1", "title": "Row 1"}]}]
    header_text: Optional[str] = None,
    footer_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envoie un message interactif avec liste déroulante
    POST /{PHONE_NUMBER_ID}/messages
    """
    client = await get_http_client()
    
    interactive_payload: Dict[str, Any] = {
        "type": "list",
        "body": {"text": body_text},
        "action": {
            "button": button_text,
            "sections": sections
        }
    }
    
    if header_text:
        interactive_payload["header"] = {"type": "text", "text": header_text}
    if footer_text:
        interactive_payload["footer"] = {"text": footer_text}
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": interactive_payload
    }
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# 2. MÉDIAS - Upload / Download / Delete
# ============================================================================

@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def upload_media(
    phone_number_id: str,
    access_token: str,
    file_path: str,
    mime_type: str
) -> Dict[str, Any]:
    """
    Upload un fichier média
    POST /{PHONE_NUMBER_ID}/media
    """
    client = await get_http_client_for_media()
    
    # Convertir le mime_type en type WhatsApp (image, video, audio, document)
    whatsapp_type = _mime_type_to_whatsapp_type(mime_type)
    
    with open(file_path, "rb") as f:
        files = {
            "file": (file_path.split("/")[-1], f, mime_type),
            "messaging_product": (None, "whatsapp"),
            "type": (None, whatsapp_type)  # Type WhatsApp, pas le mime_type
        }
        
        response = await client.post(
            f"{GRAPH_API_BASE}/{phone_number_id}/media",
            headers={"Authorization": f"Bearer {access_token}"},
            files=files
        )
    
    response.raise_for_status()
    return response.json()


def _mime_type_to_whatsapp_type(mime_type: str) -> str:
    """
    Convertit un mime_type en type WhatsApp (image, video, audio, document)
    """
    if not mime_type:
        return "document"
    
    mime_lower = mime_type.lower()
    
    if mime_lower.startswith("image/"):
        return "image"
    elif mime_lower.startswith("video/"):
        return "video"
    elif mime_lower.startswith("audio/"):
        return "audio"
    else:
        return "document"


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def upload_media_from_bytes(
    phone_number_id: str,
    access_token: str,
    file_content: bytes,
    filename: str,
    mime_type: str
) -> Dict[str, Any]:
    """
    Upload un fichier média depuis bytes
    POST /{PHONE_NUMBER_ID}/media
    
    Args:
        phone_number_id: ID du numéro de téléphone WhatsApp
        access_token: Token d'accès
        file_content: Contenu du fichier en bytes
        filename: Nom du fichier
        mime_type: Type MIME du fichier (ex: "image/jpeg", "video/mp4")
    """
    client = await get_http_client_for_media()
    
    # Convertir le mime_type en type WhatsApp (image, video, audio, document)
    whatsapp_type = _mime_type_to_whatsapp_type(mime_type)
    
    files = {
        "file": (filename, file_content, mime_type),
        "messaging_product": (None, "whatsapp"),
        "type": (None, whatsapp_type)  # Type WhatsApp, pas le mime_type
    }
    
    logger.info(f"📤 Uploading media: filename={filename}, mime_type={mime_type}, whatsapp_type={whatsapp_type}, size={len(file_content)} bytes")
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/media",
        headers={"Authorization": f"Bearer {access_token}"},
        files=files
    )
    
    response.raise_for_status()
    return response.json()


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def get_media_url(media_id: str, access_token: str) -> Dict[str, Any]:
    """
    Récupère l'URL de téléchargement d'un média
    GET /{MEDIA_ID}
    """
    client = await get_http_client()
    
    response = await client.get(
        f"{GRAPH_API_BASE}/{media_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    response.raise_for_status()
    return response.json()


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def download_media(media_id: str, access_token: str) -> bytes:
    """
    Télécharge le contenu d'un média
    GET /{MEDIA_ID} puis GET de l'URL retournée
    """
    # Récupérer l'URL
    media_info = await get_media_url(media_id, access_token)
    download_url = media_info.get("url")
    
    if not download_url:
        raise ValueError("No download URL in media response")
    
    # Télécharger le contenu
    client = await get_http_client_for_media()
    response = await client.get(
        download_url,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    response.raise_for_status()
    return response.content


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def delete_media(media_id: str, access_token: str) -> Dict[str, Any]:
    """
    Supprime un média du stockage Meta
    DELETE /{MEDIA_ID}
    """
    client = await get_http_client()
    
    response = await client.delete(
        f"{GRAPH_API_BASE}/{media_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# 3. NUMÉROS DE TÉLÉPHONE (Phone Numbers)
# ============================================================================

async def list_phone_numbers(waba_id: str, access_token: str) -> Dict[str, Any]:
    """
    Liste les numéros de téléphone d'un WABA
    GET /{WABA-ID}/phone_numbers
    """
    client = await get_http_client()
    
    response = await client.get(
        f"{GRAPH_API_BASE}/{waba_id}/phone_numbers",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    response.raise_for_status()
    return response.json()


async def get_phone_number_details(phone_number_id: str, access_token: str) -> Dict[str, Any]:
    """
    Récupère les détails d'un numéro
    GET /{PHONE_NUMBER_ID}
    """
    client = await get_http_client()
    
    response = await client.get(
        f"{GRAPH_API_BASE}/{phone_number_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"fields": "display_phone_number,verified_name,quality_rating,code_verification_status"}
    )
    response.raise_for_status()
    return response.json()


async def register_phone_number(
    phone_number_id: str,
    access_token: str,
    pin: str
) -> Dict[str, Any]:
    """
    Enregistre un numéro pour l'API Cloud + définit le PIN 2FA
    POST /{PHONE_NUMBER_ID}/register
    """
    client = await get_http_client()
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/register",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "messaging_product": "whatsapp",
            "pin": pin
        }
    )
    response.raise_for_status()
    return response.json()


async def deregister_phone_number(phone_number_id: str, access_token: str) -> Dict[str, Any]:
    """
    Désenregistre un numéro
    POST /{PHONE_NUMBER_ID}/deregister
    """
    client = await get_http_client()
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/deregister",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"messaging_product": "whatsapp"}
    )
    response.raise_for_status()
    return response.json()


async def request_verification_code(
    phone_number_id: str,
    access_token: str,
    code_method: str = "SMS",  # "SMS" ou "VOICE"
    language: str = "en_US"
) -> Dict[str, Any]:
    """
    Demande l'envoi du code de vérification
    POST /{PHONE_NUMBER_ID}/request_code
    """
    client = await get_http_client()
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/request_code",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "code_method": code_method,
            "language": language
        }
    )
    response.raise_for_status()
    return response.json()


async def verify_code(
    phone_number_id: str,
    access_token: str,
    code: str
) -> Dict[str, Any]:
    """
    Valide le code de vérification reçu
    POST /{PHONE_NUMBER_ID}/verify_code
    """
    client = await get_http_client()
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/verify_code",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"code": code}
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# 4. PROFIL BUSINESS WHATSAPP
# ============================================================================

@retry_on_network_error(max_attempts=2, min_wait=0.5, max_wait=2.0)
async def get_business_profile(phone_number_id: str, access_token: str) -> Dict[str, Any]:
    """
    Récupère le profil business WhatsApp
    GET /{PHONE_NUMBER_ID}/whatsapp_business_profile
    
    Optimisé avec:
    - Cache (TTL 5 minutes) car le profil change rarement
    - Retry automatique en cas d'erreur réseau
    - Timeout optimisé pour réduire la latence
    """
    from app.core.cache import get_cached_or_fetch
    
    cache_key = f"whatsapp_business_profile:{phone_number_id}"
    
    async def _fetch_profile():
        client = await get_http_client()
        
        # Timeout optimisé pour cette requête spécifique
        timeout = httpx.Timeout(connect=1.5, read=4.0, write=2.0, pool=1.5)
        
        response = await client.get(
            f"{GRAPH_API_BASE}/{phone_number_id}/whatsapp_business_profile",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate"
            },
            params={"fields": "about,address,description,email,profile_picture_url,websites,vertical"},
            timeout=timeout
        )
        response.raise_for_status()
        return response.json()
    
    # Cache avec TTL de 5 minutes (le profil change rarement)
    return await get_cached_or_fetch(
        cache_key,
        _fetch_profile,
        ttl_seconds=300  # 5 minutes
    )


async def update_business_profile(
    phone_number_id: str,
    access_token: str,
    profile_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Met à jour le profil business WhatsApp
    POST /{PHONE_NUMBER_ID}/whatsapp_business_profile
    
    profile_data peut contenir:
    - about: str (description courte, max 139 caractères)
    - address: str
    - description: str (description longue, max 512 caractères)
    - email: str
    - websites: List[str]
    - vertical: str (secteur d'activité)
    - profile_picture_handle: str (media_id d'une image uploadée)
    """
    client = await get_http_client()
    
    # Optimisation : construire le payload minimal
    payload = {
        "messaging_product": "whatsapp",
        **profile_data
    }
    
    # Headers optimisés pour la performance
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }
    
    # Appel avec timeout spécifique pour cette opération
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/whatsapp_business_profile",
        headers=headers,
        json=payload,
        timeout=httpx.Timeout(connect=2.0, read=6.0, write=3.0, pool=2.0)  # Timeout réduit
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# 5. TEMPLATES DE MESSAGES
# ============================================================================

async def get_message_template_by_id(
    template_id: str,
    access_token: str
) -> Optional[Dict[str, Any]]:
    """
    Récupère un template spécifique par son ID
    GET /{template_id}?fields=name,status,category,language,components
    
    Retourne None si le template n'existe pas ou n'est pas encore synchronisé.
    """
    client = await get_http_client()
    
    try:
        response = await client.get(
            f"{GRAPH_API_BASE}/{template_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "name,status,category,language,components"}
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.debug(f"Template {template_id} not found (404) - may not be synchronized yet")
            return None
        if e.response.status_code == 400:
            # Meta peut retourner 400 (ex: ID invalide ou token WABA vs User) -> fallback sur list par nom
            logger.debug(
                "Template %s Bad Request (400) - falling back to list by name. Body: %s",
                template_id,
                e.response.text[:200] if e.response.text else "",
            )
            return None
        raise


_templates_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_TEMPLATES_CACHE_TTL = 300.0


async def list_message_templates(
    waba_id: str,
    access_token: str,
    limit: int = 100,
    after: Optional[str] = None
) -> Dict[str, Any]:
    """
    Liste les templates de messages
    GET /{WABA-ID}/message_templates
    Cached for 5min when fetching the first page (no cursor).
    """
    if after is None:
        cached = _templates_cache.get(waba_id)
        if cached:
            expires_at, data = cached
            if time.monotonic() < expires_at:
                return data

    client = await get_http_client()
    
    params = {
        "limit": limit,
        "fields": "name,status,category,language,components"
    }
    if after:
        params["after"] = after
    
    response = await client.get(
        f"{GRAPH_API_BASE}/{waba_id}/message_templates",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params
    )
    response.raise_for_status()
    result = response.json()

    if after is None:
        _templates_cache[waba_id] = (time.monotonic() + _TEMPLATES_CACHE_TTL, result)

    return result


def invalidate_templates_cache(waba_id: str | None = None):
    if waba_id:
        _templates_cache.pop(waba_id, None)
    else:
        _templates_cache.clear()


_named_body_params_cache: Dict[Tuple[str, str, str], Tuple[float, Optional[List[str]]]] = {}
_NAMED_BODY_PARAM_CACHE_TTL = 300.0


async def get_template_named_body_parameter_names(
    waba_id: str,
    access_token: str,
    template_name: str,
    language_code: str,
) -> Optional[List[str]]:
    """
    Si le BODY du template utilise des variables nommées (example.body_text_named_params),
    retourne les param_name dans l'ordre attendu par Meta.
    Sinon None (variables positionnelles {{1}}, {{2}} - pas de parameter_name sur l'envoi).
    """
    if not waba_id or not access_token or not (template_name or "").strip():
        return None
    lang_key = (language_code or "en").strip().lower()
    cache_key = (waba_id, template_name.strip(), lang_key)
    now_m = time.monotonic()
    cached = _named_body_params_cache.get(cache_key)
    if cached and now_m < cached[0]:
        return cached[1]

    result: Optional[List[str]] = None
    try:
        all_rows: List[Dict[str, Any]] = []
        cursor_after: Optional[str] = None
        while True:
            batch = await list_message_templates(
                waba_id, access_token, limit=100, after=cursor_after
            )
            chunk = batch.get("data") or []
            if not chunk:
                break
            all_rows.extend(chunk)
            cursor_after = (batch.get("paging") or {}).get("cursors", {}).get("after")
            if not cursor_after:
                break

        tpl = next(
            (
                t
                for t in all_rows
                if t.get("name") == template_name and t.get("language") == language_code
            ),
            None,
        )
        if not tpl:
            tpl = next((t for t in all_rows if t.get("name") == template_name), None)
        if not tpl:
            _named_body_params_cache[cache_key] = (
                now_m + _NAMED_BODY_PARAM_CACHE_TTL,
                None,
            )
            return None

        body_comp = next(
            (c for c in (tpl.get("components") or []) if c.get("type") == "BODY"),
            None,
        )
        if not body_comp:
            _named_body_params_cache[cache_key] = (
                now_m + _NAMED_BODY_PARAM_CACHE_TTL,
                None,
            )
            return None
        named = (body_comp.get("example") or {}).get("body_text_named_params") or []
        if not named:
            _named_body_params_cache[cache_key] = (
                now_m + _NAMED_BODY_PARAM_CACHE_TTL,
                None,
            )
            return None
        names: List[str] = []
        for p in named:
            if not isinstance(p, dict):
                continue
            pn = (p.get("param_name") or "").strip()
            if pn:
                names.append(pn)
        result = names if names else None
    except Exception as exc:
        logger.warning("get_template_named_body_parameter_names: %s", exc, exc_info=True)
        result = None

    _named_body_params_cache[cache_key] = (
        time.monotonic() + _NAMED_BODY_PARAM_CACHE_TTL,
        result,
    )
    return result


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=6.0)
async def create_message_template(
    waba_id: str,
    access_token: str,
    name: str,
    category: str,  # "AUTHENTICATION", "MARKETING", "UTILITY"
    language: str,
    components: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Crée un nouveau template (soumis à review Meta)
    POST /{WABA-ID}/message_templates
    
    Exemple de components:
    [
        {
            "type": "HEADER",
            "format": "TEXT",
            "text": "Bonjour {{1}}"
        },
        {
            "type": "BODY",
            "text": "Votre code est {{1}}"
        },
        {
            "type": "FOOTER",
            "text": "Ne partagez pas ce code"
        },
        {
            "type": "BUTTONS",
            "buttons": [
                {"type": "URL", "text": "Visiter", "url": "https://example.com"}
            ]
        }
    ]
    """
    client = await get_http_client()
    
    payload = {
        "name": name,
        "category": category,
        "language": language,
        "components": components
    }
    
    logger.info("=" * 80)
    logger.info(f"📤 [WHATSAPP API] ========== CRÉATION TEMPLATE META ==========")
    logger.info(f"📤 [WHATSAPP API] template_name: {name}")
    logger.info(f"📤 [WHATSAPP API] category: {category}")
    logger.info(f"📤 [WHATSAPP API] language: {language}")
    logger.info(f"📤 [WHATSAPP API] components: {components}")
    logger.info(f"📤 [WHATSAPP API] components type: {type(components)}")
    if components:
        logger.info(f"📤 [WHATSAPP API] Nombre de components: {len(components)}")
        logger.info(f"📤 [WHATSAPP API] Détail des components:")
        for idx, comp in enumerate(components):
            comp_type = comp.get("type", "UNKNOWN")
            logger.info(f"📤 [WHATSAPP API]   Component {idx + 1}: type={comp_type}")
            if comp_type == "HEADER":
                logger.info(f"📤 [WHATSAPP API]     - format: {comp.get('format')}")
                logger.info(f"📤 [WHATSAPP API]     - text: {repr(comp.get('text'))}")
            elif comp_type == "BODY":
                logger.info(f"📤 [WHATSAPP API]     - text: {repr(comp.get('text')[:100] if comp.get('text') else None)}")
            elif comp_type == "FOOTER":
                logger.info(f"📤 [WHATSAPP API]     - text: {repr(comp.get('text'))}")
            elif comp_type == "BUTTONS":
                buttons_list = comp.get("buttons", [])
                logger.info(f"📤 [WHATSAPP API]     - nombre de boutons: {len(buttons_list)}")
                for btn_idx, btn in enumerate(buttons_list):
                    logger.info(f"📤 [WHATSAPP API]       Bouton {btn_idx + 1}: type={btn.get('type')}, text={repr(btn.get('text'))}")
            logger.info(f"📤 [WHATSAPP API]     Component {idx + 1} complet: {json.dumps(comp, indent=2, ensure_ascii=False)}")
    else:
        logger.warning(f"⚠️ [WHATSAPP API] AUCUN COMPONENT FOURNI!")
    logger.info(f"📤 [WHATSAPP API] Payload complet envoyé à Meta:")
    logger.info(f"📤 [WHATSAPP API] {json.dumps(payload, indent=2, ensure_ascii=False)}")
    logger.info(f"📤 [WHATSAPP API] =============================================")
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{waba_id}/message_templates",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload,
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=20.0, pool=5.0),
    )
    
    # Capturer les détails de l'erreur avant de lever l'exception
    if response.status_code != 200:
        error_detail = response.text
        try:
            error_json = response.json()
            error_detail = error_json
        except:
            pass
        logger.error(f"❌ [WHATSAPP API] Erreur Meta: status={response.status_code}, detail={error_detail}")
        logger.error(f"   Payload envoyé: {payload}")
        
        # Parser l'erreur pour détecter les tokens expirés
        raise parse_whatsapp_error(response)
    
    response.raise_for_status()
    result = response.json()
    # Évite de garder un cache stale juste après création.
    invalidate_templates_cache(waba_id)
    return result


async def delete_message_template(
    waba_id: str,
    access_token: str,
    name: str,
    hsm_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Supprime un template
    DELETE /{WABA-ID}/message_templates
    """
    client = await get_http_client()
    
    params = {"name": name}
    if hsm_id:
        params["hsm_id"] = hsm_id
    
    response = await client.delete(
        f"{GRAPH_API_BASE}/{waba_id}/message_templates",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# 6. WEBHOOKS - Subscription
# ============================================================================

async def subscribe_to_webhooks(
    waba_id: str,
    access_token: str
) -> Dict[str, Any]:
    """
    Abonne l'app aux événements WhatsApp
    POST /{WABA-ID}/subscribed_apps
    """
    client = await get_http_client()
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{waba_id}/subscribed_apps",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    response.raise_for_status()
    return response.json()


async def unsubscribe_from_webhooks(
    waba_id: str,
    access_token: str
) -> Dict[str, Any]:
    """
    Se désabonne des événements WhatsApp
    DELETE /{WABA-ID}/subscribed_apps
    """
    client = await get_http_client()
    
    response = await client.delete(
        f"{GRAPH_API_BASE}/{waba_id}/subscribed_apps",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    response.raise_for_status()
    return response.json()


async def get_subscribed_apps(
    waba_id: str,
    access_token: str
) -> Dict[str, Any]:
    """
    Récupère la liste des apps abonnées
    GET /{WABA-ID}/subscribed_apps
    """
    client = await get_http_client()
    
    response = await client.get(
        f"{GRAPH_API_BASE}/{waba_id}/subscribed_apps",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# 7. CONTACTS - Récupération des images de profil
# ============================================================================

@retry_on_network_error(max_attempts=2, min_wait=1.0, max_wait=3.0)
async def check_phone_number_has_whatsapp(
    phone_number_id: str,
    access_token: str,
    phone_number: str,
) -> Dict[str, Any]:
    """
    Vérifie si un numéro de téléphone a un compte WhatsApp actif.
    
    Cette fonction utilise l'API WhatsApp Contacts pour vérifier si un numéro
    est inscrit sur WhatsApp. Si l'API retourne des données, le numéro a WhatsApp.
    Si elle retourne une erreur spécifique, le numéro n'a probablement pas WhatsApp.
    
    Args:
        phone_number_id: ID du numéro de téléphone WhatsApp Business
        access_token: Token d'accès Graph API
        phone_number: Numéro de téléphone à vérifier (format international avec ou sans +)
    
    Returns:
        Dict avec:
        - has_whatsapp: bool (True si le numéro a WhatsApp, False sinon)
        - name: Optional[str] (nom du contact si disponible)
        - profile_picture_url: Optional[str] (URL de la photo de profil si disponible)
        - error: Optional[str] (message d'erreur si la vérification a échoué)
    """
    try:
        client = await get_http_client()
        
        # Nettoyer le numéro de téléphone (format international sans +)
        clean_phone = phone_number.replace("+", "").replace(" ", "").replace("-", "")
        
        try:
            response = await client.get(
                f"{GRAPH_API_BASE}/{phone_number_id}/contacts",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "phone_numbers": clean_phone,
                    "fields": "profile_picture_url,name"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("data") and len(data["data"]) > 0:
                    contact_data = data["data"][0]
                    # Si on a des données, le numéro a WhatsApp
                    logger.info(f"✅ Numéro {clean_phone} a WhatsApp")
                    return {
                        "has_whatsapp": True,
                        "name": contact_data.get("name"),
                        "profile_picture_url": contact_data.get("profile_picture_url"),
                        "phone_number": clean_phone
                    }
                else:
                    # Pas de données = le numéro n'a probablement pas WhatsApp
                    logger.warning(f"⚠️ Numéro {clean_phone} n'a pas de compte WhatsApp (pas de données retournées)")
                    return {
                        "has_whatsapp": False,
                        "name": None,
                        "profile_picture_url": None,
                        "phone_number": clean_phone,
                        "error": "Ce numéro ne semble pas avoir de compte WhatsApp"
                    }
            else:
                # Erreur HTTP = probablement pas WhatsApp
                error_text = response.text
                logger.warning(f"⚠️ Erreur lors de la vérification du numéro {clean_phone}: {response.status_code} - {error_text}")
                return {
                    "has_whatsapp": False,
                    "name": None,
                    "profile_picture_url": None,
                    "phone_number": clean_phone,
                    "error": f"Impossible de vérifier si ce numéro a WhatsApp (code {response.status_code})"
                }
        except httpx.HTTPStatusError as e:
            # Erreur HTTP spécifique
            if e.response.status_code == 400:
                # Erreur 400 = probablement numéro invalide ou pas WhatsApp
                logger.warning(f"⚠️ Numéro {clean_phone} invalide ou n'a pas WhatsApp (400)")
                return {
                    "has_whatsapp": False,
                    "name": None,
                    "profile_picture_url": None,
                    "phone_number": clean_phone,
                    "error": "Ce numéro ne semble pas avoir de compte WhatsApp"
                }
            else:
                logger.error(f"❌ Erreur HTTP {e.response.status_code} lors de la vérification: {e.response.text}")
                return {
                    "has_whatsapp": None,  # Inconnu
                    "name": None,
                    "profile_picture_url": None,
                    "phone_number": clean_phone,
                    "error": f"Erreur lors de la vérification (code {e.response.status_code})"
                }
        except Exception as e:
            logger.error(f"❌ Erreur lors de la vérification du numéro {clean_phone}: {e}")
            return {
                "has_whatsapp": None,  # Inconnu
                "name": None,
                "profile_picture_url": None,
                "phone_number": clean_phone,
                "error": f"Erreur lors de la vérification: {str(e)}"
            }
            
    except Exception as e:
        logger.error(f"❌ Erreur critique lors de la vérification du numéro {phone_number}: {e}", exc_info=True)
        return {
            "has_whatsapp": None,  # Inconnu
            "name": None,
            "profile_picture_url": None,
            "phone_number": phone_number.replace("+", "").replace(" ", "").replace("-", ""),
            "error": f"Erreur lors de la vérification: {str(e)}"
        }


@retry_on_network_error(max_attempts=2, min_wait=1.0, max_wait=3.0)
async def get_contact_info(
    phone_number_id: str,
    access_token: str,
    phone_number: str,
) -> Dict[str, Any]:
    """
    Récupère les informations complètes d'un contact WhatsApp via Graph API
    Inclut: nom, photo de profil, et autres métadonnées disponibles
    
    Args:
        phone_number_id: ID du numéro de téléphone WhatsApp Business
        access_token: Token d'accès Graph API
        phone_number: Numéro de téléphone du contact (format international sans +)
    
    Returns:
        Dict avec les informations du contact (profile_picture_url, name, etc.)
    """
    try:
        client = await get_http_client()
        
        # Nettoyer le numéro de téléphone
        clean_phone = phone_number.replace("+", "").replace(" ", "").replace("-", "")
        
        # Essayer via l'endpoint /contacts avec tous les champs disponibles
        try:
            response = await client.get(
                f"{GRAPH_API_BASE}/{phone_number_id}/contacts",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "phone_numbers": clean_phone,
                    "fields": "profile_picture_url,name"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("data") and len(data["data"]) > 0:
                    contact_data = data["data"][0]
                    logger.info(f"✅ Contact info found via /contacts endpoint for {clean_phone}")
                    return {
                        "profile_picture_url": contact_data.get("profile_picture_url"),
                        "name": contact_data.get("name"),
                        "phone_number": clean_phone
                    }
        except httpx.HTTPStatusError as e:
            logger.debug(f"/contacts endpoint failed: {e.response.status_code}")
        except Exception as e:
            logger.debug(f"/contacts endpoint error: {e}")
        
        # Si aucune info trouvée, retourner un dict vide
        return {
            "profile_picture_url": None,
            "name": None,
            "phone_number": clean_phone
        }
        
    except Exception as e:
        logger.error(f"❌ Error fetching contact info for {phone_number}: {e}", exc_info=True)
        return {
            "profile_picture_url": None,
            "name": None,
            "phone_number": phone_number.replace("+", "").replace(" ", "").replace("-", "")
        }


def normalize_whatsapp_user_id(phone: str) -> str:
    """E.164 digits only, no + (aligné sur le stockage contacts / champ user Meta)."""
    if not phone:
        return ""
    return phone.replace("+", "").replace(" ", "").replace("-", "").strip()


# ============================================================================
# Block users (WhatsApp Cloud API) — POST/DELETE/GET .../block_users
# ============================================================================


@retry_on_network_error(max_attempts=2, min_wait=1.0, max_wait=3.0)
async def block_whatsapp_users(
    phone_number_id: str,
    access_token: str,
    user_phone_numbers: List[str],
) -> Dict[str, Any]:
    client = await get_http_client()
    users = [{"user": normalize_whatsapp_user_id(p)} for p in user_phone_numbers if normalize_whatsapp_user_id(p)]
    if not users:
        raise ValueError("no_valid_user_phone_numbers")
    payload = {"messaging_product": "whatsapp", "block_users": users}
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/block_users",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload,
    )
    if response.status_code >= 400:
        raise parse_whatsapp_error(response)
    return response.json()


@retry_on_network_error(max_attempts=2, min_wait=1.0, max_wait=3.0)
async def unblock_whatsapp_users(
    phone_number_id: str,
    access_token: str,
    user_phone_numbers: List[str],
) -> Dict[str, Any]:
    client = await get_http_client()
    users = [{"user": normalize_whatsapp_user_id(p)} for p in user_phone_numbers if normalize_whatsapp_user_id(p)]
    if not users:
        raise ValueError("no_valid_user_phone_numbers")
    payload = {"messaging_product": "whatsapp", "block_users": users}
    response = await client.request(
        "DELETE",
        f"{GRAPH_API_BASE}/{phone_number_id}/block_users",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload,
    )
    if response.status_code >= 400:
        raise parse_whatsapp_error(response)
    return response.json()


@retry_on_network_error(max_attempts=2, min_wait=1.0, max_wait=3.0)
async def list_blocked_whatsapp_users_page(
    phone_number_id: str,
    access_token: str,
    limit: int = 100,
    after: Optional[str] = None,
) -> Dict[str, Any]:
    client = await get_http_client()
    params: Dict[str, Any] = {"limit": min(max(limit, 1), 500)}
    if after:
        params["after"] = after
    response = await client.get(
        f"{GRAPH_API_BASE}/{phone_number_id}/block_users",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    if response.status_code >= 400:
        raise parse_whatsapp_error(response)
    return response.json()


async def list_all_blocked_wa_ids(
    phone_number_id: str,
    access_token: str,
    max_pages: int = 100,
) -> List[str]:
    """
    Agrège tous les wa_id bloqués pour ce numéro Business (pagination Graph).
    """
    out: List[str] = []
    after: Optional[str] = None
    for _ in range(max_pages):
        page = await list_blocked_whatsapp_users_page(
            phone_number_id, access_token, limit=100, after=after
        )
        for item in page.get("data") or []:
            wid = item.get("wa_id")
            if wid is not None:
                norm = normalize_whatsapp_user_id(str(wid))
                if norm:
                    out.append(norm)
        paging = page.get("paging") or {}
        cursors = paging.get("cursors") or {}
        after = cursors.get("after")
        if not after:
            break
    return out


def block_users_response_failed_for_input(body: Dict[str, Any], normalized_input: str) -> Optional[str]:
    """Si Meta renvoie l'utilisateur dans failed_users, extrait un message d'erreur."""
    bu = body.get("block_users") or {}
    failed = bu.get("failed_users") or []
    for f in failed:
        inp = normalize_whatsapp_user_id(str(f.get("input") or ""))
        if inp == normalized_input:
            errs = f.get("errors") or []
            if errs and isinstance(errs[0], dict):
                return str(errs[0].get("message") or "block_failed")
            return "block_failed"
    return None


@retry_on_network_error(max_attempts=2, min_wait=1.0, max_wait=3.0)
async def get_contact_profile_picture(
    phone_number_id: str,
    access_token: str,
    phone_number: str,
    evolution_instance: Optional[str] = None  # Ignoré, gardé pour compatibilité
) -> Optional[str]:
    """
    Récupère l'URL de l'image de profil d'un contact WhatsApp via Graph API
    
    Note: WhatsApp Cloud API a des limitations pour récupérer les images de profil.
    Cette fonction essaie plusieurs endpoints Graph API disponibles.
    
    Args:
        phone_number_id: ID du numéro de téléphone WhatsApp Business
        access_token: Token d'accès Graph API
        phone_number: Numéro de téléphone du contact (format international sans +)
        evolution_instance: Ignoré (gardé pour compatibilité)
    
    Returns:
        URL de l'image de profil ou None si non disponible
    """
    try:
        client = await get_http_client()
        
        # Nettoyer le numéro de téléphone
        clean_phone = phone_number.replace("+", "").replace(" ", "").replace("-", "")
        
        # Méthode 1: Essayer via l'endpoint /contacts
        try:
            response = await client.get(
                f"{GRAPH_API_BASE}/{phone_number_id}/contacts",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "phone_numbers": clean_phone,
                    "fields": "profile_picture_url"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("data") and len(data["data"]) > 0:
                    profile_url = data["data"][0].get("profile_picture_url")
                    if profile_url:
                        logger.info(f"✅ Profile picture found via /contacts endpoint for {clean_phone}")
                        return profile_url
        except httpx.HTTPStatusError as e:
            logger.debug(f"/contacts endpoint failed: {e.response.status_code}")
        except Exception as e:
            logger.debug(f"/contacts endpoint error: {e}")
        
        # Méthode 2: Essayer via le WABA (WhatsApp Business Account)
        try:
            phone_details = await get_phone_number_details(phone_number_id, access_token)
            waba_id = phone_details.get("waba_id") or phone_details.get("whatsapp_business_account_id")
            
            if waba_id:
                response = await client.get(
                    f"{GRAPH_API_BASE}/{waba_id}/contacts",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "phone_numbers": clean_phone,
                        "fields": "profile_picture_url"
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("data") and len(data["data"]) > 0:
                        profile_url = data["data"][0].get("profile_picture_url")
                        if profile_url:
                            logger.info(f"✅ Profile picture found via WABA endpoint for {clean_phone}")
                            return profile_url
        except Exception as e:
            logger.debug(f"WABA endpoint error: {e}")
        
        # Aucune image disponible via Graph API
        logger.debug(f"No profile picture available via Graph API for {phone_number}")
        return None
        
    except Exception as e:
        logger.error(f"❌ Error fetching profile picture for {phone_number}: {e}", exc_info=True)
        return None


# ============================================================================
# 8. MANAGEMENT DU WABA (WhatsApp Business Account)
# ============================================================================

async def get_waba_details(waba_id: str, access_token: str) -> Dict[str, Any]:
    """
    Récupère les détails d'un WABA
    GET /{WABA-ID}
    """
    client = await get_http_client()
    
    response = await client.get(
        f"{GRAPH_API_BASE}/{waba_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"fields": "id,name,timezone_id,message_template_namespace,account_review_status"}
    )
    response.raise_for_status()
    return response.json()


async def list_owned_wabas(business_id: str, access_token: str) -> Dict[str, Any]:
    """
    Liste les WABAs possédés par un Business Manager
    GET /{BUSINESS-ID}/owned_whatsapp_business_accounts
    """
    client = await get_http_client()
    
    response = await client.get(
        f"{GRAPH_API_BASE}/{business_id}/owned_whatsapp_business_accounts",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    response.raise_for_status()
    return response.json()


async def list_client_wabas(business_id: str, access_token: str) -> Dict[str, Any]:
    """
    Liste les WABAs partagés en tant que partenaire
    GET /{BUSINESS-ID}/client_whatsapp_business_accounts
    """
    client = await get_http_client()
    
    response = await client.get(
        f"{GRAPH_API_BASE}/{business_id}/client_whatsapp_business_accounts",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# 9. UTILITAIRES / SÉCURITÉ
# ============================================================================

async def debug_token(access_token: str, app_id: str, app_secret: str) -> Dict[str, Any]:
    """
    Vérifie un token d'accès (scopes, expiration, etc.)
    GET /debug_token
    """
    client = await get_http_client()
    
    # Générer un app access token
    app_token = f"{app_id}|{app_secret}"
    
    response = await client.get(
        f"{GRAPH_API_BASE}/debug_token",
        params={
            "input_token": access_token,
            "access_token": app_token
        }
    )
    response.raise_for_status()
    return response.json()


async def get_app_access_token(app_id: str, app_secret: str) -> Dict[str, Any]:
    """
    Récupère un app access token
    GET /oauth/access_token
    """
    client = await get_http_client()
    
    response = await client.get(
        f"https://graph.facebook.com/oauth/access_token",
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "client_credentials"
        }
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def validate_phone_number(phone: str) -> str:
    """
    Valide et normalise un numéro de téléphone WhatsApp
    Doit être au format international sans +
    Exemple: 33612345678
    """
    # Supprimer tous les caractères non numériques
    clean = "".join(c for c in phone if c.isdigit())
    
    # Si commence par +, le retirer
    if phone.startswith("+"):
        clean = phone[1:].replace(" ", "").replace("-", "")
    
    if not clean:
        raise ValueError("Invalid phone number")
    
    return clean

