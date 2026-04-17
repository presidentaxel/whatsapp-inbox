"""Parse ISO-8601 query params for asyncpg (requires datetime objects, not str)."""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException


def parse_optional_iso_datetime(
    value: datetime | str | None,
    *,
    param_name: str = "datetime",
) -> datetime | None:
    """
    Normalise cursor / updated_since venant de Query(...) ou du service.
    FastAPI peut livrer une str même avec annotation datetime selon versions / formats.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"invalid_datetime_parameter:{param_name}",
        ) from None
