from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class BotCustomField(BaseModel):
    id: Optional[str] = None
    label: str = Field(..., max_length=120)
    value: str = Field(..., max_length=2000)


class BotProfileUpdate(BaseModel):
    business_name: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    hours: Optional[str] = None
    knowledge_base: Optional[str] = None
    custom_fields: List[BotCustomField] = Field(default_factory=list)
    template_config: dict = Field(default_factory=dict)

