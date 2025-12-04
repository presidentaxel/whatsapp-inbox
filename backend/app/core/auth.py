from types import SimpleNamespace
import hashlib

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from app.core.cache import get_cached_or_fetch
from app.core.config import settings
from app.core.http_client import get_http_client
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
    
    # Utiliser le client HTTP partagé avec timeout et retry
    client = await get_http_client()
    timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
    
    # Retry en cas d'erreur réseau
    max_retries = 2
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            response = await client.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            break  # Succès, sortir de la boucle
        except httpx.TimeoutException as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"Supabase auth timeout (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="supabase_timeout")
        except httpx.ReadError as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"Supabase auth read error (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="supabase_network_error")
        except httpx.HTTPStatusError as e:
            # Erreur HTTP (401, 403, etc.) - ne pas retry
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
        except httpx.HTTPError as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"Supabase auth HTTP error (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="supabase_unreachable")
    
    if last_error:
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
    
    # Cache de l'utilisateur basé sur le hash du token (TTL: 2 minutes)
    # Cela réduit drastiquement les appels à Supabase pour /auth/me
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
    cache_key = f"auth_user:{token_hash}"
    
    async def fetch_and_load_user():
        supabase_user = await _fetch_supabase_user(token)
        return await run_in_threadpool(load_current_user, supabase_user)
    
    return await get_cached_or_fetch(
        key=cache_key,
        fetch_func=fetch_and_load_user,
        ttl_seconds=120  # 2 minutes - balance entre fraîcheur et performance
    )

