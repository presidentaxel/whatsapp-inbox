import asyncio
import logging
from supabase import create_client
from starlette.concurrency import run_in_threadpool
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

async def supabase_execute(query_builder, timeout: float = 30.0):
    """
    Exécute une requête Supabase de manière asynchrone avec timeout
    
    Args:
        query_builder: Query builder Supabase
        timeout: Timeout en secondes (défaut: 30s)
    
    Returns:
        Résultat de la requête
    """
    try:
        return await asyncio.wait_for(
            run_in_threadpool(query_builder.execute),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error("Supabase query timeout after %ss", timeout)
        raise HTTPException(status_code=504, detail="database_timeout")
    except Exception as e:
        logger.error(f"Supabase query error: {e}", exc_info=True)
        # Réessayer une fois en cas d'erreur réseau
        try:
            return await asyncio.wait_for(
                run_in_threadpool(query_builder.execute),
                timeout=timeout
            )
        except Exception as retry_error:
            logger.error(f"Supabase query retry failed: {retry_error}", exc_info=True)
            raise HTTPException(status_code=503, detail="database_error")