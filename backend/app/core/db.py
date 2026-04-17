import asyncio
import logging
from typing import Dict, Optional, Union

import httpx
from httpx import Timeout
from postgrest._sync.client import SyncPostgrestClient
from postgrest.exceptions import APIError
from postgrest.utils import SyncClient as PostgrestHttpxClient
from supabase import create_client
from starlette.concurrency import run_in_threadpool
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


def _patch_postgrest_use_http11() -> None:
    """
    postgrest-py uses HTTP/2 by default. Supabase/edge occasionally drops HTTP/2
    streams (httpx.RemoteProtocolError: Server disconnected). HTTP/1.1 avoids that.
    """

    def create_session(
        self,
        base_url: str,
        headers: Dict[str, str],
        timeout: Union[int, float, Timeout],
        verify: bool = True,
        proxy: Optional[str] = None,
    ) -> PostgrestHttpxClient:
        return PostgrestHttpxClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            verify=verify,
            proxy=proxy,
            follow_redirects=True,
            http2=False,
        )

    SyncPostgrestClient.create_session = create_session  # type: ignore[method-assign]


_patch_postgrest_use_http11()


def _is_transient_supabase_edge_response(exc: BaseException) -> bool:
    """
    PostgREST attend du JSON ; Cloudflare (ou l'edge) peut renvoyer du HTML 400/502,
    ce qui remonte comme APIError « JSON could not be generated » avec du HTML dans details.
    Souvent transitoire ou lié à une requête trop longue / WAF — on retente.
    """
    if isinstance(exc, APIError):
        det = str(exc.details or "")
        msg = str(exc.message or "")
        if "<html" in det.lower() or "cloudflare" in det.lower():
            try:
                c = int(exc.code) if exc.code is not None else None
            except (TypeError, ValueError):
                c = None
            # Edge / WAF : souvent 400 avec corps HTML ; parfois autre code.
            return c is None or c in (400, 403, 404, 429, 502, 503, 504)
        if "json could not be generated" in msg.lower() and (
            "<html" in det.lower() or "cloudflare" in det.lower()
        ):
            return True
    low = str(exc).lower()
    return "json could not be generated" in low and (
        "<html" in low or "cloudflare" in low
    )


supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

# Taille max des listes dans .in_() pour éviter des URLs trop longues (limite Cloudflare ~8KB)
SUPABASE_IN_CLAUSE_CHUNK_SIZE = 40

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
            is_edge_html = _is_transient_supabase_edge_response(e)

            is_network_error = any(keyword in error_str for keyword in [
                "readerror",
                "connecterror",
                "timeout",
                "10035",
                "socket",
                "connection",
                "disconnected",
                "remoteprotocol",
                "server disconnected",
            ]) or isinstance(
                e,
                (
                    httpx.RemoteProtocolError,
                    httpx.ReadError,
                    httpx.ConnectError,
                    httpx.ConnectTimeout,
                    httpx.ReadTimeout,
                ),
            )
            
            # ConnectionTerminated est une erreur gRPC normale lors des reconnexions Supabase
            # On la traite comme récupérable et on la log en DEBUG pour éviter le bruit
            is_connection_terminated = (
                "connectionterminated" in error_str or 
                "ConnectionTerminated" in str(e) or
                error_type == "ConnectionTerminated"
            )
            
            if (is_network_error or is_edge_html) and attempt < retries:
                # ConnectionTerminated est une reconnexion normale, on log en DEBUG
                if is_connection_terminated:
                    logger.debug(f"Supabase connection terminated (attempt {attempt + 1}/{retries + 1}), reconnecting...")
                elif is_edge_html:
                    logger.warning(
                        "Supabase edge returned non-JSON (often Cloudflare HTML); retrying "
                        f"(attempt {attempt + 1}/{retries + 1}). "
                        "If this persists: check SUPABASE_URL, shorten filters / reduce .in_() size, "
                        "or inspect Supabase project status."
                    )
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