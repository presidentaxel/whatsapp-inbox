"""
Module de cache simple en mémoire avec TTL.

Pour une solution production multi-instances, utiliser Redis.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)


class CacheEntry:
    """Entrée de cache avec expiration."""
    
    def __init__(self, value: Any, ttl_seconds: float):
        self.value = value
        self.expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


class SimpleCache:
    """Cache simple en mémoire."""
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Récupère une valeur du cache.
        
        Returns:
            La valeur si présente et non expirée, None sinon
        """
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                logger.debug(f"Cache MISS: {key}")
                return None
            
            if entry.is_expired():
                logger.debug(f"Cache EXPIRED: {key}")
                del self._cache[key]
                return None
            
            logger.debug(f"Cache HIT: {key}")
            return entry.value
    
    async def set(self, key: str, value: Any, ttl_seconds: float = 300):
        """
        Stocke une valeur dans le cache.
        
        Args:
            key: Clé de cache
            value: Valeur à stocker
            ttl_seconds: Durée de vie en secondes (défaut: 5 minutes)
        """
        async with self._lock:
            self._cache[key] = CacheEntry(value, ttl_seconds)
            logger.debug(f"Cache SET: {key} (TTL={ttl_seconds}s)")
    
    async def delete(self, key: str):
        """Supprime une entrée du cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache DELETE: {key}")
    
    async def clear(self):
        """Vide tout le cache."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cache cleared: {count} entries removed")
    
    async def cleanup_expired(self):
        """Supprime les entrées expirées."""
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            if expired_keys:
                logger.info(f"Cache cleanup: {len(expired_keys)} expired entries removed")
    
    def get_stats(self) -> dict:
        """Retourne des statistiques sur le cache."""
        return {
            "size": len(self._cache),
            "keys": list(self._cache.keys()),
        }


# Instance globale
_cache = SimpleCache()


async def get_cache() -> SimpleCache:
    """Retourne l'instance de cache globale."""
    return _cache


def cached(ttl_seconds: float = 300, key_prefix: str = ""):
    """
    Décorateur pour mettre en cache le résultat d'une fonction async.
    
    Args:
        ttl_seconds: Durée de vie du cache en secondes
        key_prefix: Préfixe pour la clé de cache
    
    Exemple:
        @cached(ttl_seconds=300, key_prefix="bot_profile")
        async def get_bot_profile(account_id: str):
            ...
    
    La clé de cache sera: "{key_prefix}:{arg1}:{arg2}:..."
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Construire la clé de cache
            cache_key_parts = [key_prefix or func.__name__]
            cache_key_parts.extend(str(arg) for arg in args)
            cache_key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(cache_key_parts)
            
            # Chercher dans le cache
            cached_value = await _cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Appeler la fonction et mettre en cache
            result = await func(*args, **kwargs)
            await _cache.set(cache_key, result, ttl_seconds)
            return result
        
        return wrapper
    return decorator


async def get_cached_or_fetch(
    key: str,
    fetch_func,
    *args,
    ttl_seconds: float = 300,
    **kwargs
) -> Any:
    """
    Récupère une valeur du cache, ou l'obtient via fetch_func si non présente.
    
    Args:
        key: Clé de cache
        fetch_func: Fonction async à appeler si cache miss
        ttl_seconds: Durée de vie du cache
        *args, **kwargs: Arguments pour fetch_func
    
    Returns:
        La valeur (du cache ou fraîchement récupérée)
    
    Exemple:
        profile = await get_cached_or_fetch(
            f"bot_profile:{account_id}",
            get_bot_profile_from_db,
            account_id,
            ttl_seconds=300
        )
    """
    cached_value = await _cache.get(key)
    if cached_value is not None:
        return cached_value
    
    result = await fetch_func(*args, **kwargs)
    await _cache.set(key, result, ttl_seconds)
    return result


async def invalidate_cache_pattern(pattern: str):
    """
    Invalide toutes les clés de cache correspondant au pattern.
    
    Args:
        pattern: Pattern simple (supporte uniquement le wildcard "*" à la fin)
    
    Exemple:
        await invalidate_cache_pattern("bot_profile:*")
        await invalidate_cache_pattern("account:123")
    """
    cache = await get_cache()
    async with cache._lock:
        keys_to_delete = []
        
        if pattern.endswith("*"):
            # Wildcard: supprimer toutes les clés qui commencent par le pattern
            prefix = pattern[:-1]
            keys_to_delete = [
                key for key in cache._cache.keys()
                if key.startswith(prefix)
            ]
        else:
            # Clé exacte
            if pattern in cache._cache:
                keys_to_delete = [pattern]
        
        for key in keys_to_delete:
            del cache._cache[key]
        
        if keys_to_delete:
            logger.info(f"Cache invalidated: {len(keys_to_delete)} entries matching '{pattern}'")

