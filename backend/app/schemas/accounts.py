from pydantic import BaseModel, Field
from typing import Optional


class AccountCreate(BaseModel):
    name: str
    slug: str = Field(..., pattern=r"^[a-z0-9\-_.]+$")
    phone_number: str | None = None
    phone_number_id: str
    access_token: str
    verify_token: str


class AccountGoogleDriveUpdate(BaseModel):
    google_drive_folder_id: Optional[str] = None
    google_drive_enabled: Optional[bool] = None


