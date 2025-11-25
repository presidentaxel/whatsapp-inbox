"""
Module de retry logic avec backoff exponentiel pour les appels externes.
"""
import logging
from functools import wraps
from typing import TypeVar, Callable, Any

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_on_network_error(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 5.0
):
    """
    Décorateur pour retry automatique en cas d'erreur réseau.
    
    Args:
        max_attempts: Nombre maximum de tentatives
        min_wait: Temps d'attente minimum entre les tentatives (secondes)
        max_wait: Temps d'attente maximum entre les tentatives (secondes)
    
    Exemple:
        @retry_on_network_error(max_attempts=3)
        async def call_external_api():
            ...
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )


def retry_on_server_error(
    max_attempts: int = 2,
    min_wait: float = 0.5,
    max_wait: float = 2.0
):
    """
    Décorateur pour retry automatique en cas d'erreur serveur (5xx).
    
    Args:
        max_attempts: Nombre maximum de tentatives
        min_wait: Temps d'attente minimum entre les tentatives (secondes)
        max_wait: Temps d'attente maximum entre les tentatives (secondes)
    
    Exemple:
        @retry_on_server_error(max_attempts=2)
        async def call_external_api():
            ...
    """
    def should_retry_on_status(exception):
        """Retry uniquement sur les erreurs 5xx et timeout."""
        if isinstance(exception, httpx.HTTPStatusError):
            return exception.response.status_code >= 500
        return isinstance(exception, (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.ConnectError
        ))
    
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((
            httpx.HTTPStatusError,
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.ConnectError,
        )),
        retry=should_retry_on_status,
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )


async def execute_with_retry(
    func: Callable[..., Any],
    *args,
    max_attempts: int = 3,
    **kwargs
) -> Any:
    """
    Execute une fonction avec retry automatique.
    Alternative fonctionnelle au décorateur.
    
    Args:
        func: Fonction async à exécuter
        max_attempts: Nombre maximum de tentatives
        *args, **kwargs: Arguments à passer à la fonction
    
    Returns:
        Le résultat de la fonction
    
    Raises:
        RetryError: Si toutes les tentatives ont échoué
    
    Exemple:
        result = await execute_with_retry(
            my_api_call,
            param1="value",
            max_attempts=3
        )
    """
    retry_decorator = retry_on_network_error(max_attempts=max_attempts)
    retryable_func = retry_decorator(func)
    return await retryable_func(*args, **kwargs)

