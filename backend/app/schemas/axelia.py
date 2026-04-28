from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class AxeliaAttachment(BaseModel):
    mime_type: str
    data_base64: str = Field(..., max_length=12_000_000)


class AxeliaChatRequest(BaseModel):
    account_id: str
    conversation_id: str
    user_message: str = ""
    attachment: Optional[AxeliaAttachment] = None
    """Secteur métier pour orienter Axelia (priorités dans le prompt)."""
    sector: Optional[str] = None
    """Confirmation des tool_calls create_template (même flux que le Playground)."""
    approve_tool_calls: Optional[List[Dict[str, Any]]] = None

    @field_validator("user_message")
    @classmethod
    def strip_msg(cls, v: str) -> str:
        return v if isinstance(v, str) else ""


class AxeliaChatResponse(BaseModel):
    text: str
    generation_model: Optional[str] = None
    user_message_id: Optional[str] = None
    assistant_message_id: Optional[str] = None
    skills_used: Optional[List[str]] = None
    pending_tool_calls: Optional[List[Dict[str, Any]]] = None


class AxeliaConversationCreate(BaseModel):
    account_context: str = "__all__"
    title: Optional[str] = None


class AxeliaConversationPatch(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None
    hidden: Optional[bool] = None


class AxeliaMessageRating(BaseModel):
    rating: Optional[Literal[-1, 1]] = None
