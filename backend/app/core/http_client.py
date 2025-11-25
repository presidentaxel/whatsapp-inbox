"""
Module de gestion centralisée des clients HTTP avec configuration optimisée.
"""
import httpx
from typing import Optional

_http_client: Optional[httpx.AsyncClient] = None


def get_timeout_config() -> httpx.Timeout:
    """
    Configuration des timeouts pour les appels externes.
    
    - connect: temps max pour établir une connexion TCP/TLS
    - read: temps max pour lire la réponse complète
    - write: temps max pour envoyer la requête
    - pool: temps max pour obtenir une connexion du pool
    """
    return httpx.Timeout(
        connect=3.0,  # 3s pour se connecter
        read=10.0,    # 10s pour lire la réponse
        write=5.0,    # 5s pour écrire
        pool=5.0      # 5s pour obtenir une connexion du pool
    )


def get_limits_config() -> httpx.Limits:
    """
    Configuration des limites de connexion.
    
    - max_connections: nombre total de connexions simultanées
    - max_keepalive_connections: nombre de connexions à garder ouvertes
    """
    return httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20
    )


async def get_http_client() -> httpx.AsyncClient:
    """
    Retourne un client HTTP partagé avec connection pooling.
    
    Avantages:
    - Réutilisation des connexions TCP/TLS (plus rapide)
    - Configuration centralisée des timeouts
    - Moins de ressources consommées
    """
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=get_timeout_config(),
            limits=get_limits_config(),
            http2=True,  # Active HTTP/2 pour de meilleures performances
            follow_redirects=True
        )
    return _http_client


async def close_http_client():
    """
    Ferme proprement le client HTTP.
    À appeler lors du shutdown de l'application.
    """
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


async def get_http_client_for_media() -> httpx.AsyncClient:
    """
    Client HTTP spécifique pour les téléchargements de médias.
    Timeouts plus longs car les fichiers peuvent être volumineux.
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=5.0,
            read=30.0,  # 30s pour les gros fichiers
            write=10.0,
            pool=5.0
        ),
        limits=get_limits_config(),
        http2=True
    )

