from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    name: str
    slug: str = Field(..., pattern=r"^[a-z0-9\-_.]+$")
    phone_number: str | None = None
    phone_number_id: str
    access_token: str
    verify_token: str


