import asyncio
import logging
from supabase import create_client
from starlette.concurrency import run_in_threadpool
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

async def supabase_execute(query_builder, timeout: float = 30.0, retries: int = 2):
    """
    Exécute une requête Supabase de manière asynchrone avec timeout et retry
    
    Args:
        query_builder: Query builder Supabase
        timeout: Timeout en secondes (défaut: 30s)
        retries: Nombre de tentatives en cas d'erreur réseau (défaut: 2)
    
    Returns:
        Résultat de la requête
    """
    last_error = None
    
    for attempt in range(retries + 1):
        try:
            return await asyncio.wait_for(
                run_in_threadpool(query_builder.execute),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Supabase query timeout after {timeout}s (attempt {attempt + 1}/{retries + 1})")
            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))  # Backoff exponentiel
                continue
            logger.error("Supabase query timeout after all retries")
            raise HTTPException(status_code=504, detail="database_timeout")
        except Exception as e:
            last_error = e
            # Vérifier si c'est une erreur réseau récupérable
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            # Détecter les erreurs de connexion récupérables
            is_network_error = any(keyword in error_str for keyword in [
                "readerror", "connecterror", "timeout", "10035", "socket", "connection"
            ])
            
            # ConnectionTerminated est une erreur gRPC normale lors des reconnexions Supabase
            # On la traite comme récupérable et on la log en DEBUG pour éviter le bruit
            is_connection_terminated = (
                "connectionterminated" in error_str or 
                "ConnectionTerminated" in str(e) or
                error_type == "ConnectionTerminated"
            )
            
            if is_network_error and attempt < retries:
                # ConnectionTerminated est une reconnexion normale, on log en DEBUG
                if is_connection_terminated:
                    logger.debug(f"Supabase connection terminated (attempt {attempt + 1}/{retries + 1}), reconnecting...")
                else:
                    logger.warning(f"Supabase network error (attempt {attempt + 1}/{retries + 1}): {e}")
                await asyncio.sleep(0.5 * (attempt + 1))  # Backoff exponentiel
                continue
            else:
                # Si toutes les tentatives ont échoué, on log en ERROR
                if is_connection_terminated and attempt >= retries:
                    logger.warning(f"Supabase connection terminated after {retries + 1} attempts, may indicate network issues")
                else:
                    logger.error(f"Supabase query error: {e}", exc_info=True)
                if attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise HTTPException(status_code=503, detail=f"database_error: {str(e)}")
    
    # Ne devrait jamais arriver ici, mais au cas où
    if last_error:
        raise HTTPException(status_code=503, detail=f"database_error: {str(last_error)}")
    raise HTTPException(status_code=503, detail="database_error")