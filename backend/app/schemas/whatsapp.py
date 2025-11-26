"""
Schémas Pydantic pour l'API WhatsApp Business
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# MESSAGES
# ============================================================================

class SendTextMessageRequest(BaseModel):
    to: str = Field(..., description="Numéro WhatsApp du destinataire")
    text: str = Field(..., description="Contenu du message")
    preview_url: bool = Field(False, description="Activer l'aperçu des URLs")


class SendMediaMessageRequest(BaseModel):
    to: str = Field(..., description="Numéro WhatsApp du destinataire")
    media_type: str = Field(..., description="Type de média: image, audio, video, document")
    media_id: Optional[str] = Field(None, description="ID du média déjà uploadé")
    media_link: Optional[str] = Field(None, description="URL du média")
    caption: Optional[str] = Field(None, description="Légende du média")
    filename: Optional[str] = Field(None, description="Nom du fichier (pour documents)")
    
    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, v):
        allowed = ["image", "audio", "video", "document"]
        if v not in allowed:
            raise ValueError(f"media_type must be one of: {', '.join(allowed)}")
        return v


class TemplateComponent(BaseModel):
    type: str = Field(..., description="Type de composant")
    parameters: Optional[List[Dict[str, Any]]] = Field(None, description="Paramètres du composant")


class SendTemplateMessageRequest(BaseModel):
    to: str = Field(..., description="Numéro WhatsApp du destinataire")
    template_name: str = Field(..., description="Nom du template")
    language_code: str = Field("en", description="Code langue (ex: en, fr, es)")
    components: Optional[List[Dict[str, Any]]] = Field(None, description="Composants du template")


class InteractiveButton(BaseModel):
    id: str = Field(..., description="ID unique du bouton")
    title: str = Field(..., description="Texte du bouton")


class SendInteractiveButtonsRequest(BaseModel):
    to: str = Field(..., description="Numéro WhatsApp du destinataire")
    body_text: str = Field(..., description="Texte principal du message")
    buttons: List[InteractiveButton] = Field(..., description="Liste des boutons (max 3)")
    header_text: Optional[str] = Field(None, description="Texte d'en-tête")
    footer_text: Optional[str] = Field(None, description="Texte de pied de page")
    
    @field_validator("buttons")
    @classmethod
    def validate_buttons(cls, v):
        if len(v) > 3:
            raise ValueError("Maximum 3 buttons allowed")
        return v


class ListRow(BaseModel):
    id: str = Field(..., description="ID unique de la ligne")
    title: str = Field(..., description="Titre de la ligne")
    description: Optional[str] = Field(None, description="Description de la ligne")


class ListSection(BaseModel):
    title: str = Field(..., description="Titre de la section")
    rows: List[ListRow] = Field(..., description="Lignes de la section")


class SendInteractiveListRequest(BaseModel):
    to: str = Field(..., description="Numéro WhatsApp du destinataire")
    body_text: str = Field(..., description="Texte principal du message")
    button_text: str = Field(..., description="Texte du bouton")
    sections: List[ListSection] = Field(..., description="Sections de la liste")
    header_text: Optional[str] = Field(None, description="Texte d'en-tête")
    footer_text: Optional[str] = Field(None, description="Texte de pied de page")


# ============================================================================
# PHONE NUMBERS
# ============================================================================

class RegisterPhoneRequest(BaseModel):
    pin: str = Field(..., description="PIN à 6 chiffres pour la 2FA")
    
    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v):
        if not v.isdigit() or len(v) != 6:
            raise ValueError("PIN must be exactly 6 digits")
        return v


class RequestVerificationCodeRequest(BaseModel):
    code_method: str = Field("SMS", description="Méthode: SMS ou VOICE")
    language: str = Field("en_US", description="Langue du message")
    
    @field_validator("code_method")
    @classmethod
    def validate_code_method(cls, v):
        if v not in ["SMS", "VOICE"]:
            raise ValueError("code_method must be SMS or VOICE")
        return v


class VerifyCodeRequest(BaseModel):
    code: str = Field(..., description="Code de vérification reçu")


# ============================================================================
# BUSINESS PROFILE
# ============================================================================

class UpdateBusinessProfileRequest(BaseModel):
    about: Optional[str] = Field(None, max_length=139, description="Description courte")
    address: Optional[str] = Field(None, description="Adresse")
    description: Optional[str] = Field(None, max_length=512, description="Description longue")
    email: Optional[str] = Field(None, description="Email")
    websites: Optional[List[str]] = Field(None, description="Sites web")
    vertical: Optional[str] = Field(None, description="Secteur d'activité")
    profile_picture_handle: Optional[str] = Field(None, description="Media ID de l'image de profil")


# ============================================================================
# MESSAGE TEMPLATES
# ============================================================================

class TemplateButton(BaseModel):
    type: str = Field(..., description="Type de bouton: URL, PHONE_NUMBER, QUICK_REPLY")
    text: str = Field(..., description="Texte du bouton")
    url: Optional[str] = Field(None, description="URL (pour type URL)")
    phone_number: Optional[str] = Field(None, description="Numéro (pour type PHONE_NUMBER)")


class TemplateComponentCreate(BaseModel):
    type: str = Field(..., description="Type: HEADER, BODY, FOOTER, BUTTONS")
    format: Optional[str] = Field(None, description="Format pour HEADER: TEXT, IMAGE, VIDEO, DOCUMENT")
    text: Optional[str] = Field(None, description="Texte du composant")
    buttons: Optional[List[TemplateButton]] = Field(None, description="Boutons (pour type BUTTONS)")
    
    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        allowed = ["HEADER", "BODY", "FOOTER", "BUTTONS"]
        if v not in allowed:
            raise ValueError(f"type must be one of: {', '.join(allowed)}")
        return v


class CreateMessageTemplateRequest(BaseModel):
    name: str = Field(..., description="Nom du template (lowercase, underscores)")
    category: str = Field(..., description="Catégorie: AUTHENTICATION, MARKETING, UTILITY")
    language: str = Field(..., description="Code langue (ex: en, fr_FR)")
    components: List[TemplateComponentCreate] = Field(..., description="Composants du template")
    
    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        allowed = ["AUTHENTICATION", "MARKETING", "UTILITY"]
        if v not in allowed:
            raise ValueError(f"category must be one of: {', '.join(allowed)}")
        return v
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        # Template names must be lowercase with underscores
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Template name must contain only alphanumeric characters, underscores, and hyphens")
        return v.lower()


class DeleteMessageTemplateRequest(BaseModel):
    name: str = Field(..., description="Nom du template à supprimer")
    hsm_id: Optional[str] = Field(None, description="ID HSM du template (optionnel)")


# ============================================================================
# WEBHOOKS
# ============================================================================

class WebhookSubscriptionResponse(BaseModel):
    success: bool = Field(..., description="Succès de l'opération")


# ============================================================================
# RESPONSES STANDARDS
# ============================================================================

class WhatsAppMessageResponse(BaseModel):
    messaging_product: str
    contacts: Optional[List[Dict[str, Any]]] = None
    messages: Optional[List[Dict[str, Any]]] = None


class WhatsAppErrorResponse(BaseModel):
    error: Dict[str, Any]


class MediaUploadResponse(BaseModel):
    id: str = Field(..., description="Media ID")


class PhoneNumberDetails(BaseModel):
    verified_name: Optional[str] = None
    display_phone_number: Optional[str] = None
    quality_rating: Optional[str] = None
    code_verification_status: Optional[str] = None


class BusinessProfileResponse(BaseModel):
    data: List[Dict[str, Any]]


class WABADetails(BaseModel):
    id: str
    name: Optional[str] = None
    timezone_id: Optional[str] = None
    message_template_namespace: Optional[str] = None
    account_review_status: Optional[str] = None


class TokenDebugResponse(BaseModel):
    data: Dict[str, Any]

