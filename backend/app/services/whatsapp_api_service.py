"""
Service complet pour l'API WhatsApp Business Cloud API
Implémente tous les endpoints de l'API Meta WhatsApp
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.core.http_client import get_http_client, get_http_client_for_media
from app.core.retry import retry_on_network_error

logger = logging.getLogger(__name__)

# Version de l'API WhatsApp
WHATSAPP_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"


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
    
    if components:
        template_payload["components"] = components
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template_payload
    }
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload
    )
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
    
    with open(file_path, "rb") as f:
        files = {
            "file": (file_path.split("/")[-1], f, mime_type),
            "messaging_product": (None, "whatsapp"),
            "type": (None, mime_type)
        }
        
        response = await client.post(
            f"{GRAPH_API_BASE}/{phone_number_id}/media",
            headers={"Authorization": f"Bearer {access_token}"},
            files=files
        )
    
    response.raise_for_status()
    return response.json()


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
    """
    client = await get_http_client_for_media()
    
    files = {
        "file": (filename, file_content, mime_type),
        "messaging_product": (None, "whatsapp"),
        "type": (None, mime_type)
    }
    
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

async def get_business_profile(phone_number_id: str, access_token: str) -> Dict[str, Any]:
    """
    Récupère le profil business WhatsApp
    GET /{PHONE_NUMBER_ID}/whatsapp_business_profile
    """
    client = await get_http_client()
    
    response = await client.get(
        f"{GRAPH_API_BASE}/{phone_number_id}/whatsapp_business_profile",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"fields": "about,address,description,email,profile_picture_url,websites,vertical"}
    )
    response.raise_for_status()
    return response.json()


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
    
    payload = {
        "messaging_product": "whatsapp",
        **profile_data
    }
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/whatsapp_business_profile",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# 5. TEMPLATES DE MESSAGES
# ============================================================================

async def list_message_templates(
    waba_id: str,
    access_token: str,
    limit: int = 100,
    after: Optional[str] = None
) -> Dict[str, Any]:
    """
    Liste les templates de messages
    GET /{WABA-ID}/message_templates
    """
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
    return response.json()


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
    
    response = await client.post(
        f"{GRAPH_API_BASE}/{waba_id}/message_templates",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload
    )
    response.raise_for_status()
    return response.json()


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
# 7. MANAGEMENT DU WABA (WhatsApp Business Account)
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
# 8. UTILITAIRES / SÉCURITÉ
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

