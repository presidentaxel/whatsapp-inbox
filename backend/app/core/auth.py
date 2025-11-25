from types import SimpleNamespace

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.permissions import CurrentUser, load_current_user

http_bearer = HTTPBearer(auto_error=False)


async def _fetch_supabase_user(token: str) -> SimpleNamespace:
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="supabase_not_configured")

    url = settings.SUPABASE_URL.rstrip("/") + "/auth/v1/user"
    headers = {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {token}",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
        except httpx.HTTPError:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="supabase_unreachable")

    payload = response.json()
    return SimpleNamespace(
        id=payload.get("id"),
        email=payload.get("email"),
        user_metadata=payload.get("user_metadata") or {},
        app_metadata=payload.get("app_metadata") or {},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_token")

    token = credentials.credentials
    supabase_user = await _fetch_supabase_user(token)
    return await run_in_threadpool(load_current_user, supabase_user)

